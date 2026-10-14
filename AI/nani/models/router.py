"""N.A.N.I. V2 — Model Capability Router & Provider Architecture
Provides provider registry, capability selection, and health/fallback management.
Abstracts all AI model providers without hardcoding any specific service into core.
"""

from collections import defaultdict
from typing import Any

from nani.models.base import ModelCapability, ModelProvider


class ModelRouter:
    """Manages model provider registrations, capability routing, health, and fallback selection."""

    def __init__(self) -> None:
        self._providers: dict[str, ModelProvider] = {}
        # Stores list of (priority, provider_name), sorted descending by priority
        self._capability_map: dict[ModelCapability, list[tuple[int, str]]] = defaultdict(list)

    def register_provider(self, provider: ModelProvider, priority: int = 0) -> None:
        """Registers a model provider and maps its supported capabilities.

        Cleans up any previous capability associations for this provider name to prevent stale routes.
        """
        # Purge provider name from all existing capability mappings
        for cap in list(self._capability_map.keys()):
            self._capability_map[cap] = [
                entry for entry in self._capability_map[cap] if entry[1] != provider.name
            ]

        self._providers[provider.name] = provider
        for cap in provider.supported_capabilities:
            self._capability_map[cap].append((priority, provider.name))
            self._capability_map[cap].sort(key=lambda x: x[0], reverse=True)

    def remove_provider(self, name: str) -> bool:
        """Removes a provider and unregisters it from all capability routes."""
        if name not in self._providers:
            return False
        del self._providers[name]
        for cap in list(self._capability_map.keys()):
            self._capability_map[cap] = [
                entry for entry in self._capability_map[cap] if entry[1] != name
            ]
        return True

    def get_provider(self, name: str) -> ModelProvider | None:
        """Retrieves a registered provider by name."""
        return self._providers.get(name)

    def get_provider_for_capability(
        self, capability: ModelCapability, exclude: set[str] | None = None
    ) -> ModelProvider | None:
        """Selects the highest-priority registered provider supporting the given capability."""
        excluded = exclude or set()
        entries = self._capability_map.get(capability, [])
        for _, name in entries:
            if name not in excluded and name in self._providers:
                return self._providers[name]
        return None

    def get_fallback_provider(
        self,
        capability: ModelCapability,
        failed_provider_name: str,
        attempted: set[str] | None = None,
    ) -> ModelProvider | None:
        """Selects the next available provider supporting the capability when primary fails."""
        exclusions = set(attempted or set())
        exclusions.add(failed_provider_name)
        return self.get_provider_for_capability(capability, exclude=exclusions)

    async def provider_health(self, name: str) -> bool:
        """Checks if a registered provider is healthy and available."""
        provider = self.get_provider(name)
        if not provider:
            return False
        try:
            return await provider.is_available()
        except Exception:
            return False

    def list_providers(self) -> list[ModelProvider]:
        """Lists all registered model providers."""
        return list(self._providers.values())

    def list_capabilities(self) -> dict[ModelCapability, list[str]]:
        """Returns mapping of capabilities to configured provider names."""
        return {cap: [name for _, name in entries] for cap, entries in self._capability_map.items()}

    @classmethod
    def create_default(cls, config: Any = None) -> "ModelRouter":
        """Instantiates and registers configured model providers with priority ordering."""
        from nani.config import settings
        from nani.models.providers.gemini import GeminiProvider
        from nani.models.providers.groq import GroqProvider
        from nani.models.providers.local_ollama import OllamaProvider

        cfg = config or settings
        router = cls()

        gemini_key = cfg.get_secret("gemini_api_key") if hasattr(cfg, "get_secret") else None
        if gemini_key:
            router.register_provider(GeminiProvider(api_key=gemini_key), priority=100)

        groq_key = cfg.get_secret("groq_api_key") if hasattr(cfg, "get_secret") else None
        if groq_key:
            router.register_provider(GroqProvider(api_key=groq_key), priority=90)

        # Register local Ollama as local offline fallback
        ollama_url = getattr(cfg, "ollama_base_url", "http://localhost:11434")
        router.register_provider(OllamaProvider(base_url=ollama_url), priority=10)

        return router
