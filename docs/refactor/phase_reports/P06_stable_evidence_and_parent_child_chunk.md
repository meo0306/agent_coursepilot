# P06 Stable Evidence and Parent-Child Chunk Report

## Phase verdict

- Implementation status: P06-T01 through P06-T08 are complete.
- Exit Gate: **passed**. Chunk profile changes leave source Evidence intact, every emitted Context
  link resolves to validated source Evidence, and the frozen semantic/redundancy metrics have code
  and tests.
- Start/end Git commit: `b6483f5ae8a0b3c3e45858c3872b4ed86e94502d` / uncommitted at the
  same commit.
- Branch: `refactor/p00-baseline`.
- Scope protection: no commit, push, PR, public API change, Graph change, legacy Chunk migration,
  Chroma replacement, Active Index publication, Gold modification or post-P06 implementation was
  performed.

## Task completion

| Task | Status | Evidence |
|---|---|---|
| P06-T01 | completed | Stable `ev1_*` identity binds DocumentVersion, ordered source Block/ranges and exact content Hash; PageBBox and OCR provenance are explicit |
| P06-T02 | completed | Deterministic semantic grouping covers headings, paragraphs, lists, steps, tables, examples and formulas while excluding P05 non-body roles/noise |
| P06-T03 | completed | Course-scoped Resolver, bounded Batch Resolver and Source Preview reconstruct and validate persisted Evidence fail closed |
| P06-T04 | completed | Versioned Chunk Profile/ChunkSet, Parent/Child model, one Parent per Child and exact ChunkEvidence coverage links |
| P06-T05 | completed | Section → Evidence → sentence → checked-token-limit splitting; overlap and hard atomic splits are visible and deterministic |
| P06-T06 | completed | Source deduplication, adjacency, long-unit handling, OCR provenance and coarse DOCX page location preserve auditability |
| P06-T07 | completed_skeleton | P10 migration interface accepts valid same-version stable Evidence, rejects legacy Chunk IDs and marks cross-version mapping for review |
| P06-T08 | completed_gate_passed | two Approved-DS2-only B1/B2 runs reproduce byte-identical system output; all P06-specific metrics have unit tests |

## Changed files

### Domain, Evidence and Chunking

- `src/courserag/domain/evidence.py`
- `src/courserag/domain/chunk.py`
- `src/courserag/domain/document.py`
- `src/courserag/domain/__init__.py`
- `src/courserag/evidence/`
- `src/courserag/chunking/`
- `resources/evidence_profiles/semantic_units_v1.json`
- `resources/chunk_profiles/parent_child_v1.json`

### Stage, persistence and configuration

- `src/courserag/jobs/evidence.py`
- `src/courserag/jobs/chunking.py`
- `src/courserag/persistence/models/content.py`
- `src/courserag/persistence/models/__init__.py`
- `src/courserag/persistence/repositories.py`
- `alembic/versions/2026_08_04_0011-stable-evidence-parent-child-chunks.py`
- `src/core/settings.py`
- `src/courserag/parsers/pagination.py`
- `src/courserag/parsers/normalizer.py`

### Evaluation and tests

- `src/courserag/evals/p06_metrics.py`
- `src/courserag/evals/__init__.py`
- `src/evaluation/p06_evidence_eval.py`
- `tests/courserag/evidence/`
- `tests/courserag/chunking/`
- `tests/courserag/test_p06_stages.py`
- `tests/courserag/test_p06_migrations.py`
- `tests/evals/test_p06_metrics.py`
- `tests/evals/test_p06_eval.py`
- `tests/courserag/test_p03_migrations.py`
- `tests/app/test_streamlit_app.py`
- `tests/integration/test_docker_e2e.py`

### Governance

- `docs/refactor/EXECUTION_STATUS.md`
- `docs/refactor/DECISION_LOG.md`
- `docs/refactor/RISK_REGISTER.md`
- this report

The Streamlit test-path edits anchor the existing app test to the repository path on Windows. The
P03 migration-test edit keeps its parity assertion scoped to the database at revision 0010; the
new P06 test owns 0011 parity and round-trip behavior. Neither change affects runtime behavior.

## Database, API and configuration

