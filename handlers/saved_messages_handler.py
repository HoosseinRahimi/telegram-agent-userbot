"""
Saved Messages ('me') Command Handler.

Enables on-demand control of the userbot by sending text commands directly
to Saved Messages:
- /summary <channel> [limit] [topic] : Summarizes a single channel or chat.
- /digest [limit]                    : Generates a digest across all configured channels.
- /pause [minutes]                   : Temporarily pauses auto-reply.
- /resume                            : Resumes auto-reply.
- /mode <gemini|openai|mock>         : Switches the active LLM engine on the fly.
- /blacklist <add|remove> <target>   : Dynamically manages the blacklist.
- /status                            : Displays current userbot operational status.
- /help                              : Lists available commands and usage guide.
"""

from __future__ import annotations

import logging
from typing import Any, List, Optional

from config.settings import Settings
from filters.blacklist_filter import BlacklistFilter
from filters.pipeline import FilterPipeline
from llm.factory import create_llm_provider
from services.auto_reply_service import AutoReplyService
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
    auto_reply_service: Optional[AutoReplyService] = None,
    filter_pipeline: Optional[FilterPipeline] = None,
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

        parts = text.split()
        cmd = parts[0].lower()

        # 1. /summary
        if cmd in ("/summary", "/خلاصه"):
            target, limit, topic = parse_summary_args(text)
            if not target:
                await client.send_message(
                    "me",
                    "ℹ️ **راهنمای دستور خلاصه‌سازی:**\n"
                    "`/summary @channel_username [تعداد پیام] [موضوع اختیاری]`\n"
                    "مثال: `/summary @durov 25 اخبار تلگرام`",
                )
                return

            await client.send_message(
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

        # 2. /digest
        elif cmd in ("/digest", "/بولتن"):
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

        # 3. /pause
        elif cmd in ("/pause", "/توقف"):
            if not auto_reply_service:
                await client.send_message("me", "⚠️ سرویس پاسخ‌دهی خودکار در دسترس نیست.")
                return

            minutes = None
            if len(parts) >= 2 and parts[1].isdigit():
                minutes = int(parts[1])

            msg = auto_reply_service.pause(minutes)
            await client.send_message("me", msg)

        # 4. /resume
        elif cmd in ("/resume", "/ادامه"):
            if not auto_reply_service:
                await client.send_message("me", "⚠️ سرویس پاسخ‌دهی خودکار در دسترس نیست.")
                return

            msg = auto_reply_service.resume()
            await client.send_message("me", msg)

        # 5. /mode
        elif cmd in ("/mode", "/مدل"):
            if len(parts) < 2:
                current = settings.llm_provider
                await client.send_message(
                    "me",
                    f"ℹ️ موتور فعال کنونی: `{current.upper()}`\n"
                    "نحوه تغییر: `/mode <gemini|openai|mock>`",
                )
                return

            new_mode = parts[1].lower()
            if new_mode not in ("gemini", "openai", "mock"):
                await client.send_message(
                    "me",
                    "❌ مدل نامعتبر است. گزینه‌های مجاز: `gemini` یا `openai` یا `mock`",
                )
                return

            try:
                settings.llm_provider = new_mode
                new_provider = create_llm_provider(settings)
                if auto_reply_service:
                    auto_reply_service.llm = new_provider
                digest_service.llm = new_provider
                await client.send_message(
                    "me",
                    f"🧠 موتور هوش مصنوعی با موفقیت به `{new_mode.upper()}` تغییر یافت.",
                )
            except Exception as exc:
                logger.error(f"[SavedMessagesHandler] Error switching LLM mode: {exc}")
                await client.send_message("me", f"❌ خطا در تغییر موتور هوش مصنوعی: {exc}")

        # 6. /blacklist
        elif cmd in ("/blacklist", "/بلاک"):
            if len(parts) < 3 or parts[1].lower() not in ("add", "remove"):
                await client.send_message(
                    "me",
                    "ℹ️ **راهنمای مدیریت لیست سیاه:**\n"
                    "• افزودن: `/blacklist add @username` یا `/blacklist add 12345678`\n"
                    "• حذف: `/blacklist remove @username` یا `/blacklist remove 12345678`",
                )
                return

            action = parts[1].lower()
            target_entry = parts[2].strip()

            # Find BlacklistFilter in pipeline
            bl_filter: Optional[BlacklistFilter] = None
            if filter_pipeline:
                for flt in filter_pipeline.filters:
                    if isinstance(flt, BlacklistFilter):
                        bl_filter = flt
                        break

            if action == "add":
                if bl_filter:
                    added_repr = bl_filter.add_entry(target_entry)
                else:
                    added_repr = target_entry
                if target_entry not in settings.blacklist_users:
                    settings.blacklist_users.append(target_entry)
                await client.send_message(
                    "me",
                    f"🚫 شناسه/کاربر `{added_repr}` با موفقیت به لیست سیاه اضافه شد.",
                )
            elif action == "remove":
                removed = False
                if bl_filter:
                    removed = bl_filter.remove_entry(target_entry)
                if target_entry in settings.blacklist_users:
                    settings.blacklist_users.remove(target_entry)
                    removed = True
                if removed:
                    await client.send_message(
                        "me",
                        f"✅ شناسه/کاربر `{target_entry}` با موفقیت از لیست سیاه حذف شد.",
                    )
                else:
                    await client.send_message(
                        "me",
                        f"⚠️ شناسه/کاربر `{target_entry}` در لیست سیاه یافت نشد.",
                    )

        # 7. /status
        elif cmd in ("/status", "/وضعیت"):
            channels_repr = ", ".join(str(c) for c in settings.digest_channels) if settings.digest_channels else "تنظیم نشده"
            pause_status = "🟢 فعال"
            if auto_reply_service and auto_reply_service.check_is_paused():
                if auto_reply_service.paused_until:
                    pause_status = f"⏸️ متوقف (تا {auto_reply_service.paused_until.strftime('%H:%M:%S')})"
                else:
                    pause_status = "⏸️ متوقف (تا دستور بعدی)"

            status_text = (
                "🤖 **وضعیت یوزربات تلگرام (Userbot Status)**\n"
                "━━━━━━━━━━━━━━━━━━━━━\n"
                f"🟢 **وضعیت اتصال:** آنلاین و آماده\n"
                f"💬 **پاسخ‌دهی خودکار (Auto-Reply):** {pause_status}\n"
                f"🧠 **موتور هوش مصنوعی:** `{settings.llm_provider.upper()}`\n"
                f"🎯 **کانال‌های دایجست:** `{channels_repr}`\n"
                f"⏱️ **بازه خلاصه‌سازی خودکار:** `{settings.digest_interval_minutes}` دقیقه\n"
                f"🚫 **تعداد لیست سیاه:** `{len(settings.blacklist_users)}` شناسه/کاربر\n"
                f"🛡️ **لایه‌های امنیتی:** FloodWait Backoff + ChatDebouncer + Active Cooldown"
            )
            await client.send_message("me", status_text)

        # 8. /help
        elif cmd in ("/help", "/راهنما"):
            help_text = (
                "📖 **راهنمای فرامین تلگرام یوزربات (در Saved Messages):**\n"
                "━━━━━━━━━━━━━━━━━━━━━\n"
                "• `/summary <کانال> [تعداد] [موضوع]` : خلاصه‌سازی فوری چت یا کانال\n"
                "• `/digest [تعداد پیام]` : تولید بولتن تجمیعی از کانال‌های منتخب\n"
                "• `/pause [دقیقه]` : توقف موقت پاسخ‌دهی خودکار\n"
                "• `/resume` : فعال‌سازی مجدد پاسخ‌دهی خودکار\n"
                "• `/mode <gemini|openai|mock>` : تغییر آنلاین موتور هوش مصنوعی\n"
                "• `/blacklist <add|remove> <کاربر>` : مدیریت پویا لیست سیاه\n"
                "• `/status` : مشاهده وضعیت سلامت، تنظیمات و پایشگرها\n"
                "• `/help` : نمایش این راهنما\n\n"
                "💡 *کلیه خروجی‌ها و گزارش‌ها مستقیماً در همین بخش (Saved Messages) تحویل می‌گردند.*"
            )
            await client.send_message("me", help_text)

    if event_filter is not None and hasattr(client, "add_event_handler"):
        client.add_event_handler(_on_saved_message, event_filter)
        logger.info("[SavedMessagesHandler] Registered Saved Messages command listener.")
    elif hasattr(client, "add_event_handler"):
        client.add_event_handler(_on_saved_message)
