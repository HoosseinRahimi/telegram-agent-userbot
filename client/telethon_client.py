"""
Telethon MTProto Client Wrapper & Session Manager.

Encapsulates client initialization, authentication lifecycle, event wiring,
and decorated safe MTProto operations with anti-ban protection.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from config.settings import Settings

from .anti_ban import with_floodwait

logger = logging.getLogger(__name__)


class UserbotClient:
    """
    High-level Telegram MTProto userbot client managing connection lifecycle,
    session security, and anti-ban safe message interactions.
    """

    def __init__(self, settings: Settings, raw_client: Any | None = None) -> None:
        self.settings = settings
        self._raw_client = raw_client
        self._is_started = False

    @property
    def client(self) -> Any:
        """Returns the underlying Telethon client instance, creating it lazily if not provided."""
        if self._raw_client is None:
            from telethon import TelegramClient
            from telethon.sessions import StringSession

            session: str | StringSession
            if self.settings.telegram_session_string:
                session = StringSession(self.settings.telegram_session_string)
            else:
                session = self.settings.telegram_session_name

            self._raw_client = TelegramClient(
                session,
                self.settings.telegram_api_id,
                self.settings.telegram_api_hash,
            )
        return self._raw_client

    async def start(self) -> None:
        """Connects and starts the Telegram client session."""
        if not self._is_started:
            logger.info("[Client] Starting Telegram userbot client...")
            raw = self.client
            if hasattr(raw, "start"):
                await raw.start()
            self._is_started = True
            me = await self.get_me()
            if me:
                first_name = getattr(me, "first_name", "") or ""
                username = getattr(me, "username", "") or ""
                user_id = getattr(me, "id", "unknown")
                logger.info(f"[Client] Authenticated as {first_name} (@{username}, ID={user_id})")

    async def disconnect(self) -> None:
        """Safely terminates the Telegram connection."""
        if self._raw_client and hasattr(self._raw_client, "disconnect"):
            logger.info("[Client] Disconnecting Telegram client...")
            await self._raw_client.disconnect()
        self._is_started = False

    async def run_until_disconnected(self) -> None:
        """Blocks until the client disconnects."""
        if self._raw_client and hasattr(self._raw_client, "run_until_disconnected"):
            await self._raw_client.run_until_disconnected()

    def add_event_handler(self, callback: Callable[..., Any], event: Any) -> None:
        """Registers an event handler on the Telethon client."""
        self.client.add_event_handler(callback, event)

    async def get_me(self) -> Any:
        """Retrieves information about the currently authenticated user."""
        if hasattr(self.client, "get_me"):
            return await self.client.get_me()
        return None

    @with_floodwait(max_retries=3, max_wait_seconds=300)
    async def send_message_safe(
        self,
        entity: Any,
        message: str,
        reply_to: Any | None = None,
        **kwargs: Any,
    ) -> Any:
        """
        Sends a message with FloodWait protection and automatic retries.
        """
        return await self.client.send_message(
            entity=entity,
            message=message,
            reply_to=reply_to,
            **kwargs,
        )

    @with_floodwait(max_retries=3, max_wait_seconds=300)
    async def send_read_acknowledge_safe(
        self,
        entity: Any,
        max_id: int | None = None,
        **kwargs: Any,
    ) -> Any:
        """
        Marks messages as read in a chat with FloodWait protection.
        """
        if hasattr(self.client, "send_read_acknowledge"):
            return await self.client.send_read_acknowledge(entity=entity, max_id=max_id, **kwargs)
        return None

    async def iter_messages_safe(
        self,
        entity: Any,
        limit: int = 50,
        **kwargs: Any,
    ) -> list[Any]:
        """
        Fetches message history from a chat or channel with FloodWait protection.
        Returns a list of message objects.
        """
        @with_floodwait(max_retries=3, max_wait_seconds=300)
        async def _fetch() -> list[Any]:
            messages = []
            if hasattr(self.client, "iter_messages"):
                async for msg in self.client.iter_messages(entity, limit=limit, **kwargs):
                    messages.append(msg)
            elif hasattr(self.client, "get_messages"):
                res = await self.client.get_messages(entity, limit=limit, **kwargs)
                messages = list(res) if res else []
            return messages

        return await _fetch()
