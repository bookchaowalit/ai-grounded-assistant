"""Privacy-safe redaction for user questions before retrieval or telemetry."""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class RedactionResult:
    text: str
    applied: bool
    categories: tuple[str, ...]

    def as_dict(self) -> dict[str, object]:
        return {"applied": self.applied, "categories": list(self.categories)}


_PATTERNS: tuple[tuple[str, re.Pattern[str], str], ...] = (
    (
        "private-key",
        re.compile(
            r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?(?:-----END [A-Z ]*PRIVATE KEY-----|$)",
            re.DOTALL,
        ),
        "[REDACTED_PRIVATE_KEY]",
    ),
    (
        "provider-key",
        re.compile(
            r"\b(?:AKIA[0-9A-Z]{16}|gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,}"
            r"|sk-[A-Za-z0-9_-]{20,}|xox[abprs]-[A-Za-z0-9-]{10,})\b"
        ),
        "[REDACTED_SECRET]",
    ),
    (
        "jwt",
        re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}"),
        "[REDACTED_TOKEN]",
    ),
    (
        "bearer-token",
        re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]+", re.IGNORECASE),
        "[REDACTED_TOKEN]",
    ),
    (
        "api-key",
        re.compile(r"\b(?:api[_-]?key|access[_-]?token|secret|token)\s*[:=]\s*[^\s,;]+", re.IGNORECASE),
        "[REDACTED_SECRET]",
    ),
    (
        "email",
        re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE),
        "[REDACTED_EMAIL]",
    ),
    (
        "phone",
        # International (+CC ...) or Thai-style 0XX numbers with 9-10 digits.
        re.compile(r"(?<![\w+])(?:\+\d{1,3}[\s-]?|0)\d(?:[\s-]?\d){7,9}(?!\w)"),
        "[REDACTED_PHONE]",
    ),
)


def redact_question(text: str) -> RedactionResult:
    """Redact credential-shaped and direct contact values without logging matches."""

    redacted = text
    categories: list[str] = []
    for category, pattern, replacement in _PATTERNS:
        redacted, count = pattern.subn(replacement, redacted)
        if count and category not in categories:
            categories.append(category)
    return RedactionResult(redacted, bool(categories), tuple(categories))

