# P04 Structured PDF/DOCX Parsing and DOCX Pagination Report

## Phase verdict

- Implementation status: T01-T08 complete; exact r6 approval and corrected formal P04/B0
  evaluation complete.
- Exit Gate: **passed**. Two runs on unchanged Approved DS1 reproduce all metrics, all ten DOCX
  pagination diagnostics and the strict Gate decision.
- Start/end Git commit: `b6483f5ae8a0b3c3e45858c3872b4ed86e94502d` / uncommitted at the
  same commit.
- Branch: `refactor/p00-baseline`.
- Scope protection: no commit, push, PR, public API cutover, Chroma replacement, OCR body text,
  final Chunk/KP implementation, legacy deletion or destructive migration.

## Task completion

| Task | Status | Evidence |
|---|---|---|
| P04-T01 | completed | Frozen Pydantic v2 IR for Document/Page/Block/Line/Span/Section/Table/SourceSpan/Warning/Renderer/Preview/Quality with deterministic JSON, Hashes and stable IDs |
| P04-T02 | completed | PyMuPDF `rawdict` parser retains page geometry, Blocks/Lines/Spans, fonts, BBoxes, images and deterministic reading order; native table records included |
| P04-T03 | completed | `python-docx` parser retains Paragraph/Run/Heading/Numbering/Table/Break/Inline Shape and source Anchors |
| P04-T04 | completed | Fixed LibreOffice `7.4.7.2` headless profile, exact Noto CJK package/font lock, raw artifact retention, canonical PDF and ordered page Manifest |
| P04-T05 | completed | Conservative monotonic DOCX Block alignment; physical page, optional display/Section labels, confidence and warnings; low-confidence pages stay null |
| P04-T06 | completed | Heading hierarchy, TOC assistance, non-destructive repeated header/footer/page-number labels, continuation links and table structure |
| P04-T07 | completed | Parse Preview and Quality Report expose routing, substitutions, unresolved/low-confidence alignment and structure diagnostics |
| P04-T08 | completed; Gate passed | exact r6 remains approved as 55 immutable records; exact OOXML source-unit resolution corrected the formal evaluator binding and two P04/B0 runs reproduced DOCX pagination 10/10 plus every strict Gate check |

## Changed files

### Domain, parsing and pipeline

- `src/courserag/domain/document.py`
- `src/courserag/domain/__init__.py`
- `src/courserag/parsers/__init__.py`
- `src/courserag/parsers/base.py`
- `src/courserag/parsers/pdf.py`
- `src/courserag/parsers/docx.py`
- `src/courserag/parsers/pagination.py`
- `src/courserag/parsers/structure.py`
- `src/courserag/parsers/quality.py`
- `src/courserag/parsers/artifact_bundle.py`
- `src/courserag/jobs/parsing.py`
- `src/courserag/persistence/materialize.py`
- `src/courserag/persistence/repositories.py`

### Evaluation, renderer and configuration

