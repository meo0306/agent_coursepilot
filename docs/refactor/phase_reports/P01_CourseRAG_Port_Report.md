# P01 CourseRAG Port Phase Report

## Scope and inputs

- Phase: P01 — logical split and CourseRAG Port
- Start Commit: `21d2cc50ebe9b7442b360e2bcac01af9d1793646`
- Branch: `refactor/p00-baseline`
- Initial and final Git state: no pre-existing user changes; P01 changes remain uncommitted
- Prerequisites: P00 passed; P02 also passed before P01 execution
- Approved boundary: migrate document build, search and shared Graph retrieval only
- Frozen inputs: documents 00, 01, 04, 05 and 07 plus Master Rules

No commit, push, PR, database migration, destructive data operation or real network call was
performed.

## Repository audit

Before P01, `src/courserag/` contained only the P02 evaluation package. The current runtime
implemented build and search in `KnowledgeBaseService`, imported the legacy Retriever directly in
the Lesson/Exam shared retrieval node, and had no CourseRAG Port, Mock, Remote client or shared
contract tests. Existing temporary SQLite/Chroma fixtures, deterministic Graph tests,
IdempotencyService and `httpx.MockTransport` were suitable foundations.

The audit also found four compatibility boundaries:

1. legacy CoursePilot uploads support more formats than the frozen PDF/DOCX CourseRAG MVP;
2. legacy Chunk records have no stable Evidence or version identities;
3. review write-back stores whole lesson/PPT artifacts directly in Chroma;
4. lesson generation still extracts knowledge points from retrieved Context.

Items 3 and 4 remain deliberately unchanged under P01-D001.

## Implemented task IDs

- P01-T01: added CourseRAG domain/application/api/infrastructure package layers.
- P01-T02: added six subports, composite service boundary and typed DTO families.
- P01-T03: added RequestContext, ResponseMeta, UTC validation, stable errors and tracing.
- P01-T04: added LocalCourseRAGAdapter over the unchanged B0 build and dense-search runtime.
- P01-T05: added deterministic MockCourseRAGService with fault and idempotency controls.
- P01-T06: added injected-transport RemoteCourseRAGClient and frozen v1 HTTP paths.
- P01-T07: changed the old KB facade and shared Graph retrieval node to call the Port.
- P01-T08: added one shared Local/Mock/Remote contract suite and Mock Graph Smoke tests.

## Key decisions

- P01-D001 keeps the approved narrow migration boundary.
- P01-D002 prohibits synthesized Evidence/version identity for legacy Chunks.
- P01-D003 keeps RemoteCourseRAGClient contract-only and explicitly injected.
- Local advanced capabilities fail with `FEATURE_NOT_AVAILABLE`; no deterministic or Provider
  fallback is hidden.
- Port objects are not stored in Graph State, Checkpoint or trace metadata. A context-local test
  override supplies Mock behavior while the single-process demo defaults to Local.

## Files changed

Public CourseRAG boundary:

- `src/courserag/__init__.py`
- `src/courserag/domain/__init__.py`
- `src/courserag/application/__init__.py`
- `src/courserag/infrastructure/__init__.py`
- `src/courserag/api/__init__.py`
- `src/courserag/api/http_schema.py`
- `src/courserag/contracts/__init__.py`
- `src/courserag/contracts/common.py`
- `src/courserag/contracts/knowledge_base.py`
- `src/courserag/contracts/retrieval.py`
- `src/courserag/contracts/evidence.py`
- `src/courserag/contracts/qa.py`
- `src/courserag/contracts/verified_content.py`
- `src/courserag/contracts/service_info.py`

CoursePilot boundary and compatibility:

- `src/coursepilot/ports/__init__.py`
- `src/coursepilot/ports/courserag.py`
- `src/coursepilot/adapters/__init__.py`
- `src/coursepilot/adapters/courserag_mapping.py`
- `src/coursepilot/adapters/local_courserag.py`
- `src/coursepilot/adapters/mock_courserag.py`
- `src/coursepilot/clients/__init__.py`
- `src/coursepilot/clients/remote_courserag.py`
- `src/coursepilot/services/courserag_runtime.py`
- `src/coursepilot/services/kb_service.py`
- `src/agents/coursepilot/nodes/retrieve_nodes.py`

Tests and governance:

- `tests/contracts/test_courserag_contract.py`
- `tests/contracts/test_courserag_http_schema.py`
- `tests/coursepilot/test_local_courserag_adapter.py`
- `tests/coursepilot/test_mock_courserag_graphs.py`
- `tests/coursepilot/test_mock_courserag_service.py`
- `tests/coursepilot/test_retrieve_nodes.py`
- `docs/refactor/EXECUTION_STATUS.md`
- `docs/refactor/DECISION_LOG.md`
- `docs/refactor/RISK_REGISTER.md`
- `docs/refactor/phase_reports/P01_CourseRAG_Port_Report.md`

## API/database/config changes

- Public API: no route, status-code or response-schema change. The saved B0 interface snapshot
  remains identical.
