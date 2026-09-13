"""
Modular LLM Factory and Provider Registry.

Instantiates and configures the active LLM provider based on application settings.
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Dict, Optional, Type

from config.settings import Settings
from .base import BaseLLMProvider
from .gemini_provider import GeminiProvider
from .mock_provider import MockLLMProvider
from .openai_provider import OpenAIProvider

logger = logging.getLogger(__name__)

# Registry mapping provider keys to factory constructors
PROVIDER_REGISTRY: Dict[str, Callable[[Settings], BaseLLMProvider]] = {}


def register_provider(
    name: str,
    factory: Callable[[Settings], BaseLLMProvider],
) -> None:
    """Registers a new LLM provider factory under a given name."""
    PROVIDER_REGISTRY[name.lower()] = factory


def _create_gemini(settings: Settings) -> BaseLLMProvider:
    return GeminiProvider(
        api_key=settings.gemini_api_key,
        model_name=settings.gemini_model,
    )


def _create_openai(settings: Settings) -> BaseLLMProvider:
    return OpenAIProvider(
        api_key=settings.openai_api_key,
        model_name=settings.openai_model,
        base_url=settings.openai_base_url,
    )


def _create_mock(settings: Settings) -> BaseLLMProvider:
    return MockLLMProvider()


# Register default built-in providers
register_provider("gemini", _create_gemini)
register_provider("openai", _create_openai)
register_provider("mock", _create_mock)


def create_llm_provider(settings: Settings) -> BaseLLMProvider:
    """
    Factory function creating an instance of BaseLLMProvider configured according to Settings.
    """
    provider_name = settings.llm_provider.lower().strip()
    factory = PROVIDER_REGISTRY.get(provider_name)
    if not factory:
        valid = ", ".join(repr(k) for k in PROVIDER_REGISTRY.keys())
        raise ValueError(
            f"Unknown LLM provider '{settings.llm_provider}'. Supported providers are: {valid}"
        )

    logger.info(f"[LLM Factory] Initializing active LLM provider: '{provider_name}'")
    return factory(settings)
