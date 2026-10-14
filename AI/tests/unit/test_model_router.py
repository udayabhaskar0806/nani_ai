"""Unit tests for ModelRouter registration, capability matching, and fallback handling."""

import pytest

from nani.models.base import ModelCapability, ModelProvider, ModelRequest, ModelResponse
from nani.models.router import ModelRouter


class MockProvider(ModelProvider):
    def __init__(
        self, provider_name: str, caps: list[ModelCapability], available: bool = True
    ) -> None:
        self._name = provider_name
        self._caps = caps
        self._available = available

    @property
    def name(self) -> str:
        return self._name

    @property
    def supported_capabilities(self) -> list[ModelCapability]:
        return self._caps

    async def generate(self, request: ModelRequest) -> ModelResponse:
        return ModelResponse(
            content=f"Response from {self._name}",
            provider_name=self._name,
            model_name="mock-model",
        )

    async def is_available(self) -> bool:
        return self._available


@pytest.mark.asyncio
async def test_model_router_registration_and_lookup():
    router = ModelRouter()
    p_fast = MockProvider("fast-mock", [ModelCapability.FAST])
    p_code = MockProvider("code-mock", [ModelCapability.CODING, ModelCapability.REASONING])

    router.register_provider(p_fast, priority=1)
    router.register_provider(p_code, priority=5)

    assert router.get_provider("fast-mock") is p_fast
    assert router.get_provider_for_capability(ModelCapability.FAST) is p_fast
    assert router.get_provider_for_capability(ModelCapability.CODING) is p_code
    assert router.get_provider_for_capability(ModelCapability.VISION) is None


@pytest.mark.asyncio
async def test_model_router_fallback_selection():
    router = ModelRouter()
    primary = MockProvider("primary-coder", [ModelCapability.CODING])
    fallback = MockProvider("backup-coder", [ModelCapability.CODING])

    router.register_provider(primary, priority=10)
    router.register_provider(fallback, priority=5)

    chosen = router.get_provider_for_capability(ModelCapability.CODING)
    assert chosen is primary

    # Fallback when primary fails
    fb = router.get_fallback_provider(ModelCapability.CODING, failed_provider_name="primary-coder")
    assert fb is fallback


@pytest.mark.asyncio
async def test_model_router_provider_health_and_removal():
    router = ModelRouter()
    healthy = MockProvider("healthy-p", [ModelCapability.FAST], available=True)
    unhealthy = MockProvider("broken-p", [ModelCapability.REASONING], available=False)

    router.register_provider(healthy)
    router.register_provider(unhealthy)

    assert await router.provider_health("healthy-p") is True
    assert await router.provider_health("broken-p") is False
    assert await router.provider_health("unknown-p") is False

    assert router.remove_provider("healthy-p") is True
    assert router.get_provider("healthy-p") is None
    assert router.get_provider_for_capability(ModelCapability.FAST) is None
