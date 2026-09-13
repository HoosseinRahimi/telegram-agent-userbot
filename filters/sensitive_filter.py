"""
Sensitive Keyword & Security Detector Filter.

Scans incoming message text for confidential keywords (OTP, passwords, payment info,
credentials, seed phrases in English & Persian).
Upon detection, halts auto-replies and flags the message as a security alert.
"""

from __future__ import annotations

import re
from typing import Iterable, List, Optional
from .base import BaseFilter, FilterContext, FilterResult


class SensitiveFilter(BaseFilter):
    """
    Detects sensitive, financial, or authentication credentials in message content.
    """

    def __init__(self, sensitive_keywords: Optional[Iterable[str]] = None) -> None:
        self.keywords: List[str] = []
        if sensitive_keywords:
            self.keywords = [k.strip().lower() for k in sensitive_keywords if k and k.strip()]

    async def check(self, context: FilterContext) -> FilterResult:
        text = (context.text or "").strip().lower()
        if not text:
            return FilterResult.allow()

        for kw in self.keywords:
            if not kw:
                continue
            # Use regex word boundaries for short ascii words (<=4 chars) to avoid false positives like 'code' in 'decode'
            if len(kw) <= 4 and kw.isalnum() and kw.isascii():
                pattern = rf"\b{re.escape(kw)}\b"
                if re.search(pattern, text):
                    return FilterResult.block(
                        reason=f"Message contains sensitive security keyword: '{kw}'",
                        is_security_alert=True,
                        matched_keyword=kw,
                    )
            else:
                # Substring match for longer phrases or Persian text
                if kw in text:
                    return FilterResult.block(
                        reason=f"Message contains sensitive security keyword: '{kw}'",
                        is_security_alert=True,
                        matched_keyword=kw,
                    )

        return FilterResult.allow()
