"""
Security Alert Service.

Dispatches high-priority security notifications to Telegram Saved Messages ('me')
whenever confidential keywords, OTPs, or suspicious interactions are intercepted.
"""

from __future__ import annotations

from datetime import datetime
import logging
from typing import Any, Optional

from client.telethon_client import UserbotClient
from filters.base import FilterContext

logger = logging.getLogger(__name__)


class AlertService:
    """
    Formats and delivers security alerts to the user's Saved Messages.
    """

    def __init__(self, userbot_client: UserbotClient) -> None:
        self.client = userbot_client

    async def send_security_alert(
        self,
        context: FilterContext,
        matched_keyword: Optional[str] = None,
        reason: Optional[str] = None,
    ) -> Any:
        """
        Constructs and dispatches a structured security alert to 'me'.
        """
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        sender_repr = f"ID: `{context.sender_id}`"
        if context.sender_username:
            sender_repr += f" (@{context.sender_username})"

        alert_text = (
            "🚨 **هشدار امنیتی تلگرام یوزربات | Security Alert**\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"⚠️ **علت هشدار:** شناسایی محتوای حساس و توقف پاسخ خودکار\n"
            f"👤 **فرستنده:** {sender_repr}\n"
            f"🔑 **کلیدواژه شناسایی‌شده:** `{matched_keyword or 'حساس/محرمانه'}`\n"
            f"⏰ **زمان:** `{now}`\n\n"
            f"📝 **متن پیام دریافتی:**\n"
            f"> {context.text}\n\n"
            "🛡️ **وضعیت ایجنت:** پاسخ‌دهی خودکار به این پیام بلافاصله متوقف گردید."
        )

        logger.warning(
            f"[AlertService] Dispatching security alert for sender {context.sender_id} "
            f"(keyword: {matched_keyword}) to Saved Messages."
        )

        try:
            return await self.client.send_message_safe("me", alert_text)
        except Exception as exc:
            logger.error(f"[AlertService] Failed to deliver security alert to 'me': {exc}")
            return None
