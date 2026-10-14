"""N.A.N.I. V2 — Google Gemini Model Provider
Direct async REST client for Gemini models supporting text, code, JSON schema, and multimodal vision.
Zero heavy SDK dependencies; uses standard httpx async client.
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

DEFAULT_GEMINI_MODEL = "gemini-flash-lite-latest"
GEMINI_API_ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models"


class GeminiProvider(ModelProvider):
    """Google Gemini model provider with multimodal vision and JSON schema support."""

    def __init__(
        self,
        api_key: str | None = None,
        default_model: str = DEFAULT_GEMINI_MODEL,
        timeout_seconds: float = 30.0,
    ) -> None:
        self.api_key = api_key or ""
        self.default_model = default_model
        self.timeout_seconds = timeout_seconds

    @property
    def name(self) -> str:
        return "gemini"

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
        # Flash is ideal for fast, coding, and vision
        return self.default_model

    def _convert_messages(self, messages: list[ModelMessage]) -> list[dict[str, Any]]:
        contents: list[dict[str, Any]] = []
        for msg in messages:
            role = "user" if msg.role in ("user", "system") else "model"
            parts: list[dict[str, Any]] = [{"text": msg.content}]
            for b64 in msg.images_base64:
                parts.append(
                    {
                        "inline_data": {
                            "mime_type": "image/jpeg",
                            "data": b64,
                        }
                    }
                )
            contents.append({"role": role, "parts": parts})
        return contents

    async def generate(self, request: ModelRequest) -> ModelResponse:
        if not self.api_key:
            raise ValueError("Gemini API key is not configured.")

        model = self._select_model_for_capability(request.capability)
        url = f"{GEMINI_API_ENDPOINT}/{model}:generateContent?key={self.api_key}"

        contents = self._convert_messages(request.messages)
        payload: dict[str, Any] = {"contents": contents}

        generation_config: dict[str, Any] = {
            "temperature": request.temperature,
            "maxOutputTokens": request.max_tokens,
        }

        if request.response_json_schema:
            generation_config["responseMimeType"] = "application/json"
            generation_config["responseSchema"] = request.response_json_schema

        payload["generationConfig"] = generation_config

        if request.system_prompt:
            payload["systemInstruction"] = {"parts": [{"text": request.system_prompt}]}

        t_start = time.monotonic()
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            resp = await client.post(url, json=payload)

        latency_ms = int((time.monotonic() - t_start) * 1000)

        if resp.status_code != 200:
            err_msg = f"Gemini API request failed with status {resp.status_code}: {resp.text[:500]}"
            global_logger.log_event(
                event_type="MODEL_ERROR",
                status="ERROR",
                data={"provider": "gemini", "model": model, "error": err_msg},
            )
            raise RuntimeError(err_msg)

        data = resp.json()
        candidates = data.get("candidates", [])
        if not candidates:
            raise RuntimeError("Gemini returned empty candidate response.")

        candidate = candidates[0]
        content_obj = candidate.get("content", {})
        parts = content_obj.get("parts", [])
        text_content = "".join(p.get("text", "") for p in parts)

        usage = data.get("usageMetadata", {})
        tokens_used = usage.get("totalTokenCount")

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