- `src/courserag/evals/parsing_metrics.py`
- `src/courserag/evals/schemas.py`
- `src/evaluation/p04_pilot.py`
- `src/evaluation/ds1_p04_data.py`
- `src/evaluation/ds1_p04_approval.py`
- `src/evaluation/p04_formal.py`
- `src/evaluation/contracts.py`
- `src/evaluation/datasets.py`
- `src/evaluation/schema_export.py`
- `datasets/schemas/v1/courserag_ds1.schema.json`
- `datasets/schemas/v1/courserag_ds1_candidate_manifest.schema.json`
- `datasets/schemas/v1/courserag_ds1_review_decisions.schema.json`
- `datasets/schemas/v1/courserag_ds1_batch_approval.schema.json`
- `datasets/schemas/v1/course_eval_candidate_revision_history.schema.json`
- `datasets/courserag_eval/v1/candidates/ds1/p04_native_docx_r1.json`
- `datasets/courserag_eval/v1/candidates/ds1/p04_native_docx_r2.json`
- `datasets/courserag_eval/v1/candidates/ds1/p04_native_docx_r3.json`
- `datasets/courserag_eval/v1/candidates/ds1/p04_native_docx_r4.json`
- `datasets/courserag_eval/v1/candidates/ds1/p04_native_docx_r5.json`
- `datasets/courserag_eval/v1/candidates/ds1/p04_native_docx_r6.json`
- `datasets/courserag_eval/v1/approved/ds1/p04_native_docx.json`
- `datasets/courserag_eval/v1/provenance/ds1_p04_approval.json`
- `datasets/courserag_eval/v1/reviews/ds1_p04_review_decisions_r3.json`
- `datasets/courserag_eval/v1/reviews/ds1_p04_review_decisions_r4.json`
- `datasets/courserag_eval/v1/provenance/ds1_p04_candidate_manifest.json`
- `datasets/courserag_eval/v1/provenance/ds1_p04_candidate_revision_history.json`
- `resources/renderers/libreoffice_headless_v1/profile.json`
- `resources/renderers/libreoffice_headless_v1/fonts.lock.json`
- `resources/renderers/libreoffice_headless_v1/README.md`
- `src/core/settings.py`
- `compose.yaml`
- `docker/Dockerfile.service`
- `pyproject.toml`

### Tests and governance

- `tests/courserag/parsers/test_document_ir.py`
- `tests/courserag/parsers/test_structured_parsers.py`
- `tests/courserag/parsers/test_docx_pagination.py`
- `tests/courserag/parsers/test_docx_pagination_fixture.py`
- `tests/courserag/parsers/test_structure_quality.py`
- `tests/courserag/test_p04_parse_stage.py`
- `tests/evals/test_parsing_metrics.py`
- `tests/evals/test_ds1_p04_candidate.py`
- `tests/evals/test_p04_formal.py`
- `tests/evals/test_dataset_boundaries.py`
- `docs/refactor/EXECUTION_STATUS.md`
- `docs/refactor/DECISION_LOG.md`
- `docs/refactor/RISK_REGISTER.md`
- this report

## Database, API and configuration impact

- Database: no Alembic revision and no new table. The P04 Stage idempotently materializes immutable
  projections into the P03 `courserag_parsed_documents`, Page, Section and Block facts. A conflicting
  artifact for the same DocumentVersion is rejected instead of overwritten.
- API/Graph: no HTTP route, request/response Schema, Graph node/edge or legacy service behavior
  changed. B0 runtime remains on the existing Local/Chroma path.
- Configuration: additive `COURSERAG_RENDERER_PROFILE_PATH`, `COURSERAG_LIBREOFFICE_PATH`,
  `COURSERAG_RENDER_TIMEOUT_SECONDS`, `COURSERAG_MAX_DOCUMENT_BYTES` and
  `COURSERAG_MAX_PDF_PAGES`, all with bounded/safe defaults.
- Container: service image adds `fontconfig`, exact `fonts-noto-cjk` package and LibreOffice Writer,
  and copies the hash-bound renderer resources.
- Test discovery: `testpaths=["tests"]` prevents repository-local evaluation/cache artifacts under
  `storage_eval/` from being collected as third-party tests; product runtime is unaffected.
- Dataset governance: active Candidate inventory now verifies the Hash of every declared revision
  and excludes only files explicitly marked `superseded`; duplicate IDs among active files remain
  a hard error. No Product runtime path consumes this evaluation-only history.

## Verification

