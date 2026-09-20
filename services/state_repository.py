"""
Persistent & Atomic Runtime State Repository.

Persists dynamic runtime configurations across userbot restarts:
- /pause and /resume status and expiry
- Active LLM provider (/mode)
- Blacklist and allowlist entries
- Last manual human activity timestamps
Uses atomic file writing (write to temp file then replace) to prevent corruption.
"""

from __future__ import annotations

import json
import logging
import os
import re
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def normalize_entry(entry: Any) -> int | str:
    """Normalizes username (strips leading @, lowercases) or converts numeric string to int."""
    if isinstance(entry, int):
        return entry
    text = str(entry).strip()
    if re.match(r"^-?\d+$", text):
        return int(text)
    if text.startswith("@"):
        text = text[1:].strip()
    return text.lower()


class StateRepository:
    """
    Manages atomic persistence of runtime state in a JSON file.
    """

    def __init__(self, state_file_path: str = "data/bot_state.json") -> None:
        self.path = Path(state_file_path)
        self._state: dict[str, Any] = {
            "version": 1,
            "paused": False,
            "paused_until": None,
            "llm_provider": None,
            "blacklist": [],
            "allowlist": [],
            "last_manual_activity": {},
        }
        self._load()

    def _load(self) -> None:
        """Loads state from disk if file exists."""
        if self.path.exists() and self.path.is_file():
            try:
                content = self.path.read_text(encoding="utf-8")
                loaded = json.loads(content)
                if isinstance(loaded, dict):
                    self._state.update(loaded)
                    logger.info(f"[StateRepository] Loaded runtime state from {self.path}")
            except Exception as exc:
                logger.warning(f"[StateRepository] Could not parse state file {self.path}: {exc}. Starting fresh.")

    def _save(self) -> None:
        """Atomically saves state to disk."""
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temp_fd, temp_path = tempfile.mkstemp(dir=self.path.parent, prefix="state_", suffix=".tmp")
            with os.fdopen(temp_fd, "w", encoding="utf-8") as f:
                json.dump(self._state, f, ensure_ascii=False, indent=2)
            os.replace(temp_path, self.path)
        except Exception as exc:
            logger.error(f"[StateRepository] Failed to persist state to {self.path}: {exc}")

    # --- Pause State ---

    def is_paused(self) -> bool:
        if not self._state.get("paused", False):
            return False
        until_str = self._state.get("paused_until")
        if until_str:
            try:
                until_dt = datetime.fromisoformat(until_str)
                if datetime.now() >= until_dt:
                    self.set_paused(False)
                    return False
            except Exception:
                pass
        return True

    def set_paused(self, paused: bool, until: datetime | None = None) -> None:
        self._state["paused"] = paused
        self._state["paused_until"] = until.isoformat() if until else None
        self._save()

    # --- LLM Mode ---

    def get_llm_provider(self) -> str | None:
        return self._state.get("llm_provider")

    def set_llm_provider(self, provider: str) -> None:
        self._state["llm_provider"] = provider.lower().strip()
        self._save()

    # --- Blacklist ---

    def get_blacklist(self) -> list[int | str]:
        return list(self._state.get("blacklist", []))

    def add_to_blacklist(self, entry: int | str) -> None:
        norm = normalize_entry(entry)
        current = self.get_blacklist()
        if norm not in current:
            current.append(norm)
            self._state["blacklist"] = current
            self._save()

    def remove_from_blacklist(self, entry: int | str) -> bool:
        norm = normalize_entry(entry)
        current = self.get_blacklist()
        if norm in current:
            current.remove(norm)
            self._state["blacklist"] = current
            self._save()
            return True
        return False

    # --- Allowlist ---

    def get_allowlist(self) -> list[int | str]:
        return list(self._state.get("allowlist", []))

    def add_to_allowlist(self, entry: int | str) -> None:
        norm = normalize_entry(entry)
        current = self.get_allowlist()
        if norm not in current:
            current.append(norm)
            self._state["allowlist"] = current
            self._save()