- HTTP contract: added unmounted `/api/courserag/v1` path definitions for a Contract Fake.
- Database: no ORM or Alembic change; Head remains `0007_add_async_task_queue_fields`.
- Configuration: no environment variable, dependency, lock-file, Provider, model or Chroma
  Collection change.
- Compatibility: old TXT/Markdown/XLSX uploads remain available through CoursePilot; CourseRAG
  capabilities advertise only PDF/DOCX.
- Idempotency: Local and Mock build requests replay the original job for the same semantic request
  and reject key reuse with a changed request.

## Tests and commands

Initial baseline:

- P01 retrieval/API audit set: 10 passed.
- old Graph/API set: 25 passed.
- full split baseline: 204 passed, 5 skipped.
- Ruff and Mypy: passed, 141 source files.

Implementation checkpoints:

- contract imports/serialization: passed.
- contract-layer Ruff/Mypy: passed, 20 source files.
- Local adapter: 5 passed.
- Mock plus Remote HTTP: 5 passed.
- Port wiring plus old build/search: 14 passed.
- shared contracts plus Mock Graph Smoke: 19 passed.
- old Graph/API regression: 25 passed.
- async/idempotency/interface/upload/search/write-back regression: 23 passed.
- gated owner DOCX/PDF B0 Smoke: 1 passed.

Gate Repair checkpoint:

- completed a read-only post-stage audit before repair;
- added the two missing frozen SourceTier values and restricted verified writeback to
  `teacher_verified`;
- made nested ContextRequest course/query/context inheritance and consistency fail closed;
- encoded every HTTP path identifier as an opaque segment, including dot segments;
- added Mock request-Hash replay/conflict handling for register, delete and revoke, and made
  document identity course-scoped;
- made Local reject candidate/rerank divergence, deep section paths and unsupported tiers while
  mapping unexpected backend failures to redacted structured errors;
- made Remote reject unsupported request versions and mismatched success/error
  request/trace/API-version metadata;
- expanded the P01 focused contract and adapter set from 31 to 49 passing tests.

Final commands:

```text
uv sync --frozen
Checked 181 packages

uv run pytest -q
250 passed, 5 skipped, 5 third-party SWIG deprecation warnings in 30.13s

uv run ruff format --check
225 files already formatted

uv run ruff check
All checks passed

uv run mypy src/
Success: no issues found in 163 source files

uv run python -m alembic heads
0007_add_async_task_queue_fields (head)

git diff --check
exit 0; only existing Windows LF-to-CRLF notices
```

The first fresh full collection exposed one adapter/service import cycle. Legacy application
service imports were moved inside the two Local methods that use them. The focused repair set
reported 49 passed, and the final full run above passed.

## Evaluation results

P01 adds no quality metric, Gold data or formal evaluation claim. The existing deterministic and
owner-supplied DOCX/PDF B0 flows remain operational. Legacy Search responses explicitly report
that stable Evidence and versions are unavailable; no Chunk ID is promoted into Gold or Evidence.

## Compatibility and migration

- Existing build execution still uses the same parser, chunker, Chroma write and ORM sequence.
- Existing dense retrieval uses the same CoursePilotRetriever and result score.
- Existing KBSearchResult fields are reconstructed without loss.
- Existing Lesson/Exam missing-context messages and Graph state shape are unchanged.
- Review write-back, PPT Chunk checks and lesson knowledge-point extraction are unchanged.
- Rollback is code-only because no table, Collection, stored file or public API was migrated.

## Risks and remaining work

- P01-R02: real Document/Index/Evidence versions await P03/P06.
- P01-R03: advanced Local methods remain explicitly unsupported.
- P01-R04: review write-back and knowledge-point ownership await P07/P10/P14/P17.
- P01-R05: Remote production reliability remains P17.
- P01-R07: versioned atomic index publication remains P03.
- P01-R08 through P01-R12: post-stage idempotency, isolation, fail-closed Local behavior,
  Remote correlation and frozen-contract coverage defects were repaired and regression-tested.
- P02-R01 remains open: human Approved Gold does not yet exist.

Secret scan found no literal assignment in source/tests. The only visible database-like temporary
file is the pre-existing ignored `checkpoints.db`. No untracked P01 temporary artifact exists in
the repository.

## Exit Gate evidence

- CoursePilot Graph nodes add no Chroma or Parser import: passed by AST contract test.
- The shared retrieval node no longer imports the legacy Retriever directly.
- Old API response compatibility: passed by interface snapshot and old API regressions.
- Local, Mock and Remote pass one capability-aware contract suite; specialized regressions cover
  every repaired idempotency, isolation, path, structured-error and response-correlation defect.
- Main tests, formatting, lint and type checking pass.
- Owner DOCX/PDF B0 Smoke and old end-to-end flows pass.

P01 Exit Gate: **passed**.

## Next-phase readiness

P03 now has both P01 and P02 prerequisites and is ready to enter its own Plan-mode audit. No P03
implementation was started. P11 and later CoursePilot-wide removal of legacy RAG imports remain
blocked by their declared prerequisites.
