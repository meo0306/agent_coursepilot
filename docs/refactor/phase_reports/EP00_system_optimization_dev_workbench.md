# EP-00 Post-P18 Dev Workbench

## Status

EP-00 implementation, scope-reduction remediation, human approval and approved-data materialization
are complete. The r2 dataset passed Course Owner review on 2026-08-31 with 27/27 Task Case
approvals; the owner separately approved all seven Failure Replays. The approved Loader and Exit
Gate pass. No external Provider call, runtime behavior change or new generated-quality claim was
produced. EP-01 is ready but was not started.

## Completed tasks and requirements

- `EP00-T01` / `OPT-EVAL-001`: strict P18/Test/Blind isolation and approved-only metric loading.
- `EP00-T02` / `OPT-EVAL-002`: joint Task Demand, Evidence Package, Candidate Adequacy and Artifact
  Rubric schemas.
- `EP00-T03`: 27 new Task Cases; Lesson, Exam and PPT each contain three thin, three medium and
  three rich Evidence capacities.
- `EP00-T04`: every Artifact family covers definition, comparison, process, formula, table,
  numeric and case material.
- `EP00-T05`: seven failure replays cover three Artifact Schema failures, timeout, missing Exam
  Batch, incomplete Evidence Group and missing Index.
- `EP00-T06` / `OPT-EVAL-003`: JSON-only Case approval and Artifact blind-review packages with reviewer/time,
  1—5 Rubric, integer 0—4 Edit Burden and six repeated blind-review assignments.
- `EP00-T07`: historical B0/B10 aggregates are recorded with scope limitations; the new unified
  baseline is explicitly pending data approval and Provider authorization.

## Data result

- 27 Candidate Task Cases: Lesson 9, Exam 9, PPT 9.
- Per Artifact: thin/medium/rich = 3/3/3.
- Current r2 Candidate Adequacy per Artifact: `adequate=9`; no missing KP or material requirement.
- Current r2 quantity coverage: Lesson 1/1/2 sessions; Exam 2/4/6 questions; PPT 3/5/7 slides.
- Current r2 source scope: 15 unique non-P18 Evidence records referenced through 15 unique approved
  P09 Dev Context records; 54 Case-level items are all bound to declared task KPs.
- Seven failure replays and 33 future Artifact review units, including six repeat groups.
- `datasets/system_optimization/v1/approved/` contains 27 Task Cases, seven Failure Replays and 34
  hash-bound Review Log entries.

## Course Owner r1 review result

- Schema and coverage validation: passed; 27/27 unique expected record IDs, no pending decisions,
  and all reviewer/time fields are present.
- Decisions: 24 `request_changes`, three `reject`, zero `approve`.
- Human Adequacy: 24 `needs_more_evidence`, three `unresolvable`, zero `adequate`.
- The rejected records are `sysopt-v1-lesson-03`, `sysopt-v1-exam-03` and
  `sysopt-v1-ppt-03`; each lacks visible Evidence for two required knowledge points.
- All 12 generator-labelled `adequate` records were reclassified as `needs_more_evidence`.
  Medium/rich capacity was inflated by Evidence outside the required knowledge points, so total
  item count was not a valid proxy for usable long-form generation support.

## Owner-approved r2 remediation

- The owner selected the existing-Evidence scope-reduction option on 2026-08-30; no new CourseRAG
  Evidence was generated.
- All 27 Cases remain, including three thin, three medium and three rich Cases per Artifact.
- Output scale now follows available Evidence: Lesson 1/1/2 sessions, Exam 2/4/6 questions and PPT
  3/5/7 slides for single/adjacent/non-adjacent topic demands.
- Every visible Evidence item belongs to a declared task KP; unmapped filler count is zero.
- All KP groups are complete, all required material types are present and the three rejected r1
  Cases were rebuilt as resolvable candidates.
- Mean estimated Evidence tokens increase by tier: thin 13.22, medium 47.78 and rich 106.67.
- The r1 decision JSON remains at its original path. The second review uses
  `review/case_review_decisions_r2_template.json` and does not overwrite r1.

