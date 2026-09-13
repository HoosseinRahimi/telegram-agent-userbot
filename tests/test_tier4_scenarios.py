"""
Tier 4: Real-World End-to-End User Scenarios Test Suite.

Simulates complete user journeys:
1. Scenario 1: Legitimate contact sends DM -> Humanized AI auto-reply.
2. Scenario 2: Suspicious user requests OTP -> Auto-reply halts + Security alert to 'me'.
3. Scenario 3: User commands /summary @channel in Saved Messages -> Digest delivered.
4. Scenario 4: Background DigestScheduler periodically delivers automated bulletin.
"""

from __future__ import annotations

import asyncio
import pytest

from client.telethon_client import UserbotClient
from config.settings import Settings
from filters.base import FilterContext
from filters.pipeline import build_default_pipeline
from handlers.saved_messages_handler import register_saved_messages_handler
from llm.mock_provider import MockLLMProvider
from scheduler.digest_scheduler import DigestScheduler
from services.alert_service import AlertService
from services.auto_reply_service import AutoReplyService
from services.digest_service import DigestService
from services.humanizer import HumanizerService
from tests.conftest import MockMessage, MockTelethonClient


async def test_scenario1_legitimate_dm_auto_reply(
    mock_telethon_client: MockTelethonClient,
    sample_settings: Settings,
    fast_sleep,
) -> None:
    """
    Scenario 1: Legitimate user sends a greeting in private chat.
    The userbot reads, types with human delay, and sends an intelligent reply.
    """
    client_wrapper = UserbotClient(settings=sample_settings, raw_client=mock_telethon_client)
    llm = MockLLMProvider(default_response="سلام دوست عزیز! در خدمت شما هستم.")
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

    ctx = FilterContext(
        sender_id=778899,
        sender_username="friend_user",
        is_bot=False,
        is_self=False,
        text="سلام حسین جان، وقت داری صحبت کنیم؟",
        chat_id=778899,
    )

    sent = await auto_reply.handle_incoming_private_message(ctx, message_id=101)

    assert sent is not None
    assert "سلام دوست عزیز" in sent.text
    # Verify reading and typing delays were simulated
    assert len(fast_sleep.calls) >= 2
    # Verify read acknowledgment was triggered
    assert len(mock_telethon_client.read_acknowledges) == 1
    assert mock_telethon_client.read_acknowledges[0]["entity"] == 778899


async def test_scenario2_security_phishing_attack_halt_and_alert(
    mock_telethon_client: MockTelethonClient,
    sample_settings: Settings,
    fast_sleep,
) -> None:
    """
    Scenario 2: Malicious user requests an OTP or password.
    Auto-reply immediately halts, and a security alert is dispatched to Saved Messages.
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

    ctx = FilterContext(
        sender_id=666777,
        sender_username="phishing_attacker",
        is_bot=False,
        is_self=False,
        text="سلام، لطفاً سریعاً کد تایید تلگرام یا رمز عبور اکانتت را بفرست!",
        chat_id=666777,
    )

    sent = await auto_reply.handle_incoming_private_message(ctx, message_id=202)

    # Auto-reply must NOT be sent to the attacker!
    assert sent is None

    # Alert must be sent to 'me'
    assert len(mock_telethon_client.sent_messages) == 1
    alert_msg = mock_telethon_client.sent_messages[0]
    assert alert_msg["entity"] == "me"
    assert "هشدار امنیتی" in alert_msg["message"]
    assert "666777" in alert_msg["message"]
    assert "phishing_attacker" in alert_msg["message"]


async def test_scenario3_saved_messages_on_demand_summary(
    mock_telethon_client: MockTelethonClient,
    sample_settings: Settings,
) -> None:
    """
    Scenario 3: User commands /summary @tech_channel in Saved Messages.
    The userbot scans the channel, generates an analytical summary, and replies in 'me'.
    """
    # Seed channel history with posts
    mock_telethon_client.chat_history["@tech_channel"] = [
        MockMessage(id=1, sender_id=1, text="نسخه جدید پایتون با سرعت بالاتر منتشر شد.", chat_id=1),
        MockMessage(id=2, sender_id=1, text="هوش مصنوعی گوگل از مدل‌های جدید رونمایی کرد.", chat_id=1),
    ]

    client_wrapper = UserbotClient(settings=sample_settings, raw_client=mock_telethon_client)
    llm = MockLLMProvider()
    digest_svc = DigestService(userbot_client=client_wrapper, llm_provider=llm)

    register_saved_messages_handler(
        client=mock_telethon_client,
        digest_service=digest_svc,
        settings=sample_settings,
    )

    # Find the registered handler
    handler_fn, _ = mock_telethon_client.event_handlers[0]

    # Simulate sending /summary command in Saved Messages
    cmd_event = MockMessage(id=301, sender_id=999999, text="/summary @tech_channel 20", chat_id=999999)
    await handler_fn(cmd_event)

    # Check sent messages in 'me'
    assert len(mock_telethon_client.sent_messages) >= 2
    # First message is "⏳ در حال اسکن..."
    assert "در حال اسکن" in mock_telethon_client.sent_messages[0]["message"]
    # Final message is the delivered summary report
    summary_report = mock_telethon_client.sent_messages[1]["message"]
    assert "خلاصه تحلیلی اختصاصی" in summary_report


async def test_scenario4_background_periodic_digest_scheduler(
    mock_telethon_client: MockTelethonClient,
    sample_settings: Settings,
) -> None:
    """
    Scenario 4: Periodic DigestScheduler executes in the background and delivers reports.
    """
    mock_telethon_client.chat_history["test_channel"] = [
        MockMessage(id=1, sender_id=1, text="پست آزمایشی کانال خبر", chat_id=1)
    ]
    sample_settings.digest_channels = ["test_channel"]
    sample_settings.digest_interval_minutes = 1  # 1 min for fast testing

    client_wrapper = UserbotClient(settings=sample_settings, raw_client=mock_telethon_client)
    llm = MockLLMProvider()
    digest_svc = DigestService(userbot_client=client_wrapper, llm_provider=llm)

    # Use a custom sleep function that triggers once then stops the scheduler
    loop_count = 0

    async def custom_scheduler_sleep(seconds: float) -> None:
        nonlocal loop_count
        loop_count += 1
        if loop_count > 1:
            await scheduler.stop()

    scheduler = DigestScheduler(
        digest_service=digest_svc,
        settings=sample_settings,
        sleep_func=custom_scheduler_sleep,
    )

    scheduler.start()
    assert scheduler.is_running
    # Give the async loop a cycle to run
    await asyncio.sleep(0.05)
    await scheduler.stop()
    assert not scheduler.is_running
