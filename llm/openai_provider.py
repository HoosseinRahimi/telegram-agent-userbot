"""
OpenAI & Compatible Provider.

Integrates with OpenAI API as well as compatible local engines (Ollama, vLLM, LM Studio)
via the AsyncOpenAI client interface.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from .base import (
    BaseLLMProvider,
    LLMAuthenticationError,
    LLMError,
    LLMMessage,
    LLMRateLimitError,
    LLMRequest,
    LLMResponse,
    LLMUnavailableError,
)

logger = logging.getLogger(__name__)


class OpenAIProvider(BaseLLMProvider):
    """
    LLM Provider powered by OpenAI or OpenAI-compatible endpoints.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model_name: str = "gpt-4o-mini",
        base_url: Optional[str] = None,
    ) -> None:
        self.api_key = api_key
        self.model_name = model_name
        self.base_url = base_url
        self._client: Optional[Any] = None

    @property
    def provider_name(self) -> str:
        return "openai"

    def _get_client(self) -> Any:
        """Initializes and caches the AsyncOpenAI client."""
        if self._client is None:
            effective_key = self.api_key or "sk-dummy-key"
            try:
                from openai import AsyncOpenAI
                self._client = AsyncOpenAI(
                    api_key=effective_key,
                    base_url=self.base_url or None,
                )
            except ImportError:
                raise LLMUnavailableError(
                    "OpenAI SDK is not installed. Please install 'openai' package."
                )
        return self._client

    async def generate(self, request: LLMRequest) -> LLMResponse:
        """
        Generates chat completions using AsyncOpenAI.
        """
        client = self._get_client()

        messages: List[Dict[str, str]] = []

        if request.system_prompt:
            messages.append({"role": "system", "content": request.system_prompt})

        if request.messages:
            for msg in request.messages:
                if msg.role == "system" and request.system_prompt and msg.content == request.system_prompt:
                    continue  # already added
                messages.append({"role": msg.role, "content": msg.content})
        elif request.prompt:
            messages.append({"role": "user", "content": request.prompt})

        try:
            response = await client.chat.completions.create(
                model=self.model_name,
                messages=messages,
                temperature=request.temperature,
                max_tokens=request.max_tokens,
            )

            choice = response.choices[0]
            content = choice.message.content or ""
            finish_reason = getattr(choice, "finish_reason", "stop")

            usage_dict = None
            if hasattr(response, "usage") and response.usage:
                usage_dict = {
                    "prompt_tokens": getattr(response.usage, "prompt_tokens", 0),
                    "completion_tokens": getattr(response.usage, "completion_tokens", 0),
                    "total_tokens": getattr(response.usage, "total_tokens", 0),
                }

            return LLMResponse(
                content=content,
                model=self.model_name,
                finish_reason=finish_reason,
                usage=usage_dict,
                raw_response=response,
            )

        except Exception as exc:
            err_msg = str(exc)
            if "429" in err_msg or "rate_limit" in err_msg.lower():
                raise LLMRateLimitError(f"OpenAI rate limit hit: {err_msg}") from exc
            if "401" in err_msg or "invalid_api_key" in err_msg.lower():
                raise LLMAuthenticationError(f"OpenAI authentication failed: {err_msg}") from exc
            raise LLMError(f"OpenAI completion error: {err_msg}") from exc
