"""N.A.N.I. V2 — OpenRouter Multi-Model Provider
Unified client for OpenRouter inference API (GPT-4o, Claude 3.5, Llama 3.3, Mistral).
"""

import time
from typing import Any

import httpx

from nani.core.logger import logger as global_logger
from nani.models.base import (
    ModelCapability,
    ModelMessage,
    ModelProvider,
    ModelRequest,
    ModelResponse,
)

DEFAULT_OPENROUTER_MODEL = "openai/gpt-4o"
FAST_OPENROUTER_MODEL = "meta-llama/llama-3.3-70b-instruct"
REASONING_OPENROUTER_MODEL = "deepseek/deepseek-r1"
OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"


class OpenRouterProvider(ModelProvider):
    """OpenRouter flexible aggregator provider."""

    def __init__(
        self,
        api_key: str | None = None,
        default_model: str = DEFAULT_OPENROUTER_MODEL,
        fast_model: str = FAST_OPENROUTER_MODEL,
        reasoning_model: str = REASONING_OPENROUTER_MODEL,
        timeout_seconds: float = 60.0,
    ) -> None:
        self.api_key = api_key or ""
        self.default_model = default_model
        self.fast_model = fast_model
        self.reasoning_model = reasoning_model
        self.timeout_seconds = timeout_seconds

    @property
    def name(self) -> str:
        return "openrouter"

    @property
    def supported_capabilities(self) -> list[ModelCapability]:
        return [
            ModelCapability.FAST,
            ModelCapability.REASONING,
            ModelCapability.CODING,
            ModelCapability.VISION,
            ModelCapability.RESEARCH,
            ModelCapability.VERIFICATION,
        ]

    def _select_model_for_capability(self, capability: ModelCapability) -> str:
        if capability == ModelCapability.FAST:
            return self.fast_model
        if capability in (ModelCapability.REASONING, ModelCapability.VERIFICATION):
            return self.reasoner_or_default()
        return self.default_model

    def reasoner_or_default(self) -> str:
        return self.reasoning_model or self.default_model

    def _convert_messages(
        self, messages: list[ModelMessage], system_prompt: str | None
    ) -> list[dict[str, Any]]:
        formatted: list[dict[str, Any]] = []
        if system_prompt:
            formatted.append({"role": "system", "content": system_prompt})
        for msg in messages:
            if msg.images_base64:
                # Multimodal OpenRouter format
                parts: list[dict[str, Any]] = [{"type": "text", "text": msg.content}]
                for img in msg.images_base64:
                    parts.append(
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/png;base64,{img}"},
                        }
                    )
                formatted.append({"role": msg.role, "content": parts})
            else:
                formatted.append({"role": msg.role, "content": msg.content})
        return formatted

    async def generate(self, request: ModelRequest) -> ModelResponse:
        if not self.api_key:
            raise ValueError("OpenRouter API key is not configured.")

        model = self._select_model_for_capability(request.capability)
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/nani-ai/nani",
            "X-Title": "NANI V2 Sovereign Assistant",
        }

        messages = self._convert_messages(request.messages, request.system_prompt)
        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
        }

        if request.response_json_schema:
            payload["response_format"] = {"type": "json_object"}

        t_start = time.monotonic()
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            resp = await client.post(OPENROUTER_API_URL, headers=headers, json=payload)

        latency_ms = int((time.monotonic() - t_start) * 1000)

        if resp.status_code != 200:
            err_msg = (
                f"OpenRouter API request failed with status {resp.status_code}: {resp.text[:500]}"
            )
            global_logger.log_event(
                event_type="MODEL_ERROR",
                status="ERROR",
                data={"provider": "openrouter", "model": model, "error": err_msg},
            )
            raise RuntimeError(err_msg)

        data = resp.json()
        choices = data.get("choices", [])
        if not choices:
            raise RuntimeError("OpenRouter returned empty choices in response.")

        choice = choices[0]
        text_content = choice.get("message", {}).get("content", "")

        usage = data.get("usage", {})
        tokens_used = usage.get("total_tokens")

        return ModelResponse(
            content=text_content,
            provider_name=self.name,
            model_name=model,
            tokens_used=tokens_used,
            latency_ms=latency_ms,
            raw_response=data,
        )

    async def is_available(self) -> bool:
        return bool(self.api_key and self.api_key.strip())
