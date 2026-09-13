"""
Auto-Reply Orchestration Service.

Coordinates the end-to-end DM auto-reply lifecycle:
1. Filters incoming message (System accounts, bots, blacklist, sensitive keywords).
2. Triggers security alerts on sensitive/confidential events and halts reply.
3. Retrieves conversational context history from recent messages.
4. Simulates realistic reading delay.
5. Queries the modular LLM engine with the configured persona.
6. Simulates typing action with proportional typing duration.
7. Dispatches the reply using safe MTProto call with anti-ban retries.
"""

from __future__ import annotations

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
    Loads persona system instructions from a external text file.
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
    Manages automated, safe, human-like responses for private chats.
    """

    def __init__(
        self,
        userbot_client: UserbotClient,
        llm_provider: BaseLLMProvider,
        filter_pipeline: FilterPipeline,
        alert_service: AlertService,
        humanizer_service: HumanizerService,
        persona_prompt_path: str = "persona_prompt.txt",
    ) -> None:
        self.client = userbot_client
        self.llm = llm_provider
        self.pipeline = filter_pipeline
        self.alert_service = alert_service
        self.humanizer = humanizer_service
        self.persona_prompt = load_persona_prompt(persona_prompt_path)

    async def handle_incoming_private_message(
        self,
        context: FilterContext,
        message_id: Optional[int] = None,
    ) -> Optional[Any]:
        """
        Processes an incoming private message event through safety checks,
        LLM generation, and humanized dispatch.
        """
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

        # 4. Simulate human reading time based on incoming text
        await self.humanizer.simulate_reading(context.text)

        # 5. Fetch recent chat history for context (up to 5 recent messages)
        recent_history: List[LLMMessage] = []
        try:
            raw_msgs = await self.client.iter_messages_safe(chat_id, limit=5)
            # Reorder chronologically
            for msg in reversed(raw_msgs):
                text = getattr(msg, "text", "") or getattr(msg, "message", "") or ""
                if not text.strip():
                    continue
                is_out = getattr(msg, "out", False)
                role = "assistant" if is_out else "user"
                recent_history.append(LLMMessage(role=role, content=text.strip()))
        except Exception as exc:
            logger.debug(f"[AutoReplyService] Could not fetch chat history: {exc}")

        # Ensure current incoming message is present in the messages list
        if not recent_history or recent_history[-1].content != context.text:
            recent_history.append(LLMMessage(role="user", content=context.text))

        # 6. Generate response via LLM
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

        # 7. Simulate typing action and proportional typing duration
        await self.humanizer.simulate_typing_and_wait(
            entity=chat_id,
            reply_text=reply_text,
        )

        # 8. Dispatch reply to user
        logger.info(f"[AutoReplyService] Sending humanized reply to {chat_id} ({len(reply_text)} chars)")
        sent_msg = await self.client.send_message_safe(
            entity=chat_id,
            message=reply_text,
            reply_to=message_id,
        )

        # 9. Mark messages as read
        try:
            await self.client.send_read_acknowledge_safe(chat_id, max_id=message_id)
        except Exception as exc:
            logger.debug(f"[AutoReplyService] send_read_acknowledge notice: {exc}")

        return sent_msg
