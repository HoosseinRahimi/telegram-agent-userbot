"""
Blacklist Filter.

Blocks users, channels, or chats configured in the userbot's blacklist.
Supports matching by numeric user ID or username (case-insensitive).
"""

from __future__ import annotations

from collections.abc import Iterable

from .base import BaseFilter, FilterContext, FilterResult


class BlacklistFilter(BaseFilter):
    """
    Blocks senders whose ID or username appears in the blacklist.
    """

    def __init__(self, blacklist: Iterable[int | str] | None = None) -> None:
        self.blacklisted_ids: set[int | str] = set()
        self.blacklisted_usernames: set[str] = set()

        if blacklist:
            for item in blacklist:
                if item is None:
                    continue
                s_item = str(item).strip()
                if not s_item:
                    continue
                if s_item.lstrip("-").isdigit():
                    self.blacklisted_ids.add(int(s_item))
                    self.blacklisted_ids.add(s_item)
                else:
                    self.blacklisted_usernames.add(s_item.lower().lstrip("@"))

    async def check(self, context: FilterContext) -> FilterResult:
        # Check numeric ID
        sender_id = context.sender_id
        if sender_id in self.blacklisted_ids or str(sender_id) in self.blacklisted_ids:
            return FilterResult.block(
                reason=f"Blocked sender ID {sender_id} matching blacklist."
            )

        # Check username
        if context.sender_username:
            uname = context.sender_username.lower().lstrip("@")
            if uname in self.blacklisted_usernames:
                return FilterResult.block(
                    reason=f"Blocked username @{uname} matching blacklist."
                )

        return FilterResult.allow()

    def add_entry(self, item: int | str) -> str:
        """Dynamically adds an ID or username to the blacklist."""
        s_item = str(item).strip()
        if not s_item:
            return ""
        if s_item.lstrip("-").isdigit():
            self.blacklisted_ids.add(int(s_item))
            self.blacklisted_ids.add(s_item)
            return s_item
        else:
            uname = s_item.lower().lstrip("@")
            self.blacklisted_usernames.add(uname)
            return f"@{uname}"

    def remove_entry(self, item: int | str) -> bool:
        """Dynamically removes an ID or username from the blacklist."""
        s_item = str(item).strip()
        removed = False
        if s_item.lstrip("-").isdigit():
            val = int(s_item)
            if val in self.blacklisted_ids or s_item in self.blacklisted_ids:
                self.blacklisted_ids.discard(val)
                self.blacklisted_ids.discard(s_item)
                removed = True
        else:
            uname = s_item.lower().lstrip("@")
            if uname in self.blacklisted_usernames:
                self.blacklisted_usernames.discard(uname)
                removed = True
        return removed

