# Evaluation datasets

P02 establishes versioned evaluation contracts without claiming that formal Gold exists.

- `candidates/` contains synthetic or human/LLM-assisted candidate records.
- `approved/` may contain only human-approved records linked to `reviews/review_log.jsonl`.
- `splits/` separates Pilot, Dev, and Test identifiers.
- `human_scores/pilot.jsonl` contains synthetic, candidate-only records that exercise the
  frozen human-review fields and complete Rubric dimensions; these are contract examples, not
  human-approved quality judgments.
- Each dataset version's `test.lock.json` controls whether its Test split may be used by the
  formal runner.
- A Run Manifest must bind the exact dataset `manifest.json` and selected Split file SHA-256
  before the Runner creates a checkpoint.
- Runtime outputs belong under `reports/evals/` or ignored `storage_eval/`, never here.

The owner-supplied PDF and DOCX remain local-only. Full local candidate content is written to
`storage_eval/p02_local_candidates/`; only safe metadata and hashes may be committed.
