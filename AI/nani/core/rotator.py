"""N.A.N.I. Free Token Rotator & Auto-Failover Engine
Manages a pool of free-tier AI providers and automatically switches on rate limits (HTTP 429) or errors.
"""

import os
import time
import httpx
from typing import List, Dict, Any, Optional, Generator
from openai import OpenAI
from nani.config import Config

class ProviderNode:
    def __init__(self, name: str, base_url: str, api_key: str, default_model: str, priority: int = 1):
        self.name = name
        self.base_url = base_url
        self.api_key = api_key
        self.default_model = default_model
        self.priority = priority
        self.cooldown_until = 0.0
        self.error_count = 0
        self.total_calls = 0

    @property
    def is_configured(self) -> bool:
        if self.name == "ollama":
            return True
        return bool(self.api_key and self.api_key.strip())

    @property
    def is_available(self) -> bool:
        return self.is_configured and time.time() > self.cooldown_until

    def mark_cooldown(self, seconds: int = 60):
        self.cooldown_until = time.time() + seconds
        self.error_count += 1

    def get_client(self) -> OpenAI:
        key = self.api_key if self.api_key else "dummy-key"
        return OpenAI(base_url=self.base_url, api_key=key, timeout=20.0)

class TokenRotator:
    def __init__(self):
        self.providers: List[ProviderNode] = self._setup_providers()

    def _setup_providers(self) -> List[ProviderNode]:
        """Initializes the priority waterfall of free/cheap AI providers."""
        nodes = [
            # 1. Groq Free Tier (Blazing fast, generous RPM)
            ProviderNode(
                name="groq",
                base_url="https://api.groq.com/openai/v1",
                api_key=Config.GROQ_API_KEY,
                default_model="llama-3.3-70b-versatile",
                priority=1
            ),
            # 2. Google Gemini Free Tier via OpenAI endpoint
            ProviderNode(
                name="gemini",
                base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
                api_key=Config.GEMINI_API_KEY,
                default_model="gemini-3.1-flash-lite",
                priority=1  # Since user provided this key, prioritize it!
            ),
            # 3. OpenRouter Free Tier (:free models)
            ProviderNode(
                name="openrouter",
                base_url="https://openrouter.ai/api/v1",
                api_key=Config.OPENROUTER_API_KEY,
                default_model="deepseek/deepseek-r1:free",
                priority=3
            ),
            # 4. DeepSeek Direct API
            ProviderNode(
                name="deepseek",
                base_url="https://api.deepseek.com",
                api_key=Config.DEEPSEEK_API_KEY,
                default_model="deepseek-chat",
                priority=4
            ),
            # 5. Local Ollama (Always available offline, $0 cost)
            ProviderNode(
                name="ollama",
                base_url=Config.OLLAMA_BASE_URL,
                api_key="",
                default_model="qwen2.5:3b",
                priority=10
            ),
        ]
        # Sort by priority
        return sorted(nodes, key=lambda n: n.priority)

    def get_available_providers(self) -> List[ProviderNode]:
        """Returns all configured and non-cooling providers."""
        return [p for p in self.providers if p.is_available]

    def chat_completion(self, messages: List[Dict[str, str]], model_override: Optional[str] = None, temperature: float = 0.6) -> Dict[str, Any]:
        """Executes a chat completion with automatic failover across all providers."""
        errors_logged = []

        for provider in self.get_available_providers():
            target_model = model_override or provider.default_model
            try:
                client = provider.get_client()
                response = client.chat.completions.create(
                    model=target_model,
                    messages=messages,
                    temperature=temperature,
                    stream=False
                )
                provider.total_calls += 1
                content = response.choices[0].message.content or ""
                return {
                    "success": True,
                    "provider": provider.name,
                    "model": target_model,
                    "content": content
                }
            except Exception as e:
                err_str = str(e)
                errors_logged.append(f"{provider.name}: {err_str[:120]}")
                # Rate limit or quota error: put in cooldown
                if "429" in err_str or "rate_limit" in err_str.lower() or "quota" in err_str.lower():
                    provider.mark_cooldown(seconds=90)
                else:
                    provider.mark_cooldown(seconds=30)
                continue

        # If all providers failed or none configured
        return {
            "success": False,
            "provider": "none",
            "model": "none",
            "content": f"[N.A.N.I. Failover Warning]: All providers exhausted or unconfigured.\nAttempted: {'; '.join(errors_logged)}"
        }

    def chat_completion_stream(self, messages: List[Dict[str, str]], model_override: Optional[str] = None, temperature: float = 0.6) -> Generator[str, None, None]:
        """Streams tokens from the best available provider with automatic fallback."""
        for provider in self.get_available_providers():
            target_model = model_override or provider.default_model
            try:
                client = provider.get_client()
                response = client.chat.completions.create(
                    model=target_model,
                    messages=messages,
                    temperature=temperature,
                    stream=True
                )
                for chunk in response:
                    delta = chunk.choices[0].delta.content or ""
                    if delta:
                        yield delta
                provider.total_calls += 1
                return
            except Exception as e:
                err_str = str(e)
                if "429" in err_str or "rate_limit" in err_str.lower():
                    provider.mark_cooldown(seconds=90)
                else:
                    provider.mark_cooldown(seconds=30)
                continue

        yield "\n[N.A.N.I. Rotator]: All providers currently unavailable. Check your API keys in .env or start local Ollama."

    def get_status_summary(self) -> List[Dict[str, Any]]:
        status = []
        for p in self.providers:
            state = "Ready" if p.is_available else ("Cooldown" if p.is_configured else "Unconfigured")
            status.append({
                "provider": p.name,
                "model": p.default_model,
                "state": state,
                "calls": p.total_calls,
                "errors": p.error_count
            })
        return status