- Revision 0011 adds Evidence-to-Block links, Evidence PageBBox facts, Evidence adjacency,
  versioned Chunk Profiles and Chunk Sets. It additively extends existing Chunk and
  ChunkEvidence tables with ChunkSet/Parent/profile/token/warning and coverage-range facts.
- `index_version_id` is nullable for Chunk Sets created before indexing; the FK changes from
  `CASCADE` to `SET NULL`. Downgrade restores the old FK and removes all 0011 facts, so it is an
  explicit operator rollback only after P06 writes stop and Artifacts are retained.
- Application services use Repository methods; no scattered SQLAlchemy query was introduced in
  Evidence or Chunking domain logic.
- Stage fingerprints bind ParsedDocument/Evidence Artifact identity, builder or Chunk Profile,
  exact local tokenizer Hash and configuration. Cache reuse and materialization are idempotent.
- Added settings select the Evidence/Chunk profiles, exact local tokenizer path, maximum batch
  resolve size and Source Preview character limit. Missing or mismatched tokenizer/Profile identity
  fails closed without download or fallback.
- Public HTTP APIs, P01 Port DTOs, CoursePilot Graphs, legacy ORM tables, old Chroma collections,
  B0 behavior and the Active Index are unchanged.

## Evidence and Chunk contracts

- Stable Evidence ID: `ev1_<sha256>` over DocumentVersion, ordered source Block IDs/ranges,
  per-unit text Hashes and combined content Hash.
- Evidence identity intentionally excludes Chunk Profile. Source units, page BBoxes, previous/next
  relations, confidence, OCR engine/model/image/Profile and warning codes remain resolvable.
- DOCX exact Block geometry is not invented. After a successful fixed-renderer alignment, P06 uses
  the real page dimensions with a full-page coarse box and `COARSE_DOCX_PAGE_BBOX`.
- Chunk Profile `parent_child/v1` uses local tokenizer SHA-256
  `ecb6f9fc369894346f0511f4074ca75cee5cd5f3b06d02f1ba35fcd39f8e121d`, Parent limits
  1200/1600/2200, Child limits 250/350/500 and overlap 48.
- Every Child references exactly one Parent. Every Parent/Child records ordered Evidence coverage
  ranges and a coverage Hash; Chunk/ChunkSet identity changes when the Profile changes.
- The citation migration skeleton performs no automatic cross-version or legacy mapping. Detailed
  migration remains P10.

## Formal Approved-DS2 Pilot

### Identity and leakage controls

- Approved DS2 SHA-256:
  `f49d84027cde8341d906e270d29cc46e7b71eb6de4da5220188cb03894436b78`.
- Gold count: 120; Gold remains physically separate and byte-unchanged.
- Product output uses P04 structured Artifacts plus stored P05 RapidOCR runtime output. It is frozen
  before the approved work-package UUID-to-logical-document adapter is applied for scoring.
- Automatic tuning, LLM-as-a-Judge, fallback and system-output-derived Gold are all false.
- B1 is the fixed flat 1000-character/150-character-overlap baseline. B2 uses the checked
  Evidence/Parent-Child implementation and exact local tokenizer.

### Reproducibility

| Artifact | Run 3 | Run 4 |
|---|---|---|
| Run Manifest SHA-256 | `a5a66acece5a1205865a3c5d9c48b28b51123160161960e3c20f0402dce75675` | `c207a94250abc92641924eacd83f4a6ddbebc0b57b5297911bd0209f6576ec50` |
| Report SHA-256 | `79df9f29eeea4b95f3fdaca4df6cedba9cf073b76f61c8de55467a2f87577886` | `586f34579ce2f68ff0db90d82480f1989e66cb8f830554de3e0ac128a77c884d` |
| System output SHA-256 | `bfa6a41e3063520b281da4413a2bce6348b41c85dcb8180f5063fa6b76e6d396` | `bfa6a41e3063520b281da4413a2bce6348b41c85dcb8180f5063fa6b76e6d396` |

Run IDs/timestamps intentionally make Manifest and Report Hashes different. The byte-identical
system output proves deterministic product output under the same inputs/Profile.

### Metrics

