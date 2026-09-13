"""
Bot Account Filter.

Rejects messages originating from Telegram bot accounts to prevent infinite loops,
automated spam, and bot-to-bot conversational deadlock.
"""

from __future__ import annotations

from .base import BaseFilter, FilterContext, FilterResult


class BotFilter(BaseFilter):
    """
    Blocks incoming messages sent by bot accounts.
    """

    async def check(self, context: FilterContext) -> FilterResult:
        if context.is_bot:
            return FilterResult.block(reason="Blocked bot account (is_bot=True).")

        if context.sender_username:
            uname = context.sender_username.lower().lstrip("@")
            if uname.endswith("bot"):
                return FilterResult.block(
                    reason=f"Blocked sender with bot username suffix (@{uname})."
                )

        return FilterResult.allow()
