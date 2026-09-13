"""
Google Gemini LLM Provider.

Integrates with Google Gemini API using the official SDK (`google-genai` / `google.genai`).
Translates prompts, system instructions, and multi-turn messages into Gemini API calls.
"""

from __future__ import annotations

import logging
from typing import Any, List, Optional

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


class GeminiProvider(BaseLLMProvider):
    """
    LLM Provider powered by Google Gemini API.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model_name: str = "gemini-2.5-flash",
    ) -> None:
        self.api_key = api_key
        self.model_name = model_name
        self._client: Optional[Any] = None

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
                except ImportError:
                    raise LLMUnavailableError(
                        "Google GenAI SDK is not installed. Please install 'google-genai' package."
                    )
        return self._client

    async def generate(self, request: LLMRequest) -> LLMResponse:
        """
        Executes text generation via Google Gemini API.
        """
        client = self._get_client()

        # Build prompt & system instruction
        system_instruction = request.system_prompt
        contents: List[Any] = []

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

        try:
            # Modern google-genai Client API: client.aio.models.generate_content
            if hasattr(client, "aio") and hasattr(client.aio, "models"):
                config = {}
                if system_instruction:
                    config["system_instruction"] = system_instruction
                if request.temperature is not None:
                    config["temperature"] = request.temperature
                if request.max_tokens is not None:
                    config["max_output_tokens"] = request.max_tokens

                response = await client.aio.models.generate_content(
                    model=self.model_name,
                    contents=contents,
                    config=config if config else None,
                )
                text = response.text or ""
                return LLMResponse(content=text, model=self.model_name, raw_response=response)

            # Modern synchronous fallback executed in executor or legacy API
            elif hasattr(client, "models"):
                response = client.models.generate_content(
                    model=self.model_name,
                    contents=contents,
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

        except Exception as exc:
            err_msg = str(exc)
            if "429" in err_msg or "ResourceExhausted" in err_msg or "QuotaExceeded" in err_msg:
                raise LLMRateLimitError(f"Gemini API rate limit exceeded: {err_msg}") from exc
            if "401" in err_msg or "API_KEY_INVALID" in err_msg or "Unauthorized" in err_msg:
                raise LLMAuthenticationError(f"Gemini API authentication failed: {err_msg}") from exc
            raise LLMError(f"Gemini API invocation error: {err_msg}") from exc