| Metric | B1 | B2 | Interpretation |
|---|---:|---:|---|
| Complete semantic-unit rate | 0.833333 | 0.841667 | B2 covers 101/120 versus B1 100/120 |
| Cross-boundary split error | 0.166667 | 0.158333 | lower is better |
| Chunk redundancy rate | 0.042520 | 0.000386 | B2 overlap is limited to explicit child overlap |
| Gold Chunk/Evidence coverage | n/a | 0.841667 | 101/120 Approved units map to B2 Chunk/Evidence |
| Evidence text consistency | n/a | 0.841667 | 101/120 exact normalized Gold units match one runtime Evidence |
| Evidence resolving rate | n/a | 1.000000 | 4,538/4,538 emitted links resolve |
| Runtime Evidence full coverage | n/a | 1.000000 | 1,961/1,961 runtime Evidence records are linked |
| PageBBox consistency | n/a | 0.800000 | 96/120; coarse DOCX pages remain explicit |
| OCR provenance preservation | n/a | 0.800000 | 8/10 Approved OCR-derived cases retain complete runtime provenance |
| Parent expansion sufficiency | n/a | 0.636364 | 35/55 dependency-bearing Gold cases receive sufficient Parent context |

B2 emits 2,230 Evidence records, 1,078 Parent Chunks and 1,327 Child Chunks across the evaluated
runtime documents. The remaining 19 unmatched semantic units are concentrated in upstream PDF
line boundaries and DOCX formula/table structure. They are recorded as quality debt and did not
cause Gold rewriting or a permissive resolver fallback.

## Verification evidence

| Command/check | Result |
|---|---|
| `uv sync --frozen` | passed; 181 packages checked |
| `uv run pytest -q tests/courserag/evidence/` | 6 passed |
| `uv run pytest -q tests/courserag/chunking/` | 3 passed |
| P06 Stage/migration focused tests | 2 passed |
| P06 metric/Runner focused tests | 3 passed, 5 dependency warnings |
| DOCX pagination/parser regression | 15 passed, 5 dependency warnings |
| gated owner PDF/DOCX B0 Smoke | 1 passed |
| final `uv run pytest -q` | 366 passed, 5 skipped, 5 dependency warnings; 59.04 seconds |
| `uv run ruff format --check` | 341 files already formatted |
| `uv run ruff check` | passed |
| `uv run mypy src/` | 0 errors in 239 source files |
| `uv run alembic heads` | `0011_stable_evidence_chunks (head)` |
| `git diff --check` | passed; only Windows LF/CRLF notices |
| Secret/temp/fallback/destructive audit | no real Secret, automatic fallback or tracked temporary evaluation output; downgrade-only removals are documented and were not applied to product data |

The first full test run exposed two test-contract defects: the old P03 parity test included future
0011 ORM facts, and a Streamlit path was CWD-relative on Windows. Both were repaired narrowly;
their three focused tests passed, followed by the clean full result above.

## Risks and rollback

- Evidence/Chunk quality is measurable but not perfect: 19/120 Gold units remain unmatched, OCR
  provenance is 8/10 and Parent expansion is 35/55. These do not violate the P06 structural Gates,
  but P07 must retain the warnings and avoid overstating verified context.
- DOCX page location is deliberately coarse where P04 exposes a page anchor without Block geometry.
  P10 citation UI must display the whole-page scope rather than imply a precise highlight.
- Legacy public search still returns legacy Chunks without stable Evidence. The new P06 pipeline is
  ready, but public cutover and citation migration remain separately gated.
- Rolling back runtime usage means selecting the prior P04 Artifact path/Profile and stopping P06
  materialization; existing P04/P05 Artifacts and Active/legacy indexes are untouched.
- Downgrading 0011 removes P06 relationship/Profile/ChunkSet columns and tables. It must never be
  automatic and was tested only in an isolated temporary database.

## Exit Gate

| Gate | Result | Evidence |
|---|---|---|
| Chunker changes do not lose original Evidence | passed | profile-change test changes ChunkSet/Chunks while preserving the identical Evidence Artifact/IDs; runtime Evidence coverage is 1,961/1,961 |
| Every Context item resolves to original source | passed | 4,538/4,538 emitted ChunkEvidence links resolve through course-scoped, hash-validating Resolver contracts |
| Semantic integrity and redundancy are computable | passed | all P06-specific metrics have implementations/unit tests; two formal runs report semantic completeness, boundary error and redundancy |

Overall P06 Exit Gate: **passed**. P06 is complete and P07 meets its upstream prerequisite. P07
and all later phases remain unstarted.
