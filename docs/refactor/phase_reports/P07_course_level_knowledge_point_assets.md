# P07 Course-level Knowledge Point Asset Pipeline Report

## Phase verdict

- Implementation: P07-T01 through T08 are complete. Exact r2 Protocol, Calibration, exact 0.75
  Threshold Freeze and the single Holdout all completed.
- Exit Gate: **passed**. Explicit KP/Evidence/Chunk N:N modeling and human-approved
  Gold pass. Calibration confirms 19 partition calls and the full 27-call architecture versus
  1,327 B0 Child Chunks (97.9653% reduction). The single Holdout completed without tuning.
- Start/end Git commit: `b6483f5ae8a0b3c3e45858c3872b4ed86e94502d` / uncommitted at the
  same commit.
- Branch: `refactor/p00-baseline`.
- Scope protection: no commit, push, PR, legacy Chroma change, online-retrieval-triggered
  extraction, later-phase implementation or Gold rewrite. Authorized transfer occurred only for
  the approved Calibration partition; Holdout remains untouched.

## Task results

| Task | Result | Evidence |
|---|---|---|
| P07-T01 | completed | deterministic Section/Parent Window builder; 24 scopes become 27 local-tokenizer Windows, maximum 2,981 tokens, one-Evidence overlap, zero oversized Windows |
| P07-T02 | completed_implementation | OpenAI-compatible structured Provider, bounded concurrent runner, transient-only exponential retry, Prompt/Model/Window/Profile cache identity, stale attempt recovery and force rerun |
| P07-T03 | completed | NFKC/casefold normalization, generic/number-only filtering, source-Evidence validation, exact Section deduplication and course-scoped consolidation |
| P07-T04 | completed | persistent KnowledgePoint, Alias, EvidenceLink, derived ChunkLink, optional Parent, extraction Batch/Window/Run and ReviewAction facts |
| P07-T05 | completed | versioned five-component publish score; Provider confidence is trace-only and cannot approve an asset |
| P07-T06 | completed | exact freeze Candidate approved; 0.75 retained before Holdout |
| P07-T07 | completed | authenticated list/detail/modify/approve/reject/deprecate/merge/split HTTP API with version and idempotency contracts |
| P07-T08 | completed | Calibration 19 calls/260,786 tokens; Holdout 8 calls/112,388 tokens; total 27 calls and no fallback/LLM judge/Gold-as-input |

## Changed files

### Domain, pipeline and Provider

- `src/courserag/domain/knowledge_point.py`
- `src/courserag/knowledge_points/`
- `src/courserag/infrastructure/knowledge_point_provider.py`
- `src/courserag/jobs/knowledge_points.py`
- `resources/prompts/courserag/extract_knowledge_points_v1.md`
- `resources/knowledge_point_profiles/default_v1.json`

### Persistence, application and API

- `src/courserag/persistence/models/knowledge.py`
- `src/courserag/persistence/models/__init__.py`
- `src/courserag/persistence/repositories.py`
- `alembic/versions/2026_08_05_0012-knowledge-point-assets.py`
- `src/courserag/application/knowledge_point_service.py`
- `src/courserag/api/knowledge_points.py`
- `src/courserag/api/http_schema.py`
- `src/courserag/api/__init__.py`
- `src/service/service.py`

### Evaluation, configuration and compatibility

- `src/courserag/evals/knowledge_point_metrics.py`
- `src/evaluation/p07_knowledge_point_eval.py`
- `src/evaluation/p07_split_revision.py`
- `datasets/courserag_eval/v1/provenance/ds3_p07_split_r2.json`
- `datasets/courserag_eval/v1/provenance/p07_evaluation_protocol_r2.json`
- `src/core/settings.py`
- `.env.example`
- `src/coursepilot/services/__init__.py`
- `tests/courserag/knowledge_points/`
- `tests/courserag/test_p07_migrations.py`
- `tests/evals/test_p07_knowledge_point_metrics.py`
- `tests/evals/test_p07_knowledge_point_eval.py`
- `tests/evals/test_p07_split_revision.py`
- `tests/coursepilot/test_b0_interface_capture.py`
- `tests/courserag/test_p03_migrations.py`
- `tests/service/test_service.py`

