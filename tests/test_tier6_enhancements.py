"""
Tier 6: New Enhancements Test Suite.

Tests:
1. Persian and Unicode normalization in SensitiveFilter (ZWNJ, Arabic kaf/yeh, harakat).
2. ChatDebouncer aggregation and timer reset for rapid consecutive messages.
3. Active Chat Cooldown (human presence detection) in AutoReplyService.
4. Pause and Resume control in AutoReplyService.
5. Saved Messages dynamic commands (/pause, /resume, /mode, /blacklist).
6. Quoted / reply-to message context enrichment.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

from client.telethon_client import UserbotClient
from config.settings import Settings
from filters.base import FilterContext
from filters.pipeline import build_default_pipeline
from filters.sensitive_filter import SensitiveFilter
from handlers.saved_messages_handler import register_saved_messages_handler
from llm.mock_provider import MockLLMProvider
from services.alert_service import AlertService
from services.auto_reply_service import AutoReplyService
from services.chat_debouncer import ChatDebouncer
from services.digest_service import DigestService
from services.humanizer import HumanizerService
from tests.conftest import MockMessage, MockTelethonClient


def asyncio_run(coro):
    return asyncio.run(coro)


# --- 1. Persian & Unicode Normalization Tests ---

def test_sensitive_filter_persian_zwnj_normalization() -> None:
    """Tests that ZWNJ between words is normalized and matched."""
    flt = SensitiveFilter(sensitive_keywords=["رمز عبور", "کد تایید"])

    # Message with ZWNJ (نیم‌فاصله: \u200c)
    text_with_zwnj = "لطفاً رمز\u200cعبور خود را ارسال فرمایید"
    res = asyncio_run(flt.check(FilterContext(sender_id=1, text=text_with_zwnj)))
    assert not res.allowed
    assert res.is_security_alert
    assert "رمز عبور" in res.matched_keyword


def test_sensitive_filter_arabic_kaf_yeh_normalization() -> None:
    """Tests that Arabic kaf (ك) and yeh (ي) are normalized to Persian equivalents."""
    flt = SensitiveFilter(sensitive_keywords=["کد تایید", "شماره حساب"])

    # Message using Arabic characters: ك instead of ک, and ي instead of ی
    text_arabic = "لطفاً كد تاييد خود را ارسال كنيد"
    res = asyncio_run(flt.check(FilterContext(sender_id=1, text=text_arabic)))
    assert not res.allowed
    assert res.is_security_alert
    assert "کد تایید" in res.matched_keyword


def test_sensitive_filter_harakat_diacritics_stripping() -> None:
    """Tests that Arabic/Persian diacritics (harakat/tanween) are stripped."""
    flt = SensitiveFilter(sensitive_keywords=["رمز عبور"])

    # "رَمْزِ عُبُورْ" with harakat
    text_harakat = "ارسال رَمْزِ عُبُورْ ضروری است"
    res = asyncio_run(flt.check(FilterContext(sender_id=1, text=text_harakat)))
    assert not res.allowed
    assert res.is_security_alert


# --- 2. ChatDebouncer Tests ---

async def test_chat_debouncer_aggregates_rapid_messages(fast_sleep) -> None:
    """Verifies that multiple messages sent within debounce window are merged into one."""
    dispatched_batches: list[tuple[FilterContext, int | None]] = []

    async def mock_dispatch(ctx: FilterContext, msg_id: int | None) -> None:
        dispatched_batches.append((ctx, msg_id))

    debouncer = ChatDebouncer(
        dispatch_callback=mock_dispatch,
        debounce_delay=0.1,
        sleep_func=fast_sleep,
    )

    ctx1 = FilterContext(sender_id=101, text="سلام", chat_id=101)
    ctx2 = FilterContext(sender_id=101, text="خوبی؟", chat_id=101)
    ctx3 = FilterContext(sender_id=101, text="یه سوال داشتم", chat_id=101)

    # Rapid consecutive enqueue
    await debouncer.enqueue(ctx1, message_id=1)
    await debouncer.enqueue(ctx2, message_id=2)
    await debouncer.enqueue(ctx3, message_id=3)

    # Let the debounce timer complete
    await asyncio.sleep(0.01)

    assert len(dispatched_batches) == 1
    combined_ctx, latest_msg_id = dispatched_batches[0]
    assert latest_msg_id == 3
    assert "سلام\nخوبی؟\nیه سوال داشتم" == combined_ctx.text


# --- 3. Active Chat Cooldown Tests ---

async def test_active_chat_cooldown_skips_when_human_active(
    mock_telethon_client: MockTelethonClient,
    mock_llm_provider: MockLLMProvider,
    fast_sleep,
) -> None:
    """If the bot owner recently sent an outgoing message in the chat, auto-reply is skipped."""
    userbot_client = UserbotClient(
        settings=Settings(telegram_api_id=123, telegram_api_hash="abc", llm_provider="mock"),
        raw_client=mock_telethon_client,
    )
    pipeline = build_default_pipeline(settings=userbot_client.settings)
    alert_service = AlertService(userbot_client=userbot_client)
    humanizer = HumanizerService(userbot_client=userbot_client, sleep_func=fast_sleep)

    auto_reply = AutoReplyService(
        userbot_client=userbot_client,
        llm_provider=mock_llm_provider,
        filter_pipeline=pipeline,
        alert_service=alert_service,
        humanizer_service=humanizer,
        active_cooldown_seconds=300,  # 5 minutes
    )

    chat_id = 555
    # Simulate chat history where userbot owner sent a message 30 seconds ago
    recent_date = datetime.now(timezone.utc) - timedelta(seconds=30)
    mock_telethon_client.chat_history[chat_id] = [
        MockMessage(id=1, sender_id=999, text="سلام وقت بخیر", chat_id=chat_id, out=False),
        MockMessage(id=2, sender_id=123, text="سلام، جانم بفرمایید", chat_id=chat_id, out=True, date=recent_date),
    ]

    incoming_ctx = FilterContext(sender_id=999, text="یه فایل براتون فرستادم", chat_id=chat_id)
    result = await auto_reply.handle_incoming_private_message(incoming_ctx, message_id=3)

    # Must skip auto-reply because human is actively chatting
    assert result is None


async def test_active_chat_cooldown_allows_when_inactive(
    mock_telethon_client: MockTelethonClient,
    mock_llm_provider: MockLLMProvider,
    fast_sleep,
) -> None:
    """If the bot owner's last message was long ago (> cooldown), auto-reply triggers normally."""
    userbot_client = UserbotClient(
        settings=Settings(telegram_api_id=123, telegram_api_hash="abc", llm_provider="mock"),
        raw_client=mock_telethon_client,
    )
    pipeline = build_default_pipeline(settings=userbot_client.settings)
    alert_service = AlertService(userbot_client=userbot_client)
    humanizer = HumanizerService(userbot_client=userbot_client, sleep_func=fast_sleep)

    auto_reply = AutoReplyService(
        userbot_client=userbot_client,
        llm_provider=mock_llm_provider,
        filter_pipeline=pipeline,
        alert_service=alert_service,
        humanizer_service=humanizer,
        active_cooldown_seconds=300,
    )

    chat_id = 777
    # Last message was sent 2 hours ago
    old_date = datetime.now(timezone.utc) - timedelta(hours=2)
    mock_telethon_client.chat_history[chat_id] = [
        MockMessage(id=1, sender_id=123, text="خداحافظ", chat_id=chat_id, out=True, date=old_date),
    ]

    incoming_ctx = FilterContext(sender_id=888, text="سلام هستید؟", chat_id=chat_id)
    result = await auto_reply.handle_incoming_private_message(incoming_ctx, message_id=2)

    # Should reply because cooldown expired
    assert result is not None
    assert "سلام هستید؟" in result.text


