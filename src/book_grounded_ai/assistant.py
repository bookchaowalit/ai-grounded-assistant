"""Grounded answer orchestration with deterministic fallback and safe telemetry."""

from __future__ import annotations

import time
from typing import Any

from .config import (
    ANSWER_SCHEMA_VERSION,
    APP_NAME,
    CORPUS_SCHEMA_VERSION,
    LATENCY_TARGET_MS,
    MAX_ANSWER_CHARS,
    MAX_QUESTION_CHARS,
    MODEL_ADAPTER,
    RETRIEVAL_MIN_SCORE,
    RETRIEVAL_TOP_K,
)
from .guardrails import detect_prompt_injection
from .redaction import redact_question
from .retrieval import retrieve
from .schema import validate_question
from .store import Corpus
from .telemetry import SafeTelemetrySink


class GroundedAssistant:
    """Answer only from approved local context; no external action or provider call."""

    def __init__(self, corpus: Corpus, *, telemetry: SafeTelemetrySink | None = None) -> None:
        self.corpus = corpus
        self.telemetry = telemetry or SafeTelemetrySink()

    def metadata(self) -> dict[str, Any]:
        return {
            "assistant": APP_NAME,
            "api_mode": "provider-neutral-local-reference",
            "adapter": MODEL_ADAPTER,
            "answer_schema_version": ANSWER_SCHEMA_VERSION,
            "corpus_schema_version": CORPUS_SCHEMA_VERSION,
            "dataset": self.corpus.dataset,
            "records_count": len(self.corpus.records),
            "context_budget": {"max_question_chars": MAX_QUESTION_CHARS, "top_k": RETRIEVAL_TOP_K},
            "output_budget": {"max_answer_chars": MAX_ANSWER_CHARS},
            "latency_target_ms": LATENCY_TARGET_MS,
            "fallback_policy": "return insufficient-context when lexical evidence is below threshold",
            "injection_policy": "refuse questions with instruction-override, prompt-exfiltration, role-hijack or role-delimiter content; reject corpus records containing them",
            "external_actions": False,
            "data_status": "valid",
            "lineage": self.corpus.lineage.as_dict(),
        }

    def answer(self, question: str) -> dict[str, Any]:
        started = time.perf_counter()
        normalized = validate_question(question)
        redaction = redact_question(normalized)
        if not redaction.text.strip():
            raise ValueError("question contains no retrievable text after redaction")
        injection_categories = detect_prompt_injection(normalized)
        guardrail = {"prompt_injection": bool(injection_categories), "categories": list(injection_categories)}
        matches = (
            []
            if injection_categories
            else retrieve(
                self.corpus.records,
                redaction.text,
                top_k=RETRIEVAL_TOP_K,
                minimum_score=RETRIEVAL_MIN_SCORE,
            )
        )
        if injection_categories:
            # Refuse instead of answering: the question tries to change the
            # assistant's instructions. The matched text is never echoed.
            answer = (
                "I can only answer questions from approved context and cannot follow "
                "instructions embedded in a question."
            )
            source_ids = ()
            outcome = "refused"
            payload = {
                "assistant": APP_NAME,
                "answer_schema_version": ANSWER_SCHEMA_VERSION,
                "adapter": MODEL_ADAPTER,
                "data_status": "refused",
                "answer": answer,
                "uncertainty": "high",
                "fallback": True,
                "fallback_reason": "question contains instruction-override or prompt-exfiltration content",
                "grounding": {"source_ids": [], "citations": [], "evidence_score": 0, "matched_terms": []},
                "redaction": redaction.as_dict(),
            }
        elif matches:
            match = matches[0]
            record = match.record
            answer = f"{record['title']}: {record['text']}"
            answer = answer[:MAX_ANSWER_CHARS]
            source_ids = (record["id"],)
            citations = [{"id": record["id"], "title": record["title"], "source_url": record["source_url"]}]
            outcome = "grounded"
            payload: dict[str, Any] = {
                "assistant": APP_NAME,
                "answer_schema_version": ANSWER_SCHEMA_VERSION,
                "adapter": MODEL_ADAPTER,
                "data_status": "grounded",
                "answer": answer,
                "uncertainty": "low",
                "fallback": False,
                "grounding": {
                    "source_ids": list(source_ids),
                    "citations": citations,
                    "evidence_score": match.score,
                    "matched_terms": list(match.matched_terms),
                },
                "redaction": redaction.as_dict(),
            }
        else:
            answer = "I do not have enough approved context to answer that question."
            source_ids = ()
            outcome = "fallback"
            payload = {
                "assistant": APP_NAME,
                "answer_schema_version": ANSWER_SCHEMA_VERSION,
                "adapter": MODEL_ADAPTER,
                "data_status": "insufficient-context",
                "answer": answer,
                "uncertainty": "high",
                "fallback": True,
                "fallback_reason": "no approved source met the retrieval threshold",
                "grounding": {"source_ids": [], "citations": [], "evidence_score": 0, "matched_terms": []},
                "redaction": redaction.as_dict(),
            }
        latency_ms = int((time.perf_counter() - started) * 1000)
        event = self.telemetry.record(
            redacted_question=redaction.text,
            answer=answer,
            redaction_applied=redaction.applied,
            redaction_categories=redaction.categories,
            source_ids=source_ids,
            outcome=outcome,
            latency_ms=latency_ms,
        )
        payload["guardrail"] = guardrail
        payload["telemetry"] = {"event_id": event.event_id, "raw_payload_persisted": False}
        return payload
