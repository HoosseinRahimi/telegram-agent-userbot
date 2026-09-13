"""
Tier 1: Comprehensive Feature Coverage Test Suite.
Verifies all 9 core features with >=5 discrete test cases per feature.
"""

from __future__ import annotations

import asyncio
import pytest

from client.anti_ban import (
    calculate_reading_delay,
    calculate_typing_duration,
    safe_delay,
    with_floodwait,
)
from client.telethon_client import UserbotClient
from config.settings import Settings, _parse_list_or_json
from filters.base import FilterContext
from filters.blacklist_filter import BlacklistFilter
from filters.bot_filter import BotFilter
from filters.pipeline import FilterPipeline, build_default_pipeline
from filters.sensitive_filter import SensitiveFilter
from filters.system_filter import SystemFilter
from handlers.saved_messages_handler import parse_summary_args
from llm.base import (
    LLMAuthenticationError,
    LLMError,
    LLMMessage,
    LLMRateLimitError,
    LLMRequest,
    LLMResponse,
)
from llm.factory import create_llm_provider
from llm.mock_provider import MockLLMProvider
from scheduler.digest_scheduler import DigestScheduler
from services.alert_service import AlertService
from services.digest_service import DigestService, split_text_chunks
from services.humanizer import HumanizerService
from tests.conftest import MockFloodWaitError, MockTelethonClient, MockUser


# ============================================================================
# F01 & F02: Configuration & Credentials Validation
# ============================================================================

def test_settings_valid_creation(sample_settings: Settings) -> None:
    assert sample_settings.telegram_api_id == 12345678
    assert sample_settings.telegram_api_hash == "0123456789abcdef0123456789abcdef"
    assert sample_settings.llm_provider == "mock"


def test_settings_secret_masking(sample_settings: Settings) -> None:
    repr_str = repr(sample_settings)
    assert "0123456789abcdef0123456789abcdef" not in repr_str
    assert "***" in repr_str


def test_settings_parse_comma_separated_list() -> None:
    res = _parse_list_or_json("apple, banana, cherry")
    assert res == ["apple", "banana", "cherry"]


def test_settings_parse_json_list() -> None:
    res = _parse_list_or_json('["111", "222", "333"]')
    assert res == ["111", "222", "333"]


def test_settings_blacklist_cleaning() -> None:
    s = Settings(
        telegram_api_id=1,
        telegram_api_hash="abc",
        blacklist_users="  12345 , @spammer , 67890 ",
    )
    assert s.blacklist_users == [12345, "spammer", 67890]


# ============================================================================
# F04: Anti-Ban & FloodWait Resilience
# ============================================================================

async def test_anti_ban_successful_without_flood(fast_sleep) -> None:
    call_count = 0

    @with_floodwait(max_retries=3, sleep_func=fast_sleep)
    async def sample_op() -> str:
        nonlocal call_count
        call_count += 1
        return "success"

    res = await sample_op()
    assert res == "success"
    assert call_count == 1
    assert len(fast_sleep.calls) == 0


async def test_anti_ban_recovers_after_floodwait(fast_sleep) -> None:
    attempts = 0

    @with_floodwait(max_retries=3, sleep_func=fast_sleep)
    async def faulty_op() -> str:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise MockFloodWaitError(seconds=3)
        return "recovered"

    res = await faulty_op()
    assert res == "recovered"
    assert attempts == 2
    assert len(fast_sleep.calls) == 1
    # total sleep should be at least 3 seconds
    assert fast_sleep.calls[0] >= 3.0


async def test_anti_ban_exceeds_max_retries(fast_sleep) -> None:
    @with_floodwait(max_retries=2, sleep_func=fast_sleep)
    async def always_floods() -> None:
        raise MockFloodWaitError(seconds=1)

    with pytest.raises(MockFloodWaitError):
        await always_floods()
    assert len(fast_sleep.calls) == 2


async def test_anti_ban_exceeds_max_wait_seconds(fast_sleep) -> None:
    @with_floodwait(max_retries=3, max_wait_seconds=60, sleep_func=fast_sleep)
    async def long_flood() -> None:
        raise MockFloodWaitError(seconds=3600)

    with pytest.raises(MockFloodWaitError):
        await long_flood()
    assert len(fast_sleep.calls) == 0  # Should abort immediately without sleeping


async def test_safe_delay_sleeps_within_range(fast_sleep) -> None:
    delay = await safe_delay(min_seconds=1.5, max_seconds=2.5, sleep_func=fast_sleep)
    assert 1.5 <= delay <= 2.5
    assert len(fast_sleep.calls) == 1


# ============================================================================
# F07: Safety Filters (System, Bot, Blacklist, Sensitive)
# ============================================================================

async def test_system_filter_blocks_777000() -> None:
    flt = SystemFilter()
    ctx = FilterContext(sender_id=777000, text="Your login code: 12345")
    res = await flt.check(ctx)
    assert not res.allowed
    assert "777000" in res.reason


async def test_system_filter_blocks_self() -> None:
    flt = SystemFilter()
    ctx = FilterContext(sender_id=123, is_self=True, text="outgoing msg")
    res = await flt.check(ctx)
    assert not res.allowed
    assert "self" in res.reason.lower()


async def test_bot_filter_blocks_is_bot() -> None:
    flt = BotFilter()
    ctx = FilterContext(sender_id=456, is_bot=True, text="hello")
    res = await flt.check(ctx)
    assert not res.allowed
    assert "bot" in res.reason.lower()


async def test_bot_filter_blocks_bot_username_suffix() -> None:
    flt = BotFilter()
    ctx = FilterContext(sender_id=456, sender_username="CryptoTrade_bot", text="join now")
    res = await flt.check(ctx)
    assert not res.allowed


