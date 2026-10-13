# Evidence: hallucination observation, n=50 same-question paired run

Caliber (stated conservatively):

- n=50 questions, military PUBLIC-DOMAIN facts (SIPRI / open budget data etc.);
  same model, same version, same prompts, paired runs with and without the
  deterministic guard layer.
- Pure-hallucination count: without guard 24/50 (48.0%), with guard 12/50
  (24.0%). Partial-hallucination (mixed) records: 7 with guard.
- No significance test performed; small sample; the difference may reflect
  sampling variance. This is a downstream-usage observation, NOT a claim about
  the model itself.
- Judgment records (per-question verdicts and full model responses) are in
  `testA_results.json` — raw, unmodified.

## Reproduction

`testA_harness.py` is the sanitized publication copy of the runner (API key
via `DEEPSEEK_API_KEY` env). Question set and ground-truth sources are public
(SIPRI etc.).
