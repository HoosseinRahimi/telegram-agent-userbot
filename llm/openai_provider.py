"""
OpenAI & Compatible Provider.

Integrates with OpenAI API as well as compatible local engines (Ollama, vLLM, LM Studio)
via the AsyncOpenAI client interface.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from .base import (
    BaseLLMProvider,
    LLMAuthenticationError,
    LLMError,
    LLMRateLimitError,
    LLMRequest,
    LLMResponse,
    LLMUnavailableError,
)

logger = logging.getLogger(__name__)


class OpenAIProvider(BaseLLMProvider):
    """
    LLM Provider powered by OpenAI or OpenAI-compatible endpoints.
    Includes timeout, exponential backoff retry for transient errors, and strict credential validation.
    """

    def __init__(
        self,
        api_key: str | None = None,
        model_name: str = "gpt-4o-mini",
        base_url: str | None = None,
        timeout_seconds: float = 30.0,
        max_retries: int = 3,
        initial_backoff: float = 1.0,
        retry_backoff_factor: float = 2.0,
    ) -> None:
        self.api_key = api_key
        self.model_name = model_name
        self.base_url = base_url
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self.initial_backoff = initial_backoff
        self.retry_backoff_factor = retry_backoff_factor
        self._client: Any | None = None

    @property
    def provider_name(self) -> str:
        return "openai"

    def _get_client(self) -> Any:
        """Initializes and caches the AsyncOpenAI client."""
        if self._client is None:
            # If no base_url, we require a valid API key (not placeholder)
            if not self.base_url:
                if not self.api_key or self.api_key.startswith("sk-example-"):
                    raise LLMAuthenticationError(
                        "OPENAI_API_KEY is missing or contains placeholder value."
                    )
            effective_key = self.api_key or "local-token"
            try:
                from openai import AsyncOpenAI
                self._client = AsyncOpenAI(
                    api_key=effective_key,
                    base_url=self.base_url or None,
                    timeout=self.timeout_seconds,
                )
            except ImportError as err:
                raise LLMUnavailableError(
                    "OpenAI SDK is not installed. Please install 'openai' package."
                ) from err
        return self._client

    async def generate(self, request: LLMRequest) -> LLMResponse:
        """
        Generates chat completions using AsyncOpenAI with timeout and retry backoff.
        """
        client = self._get_client()

        messages: list[dict[str, str]] = []

        if request.system_prompt:
            messages.append({"role": "system", "content": request.system_prompt})

        if request.messages:
            for msg in request.messages:
                if msg.role == "system" and request.system_prompt and msg.content == request.system_prompt:
                    continue  # already added
                messages.append({"role": msg.role, "content": msg.content})
        elif request.prompt:
            messages.append({"role": "user", "content": request.prompt})

        last_exc: Exception | None = None

        for attempt in range(self.max_retries):
            try:
                async with asyncio.timeout(self.timeout_seconds):
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

            except (TimeoutError, asyncio.TimeoutError) as exc:
                last_exc = exc
                if attempt == self.max_retries - 1:
                    raise LLMUnavailableError(
                        f"OpenAI request timed out after {self.timeout_seconds}s"
                    ) from exc
                backoff = self.initial_backoff * (self.retry_backoff_factor ** attempt)
                logger.warning(
                    f"[OpenAIProvider] Request timed out (attempt {attempt + 1}/{self.max_retries}). "
                    f"Retrying in {backoff:.1f}s..."
                )
                await asyncio.sleep(backoff)

            except Exception as exc:
                last_exc = exc
                status_code = getattr(exc, "status_code", None)
                err_msg = str(exc).lower()

                # 401 Unauthorized / Invalid API Key -> fail immediately, do not retry
                if status_code == 401 or "401" in err_msg or "invalid_api_key" in err_msg:
                    raise LLMAuthenticationError(f"OpenAI authentication failed: {exc}") from exc

                # 429 Rate Limit
                if status_code == 429 or "429" in err_msg or "rate_limit" in err_msg:
                    if attempt == self.max_retries - 1:
                        raise LLMRateLimitError(f"OpenAI rate limit exceeded: {exc}") from exc
                    backoff = self.initial_backoff * (self.retry_backoff_factor ** attempt)
                    logger.warning(
                        f"[OpenAIProvider] Rate limit hit (attempt {attempt + 1}/{self.max_retries}). "
                        f"Retrying in {backoff:.1f}s..."
                    )
                    await asyncio.sleep(backoff)
                    continue

                # 5xx Server Errors
                if (status_code and status_code >= 500) or "500" in err_msg or "502" in err_msg or "503" in err_msg:
                    if attempt == self.max_retries - 1:
                        raise LLMUnavailableError(f"OpenAI server error ({status_code}): {exc}") from exc
                    backoff = self.initial_backoff * (self.retry_backoff_factor ** attempt)
                    logger.warning(
                        f"[OpenAIProvider] Server error {status_code} (attempt {attempt + 1}/{self.max_retries}). "
                        f"Retrying in {backoff:.1f}s..."
                    )
                    await asyncio.sleep(backoff)
                    continue

                # Non-retryable error
                raise LLMError(f"OpenAI completion error: {exc}") from exc

        raise LLMError(f"OpenAI completion failed after {self.max_retries} attempts: {last_exc}")
