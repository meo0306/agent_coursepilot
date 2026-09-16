# P03 CourseRAG Persistence, Versioning and Build Pipeline Phase Report

## Scope and inputs

- Phase: P03 — CourseRAG persistence, versioning and build pipeline
- Start Commit: `b6483f5ae8a0b3c3e45858c3872b4ed86e94502d`
- Branch: `refactor/p00-baseline`
- Prerequisites: P01 and P02 passed; the Pre-P03 DS0 checkpoint passed
- Approved boundary: complete the new versioned pipeline and legacy Document/Task bridge, but do
  not default-cut over the public B0 build/search path
- Frozen inputs: documents 00, 02, 04 and 07 plus Master Rules

The start audit recorded 14 modified and 11 untracked protected Pre-P03 entries. P03 preserved
those changes, made no commit/push/PR, and did not run a migration against a user database.

## Repository audit

The audit found one PostgreSQL CoursePilot metadata tree ending at Alembic 0007, mutable legacy
Document/Chunk facts, a build path that deletes legacy DB/Chroma chunks before replacement, and a
leased GenerationTask worker with expired-lease takeover. No `courserag/persistence`, jobs,
version manager or artifact cache existed. Docker service packaging also omitted `src/courserag`.

The supplied fixture scope remains one content-distinct PDF and one DOCX in `data/sample_files`.
The public B0 facade and Graphs already pass against those files and were retained unchanged.

## Implemented task IDs

- P03-T01: added KnowledgeBase, SourceDocument, DocumentVersion, ParsedDocument, BuildJob,
  BuildStageRun, IndexVersion and supporting ORM facts.
- P03-T02: added first-version Section/Block/Evidence/Chunk/KP/Writeback/Run facts and indexes.
- P03-T03: added Repository and UnitOfWork persistence boundaries.
- P03-T04: added BuildStage Protocol, KB/semantic-identity-scoped fingerprinting, opaque Artifact
  URI/hash, atomic content-addressed writes, verified cache hits, retries and Stage status.
- P03-T05: reused GenerationTask leasing for explicit `courserag_build` jobs, expired-lease
  takeover, Stage resume, failure persistence and manual Stage retry.
- P03-T06: added exact KB/build/document and shard-Hash validation for dense/sparse Manifests plus
  transactional Active Pointer publication.
- P03-T07: added dry-run-first DB/physical orphan and stale-staging cleanup with retention settings
  and audit records.
- P03-T08: added PDF/DOCX legacy Document mapping without altering the public B0 route.

## Key decisions

- P03-D001: separate CourseRAG metadata on the shared database; no new-to-legacy foreign keys.
- P03-D002: explicit internal bridge only; no default public cutover.
- P03-D003: at-least-once execution with idempotent Stage effects.
- P03-D004: sparse is explicitly `not_materialized` until P08 unless a valid Manifest exists.
- P03-D005: opaque content-addressed Artifacts and dry-run-first cleanup.

## Files changed

- Persistence: `src/courserag/persistence/` and Alembic revisions 0008/0009.
- Jobs/indexing: `src/courserag/jobs/` and `src/courserag/indexing/`.
- Compatibility: `src/coursepilot/adapters/courserag_build_bridge.py` and the new worker dispatch.
- Packaging/config: `alembic/env.py`, `src/core/settings.py`, `compose.yaml`, and
  `docker/Dockerfile.service`.
- Tests: `tests/courserag/`.
- Governance: Execution Status, Decision Log, Risk Register and this report.

No P03 change was made to the protected Pre-P03 dataset/evaluation files already present at stage
start.

## API/database/config changes

- Public API: none. No route, request/response schema, status code or public runtime selector was
  added or changed.
- Database: 32 additive `courserag_*` tables in revisions `0008_courserag_core` and
  `0009_courserag_content`; separate metadata, no legacy-table FK and reversible downgrade.
- Configuration: added `COURSERAG_ARTIFACT_DIR`, `COURSERAG_ARTIFACT_RETENTION_HOURS` and
  `COURSERAG_STAGING_RETENTION_HOURS` with local, bounded defaults.
- Packaging: the service image and Compose watch now include `src/courserag`.
- Dependencies/lock: no dependency declaration or final `uv.lock` change.
- Provider/Gold: none. No model call, LLM judge, Gold promotion or Fallback change.

## Tests and commands

Implementation and Gate Repair checkpoints:

