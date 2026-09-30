# Upgrade Plan

**Current state: 7.5/10** — small, well-bounded local reference assistant with
fail-closed corpus lineage, redaction, English+Thai prompt-injection refusal,
bounded rate limiter and CI; still lexical-only retrieval with a 3-record
corpus and a 13-case golden set.

## Backlog

### P0
- (none open)

### P1
- Grow the corpus beyond 3 records (with manifest re-hash) so the golden set
  can include multi-source and ambiguous-retrieval cases.
- Add an evaluation gate on per-outcome recall (e.g. `refused` recall must be
  1.0 even if the overall threshold is later relaxed).

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

## Done in this pass (pass 2)
- Guardrails: Thai-language instruction-override and prompt-exfiltration
  patterns (compiled on NFKC text so SARA AM matches), English override now
  covers "guidance/directions/directives"; categories are de-duplicated.
- `_RateLimiter`: idle clients evicted on a periodic sweep, tracked-client
  table capped (`max_clients`, new ids fail closed when full), injectable
  clock for deterministic tests.
- Golden set 5 → 13 cases (near-miss benign "ignore stale rows", paraphrased
  and Thai injections, extra fallback); `make evaluate` now reports
  per-outcome precision/recall. Tests 30 → 35 (+ more subtests).
