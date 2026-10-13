"""N.A.N.I. V2 — Model Capabilities & Provider Interface
Abstracts model providers behind capability requests (FAST, REASONING, CODING, VISION, RESEARCH, VERIFICATION).
"""

from abc import ABC, abstractmethod
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class ModelCapability(str, Enum):
    FAST = "FAST"  # Intent extraction, quick classification, simple routing
    REASONING = "REASONING"  # Deep logic, architectural decisions, root cause diagnosis
    CODING = "CODING"  # Code generation, syntax analysis, diff patching
    VISION = "VISION"  # Multimodal screen perception, OCR, coordinate localization
    RESEARCH = "RESEARCH"  # Multi-source web synthesis, RFC analysis
    VERIFICATION = "VERIFICATION"  # Independent test & diff review, validation


class ModelMessage(BaseModel):
    role: str  # "system", "user", "assistant"
    content: str
    images_base64: list[str] = Field(default_factory=list)


class ModelRequest(BaseModel):
    capability: ModelCapability
    messages: list[ModelMessage]
    system_prompt: str | None = None
    temperature: float = 0.2
    max_tokens: int = 4096
    response_json_schema: dict[str, Any] | None = None


class ModelResponse(BaseModel):
    content: str
    provider_name: str
    model_name: str
    tokens_used: int | None = None
    latency_ms: int = 0
    raw_response: dict[str, Any] = Field(default_factory=dict)


class ModelProvider(ABC):
    @property
    @abstractmethod
    def name(self) -> str:
        """Name of provider (e.g., 'gemini', 'groq', 'openrouter', 'ollama')."""
        pass

    @property
    @abstractmethod
    def supported_capabilities(self) -> list[ModelCapability]:
        """List of capabilities supported by this provider."""
        pass

    @abstractmethod
    async def generate(self, request: ModelRequest) -> ModelResponse:
        """Executes completion request against this provider."""
        pass

    @abstractmethod
    async def is_available(self) -> bool:
        """Checks if provider key is configured and health check passes."""
        pass
