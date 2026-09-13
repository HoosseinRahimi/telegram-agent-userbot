"""
Channel & Chat Summarization and Digest Service.

Extracts message history from channels, groups, and chats, feeds cleaned context
to the modular LLM engine, chunks responses, and delivers analytical digests.
"""

from __future__ import annotations

from datetime import datetime
import logging
from typing import Any, List, Optional, Union

from client.telethon_client import UserbotClient
from llm.base import BaseLLMProvider, LLMMessage, LLMRequest

logger = logging.getLogger(__name__)

TELEGRAM_MAX_MESSAGE_LENGTH = 4096


def split_text_chunks(text: str, max_size: int = 4000) -> List[str]:
    """
    Splits long messages into safe chunks within Telegram's character limits,
    preserving paragraph and line breaks wherever possible.
    """
    if len(text) <= max_size:
        return [text]

    chunks: List[str] = []
    lines = text.splitlines(keepends=True)
    current_chunk = ""

    for line in lines:
        if len(current_chunk) + len(line) <= max_size:
            current_chunk += line
        else:
            if current_chunk:
                chunks.append(current_chunk.strip())
                current_chunk = ""

            # If a single line exceeds max_size, split by characters
            while len(line) > max_size:
                chunks.append(line[:max_size])
                line = line[max_size:]
            current_chunk = line

    if current_chunk.strip():
        chunks.append(current_chunk.strip())

    return chunks


class DigestService:
    """
    Extracts chat histories, orchestrates LLM analytical summarization,
    and dispatches multi-part digests to Saved Messages.
    """

    def __init__(
        self,
        userbot_client: UserbotClient,
        llm_provider: BaseLLMProvider,
    ) -> None:
        self.client = userbot_client
        self.llm = llm_provider

    async def extract_chat_history(
        self,
        entity: Any,
        limit: int = 30,
    ) -> List[str]:
        """
        Fetches up to `limit` recent messages from the specified chat/channel.
        Returns cleaned chronological strings: [Sender]: Message text.
        """
        raw_messages = await self.client.iter_messages_safe(entity, limit=limit)
        history_lines: List[str] = []

        # Iterate in chronological order (oldest to newest)
        for msg in reversed(raw_messages):
            text = getattr(msg, "text", "") or getattr(msg, "message", "") or ""
            if not text.strip():
                continue

            sender_id = getattr(msg, "sender_id", "unknown")
            date_str = ""
            if hasattr(msg, "date") and msg.date:
                try:
                    date_str = msg.date.strftime("%H:%M")
                except Exception:
                    pass

            prefix = f"[{date_str}] " if date_str else ""
            history_lines.append(f"{prefix}{sender_id}: {text.strip()}")

        return history_lines

    async def summarize_chat(
        self,
        entity: Any,
        limit: int = 30,
        custom_topic: Optional[str] = None,
    ) -> str:
        """
        Extracts messages from `entity` and generates an analytical summary via the LLM.
        """
        history = await self.extract_chat_history(entity, limit=limit)
        if not history:
            return "❌ هیچ پیامی در تاریخچه اخیر این کانال یا چت برای خلاصه‌سازی یافت نشد."

        channel_title = str(entity)
        formatted_history = "\n".join(history)

        system_prompt = (
            "شما دستیار هوش مصنوعی تحلیلگر و خلاصه‌ساز تلگرام هستید.\n"
            "وظیفه شما بررسی تاریخچه پیام‌های ارائه‌شده و تولید خلاصه‌ای ساختاریافته، دقیق و تحلیلی است.\n"
            "خلاصه باید شامل بخش‌های زیر باشد:\n"
            "1. 📌 محورهای اصلی و موضوعات کلیدی\n"
            "2. 💡 نکات و رویدادهای مهم (به صورت بالت پوینت)\n"
            "3. 🔍 نتیجه‌گیری و جمع‌بندی کوتاه\n"
            "پاسخ را با زبان فارسی روان و خوانا، با فرمت‌بندی استاندارد تلگرام (Markdown) ارائه دهید."
        )

        user_prompt = (
            f"لطفاً تاریخچه {len(history)} پیام اخیر از «{channel_title}» را تحلیل و خلاصه کنید:\n\n"
            f"--- شروع تاریخچه پیام‌ها ---\n"
            f"{formatted_history}\n"
            f"--- پایان تاریخچه پیام‌ها ---"
        )
        if custom_topic:
            user_prompt += f"\nتمرکز ویژه بر موضوع: {custom_topic}"

        req = LLMRequest(
            messages=[
                LLMMessage(role="system", content=system_prompt),
                LLMMessage(role="user", content=user_prompt),
            ],
            temperature=0.3,
            max_tokens=1500,
        )

        response = await self.llm.generate(req)
        return response.content

    async def deliver_digest(
        self,
        target_entity: Any,
        title: str,
        summary_content: str,
    ) -> List[Any]:
        """
        Formats, chunks, and delivers a summary report to target entity (defaults to 'me').
        """
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        header = f"📰 **{title}**\n⏰ `{now}`\n━━━━━━━━━━━━━━━━━━━━━\n\n"
        full_text = header + summary_content

        chunks = split_text_chunks(full_text, max_size=3900)
        sent_messages = []

        for idx, chunk in enumerate(chunks):
            if len(chunks) > 1:
                chunk_header = f"*(بخش {idx + 1} از {len(chunks)})*\n" if idx > 0 else ""
                part_text = chunk_header + chunk
            else:
                part_text = chunk

            sent = await self.client.send_message_safe(target_entity, part_text)
            sent_messages.append(sent)

        return sent_messages

    async def generate_channels_digest(
        self,
        channels: List[Union[str, int]],
        limit_per_channel: int = 20,
        deliver_to: str = "me",
    ) -> List[Any]:
        """
        Collects messages across multiple configured channels, compiles a combined digest,
        and dispatches the report to 'me'.
        """
        if not channels:
            logger.info("[DigestService] No channels configured for digest.")
            return []

        summaries: List[str] = []
        for ch in channels:
            try:
                summary = await self.summarize_chat(ch, limit=limit_per_channel)
                summaries.append(f"### 📢 کانال/چت `{ch}`:\n{summary}\n")
            except Exception as exc:
                logger.error(f"[DigestService] Error summarizing channel {ch}: {exc}")
                summaries.append(f"### 📢 کانال/چت `{ch}`:\n⚠️ خطا در دریافت پیام‌ها: {exc}\n")

        combined = "\n━━━━━━━━━━━━━━━━━━━━━\n".join(summaries)
        return await self.deliver_digest(
            target_entity=deliver_to,
            title="گزارش تجمیعی کانال‌های منتخب تلگرام",
            summary_content=combined,
        )
