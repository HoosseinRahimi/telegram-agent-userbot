"""
Sensitive Keyword & Security Detector Filter.

Scans incoming message text for confidential keywords (OTP, passwords, payment info,
credentials, seed phrases in English & Persian).
Upon detection, halts auto-replies and flags the message as a security alert.
Includes comprehensive Persian & Arabic Unicode normalization (ZWNJ, Arabic kaf/yeh, harakat).
"""

from __future__ import annotations

import re
from collections.abc import Iterable

from .base import BaseFilter, FilterContext, FilterResult


def convert_eastern_digits_to_ascii(text: str) -> str:
    """Converts Persian (۰-۹) and Arabic-Indic (٠-٩) numerals to ASCII digits."""
    if not text:
        return ""
    persian_digits = "۰۱۲۳۴۵۶۷۸۹"
    arabic_digits = "٠١٢٣٤٥٦٧٨٩"
    for i in range(10):
        text = text.replace(persian_digits[i], str(i)).replace(arabic_digits[i], str(i))
    return text


def luhn_checksum(card_number: str) -> bool:
    """
    Validates a number using the Luhn algorithm (mod 10).
    Accepts raw digits string.
    """
    digits = [int(d) for d in card_number if d.isdigit()]
    if len(digits) < 2:
        return False

    total = 0
    reverse_digits = digits[::-1]
    for i, digit in enumerate(reverse_digits):
        if i % 2 == 1:
            doubled = digit * 2
            total += doubled - 9 if doubled > 9 else doubled
        else:
            total += digit
    return total % 10 == 0


def normalize_text(text: str) -> str:
    """
    Normalizes text for security keyword detection:
    - Converts Persian and Arabic digits to ASCII
    - Lowercases English letters
    - Replaces Arabic kaf (ك) with Persian kaf (ک)
    - Replaces Arabic yeh (ي, ى) with Persian yeh (ی)
    - Replaces ZWNJ (\u200c) and zero-width spaces (\u200b, \ufeff) with a standard space
    - Strips Arabic/Persian diacritics/harakat (\u064b through \u065f, \u0670)
    - Collapses multiple whitespaces into a single space
    """
    if not text:
        return ""

    text = convert_eastern_digits_to_ascii(text)
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


# Structural Regexes for sensitive content detection
RE_OTP = re.compile(
    r"(?i)(?:code|otp|passcode|رمز|کد|تایید|ورود|اعتبارسنجی)[^:\n\d]{0,20}[:=]?\s*(\d{4,8})\b"
)
RE_PRIVATE_KEY = re.compile(
    r"-----BEGIN [A-Z ]+ PRIVATE KEY-----"
)
RE_SECRET_TOKEN = re.compile(
    r"\b(?:sk-[a-zA-Z0-9]{20,}|AIzaSy[a-zA-Z0-9_-]{33})\b"
)
RE_CARD_CANDIDATE = re.compile(
    r"\b(?:\d[ -]*?){13,19}\b"
)


class SensitiveFilter(BaseFilter):
    """
    Detects sensitive, financial, or authentication credentials in message content.
    Combines configured keyword matching with structural detection (Luhn credit cards,
    OTP codes, private keys, API tokens).
    """

    def __init__(self, sensitive_keywords: Iterable[str] | None = None) -> None:
        self.keywords: list[str] = []
        if sensitive_keywords:
            self.keywords = [normalize_text(k) for k in sensitive_keywords if k and k.strip()]

    async def check(self, context: FilterContext) -> FilterResult:
        raw_text = context.text or ""
        normalized_text = normalize_text(raw_text)
        if not normalized_text:
            return FilterResult.allow()

        # 1. Configured Keyword Matching
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

        # 2. Structural Check: Secret tokens & Private Keys
        if RE_PRIVATE_KEY.search(raw_text):
            return FilterResult.block(
                reason="Message contains private cryptographic key",
                is_security_alert=True,
                matched_keyword="[PRIVATE_KEY]",
            )

        if RE_SECRET_TOKEN.search(raw_text):
            return FilterResult.block(
                reason="Message contains secret API token",
                is_security_alert=True,
                matched_keyword="[API_TOKEN]",
            )

        # 3. Structural Check: Credit / Debit Cards with Luhn Check
        for match in RE_CARD_CANDIDATE.finditer(normalized_text):
            candidate_digits = re.sub(r"\D", "", match.group(0))
            if 13 <= len(candidate_digits) <= 19 and luhn_checksum(candidate_digits):
                return FilterResult.block(
                    reason="Message contains valid credit or debit card number (Luhn verified)",
                    is_security_alert=True,
                    matched_keyword="[CREDIT_CARD]",
                )

        # 4. Structural Check: OTP / Verification codes
        otp_match = RE_OTP.search(normalized_text)
        if otp_match:
            code = otp_match.group(1)
            return FilterResult.block(
                reason=f"Message contains one-time password / OTP code: {code}",
                is_security_alert=True,
                matched_keyword="[OTP]",
            )

        return FilterResult.allow()
