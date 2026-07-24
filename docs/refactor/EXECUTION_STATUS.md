# Refactor Execution Status

- Frozen document set: v1.0
- Baseline commit: `eb9b3a6aa51348cf1fba0de7a21e5d073761939b`
- Current branch: `refactor/p00-baseline`
- Current phase: P01
- Last updated: 2026-07-24

| Phase | Status | Start Commit | End Commit | Gate | Report |
|---|---|---|---|---|---|
| P00 | completed | `eb9b3a6` | uncommitted (`eb9b3a6`) | passed | `phase_reports/P00_baseline_freeze_and_execution_scaffold.md` |
| P01 | completed | `21d2cc5` | uncommitted (`21d2cc5`) | passed | `phase_reports/P01_CourseRAG_Port_Report.md` |
| P02 | completed | `e3f4efa` | uncommitted (`e3f4efa`) | passed | `phase_reports/P02_evaluation_data_scaffold_and_b0_runner.md` |
| P03 | not_started | | | ready | |
| P04 | not_started | | | blocked_by_P03 | |
| P05 | not_started | | | blocked_by_P04 | |
| P06 | not_started | | | blocked_by_P05 | |
| P07 | not_started | | | blocked_by_P06 | |
| P08 | not_started | | | blocked_by_P07 | |
| P09 | not_started | | | blocked_by_P08 | |
| P10 | not_started | | | blocked_by_P09 | |
| P11 | not_started | | | blocked_by_P10 | |
| P12 | not_started | | | blocked_by_P11 | |
| P13 | not_started | | | blocked_by_P12 | |
| P14 | not_started | | | blocked_by_P13 | |
| P15 | not_started | | | blocked_by_P14 | |
| P16 | not_started | | | blocked_by_P15 | |
| P17 | not_started | | | blocked_by_P16 | |
| P18 | not_started | | | blocked_by_P17 | |
| P19 | not_started | | | blocked_by_P18 | |

## Current phase tasks

| Task | Status | Evidence |
|---|---|---|
| P01-T01 | completed | `courserag` domain/application/api/infrastructure package skeleton added without moving P02 evals |
| P01-T02 | completed | six typed subports, all four frozen SourceTier values, strict DTOs and outer/nested ContextRequest invariants |
| P01-T03 | completed | RequestContext/ResponseMeta, stable errors, UTC validation and fail-closed request/trace/API-version continuity |
| P01-T04 | completed | Local adapter preserves B0 dense retrieval while rejecting unsupported widening/rerank/deep-section requests and mapping backend errors |
| P01-T05 | completed | deterministic Mock supports fixed search, fault injection, course isolation and request-hash idempotency for every side effect |
| P01-T06 | completed | injected Remote client, opaque encoded v1 path segments and response correlation/version validation; no production remote selection |
| P01-T07 | completed | old KB facade and shared Lesson/Exam retrieval node now call the Port; old HTTP responses remain unchanged |
| P01-T08 | completed | shared Local/Mock/Remote contracts plus idempotency, isolation, path and correlation regressions pass; three Graph Mock Smoke tests pass |

P01's P00 prerequisite passed before work began; P02 had also already passed. P01 is complete
under the explicitly approved narrow boundary: document build execution, dense search and the
shared Lesson/Exam retrieval node use the CourseRAG Port while the existing CoursePilot HTTP
surface and B0 behavior remain compatible. The public DTO layer does not invent stable Evidence
or version identities for legacy Chunks: Evidence IDs remain empty and explicit
`legacy-unversioned`/`legacy-active` markers and warnings are returned. Advanced P03+ capabilities
are declared unsupported rather than silently falling back. Review write-back and repeated lesson
knowledge-point extraction remain unchanged and are recorded as later-phase work. The final exact
test run reports 250 passed and 5 explicit gated skips; the owner-supplied DOCX/PDF B0 Smoke,
shared contracts, old API/Graph regressions, Ruff, Mypy, Alembic Head, secret and temporary-file
checks all pass. The P01 Exit Gate is passed, and P03 now has both P01 and P02 prerequisites.