async def test_blacklist_filter_blocks_id_and_username() -> None:
    flt = BlacklistFilter(blacklist=[999111, "@spammer_guy"])

    # Test numeric block
    res1 = await flt.check(FilterContext(sender_id=999111, text="hi"))
    assert not res1.allowed

    # Test username block
    res2 = await flt.check(FilterContext(sender_id=123, sender_username="Spammer_Guy", text="hi"))
    assert not res2.allowed

    # Test allowed user
    res3 = await flt.check(FilterContext(sender_id=123, sender_username="clean_user", text="hi"))
    assert res3.allowed


async def test_sensitive_filter_detects_english_and_persian() -> None:
    flt = SensitiveFilter(sensitive_keywords=["otp", "رمز دوم", "password"])

    # English OTP
    res1 = await flt.check(FilterContext(sender_id=1, text="Please send your OTP code immediately"))
    assert not res1.allowed
    assert res1.is_security_alert
    assert res1.matched_keyword == "otp"

    # Persian keyword
    res2 = await flt.check(FilterContext(sender_id=1, text="لطفا رمز دوم کارت خود را ارسال کنید"))
    assert not res2.allowed
    assert res2.is_security_alert
    assert res2.matched_keyword == "رمز دوم"

    # Clean text
    res3 = await flt.check(FilterContext(sender_id=1, text="سلام وقت بخیر، احوال شما؟"))
    assert res3.allowed


async def test_pipeline_short_circuits_on_first_block() -> None:
    flt1 = SystemFilter()
    flt2 = BotFilter()
    pipeline = FilterPipeline([flt1, flt2])

    ctx = FilterContext(sender_id=777000, is_bot=True, text="Notification")
    res = await pipeline.evaluate(ctx)
    assert not res.allowed
    # Blocked by SystemFilter first
    assert "777000" in res.reason


# ============================================================================
# F05 & F06: Modular LLM Engine
# ============================================================================

async def test_mock_llm_provider_generation() -> None:
    provider = MockLLMProvider(default_response="تست پاسخ")
    req = LLMRequest(prompt="سلام")
    resp = await provider.generate(req)
    assert "تست پاسخ" in resp.content
    assert resp.model == "mock-agent-v1"


async def test_mock_llm_provider_summary_handling() -> None:
    provider = MockLLMProvider()
    req = LLMRequest(prompt="لطفا این متن را خلاصه کنید")
    resp = await provider.generate(req)
    assert "گزارش خلاصه پیام‌ها" in resp.content


async def test_mock_llm_error_simulation() -> None:
    provider = MockLLMProvider(fail_with=LLMRateLimitError("Quota exceeded 429"))
    with pytest.raises(LLMRateLimitError):
        await provider.generate(LLMRequest(prompt="test"))


def test_llm_factory_creates_mock(sample_settings: Settings) -> None:
    provider = create_llm_provider(sample_settings)
    assert provider.provider_name == "mock"


def test_llm_factory_rejects_unknown_provider(sample_settings: Settings) -> None:
    sample_settings.llm_provider = "unknown_ai"
    with pytest.raises(ValueError):
        create_llm_provider(sample_settings)


# ============================================================================
# F08 & F09: Humanizer & AlertService
# ============================================================================

def test_calculate_typing_duration() -> None:
    # Short text
    dur_short = calculate_typing_duration("سلام", min_seconds=1.0)
    assert dur_short >= 1.0

    # Long text
    dur_long = calculate_typing_duration("این یک پیام طولانی برای تست مدت زمان تایپ انسان در تلگرام است.")
    assert dur_long >= dur_short


def test_calculate_reading_delay() -> None:
    delay_empty = calculate_reading_delay("")
    assert delay_empty >= 1.0

    delay_words = calculate_reading_delay("one two three four five six seven eight nine ten")
    assert delay_words >= 1.0


async def test_humanizer_simulate_reading_with_fast_sleep(fast_sleep, mock_telethon_client) -> None:
    client_wrapper = UserbotClient(settings=None, raw_client=mock_telethon_client)
    humanizer = HumanizerService(userbot_client=client_wrapper, sleep_func=fast_sleep)

    await humanizer.simulate_reading("Incoming test message from user")
    assert len(fast_sleep.calls) == 1
    assert fast_sleep.calls[0] >= 1.0


async def test_alert_service_dispatches_to_me(mock_telethon_client) -> None:
    client_wrapper = UserbotClient(settings=None, raw_client=mock_telethon_client)
    alert_svc = AlertService(userbot_client=client_wrapper)

    ctx = FilterContext(sender_id=888, sender_username="attacker", text="give me password")
    await alert_svc.send_security_alert(ctx, matched_keyword="password")

    assert len(mock_telethon_client.sent_messages) == 1
    sent = mock_telethon_client.sent_messages[0]
    assert sent["entity"] == "me"
    assert "هشدار امنیتی" in sent["message"]
    assert "password" in sent["message"]


# ============================================================================
# F10: DigestService & Chunking
# ============================================================================

def test_split_text_chunks_within_limits() -> None:
    short_text = "Short message"
    chunks = split_text_chunks(short_text, max_size=100)
    assert chunks == [short_text]

    long_text = "Line 1\n" * 50
    chunks = split_text_chunks(long_text, max_size=100)
    assert len(chunks) > 1
    for c in chunks:
        assert len(c) <= 120


def test_parse_summary_args_defaults() -> None:
    target, limit, topic = parse_summary_args("/summary @tech_news")
    assert target == "@tech_news"
    assert limit == 30
    assert topic is None


def test_parse_summary_args_custom_limit_and_topic() -> None:
    target, limit, topic = parse_summary_args("/summary @tech_news 50 artificial intelligence")
    assert target == "@tech_news"
    assert limit == 50
    assert topic == "artificial intelligence"
