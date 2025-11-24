"""Validators and normalizers for tax ids and address text.

This module provides:
- normalize_digits: keep only digits
- validate_cnpj: raises ValidationError if checksum is invalid
- normalize_text_unaccent: trims, collapses spaces, lowercases for indexing; strips accents if available
"""
from __future__ import annotations

import re
import unicodedata
from typing import Optional

from django.core.exceptions import ValidationError


_DIGITS_RE = re.compile(r"\D+")
_SPACE_RE = re.compile(r"\s+")


def normalize_digits(text: Optional[str]) -> str:
    """Return only the digits from the given text (or empty string if None)."""
    if not text:
        return ""
    return _DIGITS_RE.sub("", str(text))


def _cnpj_calculate_digit(numbers: str) -> int:
    """Calculate CNPJ check digit from first 12 or 13 digits."""
    weights_first = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    weights_second = [6] + weights_first
    if len(numbers) == 12:
        weights = weights_first
    elif len(numbers) == 13:
        weights = weights_second
    else:
        raise ValueError("CNPJ must have 12 or 13 base digits for digit calc")
    total = sum(int(n) * w for n, w in zip(numbers, weights))
    remainder = total % 11
    return 0 if remainder < 2 else 11 - remainder


def validate_cnpj(text_digits: str) -> None:
    """Validate a CNPJ string (digits-only) by checksum.

    Raises ValidationError if invalid.
    """
    if not text_digits or len(text_digits) != 14 or len(set(text_digits)) == 1:
        raise ValidationError("Invalid CNPJ")
    base = text_digits[:12]
    d1 = _cnpj_calculate_digit(base)
    d2 = _cnpj_calculate_digit(base + str(d1))
    if text_digits[-2:] != f"{d1}{d2}":
        raise ValidationError("Invalid CNPJ checksum")


def normalize_text_unaccent(s: Optional[str]) -> str:
    """Normalize text for indexing: strip, collapse spaces, remove accents, lower-case.

    We do not enforce lower-case in stored values except for normalization purposes
    inside functional unique indexes, but returning a clean form helps consistency.
    """
    if s is None:
        return ""
    s = str(s).strip()
    s = _SPACE_RE.sub(" ", s)
    # Remove accents
    nfkd_form = unicodedata.normalize('NFKD', s)
    s = "".join([c for c in nfkd_form if not unicodedata.combining(c)])
    return s
