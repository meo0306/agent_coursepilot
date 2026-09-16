# ED-PRE03 CourseRAG DS0 Candidate Freeze Report

- Date: 2026-07-29
- Revision: 2, after `course_owner` requested denser late clean-scan pages
- Scope: Pre-P03 evaluation-data preparation only
- Frozen documents used: 02, 03, 03A, 04, 07
- Gold state: six DS0 Pilot records `approved`; no DS1–DS8 Gold
- Reviewer checkpoint: completed by `course_owner` at `2026-07-29T00:22:31.1188978Z`
- Fixture Manifest SHA-256:
  `b4f6f71ddc63d25e89fdc608e818e645d9d20558566ff09ea64a2b74d1c2d7b7`
- DS0 Candidate file SHA-256:
  `566d1784fc1479bbe723915b3daaa5501604204ac1589bae2b34a94a713759ae`
- DS1 sampling-plan SHA-256:
  `8700d3b449586de8f86c7107c67a8fc8d5215212c639bb1c7568af8ed1c061ba`
- Approved DS0 file SHA-256:
  `d9174a4dd75182b608ed161d803acb9ddb8bc16f0aa1933641b2328326eb1306`
- Review log SHA-256:
  `9d64d4c8d161b7396e70a0621ecbf9e78faad26b7b972a0450c4071693bbc3db`
- DOCX QA render-profile SHA-256:
  `1ea29f247b356a9f2cbcb964ac1a14691623b52f72cac94e57a0fff1223a16cc`

## 1. Outcome

The Pre-P03 implementation and mandatory human DS0 approval boundary are complete. Six approved
evaluation documents are defined from exactly two owner-supplied semantic sources. The other four
documents are deterministic transformations for parsing, OCR, pagination, and migration testing;
they are not independent corpora and are excluded from retrieval, knowledge-point, and QA
evaluation.

The first unapproved candidate batch was superseded after the owner returned its clean-scan page
selection. The change and both batch Hashes are retained in
`provenance/candidate_revision_history.json`; the first batch was never approved. The exact revised
Candidate file was revalidated and approved by `course_owner`. The retained Candidate records,
Approved DS0 records, six ApprovalRecords, and six append-only review-log entries form a complete
Hash-linked chain. No source fact was added or rewritten. Dev/Test remain empty and
`test.lock.json` remains `locked=false`.

## 2. Task IDs

| Task | Result | Evidence |
|---|---|---|
| ED-PRE03-T01 | completed | DS0/DS1/DS2/DS5 contracts extended additively; 27 Schemas exported |
| ED-PRE03-T02 | completed | two Primary and four deterministic derived binaries constructed |
| ED-PRE03-T03 | completed | six DS0 Candidate records and complete provenance Manifest generated |
| ED-PRE03-T04 | completed | DS1 Pilot sampling plan generated without DS1 Gold or guessed DOCX pages |
| ED-PRE03-T05 | completed | reproducibility, PDF, DOCX source mapping, canonical render QA, tests and static gates pass |
| ED-PRE03-T06 | completed | six exact revised Candidate records approved by `course_owner`; ApprovalRecords and review log validated |

## 3. Semantic-source boundary

| Course | Primary document | Independent semantic source? | Derived variants |
|---|---|---:|---|
| `course_ai_algorithms_systems` | `doc_ai_algorithms_systems` | yes | `doc_ai_algorithms_systems_structure_stress` |
| `course_ai_general_education` | `doc_ai_general_education_excerpt` | yes | clean scan, compressed scan, mixed PDF |

Every course has one `mutually_exclusive_variant_group`. Only the two Primary artifacts have
`retrieval_eligible=true`. A build or index must select at most one member of a variant group, and
the derived members may be selected only for parsing/OCR/pagination/migration evaluation.

## 4. Candidate approval table

`Candidate Hash` is the canonical record digest that must be copied into a future ApprovalRecord.
The full file SHA-256 is also shown so approval cannot silently drift to another binary.

