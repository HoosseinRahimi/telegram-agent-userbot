"""
Human-like Behavior and Typing Simulation Service.

Simulates realistic human delays:
1. Reading delay: Time taken to read the incoming message before typing.
2. Typing action: Emitting Telegram 'typing' chat status.
3. Proportional typing duration: Delay corresponding to the length of the generated reply.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable, Coroutine
from typing import Any

from client.anti_ban import calculate_reading_delay, calculate_typing_duration
from client.telethon_client import UserbotClient

logger = logging.getLogger(__name__)


class HumanizerService:
    """
    Manages human-like timing patterns and typing indicators before sending messages.
    """

    def __init__(
        self,
        userbot_client: UserbotClient,
        sleep_func: Callable[[float], Coroutine[Any, Any, None]] | None = None,
        chars_per_second: float = 25.0,
    ) -> None:
        self.client = userbot_client
        self.sleep = sleep_func or asyncio.sleep
        self.chars_per_second = chars_per_second

    async def simulate_reading(self, incoming_text: str, max_delay: float = 4.0) -> float:
        """
        Calculates and awaits a reading delay based on incoming text length.
        """
        delay = calculate_reading_delay(incoming_text, max_seconds=max_delay)
        logger.debug(f"[Humanizer] Simulating reading delay: {delay:.2f}s")
        await self.sleep(delay)
        return delay

    async def simulate_typing_and_wait(
        self,
        entity: Any,
        reply_text: str,
        min_seconds: float = 1.0,
        max_seconds: float = 8.0,
    ) -> float:
        """
        Emits typing chat action on Telegram and waits for a proportional typing duration.
        """
        duration = calculate_typing_duration(
            reply_text,
            chars_per_second=self.chars_per_second,
            min_seconds=min_seconds,
            max_seconds=max_seconds,
        )
        logger.debug(f"[Humanizer] Simulating typing ({len(reply_text)} chars) for {duration:.2f}s")

        # Emit typing action if supported by the client
        try:
            raw_client = getattr(self.client, "client", None)
            if raw_client and hasattr(raw_client, "action"):
                # In Telethon: async with client.action(entity, 'typing'): await sleep(duration)
                try:
                    action_ctx = raw_client.action(entity, "typing")
                    if hasattr(action_ctx, "__aenter__"):
                        async with action_ctx:
                            await self.sleep(duration)
                            return duration
                except Exception as act_err:
                    logger.debug(f"[Humanizer] Action context error (fallback to sleep): {act_err}")
        except Exception as exc:
            logger.debug(f"[Humanizer] Error while initiating typing action: {exc}")

        # Fallback to direct sleep if action context is unavailable
        await self.sleep(duration)
        return duration
