# Pre-P04 DS1 input Candidate and approval report

**Date:** 2026-07-29  
**Task scope:** ED-PRE04-T01 through ED-PRE04-T05, first human checkpoint  
**Status:** exact-Hash input selection approved by `course_owner`  
**P04 implementation status:** not started  
**Gold status:** `ds0_pilot_approved`; no DS1 Gold

## 1. Outcome and approval boundary

The P04 annotation input Candidate is source-grounded, deterministic and has been explicitly
approved by the course owner. It selects inputs only; it does not assert Parser correctness,
approve DS1 Gold, assign a
DOCX page number, create OCR transcription, populate Dev/Test or lock Test.

- Candidate: `datasets/courserag_eval/v1/candidates/work_packages/p04_input.json`
- Candidate file SHA-256:
  `b305f328a8e76555e661e048f34c7ea7c89ed82c9fb9982f4877e1b6a80df582`
- P03 identity snapshot:
  `datasets/courserag_eval/v1/provenance/p03_eval_identity_snapshot.json`
- Identity snapshot SHA-256:
  `ed489003274a7e136ffe39b900e8d2a07f428a1e79176605c4d6bcc2f6765609`
- Approved DS0 file SHA-256:
  `d9174a4dd75182b608ed161d803acb9ddb8bc16f0aa1933641b2328326eb1306`
- Fixture Manifest SHA-256:
  `b4f6f71ddc63d25e89fdc608e818e645d9d20558566ff09ea64a2b74d1c2d7b7`
- Approved work package:
  `datasets/courserag_eval/v1/approved/work_packages/p04_input.json`
- Approved file SHA-256:
  `06700604f3c69724090ee6a995c2696b41278f5bf45d64e90beeddba4a484e5c`
- Approval review ID: `review-pre-p04-input-20260729-01`
- Candidate canonical record digest:
  `4834154e4834d6049d9d53e11d20bd730224ee13c264350397248e3d6e2dbbc9`
- Approved canonical record digest:
  `8d1465d604b64320209c1ad18924a8f3ebe7806a14846115544d87500221288f`
- Manifest `phase_input_status.p04`: `approved_for_annotation`

`course_owner` explicitly replied “批准” to the blocking question naming the Candidate file Hash
above. The approval CLI verified that file Hash before creating the Approved package and appended
one review entry. An identical replay retained the same Approved file and kept the review log at
eight lines. A future content change requires a new Candidate revision and review event.

## 2. Isolated P03 identity evidence

The evaluation database is isolated as Compose project `coursepilot_eval_p04`, named database
`coursepilot_eval`, and loopback-only endpoint `127.0.0.1:55432`. Alembic is at
`0009_courserag_content`. Candidate verification found exactly 2 KnowledgeBases, 6
SourceDocuments, 6 DocumentVersions, 6 BuildJobs, 6 Build-to-version links, 6 successful inventory
Stage runs and 6 Artifacts. Every Build links exactly one DocumentVersion. KnowledgeBase status is
`empty`, document/version status is `registered`, and the successful Build means only
`p03_inventory`; it does not claim parsing, indexing or Ready state.

### 2.1 Algorithms-system lineage

- `doc_ai_algorithms_systems` (Primary, retrievable)
  - KB `4fb3279f-1ec5-5906-b34e-8831bd16f613`
  - SourceDocument `ff159def-fccd-57c6-a025-241be4b29ad8`
  - DocumentVersion `fa0b5b36-a126-5c7f-aefb-a368d6656b38`
  - binary SHA-256 `c93df4cb4bb533e381647e7591104ff06ecc6a486582d77b3e6d63511428066b`
  - Build `163e8584-9000-5cea-8744-d362df16a04d`
  - request `b0eee7dc44c4cbc3020e5fc1b82f70df2c9f7861bbc77e003f3d014a4aa52753`
  - Stage fingerprint `be12bfe48b37627b0a1031112f89ff549e29024f0f9d5a6340355ecdf6f440b9`
  - Artifact `52a70e89b9433999123961e457d86cafcbfc1079dd38750db48fd5dd8a91ccf4`