| Record / document | Course | Role / parent | File SHA-256 | Page count and basis | Candidate Hash | Decision |
|---|---|---|---|---|---|---|
| `ds0-doc-ai-algorithms-systems` / `doc_ai_algorithms_systems` | `course_ai_algorithms_systems` | Primary | `c93df4cb4bb533e381647e7591104ff06ecc6a486582d77b3e6d63511428066b` | formal `null`; DOCX file-property candidate `183`; awaiting P04 fixed Renderer | `595854057b2e07a1f0b6ac39ca6946e71cf5cdf8664985dcac78e595ba152b66` | approved |
| `ds0-doc-ai-general-education-excerpt` / `doc_ai_general_education_excerpt` | `course_ai_general_education` | Primary | `15344771664d40cf190be7790be3d266eb94a2798a4c2608fcf4d1ffa8fd231d` | `32`; verified PDF page tree | `3d2d54b42a6f24461a8856f7dda87ef9f2a8d043a6b235623549624977e3d299` | approved |
| `ds0-doc-ai-general-education-scan-clean` | `course_ai_general_education` | Derived from PDF Primary | `4f0166c18e79aa29d06ef2d32597d532b76da17a53292a09e58b5b7e783df7a1` | `5`; derived page map | `1139cae3cf4dca2b1bfa5d778cffb947a81e48b5aa40db253633fda01357a57d` | approved |
| `ds0-doc-ai-general-education-scan-compressed` | `course_ai_general_education` | Derived from PDF Primary | `81b678dbf4737eafcbadbf6c7c9d3c8b92b955eccd6a8f1a4c28cbed98e93554` | `5`; derived page map | `3d3d103ec51ce2ef5b8ad3e742c69ef8a307021aaea77c24fb37b3cbad453be0` | approved |
| `ds0-doc-ai-general-education-mixed` | `course_ai_general_education` | Derived from PDF Primary | `f5d384f9affff159c78a9f3654a0ec918c05a0ba8370405da9e8fd030d073e4a` | `32`; derived page map | `1d7f01649a24820aa17cbdfd0f052ca3171c17cc4c5540111669c297fad4ebda` | approved |
| `ds0-doc-ai-algorithms-systems-structure-stress` | `course_ai_algorithms_systems` | Derived from DOCX Primary | `a848d60e97f28aef93877bea63dfea1bb8c9303843a8e0a27b7939c3b4fdb72b` | formal `null`; QA-only observation `128`; awaiting P04 fixed Renderer | `922aad9e22e55b849cc7b04c4ac9b4993000125900ec47e529e79f0c50b009d3` | approved |

Approval review IDs are `review-pre-p03-ds0-20260729-01-01` through
`review-pre-p03-ds0-20260729-01-06`. Approved-record canonical Hashes are, in table order:
`539c43baed7b2b8e0c3668d9a8c08694c1907239fef0a988cee7bf8731c6e677`,
`62827d4f93f5045b710e6e0a251cc6352057384e68fcabe58958997d519dd4df`,
`acd1cdcc9746bc03cf5c4ff60dcd2f776784c1edca78a1766fb592343021f402`,
`3ca057395005a007cbd318cd4d9d2f7cdf80af7ecfa090286665af3376e5c34b`,
`eaaf191a5fc11f4a1a67866c39e854c6c4ca262c46121804bd85702cd7c1e82f`,
and `41ddc5f9ca1b2205c72252d0521fa3f1b91023a471eaaf6ad2f208a64ef016ff`.

## 5. Exact transformations

### 5.1 PDF fixtures

| Fixture | Physical source pages | Parameters | Output mapping |
|---|---|---|---|
| clean scan | `21, 23, 24, 26, 30` | 300 DPI, RGB, lossless PNG image per page | output pages `1–5` map in listed order; every output page has no text layer |
| compressed scan | `11, 15, 18, 27, 31` | 180 DPI, grayscale JPEG, quality 70, no optimize/progressive metadata | output pages `1–5` map in listed order; every output page has no text layer |
| mixed PDF | full `1–32`; rasterize `9, 22, 25, 29, 32` | raster pages use 200 DPI grayscale JPEG quality 75; all other pages are inserted natively | only the five specified pages lack a text layer; physical page numbers are unchanged |

The new clean-scan selection is in the later part of the 32-page source, is disjoint from both
other raster page sets, and contains 1,054 / 958 / 1,103 / 1,174 / 893 characters in the native
source text layer. The page images cover dense explanatory prose, hierarchical headings, an AI
anchor image, a QR/noise region, and a robot image. The physical source pages correspond to the
printed footer labels `013, 015, 016, 018, 022`; the offset is front matter in the source PDF, not a
mapping error.

All generated pages preserve the source page rectangle. Visual montages of all 42 derived PDF
pages were inspected; no clipping or missing page content was observed.

### 5.2 DOCX structure-stress fixture

- Copies 3,880 source body paragraphs and 454 source table cells; each of the 4,334 units has a
  source locator, target locator, and exact UTF-8 text SHA-256.
- Copies no image/media binary and introduces no course statement.
- Uses four A4 Sections, column pattern `one/two/one/two`, page-number restarts in Sections 2 and
  4, a header copied from the first non-empty source paragraph, and a page-field-only footer.
- Tables use explicit fixed widths of 10,034 DXA in one-column Sections and 4,765 DXA in
  two-column Sections; no fixed row height is used.
- The first canonical render exposed a clipped two-column table. The width rule was corrected,
  the fixture was regenerated, and the final canonical render was reviewed on all 128 pages plus
  full-resolution boundary/table pages. No table overflow, column overlap, page-edge clipping, or
  missing mapped text remained.
- The QA environment is reproducible from `docker/Dockerfile.eval-docx-qa`: LibreOffice
  `7.4.7.2`, Poppler `22.12.0`, pdf2image `1.17.0`, image ID
  `sha256:7051ac5e31cb11fddf994960135a460e8de6486c39c61366962fdceeacb00643`,
  and font-manifest SHA-256
  `780fbf5bed4c88c289940b40060ed9abee2fdceda87f2a2a4bf46aaefd200baf`.