## Course Owner r2 review result

- Schema and coverage validation: passed; 27/27 unique expected record IDs, no pending decisions,
  no duplicates and no missing or unexpected IDs.
- Decisions: 27 `approve`, zero `reject` and zero `request_changes`.
- Human Adequacy: 27 `adequate`.
- Reviewer: `course_owner`; reviewed at `2026-08-31T10:41:29+08:00`.
- Review approval does not itself create the `approved/` dataset. Materialization and approved
  Loader validation remain a separate explicitly authorized action.

## Files

New source package:

- `src/evaluation/system_optimization/__init__.py`
- `src/evaluation/system_optimization/schemas.py`
- `src/evaluation/system_optimization/dev_loader.py`
- `src/evaluation/system_optimization/dev_data.py`
- `src/evaluation/system_optimization/review.py`
- `src/evaluation/system_optimization/baseline_runner.py`
- `src/evaluation/system_optimization/approval.py`

New tests:

- `tests/evals/system_optimization/test_schemas.py`
- `tests/evals/system_optimization/test_dev_loader.py`
- `tests/evals/system_optimization/test_dev_data.py`
- `tests/evals/system_optimization/test_review.py`
- `tests/evals/system_optimization/test_baseline_runner.py`
- `tests/evals/system_optimization/test_approval.py`

New Candidate assets are under `datasets/system_optimization/v1/candidates/`: `dev_cases.json`,
`failure_replays.json`, `historical_baseline.json`, the Case approval package and the future
Artifact blind-review templates. Existing P18 datasets, reports, locks and human-review files were
not modified.

Approved assets:

- `datasets/system_optimization/v1/approved/dev_cases.json`
- `datasets/system_optimization/v1/approved/failure_replays.json`
- `datasets/system_optimization/v1/approved/review_log.jsonl`

## API, database and configuration

- Public API and CoursePilot/CourseRAG Port: unchanged.
- PostgreSQL and Alembic: unchanged; no migration.
- Prompt, model Profile, Compose and Index: unchanged.
- Provider requests, Token use and cost: zero.
- External repositories, commit, push and PR: none.

## Verification

Commands and results:

```text
python -m pytest -q tests/evals/system_optimization
18 passed

python -m pytest -q tests/evals/test_dataset_boundaries.py tests/evals/test_p18_runtime.py
23 passed, 5 existing SWIG deprecation warnings

python -m evaluation.system_optimization.dev_loader --status approved --check-only
approved; 27 Task Cases; 7 failures; metric eligible=true; Provider calls=0

python -m evaluation.system_optimization.baseline_runner --artifact all --split dev
approved; quality metrics eligible=true; P18 Test/Blind loaded=false; Provider calls=0

python -m ruff check src/evaluation/system_optimization tests/evals/system_optimization
passed

python -m mypy src/evaluation/system_optimization
passed, 6 source files
```

`git diff --check`: passed（仅有仓库既有/用户文件的行尾转换提示，无空白错误）。Full repository tests were not required for
this additive evaluation-only package; the existing dataset-boundary and P18 runtime regression
sets were run in addition to the new focused suite.

## Risks and Gate

Historical human metrics remain non-comparable across Artifact units and are not
optimization-eligible. A real new Dev generation Baseline still requires separate Provider
authorization and is not part of the EP-00 Exit Gate.

- Implementation Gate: passed.
- r1 Data approval Gate: failed (`24 request_changes`, `3 reject`, `0 approve`).
- r2 automated candidate checks: passed; human Data review passed 27/27.
- Failure Replay approval: passed 7/7 by explicit Course Owner authorization.
- Approved materialization: passed; 34/34 Approval/Review bindings validated idempotently.
- EP-00 overall Exit Gate: passed.
- EP-01 readiness: ready, but EP-01 has not started per Course Owner direction.

Rollback is deletion of the new `src/evaluation/system_optimization/`,
`tests/evals/system_optimization/` and `datasets/system_optimization/` trees plus these lightweight
governance entries. No runtime or persisted business data rollback is necessary.
