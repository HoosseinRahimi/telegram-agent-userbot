"""
Pytest Test Infrastructure & 100% Offline Mocks.

Provides:
- Native async test runner hook (zero external plugin dependency).
- MockTelethonClient: In-memory MTProto simulation without real Telegram connection.
- MockLLMProvider: Deterministic LLM engine.
- fast_sleep: Replaces asyncio.sleep for instantaneous execution while recording calls.
- sample_settings: Valid test Settings fixture.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
import inspect
from typing import Any, AsyncIterator, Callable, Dict, List, Optional, Union

import pytest

from config.settings import Settings
from filters.base import FilterContext
from llm.base import BaseLLMProvider, LLMMessage, LLMRequest, LLMResponse
from llm.mock_provider import MockLLMProvider


# ============================================================================
# Native Async Test Runner Hook
# ============================================================================

@pytest.hookimpl(tryfirst=True)
def pytest_pyfunc_call(pyfuncitem: Any) -> Optional[bool]:
    """
    Executes async coroutine test functions using asyncio.run() natively,
    avoiding the requirement for external pytest-asyncio plugins.
    """
    if inspect.iscoroutinefunction(pyfuncitem.obj):
        argnames = pyfuncitem._fixtureinfo.argnames
        kwargs = {arg: pyfuncitem.funcargs[arg] for arg in argnames if arg in pyfuncitem.funcargs}
        asyncio.run(pyfuncitem.obj(**kwargs))
        return True
    return None


# ============================================================================
# Mock Data Models & Exceptions
# ============================================================================

class MockFloodWaitError(Exception):
    """Simulates Telethon FloodWaitError with a seconds attribute."""
    def __init__(self, seconds: int = 5) -> None:
        super().__init__(f"A wait of {seconds} seconds is required (caused by FloodWaitError)")
        self.seconds = seconds


@dataclass
class MockUser:
    id: int
    first_name: str = "TestUser"
    username: Optional[str] = None
    bot: bool = False


@dataclass
class MockMessage:
    id: int
    sender_id: int
    text: str
    chat_id: int
    date: datetime = field(default_factory=datetime.now)
    out: bool = False
    sender: Optional[MockUser] = None
    is_private: bool = True

    @property
    def message(self) -> str:
        return self.text

    @property
    def raw_text(self) -> str:
        return self.text

    async def get_sender(self) -> Optional[MockUser]:
        return self.sender or MockUser(id=self.sender_id, bot=False)

    async def reply(self, response_text: str) -> MockMessage:
        return MockMessage(
            id=self.id + 1000,
            sender_id=0,
            text=response_text,
            chat_id=self.chat_id,
            out=True,
        )


class MockActionContext:
    """Simulates Telethon async with client.action(chat, 'typing'): context."""
    def __init__(self, action_type: str = "typing") -> None:
        self.action_type = action_type
        self.entered = False
        self.exited = False

    async def __aenter__(self) -> MockActionContext:
        self.entered = True
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.exited = True


# ============================================================================
# Mock Telethon Client
# ============================================================================

class MockTelethonClient:
    """
    In-memory offline simulation of Telethon TelegramClient.
    Tracks all sent messages, chat actions, reads, and event registrations.
    """

    def __init__(self) -> None:
        self.sent_messages: List[Dict[str, Any]] = []
        self.chat_history: Dict[Any, List[MockMessage]] = {}
        self.event_handlers: List[tuple[Callable[..., Any], Any]] = []
        self.read_acknowledges: List[Dict[str, Any]] = []
        self.actions_triggered: List[tuple[Any, str]] = []
        self.is_connected = True
        self.next_message_id = 100
        self.floodwait_trigger: Optional[int] = None  # if set, raises MockFloodWaitError N times
        self._floodwait_count = 0

    def add_event_handler(self, callback: Callable[..., Any], event_filter: Any = None) -> None:
        self.event_handlers.append((callback, event_filter))

    async def get_me(self) -> MockUser:
        return MockUser(id=999999, first_name="Hossein", username="hossein_user")

    def action(self, entity: Any, action_type: str) -> MockActionContext:
        self.actions_triggered.append((entity, action_type))
        return MockActionContext(action_type=action_type)

    async def send_message(
        self,
        entity: Any,
        message: str,
        reply_to: Optional[Any] = None,
        **kwargs: Any,
    ) -> MockMessage:
        if self.floodwait_trigger and self._floodwait_count < self.floodwait_trigger:
            self._floodwait_count += 1
            raise MockFloodWaitError(seconds=2)

        self.next_message_id += 1
        msg_obj = MockMessage(
            id=self.next_message_id,
            sender_id=999999,
            text=message,
            chat_id=entity if isinstance(entity, int) else 0,
            out=True,
        )
        self.sent_messages.append({
            "entity": entity,
            "message": message,
            "reply_to": reply_to,
            "msg_obj": msg_obj,
            "kwargs": kwargs,
        })
        return msg_obj

    async def send_read_acknowledge(self, entity: Any, max_id: Optional[int] = None, **kwargs: Any) -> bool:
        self.read_acknowledges.append({"entity": entity, "max_id": max_id})
        return True

    async def iter_messages(self, entity: Any, limit: int = 50, **kwargs: Any) -> AsyncIterator[MockMessage]:
        msgs = self.chat_history.get(entity, [])[:limit]
        for m in msgs:
            yield m

    async def get_messages(self, entity: Any, limit: int = 50, **kwargs: Any) -> List[MockMessage]:
        return self.chat_history.get(entity, [])[:limit]


# ============================================================================
# Pytest Fixtures
# ============================================================================

class FastSleepRecorder:
    """Fast in-memory mock for asyncio.sleep that tracks elapsed sleep calls without waiting."""
    def __init__(self) -> None:
        self.calls: List[float] = []
        self.total_seconds: float = 0.0

    async def __call__(self, seconds: float) -> None:
        self.calls.append(seconds)
        self.total_seconds += seconds


@pytest.fixture
def fast_sleep() -> FastSleepRecorder:
    return FastSleepRecorder()


@pytest.fixture
def sample_settings() -> Settings:
    return Settings(
        telegram_api_id=12345678,
        telegram_api_hash="0123456789abcdef0123456789abcdef",
        telegram_session_name="test_session",
        llm_provider="mock",
        blacklist_users=["111222", "blocked_user"],
        sensitive_keywords=["otp", "رمز عبور", "card number", "رمز دوم"],
        digest_channels=["test_channel", "crypto_news"],
        digest_interval_minutes=60,
    )


@pytest.fixture
def mock_telethon_client() -> MockTelethonClient:
    return MockTelethonClient()


@pytest.fixture
def mock_llm_provider() -> MockLLMProvider:
    return MockLLMProvider(default_response="پاسخ تست ایجنت هوشمند")
