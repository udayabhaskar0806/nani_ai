"""N.A.N.I. V2 — Groq High-Speed Model Provider
Direct async REST client for Groq fast-inference API using OpenAI-compatible payload.
Supports Llama-3.3-70B, Llama-3.1-8B, and Qwen models with ultra-low latency.
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

DEFAULT_GROQ_MODEL = "llama-3.3-70b-versatile"
FAST_GROQ_MODEL = "llama-3.1-8b-instant"
GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"


class GroqProvider(ModelProvider):
    """Groq ultra-fast inference provider."""

    def __init__(
        self,
        api_key: str | None = None,
        default_model: str = DEFAULT_GROQ_MODEL,
        fast_model: str = FAST_GROQ_MODEL,
        timeout_seconds: float = 30.0,
    ) -> None:
        self.api_key = api_key or ""
        self.default_model = default_model
        self.fast_model = fast_model
        self.timeout_seconds = timeout_seconds

    @property
    def name(self) -> str:
        return "groq"

    @property
    def supported_capabilities(self) -> list[ModelCapability]:
        return [
            ModelCapability.FAST,
            ModelCapability.REASONING,
            ModelCapability.CODING,
            ModelCapability.RESEARCH,
            ModelCapability.VERIFICATION,
        ]

    def _select_model_for_capability(self, capability: ModelCapability) -> str:
        if capability == ModelCapability.FAST:
            return self.fast_model
        return self.default_model

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
            raise ValueError("Groq API key is not configured.")

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

        if request.response_json_schema:
            payload["response_format"] = {"type": "json_object"}

        models_to_try = [model]
        for alt in ("qwen/qwen3.8-27b", "openai/gpt-oss-120b", "llama-3.3-70b-versatile"):
            if alt not in models_to_try:
                models_to_try.append(alt)

        last_resp = None
        for m in models_to_try:
            payload["model"] = m
            t_start = time.monotonic()
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                resp = await client.post(GROQ_API_URL, headers=headers, json=payload)
            latency_ms = int((time.monotonic() - t_start) * 1000)
            last_resp = resp
            if resp.status_code == 200:
                model = m
                break
            if resp.status_code != 404 and "model_not_found" not in resp.text:
                break

        if last_resp is None or last_resp.status_code != 200:
            err_msg = f"Groq API request failed with status {last_resp.status_code if last_resp else 'unknown'}: {last_resp.text[:500] if last_resp else ''}"
            global_logger.log_event(
                event_type="MODEL_ERROR",
                status="ERROR",
                data={"provider": "groq", "model": model, "error": err_msg},
            )
            raise RuntimeError(err_msg)

        data = last_resp.json()

        choices = data.get("choices", [])
        if not choices:
            raise RuntimeError("Groq returned empty choices in response.")

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