| Command/check | Result |
|---|---|
| `uv run pytest -q` | 298 passed, 5 skipped, 5 dependency warnings in 78.83s |
| `uv run ruff format --check` | 280 files already formatted |
| `uv run ruff check` | all checks passed |
| `uv run mypy src/` | success, 0 errors in 200 source files |
| parser + Stage + metrics + Schema focused suite | 32 passed |
| real 128-page DOCX pagination reproducibility fixture | 1 passed |
| gated owner PDF/DOCX B0 Smoke | 1 passed |
| P03/P04 Stage integration subset | 9 passed |
| dataset validation | CourseRAG 15 records; CoursePilot 4 records |
| JSON Schema export check | 29 Schemas verified |
| `git diff --check` | passed; only existing LF/CRLF conversion notices |
| Secret/temp/fallback audit | no P04 embedded Secret or temp file; parser failures are fail-closed; evaluation policy is `FAIL_RUN` |
| formal DS1 focused suite | 28 passed: Schema, review lineage, 7x4 visible Gold, 6x4 OOXML provenance, single-record r6 delta, Candidate, revision history, data boundaries and isolated approval |
| post-Candidate full Pytest | 308 passed, 5 existing gated skips, 5 dependency warnings in 56.76s |
| post-Candidate Ruff 0.14.5 | 283 Python files formatted; `check` passed; Windows-bind EXE002 ignored because executable bits are not meaningful on the host filesystem |
| post-Candidate Mypy 1.18.2 | success, 0 errors in 202 source files; cache kept under container `/tmp` |
| post-Candidate JSON Schema export | 33 Schemas exported and validated |
| exact approval replay | 55 Approved records; identical Approved and batch-approval Hashes on both runs |
| formal Runner focused tests | 15 passed for approval boundary, strict Gate, Pre-P04 isolation and parsing metrics |
| post-approval full Pytest | 310 passed, 5 existing gated skips, 5 dependency warnings in 56.36s |
| post-approval Ruff | format check: 285 files; lint check passed |
| post-approval Mypy | success, 0 errors in 203 source files; cache kept under container `/tmp` |
| post-approval JSON Schema export | 33 Schemas verified |
| post-approval dataset validation | CourseRAG 125 records; CoursePilot 4 records; Candidate/Approved/Split/lock boundaries pass |
| bookmark-mapping focused regression | 3 passed; exact stress mappings are 19→19, 144→144, 1034→1035, 1614→1615 and 3782→3785 |
| corrected formal P04/B0 double run | P04/B0 metrics, 10 pagination diagnostics and strict Gate are identical; both Gates pass |
| post-repair full Pytest | 311 passed, 5 existing gated skips, 5 dependency warnings in 59.70s |
| post-repair Ruff | format check: 285 files; lint check passed |
| post-repair Mypy | success, 0 errors in 203 source files |
| post-repair Schema/dataset validation | 33 Schemas; CourseRAG 125 records; CoursePilot 4 records |

The first in-sandbox `uv run` attempts were denied access to the user-level uv cache. The exact
commands above were then rerun with read access to that existing cache; no dependency installation
or environment repair was performed.

## Pilot and metric evidence

- Run: `storage_eval/p04_pilot_final3/` (ignored evaluation output, not tracked Gold).
- Run Manifest SHA-256:
  `e92a1b6e239defb43f0d284d8f3cdf75ca4df7f90a366ced23c6ebb339428a88`.
- Report SHA-256:
  `8a7a9a7704c059a8446267da6bc167d2d162139ec1b63d4187c36b5e7a86bdbd`.
- Fresh run completed; `--resume` verified the same identity and skipped successful cases.
- Policy: `fallback_policy=fail_run`, `llm_as_judge=false`, `tuning_enabled=false`,
  `gold_status=no_ds1_gold`, output restricted to `storage_eval/`.

### Native PDF and OCR routing

- Native selected pages: 5 pages, 183 Blocks with BBoxes, 523 text Spans, 68 heuristic headings,
  1 detected table and no warnings.
- Clean-scan route: 5/5 pages emitted `ocr_pending`; no OCR body text was produced.

### DOCX renderer and alignment

| Evidence | Primary DOCX | Layout-stress DOCX |
|---|---:|---:|
| Canonical PDF repeat | pass | pass |
| Page Manifest repeat | pass | pass |
| Canonical PDF SHA-256 | `4642e5c653b265b71bdbf9878218ca058188a9420b8b5930317cf4442c09fb95` | `68c178e0ecb7ef615564bbef92c068037dba20ca600e418e53300b5a92cf570c` |
| Physical pages (candidate, not Gold) | 636 | 128 |
| Selected anchors assigned | 5/5 | 5/5 |
| Minimum selected-anchor confidence | 1.0 | 1.0 |
| Overall page-assignment coverage | 93.20% | 95.49% |
| Unresolved/low-confidence Blocks | 231 | 153 |
| Requested-font substitutions | 18 | 0 |
| Selected anchors with display label | 0/5 | 5/5 |

