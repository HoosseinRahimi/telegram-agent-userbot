"""
Application configuration management using Pydantic BaseSettings.
Loads environment variables from .env, validates required credentials,
parses compound list fields, and ensures secrets are masked in string representations.
"""

from __future__ import annotations

import functools
import json
import re
from typing import Any, List, Optional, Union

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Default sensitive keywords (English and Persian) for security monitoring
DEFAULT_SENSITIVE_KEYWORDS: list[str] = [
    "otp",
    "code",
    "password",
    "passcode",
    "secret",
    "token",
    "private key",
    "seed phrase",
    "recovery phrase",
    "bearer",
    "credit card",
    "debit card",
    "cvv",
    "cvv2",
    "card number",
    "کد تایید",
    "کد ورود",
    "رمز عبور",
    "پسورد",
    "رمز دوم",
    "رمز یکبار مصرف",
    "کلمات بازیابی",
    "شماره کارت",
    "شماره شبا",
    "شماره حساب",
]


def _parse_list_or_json(
    raw: Any,
    item_converter: Optional[callable] = None,
) -> list[Any]:
    """
    Parses a string or iterable into a typed list.
    Supports JSON list strings (e.g. '["a", "b"]') and comma-separated strings (e.g. 'a, b').
    """
    if raw is None:
        return []

    if isinstance(raw, str):
        cleaned = raw.strip()
        if not cleaned:
            return []
        try:
            parsed = json.loads(cleaned)
            if isinstance(parsed, list):
                items = parsed
            else:
                items = [cleaned]
        except (json.JSONDecodeError, ValueError):
            items = [item.strip() for item in cleaned.split(",") if item.strip()]
    elif isinstance(raw, (list, tuple, set)):
        items = list(raw)
    else:
        items = [raw]

    result = []
    for item in items:
        if item is None:
            continue
        if item_converter is not None:
            converted = item_converter(item)
            if converted is not None:
                result.append(converted)
        else:
            result.append(item)
    return result


def _normalize_entity_identifier(item: Any) -> Union[int, str]:
    """
    Converts a string or int into an int (if numeric) or string (stripped of '@').
    """
    if isinstance(item, int):
        return item
    text = str(item).strip()
    if re.match(r"^-?\d+$", text):
        return int(text)
    if text.startswith("@"):
        text = text[1:].strip()
    return text


def _normalize_keyword(item: Any) -> Optional[str]:
    """Converts a keyword item into a lowercased, stripped string."""
    text = str(item).strip().lower()
    return text if text else None


