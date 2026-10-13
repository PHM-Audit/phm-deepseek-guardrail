# Adjudication trail — API contract suite (2026-10-12)

English summary of the internal adjudication record (原记录为中文，含数字通道证据).

## Defect candidate #1 — retracted

Candidate: "finish_reason returns an empty string instead of `tool_calls`
during tool calls" (phase 1).

Root cause: **local display-channel artifact**, not an API defect. A literal
string in our own terminal output was being filtered. Digital-channel
re-verification (character-code sequence of the API's `finish_reason` value,
length 10 = the protocol-correct enum; plus git-blob hash comparison of the
upstream chat-template file against the published Hugging Face oid) confirmed
the API returns the byte-correct value. Candidate formally retracted on
2026-10-12.

## Other initial non-OK verdicts — adjudicated

- phase1 temperature/param CONTRACT_VIOLATION x2: harness expectation errors
  (our cases encoded stricter behavior than documented). Harness fixed,
  cases re-verified OK.
- phase2 ANOMALY x1: documented known behavior — `reasoning_tokens` consuming
  the `max_tokens` budget yields empty content by design. Not filed.
- phase2 ANOMALY x1 (P6): contradictory parameter combination
  (thinking disabled + reasoning_effort=max) silently accepted — docs do not
  define this domain; logged as observation, not filed.
- phase3 ANOMALY x1: logged as observation; not filed.

## Process note

The candidate-to-retraction cycle (candidate raised → digital-channel
verification → retraction with evidence) is published deliberately: we
consider a visible self-correction trail more credible than a clean-looking
record.