- exact `uv sync --frozen`: passed in the isolated locked environment.
- P03 migrations, fingerprints/cache, Active Pointer, bridge/lease recovery and cleanup: 17 passed.
- owner PDF/DOCX B0 Smoke: 1 passed.
- full regression: 276 passed, 5 explicit gated skips (two Docker E2E, one real LLM, one P02 local
  candidate parse and the default-off B0 sample; B0 was enabled and passed separately), plus 5
  third-party SWIG deprecation warnings.
- Ruff format: 257 files already formatted.
- Ruff lint: all checks passed.
- Mypy: 185 source files, zero issues.
- Alembic heads/history: one Head, `0009_courserag_content`.
- Compose base, base+eval and `.env.eval.example` merged config: all parsed successfully.

Real PostgreSQL migration evidence used a dedicated loopback-only temporary container/database:

```text
0007_add_async_task_queue_fields -> 0008_courserag_core -> 0009_courserag_content
0009_courserag_content -> 0008_courserag_core -> 0007_add_async_task_queue_fields
0007_add_async_task_queue_fields -> 0008_courserag_core -> 0009_courserag_content
alembic current: 0009_courserag_content (head)
```

The dedicated loopback-only temporary database/container was removed afterward. PostgreSQL also
confirmed that `courserag_build_stage_runs` has only the intended
`(build_job_id, stage_name, attempt_number)` unique constraint in addition to its primary key.

## Evaluation results

P03 adds no quality metric or formal Gold. The deterministic Stage/cache and recovery tests are
engineering evidence only. The owner-supplied PDF/DOCX B0 Smoke remains 1/1 passed and the public
legacy runtime is unchanged.

## Compatibility and migration

- Existing public B0 build/search and old Chroma collections remain untouched.
- The compatibility bridge accepts only frozen MVP PDF/DOCX and stores legacy IDs as mapping
  values; it does not promote Chunk IDs to Evidence.
- New build replay may execute pure Stage computation more than once, but the runner owns the only
  Stage artifact side effect and makes it idempotent by verified content address. Same-job Resume
  reuses a succeeded attempt; explicit retry creates the next numbered attempt.
- Failed or stale candidate publication does not change the Active Pointer.
- Rollback is `alembic downgrade 0007_add_async_task_queue_fields` for the additive facts plus
  code/config removal; it does not require altering legacy rows or collections.

## Risks and remaining work

- P03-R05 remains open by design: the preserved public B0 rebuild is still non-atomic until a
  separately approved versioned cutover.
- Sparse implementation is deferred to P08; `not_materialized` is explicit.
- Final Parser/OCR algorithms, legacy Chunk-to-Evidence migration and Chroma replacement remain
  prohibited/deferred.
- Migration revisions own explicit immutable table metadata and do not import live application
  ORM; future model changes must use new revisions and retain parity/round-trip CI.
- P02-R01, P02-R10 and P02-R14 remain open; P03 did not create Gold or formal DOCX pagination.

Secret scanning found no literal credential in P03 source/config/report files. Provider metadata
uses an allowlist and rejects secret-bearing keys; persisted Stage, Build and task errors use fixed
redacted messages. Artifact facts use opaque URIs and no absolute source path is persisted. No
unexplained fallback, destructive legacy migration, tracked temporary file or residual temporary
Docker container was found.

## Exit Gate evidence

- Same input reuses a Stage: **PASS**. Same-job Resume returns the verified original Stage attempt;
  cross-job cache reuse is Hash-verified, while a different KB or semantic input identity does not
  collide. Missing/corrupt artifacts re-execute safely.
- Build failure does not break Active Index: **PASS**. Missing shards, mismatched KB/build/document
  sets and stale expected pointers fail closed; failed candidates never replace Active.
- Worker crash can be taken over without duplicate Stage effect: **PASS**. Lease takeover,
  stale-attempt closure, manual retry, same-job Resume and CAS orphan adoption are covered; Stage
  implementations are constrained to pure computation and the runner owns the idempotent write.
- Main tests, Ruff, Mypy and owner PDF/DOCX B0 Smoke pass.
- Public API, legacy tables, Chroma, Parser, Provider and Gold behavior are unchanged.

The repository-wide `git diff --check` still reports only the protected, pre-P03 extra EOF blank in
`codex_prompts/91_INDEPENDENT_PHASE_VERIFICATION.md`; the tracked P03 scope passes its own diff
check, and that protected file was not changed during P03 Gate Repair.

P03 Exit Gate: **passed**.

## Next-phase readiness

P04 has its P03 upstream prerequisite and may enter its own audit/Plan flow. P03 did not start P04
or any later Parser/OCR, sparse, retrieval, Gold or service-split implementation.
