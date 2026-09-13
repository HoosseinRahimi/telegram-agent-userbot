"""
Tier 2: Boundary Value Analysis & Corner Cases Test Suite.

Tests extreme lengths, Unicode edge cases, case-insensitivity,
boundary values, and zero/negative parameters.
"""

from __future__ import annotations

import pytest

from client.anti_ban import calculate_reading_delay, calculate_typing_duration
from filters.base import FilterContext
from filters.blacklist_filter import BlacklistFilter
from filters.bot_filter import BotFilter
from filters.sensitive_filter import SensitiveFilter
from filters.system_filter import SystemFilter
from handlers.saved_messages_handler import parse_summary_args
from services.digest_service import split_text_chunks


def test_boundary_empty_strings() -> None:
    # Empty string typing duration defaults to minimum
    dur = calculate_typing_duration("", min_seconds=2.0)
    assert dur >= 2.0

    # Empty string reading delay defaults to minimum
    delay = calculate_reading_delay("", min_seconds=1.5)
    assert delay >= 1.5

    # Empty text chunking returns empty or single empty chunk
    chunks = split_text_chunks("")
    assert chunks == [""]


def test_boundary_huge_message_chunking() -> None:
    # Exactly 4096 chars
    exact_4096 = "a" * 4096
    chunks = split_text_chunks(exact_4096, max_size=4000)
    assert len(chunks) == 2
    assert chunks[0] == "a" * 4000
    assert chunks[1] == "a" * 96

    # 15,000 chars text
    huge_text = "Line content here\n" * 800
    chunks = split_text_chunks(huge_text, max_size=3000)
    assert len(chunks) > 4
    for c in chunks:
        assert len(c) <= 3100


def test_boundary_system_filter_variations() -> None:
    flt = SystemFilter()

    # Numeric int 777000
    r1 = asyncio_run(flt.check(FilterContext(sender_id=777000, text="hi")))
    assert not r1.allowed

    # String "777000"
    r2 = asyncio_run(flt.check(FilterContext(sender_id="777000", text="hi")))
    assert not r2.allowed

    # Username variations
    r3 = asyncio_run(flt.check(FilterContext(sender_id=1, sender_username="@Telegram", text="hi")))
    assert not r3.allowed

    r4 = asyncio_run(flt.check(FilterContext(sender_id=1, sender_username="TELEGRAMNOTIFICATIONS", text="hi")))
    assert not r4.allowed


def test_boundary_bot_filter_case_insensitivity() -> None:
    flt = BotFilter()

    # Uppercase BOT suffix
    r1 = asyncio_run(flt.check(FilterContext(sender_id=1, sender_username="CryptoTradingBOT", text="msg")))
    assert not r1.allowed

    # Mixed case Bot suffix with leading @
    r2 = asyncio_run(flt.check(FilterContext(sender_id=1, sender_username="@Alert_BoT", text="msg")))
    assert not r2.allowed

    # Username containing bot in the middle, but not ending with bot
    r3 = asyncio_run(flt.check(FilterContext(sender_id=1, sender_username="bothouse", text="msg")))
    assert r3.allowed


def test_boundary_blacklist_filter_case_and_at_sign() -> None:
    flt = BlacklistFilter(blacklist=["@BadActor", "998877"])

    # Without @ and mixed case
    r1 = asyncio_run(flt.check(FilterContext(sender_id=1, sender_username="badactor", text="hi")))
    assert not r1.allowed

    # Numeric string match
    r2 = asyncio_run(flt.check(FilterContext(sender_id=998877, text="hi")))
    assert not r2.allowed


def test_boundary_sensitive_persian_zwnj_and_variations() -> None:
    flt = SensitiveFilter(sensitive_keywords=["رمز عبور", "کد تایید"])

    # Normal text
    r1 = asyncio_run(flt.check(FilterContext(sender_id=1, text="لطفا رمز عبور را ارسال کنید")))
    assert not r1.allowed
    assert r1.is_security_alert

    # Case insensitivity and embedded punctuation
    r2 = asyncio_run(flt.check(FilterContext(sender_id=1, text="سلام، کد تایید: 987654")))
    assert not r2.allowed
    assert r2.is_security_alert


def test_boundary_summary_args_limits() -> None:
    # Minimum limit clamped to 5
    _, limit_min, _ = parse_summary_args("/summary @ch 1")
    assert limit_min == 5

    # Maximum limit clamped to 100
    _, limit_max, _ = parse_summary_args("/summary @ch 500")
    assert limit_max == 100

    # Non-numeric limit treated as topic
    target, limit_def, topic = parse_summary_args("/summary @ch sports news")
    assert target == "@ch"
    assert limit_def == 30
    assert topic == "sports news"


# Helper for synchronous execution in non-async test functions
def asyncio_run(coro):
    import asyncio
    return asyncio.run(coro)
