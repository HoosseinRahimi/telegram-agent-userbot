"""
Unified Telegram Message Sender Abstraction.

Provides safe, resilient message dispatching to Telegram:
- Automatic message chunking (<= 4096 characters per Telegram protocol limits).
- Markdown-safe fallback: falls back to plain text if Telegram Markdown parsing fails.
- Unified FloodWait recovery and retries.
- Sensitive alert redaction and truncation.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from client.telethon_client import UserbotClient

logger = logging.getLogger(__name__)

# Maximum allowed characters in a single Telegram message
MAX_TELEGRAM_MESSAGE_LENGTH = 4096


def split_text_into_chunks(text: str, max_length: int = MAX_TELEGRAM_MESSAGE_LENGTH) -> list[str]:
    """
    Splits long text into manageable chunks respecting word and paragraph boundaries.
    """
    if not text:
        return []
    if len(text) <= max_length:
        return [text]

    chunks: list[str] = []
    remaining = text

    while len(remaining) > max_length:
        split_pos = -1

        # Prefer splitting on double newline (paragraph boundary)
        pos = remaining.rfind("\n\n", 0, max_length)
        if pos != -1 and pos >= max_length // 2:
            split_pos = pos + 2

        # Next prefer single newline
        if split_pos == -1:
            pos = remaining.rfind("\n", 0, max_length)
            if pos != -1 and pos >= max_length // 3:
                split_pos = pos + 1

        # Next prefer whitespace
        if split_pos == -1:
            pos = remaining.rfind(" ", 0, max_length)
            if pos != -1 and pos >= max_length // 4:
                split_pos = pos + 1

        # Hard cutoff fallback
        if split_pos == -1:
            split_pos = max_length

        chunk = remaining[:split_pos].rstrip()
        if chunk:
            chunks.append(chunk)
        remaining = remaining[split_pos:].lstrip()

    if remaining:
        chunks.append(remaining)

    return chunks


def redact_sensitive_text(text: str, max_length: int | None = 200) -> str:
    """
    Redacts credentials, card numbers, and tokens.
    If max_length is provided, truncates text for safe logging/alerts.
    """
    if not text:
        return ""

    content = text
    if max_length is not None and len(content) > max_length:
        content = content[:max_length] + "... [متن طولانی کوتاه شد]"

    # Mask private keys
    content = re.sub(
        r"-----BEGIN [A-Z ]+ PRIVATE KEY-----[\s\S]*?-----END [A-Z ]+ PRIVATE KEY-----",
        "[REDACTED_PRIVATE_KEY]",
        content,
    )
    content = re.sub(r"-----BEGIN [A-Z ]+ PRIVATE KEY-----", "[REDACTED_PRIVATE_KEY]", content)

    # Mask API keys
    content = re.sub(r"\b(sk-[a-zA-Z0-9]{6})[a-zA-Z0-9]{14,}\b", r"\1...[REDACTED_TOKEN]", content)
    content = re.sub(r"\b(AIzaSy)[a-zA-Z0-9_-]{27}\b", r"\1...[REDACTED_KEY]", content)

    # Mask 16-digit card patterns (ASCII and Persian/Arabic digits)
    content = re.sub(r"\b(\d{4})[- ]?(\d{4})[- ]?(\d{4})[- ]?(\d{4})\b", r"\1-****-****-\4", content)
    content = re.sub(r"\b([۰-۹]{4})[- ]?([۰-۹]{4})[- ]?([۰-۹]{4})[- ]?([۰-۹]{4})\b", r"\1-****-****-\4", content)

    # Mask 4-8 digit potential OTPs next to sensitive words
    content = re.sub(r"(?i)(code|otp|رمز|کد)([^:\n\d]{0,20})[:=]?\s*(\d{4,8})", r"\1\2: ****", content)
    content = re.sub(r"(?i)(code|otp|رمز|کد)([^:\n\d]{0,20})[:=]?\s*([۰-۹]{4,8})", r"\1\2: ****", content)

    return content


class TelegramMessageSender:
    """
    Centralized dispatcher for sending Telegram messages safely.
    Handles chunking, Markdown fallback, and FloodWait resilience.
    """

    def __init__(self, userbot_client: UserbotClient) -> None:
        self.client = userbot_client

    async def send_message(
        self,
        entity: int | str,
        text: str,
        reply_to: int | None = None,
        parse_mode: str | None = "md",
        max_chunk_length: int = MAX_TELEGRAM_MESSAGE_LENGTH,
    ) -> list[Any]:
        """
        Sends text to entity, splitting into chunks if text exceeds Telegram limits.
        Falls back to plain text if Markdown parsing errors occur.
        """
        if not text or not text.strip():
            logger.warning(f"[TelegramMessageSender] Attempted to send empty message to {entity}")
            return []

        chunks = split_text_into_chunks(text, max_length=max_chunk_length)
        sent_messages: list[Any] = []

        for idx, chunk in enumerate(chunks):
            current_reply_to = reply_to if idx == 0 else None
            try:
                msg = await self.client.send_message_safe(
                    entity=entity,
                    message=chunk,
                    reply_to=current_reply_to,
                    parse_mode=parse_mode,
                )
                sent_messages.append(msg)
            except Exception as exc:
                err_str = str(exc).lower()
                # If markdown parsing error, retry without parse mode
                if "parse" in err_str or "markdown" in err_str or "entity" in err_str:
                    logger.warning(
                        f"[TelegramMessageSender] Markdown parsing failed ({exc}). "
                        f"Retrying chunk {idx + 1}/{len(chunks)} in plain text mode."
                    )
                    try:
                        msg = await self.client.send_message_safe(
                            entity=entity,
                            message=chunk,
                            reply_to=current_reply_to,
                            parse_mode=None,
                        )
                        sent_messages.append(msg)
                    except Exception as retry_exc:
                        logger.error(f"[TelegramMessageSender] Failed to send plain text chunk: {retry_exc}")
                else:
                    logger.error(f"[TelegramMessageSender] Failed to send message chunk: {exc}")

        return sent_messages
