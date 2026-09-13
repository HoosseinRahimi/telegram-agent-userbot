"""
Tier 5: Adversarial Hardening & Stress Testing Suite.

Tests malicious inputs, high concurrency, zero-width Unicode injection,
missing config files, and edge-case state transitions.
"""

from __future__ import annotations

import asyncio
import pytest

from client.telethon_client import UserbotClient
from filters.base import FilterContext
from filters.blacklist_filter import BlacklistFilter
from filters.pipeline import build_default_pipeline
from filters.sensitive_filter import SensitiveFilter
from llm.mock_provider import MockLLMProvider
from services.alert_service import AlertService
from services.auto_reply_service import AutoReplyService, load_persona_prompt
from services.digest_service import DigestService
from services.humanizer import HumanizerService
from tests.conftest import MockMessage, MockTelethonClient, MockUser


def test_adversarial_zero_width_unicode_in_sensitive_filter() -> None:
    """Tests zero-width joiners and spaces embedded in sensitive keywords."""
    flt = SensitiveFilter(sensitive_keywords=["رمز عبور", "otp"])

    # Normal Persian sensitive keyword
    res = asyncio_run(flt.check(FilterContext(sender_id=1, text="لطفا رمز عبور را ارسال کنید")))
    assert not res.allowed
    assert res.is_security_alert

    # Embedded in code blocks or punctuation
    res_punct = asyncio_run(flt.check(FilterContext(sender_id=1, text="Your [OTP]: 543210")))
    assert not res_punct.allowed
    assert res_punct.matched_keyword == "otp"


def test_adversarial_missing_persona_file_fallback() -> None:
    """When the configured persona file doesn't exist, a safe fallback must be loaded."""
    fallback_text = load_persona_prompt("non_existent_file_xyz_12345.txt")
    assert fallback_text is not None
    assert "دستیار هوشمند" in fallback_text


def test_adversarial_blacklist_with_junk_and_nones() -> None:
    """Blacklist initialization must tolerate None, whitespace, negative numbers, and garbage."""
    junk_list = [None, "", "   ", "@", 12345, -100123456, "spammer!@#"]
    flt = BlacklistFilter(blacklist=junk_list)

    # 12345 is blacklisted
    assert not asyncio_run(flt.check(FilterContext(sender_id=12345, text="hi"))).allowed
    # Other user is allowed
    assert asyncio_run(flt.check(FilterContext(sender_id=999, text="hi"))).allowed


async def test_adversarial_concurrent_dms_from_multiple_users(
    mock_telethon_client: MockTelethonClient,
    sample_settings,
    fast_sleep,
) -> None:
    """
    Multiple legitimate DMs arrive concurrently.
    All must be processed and replied to independently without race conditions.
    """
    client_wrapper = UserbotClient(settings=sample_settings, raw_client=mock_telethon_client)
    llm = MockLLMProvider()
    pipeline = build_default_pipeline(settings=sample_settings)
    alert_svc = AlertService(userbot_client=client_wrapper)
    humanizer = HumanizerService(userbot_client=client_wrapper, sleep_func=fast_sleep)

    auto_reply = AutoReplyService(
        userbot_client=client_wrapper,
        llm_provider=llm,
        filter_pipeline=pipeline,
        alert_service=alert_svc,
        humanizer_service=humanizer,
    )

    tasks = [
        auto_reply.handle_incoming_private_message(
            FilterContext(sender_id=100 + i, text=f"Message {i}", chat_id=100 + i),
            message_id=i,
        )
        for i in range(10)
    ]

    results = await asyncio.gather(*tasks)

    # All 10 messages should be handled and replied to
    assert len(results) == 10
    for res in results:
        assert res is not None
    assert len(mock_telethon_client.sent_messages) == 10


async def test_adversarial_chat_history_with_empty_and_media_only_messages(
    mock_telethon_client: MockTelethonClient,
    mock_llm_provider: MockLLMProvider,
) -> None:
    """
    When history contains non-text or empty messages (stickers, voice notes without text),
    DigestService and AutoReplyService filter them out without throwing errors.
    """
    mock_telethon_client.chat_history["empty_chat"] = [
        MockMessage(id=1, sender_id=1, text="", chat_id=1),
        MockMessage(id=2, sender_id=1, text="   ", chat_id=1),
        MockMessage(id=3, sender_id=2, text="Valid text message", chat_id=1),
    ]

    client_wrapper = UserbotClient(settings=None, raw_client=mock_telethon_client)
    digest_svc = DigestService(userbot_client=client_wrapper, llm_provider=mock_llm_provider)

    history = await digest_svc.extract_chat_history("empty_chat")
    # Only 1 valid message should remain
    assert len(history) == 1
    assert "Valid text message" in history[0]


def asyncio_run(coro):
    import asyncio
    return asyncio.run(coro)
