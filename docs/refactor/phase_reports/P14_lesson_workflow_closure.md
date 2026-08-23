# P14 Closure Report: Model Gateway and CP-B0 Comparison

## Outcome

The offline implementation is complete. P14 now routes Blueprint, Session, and future
targeted repairs through the explicit Model Gateway profiles `planner_main`,
`generator_main`, and `content_repair_main`. Deterministic generation remains a Contract
Fake only. P14 loads the approved CourseRAG KnowledgePoint Snapshot directly, so its KP
extractor count is zero.

The additive export and writeback endpoints enforce artifact-version hashes, separate
approval scopes, idempotent side effects, and exactly one `$.sessions[n]` writeback path.
Whole-lesson, collection, stale-version, and out-of-scope Evidence writes are rejected
before the CourseRAG Port is called. Legacy Lesson endpoints remain unchanged.

## Provider preflight and run

The preflight estimate was 42,010 input tokens and a maximum-output upper bound of 131,072
tokens. Using the configured DeepSeek pricing, the estimated upper bound was CNY 0.3042,
below the approved CNY 0.50 cap.

The one authorized real run used `deepseek-v4-flash` through the configured
OpenAI-compatible endpoint, with Evaluation mode and deterministic fallback disabled. The
provider read timed out; the run stopped fail-closed and did not switch models or use a
deterministic answer. Failure evidence is stored at
`storage_eval/p14_closure/provider_run_failure.json`. No additional provider call is made
by this implementation without new authorization.

The provider dashboard later confirmed 24 requests, 186,237 billed tokens and CNY 0.28 of
consumption. The local failure artifact lacked complete Usage because the client abandoned the
responses at a forced 45-second read timeout; a read timeout does not prove that provider-side
generation stopped. The run also had no per-request durable response checkpoint, so successful
responses before the terminal failure could not be recovered locally.

The approved code-only repair now:

- honors the selected logical Profile timeout instead of replacing it with the global timeout;
- uses a P14-only profile with 180-second Planner/Repair and 240-second Generator read timeouts;
- never retries a read timeout, parse failure or other ambiguous post-send failure;
- permits one retry only for a proven `httpx.ConnectError`/`ConnectTimeout` before a response;
- marks timed-out attempts `unknown_pending_reconciliation` instead of treating missing Usage as
  zero cost;
- atomically persists every successful structured response before the workflow advances, and
  requires explicit `--resume` to reuse an exact request identity without another Provider call;
- records physical Provider request count separately from logical invocation and cache-hit count.

No Provider call was made while implementing or validating this repair. The offline preflight
remains 42,010 estimated input tokens, 131,072 maximum output tokens and CNY 0.3042 upper bound.
Because the failed run already consumed CNY 0.28, only CNY 0.22 remains under the old nominal cap;
that old authorization is not reused automatically.

The Course Owner separately authorized one Blueprint-only smoke with a CNY 0.03 hard cap. The
previously failing `p14-lesson-02-perceptron-lab` request completed in 58.682 seconds with exactly
one Provider request, no retry, no cache hit, no fallback and no model switch. It produced a valid
two-session Blueprint with SHA-256
`0129d22b36be6ca2784642ec22578da209c81e36f20e74e316635865ddc29ccf`.
Provider Usage was 3,095 input, 7,621 output/Thinking and 10,716 total tokens; the configured local
cost calculation was CNY 0.018337. The response and invocation audit were atomically persisted
under `storage_eval/p14_closure/smoke/checkpoint`, and the Secret scan was clear.

This isolates the original failure to the forced 45-second client timeout: the same request
completed after approximately 59 seconds once the 180-second Planner Profile timeout was honored.
It also shows that Provider output Usage can exceed the 4,096 final-output setting when Thinking
tokens are included. Therefore the old full-run maximum-output estimate is not reused for another
authorization; a complete Pilot requires a new estimate based on the observed Thinking ratio.

## Thinking-aware budget gate and completed comparison

The approved closure repair added a durable incremental budget ledger and a request guard at the
Model Gateway boundary. A cache miss reserves local input plus 2.25 times the configured output
allowance before dispatch; the reservation is replaced by Provider Usage after success. Ambiguous
post-send failure retains the reservation, while a proven not-sent connection failure releases it.
The run pauses before dispatch if the next reservation would cross CNY 0.50, 100,000 input tokens,
or 200,000 output/Thinking tokens.