Raw PDF Hashes differed because of volatile metadata; canonical PDF and ordered page Manifests
matched. The primary result also contains 517 heuristic Sections, 22 tables and 22,520 Runs. These
are diagnostics, not quality scores or Gold.

### Implemented non-generic metrics

Unit-tested metrics cover heading precision/recall/F1 and level accuracy, Section boundary
accuracy, exact page mapping, parse success, OCR character error rate, OCR/noise precision/recall/
F1, reading-order Kendall tau, table structure/cell metrics and BBox IoU. Their formal Pilot values
are intentionally `not_applicable_no_approved_ds1_gold`; emitting scores from parser output itself
would violate the Gold-separation rule.

## Formal DS1 Candidate evidence

- Current Candidate: `datasets/courserag_eval/v1/candidates/ds1/p04_native_docx_r6.json`.
- Candidate SHA-256:
  `7179ce9a48be77118ad68bfa7376bbe69e030f0e69ad0faba8435b0e0ee3c3aa`.
- Counts: Page 15 / DOCX Pagination 10 / Section 20 / Table 10 / OCR 0.
- Label basis: independent Poppler BBoxes/PDF objects, raw DOCX OOXML, original table cells and
  fixed LibreOffice rendered snapshots; no P04 Parser prediction is imported.
- Renderer baseline: LibreOffice Headless 7.4.7.2; canonical primary/stress PDF Hashes are
  `4642e5c653b265b71bdbf9878218ca058188a9420b8b5930317cf4442c09fb95` and
  `68c178e0ecb7ef615564bbef92c068037dba20ca600e418e53300b5a92cf570c`.
- Pagination candidates: primary physical pages 6/44/145/251/618 with display labels null;
  stress physical pages 1/8/33/51/124, retaining only visually observable labels.
- Review lineage: the owner artifact binds exact r3 Hash
  `abbaf5114408990783dd209c3189e5ecfa4332a00aaab8b0e02ec892bdce1ac3`, accepts 54/55 records
  and returns only `ds1-table-docx-020`. r6 preserves all 54 reviewed record Hashes and changes
  only that table relative to r4.
- Table 020 re-recognition: raw OOXML contains a 6x4 source grid with no merged cells, but fixed
  LibreOffice pages 547-548 visibly contain one header row on page 547 and six rows on page 548.
  Per the owner's correction, r6 TableGold is therefore 7x4; the 6x4 OOXML grid is retained in
  the Manifest/review evidence. The r6 card shows both page images and both grids. The unreviewed
  r5 was superseded before delivery after a record-Hash isolation audit.
- Review: offline 55-card package contains 27 local source images and no external resource; the
  54 retained records are pre-checked and only table 020 requires re-review.
- Approval boundary: exact r6 was approved into a physically separate 55-record file; all records
  bind their Candidate Hashes, the batch approval binds both file Hashes, Dev/Test remain empty and
  Test remains unlocked.

## Formal approval and P04/B0 evaluation

- Approved DS1 SHA-256:
  `7e12edb2b66912d915b1d1ca3b7df873edb910cb7dcaf57d07872c83d84964ea`.
- Batch approval SHA-256:
  `e9fdc5fc6d72bf2626e98bab16435f361d8fbef4ef547d0b8fe4f128a7d285b0`.
- Corrected run 1: `storage_eval/p04_formal_ds1_r6_source_unit_fix_run1/report.json`, report SHA-256
  `a14bd1767a1970507402c270b865e29ecb089abe79f8eaa7a2f8e4d6e9240578`; Run Manifest SHA-256
  `7e2ab22c584e76d3ff84790ad5474911ac2536971ecbdcdd5dbb008b0fd2f0ad`.
