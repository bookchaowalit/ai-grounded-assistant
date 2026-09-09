"""Deterministic lexical retrieval for the provider-neutral local adapter."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Sequence


STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "be",
    "does",
    "for",
    "how",
    "in",
    "is",
    "of",
    "should",
    "the",
    "to",
    "what",
    "where",
    "which",
}


def terms(text: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-z0-9][a-z0-9_-]+", text.lower())
        if token not in STOPWORDS
    }


@dataclass(frozen=True)
class RetrievalMatch:
    record: dict[str, str]
    score: int
    matched_terms: tuple[str, ...]


def retrieve(records: Sequence[dict[str, str]], question: str, *, top_k: int, minimum_score: int) -> list[RetrievalMatch]:
    question_terms = terms(question)
    matches: list[RetrievalMatch] = []
    for record in records:
        record_terms = terms(f"{record['title']} {record['text']}")
        overlap = sorted(question_terms & record_terms)
        if len(overlap) >= minimum_score:
            matches.append(RetrievalMatch(dict(record), len(overlap), tuple(overlap)))
    matches.sort(key=lambda match: (-match.score, match.record["id"]))
    return matches[:top_k]