class Settings(BaseSettings):
    """
    Userbot configuration settings.
    Automatically reads environment variables from .env file or OS environment.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # Telegram MTProto Credentials
    telegram_api_id: int = Field(
        ...,
        description="Telegram API ID obtained from my.telegram.org",
    )
    telegram_api_hash: str = Field(
        ...,
        description="Telegram API Hash obtained from my.telegram.org",
    )
    telegram_session_name: str = Field(
        default="userbot_session",
        description="SQLite session file name",
    )
    telegram_session_string: Optional[str] = Field(
        default=None,
        description="Optional in-memory StringSession string",
    )

    # Modular LLM Provider Configuration
    llm_provider: str = Field(
        default="gemini",
        description="Active LLM provider: 'gemini', 'openai', or 'mock'",
    )
    gemini_api_key: Optional[str] = Field(
        default=None,
        description="Google Gemini API key",
    )
    gemini_model: str = Field(
        default="gemini-2.5-flash",
        description="Google Gemini model identifier",
    )
    openai_api_key: Optional[str] = Field(
        default=None,
        description="OpenAI API key or compatible endpoint token",
    )
    openai_model: str = Field(
        default="gpt-4o-mini",
        description="OpenAI model identifier",
    )
    openai_base_url: Optional[str] = Field(
        default=None,
        description="Optional base URL for OpenAI-compatible inference servers",
    )

    # Blacklist & Safety Filters
    blacklist_users: list[Union[int, str]] = Field(
        default_factory=list,
        description="List of user IDs or usernames to completely ignore",
    )
    sensitive_keywords: list[str] = Field(
        default_factory=lambda: list(DEFAULT_SENSITIVE_KEYWORDS),
        description="Keywords that trigger emergency security alert to Saved Messages",
    )

    # Channel Monitoring & Digest
    digest_channels: list[Union[int, str]] = Field(
        default_factory=list,
        description="Channels to monitor for analytical summaries",
    )
    digest_interval_minutes: int = Field(
        default=360,
        description="Frequency of scheduled periodic digest in minutes",
    )

    # Agent Persona
    persona_prompt_path: str = Field(
        default="persona_prompt.txt",
        description="Path to persona prompt file",
    )

    # --- Field Validators ---

    @field_validator("telegram_api_id", mode="before")
    @classmethod
    def validate_api_id(cls, v: Any) -> int:
        if v is None:
            raise ValueError("telegram_api_id cannot be None")
        try:
            val = int(v)
        except (ValueError, TypeError) as exc:
            raise ValueError(f"telegram_api_id must be a valid integer, got: {v!r}") from exc
        if val <= 0:
            raise ValueError(f"telegram_api_id must be a positive integer, got: {val}")
        return val

    @field_validator("telegram_api_hash", mode="before")
    @classmethod
    def validate_api_hash(cls, v: Any) -> str:
        if v is None:
            raise ValueError("telegram_api_hash cannot be None")
        val = str(v).strip()
        if not val:
            raise ValueError("telegram_api_hash cannot be empty")
        return val

    @field_validator("llm_provider", mode="before")
    @classmethod
    def validate_llm_provider(cls, v: Any) -> str:
        if not v:
            return "gemini"
        provider = str(v).strip().lower()
        allowed = {"gemini", "openai", "mock"}
        if provider not in allowed:
            raise ValueError(f"llm_provider must be one of {allowed}, got: {provider!r}")
        return provider

    @field_validator("blacklist_users", mode="before")
    @classmethod
    def validate_blacklist_users(cls, v: Any) -> list[Union[int, str]]:
        return _parse_list_or_json(v, item_converter=_normalize_entity_identifier)

    @field_validator("sensitive_keywords", mode="before")
    @classmethod
    def validate_sensitive_keywords(cls, v: Any) -> list[str]:
        if v is None:
            return list(DEFAULT_SENSITIVE_KEYWORDS)
        if isinstance(v, str) and not v.strip():
            return list(DEFAULT_SENSITIVE_KEYWORDS)
        parsed = _parse_list_or_json(v, item_converter=_normalize_keyword)
        return parsed if parsed else list(DEFAULT_SENSITIVE_KEYWORDS)

    @field_validator("digest_channels", mode="before")
    @classmethod
    def validate_digest_channels(cls, v: Any) -> list[Union[int, str]]:
        return _parse_list_or_json(v, item_converter=_normalize_entity_identifier)

    @field_validator("digest_interval_minutes", mode="before")
    @classmethod
    def validate_digest_interval(cls, v: Any) -> int:
        if v is None:
            return 360
        try:
            val = int(v)
        except (ValueError, TypeError) as exc:
            raise ValueError(f"digest_interval_minutes must be an integer, got: {v!r}") from exc
        if val <= 0:
            raise ValueError(f"digest_interval_minutes must be positive, got: {val}")
        return val

    # --- Masking Secrets in __repr__ and __str__ ---

    def __repr__(self) -> str:
        secret_keys = {
            "telegram_api_hash",
            "gemini_api_key",
            "openai_api_key",
            "telegram_session_string",
        }
        items = []
        for name in self.__class__.model_fields:
            val = getattr(self, name)
            if name in secret_keys and val:
                val_str = str(val)
                if len(val_str) > 6:
                    masked = f"'{val_str[:3]}...***'"
                else:
                    masked = "'***MASKED***'"
                items.append(f"{name}={masked}")
            else:
                items.append(f"{name}={val!r}")
        return f"Settings({', '.join(items)})"

    def __str__(self) -> str:
        return self.__repr__()


@functools.lru_cache()
def get_settings() -> Settings:
    """
    Returns a cached singleton instance of Settings.
    To reload after environment changes, call `get_settings.cache_clear()`.
    """
    return Settings()
