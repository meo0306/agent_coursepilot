# P05 OCR Page Routing and Mixed-page Merge Report

## Phase verdict

- Implementation status: P05-T01 through P05-T07 are complete.
- Exit Gate: **passed**. OCR Gold is page/region-addressable, low-confidence/resource failures
  are visible, and the owner-selected RapidOCR `default_v1` is repeatable under its explicitly
  approved 90-second limit.
- Start/end Git commit: `b6483f5ae8a0b3c3e45858c3872b4ed86e94502d` / uncommitted at the
  same commit.
- Branch: `refactor/p00-baseline`.
- Scope protection: no commit, push, PR, public API change, Graph change, Chroma replacement,
  Active Index publication, OCR-derived Gold or post-P05 implementation was performed.
- Runtime default: `COURSERAG_OCR_PROVIDER=rapidocr`, Profile `default_v1`; explicit rollback is
  `COURSERAG_OCR_PROVIDER=disabled`.

## Task completion

| Task | Status | Evidence |
|---|---|---|
| P05-T01 | completed | Configurable native/ocr/hybrid classifier, explicit features/reasons, force-OCR and Profile Hash; 15 Approved OCR positives plus 15 Approved native negatives score precision/recall/F1 1.0 |
| P05-T02 | completed | Common OCR contract, bounded subprocess guard and fail-closed RapidOCR/Tesseract/PaddleOCR adapters; no automatic Provider fallback |
| P05-T03 | completed | Engine/model/Profile/image identity, DPI, text, pixel/page coordinates, confidence, warnings, duration/RSS, deterministic Artifact and additive reversible 0010 persistence |
| P05-T04 | completed | Native/OCR coordinate merge, NFKC/whitespace matching, IoU/text deduplication, native priority, stable order and retained raw OCR provenance |
| P05-T05 | completed | Configurable timeout plus 20MP and 1.5-GiB limits; timeout/memory/crash/empty/low-confidence paths become visible warnings or fail-closed identity errors |
| P05-T06 | completed | Exact r3 Gold approved idempotently; two isolated runs each of RapidOCR, Tesseract and PaddleOCR used the same 15 Approved PNGs and frozen resource envelope |
| P05-T07 | completed | Owner selected RapidOCR and confirmed 90 seconds; two fresh `default_v1` runs complete 15/15 pages without warnings and reproduce every per-page semantic Hash |

## Changed files

### Domain, parser, Stage and persistence

- `src/courserag/domain/document.py`
- `src/courserag/parsers/page_classifier.py`
- `src/courserag/parsers/pdf.py`
- `src/courserag/parsers/normalizer.py`
- `src/courserag/parsers/artifact_bundle.py`
- `src/courserag/parsers/ocr/`
- `src/courserag/jobs/ocr.py`
- `src/courserag/persistence/models/document.py`
- `src/courserag/persistence/materialize.py`
- `src/courserag/persistence/repositories.py`
- `alembic/versions/2026_08_02_0010-expand_ocr_page_results.py`

### Evaluation, data and runtime profiles

- `src/courserag/evals/schemas.py`
- `src/courserag/evals/ocr_metrics.py`
- `src/evaluation/p05_ocr_data.py`
- `src/evaluation/p05_ocr_approval.py`
- `src/evaluation/p05_ocr_eval.py`
- `src/evaluation/p05_ocr_compare.py`
- `src/evaluation/p05_ocr_runtime.py`
- `src/courserag/parsers/ocr/runtime_profile.py`
- `resources/ocr_profiles/`
- `datasets/courserag_eval/v1/candidates/ds1/`
- `datasets/courserag_eval/v1/approved/ds1/p05_ocr.json`
- `datasets/courserag_eval/v1/provenance/p05_ocr_approval.json`
- `docker/Dockerfile.eval-ocr`
- `docker/Dockerfile.service`
- `compose.eval-ocr.yaml`
- `compose.yaml`
- `.dockerignore`
- `pyproject.toml`
- `uv.lock`
- `src/core/settings.py`

### Tests and governance

- `tests/courserag/parsers/`
- `tests/courserag/test_p05_ocr_stage.py`
- `tests/courserag/test_p05_migrations.py`
- `tests/evals/test_p05_ocr_data.py`
- `tests/evals/test_p05_ocr_eval.py`
- `tests/core/test_settings.py`
- `docs/refactor/EXECUTION_STATUS.md`
- `docs/refactor/DECISION_LOG.md`
- `docs/refactor/RISK_REGISTER.md`
- this report

