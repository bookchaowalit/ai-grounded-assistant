"""Prompt-injection and hidden-character guardrails for questions and corpus text.

The baseline adapter is extractive, so an injected instruction cannot change
what it does. The guard still runs on every question and every corpus record
because the same contract must hold once a generative provider adapter is
plugged in: user input and retrieved context are data, never instructions.

Detection is deterministic and pattern-based. It is a defence-in-depth signal,
not a proof of safety; the refusal path never echoes the matched text.
"""

from __future__ import annotations

import re
import unicodedata

# Zero-width, word-joiner, BOM and bidi override/isolate characters. They are
# invisible in most UIs and are a common way to smuggle or hide instructions.
_HIDDEN_CHARS = re.compile("[​-‏‪-‮⁠-⁤⁦-⁩﻿]")

# C0/C1 control characters other than tab, newline and carriage return.
_CONTROL_CHARS = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]")

_INJECTION_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "instruction-override",
        re.compile(
            r"\b(?:ignore|disregard|forget|override|bypass|skip)\b[^.?!\n]{0,40}?"
            r"\b(?:previous|prior|above|earlier|preceding|all|any|your|the|system|developer)\b[^.?!\n]{0,20}?"
            r"\b(?:instructions?|prompts?|rules?|guidelines?|polic(?:y|ies)|context|guardrails?)\b"
        ),
    ),
    (
        "prompt-exfiltration",
        re.compile(
            r"\b(?:reveal|show|print|repeat|output|display|leak|dump|tell me|what (?:is|are))\b[^.?!\n]{0,30}?"
            r"\b(?:system|hidden|initial|original|developer|secret)\s+(?:prompt|instructions?|message|rules)\b"
        ),
    ),
    (
        "role-hijack",
        re.compile(
            r"\b(?:you are now|from now on,? you|pretend (?:to be|you are)|act as (?:an? )?(?:unrestricted|jailbroken|dan)\b"
            r"|developer mode|jailbreak|do anything now)"
        ),
    ),
    (
        "role-delimiter",
        re.compile(
            r"(?:<\|(?:im_start|im_end|system|endoftext)\|>|\[/?inst\]|<</?sys>>|</?system>"
            r"|^\s*#{2,}\s*(?:system|instruction)s?\b|^\s*(?:system|assistant)\s*:)",
            re.MULTILINE,
        ),
    ),
)


def strip_hidden_characters(text: str) -> tuple[str, bool]:
    """Remove invisible formatting characters; report whether any were present."""

    cleaned, count = _HIDDEN_CHARS.subn("", text)
    return cleaned, bool(count)


def has_control_characters(text: str) -> bool:
    return bool(_CONTROL_CHARS.search(text))


def _canonical(text: str) -> str:
    # NFKC folds full-width / compatibility look-alikes ("ｉｇｎｏｒｅ") for
    # detection only; the caller's text is never rewritten with NFKC because
    # that would alter Thai (SARA AM) and other scripts used for retrieval.
    folded = unicodedata.normalize("NFKC", _HIDDEN_CHARS.sub("", text)).casefold()
    return re.sub(r"[ \t]+", " ", folded)


def detect_prompt_injection(text: str) -> tuple[str, ...]:
    """Return the injection categories found in ``text`` (empty when clean)."""

    canonical = _canonical(text)
    return tuple(category for category, pattern in _INJECTION_PATTERNS if pattern.search(canonical))