# --- 4. Pause & Resume Tests ---

async def test_auto_reply_pause_and_resume(
    mock_telethon_client: MockTelethonClient,
    mock_llm_provider: MockLLMProvider,
    fast_sleep,
) -> None:
    """Verifies that pause halts auto-replies and resume restores them."""
    userbot_client = UserbotClient(
        settings=Settings(telegram_api_id=123, telegram_api_hash="abc", llm_provider="mock"),
        raw_client=mock_telethon_client,
    )
    pipeline = build_default_pipeline(settings=userbot_client.settings)
    auto_reply = AutoReplyService(
        userbot_client=userbot_client,
        llm_provider=mock_llm_provider,
        filter_pipeline=pipeline,
        alert_service=AlertService(userbot_client=userbot_client),
        humanizer_service=HumanizerService(userbot_client=userbot_client, sleep_func=fast_sleep),
    )

    ctx = FilterContext(sender_id=111, text="سلام", chat_id=111)

    # 1. Normal state -> replies
    res1 = await auto_reply.handle_incoming_private_message(ctx)
    assert res1 is not None

    # 2. Pause -> skips
    auto_reply.pause()
    assert auto_reply.check_is_paused()
    res2 = await auto_reply.handle_incoming_private_message(ctx)
    assert res2 is None

    # 3. Resume -> replies again
    auto_reply.resume()
    assert not auto_reply.check_is_paused()
    res3 = await auto_reply.handle_incoming_private_message(ctx)
    assert res3 is not None


