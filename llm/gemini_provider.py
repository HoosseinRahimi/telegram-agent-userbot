"""
Google Gemini LLM Provider.

Integrates with Google Gemini API using the official SDK (`google-genai` / `google.genai`).
Translates prompts, system instructions, and multi-turn messages into Gemini API calls.
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


class GeminiProvider(BaseLLMProvider):
    """
    LLM Provider powered by Google Gemini API.
    Includes timeout, exponential backoff retry for transient errors, and robust error classification.
    """

    def __init__(
        self,
        api_key: str | None = None,
        model_name: str = "gemini-2.5-flash",
        timeout_seconds: float = 30.0,
        max_retries: int = 3,
        initial_backoff: float = 1.0,
        retry_backoff_factor: float = 2.0,
    ) -> None:
        self.api_key = api_key
        self.model_name = model_name
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self.initial_backoff = initial_backoff
        self.retry_backoff_factor = retry_backoff_factor
        self._client: Any | None = None

    @property
    def provider_name(self) -> str:
        return "gemini"

    def _get_client(self) -> Any:
        """Initializes and caches the Gemini SDK client."""
        if self._client is None:
            if not self.api_key or self.api_key.startswith("AIzaSyExample"):
                raise LLMAuthenticationError("GEMINI_API_KEY is missing or contains placeholder value.")

            try:
                # Prefer google.genai (new SDK)
                from google import genai
                self._client = genai.Client(api_key=self.api_key)
            except ImportError:
                try:
                    # Fallback to google.generativeai if installed
                    import google.generativeai as legacy_genai
                    legacy_genai.configure(api_key=self.api_key)
                    self._client = legacy_genai
                except ImportError as err:
                    raise LLMUnavailableError(
                        "Google GenAI SDK is not installed. Please install 'google-genai' package."
                    ) from err
        return self._client

    async def generate(self, request: LLMRequest) -> LLMResponse:
        """
        Executes text generation via Google Gemini API with timeout and retry backoff.
        """
        client = self._get_client()

        # Build prompt & system instruction
        system_instruction = request.system_prompt
        contents: list[Any] = []

        if request.messages:
            for msg in request.messages:
                if msg.role == "system":
                    system_instruction = msg.content
                elif msg.role in ("user", "human"):
                    contents.append({"role": "user", "parts": [{"text": msg.content}]})
                elif msg.role in ("assistant", "model"):
                    contents.append({"role": "model", "parts": [{"text": msg.content}]})
        elif request.prompt:
            contents.append(request.prompt)

        config: dict[str, Any] = {}
        if system_instruction:
            config["system_instruction"] = system_instruction
        if request.temperature is not None:
            config["temperature"] = request.temperature
        if request.max_tokens is not None:
            config["max_output_tokens"] = request.max_tokens

        last_exc: Exception | None = None

        for attempt in range(self.max_retries):
            try:
                async with asyncio.timeout(self.timeout_seconds):
                    # Modern google-genai Client API: client.aio.models.generate_content
                    if hasattr(client, "aio") and hasattr(client.aio, "models"):
                        response = await client.aio.models.generate_content(
                            model=self.model_name,
                            contents=contents,
                            config=config if config else None,
                        )
                        text = response.text or ""
                        return LLMResponse(content=text, model=self.model_name, raw_response=response)

                    # Modern synchronous fallback executed in thread pool to prevent blocking event loop
                    elif hasattr(client, "models"):
                        response = await asyncio.to_thread(
                            client.models.generate_content,
                            model=self.model_name,
                            contents=contents,
                            config=config if config else None,
                        )
                        text = response.text or ""
                        return LLMResponse(content=text, model=self.model_name, raw_response=response)
                    else:
                        # Legacy GenerativeModel interface
                        model = client.GenerativeModel(
                            self.model_name,
                            system_instruction=system_instruction,
                        )
                        response = await model.generate_content_async(contents)
                        text = response.text or ""
                        return LLMResponse(content=text, model=self.model_name, raw_response=response)

            except (TimeoutError, asyncio.TimeoutError) as exc:
                last_exc = exc
                if attempt == self.max_retries - 1:
                    raise LLMUnavailableError(
                        f"Gemini request timed out after {self.timeout_seconds}s"
                    ) from exc
                backoff = self.initial_backoff * (self.retry_backoff_factor ** attempt)
                logger.warning(
                    f"[GeminiProvider] Request timed out (attempt {attempt + 1}/{self.max_retries}). "
                    f"Retrying in {backoff:.1f}s..."
                )
                await asyncio.sleep(backoff)

            except Exception as exc:
                last_exc = exc
                status_code = getattr(exc, "code", None) or getattr(exc, "status_code", None)
                err_msg = str(exc).lower()

                # 401 / 403 / Invalid key
                if status_code in (401, 403) or "401" in err_msg or "api_key_invalid" in err_msg or "unauthorized" in err_msg:
                    raise LLMAuthenticationError(f"Gemini API authentication failed: {exc}") from exc

                # 429 / Quota / Rate limit
                if status_code == 429 or "429" in err_msg or "resourceexhausted" in err_msg or "quota" in err_msg:
                    if attempt == self.max_retries - 1:
                        raise LLMRateLimitError(f"Gemini API rate limit exceeded: {exc}") from exc
                    backoff = self.initial_backoff * (self.retry_backoff_factor ** attempt)
                    logger.warning(
                        f"[GeminiProvider] Rate limit hit (attempt {attempt + 1}/{self.max_retries}). "
                        f"Retrying in {backoff:.1f}s..."
                    )
                    await asyncio.sleep(backoff)
                    continue

                # 5xx / Server errors
                if (status_code and status_code >= 500) or "500" in err_msg or "503" in err_msg or "unavailable" in err_msg:
                    if attempt == self.max_retries - 1:
                        raise LLMUnavailableError(f"Gemini server error ({status_code}): {exc}") from exc
                    backoff = self.initial_backoff * (self.retry_backoff_factor ** attempt)
                    logger.warning(
                        f"[GeminiProvider] Server error (attempt {attempt + 1}/{self.max_retries}). "
                        f"Retrying in {backoff:.1f}s..."
                    )
                    await asyncio.sleep(backoff)
                    continue

                raise LLMError(f"Gemini API invocation error: {exc}") from exc

        raise LLMError(f"Gemini API invocation failed after {self.max_retries} attempts: {last_exc}")
