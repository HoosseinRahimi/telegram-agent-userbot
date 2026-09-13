"""
Saved Messages ('me') Command Handler.

Enables on-demand control of the userbot by sending text commands directly
to Saved Messages:
- /summary <channel> [limit] : Summarizes a single channel or chat.
- /digest [limit]            : Generates a digest across all configured channels.
- /status                    : Displays current userbot operational status.
- /help                      : Lists available commands and usage guide.
"""

from __future__ import annotations

import logging
from typing import Any, List, Optional

from config.settings import Settings
from services.digest_service import DigestService

logger = logging.getLogger(__name__)


def parse_summary_args(text: str) -> tuple[Optional[str], int, Optional[str]]:
    """
    Parses command arguments from: /summary <target> [limit] [topic...]
    Returns (target, limit, topic).
    """
    parts = text.strip().split()
    if len(parts) < 2:
        return None, 30, None

    target = parts[1]
    limit = 30
    topic = None

    if len(parts) >= 3 and parts[2].isdigit():
        limit = min(max(int(parts[2]), 5), 100)
        if len(parts) >= 4:
            topic = " ".join(parts[3:])
    elif len(parts) >= 3:
        topic = " ".join(parts[2:])

    return target, limit, topic


def register_saved_messages_handler(
    client: Any,
    digest_service: DigestService,
    settings: Settings,
) -> None:
    """
    Registers a Telethon NewMessage listener restricted to 'me' (Saved Messages).
    """
    try:
        from telethon import events
        event_filter = events.NewMessage(chats="me")
    except ImportError:
        event_filter = None

    async def _on_saved_message(event: Any) -> None:
        text = (getattr(event, "raw_text", "") or getattr(event, "text", "") or "").strip()
        if not text.startswith("/"):
            return

        cmd = text.split()[0].lower()

        if cmd in ("/summary", "/خلاصه"):
            target, limit, topic = parse_summary_args(text)
            if not target:
                await client.send_message(
                    "me",
                    "ℹ️ **راهنمای دستور خلاصه‌سازی:**\n"
                    "`/summary @channel_username [تعداد پیام]`\n"
                    "مثال: `/summary @durov 25`",
                )
                return

            status_msg = await client.send_message(
                "me",
                f"⏳ در حال اسکن {limit} پیام اخیر از `{target}` و تولید خلاصه تحلیلی...",
            )

            try:
                summary = await digest_service.summarize_chat(
                    entity=target,
                    limit=limit,
                    custom_topic=topic,
                )
                await digest_service.deliver_digest(
                    target_entity="me",
                    title=f"خلاصه تحلیلی اختصاصی: {target}",
                    summary_content=summary,
                )
            except Exception as exc:
                logger.error(f"[SavedMessagesHandler] Error running /summary: {exc}")
                await client.send_message("me", f"❌ خطا در اجرای خلاصه‌سازی: {exc}")

        elif cmd in ("/digest", "/بولتن"):
            parts = text.split()
            limit = 20
            if len(parts) >= 2 and parts[1].isdigit():
                limit = min(max(int(parts[1]), 5), 50)

            channels = settings.digest_channels
            if not channels:
                await client.send_message(
                    "me",
                    "⚠️ هیچ کانالی در تنظیمات `DIGEST_CHANNELS` در فایل `.env` تعریف نشده است.",
                )
                return

            await client.send_message(
                "me",
                f"⏳ در حال جمع‌آوری و تحلیل پیام‌های {len(channels)} کانال منتخب (هر کدام {limit} پیام)...",
            )

            try:
                await digest_service.generate_channels_digest(
                    channels=channels,
                    limit_per_channel=limit,
                    deliver_to="me",
                )
            except Exception as exc:
                logger.error(f"[SavedMessagesHandler] Error running /digest: {exc}")
                await client.send_message("me", f"❌ خطا در تولید دایجست: {exc}")

        elif cmd in ("/status", "/وضعیت"):
            channels_repr = ", ".join(settings.digest_channels) if settings.digest_channels else "تنظیم نشده"
            status_text = (
                "🤖 **وضعیت یوزربات تلگرام (Userbot Status)**\n"
                "━━━━━━━━━━━━━━━━━━━━━\n"
                f"🟢 **وضعیت اتصال:** آنلاین و فعال\n"
                f"🧠 **موتور هوش مصنوعی:** `{settings.llm_provider.upper()}`\n"
                f"🎯 **کانال‌های دایجست:** `{channels_repr}`\n"
                f"⏱️ **بازه خلاصه‌سازی خودکار:** `{settings.digest_interval_minutes}` دقیقه\n"
                f"🚫 **تعداد لیست سیاه:** `{len(settings.blacklist_users)}` کاربر/شناسه\n"
                f"🛡️ **لایه‌های امنیتی ضد بن:** فعال (FloodWait Backoff + Humanizer)"
            )
            await client.send_message("me", status_text)

        elif cmd in ("/help", "/راهنما"):
            help_text = (
                "📖 **راهنمای فرامین تلگرام یوزربات (در Saved Messages):**\n"
                "━━━━━━━━━━━━━━━━━━━━━\n"
                "• `/summary <کانال/چت> [تعداد]` : خلاصه‌سازی فوری پیام‌های یک کانال\n"
                "• `/digest [تعداد پیام]` : استخراج و تولید بولتن از تمام کانال‌های منتخب\n"
                "• `/status` : مشاهده وضعیت سلامت و تنظیمات ایجنت\n"
                "• `/help` : نمایش این راهنما\n\n"
                "💡 *نکته: کلیه پاسخ‌ها و گزارش‌ها مستقیماً در همین بخش (Saved Messages) تحویل می‌گردند.*"
            )
            await client.send_message("me", help_text)

    if event_filter is not None and hasattr(client, "add_event_handler"):
        client.add_event_handler(_on_saved_message, event_filter)
        logger.info("[SavedMessagesHandler] Registered Saved Messages command listener.")
    elif hasattr(client, "add_event_handler"):
        client.add_event_handler(_on_saved_message)
