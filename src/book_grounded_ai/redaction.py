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

