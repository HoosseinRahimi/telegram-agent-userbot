# E2E Test Infrastructure: Telegram AI Agent Userbot

## Test Philosophy
- **Opaque-box & Requirement-driven**: Validates requirements across all 4 production tiers and improvement phases.
- **100% Offline & Deterministic**: Zero reliance on live Telegram MTProto servers, active phone numbers, or external cloud LLM endpoints.
- **Instantaneous Execution**: Auto-patching `FastSleepRecorder` eliminates real-time waiting while recording exact sleep parameters for assertion.
- **Native Async Runner**: Zero external test plugin dependencies; runs asynchronously out of the box via native `pytest_pyfunc_call` hook.
- **Methodology**: Category-Partition + Boundary Value Analysis + Pairwise Combinatorial Testing + Adversarial / Stress Testing.

---

## Test Inventory & Structure

| Suite File | Focus Area | Tests | Key Capabilities Verified |
|------------|------------|:-----:|---------------------------|
| `tests/test_p0_fixes.py` | Phase 1 (P0) Baseline | 7 | CSV `.env` parsing without `SettingsError`, Active Cooldown differentiating bot from human, safe defaults (`AUTO_REPLY_ENABLED=false`, `ALLOWLIST_USERS`, `DRY_RUN`, `SEND_HISTORY_TO_PROVIDER`). |
| `tests/test_p1_reliability.py` | Phase 2 (P1) Reliability | 8 | `ChatDebouncer` per-chat serialization lock & global concurrency semaphore, LLM timeout & exponential retry backoff, atomic `/mode` switch with rollback on failure, `TelegramMessageSender` <=4096 chunking, atomic `StateRepository` persistence. |
| `tests/test_p3_security.py` | Phase 3 (Security & Privacy) | 12 | `SensitiveFilter` Luhn algorithm credit card verification, structural OTP regex with Persian/Arabic numerals, private key interception, `AlertService` anti-flood throttling & suppressed alert notice, `DMHandler` media-only ignore, age cutoff (>300s), MTProto message deduplication, `<untrusted_user_input>` prompt injection defense, and PII redaction. |
| `tests/test_tier1_features.py` | Tier 1: Core Feature Verification | 29 | Settings validation, secret masking, blacklist parsing, FloodWait recovery, filters (System, Bot, Blacklist, Sensitive), LLM factory & mock, Humanizer, Saved Messages commands. |
| `tests/test_tier2_boundaries.py` | Tier 2: Boundary & Corner Cases | 7 | Empty strings, huge message chunking, system account edge cases, Persian ZWNJ, Arabic Kaf/Yeh normalization, Harakat stripping, summary limits. |
| `tests/test_tier3_combinations.py` | Tier 3: Combinatorial & Failover | 5 | Blacklist before sensitive keyword (short-circuiting), Bot before sensitive, FloodWait recovery during auto-reply, LLM outage resilience, partial digest resilience. |
| `tests/test_tier4_scenarios.py` | Tier 4: Real-World Scenarios | 4 | Legitimate DM auto-reply workflow, security phishing attack halt & alert, on-demand `/summary`, background periodic digest. |
| `tests/test_tier5_adversarial.py` | Tier 5: Adversarial & Stress | 5 | Zero-width unicode attacks, missing persona file fallback, junk in blacklist, concurrent DMs from multiple users, history with empty/media messages. |
| `tests/test_tier6_enhancements.py` | Tier 6: Behavioral Enhancements | 9 | Advanced normalization, debouncer aggregation, active chat cooldown, pause/resume, dynamic blacklist/mode commands, quoted message context. |
| **Total** | **Full Coverage Suite** | **86** | **100% Offline, Fast & Deterministic** |

---

## Running Tests

### 1. Run Complete Test Suite
```bash
pytest tests/ -v
```

### 2. Run with Code Coverage Report
```bash
pytest --cov=. --cov-report=term-missing --cov-report=html
```

### 3. Run Specific Test Suite
```bash
pytest tests/test_p0_fixes.py -v
pytest tests/test_p1_reliability.py -v
pytest tests/test_p3_security.py -v
```

### 4. Code Formatting and Linting (Ruff)
```bash
ruff check .
ruff format --check .
```
