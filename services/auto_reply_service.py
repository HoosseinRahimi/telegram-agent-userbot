"""
Auto-Reply Orchestration Service.

Coordinates the end-to-end DM auto-reply lifecycle:
1. Verifies pause state (/pause /resume commands).
2. Filters incoming message (System accounts, bots, blacklist, sensitive keywords).
3. Triggers security alerts on sensitive/confidential events and halts reply.
4. Detects active human presence (active chat cooldown) to prevent interrupting live conversations.
5. Enriches conversational context with quoted/reply-to message and recent history.
6. Simulates realistic reading delay.
7. Queries the modular LLM engine with the configured persona.
8. Simulates typing action with proportional typing duration.
9. Dispatches the reply using safe MTProto call with anti-ban retries.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import logging
from pathlib import Path
from typing import Any, List, Optional

from client.telethon_client import UserbotClient
from filters.base import FilterContext
from filters.pipeline import FilterPipeline
from llm.base import BaseLLMProvider, LLMMessage, LLMRequest
from .alert_service import AlertService
from .humanizer import HumanizerService

logger = logging.getLogger(__name__)


def load_persona_prompt(file_path: str) -> str:
    """
    Loads persona system instructions from an external text file.
    Falls back to a default professional Persian persona if the file is missing.
    """
    path = Path(file_path)
    if path.exists() and path.is_file():
        try:
            content = path.read_text(encoding="utf-8").strip()
            if content:
                return content
        except Exception as exc:
            logger.warning(f"[AutoReplyService] Could not read persona file {file_path}: {exc}")

    return (
        "شما دستیار هوشمند و شخصی تلگرام هستید.\n"
        "وظیفه شما پاسخ‌دهی محترمانه، طبیعی، روان و دقیق به پیام‌های مخاطبان در چت خصوصی است.\n"
        "به زبان فارسی با لحنی دوستانه اما حرفه‌ای صحبت کنید.\n"
        "از پاسخ‌های کلیشه‌ای و تکرار نامتعارف ربات‌گونه پرهیز کنید."
    )


class AutoReplyService:
    """
    Manages automated, safe, human-like responses for private chats with
    concurrency protection, active chat cooldown, and pause control.
    """

    def __init__(
        self,
        userbot_client: UserbotClient,
        llm_provider: BaseLLMProvider,
        filter_pipeline: FilterPipeline,
        alert_service: AlertService,
        humanizer_service: HumanizerService,
        persona_prompt_path: str = "persona_prompt.txt",
        active_cooldown_seconds: int = 300,
    ) -> None:
        self.client = userbot_client
        self.llm = llm_provider
        self.pipeline = filter_pipeline
        self.alert_service = alert_service
        self.humanizer = humanizer_service
        self.persona_prompt = load_persona_prompt(persona_prompt_path)
        self.active_cooldown_seconds = active_cooldown_seconds

        # Dynamic pause control state
        self.is_paused: bool = False
        self.paused_until: Optional[datetime] = None

    def pause(self, minutes: Optional[int] = None) -> str:
        """Pauses auto-reply globally, either indefinitely or for a set duration."""
        self.is_paused = True
        if minutes and minutes > 0:
            self.paused_until = datetime.now() + timedelta(minutes=minutes)
            msg = f"⏸️ پاسخ‌دهی خودکار به مدت {minutes} دقیقه متوقف شد (تا {self.paused_until.strftime('%H:%M:%S')})."
        else:
            self.paused_until = None
            msg = "⏸️ پاسخ‌دهی خودکار تا دستور بعدی (/resume) متوقف شد."
        logger.info(f"[AutoReplyService] {msg}")
        return msg

    def resume(self) -> str:
        """Resumes auto-reply globally."""
        self.is_paused = False
        self.paused_until = None
        msg = "▶️ پاسخ‌دهی خودکار مجدداً فعال شد."
        logger.info(f"[AutoReplyService] {msg}")
        return msg

    def check_is_paused(self) -> bool:
        """Evaluates whether auto-reply is currently paused."""
        if not self.is_paused:
            return False
        if self.paused_until is not None:
            if datetime.now() >= self.paused_until:
                self.resume()
                return False
        return True

    async def handle_incoming_private_message(
        self,
        context: FilterContext,
        message_id: Optional[int] = None,
        quoted_text: Optional[str] = None,
    ) -> Optional[Any]:
        """
        Processes an incoming private message event through safety checks,
        active chat cooldown, LLM generation, and humanized dispatch.
        """
        # 0. Check pause state
        if self.check_is_paused():
            logger.debug("[AutoReplyService] Auto-reply is paused. Skipping incoming message.")
            return None

        # 1. Evaluate safety pipeline
        filter_result = await self.pipeline.evaluate(context)

        # 2. Check for security alerts (OTP, credentials, payment data)
        if filter_result.is_security_alert:
            logger.warning(
                f"[AutoReplyService] Sensitive content detected from {context.sender_id}. "
                f"Halting auto-reply and sending security alert to Saved Messages."
            )
            await self.alert_service.send_security_alert(
                context=context,
                matched_keyword=filter_result.matched_keyword,
                reason=filter_result.reason,
            )
            return None

        # 3. If blocked for any other reason (system account, bot, blacklist), silently ignore
        if not filter_result.allowed:
            logger.debug(f"[AutoReplyService] Message skipped: {filter_result.reason}")
            return None

        chat_id = context.chat_id or context.sender_id

        # 4. Fetch recent chat history to check active human cooldown and provide LLM context
        recent_history: List[LLMMessage] = []
        try:
            raw_msgs = await self.client.iter_messages_safe(chat_id, limit=8)

            # Check Active Chat Cooldown: did the bot owner send an outgoing message recently?
            if self.active_cooldown_seconds > 0:
                now_utc = datetime.now(timezone.utc)
                for msg in raw_msgs:
                    if getattr(msg, "out", False):
                        msg_date = getattr(msg, "date", None)
                        if msg_date:
                            if hasattr(msg_date, "tzinfo") and msg_date.tzinfo:
                                diff = (now_utc - msg_date).total_seconds()
                            else:
                                diff = (datetime.utcnow() - msg_date).total_seconds()

                            if 0 <= diff < self.active_cooldown_seconds:
                                logger.info(
                                    f"[AutoReplyService] Active human presence detected in chat {chat_id} "
                                    f"({diff:.0f}s ago). Cooldown active ({self.active_cooldown_seconds}s). Skipping auto-reply."
                                )
                                return None

            # Build chronological recent history (up to 5 recent non-empty messages)
            for msg in reversed(raw_msgs[:5]):
                text = getattr(msg, "text", "") or getattr(msg, "message", "") or ""
                if not text.strip():
                    continue
                is_out = getattr(msg, "out", False)
                role = "assistant" if is_out else "user"
                recent_history.append(LLMMessage(role=role, content=text.strip()))
        except Exception as exc:
            logger.debug(f"[AutoReplyService] Could not fetch chat history: {exc}")

        # 5. Simulate human reading time based on incoming text
        await self.humanizer.simulate_reading(context.text)

        # 6. Format current incoming message with quoted text if present
        effective_quoted = quoted_text or getattr(context, "quoted_text", None)
        current_input = context.text
        if effective_quoted and effective_quoted.strip():
            current_input = f'[در پاسخ به پیام: "{effective_quoted.strip()}"]\n{current_input}'

        # Ensure current incoming message is present in the messages list
        if not recent_history or recent_history[-1].content != current_input:
            recent_history.append(LLMMessage(role="user", content=current_input))

        # 7. Generate response via LLM
        req = LLMRequest(
            messages=[LLMMessage(role="system", content=self.persona_prompt)] + recent_history,
            temperature=0.7,
            max_tokens=800,
        )

        try:
            llm_response = await self.llm.generate(req)
            reply_text = (llm_response.content or "").strip()
        except Exception as exc:
            logger.error(f"[AutoReplyService] LLM generation failed: {exc}")
            return None

        if not reply_text:
            logger.warning("[AutoReplyService] LLM returned empty response. Skipping reply.")
            return None

        # 8. Simulate typing action and proportional typing duration
        await self.humanizer.simulate_typing_and_wait(
            entity=chat_id,
            reply_text=reply_text,
        )

        # 9. Dispatch reply to user
        logger.info(f"[AutoReplyService] Sending humanized reply to {chat_id} ({len(reply_text)} chars)")
        sent_msg = await self.client.send_message_safe(
            entity=chat_id,
            message=reply_text,
            reply_to=message_id,
        )

        # 10. Mark messages as read
        try:
            await self.client.send_read_acknowledge_safe(chat_id, max_id=message_id)
        except Exception as exc:
            logger.debug(f"[AutoReplyService] send_read_acknowledge notice: {exc}")

        return sent_msg
