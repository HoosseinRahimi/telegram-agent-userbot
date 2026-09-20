# 🤖 Telegram AI Agent Userbot

[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Telethon](https://img.shields.io/badge/Telethon-MTProto-blueviolet.svg)](https://github.com/LonamiWebs/Telethon)
[![Docker](https://img.shields.io/badge/Docker-Ready-2496ED.svg)](Dockerfile)
[![Tests: 86 Passed](https://img.shields.io/badge/Tests-86%20Passed-brightgreen.svg)](tests/)

[English](README_EN.md) | [فارسی](README.md)

A modular, production-ready, privacy-first **Telegram MTProto Userbot** built with **Telethon** and powered by multi-provider LLM engines (**Google Gemini**, **OpenAI**, and **Ollama / Local LLMs**), featuring advanced **Rate-Limit Resilience** and FloodWait recovery.

---

## 🌟 Key Capabilities & Security Architecture

1. **Intelligent Channel & Chat Summarization (Digest & Monitoring):**
   - **On-Demand:** Trigger real-time analytical summaries of any channel or chat with `/summary` or multi-channel digests with `/digest` directly in your **Saved Messages**.
   - **Scheduled:** Automatic periodic digest worker delivering curated summaries to your Saved Messages at configurable intervals.
   - **Prompt Injection Defense:** Wraps all external channel histories in structural `<untrusted_channel_history>` XML tags with strict system directives to prevent prompt overrides.

2. **Human-like Private Chat Auto-Reply (DM Agent):**
   - **Safe Defaults:** Auto-reply is disabled by default (`AUTO_REPLY_ENABLED=false`) to prevent unintended responses. Scoped allowlists (`ALLOWLIST_USERS`) and simulation mode (`DRY_RUN=true`) ensure complete control.
   - **ChatDebouncer:** Serializes incoming messages per chat with a dedicated `asyncio.Lock` and limits system-wide dispatches via an `asyncio.Semaphore`.
   - **Human Presence Cooldown:** Automatically suppresses bot replies if the account owner has actively chatted in that conversation recently.
   - **Quoted Message Context:** Enriches LLM context with quoted/replied-to messages for nuanced understanding.
   - **Humanizer Simulation:** Calculates realistic reading delays, displays Telegram `Typing...` chat actions, and applies proportional typing durations with randomized jitter.

3. **Multi-Layered Security & Privacy Defenses:**
   - **Rate-Limit Resilience (`@with_floodwait`):** Intercepts Telegram rate limit errors, applies dynamic backoff with jitter, and safely retries requests.
   - **Structural Financial & OTP Filter:** Intercepts 13-19 digit credit/debit cards using the **Luhn Algorithm**, detects 4-8 digit OTP codes, and blocks private keys/API tokens.
   - **Alert Anti-Flood Throttling:** Throttles security alerts per sender (60-second cooldown) to protect your Saved Messages from spam.
   - **PII Redaction Before Cloud Inference:** Masks sensitive card patterns and OTPs before prompts leave the local machine for third-party LLM providers.
   - **Atomic State Persistence:** Persists pause state, active mode, and blacklist changes in `/data/state.json` via atomic file replacements (`os.replace`).

---

## 🏛️ System Architecture

```
telegram_agent_userbot/
├── config/
│   ├── __init__.py
│   └── settings.py             # Pydantic Settings with robust non-JSON CSV parser
├── client/
│   ├── __init__.py
│   ├── telethon_client.py      # MTProto client lifecycle & session management
│   ├── anti_ban.py             # @with_floodwait retry decorator with jitter & typing duration
│   └── message_sender.py       # Safe message dispatcher with <=4096 chunking & PII redaction
├── llm/
│   ├── __init__.py
│   ├── base.py                 # BaseLLMProvider, LLMRequest, LLMResponse, LLMMessage
│   ├── gemini_provider.py      # Google Gemini provider with timeout & exponential backoff
│   ├── openai_provider.py      # OpenAI & Ollama/vLLM provider with 429/5xx retry logic
│   ├── mock_provider.py        # Offline deterministic MockLLMProvider for unit testing
│   └── factory.py              # LLM factory & provider registry
├── filters/
│   ├── __init__.py
│   ├── base.py                 # BaseFilter, FilterContext, FilterResult
│   ├── system_filter.py        # Blocks 777000 & official service notifications
│   ├── bot_filter.py           # Blocks bots (is_bot flag & *bot suffix)
│   ├── blacklist_filter.py     # Blocks blacklisted user IDs / usernames with runtime mutations
│   ├── sensitive_filter.py     # Luhn credit cards, OTP codes, private keys, and Persian Unicode
│   └── pipeline.py             # FilterPipeline short-circuiting orchestrator
├── services/
│   ├── __init__.py
│   ├── alert_service.py        # Dispatches security alerts to Saved Messages with anti-flood
│   ├── chat_debouncer.py       # Per-chat lock & global concurrency semaphore
│   ├── humanizer.py            # Proportional typing delay, reading delay, and jitter
│   ├── digest_service.py       # Message history extraction, chunking, and analytical summarization
│   ├── auto_reply_service.py   # DM auto-reply orchestration with human presence cooldown & PII redaction
│   └── state_repository.py     # Atomic state persistence at /data/state.json
├── handlers/
│   ├── __init__.py
│   ├── dm_handler.py           # Media-only policy, message age cutoff, and deduplication
│   └── saved_messages_handler.py # /summary, /digest, /pause, /resume, /mode, /blacklist, /status
├── scheduler/
│   ├── __init__.py
│   └── digest_scheduler.py     # Native asyncio periodic digest background worker
├── scripts/
│   └── generate_session_string.py # Interactive CLI tool to generate TELEGRAM_SESSION_STRING
├── tests/
│   ├── __init__.py
│   ├── conftest.py             # 100% offline mocks (Telethon, LLM, FastSleep)
│   ├── test_p0_fixes.py        # P0: CSV settings, bot vs human cooldown, safe defaults (7 tests)
│   ├── test_p1_reliability.py  # P1: Debouncer lock, LLM retry/timeout, atomic state (8 tests)
│   ├── test_p3_security.py     # P3: Luhn checks, OTP regex, alert throttling, age cutoff (12 tests)
│   ├── test_tier1_features.py  # Tier 1: Core feature verification (29 tests)
│   ├── test_tier2_boundaries.py# Tier 2: Boundary & Persian Unicode cases (7 tests)
│   ├── test_tier3_combinations.py# Tier 3: Cross-feature interactions & resilience (5 tests)
│   ├── test_tier4_scenarios.py # Tier 4: Real-world E2E workflows & attacks (4 tests)
│   ├── test_tier5_adversarial.py# Tier 5: Stress, concurrency & adversarial tests (5 tests)
│   └── test_tier6_enhancements.py# Tier 6: Debouncer, cooldown, pause/resume & commands (9 tests)
├── Dockerfile                  # Multi-stage container build with non-root user
├── docker-compose.yml          # Container orchestration with ./data volume mount
├── pyproject.toml              # PEP 517/621 project configuration with Ruff and Pytest
├── .env.example                # Clean environment variables template with safe defaults
├── requirements.txt            # Python package dependencies
├── persona_prompt.txt          # Customizable agent persona prompt
├── main.py                     # Application bootstrap with SIGINT/SIGTERM handling
└── README.md                   # Persian documentation
```

---

## 🚀 Quickstart Guide

### Prerequisites
- Python 3.10 or higher (or Docker)
- Telegram account credentials (`API_ID` & `API_HASH` from [my.telegram.org](https://my.telegram.org))

### Step 1: Clone Repository
```bash
git clone https://github.com/HoosseinRahimi/telegram-agent-userbot.git
cd telegram-agent-userbot
```

### Step 2: Configure Environment Variables
Copy `.env.example` to `.env`:
```bash
cp .env.example .env
```
Edit `.env` with your API credentials:
```env
TELEGRAM_API_ID=12345678
TELEGRAM_API_HASH=your_telegram_api_hash_here

# LLM Provider: 'gemini', 'openai', or 'mock'
LLM_PROVIDER=gemini
GEMINI_API_KEY=your_google_gemini_api_key_here
GEMINI_MODEL=gemini-2.5-flash

# Safety & Auto-Reply Controls
AUTO_REPLY_ENABLED=false
ALLOWLIST_USERS=12345678,trusted_friend
DRY_RUN=false
SEND_HISTORY_TO_PROVIDER=true
REDACT_PII_BEFORE_LLM=true

# Channels to monitor for periodic digest
DIGEST_CHANNELS=durov,tech_news_channel
DIGEST_INTERVAL_MINUTES=360
```

### Step 3: Customize Agent Persona (`persona_prompt.txt`)
Modify `persona_prompt.txt` to define the AI assistant's persona, tone, language, and guidelines without altering any Python code.

### Step 4: Run the Application

#### Option A: Direct Python Execution
```bash
# Install dependencies
pip install -e ".[dev]"

# Run the userbot
python main.py
```
> **Note on First Run:** During initial startup, Telethon will prompt you in the terminal for your phone number, login code, and 2FA password (if enabled). The session is saved to `userbot_session.session`.

#### Option B: Docker Compose (Recommended for Production)
```bash
docker-compose up -d
```
All persistent session and configuration data are safely stored in `./data`.

---

## 🎮 Saved Messages Command Center

Control your userbot privately and securely by sending commands directly to your **Saved Messages** (`me`):

| Command | Description | Example |
|---|---|---|
| `/summary <channel> [limit] [topic]` | Analyzes and summarizes recent messages from a channel | `/summary @durov 30 AI updates` |
| `/digest [limit]` | Compiles a consolidated digest across all monitored channels | `/digest 20` |
| `/pause [minutes]` | Temporarily pauses auto-replies (timed or indefinite) | `/pause 60` |
| `/resume` | Resumes automated replies | `/resume` |
| `/mode <gemini\|openai\|mock>` | Atomically switches active LLM engine with pre-flight health check | `/mode openai` |
| `/blacklist <add\|remove> <user>` | Dynamically adds or removes user IDs / usernames from blacklist | `/blacklist add @spammer` |
| `/status` | Displays connection health, active model, allowlist, dry run, and stats | `/status` |
| `/help` | Shows the full command manual | `/help` |

---

## 🧪 Offline Verification & Testing

The userbot includes a comprehensive offline test suite requiring no network connection or API keys:

```bash
pytest tests/ -v
```

### Test Coverage (86 Tests / 100% Pass Rate):
- **Phase 0 Tests (7 tests):** CSV parsing, bot vs human cooldown, allowlist, dry run.
- **Phase 1 Tests (8 tests):** Debouncer lock, LLM timeout & retry, atomic mode switch, atomic state persistence.
- **Phase 3 Tests (12 tests):** Luhn credit cards, OTP regex, alert throttling, media-only policy, message age cutoff.
- **Tier 1-6 Tests (59 tests):** Comprehensive coverage of core features, boundary cases, combinations, real-world scenarios, and stress tests.

---

## ⚖️ Disclaimer & Account Safety

⚠️ **Telegram Terms of Service Notice:**
This software operates as a **Telegram Userbot** automating actions on personal accounts via the MTProto protocol. While it employs advanced rate-limiting resilience (`@with_floodwait`), human-like typing delays (`Humanizer`), and active chat cooldowns, automated user accounts carry inherent risks under [Telegram's Terms of Service](https://telegram.org/tos).

**Best Practices:**
1. Test your setup using `DRY_RUN=true` first.
2. Scope automated replies to trusted users with `ALLOWLIST_USERS`.
3. Never use this tool for unsolicited marketing, bulk messaging, or spam.
4. The developers assume no liability for account limitations, temporary restrictions, or bans resulting from user activity.

---

## 📄 License

This project is licensed under the [MIT License](LICENSE).
