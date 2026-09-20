"""
Sensitive Keyword & Security Detector Filter.

Scans incoming message text for confidential keywords (OTP, passwords, payment info,
credentials, seed phrases in English & Persian).
Upon detection, halts auto-replies and flags the message as a security alert.
Includes comprehensive Persian & Arabic Unicode normalization (ZWNJ, Arabic kaf/yeh, harakat).
"""

from __future__ import annotations

import re
from typing import Iterable, List, Optional
from .base import BaseFilter, FilterContext, FilterResult


def normalize_text(text: str) -> str:
    """
    Normalizes text for security keyword detection:
    - Lowercases English letters
    - Replaces Arabic kaf (ك) with Persian kaf (ک)
    - Replaces Arabic yeh (ي, ى) with Persian yeh (ی)
    - Replaces ZWNJ (\u200c) and zero-width spaces (\u200b, \ufeff) with a standard space
    - Strips Arabic/Persian diacritics/harakat (\u064b through \u065f, \u0670)
    - Collapses multiple whitespaces into a single space
    """
    if not text:
        return ""

    text = text.lower()
    # Arabic to Persian character mapping
    char_map = {
        "ك": "ک",
        "ي": "ی",
        "ى": "ی",
        "ة": "ه",
        "ؤ": "و",
        "إ": "ا",
        "أ": "ا",
        "آ": "ا",
        "\u200c": " ",  # Zero-width non-joiner (ZWNJ / نیم‌فاصله)
        "\u200b": " ",  # Zero-width space
        "\ufeff": " ",  # Zero-width no-break space (BOM)
    }
    for src, dst in char_map.items():
        text = text.replace(src, dst)

    # Remove Arabic / Persian diacritics (harakat / tanween)
    text = re.sub(r"[\u064B-\u065F\u0670]", "", text)

    # Collapse multiple whitespaces into a single space
    text = " ".join(text.split())
    return text


class SensitiveFilter(BaseFilter):
    """
    Detects sensitive, financial, or authentication credentials in message content.
    """

    def __init__(self, sensitive_keywords: Optional[Iterable[str]] = None) -> None:
        self.keywords: List[str] = []
        if sensitive_keywords:
            self.keywords = [normalize_text(k) for k in sensitive_keywords if k and k.strip()]

    async def check(self, context: FilterContext) -> FilterResult:
        normalized_text = normalize_text(context.text or "")
        if not normalized_text:
            return FilterResult.allow()

        for kw in self.keywords:
            if not kw:
                continue
            # Use regex word boundaries for short ascii words (<=4 chars) to avoid false positives like 'code' in 'decode'
            if len(kw) <= 4 and kw.isalnum() and kw.isascii():
                pattern = rf"\b{re.escape(kw)}\b"
                if re.search(pattern, normalized_text):
                    return FilterResult.block(
                        reason=f"Message contains sensitive security keyword: '{kw}'",
                        is_security_alert=True,
                        matched_keyword=kw,
                    )
            else:
                # Substring match for longer phrases or Persian text
                if kw in normalized_text:
                    return FilterResult.block(
                        reason=f"Message contains sensitive security keyword: '{kw}'",
                        is_security_alert=True,
                        matched_keyword=kw,
                    )

        return FilterResult.allow()
