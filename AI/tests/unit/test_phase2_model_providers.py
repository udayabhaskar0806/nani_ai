"""Unit tests for Phase 2 Model Providers (Gemini, Groq, Ollama) and ModelRouter integration."""

import pytest

from nani.models.base import (
    ModelCapability,
    ModelMessage,
    ModelRequest,
)
from nani.models.providers.gemini import GeminiProvider
from nani.models.providers.groq import GroqProvider
from nani.models.providers.local_ollama import OllamaProvider
from nani.models.router import ModelRouter


def test_gemini_provider_initialization_and_capabilities():
    provider = GeminiProvider(api_key="AIzaSyTestKey12345678901234567890")
    assert provider.name == "gemini"
    assert ModelCapability.VISION in provider.supported_capabilities
    assert ModelCapability.CODING in provider.supported_capabilities
    assert ModelCapability.FAST in provider.supported_capabilities


def test_gemini_provider_message_conversion():
    provider = GeminiProvider(api_key="AIzaSyTestKey12345678901234567890")
    messages = [
        ModelMessage(role="system", content="System instruction"),
        ModelMessage(
            role="user", content="Hello, write a C program", images_base64=["base64imgdata"]
        ),
        ModelMessage(role="assistant", content="Here is the code"),
    ]
    contents = provider._convert_messages(messages)
    assert len(contents) == 3
    assert contents[0]["role"] == "user"  # mapped from system/user
    assert contents[1]["role"] == "user"
    assert len(contents[1]["parts"]) == 2  # text + inline_data
    assert contents[1]["parts"][1]["inline_data"]["mime_type"] == "image/jpeg"
    assert contents[2]["role"] == "model"


@pytest.mark.asyncio
async def test_gemini_provider_rejects_missing_key():
    provider = GeminiProvider(api_key="")
    assert await provider.is_available() is False

    req = ModelRequest(
        capability=ModelCapability.FAST,
        messages=[ModelMessage(role="user", content="ping")],
    )
    with pytest.raises(ValueError, match="Gemini API key is not configured"):
        await provider.generate(req)


def test_groq_provider_initialization_and_model_selection():
    provider = GroqProvider(api_key="gsk_test12345678901234567890")
    assert provider.name == "groq"
    assert ModelCapability.CODING in provider.supported_capabilities

    fast_model = provider._select_model_for_capability(ModelCapability.FAST)
    reasoning_model = provider._select_model_for_capability(ModelCapability.REASONING)
    assert "8b" in fast_model.lower()
    assert "70b" in reasoning_model.lower()


def test_groq_provider_message_conversion():
    provider = GroqProvider(api_key="gsk_test12345678901234567890")
    messages = [
        ModelMessage(role="user", content="Hello"),
        ModelMessage(role="assistant", content="World"),
    ]
    formatted = provider._convert_messages(messages, system_prompt="Be concise")
    assert len(formatted) == 3
    assert formatted[0]["role"] == "system"
    assert formatted[0]["content"] == "Be concise"
    assert formatted[1]["role"] == "user"
    assert formatted[2]["role"] == "assistant"


@pytest.mark.asyncio
async def test_groq_provider_rejects_missing_key():
    provider = GroqProvider(api_key="")
    assert await provider.is_available() is False

    req = ModelRequest(
        capability=ModelCapability.FAST,
        messages=[ModelMessage(role="user", content="ping")],
    )
    with pytest.raises(ValueError, match="Groq API key is not configured"):
        await provider.generate(req)


def test_ollama_provider_initialization():
    provider = OllamaProvider(base_url="http://localhost:11434")
    assert provider.name == "ollama"
    assert ModelCapability.FAST in provider.supported_capabilities


def test_model_router_create_default():
    router = ModelRouter.create_default()
    # At minimum, local Ollama fallback is registered
    assert router.get_provider("ollama") is not None

    # Capabilities map to registered provider
    provider = router.get_provider_for_capability(ModelCapability.FAST)
    assert provider is not None


def test_deepseek_provider_initialization_and_model_selection():
    from nani.models.providers.deepseek import DeepSeekProvider

    provider = DeepSeekProvider(api_key="sk-test-deepseek-123456")
    assert provider.name == "deepseek"
    assert ModelCapability.REASONING in provider.supported_capabilities
    assert ModelCapability.CODING in provider.supported_capabilities

    fast_model = provider._select_model_for_capability(ModelCapability.FAST)
    reasoning_model = provider._select_model_for_capability(ModelCapability.REASONING)
    assert "chat" in fast_model
    assert "reasoner" in reasoning_model


@pytest.mark.asyncio
async def test_deepseek_provider_rejects_missing_key():
    from nani.models.providers.deepseek import DeepSeekProvider

    provider = DeepSeekProvider(api_key="")
    assert await provider.is_available() is False

    req = ModelRequest(
        capability=ModelCapability.REASONING,
        messages=[ModelMessage(role="user", content="solve logic puzzle")],
    )
    with pytest.raises(ValueError, match="DeepSeek API key is not configured"):
        await provider.generate(req)


def test_openrouter_provider_initialization_and_multimodal_conversion():
    from nani.models.providers.openrouter import OpenRouterProvider

    provider = OpenRouterProvider(api_key="sk-or-test-123456")
    assert provider.name == "openrouter"
    assert ModelCapability.VISION in provider.supported_capabilities

    messages = [
        ModelMessage(role="user", content="Examine this image", images_base64=["sample_b64"]),
    ]
    formatted = provider._convert_messages(messages, system_prompt="You are an analyst.")
    assert len(formatted) == 2
    assert formatted[0]["role"] == "system"
    assert formatted[1]["role"] == "user"
    assert isinstance(formatted[1]["content"], list)
    assert formatted[1]["content"][1]["type"] == "image_url"


@pytest.mark.asyncio
async def test_openrouter_provider_rejects_missing_key():
    from nani.models.providers.openrouter import OpenRouterProvider

    provider = OpenRouterProvider(api_key="")
    assert await provider.is_available() is False

    req = ModelRequest(
        capability=ModelCapability.CODING,
        messages=[ModelMessage(role="user", content="write test")],
    )
    with pytest.raises(ValueError, match="OpenRouter API key is not configured"):
        await provider.generate(req)
