"""
Direct Message (DM) Event Handler.

Listens for incoming private messages in Telethon and delegates processing
to the AutoReplyService.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from filters.base import FilterContext
from services.auto_reply_service import AutoReplyService

logger = logging.getLogger(__name__)


def register_dm_handler(client: Any, auto_reply_service: AutoReplyService) -> None:
    """
    Registers a Telethon NewMessage event handler for private chats.
    """
    try:
        from telethon import events
        event_filter = events.NewMessage(incoming=True, func=lambda e: getattr(e, "is_private", False))
    except ImportError:
        # For mock testing environments where telethon is not directly imported
        event_filter = None

    async def _on_private_message(event: Any) -> None:
        # Ignore non-private messages
        if not getattr(event, "is_private", False):
            return

        sender = None
        sender_id = getattr(event, "sender_id", 0)
        sender_username = None
        is_bot = False

        try:
            if hasattr(event, "get_sender"):
                sender = await event.get_sender()
            elif hasattr(event, "sender"):
                sender = event.sender
        except Exception as exc:
            logger.debug(f"[DMHandler] Could not retrieve sender object: {exc}")

        if sender:
            sender_id = getattr(sender, "id", sender_id)
            sender_username = getattr(sender, "username", None)
            is_bot = getattr(sender, "bot", False)

        text = getattr(event, "raw_text", "") or getattr(event, "text", "") or ""
        chat_id = getattr(event, "chat_id", sender_id)
        is_self = getattr(event, "out", False)

        context = FilterContext(
            sender_id=sender_id,
            sender_username=sender_username,
            is_bot=is_bot,
            is_self=is_self,
            text=text,
            chat_id=chat_id,
            raw_event=event,
        )

        message_id = getattr(event, "id", None)
        await auto_reply_service.handle_incoming_private_message(
            context=context,
            message_id=message_id,
        )

    if event_filter is not None and hasattr(client, "add_event_handler"):
        client.add_event_handler(_on_private_message, event_filter)
        logger.info("[DMHandler] Successfully registered DM event listener.")
    elif hasattr(client, "add_event_handler"):
        client.add_event_handler(_on_private_message)
