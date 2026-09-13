"""
Anti-Ban & Telegram Resilience Mechanisms.

Provides:
- with_floodwait: Async decorator handling FloodWaitError with dynamic backoff,
  jitter, and maximum wait cutoff.
- safe_delay: Async helper introducing non-deterministic jitter between API calls.
- calculate_typing_duration: Calculates realistic typing duration based on text length.
"""

from __future__ import annotations

import asyncio
import functools
import logging
import random
from typing import Any, Callable, Coroutine, Optional, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


def with_floodwait(
    max_retries: int = 3,
    max_wait_seconds: int = 300,
    jitter_range: tuple[float, float] = (0.5, 2.0),
    sleep_func: Optional[Callable[[float], Coroutine[Any, Any, None]]] = None,
) -> Callable[[Callable[..., Coroutine[Any, Any, T]]], Callable[..., Coroutine[Any, Any, T]]]:
    """
    Decorator that intercepts Telegram FloodWaitError and dynamically pauses
    execution before retrying the call.

    Args:
        max_retries: Maximum number of retry attempts before giving up.
        max_wait_seconds: Maximum flood duration in seconds we are willing to wait.
                          If Telegram demands longer, the error is re-raised.
        jitter_range: Tuple of (min_jitter, max_jitter) added to the sleep time.
        sleep_func: Optional coroutine for sleep (defaults to asyncio.sleep).
    """
    sleep = sleep_func or asyncio.sleep

    def decorator(
        func: Callable[..., Coroutine[Any, Any, T]]
    ) -> Callable[..., Coroutine[Any, Any, T]]:
        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> T:
            attempts = 0
            while True:
                try:
                    return await func(*args, **kwargs)
                except Exception as exc:
                    # Detect FloodWaitError either from Telethon or mock objects
                    # FloodWaitError classes conventionally have a `seconds` integer attribute
                    is_flood = hasattr(exc, "seconds") and (
                        "FloodWait" in type(exc).__name__
                        or "Flood" in type(exc).__name__
                    )
                    if not is_flood:
                        raise

                    wait_seconds = int(getattr(exc, "seconds", 0))
                    attempts += 1

                    if wait_seconds > max_wait_seconds:
                        logger.error(
                            f"[AntiBan] FloodWait requested {wait_seconds}s which exceeds "
                            f"the max threshold of {max_wait_seconds}s. Aborting retries."
                        )
                        raise

                    if attempts > max_retries:
                        logger.error(
                            f"[AntiBan] Exceeded maximum retry attempts ({max_retries}) "
                            f"for FloodWait ({wait_seconds}s). Re-raising."
                        )
                        raise

                    jitter = random.uniform(jitter_range[0], jitter_range[1])
                    total_sleep = max(0.1, wait_seconds + jitter)
                    logger.warning(
                        f"[AntiBan] FloodWait caught: waiting {total_sleep:.2f}s "
                        f"(requested {wait_seconds}s + jitter {jitter:.2f}s). "
                        f"Attempt {attempts}/{max_retries}."
                    )
                    await sleep(total_sleep)

        return wrapper

    return decorator


async def safe_delay(
    min_seconds: float = 1.0,
    max_seconds: float = 3.0,
    sleep_func: Optional[Callable[[float], Coroutine[Any, Any, None]]] = None,
) -> float:
    """
    Introduces a random delay to prevent repetitive machine-like timing patterns.
    Returns the actual elapsed delay.
    """
    sleep = sleep_func or asyncio.sleep
    if max_seconds < min_seconds:
        min_seconds, max_seconds = max_seconds, min_seconds
    delay = random.uniform(min_seconds, max_seconds)
    await sleep(delay)
    return delay


def calculate_typing_duration(
    text: str,
    chars_per_second: float = 25.0,
    min_seconds: float = 1.5,
    max_seconds: float = 12.0,
) -> float:
    """
    Estimates human typing duration based on character count.
    Adds slight random fluctuation (±15%).
    """
    length = len(text.strip())
    if length == 0:
        return min_seconds

    base_seconds = length / max(1.0, chars_per_second)
    # Add random variation
    fluctuation = random.uniform(0.85, 1.15)
    duration = base_seconds * fluctuation
    return round(min(max(duration, min_seconds), max_seconds), 2)


def calculate_reading_delay(
    incoming_text: str,
    words_per_minute: float = 200.0,
    min_seconds: float = 1.0,
    max_seconds: float = 8.0,
) -> float:
    """
    Simulates the time a human takes to read an incoming message before starting to type.
    """
    words = len(incoming_text.strip().split())
    if words == 0:
        return min_seconds

    seconds = (words / max(50.0, words_per_minute)) * 60.0
    fluctuation = random.uniform(0.8, 1.2)
    delay = seconds * fluctuation
    return round(min(max(delay, min_seconds), max_seconds), 2)
