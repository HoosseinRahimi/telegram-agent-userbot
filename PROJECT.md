# Project: Telegram AI Agent Userbot
# Working Directory: telegram-agent-userbot

## Architecture
Modular Python architecture built upon Telethon (MTProto), Google Gemini / OpenAI (via modular LLM engine), and Pytest offline mocking:

```
telegram_agent_userbot/
├── config/
│   ├── __init__.py
│   └── settings.py             # Pydantic BaseSettings, loads .env, validates API_ID/HASH
├── client/
│   ├── __init__.py
│   ├── telethon_client.py      # MTProto client lifecycle & session management
│   └── anti_ban.py             # @with_floodwait retry decorator with jitter
├── llm/
│   ├── __init__.py
│   ├── base.py                 # BaseLLMProvider, LLMRequest, LLMResponse, LLMMessage
│   ├── gemini_provider.py      # Google Gemini provider (google-genai / async)
│   ├── openai_provider.py      # OpenAI provider (openai.AsyncOpenAI)
│   ├── mock_provider.py        # Offline deterministic MockLLMProvider
│   └── factory.py              # LLM factory & provider registry
├── filters/
│   ├── __init__.py
│   ├── base.py                 # BaseFilter, FilterContext, FilterResult
│   ├── system_filter.py        # Blocks 777000 & official service notifications
│   ├── bot_filter.py           # Blocks bots (is_bot flag)
│   ├── blacklist_filter.py     # Blocks blacklisted user IDs / usernames
│   ├── sensitive_filter.py     # Detects sensitive keywords (OTP, passwords, cards)
│   └── pipeline.py             # FilterPipeline short-circuiting orchestrator
├── services/
│   ├── __init__.py
│   ├── alert_service.py        # Dispatches security alerts to Saved Messages ('me')
│   ├── humanizer.py            # Proportional typing delay, reading delay, and jitter
│   ├── digest_service.py       # Message history extraction, chunking, and summarization
│   └── auto_reply_service.py   # DM auto-reply orchestration with filters & humanizer
├── handlers/
│   ├── __init__.py
│   ├── dm_handler.py           # Telethon NewMessage listener for private chats
│   └── saved_messages_handler.py # Telethon listener for /summary & /digest in 'me'
├── scheduler/
│   ├── __init__.py
│   └── digest_scheduler.py     # Lightweight native asyncio periodic digest worker
├── tests/
│   ├── __init__.py
│   ├── conftest.py             # 100% offline mocks (Telethon, LLM, fast_sleep)
│   ├── test_tier1_features.py  # Tier 1: Feature coverage (>=5 per feature)
│   ├── test_tier2_boundaries.py# Tier 2: Boundary & corner cases
│   ├── test_tier3_combinations.py# Tier 3: Cross-feature interactions
│   └── test_tier4_scenarios.py # Tier 4: Real-world E2E workflows
├── .env.example                # Clean template for credentials
├── requirements.txt            # Dependencies (telethon, google-genai, openai, pytest, etc.)
├── persona_prompt.txt          # Customizable agent persona prompt
├── main.py                     # Application bootstrap & dependency injection
└── README.md                   # Setup, usage, and offline verification guide
```

---

## Feature Inventory
| # | Feature | Description | Milestone | Source |
|---|---------|-------------|-----------|--------|
| F01 | Environment Configuration | Pydantic BaseSettings loading .env with validation | M1 | Survey |
| F02 | API Credentials Validation | Validates TELEGRAM_API_ID and TELEGRAM_API_HASH | M1 | Survey |
| F03 | Telethon Session Management | Safe session file / session string management | M1 | Survey |
| F04 | Zero Hardcoded Secrets | Ensures no API keys or tokens are in source code | M1 | Survey |
| F05 | FloodWaitError Dynamic Backoff | Decorator with dynamic sleep, jitter, and safety cutoff | M1 | Survey |
| F06 | Connection Resilience | Auto-reconnect & network fault tolerance | M1 | Survey |
| F07 | BaseLLMProvider Interface | Abstract base class with LLMRequest/Response/Message | M2 | Survey |
| F08 | Gemini Provider | Google Gemini API integration using async client | M2 | Survey |
| F09 | OpenAI Provider | OpenAI API integration using AsyncOpenAI | M2 | Survey |
| F10 | Mock LLM Provider | Deterministic offline mock for testing | M2 | Survey |
| F11 | LLM Factory | Instantiates active provider from configuration | M2 | Survey |
| F12 | LLM Error Hierarchy | Typed exceptions for timeouts, rate limits, failures | M2 | Survey |
| F13 | Message History Extraction | Telethon iter_messages with limit and error handling | M3 | Survey |
| F14 | Analytical Digest Generation | Summarizes chat messages into analytical report via LLM | M3 | Survey |
| F15 | Telegram Message Chunking | Splits summaries exceeding 4096 chars safely | M3 | Survey |
| F16 | On-Demand /summary Command | Triggers single-channel summary in Saved Messages | M3 | Survey |
| F17 | On-Demand /digest Command | Triggers multi-channel digest in Saved Messages | M3 | Survey |
| F18 | Scheduled Periodic Digest | Async scheduler automatically delivering reports to 'me' | M3 | Survey |
| F19 | Self-Message Guard | Prevents userbot from responding to own messages | M4 | Survey |
| F20 | System Account Filter | Strictly rejects Telegram system (777000) messages | M4 | Survey |
| F21 | Bot Account Filter | Strictly rejects messages from bot accounts (is_bot=True) | M4 | Survey |
| F22 | Blacklist Filter | Rejects configured blacklisted user IDs and usernames | M4 | Survey |
| F23 | Sensitive Keyword Detector | Detects OTPs, passwords, banking data; halts auto-reply | M4 | Survey |
| F24 | Security Alerting Service | Sends security alert to Saved Messages on sensitive event | M4 | Survey |
| F25 | Persona Customization | Loads persona from persona_prompt.txt into system prompt | M4 | Survey |
| F26 | Proportional Typing Status | Emits typing action proportional to reply length (pulsed) | M4 | Survey |
| F27 | Human-like Delay & Jitter | Simulates realistic reading delay and typing jitter | M4 | Survey |
| F28 | Main Application Entrypoint | Bootstraps client, wires services, handles graceful exit | M4 | Survey |
| F29 | Offline Test Infrastructure | conftest.py with MockTelethonClient, fast_sleep, MockLLM | E2E / M5 | Survey |
| F30 | 100% Offline Pytest Suite | Tiers 1-4 tests covering all 28 features (exit code 0) | M5 (Phase 1) | Survey |
| F31 | Adversarial Hardening | Tier 5 white-box edge tests with zero gaps | M5 (Phase 2) | Survey |