- `doc_ai_algorithms_systems_structure_stress` (derived, non-retrievable)
  - SourceDocument `a98859b6-c3be-5b68-a646-730321534fa0`
  - DocumentVersion `cbecf1f1-078f-50f4-b622-f41c95d773a4`
  - binary SHA-256 `a848d60e97f28aef93877bea63dfea1bb8c9303843a8e0a27b7939c3b4fdb72b`
  - Build `805955b8-8418-5dbc-81c0-6bf33a98110c`
  - request `b9b4916c80658a4dc97e72ae3d5c5ab37b46399d519a90f0782319958a4a0ccb`
  - Stage fingerprint `8ba13ba837f83bc566ec9a0633f47b8dedb99fee8b4af6c8dea316d8487cd2e5`
  - Artifact `e7535567e129048d50ccc982661990016280389a3906dd380f3d122e4f975a4a`

### 2.2 General-education lineage

All four documents use KB `4f382422-d935-5185-8b1d-2ce859aec954`.

- `doc_ai_general_education_excerpt` (Primary, retrievable): SourceDocument
  `fa7a67cf-2287-5f98-913f-98404bb19647`; DocumentVersion
  `43a4cb5f-6e5f-5f20-98c4-9b3f8b6f4821`; binary
  `15344771664d40cf190be7790be3d266eb94a2798a4c2608fcf4d1ffa8fd231d`; Build
  `ea6adf19-9aab-5bb8-b3ef-cff09b6e3faa`; request
  `47dfe2e9e7100f091b4a398bb40c4421d4a4463defd0fce824b7c8f5424e8410`; fingerprint
  `0def3669f48a13940267d0410e9568f94ed5eb375bddf80dbc02d635e51e45bd`; Artifact
  `4a53c8de5b2c921f4d3ba8b2b4f5d4d5fa28a5419584fd3328e55e5c6818b0a1`.
- `doc_ai_general_education_mixed` (derived, non-retrievable): SourceDocument
  `ad342782-83a0-5372-8c09-a93e582599e1`; DocumentVersion
  `d9739a2d-de77-571c-9de7-e1c451e68f4c`; binary
  `f5d384f9affff159c78a9f3654a0ec918c05a0ba8370405da9e8fd030d073e4a`; Build
  `34b28129-d717-5828-a353-83f35ce5cb78`; request
  `7e1949842ef4b045251f597f1f1ef45a6fe4595b031d17c24147a4b0d80582b8`; fingerprint
  `bf7ee9a9009d070f08176387e9d3a078a2e48989b1bf6f37615992ca2d8f2ef2`; Artifact
  `61a79f9bc14363de7fab4f78870cf0473c6a663abc1826a6c0a9735c2c87854b`.
- `doc_ai_general_education_scan_clean` (derived, non-retrievable): SourceDocument
  `1280f0ac-c7a1-5b04-98eb-a0682500fe30`; DocumentVersion
  `445c6c7e-2aea-5739-8bbd-5d757ad7d3f5`; binary
  `4f0166c18e79aa29d06ef2d32597d532b76da17a53292a09e58b5b7e783df7a1`; Build
  `4a398b47-2958-5da0-82e7-5547061af8cb`; request
  `76dadbb561fd61706a5cdc24b34d227fa73e902ca62f0fe45ff12d9466e2dcd9`; fingerprint
  `8e9162e49b5f6e4b109fff14439b8e826845efe3205cd0c3580d6d9ae641fabf`; Artifact
  `6a7fcb9af386c9e8609189d6ee1fa9c6dad7124dbc56b7a6cd43087996642a6c`.
