"""
Tests for Phase 1 (P0) Fixes:
1. .env CSV parsing without SettingsError (P0-1).
2. Active Cooldown distinguishing bot replies from human manual presence (P0-2).
3. Safe defaults: auto_reply_enabled=False, allowlist filtering, dry-run mode, and privacy history toggle (P0-3).
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from client.telethon_client import UserbotClient
from config.settings import Settings
from filters.base import FilterContext
from filters.pipeline import build_default_pipeline
from llm.mock_provider import MockLLMProvider
from services.alert_service import AlertService
from services.auto_reply_service import AutoReplyService
from services.humanizer import HumanizerService
from tests.conftest import MockMessage, MockTelethonClient

# ============================================================================
# P0-1: .env and os.environ CSV Parsing Tests
# ============================================================================

def test_settings_load_from_environ_csv():
    """Verifies that comma-separated lists in environment variables load without SettingsError."""
    env_overrides = {
        "TELEGRAM_API_ID": "98765432",
        "TELEGRAM_API_HASH": "abcdef0123456789abcdef0123456789",
        "BLACKLIST_USERS": "11111111,22222222,spammer_user",
        "SENSITIVE_KEYWORDS": "otp,code,password,رمز عبور",
        "DIGEST_CHANNELS": "tech_news,ai_announcements,-100123456",
        "AUTO_REPLY_ENABLED": "false",
        "ALLOWLIST_USERS": "99999999,trusted_friend",
        "DRY_RUN": "true",
        "SEND_HISTORY_TO_PROVIDER": "false",
    }
    with patch.dict(os.environ, env_overrides, clear=False):
        settings = Settings()
        assert settings.telegram_api_id == 98765432
        assert settings.telegram_api_hash == "abcdef0123456789abcdef0123456789"
        assert settings.blacklist_users == [11111111, 22222222, "spammer_user"]
        assert "otp" in settings.sensitive_keywords
        assert "رمز عبور" in settings.sensitive_keywords
        assert settings.digest_channels == ["tech_news", "ai_announcements", -100123456]
        assert settings.auto_reply_enabled is False
        assert settings.allowlist_users == [99999999, "trusted_friend"]
        assert settings.dry_run is True
        assert settings.send_history_to_provider is False


def test_env_example_loads_without_settings_error(tmp_path: Path):
    """
    Verifies that copying .env.example directly (with dummy valid credentials)
    loads cleanly without SettingsError and parses all list fields correctly.
    """
    env_example_path = Path(".env.example")
    assert env_example_path.exists()
    content = env_example_path.read_text(encoding="utf-8")

    test_env_file = tmp_path / ".env"
    test_env_file.write_text(content, encoding="utf-8")

    # Load settings with env_file pointing to test_env_file
    with patch.dict(os.environ, {}, clear=True):
        settings = Settings(_env_file=test_env_file)
        assert settings.telegram_api_id == 12345678
        assert settings.blacklist_users == [11111111, 22222222, "spammer_user"]
        assert "otp" in settings.sensitive_keywords
        assert "کد تایید" in settings.sensitive_keywords
        assert settings.digest_channels == ["tech_news_channel", "ai_announcements"]
        assert settings.auto_reply_enabled is False


# ============================================================================
# P0-2: Active Cooldown & Bot vs. Human Outgoing Message Tests
# ============================================================================

async def test_active_cooldown_distinguishes_bot_replies_from_human_presence(
    mock_telethon_client: MockTelethonClient,
    sample_settings: Settings,
    fast_sleep,
):
    """
    Verifies that consecutive messages after a bot reply BOTH receive replies,
    but a genuine human manual message stops auto-replies for the cooldown period.
    """
    client_wrapper = UserbotClient(settings=sample_settings, raw_client=mock_telethon_client)
    llm = MockLLMProvider()
    pipeline = build_default_pipeline(settings=sample_settings)
    alert_service = AlertService(userbot_client=client_wrapper)
    humanizer = HumanizerService(userbot_client=client_wrapper, sleep_func=fast_sleep)

    auto_reply = AutoReplyService(
        userbot_client=client_wrapper,
        llm_provider=llm,
        filter_pipeline=pipeline,
        alert_service=alert_service,
        humanizer_service=humanizer,
        active_cooldown_seconds=300,
        auto_reply_enabled=True,
    )

    chat_id = 55555

    # 1. User sends message 1
    ctx1 = FilterContext(sender_id=chat_id, text="سلام وقت بخیر", chat_id=chat_id)
    sent1 = await auto_reply.handle_incoming_private_message(ctx1, message_id=101)
    assert sent1 is not None
    assert len(mock_telethon_client.sent_messages) == 1
    bot_reply_id = sent1.id

    # 2. Simulate history having the bot's reply (out=True, message ID is bot_reply_id)
    mock_telethon_client.chat_history[chat_id] = [
        MockMessage(id=101, sender_id=chat_id, text="سلام وقت بخیر", chat_id=chat_id, out=False),
        MockMessage(id=bot_reply_id, sender_id=0, text="پاسخ تستی", chat_id=chat_id, out=True),
    ]

    # User sends follow-up message 2 immediately
    ctx2 = FilterContext(sender_id=chat_id, text="می‌خواستم درباره پروژه بپرسم", chat_id=chat_id)
    sent2 = await auto_reply.handle_incoming_private_message(ctx2, message_id=102)
    assert sent2 is not None, "Bot reply in history must NOT trigger human presence cooldown!"
    assert len(mock_telethon_client.sent_messages) == 2

    # 3. Now simulate account owner sending a genuine manual message (out=True, unknown message ID)
    manual_msg_id = 9999
    mock_telethon_client.chat_history[chat_id].append(
        MockMessage(
            id=manual_msg_id,
            sender_id=0,
            text="سلام خودم هستم الآن جواب می‌دم",
            chat_id=chat_id,
            out=True,
            date=datetime.now(timezone.utc),
        )
    )

    # User sends message 3
    ctx3 = FilterContext(sender_id=chat_id, text="عالیه منتظرم", chat_id=chat_id)
    sent3 = await auto_reply.handle_incoming_private_message(ctx3, message_id=103)
    assert sent3 is None, "Genuine human manual message MUST trigger active cooldown and halt auto-reply!"
    assert len(mock_telethon_client.sent_messages) == 2  # No new message sent by bot


# ============================================================================
# P0-3: Safe Defaults, Allowlist & Dry-Run Tests
# ============================================================================

async def test_auto_reply_default_disabled_and_resume(
    mock_telethon_client: MockTelethonClient,
    sample_settings: Settings,
    fast_sleep,
):
    """Verifies that when auto_reply_enabled=False, incoming messages are skipped until resumed."""
    client_wrapper = UserbotClient(settings=sample_settings, raw_client=mock_telethon_client)
    llm = MockLLMProvider()
    pipeline = build_default_pipeline(settings=sample_settings)
    alert = AlertService(client_wrapper)
    humanizer = HumanizerService(client_wrapper, sleep_func=fast_sleep)

    # Service with auto_reply_enabled=False (safe default)
    auto_reply = AutoReplyService(
        userbot_client=client_wrapper,
        llm_provider=llm,
        filter_pipeline=pipeline,
        alert_service=alert,
        humanizer_service=humanizer,
        auto_reply_enabled=False,
    )

    ctx = FilterContext(sender_id=1234, text="سلام", chat_id=1234)
    res = await auto_reply.handle_incoming_private_message(ctx)
    assert res is None, "Should skip when auto_reply_enabled=False"
    assert len(mock_telethon_client.sent_messages) == 0

    # Resume explicitly
    auto_reply.resume()
    res2 = await auto_reply.handle_incoming_private_message(ctx)
    assert res2 is not None, "Should reply after explicit resume"
    assert len(mock_telethon_client.sent_messages) == 1


async def test_allowlist_filtering(
    mock_telethon_client: MockTelethonClient,
    sample_settings: Settings,
    fast_sleep,
):
    """Verifies that when allowlist is set, only allowed users receive replies."""
    client_wrapper = UserbotClient(settings=sample_settings, raw_client=mock_telethon_client)
    llm = MockLLMProvider()
    pipeline = build_default_pipeline(settings=sample_settings)
    alert = AlertService(client_wrapper)
    humanizer = HumanizerService(client_wrapper, sleep_func=fast_sleep)

    auto_reply = AutoReplyService(
        userbot_client=client_wrapper,
        llm_provider=llm,
        filter_pipeline=pipeline,
        alert_service=alert,
        humanizer_service=humanizer,
        auto_reply_enabled=True,
        allowlist_users=[111111, "trusted_user"],
    )

    # Non-allowed user
    ctx_blocked = FilterContext(sender_id=999999, sender_username="stranger", text="سلام", chat_id=999999)
    res_blocked = await auto_reply.handle_incoming_private_message(ctx_blocked)
    assert res_blocked is None
    assert len(mock_telethon_client.sent_messages) == 0

    # Allowed user by ID
    ctx_allowed_id = FilterContext(sender_id=111111, text="سلام من مجازم", chat_id=111111)
    res_allowed_id = await auto_reply.handle_incoming_private_message(ctx_allowed_id)
    assert res_allowed_id is not None
    assert len(mock_telethon_client.sent_messages) == 1

    # Allowed user by username
    ctx_allowed_user = FilterContext(sender_id=222222, sender_username="@trusted_user", text="سلام", chat_id=222222)
    res_allowed_user = await auto_reply.handle_incoming_private_message(ctx_allowed_user)
    assert res_allowed_user is not None
    assert len(mock_telethon_client.sent_messages) == 2


async def test_dry_run_mode(
    mock_telethon_client: MockTelethonClient,
    sample_settings: Settings,
    fast_sleep,
):
    """Verifies that in dry_run mode, reply is generated but not sent to Telegram."""
    client_wrapper = UserbotClient(settings=sample_settings, raw_client=mock_telethon_client)
    llm = MockLLMProvider()
    pipeline = build_default_pipeline(settings=sample_settings)
    alert = AlertService(client_wrapper)
    humanizer = HumanizerService(client_wrapper, sleep_func=fast_sleep)

    auto_reply = AutoReplyService(
        userbot_client=client_wrapper,
        llm_provider=llm,
        filter_pipeline=pipeline,
        alert_service=alert,
        humanizer_service=humanizer,
        auto_reply_enabled=True,
        dry_run=True,
    )

    ctx = FilterContext(sender_id=1234, text="تست حالت شبیه‌سازی", chat_id=1234)
    res = await auto_reply.handle_incoming_private_message(ctx)
    assert res is not None  # Returns raw event or indication of success
    assert len(mock_telethon_client.sent_messages) == 0, "Dry run must NOT send messages to Telegram client!"


async def test_send_history_to_provider_toggle(
    mock_telethon_client: MockTelethonClient,
    sample_settings: Settings,
    fast_sleep,
):
    """Verifies that send_history_to_provider=False does not send prior chat history to LLM."""
    client_wrapper = UserbotClient(settings=sample_settings, raw_client=mock_telethon_client)
    llm = MockLLMProvider()
    pipeline = build_default_pipeline(settings=sample_settings)
    alert = AlertService(client_wrapper)
    humanizer = HumanizerService(client_wrapper, sleep_func=fast_sleep)

    auto_reply = AutoReplyService(
        userbot_client=client_wrapper,
        llm_provider=llm,
        filter_pipeline=pipeline,
        alert_service=alert,
        humanizer_service=humanizer,
        auto_reply_enabled=True,
        send_history_to_provider=False,
    )

    chat_id = 7777
    mock_telethon_client.chat_history[chat_id] = [
        MockMessage(id=1, sender_id=chat_id, text="پیام قدیمی ۱", chat_id=chat_id),
        MockMessage(id=2, sender_id=chat_id, text="پیام قدیمی ۲", chat_id=chat_id),
    ]

    ctx = FilterContext(sender_id=chat_id, text="پیام جاری", chat_id=chat_id)
    with patch.object(llm, "generate", wraps=llm.generate) as mock_gen:
        await auto_reply.handle_incoming_private_message(ctx)
        call_req = mock_gen.call_args[0][0]
        # Only system prompt and current message should be present
        contents = [m.content for m in call_req.messages]
        assert "پیام جاری" in contents[-1]
        assert not any("پیام قدیمی" in c for c in contents)
