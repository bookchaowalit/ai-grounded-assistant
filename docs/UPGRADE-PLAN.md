# Upgrade Plan

**Current state: 8/10** (pass 3: 7.5 -> 8) — small, well-bounded local
reference assistant with fail-closed corpus lineage, redaction, English+Thai
prompt-injection refusal, bounded rate limiter, CI and safety-gated
evaluation; still lexical-only retrieval (top-1) with a 5-record corpus and a
17-case golden set.

## Backlog

### P0
- (none open)

### P1
- Retrieval is top-1: answers that need two records cite only one. Raise
  `RETRIEVAL_TOP_K` with a per-answer source cap and add golden cases whose
  expected source set has two ids (needs an `expected_source_ids` field).

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

## Done in this pass (pass 3)
- Evaluation safety gates (`OUTCOME_GATES`): `refused` recall = 1.0 and
  `grounded` precision = 1.0 must hold independently of the overall pass
  rate (now a `required_pass_rate` parameter); a gate with no cases fails
  instead of passing vacuously. Output adds `pass_rate` and `gates`; the CLI
  exit code follows the combined status.
- Corpus 3 -> 5 records (refusal-before-retrieval; question redaction and
  hashed telemetry — both describe this app's own verified behaviour),
  landing + Bronze updated and manifest re-hashed (`validate` passes).
- Golden set 13 -> 17: two new grounded cases, one ambiguous retrieval case
  (question overlaps two records; the right one must win) and one fallback.
- Tests 35 -> 37 (relaxed-pass-rate regression where a guardrail stops
  refusing, vacuous/overclaiming gates). `make test/check/evaluate` pass;
  ruff 0.15.8 and 0.16.9 `--select F` clean.
- Unicode guardrail gaps: soft hyphen (U+00AD), combining grapheme joiner,
  Arabic letter mark and Mongolian vowel separator survive NFKC, so
  "ig­nore all previous instructions" was not flagged; they are now hidden
  characters. Role delimiters after a lone CR, CRLF or U+2028/U+2029
  ("hello system: ...") evaded the line-anchored pattern; line breaks
  are folded to "\n" for detection. Phone redaction missed numbers written
  with Thai (๐๘๑-...) or full-width digits. Retrieval `terms()` NFKC-folds so
  full-width Latin questions match. 4 tests in `UnicodeEdgeCaseTests`.