The service-package `__init__` now resolves legacy exports lazily. This removes the pre-existing
fresh-import cycle `agents -> retrieve_nodes -> coursepilot.services -> exam_service -> exam_graph`
without changing the exported service names or runtime behavior. The B0 snapshot itself remains
unchanged; its test requires all frozen routes to survive and permits the six additive P07 routes.

## Database, API and configuration

Revision 0012:

- creates extraction Batch, Section Window, Window Run/cache and Alias tables;
- additively extends KnowledgePoint with normalized name, optional Parent, five-part score,
  extractor identity, status/version and update time;
- makes KP/Evidence and KP/Chunk N:N roles, strength and review/ranking behavior explicit;
- extends review actions with request Hash, Idempotency-Key, before/after snapshots, related IDs,
  response replay and resulting version;
- maps legacy `candidate` to `unreviewed` on upgrade and restores that legacy label on downgrade.

The reviewer API lives under `/api/courserag/v1`, shares the existing bearer dependency and returns
the frozen Request/Trace/ResponseMeta/Error contract. Writes require `Idempotency-Key`, `If-Match`
and `X-Reviewer-ID`. Merge is same-KB only, split Evidence assignments must be disjoint and complete,
Parent links reject cross-KB/self/cycles, and no API automatically creates `approved` Gold.

P07 settings select `COURSERAG_KP_*` first and inherit blank model/base/key fields from matching
`COMPATIBLE_*` values. Local validation confirmed all required values are present without logging
them. The default Provider is fail-closed; there is no free-form parse, automatic endpoint/model
fallback, reasoning/thinking parameter or online retrieval trigger.

## Pipeline and score contracts

- Window identity binds course/KB/Section, ordered stable Evidence IDs, exact content Hash and
  Window Profile Hash.
- Cache identity additionally binds Provider, model, Prompt Hash and extraction Profile Hash.
- Only transient rate/timeout/connection failures retry; schema or identity failures fail the
  Window and remain manually rerunnable.
- Candidate references must belong to their exact Window and include a primary Evidence link.
- Exact normalized consolidation is course-scoped. Parent output remains a suggestion until review.
- Score weights are evidence 0.35, naming 0.20, cross-window 0.20, ambiguity-safety 0.15 and
  duplicate-safety 0.10. Passing 0.75 yields `unreviewed`, never `approved`.
- Chunk links are deterministically derived from stable Evidence links. Changing a Chunk profile
  can rebuild those links without changing the KP/Evidence facts.

## DS3 Pilot status and data reuse

No duplicate Gold construction occurred. The Runner uses:

1. stored P06 `run-4` runtime Evidence as Provider input;
2. the existing 24 approved source scopes only to bound those runtime Evidence records;
3. exact Approved DS3 SHA-256
   `339a51f6f8f8fedeb533b6cbe0efa3ad96783dbae9580a4309924b63358b9566`
   only after system output is frozen;
4. the existing P06 UUID-to-logical-document adapter for post-output Evidence scoring.

The Runner is configured for Pilot, `tuning_enabled=false`, `fallback_policy=fail_run` and no
LLM-as-a-Judge. It supports atomic checkpoint/report writes and configuration-difference rejection.
It will report all 107 Gold items and the P06-resolvable subset separately, retaining the known
19/120 upstream Evidence gap instead of rewriting Gold.

Static Window construction produces 27 planned Provider calls versus 1,327 P06 Child Chunks, a
projected reduction of 97.9653%. This proves the “not one call per Child Chunk” architecture but is
not represented as an actual cost/latency result.

### Blocking findings

- Threshold freeze: exact r2 Calibration selects the existing 0.75 threshold. Candidate Bundle
  `c4406f507a5a4350fb254cc299adb9c5071b3664a7fdb61a4f77dd7578eda1e9` binds report Hash
  `020975e96aa8912514771373061d44b06e8e62229b9eeba253371603595d4f41`, system-output Hash, Approved
  Gold Hash and Protocol Hash. Holdout is blocked until exact owner approval.