## Database, API and configuration

- Migration 0010 additively expands `courserag_ocr_page_results` with status, model/Profile
  identity, DPI/image dimensions, OCR text/regions, result Hash, duration, peak memory and
  creation time. Existing rows may remain `legacy_incomplete`; no synthetic backfill is used.
- PostgreSQL round-trip `0009 -> 0010 -> 0009 -> 0010` passed. Downgrade removes the new OCR
  columns and is therefore an explicit operator rollback only; it was not applied to product data.
- The P05 Stage fingerprint binds the P04 Artifact, source/image Hash, Provider, model Manifest,
  Profile, DPI, routing rules and resource limits. Cache/resume rejects identity drift.
- Public HTTP APIs, CoursePilot Graphs, legacy Parser/Chroma, ORM legacy tables, Active Index and
  B0 behavior are unchanged.
- Candidate engines remain isolated. Runtime networking is disabled and model binaries are not
  committed. The default service build recipe installs only RapidOCR and creates a resolved
  model/Profile identity during image construction; Tesseract/PaddleOCR are not included.
- Additive OCR settings now default to RapidOCR and `default_v1`: 200 DPI, 20MP, 90 seconds,
  1.5 GiB and one Worker. No unreported fallback exists, and setting Provider=`disabled` restores
  the prior P04 `ocr_pending` behavior.

## Gold approval and reuse

- Active Candidate:
  `datasets/courserag_eval/v1/candidates/ds1/p05_ocr_r3.json`.
- Candidate SHA-256:
  `c203f05d2cccc5cd5fcf557a7a5eed19d86c4ecae181cd14d88a863792baa065`.
- Candidate Manifest SHA-256:
  `9aa1a9f0229d10455680ec9f5724b933298671b5b9f6fa8e1c747630bb680e56`.
- Offline review index SHA-256:
  `8446888b1836943c8c90efeca7c9cc53caef2f6deb4aed340c81920d099e0fb2`.
- The Course Owner explicitly approved that exact Candidate Hash.
- Physically separate Approved file SHA-256:
  `62824129f3525a90bcbdd3d4570d9aa6a3768c0db6949c3c2ceafa7e7ce53c51`.
- Batch ApprovalRecord SHA-256:
  `f81b2e71d97e75eb22e40a6f8e14790e2d72877db3b0f7d326c905c0b7669af0`.
- Approval replay returned the same Hashes and did not duplicate review records.
- The 15 records cover five clean lossless scans, five compressed scans and five rasterized
  mixed-document pages. Eleven source-page annotations reuse exact Approved P04 PageGold; only
  source pages 9, 22, 25 and 29 required new source annotations.
- Gold is derived from exact native parent-PDF text/geometry and fixed 200-DPI mappings, never
  from an OCR Provider result.
- Raw text/regions remain complete. The body projection excludes headers, footers, page numbers,
  QR-related regions, figures, embedded-image text and full figure captions. Same-baseline figure
  numbers and names are grouped as one caption boundary; right-column/continuation order on
  `ds1-ocr-12` remains explicit.
- r1 and r2 remain immutable superseded audit revisions; they were not deleted or approved.

## Real-engine Pilot evidence

All six runs used the same 15 Approved PNGs, 200 DPI, one CPU, one Worker, 60 seconds per page,
1.5 GiB RSS and no runtime network. Macro CER below is the approved body projection.

| Engine/run | Macro CER | Micro CER | Region Recall@0.5 | Mean IoU | p50 / p95 ms | Peak RSS bytes | Fail/resource pages | Semantic repeat |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| RapidOCR 1 | 0.076073 | 0.110476 | 0.687151 | 0.648157 | 54,820 / 60,026 | 737,906,688 | 1 | no |
| RapidOCR 2 | 0.009765 | 0.009887 | 0.779330 | 0.661689 | 50,535 / 59,320 | 736,919,552 | 0 | no |
| Tesseract 1 | 1.240041 | 1.133333 | 0.036313 | 0.126235 | 10,248 / 60,051 | 158,191,616 | 6 | yes |
| Tesseract 2 | 1.240041 | 1.133333 | 0.036313 | 0.126235 | 8,630 / 60,037 | 158,568,448 | 6 | yes |
| PaddleOCR 1 | 1.000000 | 1.000000 | 0.000000 | 0.000000 | 14,505 / 15,812 | 776,945,664 | 15 | yes, repeatable failure |
| PaddleOCR 2 | 1.000000 | 1.000000 | 0.000000 | 0.000000 | 14,723 / 16,068 | 777,756,672 | 15 | yes, repeatable failure |