- `doc_ai_general_education_scan_compressed` (derived, non-retrievable): SourceDocument
  `96ce8323-c0c5-564e-81d0-2fb566828c40`; DocumentVersion
  `c28ce27d-ec17-5862-ab00-02c639162101`; binary
  `81b678dbf4737eafcbadbf6c7c9d3c8b92b955eccd6a8f1a4c28cbed98e93554`; Build
  `a71318c8-56e2-5ca4-86f4-3899b572cb63`; request
  `0eaedfb9ac1f159aeddf1e198efa7d8e1aa11cba1c1de17c3e448a1509a01e63`; fingerprint
  `770b17babf6d779fd8d72377673e656698b81b6b4ac9aaec722653876d5edd3f`; Artifact
  `f999efe3ad477b8f58d8c3c81d63eab26991c7ef66b18a53cb322a2e5b38bc7f`.

Artifact URIs are exactly `artifact://sha256/<artifact hash>` and contain no host path or Secret.

## 3. P04 input selections

### 3.1 Native PDF pages

The 15 source physical pages are `5, 10, 11, 12, 15, 18, 20, 21, 23, 24, 26, 27, 30, 31,
32`; Pilot pages are `5, 10, 12, 20, 32`. Each record binds the Primary PDF DocumentVersion and
the actual page-text SHA-256. Visual QA rendered all 15 pages: content is readable and not cropped;
the set covers the two-column contents page, mind map, figures, dense prose, the page-20 table and
Section boundaries. Poppler reported missing Adobe-GB1/SimSun mapping warnings while rendering,
but the rendered glyphs were visually present; P04 must still freeze and test its own Parser and
Renderer dependencies.

### 3.2 DOCX pagination anchors

The Primary and structure-stress documents each contain these five mirrored anchors:

| Paragraph | Anchor | Exact source text | Source-text SHA-256 |
|---:|---|---|---|
| 19 | 1.1.1 | 1.1.1 类人行为智能：图灵测试法 | `4237a2b177515ca4ca5e1876b074f0ec809e95072dd7275abd169c2173d484a2` |
| 144 | 2.2 | 2.2 感知机与多层感知机 | `e107a8b4b906ec9aaf5241f1c7438e3cb2e5348575ff72a9b64e8490cda2f3d9` |
| 1034 | 3.5.3 | 3.5.3 注意力机制和Transformer | `315c2ceeef5073a7bff89cca37c8c634c43835bf796378a2c51fb5ade1c961d0` |
| 1614 | 5.3 | 5.3 大模型的微调与对齐 | `8b4c721ec3698a1e2378e8b41097dd20bfe06b18b420272ddb06651657ce585c` |
| 3782 | 9.7 | 9.7 全面融入人类生活的大模型技术 | `fb9470e8dae001e387da7d539db152c53f242cbbeee8c56c1e0ce5052c39b441` |

The stress mappings are bookmarks `src_p_000019`, `src_p_000144`, `src_p_001034`,
`src_p_001614` and `src_p_003782`, and their text Hashes match the Primary source units.

### 3.3 Section candidates

- PDF (8): `1.1.1`, `1.1.2`, `1.2.1`, `1.2.2`, `1.2.3`, `1.3.1`, `1.3.4`, `1.4.1`.
- DOCX (12): `1.1.1`, `2.2`, `2.2.2`, `3.1.3`, `3.5.3`, `5.1.1`, `5.2.1`, `5.3`,
  `6.2.2`, `6.2.3`, `9.1.2`, `9.7`.

PDF titles preserve the exact extracted full-width spacing and plus characters before hashing;
DOCX titles preserve exact paragraph text and paragraph index. These are selection anchors, not
P04-predicted Section boundaries.

### 3.4 Table candidates

- DOCX table indices: `0, 1, 6, 8, 10, 12, 18, 20, 21`.
- Their source headings are respectively: `2.2.2 模型与原理`, `3.1.3 深度学习应用场景`,
  `5.1.1 大模型的定义与特征`, `5.3.4 实践：大模型微调实现酒店住宿评价情感分类`,
  `6.2.2 神经辐射场三维重建`, `6.2.3 3D高斯点染三维重建`,
  `9.1.2 技术原理：可穿戴技术与人工智能`, `9.2 智能侦察`, `9.5.1 智慧服务系统概述`.