# --- 5. Saved Messages Commands Tests ---

async def test_saved_messages_pause_resume_mode_and_blacklist(
    mock_telethon_client: MockTelethonClient,
    mock_llm_provider: MockLLMProvider,
) -> None:
    """Tests /pause, /resume, /mode, and /blacklist commands in Saved Messages."""
    settings = Settings(telegram_api_id=123, telegram_api_hash="abc", llm_provider="mock")
    userbot_client = UserbotClient(settings=settings, raw_client=mock_telethon_client)
    pipeline = build_default_pipeline(settings=settings)
    digest_service = DigestService(userbot_client=userbot_client, llm_provider=mock_llm_provider)
    auto_reply = AutoReplyService(
        userbot_client=userbot_client,
        llm_provider=mock_llm_provider,
        filter_pipeline=pipeline,
        alert_service=AlertService(userbot_client=userbot_client),
        humanizer_service=HumanizerService(userbot_client=userbot_client),
    )

    register_saved_messages_handler(
        client=mock_telethon_client,
        digest_service=digest_service,
        settings=settings,
        auto_reply_service=auto_reply,
        filter_pipeline=pipeline,
    )

    # Find the handler callback from event_handlers
    handler_cb = mock_telethon_client.event_handlers[0][0]

    # Test /pause 15
    await handler_cb(MockMessage(id=1, sender_id=999999, text="/pause 15", chat_id=0))
    assert auto_reply.is_paused is True
    assert "متوقف شد" in mock_telethon_client.sent_messages[-1]["message"]

    # Test /resume
    await handler_cb(MockMessage(id=2, sender_id=999999, text="/resume", chat_id=0))
    assert auto_reply.is_paused is False
    assert "فعال شد" in mock_telethon_client.sent_messages[-1]["message"]

    # Test /blacklist add @spammer
    await handler_cb(MockMessage(id=3, sender_id=999999, text="/blacklist add @spammer", chat_id=0))
    assert "spammer" in settings.blacklist_users or "@spammer" in settings.blacklist_users
    assert "لیست سیاه اضافه شد" in mock_telethon_client.sent_messages[-1]["message"]

    # Test /blacklist remove @spammer
    await handler_cb(MockMessage(id=4, sender_id=999999, text="/blacklist remove @spammer", chat_id=0))
    assert "از لیست سیاه حذف شد" in mock_telethon_client.sent_messages[-1]["message"]

    # Test /mode mock
    await handler_cb(MockMessage(id=5, sender_id=999999, text="/mode mock", chat_id=0))
    assert "تغییر یافت" in mock_telethon_client.sent_messages[-1]["message"]


# --- 6. Quoted / Reply-To Message Context Test ---

async def test_quoted_message_context_in_prompt(
    mock_telethon_client: MockTelethonClient,
    mock_llm_provider: MockLLMProvider,
    fast_sleep,
) -> None:
    """Verifies that quoted text is prepended to the incoming message for LLM context."""
    userbot_client = UserbotClient(
        settings=Settings(telegram_api_id=123, telegram_api_hash="abc", llm_provider="mock"),
        raw_client=mock_telethon_client,
    )
    pipeline = build_default_pipeline(settings=userbot_client.settings)
    auto_reply = AutoReplyService(
        userbot_client=userbot_client,
        llm_provider=mock_llm_provider,
        filter_pipeline=pipeline,
        alert_service=AlertService(userbot_client=userbot_client),
        humanizer_service=HumanizerService(userbot_client=userbot_client, sleep_func=fast_sleep),
    )

    ctx = FilterContext(
        sender_id=1234,
        text="بله موافقم",
        chat_id=1234,
        quoted_text="آیا فردا جلسه برگزار می‌شود؟",
    )

    res = await auto_reply.handle_incoming_private_message(ctx)
    assert res is not None

    # Check that LLM request received the quoted message context
    last_req = mock_llm_provider.call_history[-1]
    last_msg = last_req.messages[-1].content
    assert "آیا فردا جلسه برگزار می‌شود؟" in last_msg
    assert "بله موافقم" in last_msg
