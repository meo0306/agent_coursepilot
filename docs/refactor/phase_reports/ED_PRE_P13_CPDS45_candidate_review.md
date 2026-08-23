# ED-PRE13 CP-DS4/5 Candidate Review

- CP-DS4 Candidate: `datasets/coursepilot_eval/v1/candidates/cp_ds4/p13_validation_r1.json` (30 records)
- CP-DS5 Candidate: `datasets/coursepilot_eval/v1/candidates/cp_ds5/p13_repair_r1.json` (15 records)
- Fixture bundle: `datasets/coursepilot_eval/v1/provenance/p13_artifact_fixtures.json`
- CP-DS4 SHA-256: `78db80ea161e9c4802a44e2948aa66c31de225734b7807ba691b86538d11dac7`
- CP-DS5 SHA-256: `57c1c315589ca4e59fd82186954d05744743a7b83f6eed77f3db2a6af1386a9d`
- Fixture SHA-256: `f385c0a0d4602dc090d388c27134dd83c8311327e3a4c39584621fae8bf23e4b`
- Bundle SHA-256: `b436f6e1901bb9447359e4fd0524f27ba39bfa24742b3ec006e451ae0bec9cd0`
- Strategy: hybrid; structural fixtures are deterministic, grounding references use only Approved DS2/DS3 from the two existing courses.
- Review: `storage_eval/cpds45_p13_review/b436f6e1901bb9447359e4fd0524f27ba39bfa24742b3ec006e451ae0bec9cd0/index.html`
- Blind second review: `storage_eval/cpds45_p13_review/b436f6e1901bb9447359e4fd0524f27ba39bfa24742b3ec006e451ae0bec9cd0/second_review.html`

No P13 output, external Provider, CourseRAG Test/Holdout, Dev/Test split or formal CP-DS1—3 Gold was used.
Candidate status remains `candidate`; approval is required before P13 implementation.

Review all 45 records. Focus on Issue code/layer/severity/scope, clean controls, injected paths,
allowed/forbidden Repair paths, preconditions, preservation paths and grounding provenance.

Review UI v2 presents compact human-readable cards by default: artifact summary, injected
before/after values, expected Issues or Repair boundaries, and one explicit review question.
Raw Gold/Fixture JSON is collapsed for exception handling. Filters, progress, bulk-pass for the
current filter and local decision persistence reduce review effort. This presentation-only change
does not alter Candidate files, record hashes or Bundle SHA-256.
