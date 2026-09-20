"""
Chat Debouncer & Message Aggregator Service.

Aggregates rapid consecutive incoming messages from the same user/chat within
a debounce time window (e.g. 2.5 seconds) to produce a single, cohesive LLM response
and prevent race conditions, multiple replies, and redundant API calls.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable, Coroutine
from typing import Any

from filters.base import FilterContext

logger = logging.getLogger(__name__)


class PendingChatBatch:
    """Holds accumulated messages and metadata for a single chat during debounce."""

    def __init__(self, initial_context: FilterContext, initial_message_id: int | None) -> None:
        self.contexts: list[FilterContext] = [initial_context]
        self.message_ids: list[int | None] = [initial_message_id]
        self.latest_context: FilterContext = initial_context
        self.latest_message_id: int | None = initial_message_id

    def add(self, context: FilterContext, message_id: int | None) -> None:
        self.contexts.append(context)
        self.message_ids.append(message_id)
        self.latest_context = context
        self.latest_message_id = message_id

    def get_aggregated_text(self) -> str:
        texts = [ctx.text for ctx in self.contexts if ctx.text and ctx.text.strip()]
        return "\n".join(texts)


class ChatDebouncer:
    """
    Debounces incoming messages on a per-chat basis with concurrency control:
    - Per-chat lock guarantees at most one dispatch runs per chat at any time.
    - Global semaphore limits concurrent LLM dispatches across all chats.
    - Cancelled tasks are cleanly awaited upon stop.
    """

    def __init__(
        self,
        dispatch_callback: Callable[[FilterContext, int | None], Coroutine[Any, Any, Any]],
        debounce_delay: float = 2.5,
        sleep_func: Callable[[float], Coroutine[Any, Any, None]] | None = None,
        max_concurrent_dispatches: int = 5,
    ) -> None:
        self.dispatch_callback = dispatch_callback
        self.debounce_delay = debounce_delay
        self.sleep = sleep_func or asyncio.sleep
        self.semaphore = asyncio.Semaphore(max_concurrent_dispatches)
        self._pending_batches: dict[int, PendingChatBatch] = {}
        self._tasks: dict[int, asyncio.Task[None]] = {}
        self._chat_locks: dict[int, asyncio.Lock] = {}
        self._lock = asyncio.Lock()

    def _get_chat_lock(self, chat_id: int) -> asyncio.Lock:
        """Returns or creates the per-chat synchronization lock."""
        if chat_id not in self._chat_locks:
            self._chat_locks[chat_id] = asyncio.Lock()
        return self._chat_locks[chat_id]

    async def enqueue(self, context: FilterContext, message_id: int | None) -> None:
        """
        Enqueues an incoming message context for debouncing.
        Resets the timer if an existing debounce window is active for this chat.
        """
        chat_id = context.chat_id or context.sender_id

        async with self._lock:
            # Cancel existing pending timer task for this chat if active
            if chat_id in self._tasks:
                existing_task = self._tasks[chat_id]
                if not existing_task.done():
                    existing_task.cancel()

            # Append to or create pending batch
            if chat_id in self._pending_batches:
                self._pending_batches[chat_id].add(context, message_id)
                logger.debug(
                    f"[ChatDebouncer] Appended message to existing batch for chat {chat_id} "
                    f"(total messages: {len(self._pending_batches[chat_id].contexts)})"
                )
            else:
                self._pending_batches[chat_id] = PendingChatBatch(context, message_id)
                logger.debug(f"[ChatDebouncer] Created new batch for chat {chat_id}")

            # Schedule new debounce timer
            self._tasks[chat_id] = asyncio.create_task(self._debounce_wait(chat_id))

    async def _debounce_wait(self, chat_id: int) -> None:
        """Waits for debounce_delay, then dispatches the aggregated batch with per-chat exclusivity."""
        try:
            await self.sleep(self.debounce_delay)
        except asyncio.CancelledError:
            # Timer was reset by another incoming message; exit quietly
            return

        chat_lock = self._get_chat_lock(chat_id)
        async with chat_lock:
            batch: PendingChatBatch | None = None
            async with self._lock:
                batch = self._pending_batches.pop(chat_id, None)
                self._tasks.pop(chat_id, None)

            if not batch:
                return

            aggregated_text = batch.get_aggregated_text()
            latest_ctx = batch.latest_context

            # Create combined FilterContext with all aggregated text
            combined_context = FilterContext(
                sender_id=latest_ctx.sender_id,
                sender_username=latest_ctx.sender_username,
                is_bot=latest_ctx.is_bot,
                is_self=latest_ctx.is_self,
                text=aggregated_text,
                chat_id=latest_ctx.chat_id,
                raw_event=latest_ctx.raw_event,
                quoted_text=latest_ctx.quoted_text,
            )

            logger.info(
                f"[ChatDebouncer] Debounce complete for chat {chat_id}. "
                f"Dispatching {len(batch.contexts)} aggregated message(s) ({len(aggregated_text)} chars)."
            )

            async with self.semaphore:
                try:
                    await self.dispatch_callback(combined_context, batch.latest_message_id)
                except Exception as exc:
                    logger.error(f"[ChatDebouncer] Error in dispatch callback for chat {chat_id}: {exc}")

    async def stop(self) -> None:
        """Cancels and cleanly awaits all active debounce tasks."""
        tasks_to_cancel: list[asyncio.Task[None]] = []
        async with self._lock:
            for task in self._tasks.values():
                if not task.done():
                    task.cancel()
                    tasks_to_cancel.append(task)
            self._tasks.clear()
            self._pending_batches.clear()

        if tasks_to_cancel:
            await asyncio.gather(*tasks_to_cancel, return_exceptions=True)