- PDF physical page 20: exact extracted anchor `表1-1　部分职业的被淘汰概率`.

The Candidate stores each DOCX table matrix Hash and observed row/column counts, and stores the
PDF page-text Hash. It does not supply P04 table-cell Gold.

### 3.5 OCR route-only candidates

| Fixture | Fixture page -> parent physical page | Representation |
|---|---|---|
| clean | `1->21, 2->23, 3->24, 4->26, 5->30` | `raster_lossless` |
| compressed | `1->11, 2->15, 3->18, 4->27, 5->31` | `raster_jpeg` |
| mixed | `9->9, 22->22, 25->25, 29->29, 32->32` | `raster_jpeg` |

All 15 records say only `route_to_ocr_pending`. Transcription, regions, BBox, OCR confidence and
OCR Gold are absent.

## 4. Isolation and pending P04 fields

Both courses use separate KnowledgeBases and every build contains one document. Primary and
derived documents share one mutual-exclusion group per course, but no Build mixes variants.
Derived fixtures are non-retrievable and may be used only for parsing, pagination, OCR or migration
tests. Six evaluation documents represent only two independent semantic sources.

The following fields remain for P04 annotation/output: reading order, regions/noise, Section
boundaries, table cells, DOCX physical page index, displayed page label, Section page index,
Renderer/font/profile manifests, rendered PDF Hash and alignment confidence. The historical DOCX
file-property value `183` and QA-only LibreOffice observation `128` are not page Gold.

## 5. Verification evidence

- `uv sync --frozen`: passed in isolated `storage_eval/pre_p04_env`; no dependency declaration or
  lock change.
- Compose merged config and fixed loopback port: passed; PostgreSQL healthy during validation.
- Alembic upgrade: `0009_courserag_content`.
- Seeder final repeated runs: identical Candidate/snapshot Hashes and invariant 2/6/6/6/6/6/6
  row counts; zero multi-document Builds.
- Schema export/check: 29 Schemas, no mismatch.
- Pre-P04/P03/evaluation focused tests: 38 passed; five third-party PyMuPDF SWIG warnings.
- Dataset validator: CourseRAG 15 existing DS records and CoursePilot 4 records valid; Candidate
  work package separately validates against the new strict Schema.
- Full project suite with isolated bytecode cache: 279 passed, 5 explicit gated skips, five
  third-party PyMuPDF SWIG warnings.
- A first bare `pytest -q` also collected ignored `storage_eval/uv_cache_pre_p04` dependency test
  trees and failed during third-party collection; explicit repository `tests/` is the valid suite.
  The existing Streamlit test additionally reused a Linux `/workspace` bytecode path on its first
  Windows run; a clean bytecode cache made it pass, followed by the clean 279-test full result.
- Ruff format: 260 files already formatted. Ruff lint: all checks passed.
- Mypy: no issues in 187 source files.
- PDF visual QA: all 15 selected pages rendered and inspected, with no crop/content-loss finding.
- DOCX structure QA: all five anchors and nine tables resolve to exact source units/Hash; no P04
  pagination claim was made.
- Approved work package and review Hash chain valid; Manifest Gold unchanged; Dev/Test empty;
  Test lock false.

## 6. Database/API/configuration and rollback

- Public HTTP API and runtime behavior: no change.
- Product database and business rows: no change.
- Database migration files: no new migration; existing 0008/0009 applied only to the isolated
  evaluation database.
- Configuration: one evaluation-only Compose port override; no Provider or model configuration.
- Approval CLI: additive, fail-closed on Candidate file Hash, executed once and replayed
  idempotently without appending a duplicate review.
- Container lifecycle: stop the isolated PostgreSQL service after verification and retain the
  named volume for P04. No volume, source file, historical Candidate or business data is deleted.

## 7. Gate and next action

ED-PRE04-T01 through T05 pass. P04 remains `not_started`, but its input gate now passes and it may
enter its own audit/implementation flow. Approval applies only to the fixed annotation inputs.
DS1 Gold remains absent until P04 output is separately generated, independently annotated and
explicitly approved.
