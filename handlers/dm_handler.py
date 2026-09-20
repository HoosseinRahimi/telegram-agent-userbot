"""
Direct Message (DM) Event Handler.

Listens for incoming private messages in Telethon and delegates processing
to the ChatDebouncer and AutoReplyService.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from filters.base import FilterContext
from services.auto_reply_service import AutoReplyService
from services.chat_debouncer import ChatDebouncer

logger = logging.getLogger(__name__)


def register_dm_handler(
    client: Any,
    auto_reply_service: AutoReplyService,
    debouncer: ChatDebouncer | None = None,
    max_message_age_seconds: int = 300,
    dedup_ttl_seconds: int = 600,
) -> ChatDebouncer:
    """
    Registers a Telethon NewMessage event handler for private chats.
    Wires incoming messages through the ChatDebouncer with:
    - Media-only policy: ignores messages with no text/caption to avoid LLM token waste.
    - Message age cutoff: ignores messages older than max_message_age_seconds (e.g. 5 mins) to prevent backlog storms.
    - Deduplication: ignores retransmitted MTProto events with duplicate message IDs.
    Returns the active ChatDebouncer instance.
    """
    if debouncer is None:
        debouncer = ChatDebouncer(
            dispatch_callback=auto_reply_service.handle_incoming_private_message,
            debounce_delay=2.5,
        )

    # In-memory deduplication cache: message_id -> timestamp
    processed_message_ids: dict[int, float] = {}

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

        # 1. Media-only policy: Ignore messages with no text/caption
        text = (getattr(event, "raw_text", "") or getattr(event, "text", "") or "").strip()
        if not text:
            logger.debug("[DMHandler] Media-only message without text received. Skipping auto-reply.")
            return

        # 2. Message ID Deduplication
        message_id = getattr(event, "id", None)
        now_utc = datetime.now(timezone.utc)
        now_ts = now_utc.timestamp()

        nonlocal processed_message_ids
        if message_id is not None:
            if message_id in processed_message_ids:
                logger.debug(f"[DMHandler] Duplicate message ID {message_id} received. Skipping.")
                return
            processed_message_ids[message_id] = now_ts

            # Cleanup expired deduplication entries if cache grows
            if len(processed_message_ids) > 500:
                cutoff = now_ts - dedup_ttl_seconds
                processed_message_ids = {
                    mid: ts for mid, ts in processed_message_ids.items() if ts > cutoff
                }

        # 3. Message Age Cutoff: Ignore old messages (e.g. from downtime / reconnect backlog)
        msg_date = getattr(event, "date", None)
        if msg_date and max_message_age_seconds > 0:
            if hasattr(msg_date, "tzinfo") and msg_date.tzinfo:
                age_seconds = (now_utc - msg_date).total_seconds()
            else:
                age_seconds = (datetime.utcnow() - msg_date).total_seconds()

            if age_seconds > max_message_age_seconds:
                logger.info(
                    f"[DMHandler] Dropping message {message_id} from {getattr(event, 'sender_id', 0)}: "
                    f"Message is {age_seconds:.0f}s old (> {max_message_age_seconds}s cutoff)."
                )
                return

        # 4. Sender extraction
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

        chat_id = getattr(event, "chat_id", sender_id)
        is_self = getattr(event, "out", False)

        # 5. Retrieve quoted / reply-to message text if available
        quoted_text: str | None = None
        if getattr(event, "reply_to_msg_id", None):
            try:
                if hasattr(event, "get_reply_message"):
                    reply_msg = await event.get_reply_message()
                    if reply_msg:
                        quoted_text = getattr(reply_msg, "text", "") or getattr(reply_msg, "message", "") or ""
            except Exception as exc:
                logger.debug(f"[DMHandler] Could not fetch quoted message: {exc}")

        context = FilterContext(
            sender_id=sender_id,
            sender_username=sender_username,
            is_bot=is_bot,
            is_self=is_self,
            text=text,
            chat_id=chat_id,
            raw_event=event,
            quoted_text=quoted_text,
        )

        await debouncer.enqueue(context=context, message_id=message_id)

    if event_filter is not None and hasattr(client, "add_event_handler"):
        client.add_event_handler(_on_private_message, event_filter)
        logger.info("[DMHandler] Successfully registered DM event listener with ChatDebouncer.")
    elif hasattr(client, "add_event_handler"):
        client.add_event_handler(_on_private_message)

    return debouncer
