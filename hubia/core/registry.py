"""Provider registry — maps model IDs to provider instances."""

from __future__ import annotations

from hubia.core.provider import AIProvider, ModelInfo


class ProviderRegistry:
    """Maps model IDs to :class:`AIProvider` instances via prefix matching.

    Providers register themselves with one or more model prefixes (e.g.
    ``"meta-ai/"``, ``"zai/"``).  When resolving a model ID the first
    matching prefix wins.
    """

    def __init__(self) -> None:
        self._providers: dict[str, AIProvider] = {}
        self._prefix_map: dict[str, str] = {}  # prefix → provider name

    def register(
        self,
        name: str,
        provider: AIProvider,
        model_prefixes: list[str],
    ) -> None:
        """Register a provider under *name* with the given *model_prefixes*.

        Example::

            registry.register("meta_ai", meta_ai_provider, ["meta-ai/"])
            registry.register("zai_web", zai_web_provider, ["zai/"])
        """
        self._providers[name] = provider
        for prefix in model_prefixes:
            self._prefix_map[prefix] = name

    def get_provider_for_model(
        self,
        model_id: str,
    ) -> tuple[AIProvider, str] | None:
        """Resolve *model_id* to an ``(AIProvider, local_model)`` pair.

        The *local_model* is the model ID with the prefix stripped (e.g.
        ``"meta-ai/muse-spark"`` → ``"muse-spark"``).  Returns ``None`` if no
        registered prefix matches.
        """
        for prefix, provider_name in self._prefix_map.items():
            if model_id.startswith(prefix):
                local_model = model_id[len(prefix) :]
                return self._providers[provider_name], local_model
        return None

    async def list_all_models(self) -> list[ModelInfo]:
        """Aggregate model lists from all registered providers."""
        models: list[ModelInfo] = []
        for provider in self._providers.values():
            provider_models = await provider.list_models()
            models.extend(provider_models)
        return models

    @property
    def providers(self) -> dict[str, AIProvider]:
        """Registered providers (name → instance)."""
        return dict(self._providers)
