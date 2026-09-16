# EP-02 Generation Context and Deterministic Adequacy

## Status

EP-02 is complete and its Exit Gate passes. CourseRAG provides a versioned task-oriented Context
contract, deterministic Adequacy report, HTTP endpoint and explicit Capability. CoursePilot can
transport the contract through Remote, Local and Mock implementations and convert EP-01 Demand and
Adequacy models. No generation Graph or Worker consumes this capability yet.

## Completed tasks

- `EP02-T01`: strict `GenerationContextRequirements` with Artifact, KP, semantic, source, budget,
  supplement and version/course/overlay/tier boundaries.
- `EP02-T02`: versioned `GenerationContextRequest/Response` wrapping the existing ContextPackage.
- `EP02-T03`: per-KP and per-Requirement results plus deterministic `ContextAdequacyReport`.
- `EP02-T04`: `BUILD_GENERATION_CONTEXT` Capability and supported contract version `v1`.
- `EP02-T05`: single-pass `GenerationContextService` over the existing Context builder.
- `EP02-T06`: authoritative Evidence/KP/source metadata adapter and deterministic capacity/group
  statistics without LLM or text heuristics.
- `EP02-T07`: authenticated generation-context HTTP endpoint with existing CourseRAG error envelope.
- `EP02-T08`: CoursePilot Port, Remote Client, Local Adapter, Mock and runtime callback support.
- `EP02-T09`: fixed Invalid Demand, Index Not Ready, Version/Boundary and Capability error behavior;
  `unresolvable` remains a normal HTTP 200 result.

## Main changes

New production modules:

- `src/courserag/contracts/generation_context.py`
- `src/courserag/application/generation_context_service.py`
- `src/courserag/infrastructure/generation_context_metadata.py`
- `src/courserag/api/generation_context.py`
- `src/coursepilot/application/generation_context_service.py`

Existing CourseRAG contract exports, API mounting, ContextPacker limits and Capability reporting were
extended. CoursePilot Port, Remote, Local, Mock and runtime assembly gained a separate generation
operation. Existing `/search`, `/contexts` and `/qa` operations retain their prior paths and call
behavior; per-request packing limits are passed only through the new generation base method.

## API, database and configuration

- Added `POST /api/courserag/v1/knowledge-bases/{course_id}/generation-contexts`.
- Added `CourseRAGOperation.BUILD_GENERATION_CONTEXT` and
  `supported_generation_context_versions`.
- `unresolvable` is HTTP 200 with a complete report; it is not an ErrorCode.
- PostgreSQL schema, Alembic revisions and persisted ContextPackage shape are unchanged.
- Environment configuration, Lesson/Exam/PPT request schemas, Task Worker and generation Graphs are
  unchanged.
- Provider/LLM calls, Test/Blind access and external side effects: zero.

## Deterministic behavior

- Unique Evidence IDs are semantic units; unique `(document_id, document_version_id)` pairs are
  sources.
- Requirement alternatives are OR within role/material lists and AND across role, material and KP
  dimensions.
- Complete Evidence groups are derived only from authoritative previous/next relations.
- Optional Requirements are reported but do not block Adequacy or reduce supported target quantity.
- Supported target quantity uses the minimum proportional capacity across required KP, semantic,
  source and semantic-unit constraints.
- `numeric`, `case` and `visual_relationship` require explicit structured metadata. Text and
  character patterns never establish them.
- Supplement rounds classify a current gap as `needs_more_evidence` or `unresolvable`; EP-02 does
  not perform a second retrieval.

## Verification

```text
Focused Generation Context tests
12 passed

Affected contracts, context, feasibility, import-boundary and API regression
85 passed

Final changed Mock/Generation Context regression
19 passed

python -m pytest -q
collection failed before execution: existing duplicate top-level test_schemas module identity

python -m pytest -q --import-mode=importlib
912 passed, 13 skipped

python -m ruff format --check
789 files already formatted

python -m ruff check
passed

python -m mypy src
Success: no issues found in 525 source files
```

The OpenAPI check confirms the new route and strict request/response models. HTTP integration proves
that `unresolvable` returns 200 and dynamic Capability reports operation plus `v1`. Boundary tests
cover no-fallback Local behavior, Remote path/correlation, deterministic reordered metadata and
index/course/tier failure behavior.

## Risks, Exit Gate and next stage

Current persisted semantic metadata is intentionally conservative. Roles or materials that cannot
be established from typed Evidence/KP facts remain missing; this prevents false Adequacy but may
under-count useful prose. Production generation wiring and empirical Dev calibration remain EP-03
and EP-04 work.

EP-02 Exit Gate: **passed**. `EP02-T01` through `EP02-T09` are complete; contract, API, adapters,
determinism, capability negotiation, fail-closed boundaries, regression, Ruff and Mypy checks pass.
There is no database/configuration migration and no real generation-path connection. EP-03 is ready
to plan but is not started by this report.

Rollback removes the new contracts/services/router/mappers, Capability and Port extensions, optional
new packing-limit entrypoint and tests. No persisted data rollback is required.
