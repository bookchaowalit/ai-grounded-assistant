"""In-memory telemetry that records hashes and outcomes, never raw prompts."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from .config import MODEL_ADAPTER


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class SafeTelemetryEvent:
    event_id: str
    event_type: str
    redacted_question_sha256: str
    answer_sha256: str
    redaction_applied: bool
    redaction_categories: tuple[str, ...]
    source_ids: tuple[str, ...]
    outcome: str
    latency_ms: int
    adapter: str = MODEL_ADAPTER

    def as_dict(self) -> dict[str, object]:
        return {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "redacted_question_sha256": self.redacted_question_sha256,
            "answer_sha256": self.answer_sha256,
            "redaction_applied": self.redaction_applied,
            "redaction_categories": list(self.redaction_categories),
            "source_ids": list(self.source_ids),
            "outcome": self.outcome,
            "latency_ms": self.latency_ms,
            "adapter": self.adapter,
        }


class SafeTelemetrySink:
    """Small local sink for tests and inspection; it intentionally does not persist text."""

    def __init__(self) -> None:
        self.events: list[SafeTelemetryEvent] = []

    def record(
        self,
        *,
        redacted_question: str,
        answer: str,
        redaction_applied: bool,
        redaction_categories: tuple[str, ...],
        source_ids: tuple[str, ...],
        outcome: str,
        latency_ms: int,
    ) -> SafeTelemetryEvent:
        question_hash = _digest(redacted_question)
        answer_hash = _digest(answer)
        event_id = _digest("|".join((question_hash, outcome, ",".join(source_ids))))[:24]
        event = SafeTelemetryEvent(
            event_id=event_id,
            event_type="assistant.answer",
            redacted_question_sha256=question_hash,
            answer_sha256=answer_hash,
            redaction_applied=redaction_applied,
            redaction_categories=redaction_categories,
            source_ids=source_ids,
            outcome=outcome,
            latency_ms=max(0, latency_ms),
        )
        self.events.append(event)
        return event