The Runner now executes the replan scenario as an initial Blueprint followed by a distinct Planner
request that receives the previous Blueprint and the approved replan instruction. Session-specific
repairable issues can trigger at most one `content_repair_main` call per Session, with caller-owned
allowed fields and post-generation preservation checks. No repair was needed in this Pilot.

The complete comparison finished successfully:

- 18 logical requests: 17 new Provider requests and one exact Smoke response cache hit;
- incremental usage: 56,967 input and 68,794 output/Thinking tokens;
- incremental calculated cost: CNY 0.194555 of the CNY 0.50 authorization;
- zero retry, failed call, deterministic fallback, silent model switch or pending reservation;
- CP-B0: 3/3 cases passed, 9 Provider calls, 3 legacy KP extractions;
- P14: 3/3 cases passed, 8 Provider calls plus one cache hit, 0 KP extractions;
- P14 Evidence Coverage and Citation Resolvability: 1.0 for all three cases;
- approved edit value preserved and the replan case made two Planner calls.

The blinded six-artifact Course Owner package is under `storage_eval/p14_closure/review`. It
contains browser-local autosave, completeness validation, JSON Blob download and a manual JSON
template. The Course Owner successfully exported and supplied all six decisions, which provides
the missing end-to-end browser download evidence. The decision file SHA-256 is
`149007b2d6ed1830f67ea9d8157e6bb48caa2177ca98a004d2d2b7f5de082a61`.

## Course Owner quality review

All six blinded artifacts were reviewed. There were no critical defects, rejected artifacts or
L0 grounding/citation/side-effect failures.

| Track | Mean L-H1—L-H8 | Mean Edit Burden | Review statuses |
|---|---:|---:|---|
| CP-B0 | 3.833 | 2.000 | 3 minor edit |
| P14 | 3.500 | 2.667 | 1 minor edit, 2 major edit |

P14 retained perfect automatic Evidence Coverage and Citation Resolvability and slightly improved
the human traceability score (L-H7: `3.333` versus `3.000`). It did not outperform the legacy
baseline on overall human quality. The clearest gaps were teaching-activity specificity (L-H5:
`2.667` versus `3.667`) and immediate teacher usability (L-H8: `2.333` versus `4.000`). The owner
notes show that several generated Session bodies repeat Blueprint activity lines instead of adding
detailed teaching scripts, materials, checkpoints and execution guidance.

This is recorded as non-blocking quality debt. It is not treated as a reason to weaken the
evidence-first design or enter an unbounded Prompt-tuning loop. The complete machine-readable
summary is `storage_eval/p14_closure/review/owner_review_summary.json`.

## Verification

- Offline CP-DS1: 3/3 passed, Evidence Coverage 1.0, P14 KP extractor calls 0.
- Model Generator profile contract: passed; planner/session calls require
  `allow_fallback=False`.
- Timeout/checkpoint repair tests: 39 passed; read timeout made one attempt, proven connection
  failure retried once, and exact successful response Resume made zero Provider requests.
- Authorized Blueprint Smoke: completed; 1 request, 10,716 tokens, CNY 0.018337, 0 retry,
  0 fallback, 0 switch, 0 downstream stages.
- Focused Mypy and Ruff checks passed; the repaired preflight completed without network access.
- Legacy LLM infrastructure and frozen B0 interface snapshot: passed.
- Full real comparison: completed, CNY 0.194555 incremental cost, 17 new requests, one cache hit.
- P14/Runtime/Repair focused closure: 50 passed, 6 skipped.
- Full suite after closure: 681 passed, 11 skipped.
- B0 sample-files smoke: 1 passed.
- Ruff format/check: passed; Mypy: 433 source files passed; Alembic head remains
  `0017_coursepilot_checkpoint_interrupts`; `git diff --check` reports only existing
  LF/CRLF normalization warnings.

## Gate conclusion

Workflow, grounding, KP separation, edit/replan, export scope, writeback and the real automatic
comparison pass. The Course Owner review is complete, with no critical defect or rejected output.
P14 is therefore `completed_with_quality_debt`: the three formal Exit Gate requirements pass, while
the lower activity-detail and teacher-usability scores remain explicit non-blocking debt. P15 is
`ready_to_start`. P10.3 remains isolated and default-off and is not reinterpreted by this result.