---

## Milestones
| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|--------|
| E2E | E2E Test Suite Track | Design & implement comprehensive offline pytest suite (Tiers 1-4) | Survey | IN_PROGRESS |
| M1 | Client & Anti-Ban Foundation | config/, client/, .env.example, requirements.txt, FloodWait | none | PLANNED |
| M2 | Modular LLM Engine | llm/ base, gemini, openai, mock, factory | M1 | PLANNED |
| M3 | Monitoring & Digest Service | services/digest_service, handlers/saved_messages_handler, scheduler | M1, M2 | PLANNED |
| M4 | Human-like DM Auto-reply & Safety | filters/, services/humanizer, alert_service, auto_reply, persona_prompt.txt, main.py | M1, M2 | PLANNED |
| M5 | Final Verification & Hardening | Phase 1: 100% E2E test pass (Tiers 1-4); Phase 2: Tier 5 adversarial hardening | M1, M2, M3, M4, E2E | PLANNED |

---

## Interface Contracts

### `config.settings` ↔ All Modules
```python
class Settings(BaseSettings):
    telegram_api_id: int
    telegram_api_hash: str
    telegram_session_name: str = "userbot_session"
    telegram_session_string: Optional[str] = None
    llm_provider: str = "gemini"  # gemini, openai, mock
    gemini_api_key: Optional[str] = None
    gemini_model: str = "gemini-2.5-flash"
    openai_api_key: Optional[str] = None
    openai_model: str = "gpt-4o-mini"
    openai_base_url: Optional[str] = None
    blacklist_users: List[Union[int, str]] = []
    sensitive_keywords: List[str] = [...]
    digest_channels: List[Union[int, str]] = []
    digest_interval_minutes: int = 360
    persona_prompt_path: str = "persona_prompt.txt"
```

### `llm.base` ↔ `services`
```python
@dataclass
class LLMMessage:
    role: str  # "system", "user", "assistant"
    content: str

@dataclass
class LLMRequest:
    messages: List[LLMMessage]
    temperature: float = 0.7
    max_tokens: int = 1024

@dataclass
class LLMResponse:
    content: str
    model: str
    tokens_used: Optional[int] = None

class BaseLLMProvider(ABC):
    @abstractmethod
    async def generate(self, request: LLMRequest) -> LLMResponse: ...
```

### `filters` ↔ `services.auto_reply_service`
```python
@dataclass
class FilterContext:
    event: Any
    sender_id: int
    sender_username: Optional[str]
    is_bot: bool
    is_self: bool
    message_text: str

@dataclass
class FilterResult:
    allowed: bool
    reason: Optional[str] = None
    is_sensitive: bool = False
    matched_keyword: Optional[str] = None

class FilterPipeline:
    async def evaluate(self, context: FilterContext) -> FilterResult: ...
```

### Anti-Ban `@with_floodwait`
```python
def with_floodwait(max_retries: int = 3, max_wait_seconds: int = 300, jitter_max: float = 2.0):
    # Catches telethon.errors.FloodWaitError, sleeps dynamic seconds + jitter, retries up to max_retries.
```

### `services.humanizer`
```python
def calculate_reading_delay(text: str) -> float: ...
def calculate_typing_delay(text: str) -> float: ...
async def simulate_human_typing(client: Any, chat_id: Any, duration: float) -> None: ...
```

---

## Code Layout
Defined under the repository root `telegram-agent-userbot`.
All implementation files reside in their designated package directories. No source code or tests may be written into `.agents/`.
