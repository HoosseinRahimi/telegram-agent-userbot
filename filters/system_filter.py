"""
System Account and Self-Message Filter.

Unconditionally blocks Telegram official service accounts (ID 777000) and self-sent messages
to prevent accidental loops or replying to Telegram service notifications.
"""

from __future__ import annotations

from .base import BaseFilter, FilterContext, FilterResult

TELEGRAM_SERVICE_IDS: set[int | str] = {777000, "777000", 42777, "42777"}
TELEGRAM_SERVICE_USERNAMES: set[str] = {"telegram", "telegramnotifications", "service_notifications"}


class SystemFilter(BaseFilter):
    """
    Blocks Telegram system notifications and self-sent messages.
    """

    async def check(self, context: FilterContext) -> FilterResult:
        # Check self-sent
        if context.is_self:
            return FilterResult.block(reason="Message sent by self (outgoing).")

        # Check official Telegram service IDs
        sender_id = context.sender_id
        if sender_id in TELEGRAM_SERVICE_IDS or str(sender_id) in TELEGRAM_SERVICE_IDS:
            return FilterResult.block(
                reason=f"Blocked Telegram official service account (ID: {sender_id})."
            )

        # Check service usernames
        if context.sender_username:
            uname = context.sender_username.lower().lstrip("@")
            if uname in TELEGRAM_SERVICE_USERNAMES:
                return FilterResult.block(
                    reason=f"Blocked Telegram official service username (@{uname})."
                )

        return FilterResult.allow()
