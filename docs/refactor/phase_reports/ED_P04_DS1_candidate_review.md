# ED-P04 DS1 Candidate Review Checkpoint

- Status: **exact Candidate approved; corrected formal P04/B0 evaluation completed and Gate passed**
- Candidate: `datasets/courserag_eval/v1/candidates/ds1/p04_native_docx_r6.json`
- Candidate SHA-256: `7179ce9a48be77118ad68bfa7376bbe69e030f0e69ad0faba8435b0e0ee3c3aa`
- Review pack: `storage_eval/ds1_p04_review/7179ce9a48be77118ad68bfa7376bbe69e030f0e69ad0faba8435b0e0ee3c3aa/index.html`
- Counts: Page 15 / DOCX Pagination 10 / Section 20 / Table 10 / OCR 0
- Renderer: `libreoffice-headless` `7.4.7.2`
- Canonical primary DOCX PDF: `4642e5c653b265b71bdbf9878218ca058188a9420b8b5930317cf4442c09fb95` (636 physical pages)
- Canonical stress DOCX PDF: `68c178e0ecb7ef615564bbef92c068037dba20ca600e418e53300b5a92cf570c` (128 physical pages)
- Word 2021 cross-check: `anchor_presence_verified_full_pdf_unavailable` — Word 2021 Find returned all five selected anchors; full PDF export was unavailable, and no Word page fact is used as Gold
- Predecessor Candidate: `8fd5fbefbcbe40c90f65c35cd3e0166cb6d62800e4927e4ed7c6cb1c661973cb`
- Current review source: `ds1_p04_review_decisions_r4.json`
- Current review source SHA-256: `acaba867ed1377ce71eca915e713ecf97933b3768269194d85f008d7f26cf895`
- Original r3 review attachment SHA-256: `0b38ca0e699acc3063a69b27fc530688585e1dc0ab5c32693a0376dd26d2f28e`
- Required re-review: `ds1-table-docx-020`
- Approved DS1: `datasets/courserag_eval/v1/approved/ds1/p04_native_docx.json`
- Approved DS1 SHA-256: `7e12edb2b66912d915b1d1ca3b7df873edb910cb7dcaf57d07872c83d84964ea`
- Batch approval SHA-256: `e9fdc5fc6d72bf2626e98bab16435f361d8fbef4ef547d0b8fe4f128a7d285b0`

## Required course_owner review

1. PDF: physical page, page type, Region BBox/type, reading order and header/footer/page-number noise.
2. DOCX pagination: exact source text/unit, physical page and visible display/Section page labels; `null` must not be guessed.
3. Section: exact title, level, parent, source boundary, first and last text.
4. Table: row/column count, merged-cell blanks, line breaks and every visible cell value.
5. Global: no invented course content, source Hashes unchanged, only two semantic sources, no OCR Gold.

Second review is mandatory for all 10 pagination records and the five Section records listed in
`datasets/courserag_eval/v1/provenance/ds1_p04_candidate_manifest.json`.

For r6, the 54 records accepted in the r3 review artifact are pre-checked in the offline package.
Only `ds1-table-docx-020` requires re-review. Its source OOXML grid is 6x4, while the fixed-renderer
physical pages 547 and 548 show seven visible rows in total; both page images, the 7x4 Gold grid
and the 6x4 source grid are shown in the review card.

The owner supplied the required exact approval:
`批准正式 DS1 Candidate 7179ce9a48be77118ad68bfa7376bbe69e030f0e69ad0faba8435b0e0ee3c3aa`.
The approval was applied twice with identical file/batch Hashes and no duplicate records. Any
future Gold correction must still create a new Candidate revision and audit event; revisions 1
through 6 remain retained and are never silently overwritten.

## Current gate

Approved DS1 contains all 55 records, `gold_status=ds1_p04_native_docx_approved` and
`phase_input_status.p04=formal_eval_ready`. Dev/Test remain empty and Test remains unlocked. The
formal Approved-DS1 Pilot-stage comparison has run; this is not a locked formal Test evaluation.

The old report `storage_eval/p04_formal_ds1_r6_verified/report.json` remains audit evidence but is
superseded for Gate decisions. It ignored the stress fixture's bookmark identity and treated the
parent `paragraph_index` as the fixture's parser ordinal, so inserted Section-break paragraphs
caused it to score the wrong Block. No Gold or product parser change was required.

The corrected formal adapter resolves exact OOXML source units, verifies source and parser Block
Hashes and has no text-search fallback. Two runs on the same Approved DS1 reproduce identical
metrics, pagination diagnostics and Gate decisions:

- `storage_eval/p04_formal_ds1_r6_source_unit_fix_run1/report.json`, SHA-256
  `a14bd1767a1970507402c270b865e29ecb089abe79f8eaa7a2f8e4d6e9240578`;
- `storage_eval/p04_formal_ds1_r6_source_unit_fix_run2/report.json`, SHA-256
  `2f05a8b11246c0670e7c50de0fdb06e94fc24ac30b2d0a3b640356dc05d4e925`.

P04 passes parsing 3/3, PDF mapping 15/15, DOCX physical mapping 10/10, all observable
display/Section mappings 5/5, normalized sample recall 780/783, renderer repeatability and every
B0 comparison constraint. The stress `5.3` bookmark resolves to parser paragraph 1615 and matches
Gold 51/`20`/20 with both source and parser Block Hashes verified. P04 Exit Gate passes; P05 is
eligible to start while remaining `not_started`.

## Verification completed before r6 re-review

- Visual Gold: page 547 contributes Gold row 0; page 548 contributes Gold rows 1-6. The combined
  visible table is 7x4 and no cell is clipped.
- Source provenance: the original DOCX has six OOXML row nodes and four columns; the generator
  verifies its exact 6x4 matrix and the Manifest/review card retain this distinction.
- Revision isolation: all 54 previously reviewed record digests are exactly unchanged; only
  `ds1-table-docx-020` differs between r4 and r6. The intermediate r5 was superseded before review
  because its first provenance encoding would have changed other table digests.
- Determinism: two r6 replays produced identical Candidate, Manifest and HTML Hashes. Manifest
  SHA-256 is `d5f8af9fa74667ada63c3d98acbdb20360207b0488b3ac711fb6914d245c198b`;
  HTML SHA-256 is `091af6bfc60dacfca75646a2f808424b1441ad4d3d3de9d167d86f0e24a68c91`.
- Tests: post-repair full Pytest 311 passed and 5 skipped; Ruff format/check passed for 285 Python
  files; Mypy found no issues in 203 source files; all 33 exported Schemas and the 125/4 record
  dataset boundary validation passed.
- Approval boundary: Candidate and Approved files remain physically separate; all 55 Approved
  records bind their Candidate record Hash, Dev/Test are empty and Test is unlocked.