- Quality: all-Gold exact-name F1 is `0.073825`; matched-item Evidence Link precision/recall are
  `0.75/0.818182`. Threshold tuning does not repair extraction/naming quality, so P07-R09 remains
  measured debt rather than using Holdout for further tuning.

## Verification

| Command/check | Result |
|---|---|
| `uv sync --frozen` | passed; 181 packages checked |
| P07/DS3/API/migration focused suite | 39 passed |
| r2 split/protocol and existing P07 evaluation focused suite | 10 passed; Mypy 0 error; Ruff passed |
| threshold freeze and corrected P07 evaluation focused suite | 9 passed; exact 0.75 Candidate deterministic |
| Resume/post-validation/Provider focused suites | 21 passed; only invalid Case reopens; bounded transient retry passes |
| B0 interface + P03/P07 migration repair suite | 6 passed |
| gated user DOCX/PDF B0 Smoke | 1 passed |
| final `uv run pytest -q` | 396 passed, 5 gated skips, 5 dependency warnings |
| `uv run ruff format --check` | 372 files already formatted |
| `uv run ruff check` | passed |
| `uv run mypy src/` | 0 errors in 257 source files |
| `uv run alembic heads` | `0012_knowledge_point_assets (head)` |
| `git diff --check` | passed; Windows LF/CRLF notices only |
| P07 Calibration integrity | report completed; Secret absent; Gold Hash unchanged; zero fallback/LLM judge/Gold-as-input; Holdout directory absent |

The first full test run reported 394 passed, 5 skipped and two test-contract failures. One expected
the entire B0 route snapshot to remain identical despite additive P07 APIs; the other compared
0010 tables to future 0012 ORM metadata. The snapshot was not rewritten. Tests were narrowed to
their true revision/compatibility boundaries, their 6-test repair suite passed, then the clean
396-test run passed.

## Risks and rollback

- Provider `json_schema` returned HTTP 400; explicit configured `json_mode`, exact Prompt contract
  and Pydantic validation completed all Calibration Windows. Method is identity-bound; no free-form
  or alternate-Provider fallback exists.
- The r2 split and Calibration are approved/completed, but 0.75 cannot be used for Holdout until
  the exact threshold-freeze Candidate is approved. Low exact-name F1 remains visible quality debt.
- Downgrading 0012 removes Window/cache/Alias/review version facts. Stop P07 writes and retain
  artifacts/audits before an explicit operator downgrade; never use downgrade as cleanup.
- Rollback of runtime use is configuration-only: disable the KP Provider and stop scheduling the
  offline KP pipeline. Existing P06 Evidence/Chunks, Active indexes, old Chroma and legacy APIs are
  untouched.

## Exit Gate

| Gate | Result | Evidence |
|---|---|---|
| KP and Evidence/Chunk are explicitly N:N | passed | 0012 tables/links, Repository materialization, idempotency and integrity tests |
| Extraction calls are clearly lower than B0 | passed | Calibration 19 + Holdout 8 = 27 calls vs 1,327 B0 proxy (97.9653% reduction) |
| Formal Gold is human approved | passed | exact Approved DS3/Approval chain is reused unchanged; runtime outputs cannot approve Gold |

Holdout used 32 Gold / 7 Scopes / 8 Windows and produced 83 candidates: exact-name precision
`0.048193`, recall `0.125`, F1 `0.069565`; Evidence Link precision/recall `1.0/0.75`. Report SHA-256
is `7220beea3c8d9a28475c247141b5f33be8d246811adf7f7440a73f65fc8ebeae`.

Final verification: `uv sync --frozen` checked 181 packages; B0 Smoke 1 passed; full Pytest 407
passed / 5 skipped; Ruff format 376 files, Ruff check and Mypy 259 source files passed.

Overall P07 Exit Gate: **passed**. P08 meets its start prerequisite, but P07-R09 remains measured
non-blocking extraction/name-normalization quality debt.
