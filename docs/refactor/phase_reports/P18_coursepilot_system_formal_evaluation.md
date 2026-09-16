# P18 CoursePilot and System Formal Evaluation

## Status

P18 formal Test has been consumed under the owner-approved Frozen Manifest. Evaluation execution is
`completed`, while the formal quality Gate remains `failed`; Test results are immutable inputs to
the report and must not be used to tune this release. The Course Owner has separately approved a
portfolio-only disposition, so P19 may package and physically split the engineering MVP without
representing this result as a production or formal-quality pass.

The failure is not a dangerous-side-effect failure. Cross-course access, unauthorized actions,
Secret leakage, duplicate side effects, silent fallback, unresolved emitted citations and tool
execution are all zero. The blocking failures are formal output/contract completeness and a missing
formal CourseRAG Test Index in the isolated Track-B environment.

## Frozen identities and execution boundary

- CP-DS0: `8814701173860a76a9db559e3cfb6cc094c2580446bfc12be33ebf02a675ba01`.
- Frozen Manifest: `fb2c13716cc329110b58d87358667323c2ab825cd3b609f6ef2cf6aa6afb23d6`.
- Test Preflight: `2a9e3cd3b5e8135d40d27d53b83aab468f8cf22edb509657f1a6bea94309ccd1`.
- Test Lock: `f16b959c27fb5c87b0f1417c295002daa635b27296575d2117661921a3ee21da`;
  92 Test/Blind/system records were released.
- DeepSeek cumulative Test use after Track A and the fixed stability repeats: 197 requests,
  761,098 input tokens, 701,816 output/Thinking tokens and estimated CNY 2.164730. This remains
  below the approved 260 / 1.2M / 1.2M / CNY 4 limits. Cohere use is 0/40 Search Units.
- Fallback and model switching are zero. Four Provider/schema failures remain in the denominator.

## Formal Test results

### Track A

- CP-B0: 12 samples, 10 Provider successes, 7/12 contract pass, 10/12 citation/trace complete,
  P50 67.935 s, P95 515.179 s, cost CNY 0.486533.
- CP-B10: 12 samples, 10 Provider successes, 9/12 contract pass, 10/12 citation/trace complete,
  P50 137.819 s, P95 737.685 s, cost CNY 1.202527.
- Four generation failures occurred: Lesson-10 B10, Exam-05 B0, Exam-10 B0 and PPT-04 B10.
  Four additional successful outputs failed their frozen contract, producing eight total contract
  failures.
- Export/render attempted all 24 outputs. The 20 generated outputs opened successfully and all
  generated PPTX files rendered with the frozen LibreOffice image; the four upstream generation
  failures necessarily produced no export.
- Stability selected one fixed Test task per component and ran two extra CP-B10 repetitions each:
  5/6 Provider successes and 3/6 contract passes. No fallback occurred.

### Offline formal components

- Validation 30/30, Repair 18/18, Recovery 12/12, Template 2/2 and Blind Fault/Security 10/10.
- All these checks used the locked Test records, had zero external Provider calls and preserved zero
  duplicate side effects.

### Track B

- Both service health endpoints and the CourseRAG Capability contract passed through the real HTTP
  boundary.
- The real PostgreSQL writeback/enrichment/overlay integration test passed and verified idempotent
  writeback-to-retrieval behavior in transaction.
- 10/10 locked Blind Fault/Security variants passed the production error boundary.
- All 8 SYS-DS1 state/side-effect contracts passed, but only the index-independent fault-recovery
  Journey could be counted as a live Journey. The isolated database contains no CourseRAG Knowledge
  Base, and neither repository artifacts nor historical Docker volumes contain a restorable P10
  formal index. Seven Journeys are therefore `blocked_missing_formal_index`.
- Track-A Gold fixtures were deliberately not installed as a fake formal index.

## Human review and outputs

The Course Owner completed all 24 blinded Artifact decisions in
`human_review/p18/formal_test/review_decisions.json` (SHA-256
`ef385e758b177c39706d00df02821c6f0ece83f50af6a406cd6830a2b2821e25`). The set contains 7 minor,
13 major and 4 reject decisions; all four generation failures are retained as Critical Defects.
The resulting Acceptable Rate is 0.2917, mean Rubric score is 2.8884 and mean Edit Burden is 2.625.
PPT decisions were checked against rendered output. These results fail the P18 L1 quality targets
independently of the existing automatic L0 failure. They remain internal diagnostic metrics: no
README/resume public metric candidate is emitted from a failed formal Gate.

Primary reports:

- `reports/p18/formal_test_report.json`
- `storage_eval/p18/formal_test/track_a/report.json`
- `storage_eval/p18/formal_test/stability/report.json`
- `storage_eval/p18/formal_test/components/report.json`
- `storage_eval/p18/formal_test/exports_docker/report.json`
- `storage_eval/p18/formal_test/track_b/report.json`

## Exit Gate

1. Mandatory thresholds: **failed** because Test contract/render completeness is below 1.0 and
   seven live Track-B Journeys lack the frozen formal index.
2. Test configuration: **frozen and consumed**; no Test-driven repair is permitted in this release.
3. Public metric traceability: raw and aggregate results, including the complete human review, are
   traceable; no positive public quality claim is released from this failed Test.
4. P18 execution status: `completed`; formal quality Gate: `failed`.
5. P19 readiness: **portfolio scope authorized**. The portfolio release must disclose the failed
   quality Gate and may not emit positive P18 quality claims. A future production candidate must
   repair the four Provider/schema failure modes, contract violations and formal Track-B index
   provisioning using new Dev evidence, then obtain a new independent Test release rather than
   rerun this Test.
