# 🤖 Telegram AI Agent Userbot

[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Telethon](https://img.shields.io/badge/Telethon-MTProto-blueviolet.svg)](https://github.com/LonamiWebs/Telethon)
[![Docker](https://img.shields.io/badge/Docker-Ready-2496ED.svg)](Dockerfile)
[![Tests: 59 Passed](https://img.shields.io/badge/Tests-59%20Passed-brightgreen.svg)](tests/)

[English](README_EN.md) | [فارسی](README.md)

A modular, production-ready, anti-ban **Telegram MTProto Userbot** built with **Telethon** and powered by multi-provider LLM engines (**Google Gemini**, **OpenAI**, and **Ollama / Local LLMs**).

---

## 🌟 Key Capabilities

1. **Intelligent Channel & Chat Summarization (Digest & Monitoring):**
   - **On-Demand:** Trigger real-time analytical summaries of any channel or chat with `/summary` or multi-channel digests with `/digest` directly in your **Saved Messages**.
   - **Scheduled:** Automatic periodic digest worker delivering curated summaries to your Saved Messages at configurable intervals.

2. **Human-like Private Chat Auto-Reply (DM Agent):**
   - **ChatDebouncer:** Intelligently aggregates rapid consecutive incoming messages from the same user into a unified prompt to prevent duplicate or out-of-order replies.
   - **Human Presence Cooldown:** Automatically pauses auto-replies if the account owner has actively chatted in that conversation within the last 5 minutes.
   - **Quoted Message Context:** Enriches LLM context with quoted/replied-to messages for nuanced understanding.
   - **Humanizer Simulation:** Calculates realistic reading delays, displays Telegram `Typing...` chat actions, and applies proportional typing durations with randomized jitter.

3. **Multi-Layered Security & Anti-Ban Protections:**
   - **Dynamic FloodWait Backoff (`@with_floodwait`):** Intercepts Telegram rate limit errors, applies dynamic sleep with jitter, and safely retries requests.
   - **System Account Filter:** Strictly ignores official Telegram service accounts (e.g., `777000`) and login codes.
   - **Bot Filter:** Blocks automated bots (`is_bot=True` and `*bot` username suffixes) to prevent bot loops and deadlock.
   - **Sensitive Keyword Detector & Emergency Alerting:** Halts auto-replies upon detecting credentials, OTPs, passwords, or payment cards (with Persian/Arabic Unicode normalization), and dispatches immediate security alerts to Saved Messages.

4. **100% Offline Test Infrastructure:**
   - Includes **59 comprehensive unit and scenario tests** across 6 tiers that run in ~4 seconds with zero network access and no API quota consumption.

---

## 🏛️ System Architecture

```
telegram_agent_userbot/
├── config/
│   ├── __init__.py
│   └── settings.py             # Pydantic BaseSettings, loads .env, validates API_ID/HASH
├── client/
│   ├── __init__.py
│   ├── telethon_client.py      # MTProto client lifecycle & session management
│   └── anti_ban.py             # @with_floodwait retry decorator with jitter & typing duration
├── llm/
│   ├── __init__.py
│   ├── base.py                 # BaseLLMProvider, LLMRequest, LLMResponse, LLMMessage
│   ├── gemini_provider.py      # Google Gemini provider (async google-genai SDK)
│   ├── openai_provider.py      # OpenAI provider (openai.AsyncOpenAI & Ollama/vLLM)
│   ├── mock_provider.py        # Offline deterministic MockLLMProvider
│   └── factory.py              # LLM factory & provider registry
├── filters/
│   ├── __init__.py
│   ├── base.py                 # BaseFilter, FilterContext, FilterResult
│   ├── system_filter.py        # Blocks 777000 & official service notifications
│   ├── bot_filter.py           # Blocks bots (is_bot flag & *bot suffix)
│   ├── blacklist_filter.py     # Blocks blacklisted user IDs / usernames with runtime mutations
│   ├── sensitive_filter.py     # Detects sensitive keywords (OTP, passwords, cards) with Unicode normalization
│   └── pipeline.py             # FilterPipeline short-circuiting orchestrator
├── services/
│   ├── __init__.py
│   ├── alert_service.py        # Dispatches security alerts to Saved Messages ('me')
│   ├── chat_debouncer.py       # Aggregates rapid consecutive messages per chat
│   ├── humanizer.py            # Proportional typing delay, reading delay, and jitter
│   ├── digest_service.py       # Message history extraction, chunking, and analytical summarization
│   └── auto_reply_service.py   # DM auto-reply orchestration with human presence cooldown & pause state
├── handlers/
│   ├── __init__.py
│   ├── dm_handler.py           # Telethon NewMessage listener for private chats with debouncer & reply context
│   └── saved_messages_handler.py # Telethon listener for /summary, /digest, /pause, /resume, /mode, /blacklist
├── scheduler/
│   ├── __init__.py
│   └── digest_scheduler.py     # Native asyncio periodic digest background worker
├── scripts/
│   └── generate_session_string.py # Interactive CLI tool to generate TELEGRAM_SESSION_STRING for cloud hosts
├── tests/
│   ├── __init__.py
│   ├── conftest.py             # 100% offline mocks (Telethon, LLM, FastSleep)
│   ├── test_tier1_features.py  # Tier 1: Feature coverage (29 tests)
│   ├── test_tier2_boundaries.py# Tier 2: Boundary & Persian Unicode cases (7 tests)
│   ├── test_tier3_combinations.py# Tier 3: Cross-feature interactions & resilience (5 tests)
│   ├── test_tier4_scenarios.py # Tier 4: Real-world E2E workflows & attacks (4 tests)
│   ├── test_tier5_adversarial.py# Tier 5: Stress, concurrency & adversarial tests (5 tests)
│   └── test_tier6_enhancements.py# Tier 6: Debouncer, cooldown, pause/resume & commands (9 tests)
├── Dockerfile                  # Production container image definition
├── docker-compose.yml          # Container orchestration with volume persistence
├── .env.example                # Clean environment variables template
├── requirements.txt            # Python package dependencies
├── persona_prompt.txt          # Customizable agent persona prompt
├── main.py                     # Application bootstrap & dependency injection
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

# Channels to monitor for periodic digest (comma-separated usernames or IDs)
DIGEST_CHANNELS=durov,tech_news_channel

# Periodic digest interval in minutes
DIGEST_INTERVAL_MINUTES=360
```

### Step 3: Customize Agent Persona (`persona_prompt.txt`)
Modify `persona_prompt.txt` to define the AI assistant's persona, tone, language, and guidelines without altering any Python code.

### Step 4: Run the Application

#### Option A: Direct Python Execution
```bash
# Install dependencies
pip install -r requirements.txt

# Run the userbot
python main.py
```
> **Note on First Run:** During initial startup, Telethon will prompt you in the terminal for your phone number, login code, and 2FA password (if enabled). The session is saved to `userbot_session.session` for subsequent automatic logins.

#### Option B: Docker Compose
```bash
docker-compose up -d
```

#### Option C: Cloud Deployment (Railway, Render, Fly.io)
For stateless or containerized cloud platforms without persistent disks, generate an in-memory session string:
```bash
python scripts/generate_session_string.py
```
Copy the output and set `TELEGRAM_SESSION_STRING` in your cloud platform's environment variables.

---

## 🎮 Saved Messages Command Center

Control your userbot privately and securely by sending commands directly to your **Saved Messages** (`me`):

| Command | Description | Example |
|---|---|---|
| `/summary <channel> [limit] [topic]` | Analyzes and summarizes recent messages from a channel | `/summary @durov 30 AI updates` |
| `/digest [limit]` | Compiles a consolidated digest across all monitored channels | `/digest 20` |
| `/pause [minutes]` | Temporarily pauses auto-replies (timed or indefinite) | `/pause 60` |
| `/resume` | Resumes automated replies | `/resume` |
| `/mode <gemini\|openai\|mock>` | Switches the active LLM engine on the fly | `/mode openai` |
| `/blacklist <add\|remove> <user>` | Dynamically adds or removes user IDs / usernames from blacklist | `/blacklist add @spammer` |
| `/status` | Displays connection health, active model, pause status, and stats | `/status` |
| `/help` | Shows the full command manual | `/help` |

---

## 🧪 Offline Verification & Testing

The userbot includes a comprehensive offline test suite requiring no network connection or API keys:

```bash
python -m pytest tests/ -v
```

### Test Coverage (59 Tests / 100% Pass Rate):
- **Tier 1 (Feature Tests - 29 tests):** Unit verification of configuration, anti-ban backoff, humanizer, LLM providers, and core filters.
- **Tier 2 (Boundary Tests - 7 tests):** Edge-case message lengths, Unicode variations, and Persian/Arabic normalizations.
- **Tier 3 (Combination Tests - 5 tests):** Filter interactions, LLM outage resilience, and partial channel error recovery.
- **Tier 4 (Scenarios Tests - 4 tests):** Full E2E workflows, phishing alert halts, on-demand summaries, and scheduler execution.
- **Tier 5 (Adversarial Tests - 5 tests):** Stress tests, concurrent message processing, and zero-width character injection.
- **Tier 6 (Enhancements Tests - 9 tests):** ChatDebouncer batching, active human presence cooldown, dynamic commands, and quoted message context.

---

## ⚖️ Disclaimer

This software is developed strictly for educational, research, and personal automation purposes. Users are solely responsible for complying with the [Telegram Terms of Service](https://telegram.org/tos). The developers assume no liability for misuse, bulk spamming, or account restrictions.

---

## 📄 License

This project is licensed under the [MIT License](LICENSE).
