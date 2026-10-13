"""N.A.N.I. LLM Inference Engine with Smart Free Token Rotator
Seamlessly manages local Ollama and free cloud providers with auto-failover.
"""

import os
from typing import Generator, List, Dict, Any, Optional
from openai import OpenAI
from nani.config import Config
from nani.core.persona import get_system_prompt
from nani.core.rotator import TokenRotator

class LLMEngine:
    def __init__(self, memory=None):
        self.memory = memory
        self.provider = Config.AI_PROVIDER
        self.model = Config.MODEL_NAME
        self.rotator = TokenRotator()
        self.direct_client = self._init_direct_client()

    def _init_direct_client(self) -> Optional[OpenAI]:
        """Initializes a specific client if user explicitly specified one instead of 'auto'."""
        if self.provider == "ollama":
            return OpenAI(base_url=Config.OLLAMA_BASE_URL, api_key="ollama", timeout=20.0)
        elif self.provider == "groq" and Config.GROQ_API_KEY:
            return OpenAI(base_url="https://api.groq.com/openai/v1", api_key=Config.GROQ_API_KEY, timeout=20.0)
        elif self.provider == "gemini" and Config.GEMINI_API_KEY:
            return OpenAI(base_url="https://generativelanguage.googleapis.com/v1beta/openai/", api_key=Config.GEMINI_API_KEY, timeout=20.0)
        elif self.provider == "openrouter" and Config.OPENROUTER_API_KEY:
            return OpenAI(base_url="https://openrouter.ai/api/v1", api_key=Config.OPENROUTER_API_KEY, timeout=20.0)
        elif self.provider == "deepseek" and Config.DEEPSEEK_API_KEY:
            return OpenAI(base_url="https://api.deepseek.com", api_key=Config.DEEPSEEK_API_KEY, timeout=20.0)
        elif Config.API_KEY:
            return OpenAI(base_url=Config.BASE_URL, api_key=Config.API_KEY, timeout=20.0)
        return None

    def generate_stream(self, prompt: str, system_override: Optional[str] = None) -> Generator[str, None, None]:
        """Streams tokens using the auto-failover rotator or specified provider."""
        user_profile = self.memory.get_profile_summary() if self.memory else ""
        system = system_override or get_system_prompt(user_profile=user_profile)

        messages = [{"role": "system", "content": system}]
        if self.memory:
            history = self.memory.get_recent_history(limit=4)
            messages.extend(history)
        messages.append({"role": "user", "content": prompt})

        # If explicitly using direct client
        if self.provider != "auto" and self.direct_client:
            try:
                response = self.direct_client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    stream=True,
                    temperature=0.6,
                )
                for chunk in response:
                    content = chunk.choices[0].delta.content or ""
                    if content:
                        yield content
                return
            except Exception as e:
                yield f"\n[N.A.N.I. Alert]: Provider {self.provider} error: {str(e)}\nSwitching to Token Rotator failover...\n"

        # Auto-failover rotator path
        yield from self.rotator.chat_completion_stream(messages)

    def generate(self, prompt: str, system_override: Optional[str] = None) -> str:
        """Synchronously generates a complete response with failover."""
        user_profile = self.memory.get_profile_summary() if self.memory else ""
        system = system_override or get_system_prompt(user_profile=user_profile)

        messages = [{"role": "system", "content": system}]
        if self.memory:
            history = self.memory.get_recent_history(limit=4)
            messages.extend(history)
        messages.append({"role": "user", "content": prompt})

        result = self.rotator.chat_completion(messages)
        if result["success"]:
            return result["content"]
        else:
            return "".join(self.generate_stream(prompt, system_override))
