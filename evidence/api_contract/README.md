# Evidence: API contract suite (51 cases, "documented promise vs actual behavior" method)

Method: each case encodes a promise from the official DeepSeek API documentation
(parameter semantics, enum values, streaming events, tool-call contract) and
asserts the live API response against it. Verdicts: OK / CONTRACT_VIOLATION /
ANOMALY.

## Composition (raw records in this directory, unmodified)

| File | Phase | Records | Initial verdicts |
|---|---|---|---|
| phase1_results.jsonl | protocol contract (params, enums) | 15 | 13 OK, 2 CONTRACT_VIOLATION |
| phase2_results.jsonl | tool calling | 32 | 30 OK, 2 ANOMALY |
| phase3_results.jsonl | streaming SSE | 8 | 7 OK, 1 ANOMALY |
| phase4_results.json | adversarial injection (chat-template hardening) | 5 | 5 survived_all=true |

## Adjudication (final disposition: zero confirmed defects)

The 5 initial non-OK verdicts were adjudicated on 2026-10-12:

- 2 CONTRACT_VIOLATION (phase 1, temperature/param cases): harness expectation
  errors (our test encoded stricter behavior than the docs promise). Harness
  corrected; cases re-verified OK.
- 2 ANOMALY: one retracted as a local display-channel artifact (a literal
  string was filtered in our own terminal output; verified via character-code
  sequence and git-blob hash of upstream template files — the API value was
  byte-correct); one reclassified as a documented known behavior
  (reasoning_tokens consuming max_tokens budget), not filed.
- 1 ANOMALY (phase 3): reclassified as an observation item; docs do not define
  the parameter domain; not filed.

Full adjudication trail: `adjudication.md`. Final disposition after digital-
channel re-verification: **zero confirmed API defects** in this suite.

## Caveats

- Self-built case set ("docs promise vs behavior" method); does not exhaust
  every documented promise. "No confirmed defects" applies to this suite only.
- Single run per case; LLM API responses are nondeterministic outside the
  asserted contract fields.
- harness.py is sanitized for publication (API key read from
  `DEEPSEEK_API_KEY` env; absolute paths removed).
