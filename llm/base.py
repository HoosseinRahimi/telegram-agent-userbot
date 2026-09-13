"""
Modular LLM Engine - Base Abstractions, Data Models, and Exception Hierarchy.

This module defines standard data structures (LLMMessage, LLMRequest, LLMResponse),
typed exceptions for error classification, and the abstract BaseLLMProvider.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Union


# ============================================================================
# Exception Hierarchy
# ============================================================================

class LLMError(Exception):
    """Base exception for all LLM errors in the userbot."""
    pass


class LLMAuthenticationError(LLMError):
    """Raised when API key is missing, invalid, or unauthorized."""
    pass


# Alias for compatibility with diverse naming conventions
LLMAuthError = LLMAuthenticationError


class LLMRateLimitError(LLMError):
    """Raised when quota is exhausted, rate limit hit (HTTP 429), or ResourceExhausted."""
    pass


class LLMResponseError(LLMError):
    """Raised when the LLM returns an empty, invalid, blocked, or malformed response."""
    pass


class LLMUnavailableError(LLMError):
    """Raised when the remote LLM endpoint is unreachable, timed out, or SDK is missing."""
    pass


# ============================================================================
# Data Models
# ============================================================================

@dataclass
class LLMMessage:
    """Represents a single message in a chat conversation."""
    role: str  # "system", "user", "assistant" (or "model")
    content: str

    def to_dict(self) -> Dict[str, str]:
        return {"role": self.role, "content": self.content}


@dataclass
class LLMRequest:
    """
    Input request payload for LLM generation.
    Supports either a list of LLMMessage objects or direct prompt/system_prompt parameters.
    """
    messages: List[LLMMessage] = field(default_factory=list)
    temperature: float = 0.7
    max_tokens: int = 1024
    prompt: Optional[str] = None
    system_prompt: Optional[str] = None
    extra_params: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # If messages not supplied but prompt was provided, construct messages list
        if not self.messages and self.prompt is not None:
            constructed: List[LLMMessage] = []
            if self.system_prompt:
                constructed.append(LLMMessage(role="system", content=self.system_prompt))
            constructed.append(LLMMessage(role="user", content=self.prompt))
            self.messages = constructed

        # If messages were provided but prompt/system_prompt were not, extract them for convenience
        if self.messages:
            if self.prompt is None:
                for msg in reversed(self.messages):
                    if msg.role == "user":
                        self.prompt = msg.content
                        break
                if self.prompt is None and self.messages:
                    self.prompt = self.messages[-1].content

            if self.system_prompt is None:
                for msg in self.messages:
                    if msg.role == "system":
                        self.system_prompt = msg.content
                        break


@dataclass
class LLMResponse:
    """
    Output payload produced by an LLM provider.
    """
    content: str
    model: str
    tokens_used: Optional[int] = None
    finish_reason: Optional[str] = "stop"
    usage: Optional[Dict[str, int]] = None
    raw_response: Optional[Any] = None

    def __post_init__(self) -> None:
        if self.tokens_used is not None and self.usage is None:
            self.usage = {"total_tokens": self.tokens_used}
        elif self.usage and self.tokens_used is None:
            self.tokens_used = self.usage.get("total_tokens")


# ============================================================================
# Abstract Base Provider
# ============================================================================

class BaseLLMProvider(ABC):
    """
    Abstract interface for all Large Language Model providers.
    All providers (Gemini, OpenAI, Mock) must implement `generate`.
    """

    @property
    def provider_name(self) -> str:
        """Returns the canonical lowercase name of the provider."""
        name = self.__class__.__name__
        if name.endswith("Provider"):
            name = name[:-8]
        return name.lower()

    @abstractmethod
    async def generate(self, request: LLMRequest) -> LLMResponse:
        """
        Asynchronously generates a response from the LLM based on request parameters.

        Args:
            request: LLMRequest containing messages, temperature, max_tokens, etc.

        Returns:
            LLMResponse containing generated content and metadata.

        Raises:
            LLMAuthenticationError: When credentials fail.
            LLMRateLimitError: When rate-limited or quota is exceeded.
            LLMResponseError: When response is empty or blocked.
            LLMUnavailableError: When remote service is unreachable.
            LLMError: General LLM generation failure.
        """
        pass

    async def generate_response(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        history: Optional[List[Union[LLMMessage, Dict[str, str]]]] = None,
        temperature: float = 0.7,
        max_tokens: int = 1024,
    ) -> str:
        """
        Convenience wrapper method that accepts primitive prompt/history strings
        and returns the generated text directly.
        """
        messages: List[LLMMessage] = []
        if system_prompt:
            messages.append(LLMMessage(role="system", content=system_prompt))
        if history:
            for item in history:
                if isinstance(item, LLMMessage):
                    messages.append(item)
                elif isinstance(item, dict):
                    messages.append(LLMMessage(
                        role=item.get("role", "user"),
                        content=item.get("content", ""),
                    ))
        messages.append(LLMMessage(role="user", content=prompt))

        req = LLMRequest(
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            prompt=prompt,
            system_prompt=system_prompt,
        )
        res = await self.generate(req)
        return res.content

    async def check_health(self) -> bool:
        """
        Performs a lightweight connectivity/credential health check.
        Returns True if operational, False otherwise.
        """
        try:
            req = LLMRequest(
                messages=[LLMMessage(role="user", content="ping")],
                max_tokens=5,
            )
            res = await self.generate(req)
            return bool(res and res.content)
        except Exception:
            return False
