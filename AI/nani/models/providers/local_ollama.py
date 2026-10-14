"""N.A.N.I. V2 — Local Ollama Model Provider
Direct async REST client for locally hosted Ollama instances.
Provides 100% offline fallback when external network or API keys are unavailable.
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

DEFAULT_OLLAMA_URL = "http://localhost:11434"
DEFAULT_OLLAMA_MODEL = "llama3:latest"


class OllamaProvider(ModelProvider):
    """Local offline Ollama provider."""

    def __init__(
        self,
        base_url: str = DEFAULT_OLLAMA_URL,
        default_model: str = DEFAULT_OLLAMA_MODEL,
        timeout_seconds: float = 60.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.default_model = default_model
        self.timeout_seconds = timeout_seconds

    @property
    def name(self) -> str:
        return "ollama"

    @property
    def supported_capabilities(self) -> list[ModelCapability]:
        return [
            ModelCapability.FAST,
            ModelCapability.REASONING,
            ModelCapability.CODING,
            ModelCapability.RESEARCH,
            ModelCapability.VERIFICATION,
        ]

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
        url = f"{self.base_url}/api/chat"
        messages = self._convert_messages(request.messages, request.system_prompt)
        payload: dict[str, Any] = {
            "model": self.default_model,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": request.temperature,
                "num_predict": request.max_tokens,
            },
        }

        if request.response_json_schema:
            payload["format"] = "json"

        t_start = time.monotonic()
        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                resp = await client.post(url, json=payload)
        except Exception as e:
            err_msg = f"Failed to connect to local Ollama instance at {self.base_url}: {e}"
            global_logger.log_event(
                event_type="MODEL_ERROR",
                status="ERROR",
                data={"provider": "ollama", "error": err_msg},
            )
            raise RuntimeError(err_msg) from e

        latency_ms = int((time.monotonic() - t_start) * 1000)

        if resp.status_code != 200:
            err_msg = f"Ollama returned error {resp.status_code}: {resp.text[:500]}"
            raise RuntimeError(err_msg)

        data = resp.json()
        message = data.get("message", {})
        text_content = message.get("content", "")
        tokens_used = data.get("eval_count")

        return ModelResponse(
            content=text_content,
            provider_name=self.name,
            model_name=self.default_model,
            tokens_used=tokens_used,
            latency_ms=latency_ms,
            raw_response=data,
        )

    async def is_available(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                res = await client.get(f"{self.base_url}/api/tags")
                return res.status_code == 200
        except Exception:
            return False
