"""
Tier 3: Pairwise Combinations & Cross-Feature Interactions Test Suite.

Tests interactions between filters, error resilience, and cascading service behaviors:
1. Blacklist vs Sensitive Keyword ordering.
2. Bot account vs Sensitive Keyword ordering.
3. FloodWait recovery during auto-reply sending.
4. LLM failure resilience in auto-reply service.
5. Partial channel failures during multi-channel digest.
"""

from __future__ import annotations

from client.telethon_client import UserbotClient
from filters.base import FilterContext
from filters.blacklist_filter import BlacklistFilter
from filters.bot_filter import BotFilter
from filters.pipeline import FilterPipeline
from filters.sensitive_filter import SensitiveFilter
from filters.system_filter import SystemFilter
from llm.base import LLMUnavailableError
from llm.mock_provider import MockLLMProvider
from services.alert_service import AlertService
from services.auto_reply_service import AutoReplyService
from services.digest_service import DigestService
from services.humanizer import HumanizerService
from tests.conftest import MockMessage, MockTelethonClient


async def test_combination_blacklist_before_sensitive_keyword(
    mock_telethon_client: MockTelethonClient,
    mock_llm_provider: MockLLMProvider,
    fast_sleep,
) -> None:
    """
    If a blacklisted user sends an OTP, BlacklistFilter must block them
    without triggering a false-alarm security alert to Saved Messages.
    """
    pipeline = FilterPipeline([
        BlacklistFilter(blacklist=[999]),
        SensitiveFilter(sensitive_keywords=["otp"]),
    ])

    client_wrapper = UserbotClient(settings=None, raw_client=mock_telethon_client)
    alert_svc = AlertService(userbot_client=client_wrapper)
    humanizer = HumanizerService(userbot_client=client_wrapper, sleep_func=fast_sleep)

    auto_reply = AutoReplyService(
        userbot_client=client_wrapper,
        llm_provider=mock_llm_provider,
        filter_pipeline=pipeline,
        alert_service=alert_svc,
        humanizer_service=humanizer,
    )

    ctx = FilterContext(sender_id=999, text="Here is your OTP code: 1234")
    res = await auto_reply.handle_incoming_private_message(ctx)

    # Must be None (no reply sent)
    assert res is None
    # No security alert sent to 'me' because Blacklist blocked it first!
    assert len(mock_telethon_client.sent_messages) == 0


async def test_combination_bot_before_sensitive_keyword(
    mock_telethon_client: MockTelethonClient,
    mock_llm_provider: MockLLMProvider,
    fast_sleep,
) -> None:
    """
    A bot sending OTP keywords must be blocked by BotFilter without triggering alert.
    """
    pipeline = FilterPipeline([
        BotFilter(),
        SensitiveFilter(sensitive_keywords=["password"]),
    ])

    client_wrapper = UserbotClient(settings=None, raw_client=mock_telethon_client)
    alert_svc = AlertService(userbot_client=client_wrapper)
    humanizer = HumanizerService(userbot_client=client_wrapper, sleep_func=fast_sleep)

    auto_reply = AutoReplyService(
        userbot_client=client_wrapper,
        llm_provider=mock_llm_provider,
        filter_pipeline=pipeline,
        alert_service=alert_svc,
        humanizer_service=humanizer,
    )

    ctx = FilterContext(sender_id=555, is_bot=True, text="Reset your password now")
    res = await auto_reply.handle_incoming_private_message(ctx)

    assert res is None
    assert len(mock_telethon_client.sent_messages) == 0


async def test_combination_floodwait_recovery_during_autoreply(
    mock_telethon_client: MockTelethonClient,
    mock_llm_provider: MockLLMProvider,
    fast_sleep,
) -> None:
    """
    When sending a reply triggers a transient FloodWaitError, the userbot
    must dynamically wait and retry, successfully delivering the message.
    """
    pipeline = FilterPipeline([SystemFilter()])
    client_wrapper = UserbotClient(settings=None, raw_client=mock_telethon_client)
    alert_svc = AlertService(userbot_client=client_wrapper)
    humanizer = HumanizerService(userbot_client=client_wrapper, sleep_func=fast_sleep)

    # Configure client to raise FloodWait once on send_message
    mock_telethon_client.floodwait_trigger = 1

    auto_reply = AutoReplyService(
        userbot_client=client_wrapper,
        llm_provider=mock_llm_provider,
        filter_pipeline=pipeline,
        alert_service=alert_svc,
        humanizer_service=humanizer,
    )

    ctx = FilterContext(sender_id=12345, text="سلام وقت بخیر")
    sent = await auto_reply.handle_incoming_private_message(ctx, message_id=42)

    assert sent is not None
    assert sent.text is not None
    assert len(mock_telethon_client.sent_messages) == 1
    assert mock_telethon_client.sent_messages[0]["reply_to"] == 42


async def test_combination_llm_outage_resilience(
    mock_telethon_client: MockTelethonClient,
    fast_sleep,
) -> None:
    """
    If the LLM endpoint fails or times out, the userbot logs the error,
    does not crash, and cleanly skips sending a malformed reply.
    """
    failing_llm = MockLLMProvider(fail_with=LLMUnavailableError("API Gateway Timeout"))
    pipeline = FilterPipeline([SystemFilter()])

    client_wrapper = UserbotClient(settings=None, raw_client=mock_telethon_client)
    alert_svc = AlertService(userbot_client=client_wrapper)
    humanizer = HumanizerService(userbot_client=client_wrapper, sleep_func=fast_sleep)

    auto_reply = AutoReplyService(
        userbot_client=client_wrapper,
        llm_provider=failing_llm,
        filter_pipeline=pipeline,
        alert_service=alert_svc,
        humanizer_service=humanizer,
    )

    ctx = FilterContext(sender_id=12345, text="سلام")
    res = await auto_reply.handle_incoming_private_message(ctx)

    assert res is None
    assert len(mock_telethon_client.sent_messages) == 0


async def test_combination_digest_partial_channel_resilience(
    mock_telethon_client: MockTelethonClient,
    mock_llm_provider: MockLLMProvider,
) -> None:
    """
    In a multi-channel digest, if one channel fails, the remaining channels
    are still summarized and delivered to Saved Messages.
    """
    # Setup channel history: channel_1 has messages, channel_2 is empty/failing
    mock_telethon_client.chat_history["channel_1"] = [
        MockMessage(id=1, sender_id=10, text="اخبار جدید روز: هوش مصنوعی تلگرام رونمایی شد", chat_id=1)
    ]
    mock_telethon_client.chat_history["channel_2"] = []

    client_wrapper = UserbotClient(settings=None, raw_client=mock_telethon_client)
    digest_svc = DigestService(userbot_client=client_wrapper, llm_provider=mock_llm_provider)

    sent = await digest_svc.generate_channels_digest(
        channels=["channel_1", "channel_2"],
        limit_per_channel=10,
        deliver_to="me",
    )

    assert len(sent) > 0
    delivered_text = sent[0].text
    assert "channel_1" in delivered_text
    assert "channel_2" in delivered_text
