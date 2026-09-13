"""
Base abstractions and data structures for message filtering pipeline.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional, Union


@dataclass
class FilterResult:
    """Outcome produced by a filter check."""
    allowed: bool
    reason: Optional[str] = None
    is_security_alert: bool = False
    matched_keyword: Optional[str] = None

    @classmethod
    def allow(cls) -> FilterResult:
        return cls(allowed=True)

    @classmethod
    def block(
        cls,
        reason: str,
        is_security_alert: bool = False,
        matched_keyword: Optional[str] = None,
    ) -> FilterResult:
        return cls(
            allowed=False,
            reason=reason,
            is_security_alert=is_security_alert,
            matched_keyword=matched_keyword,
        )


@dataclass
class FilterContext:
    """Context information about an incoming message evaluated by filters."""
    sender_id: Union[int, str]
    sender_username: Optional[str] = None
    is_bot: bool = False
    is_self: bool = False
    text: str = ""
    chat_id: Union[int, str] = 0
    raw_event: Optional[Any] = None


class BaseFilter(ABC):
    """Abstract interface for all message filters."""

    @property
    def filter_name(self) -> str:
        return self.__class__.__name__

    @abstractmethod
    async def check(self, context: FilterContext) -> FilterResult:
        """
        Evaluates the context and returns whether the message is allowed to proceed.
        """
        pass