- Corrected run 2: `storage_eval/p04_formal_ds1_r6_source_unit_fix_run2/report.json`, report SHA-256
  `2f05a8b11246c0670e7c50de0fdb06e94fc24ac30b2d0a3b640356dc05d4e925`; Run Manifest SHA-256
  `aed1629a3e1ca5369d642f21ad4192de3f0fb09ce4cff70c47c3198342cb59dd`.
- Scope: all 55 Approved DS1 records on the Pilot-stage split; this is not locked Test. No tuning,
  LLM Judge, fallback or parser-derived Gold was used.

The earlier report `storage_eval/p04_formal_ds1_r6_verified/report.json` is retained as audit
evidence but superseded for Gate decisions. Its 9/10 score did not identify a product-alignment
failure: the evaluation Runner ignored the Approved bookmark and used the parent source paragraph
index as the fixture paragraph ordinal. The stress fixture inserts Section-break paragraphs, so
the three later bookmarks resolve to parser ordinals 1035, 1615 and 3785. The corrected adapter
uses exact OOXML identities and requires both source-reference and parser-block Hash matches; it
does not search by text.

| Metric | P04 | B0 | Verdict |
|---|---:|---:|---|
| Parse success | 3/3 | 3/3 | pass |
| PDF page mapping | 15/15 | 15/15 | pass |
| DOCX physical mapping | 10/10 | N/A | pass |
| Observable display labels | 5/5 | N/A | pass |
| Observable Section pages | 5/5 | N/A | pass |
| Normalized sample text recall | 780/783 (99.62%) | 781/783 (99.74%) | pass; 0.13-point decline |
| Heading F1 | 1.0000 | 0.0000 | strictly better |
| Section boundary accuracy | 0.1500 | 0.0000 | strictly better |
| Noise F1 | 0.5714 | 0.0000 | strictly better |
| Table cell F1 | 0.9335 | 0.0000 | strictly better |
| Table row/column structure | 9/10 | 0/10 | strictly better |

All four named structural metrics are strictly better than B0 and no common applicable metric
regresses by more than two percentage points. The corrected stress `5.3` binding resolves
`bookmark:src_p_001614` to parser paragraph 1615 and reproduces physical/display/Section values
51/`20`/20 at confidence 1.0. All ten source-reference and parser-block Hash checks pass. Approved
Gold, Candidate, approval records and source binaries were not changed.

## Risks and rollback

- Mitigated limitation: P04-D003 selects the warned fixed-profile renderer and rejects 183 as a
  page-count source. Eighteen substitutions remain visible and require human visual review.
- Resolved: the apparent Approved-anchor failure was an evaluation binding defect, not a product
  alignment defect. Exact bookmark resolution and Hash checks now reproduce 10/10 twice.
- Open but non-blocking: conservative alignment leaves 231/153 unresolved Blocks outside the ten
  selected Gold anchors; changing the threshold requires reviewed labels rather than tuning on
  Test or system output.
- Rollback is additive: disable/remove the structured Parse Stage and renderer configuration; the
  legacy public API, B0 Chroma path and existing Active Index remain unchanged. P03 artifact facts
  are immutable and no destructive downgrade/data rewrite is required.

## Exit Gate

| Criterion | Verdict | Reason |
|---|---|---|
| Same Renderer Profile yields repeatable pagination | passed with recorded warnings | canonical PDF and page Manifest repeat for both DOCX inputs; raw metadata differences remain visible |
| DOCX citations retain pagination and structural Anchor | passed | all selected anchors retain structural source identity; exact OOXML bookmark mapping yields 10/10 physical and 5/5 observable display/Section mappings |
| Structured parsing is better than B0 with no severe regression | passed | all four named structure metrics improve and no common metric regresses by more than two points |
| Approved DOCX pagination mapping | passed | two corrected runs reproduce 10/10 physical and 5/5 observable display/Section mappings |

Overall P04 Exit Gate: **passed**. P05 meets its upstream prerequisite and may start under its own
stage scope; P05 remains `not_started`.
