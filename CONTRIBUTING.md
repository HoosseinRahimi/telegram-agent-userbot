# Contributing to Telegram AI Agent Userbot

Thank you for your interest in contributing to **Telegram AI Agent Userbot**! We welcome bug reports, improvements, documentation updates, and feature requests.

---

## Development Workflow

### 1. Prerequisites
- Python 3.10, 3.11, or 3.12
- Git
- Recommended: A clean virtual environment (`venv`)

### 2. Setup
```bash
# Clone the repository
git clone https://github.com/your-username/telegram-agent-userbot.git
cd telegram-agent-userbot

# Create and activate virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install package with development dependencies
pip install -e ".[dev]"
```

### 3. Coding Guidelines
- **Type Annotations**: All new functions and methods must have complete type hints (`from __future__ import annotations`).
- **Code Style**: We use **Ruff** for linting and formatting. Run:
  ```bash
  ruff check .
  ruff format --check .
  ```
- **Docstrings & Comments**: Add concise, informative docstrings to all modules, classes, and public functions.
- **100% Offline Testing**: All tests must be 100% offline using `MockTelethonClient` and `MockLLMProvider`. No tests should require active Telegram accounts or live API keys.

### 4. Running Tests
```bash
# Run all tests
pytest -v

# Run with coverage
pytest --cov=. --cov-report=term-missing
```

### 5. Pull Request Process
1. Create a descriptive branch: `git checkout -b feature/my-feature` or `git checkout -b fix/issue-name`.
2. Commit your changes with clear messages following Conventional Commits (e.g. `feat: ...`, `fix: ...`, `docs: ...`, `test: ...`).
3. Ensure all 86+ tests pass and Ruff reports 0 lint errors.
4. Submit a Pull Request targeting `main`.