- Two repeated renders produced the same 128 byte-identical page PNGs, with aggregate SHA-256
  `a19eee755f5724be5d5c4149f3db625a5852ed37c3e9fa998a82e19260ee8acf`.
  The emitted PDFs differed because LibreOffice wrote the current `CreationDate`; therefore the
  observed 128 pages remain QA evidence only and are not DOCX Pagination Gold.

## 6. Schema changes

- DS0: `course_id`, repository-relative path, Primary/derived role, parent, derivation Manifest
  Hash, mutual-exclusion group, page-count basis, and separate file-property page candidate.
- DS1: page content/noise regions and BBox, Section first/last text, OCR regions, and typed DOCX
  Pagination Gold with Renderer/font/profile/rendered-PDF Hashes.
- DS2: page BBoxes, `ocr_derived`, and bounded OCR confidence.
- DS5: 0/1/2 Graded Relevance, allowed answer variants, and expected answer/abstention behavior.
- New tracked contracts: corpus-fixture Manifest and DS1 sampling plan.
- Existing fields retain defaults where required, so the old Pilot and compatibility tests remain
  valid. Product contracts are untouched.

## 7. DS1 Pilot sampling plan

No DS1 Gold record was authored. The candidate plan contains:

- native PDF source pages `5, 10, 12, 20, 32`;
- DOCX structure anchors `1.1.1`, `2.2`, `3.5.3`, `5.3`, `9.7`, with no page number;
- all five clean-scan pages, mapping to source pages `21, 23, 24, 26, 30`, for future OCR review.

P03 must bind real DocumentVersion/Build identities. P04 must freeze the formal DOCX Renderer,
version, font Manifest, profile and deterministic rendered-PDF policy. P05 requires human OCR
transcription, reading-order and region review.

The ten P02 legacy fixed-character-window DS2 candidates remain ignored historical evidence only:
they are not split, approved, or reused as future Gold.

## 8. Verification evidence

| Check | Result |
|---|---|
| Network/install recovery | Debian HTTPS and PyPI reachable; isolated LibreOffice/Poppler/pdf2image image built successfully |
| Repeat fixture build | all four derived binary Hashes, Fixture Manifest, DS0 JSON and DS1 plan matched on the same output paths |
| Fixture verification | 6 artifacts, 2 semantic sources, 42 PDF pages, 4,334 DOCX source units passed |
| PDF text layers | clean/compressed: none on every page; mixed: absent only on `9, 22, 25, 29, 32` |
| PDF visual QA | all three page montages inspected; no clipping/content loss observed |
| DOCX canonical render | 128 A4 pages; all-page contact-sheet review and selected full-resolution review passed after one corrected overflow |
| DOCX render repeat | all 128 page PNGs byte-identical; PDFs differ by `CreationDate`, so no formal pagination claim |
| Schema export check | 27/27 verified |
| Dataset validation after approval | CourseRAG 15 records (9 Candidate plus 6 Approved); CoursePilot 4 Candidate records; complete approval chain and no split violation |
| focused fixture/Schema tests | 16 passed |
| approval utility/boundary focused tests | 7 passed; exact-file Hash binding and repeated-execution idempotency covered |
| `tests/evals` | 56 passed, 1 gated skip |
| Full Pytest | 259 passed, 5 gated skips |
| Ruff format/check | 229 files formatted; all checks passed |
| Mypy | no issues in 165 source files |

The first Docker build was interrupted while the HTTP Debian mirror transferred at roughly
1 KB/s. Direct HTTPS checks to Debian and PyPI passed; changing only the Debian mirror scheme to
HTTPS allowed the same build to resume and finish. A first test attempt also failed before
collection because a Windows `.venv` binary was mounted into Linux. The final tests used locked
Linux-native tools in an isolated image. Neither interruption was a product or dataset failure.

## 9. File, API, database and configuration impact

- Tracked: additive Schema/model/test changes, generated JSON Schemas, DS0 candidates, Fixture
  Manifest, DS1 plan, candidate-revision history, QA render profile, QA Dockerfile, and
  decision/risk/status/report updates.
- Ignored: four generated binaries and all PDF/DOCX visual-QA intermediates under
  `storage_eval/courserag_corpus/v1/`.
- Database/migrations: none.
- Product HTTP API: none.
- Product runtime configuration/Provider: none; the Dockerfile is evaluation QA tooling only.
- Frozen documents: not modified.
- Git commit/push/PR: not performed.

## 10. Exit Gate

The technical Pre-P03 construction gate and the human DS0 freeze gate both pass. Dataset Manifest
status is `ds0_pilot_approved`; all six retained Candidates are Hash-linked to six Approved DS0
records and six append-only review entries. P03 remains not started, but its data prerequisite is
now satisfied and P03 may begin under the frozen roadmap. DS1 remains a sampling plan only: after
P03, the next data action is to bind the real DocumentVersion and Build identities without guessing
DOCX pages or authoring later-stage Gold.
