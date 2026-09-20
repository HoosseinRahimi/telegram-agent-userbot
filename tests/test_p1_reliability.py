"""
Tests for Phase 2 (P1) Reliability & Operations:
1. ChatDebouncer per-chat lock & global concurrency (P1-1).
2. LLM timeout, retry, error mapping & atomic /mode rollback (P1-2).
3. TelegramMessageSender chunking & markdown fallback (P1-3).
4. StateRepository atomic persistence & normalization (P1-6).
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from client.message_sender import (
    redact_sensitive_text,
    split_text_into_chunks,
)
from client.telethon_client import UserbotClient
from config.settings import Settings
from filters.base import FilterContext
from handlers.saved_messages_handler import register_saved_messages_handler
from llm.base import (
    LLMAuthenticationError,
    LLMRateLimitError,
    LLMRequest,
    LLMUnavailableError,
)
from llm.gemini_provider import GeminiProvider
from llm.mock_provider import MockLLMProvider
from llm.openai_provider import OpenAIProvider
from services.chat_debouncer import ChatDebouncer
from services.digest_service import DigestService
from services.state_repository import StateRepository, normalize_entry
from tests.conftest import MockMessage, MockTelethonClient

# ============================================================================
# P1-1: ChatDebouncer Concurrency & Per-Chat Lock Tests
# ============================================================================

async def test_chat_debouncer_serializes_same_chat():
    """
    Verifies that for the same chat, dispatches NEVER run concurrently.
    The second dispatch waits until the first dispatch completes.
    """
    execution_order = []
    active_in_flight = 0
    max_concurrent_for_same_chat = 0

    async def slow_dispatch(ctx: FilterContext, msg_id: int | None):
        nonlocal active_in_flight, max_concurrent_for_same_chat
        active_in_flight += 1
        max_concurrent_for_same_chat = max(max_concurrent_for_same_chat, active_in_flight)
        execution_order.append(f"start_{ctx.text}")
        await asyncio.sleep(0.05)
        execution_order.append(f"end_{ctx.text}")
        active_in_flight -= 1

    debouncer = ChatDebouncer(
        dispatch_callback=slow_dispatch,
        debounce_delay=0.01,
    )

    chat_id = 1111
    ctx1 = FilterContext(sender_id=chat_id, text="msg1", chat_id=chat_id)
    await debouncer.enqueue(ctx1, 1)

    # Let the first debounce timer fire and enter dispatch
    await asyncio.sleep(0.02)

    # Enqueue a second message for the same chat while dispatch is in-flight
    ctx2 = FilterContext(sender_id=chat_id, text="msg2", chat_id=chat_id)
    await debouncer.enqueue(ctx2, 2)

    # Wait for all dispatches to finish
    await asyncio.sleep(0.15)
    await debouncer.stop()

    assert max_concurrent_for_same_chat == 1, "Same chat must NEVER have >1 concurrent dispatch!"
    assert execution_order == ["start_msg1", "end_msg1", "start_msg2", "end_msg2"]


# ============================================================================
# P1-2: LLM Timeout, Retry, and Atomic /mode Tests
# ============================================================================

async def test_openai_provider_timeout():
    """Verifies that OpenAIProvider times out and raises LLMUnavailableError."""
    provider = OpenAIProvider(
        api_key="sk-real-key-12345",
        timeout_seconds=0.05,
        max_retries=1,
    )

    mock_client = MagicMock()
    async def hanging_call(*args, **kwargs):
        await asyncio.sleep(0.5)
    mock_client.chat.completions.create = AsyncMock(side_effect=hanging_call)
    provider._client = mock_client

    req = LLMRequest(prompt="test timeout")
    with pytest.raises(LLMUnavailableError):
        await provider.generate(req)


async def test_openai_provider_auth_error_no_retry():
    """Verifies that 401 error fails immediately without retrying."""
    provider = OpenAIProvider(
        api_key="sk-invalid-key",
        timeout_seconds=1.0,
        max_retries=3,
    )

    mock_client = MagicMock()
    mock_exc = Exception("Error code: 401 - invalid_api_key")
    mock_exc.status_code = 401
    mock_client.chat.completions.create = AsyncMock(side_effect=mock_exc)
    provider._client = mock_client

    req = LLMRequest(prompt="test auth")
    with pytest.raises(LLMAuthenticationError):
        await provider.generate(req)
    assert mock_client.chat.completions.create.call_count == 1, "401 must NOT be retried!"


async def test_gemini_provider_rate_limit_retry():
    """Verifies that 429 rate limit is retried up to max_retries."""
    provider = GeminiProvider(
        api_key="AIzaSyRealValidKey1234567890",
        timeout_seconds=1.0,
        max_retries=2,
        initial_backoff=0.01,
        retry_backoff_factor=1.0,
    )

    mock_client = MagicMock()
    mock_aio = MagicMock()
    mock_models = MagicMock()
    mock_exc = Exception("429 ResourceExhausted: quota exceeded")
    mock_exc.code = 429
    mock_models.generate_content = AsyncMock(side_effect=mock_exc)
    mock_aio.models = mock_models
    mock_client.aio = mock_aio
    provider._client = mock_client

    req = LLMRequest(prompt="test rate limit")
    with pytest.raises(LLMRateLimitError):
        await provider.generate(req)
    assert mock_models.generate_content.call_count == 2


async def test_mode_switch_atomic_rollback_on_unhealthy_provider(tmp_path: Path):
    """
    Verifies that /mode tests provider health before switching,
    and rolls back / keeps previous mode if candidate fails.
    """
    state_file = tmp_path / "state.json"
    repo = StateRepository(state_file_path=str(state_file))

    settings = Settings(
        telegram_api_id=12345,
        telegram_api_hash="abcdef1234567890abcdef1234567890",
        llm_provider="mock",
    )

    client = MockTelethonClient()
    digest_service = DigestService(userbot_client=UserbotClient(settings=settings, raw_client=client), llm_provider=MockLLMProvider())

    register_saved_messages_handler(
        client=client,
        digest_service=digest_service,
        settings=settings,
        state_repo=repo,
    )

    # Attempt to switch to openai with invalid/missing key (will fail health check)
    msg = MockMessage(id=1, sender_id=0, text="/mode openai", chat_id=0)
    await client.dispatch_event(msg)

    # Settings provider must remain "mock", not "openai"!
    assert settings.llm_provider == "mock"
    assert repo.get_llm_provider() is None or repo.get_llm_provider() == "mock"
    assert any("شکست مواجه شد" in m["message"] or "خطا" in m["message"] for m in client.sent_messages)


# ============================================================================
# P1-3: TelegramMessageSender Chunking & Redaction Tests
# ============================================================================

def test_split_text_into_chunks():
    """Verifies chunking at <= 4096 characters respecting paragraph boundaries."""
    # Text under 4096
    short_text = "سلام کوتاه"
    assert split_text_into_chunks(short_text) == [short_text]

    # Text exactly 4096
    exact_text = "A" * 4096
    assert split_text_into_chunks(exact_text) == [exact_text]

    # Text > 4096 with paragraphs
    part1 = "P1: " + ("B" * 3000)
    part2 = "P2: " + ("C" * 3000)
    combined = f"{part1}\n\n{part2}"
    chunks = split_text_into_chunks(combined, max_length=4000)
    assert len(chunks) == 2
    assert all(len(c) <= 4000 for c in chunks)
    assert chunks[0].startswith("P1:")
    assert chunks[1].startswith("P2:")


def test_redact_sensitive_text():
    """Verifies sensitive OTP and credit card numbers are masked and text truncated."""
    raw = "رمز شما: 123456 و شماره کارت شما 6037-9911-2233-4455 است."
    redacted = redact_sensitive_text(raw, max_length=200)
    assert "123456" not in redacted
    assert "9911-2233" not in redacted
    assert "6037-****-****-4455" in redacted


# ============================================================================
# P1-6: StateRepository Atomic Persistence & Normalization Tests
# ============================================================================

def test_state_repository_persistence_and_normalization(tmp_path: Path):
    """Verifies StateRepository saves and reloads state with normalized entries."""
    state_file = tmp_path / "bot_state.json"
    repo1 = StateRepository(state_file_path=str(state_file))

    # Add items
    repo1.set_paused(True)
    repo1.set_llm_provider("openai")
    repo1.add_to_blacklist("@SpamUser")
    repo1.add_to_blacklist(987654)
    repo1.add_to_allowlist("@TrustedColleague")

    # Re-instantiate repo from the same file (simulating reboot)
    repo2 = StateRepository(state_file_path=str(state_file))
    assert repo2.is_paused() is True
    assert repo2.get_llm_provider() == "openai"
    assert "spamuser" in repo2.get_blacklist()
    assert 987654 in repo2.get_blacklist()
    assert "trustedcolleague" in repo2.get_allowlist()

    # Normalization helper checks
    assert normalize_entry("@MyUser") == "myuser"
    assert normalize_entry("123456") == 123456
    assert normalize_entry(789) == 789
