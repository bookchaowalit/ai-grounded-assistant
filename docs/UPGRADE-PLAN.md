# Upgrade Plan

**Current state: 7/10** — small, well-bounded local reference assistant with
fail-closed corpus lineage, redaction, prompt-injection refusal and CI; still
lexical-only retrieval with a 3-record corpus and a 5-case golden set.

## Backlog

### P0
- (none open)

### P1
- Grow the golden set: paraphrased and Thai-language injection attempts,
  near-miss benign questions ("ignore stale rows?"), and per-category
  precision/recall in `make evaluate` output.
- `_RateLimiter._events` keeps one list per client forever; evict idle
  clients so a long-running server does not grow unbounded.

### P2
- Retrieval ignores Thai text (`terms()` only matches `[a-z0-9]`); add a
  Thai tokenizer or character n-grams before adding Thai corpus records.
- Persist telemetry (hash-only) to a local JSONL sink with retention.
- Type-check with `mypy --strict src` in CI.

## Done in this pass (2026-09-30)
- New `guardrails.py`: deterministic prompt-injection detection
  (instruction-override, prompt-exfiltration, role-hijack, role-delimiter)
  on an NFKC-folded, zero-width-stripped copy of the text.
- Questions with injection are refused (`data_status: "refused"`, no
  retrieval, no echo); every answer carries a `guardrail` block; metadata
  advertises `injection_policy`.
- Corpus records with instruction-like content or hidden characters fail
  closed at load (`SCHEMA013` / `SCHEMA014`) — indirect injection defence.
- Input validation: zero-width/bidi characters stripped; all C0/C1 control
  characters (not only NUL) rejected with `INPUT004`.
- Redaction adds provider keys (AWS/GitHub/`sk-`/Slack), JWT, PEM private
  keys and phone numbers.
- Bug: a non-ASCII `Authorization` header raised `TypeError` in
  `hmac.compare_digest` (request crashed instead of 401); now compares bytes.
- Evaluation supports `refused`; golden set 3 → 5 cases; tests 13 → 30.
- CI workflow: ruff (pyflakes), `make test`, `make check`, `make evaluate`.
