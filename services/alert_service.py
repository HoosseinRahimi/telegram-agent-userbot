"""
Security Alert Service.

Dispatches high-priority security notifications to Telegram Saved Messages ('me')
whenever confidential keywords, OTPs, or suspicious interactions are intercepted.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from client.message_sender import TelegramMessageSender, redact_sensitive_text
from client.telethon_client import UserbotClient
from filters.base import FilterContext

logger = logging.getLogger(__name__)


class AlertService:
    """
    Formats and delivers security alerts to the user's Saved Messages with redaction,
    chunking, and anti-flood throttling.
    """

    def __init__(
        self,
        userbot_client: UserbotClient,
        throttle_cooldown_seconds: int = 60,
    ) -> None:
        self.client = userbot_client
        self.sender = TelegramMessageSender(userbot_client)
        self.throttle_cooldown_seconds = throttle_cooldown_seconds
        self._last_alert_time: dict[int, float] = {}  # sender_id -> timestamp
        self._suppressed_counts: dict[int, int] = {}  # sender_id -> count of suppressed alerts

    async def send_security_alert(
        self,
        context: FilterContext,
        matched_keyword: str | None = None,
        reason: str | None = None,
    ) -> Any:
        """
        Constructs and dispatches a structured security alert to 'me' with redacted sensitive details.
        Throttles alerts per sender to prevent flood in Saved Messages.
        """
        sender_id = context.sender_id
        now_dt = datetime.now()
        now_ts = now_dt.timestamp()

        # Check anti-flood throttling for the same sender
        if self.throttle_cooldown_seconds > 0 and sender_id in self._last_alert_time:
            elapsed = now_ts - self._last_alert_time[sender_id]
            if elapsed < self.throttle_cooldown_seconds:
                self._suppressed_counts[sender_id] = self._suppressed_counts.get(sender_id, 0) + 1
                logger.warning(
                    f"[AlertService] Throttling alert for sender {sender_id} "
                    f"({elapsed:.1f}s < {self.throttle_cooldown_seconds}s). "
                    f"Suppressed count: {self._suppressed_counts[sender_id]}"
                )
                return None

        suppressed = self._suppressed_counts.pop(sender_id, 0)
        self._last_alert_time[sender_id] = now_ts

        now = now_dt.strftime("%Y-%m-%d %H:%M:%S")
        sender_repr = f"ID: `{context.sender_id}`"
        if context.sender_username:
            sender_repr += f" (@{context.sender_username})"

        safe_text = redact_sensitive_text(context.text or "", max_length=200)

        suppressed_note = ""
        if suppressed > 0:
            suppressed_note = f"\n⚠️ **توجه:** تعداد {suppressed} پیام حساس دیگر از این کاربر در بازه خنک‌سازی دریافت و فشرده شد.\n"

        alert_text = (
            "🚨 **هشدار امنیتی تلگرام یوزربات | Security Alert**\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"⚠️ **علت هشدار:** {reason or 'شناسایی محتوای حساس و توقف پاسخ خودکار'}\n"
            f"👤 **فرستنده:** {sender_repr}\n"
            f"🔑 **کلیدواژه شناسایی‌شده:** `{matched_keyword or 'حساس/محرمانه'}`\n"
            f"⏰ **زمان:** `{now}`\n\n"
            f"📝 **متن پیام دریافتی (خلاصه/ماسک‌شده):**\n"
            f"> {safe_text}\n"
            f"{suppressed_note}\n"
            "🛡️ **وضعیت ایجنت:** پاسخ‌دهی خودکار به این پیام بلافاصله متوقف گردید."
        )

        logger.warning(
            f"[AlertService] Dispatching security alert for sender {context.sender_id} "
            f"(keyword: {matched_keyword}) to Saved Messages."
        )

        try:
            results = await self.sender.send_message("me", alert_text)
            return results[0] if results else None
        except Exception as exc:
            logger.error(f"[AlertService] Failed to deliver security alert to 'me': {exc}")
            return None