RapidOCR is the only quality-capable candidate, but `ds1-ocr-04` timed out in run 1 and completed
in run 2, so it is not semantically repeatable at the frozen 60-second boundary. Tesseract is
repeatable but unsuitable on quality and completion. The locked PaddleOCR CPU runtime fails all
15 pages with a oneDNN/PIR attribute-conversion error; a separate oneDNN-disabled diagnostic did
not finish its first page within 120 seconds and therefore already exceeds the frozen limit.
PaddleOCR is local inference and requires no API key; its failure is unrelated to user API
configuration.

### Run and comparison identities

| Artifact | SHA-256 |
|---|---|
| RapidOCR run 1 report | `bccaa24601c432f3005a9afd13e7f9e6b615b16eac63dbe69263842f93eb98bc` |
| RapidOCR run 2 report | `a8039ac837b1910a5936abe664f5c744a02b7a4df89d702166e09c66489e431f` |
| Tesseract run 1 report | `b6f91bb5d6ce9c7fd7417b04da8a98b05046f8b6657c72a4c01597634e1dce93` |
| Tesseract run 2 report | `0ecb41c4e9569a60c7ccc2345d06891e9770df94f32e10ff17dd902d88a879df` |
| PaddleOCR run 1 report | `e74fa78e258aae6c8e92ebc5fbb53b6f557a2598edb4ff58bcfa5ad6085645e1` |
| PaddleOCR run 2 report | `da7b144961a9231adb6cbe6d2178c5676a4ea1699abbd3c07b1d182f4b0da750` |
| Deployment evidence | `7dd31d3531d2c675952a617ef3918e0580eefb1a7bc0eba954fcc20b12bd6edf` |
| Selection-neutral comparison | `34cb6ad407eba3b5fdfeaaa72c5fb325203ca784573fe9563a3e92245659630a` |

The comparison has `default_selection=requires_explicit_human_decision` and no automatic
composite score.

### Human-selected `default_v1` validation

The owner selected RapidOCR and explicitly confirmed a 90-second hard timeout. No other resource
limit changed. A fresh runtime Profile was resolved inside the same immutable RapidOCR image and
then executed in two new, independent, network-disabled containers.

| Default run | Macro / Micro CER | Region Recall@0.5 | Mean IoU | p50 / p95 ms | Peak RSS bytes | Warning/resource pages |
|---|---:|---:|---:|---:|---:|---:|
| RapidOCR `default_v1` 1 | 0.009765 / 0.009887 | 0.779330 | 0.661689 | 51,180 / 65,120 | 724,996,096 | 0 |
| RapidOCR `default_v1` 2 | 0.009765 / 0.009887 | 0.779330 | 0.661689 | 44,373 / 55,890 | 768,208,896 | 0 |

All 15 per-page semantic Hashes match across the two runs; latency and peak RSS are intentionally
excluded from semantic identity. `ds1-ocr-04` completes in both runs. Identity evidence:

- checked `default_v1.json` SHA-256:
  `ca962f3ba5f8c4053e502acfe3e36928351a24650db2fad589d153a4d6a719a0`;
- resolved Profile identity: `1ead48fec1275cd9581f0079870bca60fcaabbea777c5909751a79ac2290623d`;
- resolved runtime Profile file SHA-256:
  `c668dda60eb7957e827583e0f5f920239f94ba8fe2199944596657884723d58a`;
- model Manifest SHA-256:
  `1f4c39ecbdd0a249adfe28d3f4f42ee8899a3951b31d4bf79710d2d978f88bf4`;
- immutable image ID:
  `sha256:a02def1a83823adf83c64efe3f86753086feb641a0a9d1849726bff83f9f3c3d`;
- run 1/2 report SHA-256:
  `a5ebe1f16240f074a848a4db2ab4d692e79c06685fb64cc4647dde2d5ecb9418` and
  `27ee9cef5aaa2c5bc5a32f7137e701ac946b626aec1f007fad24f747f463ac6e`.

### Deployment evidence

