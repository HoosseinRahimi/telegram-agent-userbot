# E2E Test Infra: Telegram AI Agent Userbot

## Test Philosophy
- **Opaque-box & Requirement-driven**: Derived directly from `ORIGINAL_REQUEST.md` (R1 through R6).
- **100% Offline**: Zero reliance on live Telegram servers, active phone numbers, or external LLM API endpoints.
- **Fast Execution**: Auto-patching `fast_sleep` eliminates real-time waiting while recording exact sleep parameters for assertion.
- **Methodology**: Category-Partition + Boundary Value Analysis + Pairwise Combinatorial Testing + Real-World Workload Testing.

---

## Feature Inventory Mapping
| # | Feature | Source | Tier 1 | Tier 2 | Tier 3 | Tier 4 |
|---|---------|--------|:------:|:------:|:------:|:------:|
| F01 | Environment Configuration | R1 | 5 | ✓ | ✓ | ✓ |
| F02 | API Credentials Validation | R1 | 5 | ✓ | ✓ | ✓ |
| F03 | Session Management | R1 | 5 | ✓ | - | ✓ |
| F04 | Anti-Ban FloodWait Handler | R5 | 5 | ✓ | ✓ | ✓ |
| F05 | BaseLLMProvider & MockLLM | R2 | 5 | - | ✓ | ✓ |
| F06 | Gemini & OpenAI Providers | R2 | 5 | ✓ | ✓ | ✓ |
| F07 | Safety Filter Pipeline (777000, bot, blacklist) | R4 | 6 | ✓ | ✓ | ✓ |
| F08 | Sensitive Keyword Alerting | R4 | 5 | ✓ | ✓ | ✓ |
| F09 | Humanizer (Typing status, reading delay, jitter) | R4 | 5 | ✓ | ✓ | ✓ |
| F10 | Saved Messages Commands (/summary, /digest) | R3 | 5 | ✓ | ✓ | ✓ |
| F11 | Periodic Digest Scheduler | R3 | 5 | ✓ | ✓ | ✓ |

---

## Test Architecture
- **Test Runner**: `pytest tests/ -v` (configured via `pytest.ini` with `asyncio_mode = auto`)
- **Test Directory**: `tests/`
  - `tests/conftest.py`: Fixtures for `MockTelethonClient`, `MockNewMessageEvent`, `MockActionContext`, `MockAsyncMessageIterator`, `MockLLMProvider`, `fast_sleep`, and sample configurations.
  - `tests/test_tier1_features.py`: Feature coverage (≥5 tests per feature, total ≥ 50 tests).
  - `tests/test_tier2_boundaries.py`: Boundary and corner cases (empty strings, 777000, case-insensitivity, extreme delays, unicode Persian keywords).
  - `tests/test_tier3_combinations.py`: Cross-feature interactions (blacklist vs security keyword, FloodWait during reply, LLM outage during command).
  - `tests/test_tier4_scenarios.py`: Full end-to-end user journeys (incoming private DM, Saved Messages /summary, Security alert to 'me').

---

## Coverage Thresholds
- Tier 1: ≥5 per feature across all core features (Target: 45+ tests)
- Tier 2: ≥5 boundary & corner case tests (Target: 10+ tests)
- Tier 3: Pairwise & cross-feature combination tests (Target: 6+ tests)
- Tier 4: Real-world end-to-end scenario workflows (Target: 4+ tests)
- **Minimum Target**: ≥ 65 tests passing with 100% success rate and zero network calls.
