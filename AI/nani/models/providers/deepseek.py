"""N.A.N.I. V2 — DeepSeek AI Model Provider
Direct async REST client for DeepSeek inference API using OpenAI-compatible payload.
Supports DeepSeek-R1 (deepseek-reasoner) and DeepSeek-V3 (deepseek-chat).
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

DEFAULT_DEEPSEEK_CHAT_MODEL = "deepseek-chat"
DEFAULT_DEEPSEEK_REASONER_MODEL = "deepseek-reasoner"
DEEPSEEK_API_URL = "https://api.deepseek.com/chat/completions"


class DeepSeekProvider(ModelProvider):
    """DeepSeek reasoning & coding provider."""

    def __init__(
        self,
        api_key: str | None = None,
        chat_model: str = DEFAULT_DEEPSEEK_CHAT_MODEL,
        reasoner_model: str = DEFAULT_DEEPSEEK_REASONER_MODEL,
        timeout_seconds: float = 60.0,
    ) -> None:
        self.api_key = api_key or ""
        self.chat_model = chat_model
        self.reasoner_model = reasoner_model
        self.timeout_seconds = timeout_seconds

    @property
    def name(self) -> str:
        return "deepseek"

    @property
    def supported_capabilities(self) -> list[ModelCapability]:
        return [
            ModelCapability.REASONING,
            ModelCapability.CODING,
            ModelCapability.FAST,
            ModelCapability.RESEARCH,
            ModelCapability.VERIFICATION,
        ]

    def _select_model_for_capability(self, capability: ModelCapability) -> str:
        if capability in (ModelCapability.REASONING, ModelCapability.VERIFICATION):
            return self.reasoner_model
        return self.chat_model

    def _convert_messages(
        self, messages: list[ModelMessage], system_prompt: str | None
    ) -> list[dict[str, str]]:
        formatted: list[dict[str, str]] = []
        if system_prompt:
            formatted.append({"role": "system", "content": system_prompt})
        for msg in messages:
            formatted.append({"role": msg.role, "content": msg.content})
        return formatted

    async def generate(self, request: ModelRequest) -> ModelResponse:
        if not self.api_key:
            raise ValueError("DeepSeek API key is not configured.")

        model = self._select_model_for_capability(request.capability)
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        messages = self._convert_messages(request.messages, request.system_prompt)
        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
        }

        # DeepSeek-reasoner does not support response_format json_object in some endpoints; guard it
        if request.response_json_schema and model != self.reasoner_model:
            payload["response_format"] = {"type": "json_object"}

        t_start = time.monotonic()
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            resp = await client.post(DEEPSEEK_API_URL, headers=headers, json=payload)

        latency_ms = int((time.monotonic() - t_start) * 1000)

        if resp.status_code != 200:
            err_msg = (
                f"DeepSeek API request failed with status {resp.status_code}: {resp.text[:500]}"
            )
            global_logger.log_event(
                event_type="MODEL_ERROR",
                status="ERROR",
                data={"provider": "deepseek", "model": model, "error": err_msg},
            )
            raise RuntimeError(err_msg)

        data = resp.json()
        choices = data.get("choices", [])
        if not choices:
            raise RuntimeError("DeepSeek returned empty choices in response.")

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