| Engine | Image ID | Image bytes | Increment over base | Python/System packages | Model bytes |
|---|---|---:|---:|---:|---:|
| RapidOCR | `sha256:a02def1a83823adf83c64efe3f86753086feb641a0a9d1849726bff83f9f3c3d` | 304,932,834 | 259,422,118 | 30 / 128 | 31,836,058 |
| Tesseract | `sha256:9563e62d93ea41705b46cce3ba250557f9744ce6892698b2b284b7a808fa9900` | 119,068,042 | 73,557,326 | 5 / 158 | 17,144,971 |
| PaddleOCR | `sha256:a8eacf1db5142dee897b3ab844f054b60efdd22dd42f0c01660e66b30c2155c4` | 588,040,897 | 542,530,181 | 68 / 128 | 139,110,993 |

Model Manifest SHA-256 values are respectively
`1f4c39ecbdd0a249adfe28d3f4f42ee8899a3951b31d4bf79710d2d978f88bf4`,
`125d19a17b160e9a7ae2024054b4f588fb94ed7b31a9fca1ed5021e02bc59f72` and
`0e0340f3a79e226d1155cd573c0c64dcf1966921d97ef5e69fabd6224b74f29c`.

## Verification evidence

| Command/check | Result |
|---|---|
| `uv sync --frozen` | passed; 181 packages checked |
| `uv run pytest -q tests/courserag/parsers/` | 33 passed |
| Stage/migration focused tests | 4 passed |
| Eval data/runner/routing focused tests | 9 passed |
| Resource/failure focused tests | 18 passed |
| gated owner PDF/DOCX B0 Smoke | 1 passed; one DOCX and one different-content PDF |
| final P05/default focused suite | 60 passed, 5 dependency warnings |
| `uv run pytest -q` | 346 passed, 4 skipped, 5 dependency warnings; 63.81 seconds |
| `uv run ruff format --check` | 311 files already formatted |
| `uv run ruff check` | passed |
| `uv run mypy src/` | 0 errors in 219 source files |
| Schema/boundary/Gold leakage guard | 29 passed; 35 JSON Schemas verified |
| Compose config and Dockerfile static build checks | both Compose files valid; both Dockerfiles pass `buildx --check` with no warnings |
| `git diff --check` | passed; only Windows LF/CRLF notices |
| Secret/temp/fallback/orphan audit | no real Secret, tracked temp file or automatic Provider fallback; zero orphan OCR run containers |

The eight engine/default reports, deployment evidence and comparison were written atomically
under `storage_eval/p05_ocr_pilot/`. Failed/intermediate diagnostic directories are retained for
audit; no evaluation data or Docker volume was deleted.

## Risks and rollback

- The 90-second Profile resolves the observed Pilot boundary and is repeatable on all 15 pages,
  but larger corpora can expose slower layouts; timeout/resource warnings remain mandatory.
- Tesseract and PaddleOCR are not suitable defaults under the frozen evidence. They remain
  isolated candidates and are not silently used as fallback.
- Confidence semantics are normalized to `[0,1]` while retaining raw Provider provenance.
- P06 must preserve r3 roles and warnings so QR/header/caption/image material cannot silently
  become Evidence.
- Switching Provider back to `disabled` restores P04 `ocr_pending` behavior without touching the
  Active Index, legacy Chroma or public API.
- Two attempts to rebuild the selected evaluation image on this workstation were blocked by a
  slow Debian mirror followed by BuildKit memory exhaustion/tool timeout. Unnecessary RapidOCR
  `libgl1`/Mesa dependencies were removed and Docker layers reordered; static checks pass. The
  exact existing image successfully ran both default Pilots, but CI must complete a clean default
  service-image rebuild before deployment. This does not block P06's Evidence work.
- Migration downgrade removes new OCR columns and must only be performed as an explicit operator
  action after OCR writes are stopped and Artifacts retained.

## Exit Gate

| Gate | Result | Evidence |
|---|---|---|
| OCR Gold can be located to page and region | passed | exact r3 approval binds 15 images, page IDs, pixel geometry, DPI and source geometry; Gold/output are physically separated |
| Low confidence does not pass silently | passed | low page/region confidence, empty output, timeout, memory and pixel limits emit warnings and `ready_with_warnings`; identity failure fails the Stage |
| Default engine selection has Pilot evidence | passed | owner selected RapidOCR; two 90-second runs reproduce all 15 semantic results with no warning/resource-limit page and bind exact Profile/model/image/report Hashes |

Overall P05 Exit Gate: **passed**. P05 is complete and P06 meets its upstream prerequisite; no P06
implementation has started.
