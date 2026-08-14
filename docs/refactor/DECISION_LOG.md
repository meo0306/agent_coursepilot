# Decision Log

## P00-D001 — Existing retrieval metrics are not accepted as Gold evidence

- Status: accepted
- Date: 2026-07-23
- Trigger: `run_real_eval.py` constructs expected retrieval identifiers after observing Top-K results.
- Frozen documents affected: 03, 03A, 06, 07
- Options:
  - publish the historical Recall/MRR/nDCG values as B0 quality metrics;
  - discard the historical run entirely;
  - preserve its engineering evidence but label its retrieval quality metrics invalid.
- Minimal safe default: preserve pipeline, latency, fallback, token, database/vector, and export evidence; mark retrieval quality metrics `non_gold_invalid_for_quality_claims`.
- Decision: define source-independent Gold and evidence spans in P02; retain the legacy runner
  unchanged, prohibit legacy Chunk IDs/Top-K output from defining formal Gold, and map B0 output
  only through the P02 source/span/text adapter.
- Compatibility/migration impact: none in P00; historical artifacts remain available.
- Evaluation impact: P00 cannot claim a credible retrieval quality score from the historical run.

## P00-D002 — Local sample documents remain independent, non-approved inputs

- Status: accepted
- Date: 2026-07-23
- Trigger: the repository owner supplied one DOCX and one PDF with different content.
- Frozen documents affected: 03, 03A, 07
- Decision: process the files independently in isolated courses; retain only relative path, format, size, and SHA-256 in B0 artifacts.
- Compatibility/migration impact: none; the files are not moved, rewritten, or promoted into runtime data.
- Evaluation impact: the files support non-Gold Smoke only and remain DS0 candidates pending P02 review.

## P00-D003 — B0 workflow uses isolated deterministic infrastructure

- Status: accepted
- Date: 2026-07-23
- Trigger: P00 requires an end-to-end B0 without changing product behavior or exposing provider secrets.
- Frozen documents affected: 06, 07
- Decision: run the public API in-process with temporary SQLite/Chroma, hashing embeddings, deterministic generation, and deterministic knowledge-point extraction.
- Implementation detail: use the existing validated two-session/six-slide combination so the current PPT validator can exercise export without modifying Graph or validator behavior.
- Compatibility/migration impact: none; no production database, Collection, API, Graph, or Provider configuration is mutated.
- Evaluation impact: the run proves connectivity, isolation, persistence counts, exports, and write-back only; it does not measure content quality.

## P00-D004 — Prompt-agent graph input contract needs explicit typing

- Status: accepted
- Date: 2026-07-23
- Trigger: after resolving the eight approved P00 Mypy errors, a fresh full check reports `src/service/service.py:139`.
- Frozen documents affected: 01, 05, 07
- Former contract: `AgentGraph` was declared as `CompiledStateGraph | Pregel`, while the HTTP prompt entrypoint always passes a `{"messages": list[AnyMessage]}` state dictionary.
- Options:
  - narrow the registry contract to the concrete compiled CoursePilot Graph types currently registered;
  - define a typed prompt-entry adapter/protocol shared by the service and agent registry;
  - suppress the mismatch with `cast`, `Any`, or `type: ignore`.
- Decision: explicitly propagate each Graph's State as its input/output type and define the registry contract as the union of the three concrete compiled CoursePilot Graph types currently registered.
- Compatibility/migration impact: static typing only; API, Graph nodes/edges/routes/state, ORM, migrations, Provider behavior, and runtime prompt invocation are unchanged.
- Evaluation impact: none; Prompt/Graph/B0 regression tests pass and the full Mypy Gate reports zero errors.

## P02-D001 — Owner-supplied source candidates remain local and unapproved

- Status: accepted
- Date: 2026-07-23
- Trigger: P02 requires a small Pilot while the supplied DOCX/PDF redistribution and formal Gold
  review status remain unverified.
- Frozen documents affected: 03, 03A, 06, 07
- Options:
  - commit source text/spans as Pilot candidates;
  - generate candidates locally and commit only safe hashes/counts;
  - skip owner-sample candidate generation.
- Decision: use the existing local parser without an external model; write DS0/DS2 source text,
  spans, and candidate records only under ignored `storage_eval/`; commit only input/output
  hashes, candidate counts, Schemas, and synthetic fixtures. No generator may set `approved`.
- Compatibility/migration impact: no runtime, API, database, Provider, or binary-file change.
- Evaluation impact: ten local candidates are available for later human review but are not
  formal Gold and cannot contribute to Test or quality claims.

## P02-D002 — Formal Runner identity and Test policy are fail closed

- Status: accepted
- Date: 2026-07-23
- Trigger: Resume, Test tuning, Fallback, and mutable Gold configuration could otherwise make
  formal results non-reproducible or leak Test information.
- Frozen documents affected: 03, 03A, 06, 07
- Options:
  - permit force-resume and record configuration drift;
  - warn on Test-policy violations;
  - reject any Run identity/configuration difference and require a locked, clean, fail-closed
    Test run.
- Decision: the P02 formal Runner has no force-resume path. It rejects Manifest/case Hash
  changes before mutation. Test requires evaluation/replay intent, tuning disabled, clean Git,
  fail-sample/fail-run Fallback, an immutable lock Hash, non-empty Approved Test IDs, and matching
  split/Approved-record Hashes.
- Compatibility/migration impact: applies only to the new formal evaluation Runner; the legacy
  B0 runtime and public API are unchanged.
- Evaluation impact: current Test locks intentionally remain `locked=false` until human Approved
  Gold exists, so premature formal Test runs fail rather than silently degrading.

## P01-D001 — P01 uses the approved narrow runtime migration boundary

- Status: accepted
- Date: 2026-07-24
- Trigger: the frozen P01 backlog says to replace direct RAG calls progressively, while the
  broader target design also moves review write-back and course knowledge-point ownership.
- Frozen documents affected: 01, 04, 05, 07
- Options:
  - migrate only document build, search and the shared Graph retrieval node;
  - add a private compatibility bridge for whole-artifact review write-back;
  - implement the later VerifiedContent and KnowledgePoint contracts early.
- Decision: migrate document build, search and the Lesson/Exam retrieval node in P01. Preserve
  existing review write-back and lesson knowledge-point extraction unchanged; assign their
  contract migrations to P07/P10/P14/P17.
- Compatibility/migration impact: existing CoursePilot APIs, Graph structure, review behavior,
  Parser/Chunker/Chroma algorithms and Provider configuration remain unchanged.
- Evaluation impact: old Graph/API and owner-supplied DOCX/PDF B0 Smoke tests remain comparable.

## P01-D002 — Legacy Chunk results expose absence of stable versions and Evidence

- Status: accepted
- Date: 2026-07-24
- Trigger: the B0 tables and Chroma metadata contain mutable Chunk IDs but no DocumentVersion,
  IndexVersion or stable Evidence ID.
- Frozen documents affected: 01, 04, 07
- Options:
  - synthesize stable-looking Evidence/version identifiers;
  - make the Local search path unusable until P03/P06;
  - retain Chunk IDs as trace fields and expose explicit legacy markers and warnings.
- Decision: never convert a legacy Chunk ID into an Evidence ID. Return `evidence_ids=[]`,
  `legacy-unversioned`, `legacy-active` and machine-readable warnings until the owning phases
  establish real identities. Capability-dependent methods return `FEATURE_NOT_AVAILABLE`.
- Compatibility/migration impact: old CoursePilot results are reconstructed without dropping
  their source type, chapter, section, page, title, content, score or verified flag.
- Evaluation impact: P02 Gold rules remain unchanged; legacy IDs cannot enter formal Gold.

## P01-D003 — RemoteCourseRAGClient is contract-only in P01

- Status: accepted
- Date: 2026-07-24
- Trigger: P01 requires an HTTP Schema and Remote Contract Fake, while production reliability and
  physical split are assigned to P17/P19.
- Frozen documents affected: 01, 04, 07
- Decision: RemoteCourseRAGClient requires an explicitly supplied `httpx.Client`; P01 tests use
  `MockTransport`. Do not add runtime selection, environment defaults, retries, authentication,
  circuit breaking or live network calls.
- Compatibility/migration impact: the local single-process demo remains the only runtime default.
- Evaluation impact: Remote serialization, trace headers, errors and idempotency are testable
  without Provider or network variability.

## P02-D003 — Pre-P03 corpus uses two semantic sources and four non-retrieval derivatives

- Status: accepted
- Date: 2026-07-28
- Trigger: DS0 must be frozen before P03, while the repository owner will provide no material
  beyond the existing DOCX and PDF and prohibits invented course content.
- Frozen documents affected: 02, 03, 03A, 04, 07
- Options:
  - treat only the two Primary files as DS0 and leave OCR/pagination paths untestable;
  - treat derived scans and layout stress documents as independent semantic corpora;
  - record two Primary semantic sources plus deterministic, traceable, mutually exclusive
    parser/OCR/pagination/migration fixtures.
- Decision: the two files belong to separate courses. Owner authorization permits repository use
  of source-derived Gold, but binaries remain in ignored directories by design. Create four
  deterministic derivatives without adding course facts; set `retrieval_eligible=false`, bind each
  to its parent and variant group, and prohibit parent/derivative co-indexing. All six DS0 records
  remain `candidate` until `reviewer_id=course_owner` explicitly approves the batch. Later formal
  Test uses a 20% blinded second review.
- Compatibility/migration impact: evaluation contracts and generated Schemas change additively;
  no product HTTP API, database, migration, runtime configuration, Parser, or index is changed.
- Evaluation impact: the corpus has six evaluation documents but only two independent semantic
  lineages. DOCX `183` is retained only as a file-property candidate; formal page count stays null
  until P04 freezes the Renderer, version, fonts, and render profile. No DS1–DS8 Gold is created by
  this decision.

## P02-D004 — Revised clean-scan pages and DOCX render remain candidate/QA evidence

- Status: accepted
- Date: 2026-07-29
- Trigger: the repository owner returned the first unapproved clean-scan selection as too early
  and insufficiently informative; subsequent canonical DOCX rendering exposed a clipped table in
  a two-column Section.
- Frozen documents affected: 02, 03, 03A, 04, 07
- Options:
  - retain the first clean selection and structural-only DOCX verification;
  - revise the clean selection but treat an ad-hoc LibreOffice page count as Pagination Gold;
  - create a new unapproved candidate batch from denser late pages, fix the layout defect without
    changing source text, and retain the isolated render as QA-only evidence.
- Decision: clean scan uses physical source pages `21, 23, 24, 26, 30`, corresponding to printed
  footer labels `013, 015, 016, 018, 022`. The pages are disjoint from the compressed and mixed
  raster sets and preserve the existing 300 DPI lossless transform. DOCX tables use the actual A4
  content/column widths; every source paragraph and table-cell Hash remains unchanged. Record the
  LibreOffice `7.4.7.2`/Poppler `22.12.0`/pdf2image `1.17.0` container and all-page visual review,
  but keep both DOCX `page_count` values null until P04 defines a formal deterministic Renderer.
  The first candidate batch is marked superseded-before-approval in revision provenance; no
  ApprovalRecord or approval review-log entry is created.
- Compatibility/migration impact: no product API, database, migration, runtime configuration,
  source document, or frozen document changes. The new Dockerfile is evaluation QA tooling only.
- Evaluation impact: the revised clean scan has stronger late-page OCR coverage. The QA render
  observed 128 A4 pages and repeated page PNGs were byte-identical, but LibreOffice emitted PDFs
  differed by `CreationDate`; therefore neither the count nor PDF Hash is formal Pagination Gold.

## P02-D005 — Course owner approves the exact revised DS0 Pilot batch

- Status: accepted
- Date: 2026-07-29
- Trigger: `course_owner` explicitly replied “批准报告中的全部六条修正版 DS0 Candidate”.
- Frozen documents affected: 03, 03A, 07
- Decision: bind the approval to Candidate file SHA-256
  `566d1784fc1479bbe723915b3daaa5501604204ac1589bae2b34a94a713759ae`
  after revalidating the six canonical Candidate Hashes and all source/derived file Hashes. Retain
  the Candidate batch, create six Approved DS0 records and ApprovalRecords, append six review-log
  entries under `reviewer_id=course_owner`, and set Manifest `gold_status=ds0_pilot_approved`.
- Compatibility/migration impact: no product API, database, migration, runtime configuration,
  source binary, Split assignment, Dev/Test content, or Test lock is changed.
- Evaluation impact: the Pre-P03 data Exit Gate passes and P03 may start. Approval applies only to
  DS0 document identity/provenance; it does not approve DS1–DS8 Gold, convert QA-only DOCX page
  observations into Pagination Gold, populate Dev/Test, or lock formal Test.

## P03-D001 — CourseRAG owns separate metadata in the shared P03 database

- Status: accepted
- Date: 2026-07-29
- Trigger: P03 needs a PostgreSQL fact source without coupling new facts to mutable legacy table
  lifecycles or physically splitting services before P19.
- Frozen documents affected: 00, 02, 04, 07
- Decision: use a separate `CourseRAGBase`/metadata and additive `courserag_*` tables on the current
  CoursePilot engine/session. Store legacy Course/Document/Task identifiers as compatibility
  values; create no foreign key from new facts to `coursepilot_*` tables.
- Compatibility/migration impact: two additive revisions follow 0007 and were tested through a
  real PostgreSQL upgrade/downgrade/re-upgrade. Existing tables and rows are unchanged.
- Evaluation impact: none; B0 identity remains traceable and no legacy Chunk becomes Evidence.

## P03-D002 — The versioned pipeline is explicit and does not replace B0 by default

- Status: accepted
- Date: 2026-07-29
- Trigger: the user approved a complete P03 pipeline plus a narrow legacy bridge while explicitly
  prohibiting a default public cutover in this phase.
- Frozen documents affected: 02, 04, 07
- Decision: expose an internal compatibility bridge that maps PDF/DOCX `Document` records into
  versioned facts and the existing leased task queue. Keep all current public build/search routes
  on the P01 Local adapter and legacy Chroma behavior until a later approved cutover.
- Compatibility/migration impact: no HTTP route, status code, response schema, Parser, retrieval
  algorithm, Chroma Collection or Provider behavior changes.
- Evaluation impact: owner PDF/DOCX B0 Smoke remains directly comparable.

## P03-D003 — Build execution is at-least-once with idempotent Stage effects

- Status: accepted
- Date: 2026-07-29
- Trigger: database leases can be reclaimed after a crash, so execution cannot honestly be
  described as exactly-once.
- Frozen documents affected: 02, 04, 07
- Decision: retain at-least-once task execution; make Stage effects idempotent with fingerprints,
  content-addressed atomic artifacts, verified cache hits and unique attempts. Persist Build/Stage
  failure evidence before the legacy worker records task failure. Manual retry names a Stage and
  remains auditable.
- Compatibility/migration impact: existing worker claim/heartbeat behavior is reused; a new
  `courserag_build` task type is created only through the explicit bridge.
- Evaluation impact: recovery can be measured without claiming code executes exactly once.

## P03-D004 — Sparse publication is explicit even though sparse indexing is deferred

- Status: accepted
- Date: 2026-07-29
- Trigger: P03 requires dense/sparse version manifests, while final sparse retrieval is assigned
  to P08 and must not be implemented early.
- Frozen documents affected: 02, 04, 07
- Decision: define and validate generic dense/sparse Manifest contracts. Dense must be `ready` to
  publish; sparse is either `ready` with its own valid Manifest or explicitly
  `not_materialized`. There is no silent empty sparse fallback.
- Compatibility/migration impact: no sparse engine, query mode or public capability is enabled.
- Evaluation impact: later runs can distinguish absence of sparse materialization from success.

## P03-D005 — Artifacts use opaque content-addressed URIs and cleanup is dry-run first

- Status: accepted
- Date: 2026-07-29
- Trigger: Stage cache and rollback require durable identity without leaking host paths or deleting
  referenced data.
- Frozen documents affected: 02, 04, 07
- Decision: publish `artifact://sha256/<digest>` URIs, write via fsync plus atomic replace, verify
  every cache read, keep absolute storage paths out of facts, and default retention cleanup to
  dry-run with reference protection and audit events.
- Compatibility/migration impact: three configurable storage/retention settings are additive and
  have safe defaults; no current stored file is moved.
- Evaluation impact: Stage artifacts and Manifest inputs are hash-traceable.

## ED-PRE04-D001 — P04 input selection binds deterministic P03 inventory identities without creating Gold

- Status: accepted
- Date: 2026-07-29
- Trigger: P03 completed without owner-sample persistence, while P04 needs real DocumentVersion,
  Build and Artifact identities plus a source-grounded annotation selection before Parser work.
- Frozen documents affected: 02, 03, 03A, 04, 07
- Options:
  - let P04 create ad-hoc identities and select examples from its own output;
  - seed the owner samples into the shared business database;
  - use a loopback-only isolated evaluation database, deterministic UUIDv5 identities and
    source-derived Candidate selections that remain separate from DS1 Gold.
- Decision: use Compose project `coursepilot_eval_p04`, database `coursepilot_eval` and fixed
  loopback port `55432`; fail instead of silently changing an occupied port or database name.
  Deterministically seed two KnowledgeBases and six Approved-DS0 document/version identities,
  each in a separate single-document `p03_inventory` Build with a verified content-addressed
  Artifact. Derived fixtures remain `retrieval_eligible=false` and cannot be co-indexed with their
  Primary. Build success means only that P03 inventory succeeded; no ParsedDocument, index or
  Ready claim follows. Select P04 annotation inputs only from exact owner-source text, hashes and
  fixture mappings. The work-package approval scope is input selection only and cannot promote
  DS1 Gold, populate Dev/Test or lock Test.
- Compatibility/migration impact: additive evaluation Schemas, a deterministic Seeder/approval
  CLI and a Compose override only. No public HTTP API, product runtime configuration, Provider,
  business database, parser, OCR, index, legacy row or migration revision is changed.
- Evaluation impact: P04 receives reproducible input identities and fixed source-grounded
  coverage. Formal DOCX page fields remain null until P04 freezes Renderer/version/fonts/profile;
  OCR transcription and coordinates remain deferred to P05. Six evaluation documents still
  represent only two independent semantic sources. The exact approval event is recorded separately
  in ED-PRE04-D002.

## ED-PRE04-D002 — Course owner approves the exact P04 input-selection Candidate

- Status: accepted
- Date: 2026-07-29
- Trigger: after receiving the complete Pre-P04 approval report, `course_owner` explicitly replied
  “批准” to the blocking question that named the exact Candidate file SHA-256.
- Frozen documents affected: 03, 03A, 07
- Decision: approve Candidate file SHA-256
  `b305f328a8e76555e661e048f34c7ea7c89ed82c9fb9982f4877e1b6a80df582` under review ID
  `review-pre-p04-input-20260729-01`. The existing P02 ApprovalRecord contract binds the canonical
  Candidate record digest `4834154e4834d6049d9d53e11d20bd730224ee13c264350397248e3d6e2dbbc9`
  and Approved record digest `8d1465d604b64320209c1ad18924a8f3ebe7806a14846115544d87500221288f`;
  the resulting Approved file SHA-256 is
  `06700604f3c69724090ee6a995c2696b41278f5bf45d64e90beeddba4a484e5c`.
- Compatibility/migration impact: create the physically separate Approved P04 work package and
  one append-only review entry; set only `phase_input_status.p04=approved_for_annotation`. Approval
  replay reuses the same file and review entry. No public API, product database/configuration,
  migration, Parser, OCR, index, source binary or Provider changes.
- Evaluation impact: approval authorizes the fixed P04 annotation inputs only. `gold_status`
  remains `ds0_pilot_approved`; it does not approve DS1 Gold, fill Dev/Test, lock Test, accept the
  DOCX `183`/QA-only `128` page observations, or approve any future P04 system output.

## P04-D001 — Canonical rendered-PDF identity excludes volatile container metadata

- Status: accepted
- Date: 2026-07-29
- Trigger: fixed LibreOffice renders preserve page content and geometry but raw PDF creation
  metadata changes between otherwise equivalent executions.
- Frozen documents affected: 02, 03, 04, 07
- Options:
  - require the raw PDF bytes to match and leave DOCX pagination non-reproducible;
  - ignore PDF identity and compare only ad-hoc page images;
  - retain the raw renderer artifact while deriving a canonical PDF from copied page content,
    with the renderer profile and font Manifest bound separately.
- Decision: retain both raw and canonical rendered PDFs. The raw Hash is provenance evidence;
  the canonical PDF Hash and ordered page Manifest are reproducibility identities. Canonicalization
  copies rendered page content/geometry and removes volatile document metadata; it does not rewrite
  text, page order or coordinates. Renderer version, image identity, profile and font lock remain
  separately hash-bound in the Run Manifest.
- Compatibility/migration impact: additive parser/evaluation behavior only; no public API,
  database migration, legacy artifact, source document or Chroma change.
- Evaluation impact: identical content/page geometry can be verified without treating volatile
  timestamps as semantic differences. Raw Hash differences remain visible and are never hidden.

## P04-D002 — DOCX pagination alignment is conservative and nullable

- Status: accepted
- Date: 2026-07-29
- Trigger: source DOCX structure has no authoritative physical page map and fuzzy alignment can
  otherwise fabricate plausible but wrong citations.
- Frozen documents affected: 02, 03, 04, 07
- Decision: align source Blocks monotonically against fixed-profile rendered-PDF text; assign a
  physical page only at or above the configured confidence threshold. Keep unresolved page fields
  null and emit an auditable warning. `display_page_label` and `section_page_index` are required
  fields but nullable when no source-grounded label/index is observable. Every aligned citation
  retains the structural source Anchor as well as available pagination.
- Compatibility/migration impact: no public response contract or legacy parser is changed. The
  P04 Stage materializes immutable projections only into the P03 tables already approved.
- Evaluation impact: low-confidence coverage is reported instead of being converted into guessed
  page Gold; selected Pilot anchors remain inspectable for independent review.

## P04-D003 — Fixed LibreOffice output is the formal DOCX pagination baseline

- Status: accepted
- Date: 2026-07-30
- Trigger: the fixed LibreOffice `7.4.7.2` profile is reproducible after canonicalization, but the
  primary DOCX requests 18 unavailable/substituted fonts and renders 636 physical pages. That
  candidate conflicts with the historical file-property count 183 and exposes no display labels.
- Frozen documents affected: 02, 03, 03A, 04, 07
- Options:
  - accept the fixed LibreOffice/font-lock output as a warned product pagination baseline and
    annotate its DS1 pages independently;
  - require a higher-fidelity Microsoft Word-compatible renderer/font package before authoring
    formal pagination Gold;
  - keep pagination non-formal and evaluate only structural Anchors for this document.
- Decision: `course_owner` selected the fixed LibreOffice Headless `7.4.7.2` profile, exact font
  Manifest and canonical-PDF identity as the formal pagination baseline. Under that profile the
  primary DOCX has 636 physical pages and the layout-stress fixture has 128 physical pages. The
  historical DOCX file-property value 183 is not a formal page count. The five selected primary
  anchors map to physical pages 6/44/145/251/618 with no visible page label; the corresponding
  stress-fixture anchors map to 1/8/33/51/124, with visible/Section page values retained only where
  observable. These values remain Candidate labels until the exact DS1 batch Hash is approved.
- Compatibility/migration impact: evaluation-only renderer and annotation policy. No product HTTP
  API, database migration, runtime default, source binary or legacy parser changes.
- Evaluation impact: resolves the renderer-choice blocker while preserving independent human
  review. Canonical repeat Hashes must match, font substitutions stay visible as limitations,
  Word 2021 is cross-check evidence only, and neither system Parser predictions nor the value 183
  may determine Gold.

## ED-P04-DS1-D001 — Formal DS1 remains an immutable source-grounded Candidate until exact approval

- Status: accepted
- Date: 2026-07-30
- Trigger: P04 implementation needs a non-circular 55-record DS1 batch, while previous work only
  approved the selection package and P04 system output cannot define its own Gold.
- Frozen documents affected: 02, 03, 03A, 04, 07
- Decision: construct 15 Page, 10 DOCX Pagination, 20 Section and 10 Table records from independent
  Poppler/PDF objects, raw OOXML and fixed rendered snapshots; generate no OCR Gold. Retain r1/r2
  as hash-verified superseded revisions and expose r3 through a completely offline review pack.
  Repository promotion requires the literal full r3 file SHA-256 and creates 55 per-record human
  ApprovalRecords plus a batch approval. A generic approval cannot promote the batch.
- Compatibility/migration impact: additive evaluation Schemas, Candidate generator, revision-aware
  inventory and approval CLI only. No product API, database, runtime configuration, OCR, index,
  Parser behavior, source binary, commit or deletion.
- Evaluation impact: prevents Gold leakage and silent revision substitution. Formal P04/B0 scoring
  remains prohibited while r3 is Candidate-only; Dev/Test remain empty and Test remains unlocked.

## ED-P04-DS1-D002 — Preserve 54 reviewed r3 records and revise only returned cross-page table 020

- Status: superseded by ED-P04-DS1-D003
- Date: 2026-07-30
- Trigger: the `course_owner` supplied a review artifact bound to r3 SHA-256
  `abbaf5114408990783dd209c3189e5ecfa4332a00aaab8b0e02ec892bdce1ac3`, with 54 reviewed IDs,
  and explicitly returned `ds1-table-docx-020` for re-recognition.
- Frozen documents affected: 02, 03, 03A, 04, 07
- Decision: retain the 54 reviewed record digests unchanged in r4. Re-recognize table 020 from raw
  OOXML and the fixed renderer: its logical data is a 6x4 non-merged grid, while its first row is
  visibly split across physical pages 547 and 548. Add page-fragment evidence without rewriting
  cell content, bind the original attachment Hash and normalized repository copy, mark r3
  superseded, append a `request_changes` review event, and require re-review only for table 020.
  The current r4 SHA-256 is
  `8fd5fbefbcbe40c90f65c35cd3e0166cb6d62800e4927e4ed7c6cb1c661973cb`.
- Compatibility/migration impact: additive evaluation Schema, provenance, review UI and tests only.
  No product API, database, configuration, renderer, source binary, OCR, Parser prediction, commit,
  deletion or migration change.
- Evaluation impact: partially completed human review is preserved without silently approving the
  corrected record. Approved DS1 remains empty; exact r4 approval and formal P04/B0 evaluation are
  still required before P04 Exit Gate can pass.

## ED-P04-DS1-D003 — Table 020 Gold follows the seven rendered-visible rows

- Status: accepted
- Date: 2026-07-30
- Trigger: during focused r4 re-review, the `course_owner` corrected the interpretation: “合并之后
  应该是7行4列吧”. Visual inspection confirms page 547 contains one bordered header row and page
  548 contains a second bordered header row plus five data rows.
- Frozen documents affected: 02, 03, 03A, 04, 07
- Decision: TableGold measures the final visible row/column structure used by the parsing metric.
  Therefore `ds1-table-docx-020` is 7x4 in r5. The DOCX still contains six OOXML row nodes, so the
  exact 6x4 OOXML cell matrix is retained separately as source provenance rather than discarded or
  misreported as Gold. Page fragments map Gold row 0 to page 547 and Gold rows 1-6 to page 548.
  r4 is superseded without approval. A pre-delivery audit then found that the first r5 provenance
  encoding would alter other reviewed table digests, so r5 was also superseded without review.
  The hash-isolated implementation is r6, SHA-256
  `7179ce9a48be77118ad68bfa7376bbe69e030f0e69ad0faba8435b0e0ee3c3aa`.
- Compatibility/migration impact: additive evaluation Schema and Candidate provenance only. No
  product API, database, runtime configuration, source DOCX, renderer, Parser output, OCR, index,
  migration, commit or deletion change.
- Evaluation impact: the row/column structure metric now compares against the human-confirmed
  visible table rather than the OOXML implementation detail. The other 54 reviewed record digests
  remain unchanged. Approved DS1 remains empty pending exact r6 approval.

## ED-P04-DS1-D004 — Exact r6 approval freezes Gold; a system mismatch fails P04 rather than rewriting Gold

- Status: evaluation diagnosis superseded by ED-P04-DS1-D005; Gold-freeze decision retained
- Date: 2026-07-30
- Trigger: the `course_owner` explicitly approved Candidate SHA-256
  `7179ce9a48be77118ad68bfa7376bbe69e030f0e69ad0faba8435b0e0ee3c3aa`, after which the formal
  P04 output left one Approved stress-fixture pagination anchor unresolved.
- Frozen documents affected: 02, 03, 03A, 04, 07
- Decision: promote the exact 55-record r6 batch without changing Candidate bytes; bind 55
  per-record ApprovalRecords and one batch ApprovalRecord; keep Dev/Test empty and Test unlocked;
  evaluate P04 and unchanged B0 on the Approved Pilot-stage batch. The P04 mismatch must fail the
  Exit Gate and must not be used to revise the human Gold. The approved file SHA-256 is
  `7e12edb2b66912d915b1d1ca3b7df873edb910cb7dcaf57d07872c83d84964ea`.
- Compatibility/migration impact: evaluation-only Approved data, audit records, Pilot IDs, formal
  Runner and tests. No product HTTP API, database migration, runtime configuration, parser
  behavior, source binary, OCR, index, commit, deletion or formal Test lock.
- Evaluation impact: four structural metrics are strictly better than B0 and common-metric
  regressions remain within two points, but the absolute DOCX mapping Gate fails at 9/10. The
  failing record is `ds1-pagination-doc-ai-algorithms-systems-structure-stress-5.3`, whose P04
  page anchor is null at confidence `0.00398406374501992`. P05 stays blocked until P04 is repaired
  and the exact Approved Gold is rerun successfully.

## ED-P04-DS1-D005 — Resolve fixture bookmarks before scoring DOCX pagination

- Status: accepted
- Date: 2026-07-31
- Trigger: read-only OOXML inspection showed that the structure-stress fixture inserts three
  Section-break paragraphs. Approved bookmarks `src_p_001034`, `src_p_001614` and `src_p_003782`
  therefore correspond to parser paragraph ordinals 1035, 1615 and 3785, not the parent-source
  indexes 1034, 1614 and 3782. The original formal Runner ignored `source_unit_id` and scored the
  wrong parser Blocks; the P04 aligner itself had already assigned the bookmarked Blocks.
- Frozen documents affected: 02, 03, 03A, 04, 07
- Decision: preserve the exact Approved r6 Gold and approval chain. In the evaluation-only formal
  adapter, resolve each Approved `source_unit_id` against raw OOXML top-level paragraphs, map a
  bookmark to the paragraph ordinal used by `StructuredDOCXParser`, and require the OOXML
  reference Hash and parsed Block Hash to equal the Approved `source_text_sha256`. Missing,
  duplicate or Hash-mismatched identities fail closed. Text search and system-output-derived
  fallback are prohibited.
- Compatibility/migration impact: evaluation Runner, regression test and reports only. No Gold,
  source binary, product parser/aligner, HTTP API, database, migration, runtime configuration,
  index, OCR, commit or Test lock changes.
- Evaluation impact: the old 9/10 report remains audit evidence but is superseded for Gate
  decisions. Two corrected runs on the same Approved SHA-256 reproduce identical metrics and
  diagnostics: 10/10 physical, 5/5 observable display and 5/5 observable Section mappings. Every
  strict Gate check passes, so P04 is complete and P05 becomes eligible to start.

## P05-D001 — OCR execution uses the approved balanced resource envelope and stays disabled by default

- Status: accepted; default-disabled clause superseded by P05-D004
- Date: 2026-08-02
- Trigger: P05 requires comparable local OCR candidates without expanding the default runtime or
  silently consuming unbounded CPU and memory.
- Frozen documents affected: 02, 03, 04, 07
- Options: embed all engines in the service image; select one engine before evidence; isolate the
  three candidates under one fixed resource profile.
- Decision: use 200 DPI, 20MP per page, 60 seconds, 1.5 GiB process-tree RSS and one sequential
  Worker. RapidOCR, Tesseract and PaddleOCR use isolated evaluation profiles. Runtime networking
  and Provider fallback are prohibited. `COURSERAG_OCR_PROVIDER` remains `disabled` until the
  evidence and a later explicit human engine choice exist.
- Compatibility/migration impact: additive configuration and evaluation images only. No public
  API, Graph, legacy Parser/Chroma behavior or Active Index changes.
- Evaluation impact: every candidate receives the same raster inputs and resource bounds; a
  candidate exceeding them is reported as failed rather than receiving relaxed limits.
- Follow-up: P05-D004 retains this 60-second envelope for the three-candidate comparison, then
  records the owner's explicit RapidOCR selection and a separately validated 90-second
  `default_v1` runtime Profile.

## P05-D002 — P05 OCR Gold uses a raw-region/body-projection split and exact Course Owner approval

- Status: accepted
- Date: 2026-08-02
- Trigger: CER and region metrics require independent OCR Gold, while system predictions cannot
  define their own labels.
- Frozen documents affected: 03, 03A, 04, 07
- Options: infer Gold from Top-K/OCR output; reuse route-only labels as text Gold; discard non-body
  raw regions; or retain source-grounded raw regions while evaluating an explicit body projection.
- Decision: r1 with SHA-256
  `2e48d78b1f48e9357bd32c02d7aa75b907318db2d71a5423a1da8cb348068865` is returned and
  superseded. r2 reuses 11 exact Approved P04 PageGold records and creates only four missing page
  annotations. It preserves all raw text/geometry, but body text and body CER exclude headers,
  footers, page numbers, QR-related regions, figures, embedded-image text and figure captions.
  Figure captions remain separately addressable. r2 with SHA-256
  `a497cc36cb599afcb77948821fe5a7e028041b0ade563c4b5d4062a0fc54b215` was returned because seven
  split captions marked only the number while leaving the adjacent figure name in body text. r3
  deterministically groups a same-baseline number/name pair near the same figure; only those seven
  record Hashes change. The resulting r3 Candidate SHA-256 is
  `c203f05d2cccc5cd5fcf557a7a5eed19d86c4ecae181cd14d88a863792baa065`; its review-index
  SHA-256 is `8446888b1836943c8c90efeca7c9cc53caef2f6deb4aed340c81920d099e0fb2`.
  The Course Owner explicitly approved that exact r3 Hash. Promotion produced the physically
  separate Approved file SHA-256
  `62824129f3525a90bcbdd3d4570d9aa6a3768c0db6949c3c2ceafa7e7ce53c51` and batch
  ApprovalRecord SHA-256
  `f81b2e71d97e75eb22e40a6f8e14790e2d72877db3b0f7d326c905c0b7669af0`.
  Replaying the approval returned the same Hashes without duplicating review records.
- Compatibility/migration impact: evaluation-only Candidate/approval files. No database, product
  runtime, Provider, source binary, Test lock, commit or deletion change.
- Evaluation impact: body and raw CER are reported separately; body Region, BBox and reading-order
  metrics use only body roles. Approved P05 OCR Gold now authorizes the three-engine Pilot, but
  does not itself choose the default Provider.

## P05-D003 — Provider identity and repeatability fail closed

- Status: accepted
- Date: 2026-08-02
- Trigger: candidate wheels can bundle/download model files whose identity differs across images,
  making CER and reproducibility claims invalid.
- Frozen documents affected: 03, 04, 07
- Options: accept package version alone; download models during runtime; require resolved runtime
  manifests containing exact model-file Hashes and immutable image IDs.
- Decision: checked-in candidate Manifests remain explicitly unresolved. An evaluation image must
  resolve package, engine and model files, write exact hashes, and bind them with the Profile and
  image ID. Missing or changed identity fails before OCR output; no alternate Provider is tried.
- Compatibility/migration impact: evaluation container and internal Adapter validation only.
- Evaluation impact: Cache and resume reject identity/config differences; two-run comparison uses
  semantic result hashes that intentionally exclude latency and peak-RSS observations.

## P05-D004 — RapidOCR is the human-selected default under a validated 90-second Profile

- Status: accepted
- Date: 2026-08-02
- Trigger: the exact Approved r3 Gold enabled two isolated runs of each OCR candidate, but no
  candidate simultaneously provides high quality and fully stable completion under the frozen
  60-second resource envelope.
- Frozen documents affected: 02, 03, 04, 07
- Options:
  - select RapidOCR as `default_v1` while explicitly accepting its one-of-two
    `ds1-ocr-04` timeout and semantic-repeatability risk;
  - retain `COURSERAG_OCR_PROVIDER=disabled`, leave P05 pending and do not start P06;
  - reject all three current candidates and separately approve a new optimization/candidate phase.
- Decision: the owner explicitly selected RapidOCR as `default_v1` and then explicitly confirmed
  a 90-second per-page hard limit. Retain 200 DPI, 20MP, 1.5 GiB process-tree RSS, one sequential
  Worker, runtime networking disabled and fail-closed Provider behavior. Tesseract and PaddleOCR
  remain non-default evaluation candidates and are never automatic fallbacks.
- Evidence: the checked `default_v1` file SHA-256 is
  `ca962f3ba5f8c4053e502acfe3e36928351a24650db2fad589d153a4d6a719a0`. The resolved runtime
  Profile identity is `1ead48fec1275cd9581f0079870bca60fcaabbea777c5909751a79ac2290623d`,
  model Manifest SHA-256 is
  `1f4c39ecbdd0a249adfe28d3f4f42ee8899a3951b31d4bf79710d2d978f88bf4`, and immutable image ID
  is `sha256:a02def1a83823adf83c64efe3f86753086feb641a0a9d1849726bff83f9f3c3d`.
  Two independent 90-second runs complete 15/15 pages with zero warning/resource-limit pages,
  body macro CER 0.009765, Region Recall@0.5 0.779330 and identical per-page semantic Hashes.
  Report SHA-256 values are
  `a5ebe1f16240f074a848a4db2ab4d692e79c06685fb64cc4647dde2d5ecb9418` and
  `27ee9cef5aaa2c5bc5a32f7137e701ac946b626aec1f007fad24f747f463ac6e`.
- PaddleOCR clarification: the locked Adapter is local CPU inference and requires no API key.
  Its 15/15 failures come from a local PaddlePaddle oneDNN/PIR conversion error; disabling oneDNN
  still failed to finish the first diagnostic page within 120 seconds.
- Compatibility/migration impact: default OCR configuration, Profile and service-image build
  recipe now select RapidOCR. The public API, Graph, Active Index, legacy B0 path and database
  schema remain unchanged. Setting the Provider back to `disabled` is the immediate rollback.
- Evaluation impact: P05-T07 and all three Exit Gates pass. P06 receives its prerequisite; this
  decision does not start P06 or authorize later-phase behavior.

## ED-PRE06-DS2-D001 — Replace the source-incomplete 1.4.1 window with complete Section 1.3.7

- Status: accepted
- Date: 2026-08-03
- Trigger: the supplied PDF excerpt ends immediately after the `1.4.1` title and a truncated first
  sentence, so the frozen 8×5 PDF allocation cannot obtain five complete semantic units from that
  Section without inventing or extending source content.
- Frozen documents affected: 02, 03, 03A, 04, 07
- Options: A) use the source-complete, dense `1.3.7 AI＋电子支付` Section on pages 31–32;
  B) reduce the PDF Section/Evidence allocation; C) retain incomplete fragments.
- Decision: the owner explicitly selected A. Keep eight PDF Sections and five Evidence records per
  Section, replace only `1.4.1` with `1.3.7`, and retain OCR parent page 32. The boundary starts at
  the exact `1.3.7` heading and ends immediately before the `1.4` heading. No text is completed,
  paraphrased or imported from outside the two supplied sources.
- Compatibility/migration impact: evaluation-only selection and provenance; no database, public
  API, product configuration, P06 implementation or source-binary change.
- Evaluation impact: the formal DS2 Candidate contains 24 complete Section windows (16 DOCX and
  eight PDF) while preserving the 80/40 allocation. Results remain limited to two independent
  semantic sources.

## ED-PRE06-DS2-D002 — DS2 stays Candidate-only until all 120 records and the exact file Hash are approved

- Status: accepted
- Date: 2026-08-03
- Trigger: P06 Evidence Builder output must not define its own Gold, and partial/group review must
  not silently promote unreviewed Evidence.
- Frozen documents affected: 02, 03, 03A, 04, 07
- Options: approve generated records automatically; approve four groups independently into Gold;
  retain one immutable Candidate and require complete review plus one exact batch approval.
- Decision: construct Evidence only from raw OOXML, native PDF/Poppler objects, fixed DOCX renders
  and already-Approved P04/P05 records. Retain pre-delivery audit revisions as superseded. Each
  offline group may export decisions, but promotion requires all 120 reviewed IDs, all four group
  IDs, no returned record and literal Candidate SHA-256
  `f4295f9783b131a8305713765907e169a83dc741d6c9af390b0b67b2f15b5bfc`.
- Compatibility/migration impact: additive evaluation Schema/generator/approval CLI only. The
  public API, business database, runtime Provider/defaults, Dev/Test and Test lock are unchanged.
- Evaluation impact: Approved DS2 and B1/B2 do not exist yet. Exact approval will create a
  physically separate Approved file, 120 record ApprovalRecords, a batch record and append-only
  review log before P06 formal evaluation is authorized.

## ED-PRE06-DS2-D003 — Preserve 98 accepted r5 records and revise only the 22 returned records

- Status: accepted
- Date: 2026-08-03
- Trigger: the Course Owner completed all four r5 review groups, accepting 98 records and returning
  22 for missing formula symbols, incomplete algorithm/list text, inaccurate semantic labels or
  insufficient necessary context.
- Frozen documents affected: 02, 03, 03A, 04, 07
- Options: regenerate all 120 records; modify the 22 records in place under r5; create append-only
  r6 while retaining the 98 accepted record Hashes and decisions.
- Decision: create immutable r6. Preserve all 98 accepted record Hashes and review decisions; revise
  only the 22 returned records from original OOXML and the frozen LibreOffice render. Eight records
  receive new stable Evidence IDs because source text/source units changed. Use the frozen rendered
  formula linearization profile for equations 14, 16, 18, 19 and 20 and the perceptron algorithm.
  Classify DOCX TableGold 0 as `procedure`, producing ten TableGold-derived records with a 9-table /
  1-procedure semantic distribution. Mark r5 `rejected`; never overwrite it.
- Compatibility/migration impact: additive evaluation Schema and revision generator only. Public
  HTTP API, business database, product configuration, source binaries and P06 implementation are
  unchanged. The literal r5 Hash in D002 is superseded by r6 SHA-256
  `f35292d55f6848e18f6e8067a8ca0e72cf0bedae49e92d60cd05cc1513c1b35c`; D002's complete-review
  and exact-approval governance remains in force.
- Evaluation impact: only 22 r6 delta records require re-review. Approved DS2 and B1/B2 still do
  not exist; P06 remains blocked until zero returns and exact r6 approval.

## ED-PRE06-DS2-D004 — Audit necessary neighbors for all 120 records using nearest/minimum exact source context

- Status: accepted
- Date: 2026-08-03
- Trigger: after completing the r6 review, the Course Owner found that necessary context had been
  treated as a generic Section-heading flag. The owner required an all-record audit that resolves
  pronouns, list/table scope, formula symbols, code scope, sequence and semantic dependencies.
- Frozen documents affected: 02, 03, 03A, 04, 07
- Options: keep r6 context fields; add a heading to every record; attach full preceding paragraphs;
  or create a context-only r7 using the nearest/minimum exact source passage for each real dependency.
- Decision: create immutable r7 and audit 120/120 records. Attach neighbors only when required;
  standalone records remain empty. Use table captions/headers, list lead-ins, exact antecedents,
  formula definitions, code definitions and process statements rather than generic Section headings.
  The Course Owner explicitly waived another item-level review for this delegated context-only
  revision. Exact batch SHA-256 approval remains mandatory and is not delegated.
- Compatibility/migration impact: r7 changes only `requires_parent` and necessary-neighbor fields.
  Gold text/content Hashes, stable Evidence IDs, source units/spans, BBoxes, semantic labels, public
  API, database and runtime configuration remain unchanged. r6 is marked superseded, not overwritten.
- Evaluation impact: 55 records require real neighbors and 65 are standalone; 78 record Hashes
  change due only to context metadata. The literal r6 Hash in D003 is superseded by r7 SHA-256
  `ebc980a4f52a763001bd2169c1215aac81eac55f4f661f7320a0e600e0acdcad`. Approved DS2 and B1/B2
  remain absent until exact batch approval.

## ED-PRE06-DS2-D005 — Promote exact r7 to Approved DS2 and open the P06 formal-input gate

- Status: accepted
- Date: 2026-08-03
- Trigger: the Course Owner explicitly approved formal DS2 Candidate SHA-256
  `ebc980a4f52a763001bd2169c1215aac81eac55f4f661f7320a0e600e0acdcad` after the r7
  all-record necessary-neighbor audit.
- Frozen documents affected: 02, 03, 03A, 04, 07
- Options: keep r7 Candidate-only; accept a generic approval; or promote only after literal file
  Hash, all 120 record Hashes, complete zero-return decisions, empty Dev/Test and unlocked Test
  validation.
- Decision: use the literal-Hash path. Create a physically separate Approved DS2, embed one
  `ApprovalRecord` in each of the 120 records, persist one batch approval and append 120 record-level
  review-log entries. A repeated approval must return identical file Hashes and append nothing.
- Compatibility/migration impact: evaluation data and governance metadata only. No HTTP API,
  database, migration, runtime configuration, source binary or P06 implementation is changed.
- Evaluation impact: `gold_status=ds2_p06_evidence_approved` and
  `phase_input_status.p06=formal_eval_ready`. This authorizes P06 implementation/formal B1/B2
  evaluation; it does not assert that the P06 Exit Gate has passed.

## P06-D001 — Stable Evidence identity is source-derived and independent from Chunk profiles

- Status: accepted
- Date: 2026-08-04
- Trigger: permanent citations must survive Chunk profile changes, while persisted rows still use
  internal database UUIDs and legacy Chunk IDs are not stable source identities.
- Frozen documents affected: 02, 03, 04, 07
- Options: reuse Chunk IDs; derive Evidence IDs from generated text only; derive a versioned stable
  key from DocumentVersion, ordered source Block/ranges and exact content Hash.
- Decision: use `ev1_<sha256>` as the external stable Evidence key. Its identity binds the
  DocumentVersion, ordered Block IDs, character ranges, per-unit text Hashes and combined content
  Hash, but excludes Chunk/Profile identity. Persist source Block links, page BBoxes and adjacency
  separately. Chunk Sets and `ch1_*` IDs bind the exact Evidence Artifact, tokenizer and versioned
  Chunk Profile; every Child has exactly one Parent and explicit Evidence coverage ranges.
- Compatibility/migration impact: additive 0011 tables/columns only. The legacy Chunk path remains
  readable and is not converted to Evidence. IndexVersion becomes nullable for pre-index Chunk Sets;
  its FK uses `SET NULL`, while P10 retains responsibility for citation migration/cutover.
- Evaluation impact: changing the Chunk Profile changes ChunkSet/Chunk identities but leaves the
  Evidence Artifact and stable Evidence IDs unchanged; focused tests verify this invariant.

## P06-D002 — Token counting and Stage identity fail closed on the checked local tokenizer

- Status: accepted
- Date: 2026-08-04
- Trigger: token-limit behavior cannot be reproducible if a missing tokenizer silently falls back
  to characters, another encoding or a network-fetched model.
- Frozen documents affected: 02, 04, 07
- Options: approximate token counts; permit automatic tokenizer fallback; require the exact local
  tokenizer and bind its Hash into the Chunk Profile and Stage fingerprint.
- Decision: require `coursepilot-local-tokenizer-v1` with SHA-256
  `ecb6f9fc369894346f0511f4074ca75cee5cd5f3b06d02f1ba35fcd39f8e121d`.
  Profile `parent_child/v1` fixes Parent 1200/1600/2200 tokens, Child 250/350/500 and overlap 48.
  Missing or changed tokenizer/Profile identity fails before Stage execution; there is no network
  download or implicit fallback.
- Compatibility/migration impact: additive configuration only; public HTTP APIs, CoursePilot
  Graphs, legacy Chroma and B0 behavior are unchanged.
- Evaluation impact: both formal runs bind the same Profile/tokenizer/source identities and produce
  byte-identical system output SHA-256 `bfa6a41e3063520b281da4413a2bce6348b41c85dcb8180f5063fa6b76e6d396`.

## P06-D003 — Formal B1/B2 scoring consumes Approved DS2 only after product output is frozen

- Status: accepted
- Date: 2026-08-04
- Trigger: DS2 uses logical evaluation document identities, while runtime P04/P05 Artifacts use
  version UUIDs; resolving that mismatch after inspecting Gold could leak labels into output.
- Frozen documents affected: 03, 03A, 04, 07
- Options: copy Gold IDs into runtime objects; score by unrestricted text search; use the approved
  work-package lineage as a fixed adapter after building product output.
- Decision: build B1/B2 solely from P04 structured Artifacts and stored P05 RapidOCR results, freeze
  product output, then apply the already-approved work-package UUID-to-logical-document mapping for
  scoring. Gold IDs/text are never imported into product modules. B1 is a fixed flat 1000/150
  character baseline; B2 is the checked Evidence/Parent-Child implementation. No tuning,
  LLM-as-a-Judge or system-output-derived Gold is allowed.
- Compatibility/migration impact: evaluation adapter and ignored `storage_eval` artifacts only;
  no public runtime contract or Approved dataset is changed.
- Evaluation impact: exact Approved DS2 SHA-256
  `f49d84027cde8341d906e270d29cc46e7b71eb6de4da5220188cb03894436b78` is scored in two
  independent runs. Report/run metadata differ by design, while system output is byte-identical.

## ADR Template

- Status: proposed / accepted / rejected / superseded
- Date:
- Trigger:
- Frozen documents affected:
- Options:
- Decision:
- Compatibility/migration impact:
- Evaluation impact:

## P07-D001 — Freeze representative source-grounded DS3 Candidate and family-isolated split

- Status: accepted_owner_approved
- Date: 2026-08-04
- Trigger: P07 needs independent Knowledge Point Gold before implementation, while P06 maps only
  101/120 Approved Evidence records at runtime and the source corpus contains only two courses.
- Frozen documents affected: 02, 03, 03A, 04, 07
- Options: derive Gold from P07/P06 outputs; add external facts; select teachable source concepts
  backed by Approved Evidence and expose upstream coverage separately.
- Decision: select 107 teachable concepts from the complete 24-Section source packets; bind every
  item to exact Approved DS2 Evidence, use verbatim Evidence as Candidate Summary, keep a separate
  empty DS2-KP addendum when no new Evidence is necessary, and isolate concept families in a
  deterministic 75/32 calibration/holdout split.
- Compatibility/migration impact: evaluation-only additive Schemas, Candidate files and CLI; no
  product API, database, runtime configuration, P06 Gold or formal result changes.
- Evaluation impact: P07 must later report both all-Gold and P06-runtime-resolvable subsets. The
  holdout may be run only once after calibration threshold freezing and is not the project Test.
  On 2026-08-05 the Course Owner attested both review passes complete with zero returns and approved
  exact Bundle SHA-256 `2ebd8f96bb8bd6f0c178dce7545ef991cceb181c6cfe2a3554592bc3daf10400`.

## P07-D002 — Keep model confidence outside the deterministic publish score

- Status: accepted
- Date: 2026-08-05
- Trigger: the technical discussion mentions model confidence, while the frozen P07 stage Prompt
  explicitly defines publish score as evidence, naming, cross-window, ambiguity and duplicate
  components and prohibits treating model self-confidence as a publication probability.
- Frozen documents affected: 02, 03A, 04, 07
- Options: add model confidence as a sixth score term; discard it; retain it only as extraction
  trace metadata and score the five deterministic components.
- Decision: retain optional `model_confidence` in the Provider result for diagnostics only. The
  versioned score uses weights 0.35/0.20/0.20/0.15/0.10 for evidence/naming/cross-window/
  ambiguity-safety/duplicate-safety. A threshold pass creates `unreviewed`, never `approved`.
- Compatibility/migration impact: no public legacy API or Gold change. The score Profile Hash binds
  the exact weights and 0.75 default; human review remains the only path to Approved Gold/assets.
- Evaluation impact: threshold reports are reproducible and cannot be inflated by an uncalibrated
  Provider self-assessment.

## P07-D003 — Repair DS3 Calibration/Holdout isolation at the Provider input Window boundary

- Status: accepted_exact_protocol_approved_and_calibration_completed
- Date: 2026-08-05
- Trigger: implementation-time leakage guard found that family-level assignment isolates all 107
  concept families, but 17 of 24 source Section Windows contain both calibration and holdout KP
  labels. A Provider call sees the whole Window, so the current split cannot support a claim that
  holdout inputs/outputs remained unseen during threshold calibration.
- Frozen documents affected: 03, 03A, 06, 07
- Options: (A) regenerate the 75/32 split by Section/Window group, accepting a changed ratio and
  fewer independent groups; (B) keep the existing family split only as descriptive Pilot strata
  and defer threshold calibration to future Section-isolated Dev Gold; (C) claim family isolation
  is sufficient despite shared inputs.
- Decision: the Course Owner selected option A. Build the split from connected components of
  Section/Provider Windows and concept families, preserving all 107 Approved Gold records and the
  prior r1 split byte-for-byte. The deterministic r2 result is 75 calibration / 32 holdout,
  actual ratio `0.7009345794392523`, and zero mixed Scopes. Its protocol Candidate Bundle is
  `7261cb63b81f5b2e260a6a578383bd41df55c690aae999891d479146395b215b`; the Course Owner separately
  approved that exact Bundle before Calibration.
- Compatibility/migration impact: product code, API, ORM and Gold records are unchanged. Option A
  would change only the split/Manifest approval chain and therefore requires explicit owner action.
- Evaluation impact: option C remains rejected. Calibration completed on only the r2 Calibration
  Scopes. The Holdout can run only after exact threshold-freeze approval.

## P07-D004 — Resolve P07 Provider settings through explicit overrides then COMPATIBLE inheritance

- Status: accepted
- Date: 2026-08-05
- Trigger: the owner directed P07 to use the model/API fields already present in `.env.example`
  without duplicating credentials or hard-coding a model.
- Frozen documents affected: 04, 05, 07
- Options: duplicate live values into new P07 fields; hard-code an endpoint/model; use optional
  P07 overrides and inherit `COMPATIBLE_MODEL`, `COMPATIBLE_BASE_URL` and `COMPATIBLE_API_KEY`.
- Decision: select explicit `COURSERAG_KP_*` values first and inherit the matching `COMPATIBLE_*`
  values when blank. The Provider fails before work if any required field is absent; no fallback,
  endpoint switching or reasoning/thinking parameter is sent.
- Compatibility/migration impact: additive configuration only. Secrets remain `SecretStr` and are
  excluded from Run Manifests, checkpoints, reports and errors.
- Evaluation impact: local validation confirms provider/model/base/key are configured without
  printing their values. Sending textbook-derived Evidence to that external endpoint remains
  governed by P07-D005.

## P07-D005 — Authorize P07 textbook-derived Evidence transfer to the configured Provider

- Status: accepted
- Date: 2026-08-05
- Trigger: the real P07 Provider evaluation needs to send Section/Window Evidence derived from the
  two supplied textbooks to the external compatible endpoint configured through `.env.example`.
- Frozen documents affected: 03, 03A, 04, 06, 07
- Decision: the Repository Owner explicitly authorized this transfer. Continue to redact endpoint,
  credential and raw Provider error values; do not persist Secrets in Manifests, reports, cache
  identities or logs. This authorization does not approve a split, threshold or Provider output.
- Compatibility/migration impact: no API, ORM, migration or product-runtime behavior changes.
- Evaluation impact: the exact P07-D003 r2 Protocol was approved and Calibration completed. No
  Provider output defined, revised or approved Gold; Holdout remains a separate one-time action.

## P07-D006 — Freeze the measured 0.75 publish threshold before Holdout

- Status: accepted_exact_owner_approval
- Date: 2026-08-05
- Trigger: exact r2 Calibration completed and must freeze a threshold before the only Holdout run.
- Frozen documents affected: 03, 03A, 04, 06, 07
- Options: retain 0.75; select another pre-evaluated grid threshold; change Prompt/model/matcher and
  recalibrate; tune after seeing Holdout.
- Candidate: deterministic selection over 0.50–0.95 maximizes F1, then precision, recall, proximity
  to the existing 0.75 default, then the higher threshold. It selects 0.75 with precision
  `0.051136`, recall `0.12`, F1 `0.071713` and 176 published candidates. Bundle SHA-256 is
  `c4406f507a5a4350fb254cc299adb9c5071b3664a7fdb61a4f77dd7578eda1e9`.
- Minimal safe default: do not run Holdout until the owner approves the exact Candidate. Do not
  interpret low exact-name F1 as a threshold-only problem; P07-R09 retains extraction/naming debt.
- Compatibility/migration impact: the Candidate recommends no Profile, API, ORM or migration
  change. Approval would freeze the existing 0.75 value for Holdout.
- Evaluation impact: Holdout runs exactly once after approval, with no threshold, Prompt, model,
  matcher or Window changes and no Test tuning.
- Approval: the owner approved exact Candidate
  `c4406f507a5a4350fb254cc299adb9c5071b3664a7fdb61a4f77dd7578eda1e9`; Holdout then completed once
  at 0.75. No rerun or post-Holdout tuning occurred.

## P08-D001 — Separate Retrieval Gold approval from P09 QA Gold and P06 gap diagnosis

- Status: accepted_plan_candidate_pending_review
- Date: 2026-08-05
- Trigger: P08 needs fixed Dev retrieval judgments before hybrid/RRF/reranker evaluation, while
  Claims and answer Rubrics belong to P09 and 19 Approved DS2 units remain unmapped by P06 runtime.
- Frozen documents affected: 02, 03, 03A, 04, 07
- Decision: build 60 DS4 and 100 DS5 Retrieval-only Candidate records from Approved DS2/DS3;
  retain all QA fields as `pending_p09`; freeze Dev 60 / Test 40 families without locking Test; and
  mark exactly ten distinct P06 gaps as a 6/4 diagnostic layer. P06 output may mark this layer but
  cannot define Query text, positive relevance, hard negatives or answerability.
- Compatibility/migration impact: evaluation Schema extensions and offline tooling only. Product
  HTTP API, ORM, migrations, runtime Provider configuration and P06/P07 Approved artifacts remain
  unchanged.
- Evaluation impact: P08 tuning can later load only the 54 `retrieval_main` Dev IDs. Dev-all 60 and
  diagnostic 6 remain reporting scopes; Test 40 is reviewed now but stays unavailable to P08.

## P08-D002 — Supersede opaque and heuristic r1 with source-readable r2

- Status: accepted_candidate_pending_review
- Date: 2026-08-05
- Trigger: Course Owner review showed that IDs without resolved text were not independently
  auditable, one DS4 AI edge case linked unrelated Knowledge Points, and one DS5 occupational
  automation case assigned an unrelated one-point result while demoting relevant context to zero.
- Frozen documents affected: 02, 03, 03A, 04, 07
- Decision: preserve r1 byte-for-byte and generate r2. Resolve every KP/Evidence ID inline to
  Approved names, exact text, necessary adjacency and source location; replace all 30 heuristic
  DS4 edge cases with curated source-grounded cases; remove all unverified heuristic one-point
  labels; select zero-point candidates outside every Required Source Package; and rewrite generic
  paraphrase/procedure prompts into content-specific questions. Recompute stable Query identities,
  Split and Bundle identity without changing upstream Gold.
- Compatibility/migration impact: evaluation Candidate, review UI and fail-closed Loader only.
  Product APIs, database schema, Provider/runtime configuration and Approved P06/P07 artifacts are
  unchanged.
- Evaluation impact: r1 cannot be approved. R2 Bundle
  `7f6b22556e3261d242dbd2b425812eeb18489dc75f6086697d808bbffbfbdf52` requires a new full
  160-record first review and the frozen 132-record blinded second review before exact approval.

## P08-D003 — Adjudicate r2 returns and comprehensively rebuild retrieval judgments as r3

- Status: accepted_option_b_candidate_pending_review
- Date: 2026-08-05
- Trigger: the r2 first review returned 25 records. Its browser exporter preserved the returned IDs
  but omitted textarea notes. Source-level inspection accepted 17 objections, retained eight
  intentional routing/expansion/retrieval boundary cases, and found broader systemic weaknesses in
  cross-Section wording and hard-negative selection.
- Frozen documents affected: 02, 03, 03A, 04, 07
- Decision: preserve r1/r2 and the exact r2 feedback artifact; generate r3 from r2 plus an explicit
  adjudication artifact. Rewrite every cross-Section prompt so it does not assert a relationship not
  present in the source; run exact containment checks and same-course confounder ranking over all
  100 DS5 cases; expose all Evidence text and judgment rationales; and export reviewer identity,
  timestamp and per-record notes. Re-display all retained r2 returns with their rationale instead of
  silently treating them as carried passes.
- Compatibility/migration impact: evaluation Candidate Schema, deterministic generator, review UI
  and tests only. No product API, database migration, runtime configuration, Approved P06/P07 Gold,
  Dev/Test or Test Lock change.
- Evaluation impact: r1 and r2 cannot be approved. R3 Bundle
  `ff64abba71d392496e7ce530f7de5c612794616557b65a7aa11e739e20759396` requires review of 117
  changed/adjudicated records in the first pass and the frozen 132-record blinded second pass before
  exact approval. Forty-three unchanged r2 pass decisions are inherited only when their record
  hashes are identical.

## P08-D004 — Record explicit all-passed P08 review through conversation attestation

- Status: accepted_review_complete_approval_pending
- Date: 2026-08-06
- Trigger: after reviewing the r3 package, the Course Owner explicitly stated that all records pass
  and that browser-exported review JSON need not be inspected or supplied.
- Frozen documents affected: 03, 03A, 07
- Decision: materialize the explicit statement as separate first- and second-pass
  `course_owner_conversation_attestation` artifacts. They must bind the exact r3 Bundle, preserve
  manifest record order, cover exactly 160/132 records, contain zero returns and identify the
  reviewer and timestamp. Conversation attestation replaces only the manual browser export, not
  the separate exact approval checkpoint.
- Compatibility/migration impact: backward-compatible evaluation review Schema and offline tool
  only; previous P08 review JSON remains valid. No product API, database, runtime configuration,
  Approved dataset, Split or Test Lock change.
- Evaluation impact: both r3 review passes are complete. Promotion remains blocked until the Course
  Owner approves the exact Bundle SHA-256 with the required literal approval statement.

## P08-D005 — Approve exact r3 Retrieval Gold and open only the P08 Dev boundary

- Status: approved
- Date: 2026-08-06
- Trigger: the Course Owner supplied the required literal approval for exact Bundle
  `ff64abba71d392496e7ce530f7de5c612794616557b65a7aa11e739e20759396` after both review passes.
- Frozen documents affected: 02, 03, 03A, 04, 07
- Decision: promote 60 DS4 and 100 DS5 Retrieval records, write Dev 60 / Test 40 IDs, keep Test
  unlocked, and allow P08 tuning to load only the 54 `retrieval_main` Dev records. Preserve all QA
  fields as empty with `qa_gold_status=pending_p09`; Retrieval approval does not approve P09 QA.
- Compatibility/migration impact: Approved evaluation artifacts, Split IDs, governance Manifest,
  ApprovalRecords and append-only review log only. No product API, database migration, Provider or
  runtime configuration change.
- Evaluation impact: Pre-P08 input is `formal_dev_eval_ready`. P08 may use only the Approved Dev
  boundary; the 40 Test IDs remain unavailable while `test.lock.json` is unlocked.

## P08-D006 — Freeze the versioned hybrid retrieval implementation contract

- Status: accepted_implementation
- Date: 2026-08-07
- Trigger: P08 requires Dense, BM25S, fusion and Reranker stages to remain independently
  ablatable while keeping legacy CoursePilot behavior available.
- Frozen documents affected: 02, 03, 04, 07
- Decision: use version-bound Dense Top 30 and BM25S Top 30, equal RRF at `k=60`, Fusion Top 30,
  then an explicitly configured Reranker and return Top 8. Chroma stores vector identity and
  filter metadata only; returned text/Evidence must cross the Repository hydration boundary.
  Evaluation failures use `fail_sample`; production may return Fusion order only with the stable
  warning `RERANKER_FAILED_FUSION_ORDER_RETURNED`. Backend defaults to `legacy`; explicitly
  selected `versioned` without a valid Active Index fails closed and never falls back to legacy.
- Compatibility/migration impact: additive Search fields and reversible 0013 only. Existing API
  fields, endpoints, legacy Chroma Collections and Active P03 index remain unchanged.
- Evaluation impact: all stage Rank/Score and latency fields are retained. Different Provider
  absolute scores must not be compared or share a rejection threshold.

## P08-D007 — Compare Jina and Cohere under explicit cost, privacy and Secret gates

- Status: accepted_execution_completed_owner_freeze_pending
- Date: 2026-08-07
- Trigger: the owner selected Jina plus Cohere, verified minimal connectivity and authorized the
  transfer of the 54 Dev queries and candidate excerpts, conditional on remaining in free quotas.
- Frozen documents affected: 03, 04, 07
- Decision: compare Jina and Cohere only, one listwise request per Query/Provider, against the same
  30 fused candidates. Hard stops are 8,000,000 estimated/Provider-reported Jina tokens, 500 Cohere
  Search Units/requests and 500,000 Embedding input tokens. Two runs must have identical ranked
  result Hashes; the second uses the exact rerank cache. Test IDs, complete source documents, Gold
  labels and user identity are never sent.
- Minimal safe default: the exposed credential remains revoked and replacement Secrets remain only
  in ignored `.env`. Until the exact Freeze Candidate is separately approved, the default Reranker
  remains disabled and no `default_v1` is written.
- Compatibility/migration impact: Provider/model/endpoint are configuration, not business-code
  constants. No automatic payment, Provider switch, model download or silent fallback is allowed.
- Evaluation impact: the Approved r3 Bundle was loaded read-only and only its 54 `retrieval_main`
  Dev cases were evaluated. Two Run result Hash sets reproduce; D009 records the exact owner
  Freeze approval, so P09 now meets its phase prerequisite.

## P08-D008 — Select a reproducible Embedding execution path after ModelScope moderation instability

- Status: accepted_local_offline_embedding
- Date: 2026-08-07
- Trigger: the owner confirmed Secret rotation and explicitly authorized sending all 1,327 Child
  Chunks to ModelScope. A one-text CourseRAG probe succeeded after adding the Provider-required
  `encoding_format=float`. Formal Dense builds then repeatedly failed on batch `128:192` with
  `Input data may contain inappropriate content`, while an unchanged diagnostic request for that
  exact batch subsequently succeeded. The result is not deterministic enough for a formal B3-B5
  baseline.
- Frozen documents affected: 03, 04, 07
- Decision: use the local/offline `Qwen/Qwen3-Embedding-0.6B` snapshot at
  `D:\AI\models\modelscope\Qwen\Qwen3-Embedding-0.6B`. Freeze the complete snapshot SHA-256
  `1db2c971796b1b286f6b73a22ee05c213a51211fdb595640cc361c1b790c9920`, weights SHA-256
  `0437e45c94563b09e13cb7a64478fc406947a93cb34a7e05870fc8dcd48e23fd`, 1,024 dimensions,
  CUDA 12.6/BF16/SDPA, maximum length 2,048, batch size 8 and query prompt `query`. Runtime verifies
  both bundle and weights and uses `local_files_only=True`.
- Minimal safe default: keep a single frozen local model identity per IndexVersion; do not retry,
  split or redact requests to bypass external moderation and do not mix Provider vectors.
- Compatibility/migration impact: no public API, database, Gold or legacy Chroma change. The local
  runtime is an explicit optional dependency and can be disabled or replaced by Profile rollback.
- Evaluation impact: the exact 54-Dev B3-B5 comparison completed twice without external Embedding
  calls. The Reranker Freeze remains a separate course-owner decision under P08-D009.

## P08-D009 — Select the P08 default Reranker from the exact formal Dev Freeze Candidate

- Status: accepted
- Date: 2026-08-07
- Trigger: two formal Runs reproduce the B3/B4/B5 result Hashes using exact Approved Bundle
  `ff64abba...` and frozen local Embedding. Freeze Candidate SHA-256 is
  `5b5d973ebf70d32cc10fa0ad4103261eee745dc4604f9e9f1a693817d3c3c95f`.
- Candidate evidence: Cohere has Recall@10 `0.8858`, MRR@10 `0.7384`, nDCG@10 `0.8259`, Complete
  Group Recall@8 `0.8426`, threshold `0.7502601` and rerank P95 `19,486 ms`. Jina has
  `0.7593`/`0.5537`/`0.6664`/`0.7130`, threshold `0.11734294` and P95 `4,518 ms` respectively.
  Cohere used 54 Search Units; Jina used 224,207 reported tokens. Both had zero Fallback/warnings.
- Decision: the course owner approved exact Candidate SHA-256
  `5b5d973ebf70d32cc10fa0ad4103261eee745dc4604f9e9f1a693817d3c3c95f` and selected Cohere
  `rerank-v4.0-pro` with Provider-specific rejection threshold `0.7502601` as `default_v1`.
  The checked Profile SHA-256 is
  `dc4109b16fb0bdfda8b226ca7f66adeb6a8b833b9a213eecea36adb1e1afcb3d`.
- Safety default: the Profile is frozen and discoverable, but runtime Provider activation remains
  explicit and Secret-gated; an unconfigured deployment remains `disabled`. Absolute scores are
  not compared across Providers. Production fallback remains Fusion order with a visible warning.
- Compatibility/migration impact: no public API, ORM or migration change. Rollback remains
  Reranker `disabled` and/or retrieval backend `legacy`; the approved Profile and audit evidence
  remain retained.

## P09-D001 — Keep QA and Context Gold as immutable overlays on Approved P08 Retrieval Gold

- Status: accepted_candidate_pending_owner_review
- Date: 2026-08-07
- Trigger: P08 approved Query/relevance records must be reused for P09 without implying that the
  earlier retrieval-only approval covered answers, Claims or refusal behavior.
- Decision: create separate 100-record QA and Context overlays bound to every P08 Query and record
  Hash. Context Gold defines complete Evidence Groups, minimal Approved-DS2 neighbors, budget and
  boundary constraints but no unique item order. Factoid/list cases retain short answers; other
  answerable cases use atomic source-verbatim Claims. Forbidden Claims are emitted only when the
  paired Required Evidence grounds a concrete comparison-conflation risk.
- Human review: first-pass all 100; second-pass every unanswerable, multi-Evidence, comparison,
  procedure, cross-Section, OCR/formula/table or otherwise high-risk record plus a stable 20% sample
  of the remainder. Candidate promotion requires both complete review artifacts and literal Bundle
  Hash approval.
- Test policy: freeze Test Gold identity but keep `test.lock.json` unlocked and prohibit P09 loaders
  from reading Test. P10 locks Test only after the full configuration is frozen.
- Compatibility/migration impact: evaluation-only additive Schemas and loaders; no product API,
  database migration or runtime configuration change. Approved P08 Retrieval Gold remains intact.

## P09-D002 — Audit answer obligations and revise only semantically incomplete r1 records

- Status: accepted_owner_reviewed_and_approved
- Date: 2026-08-07
- Trigger: the Course Owner observed that many cases have empty short-answer arrays, including
  multi-part questions. Frozen 03/03A permits empty short answers for explanatory, comparison and
  procedure cases, but requires complete atomic Claims; an all-case audit found 18 r1 records whose
  Claims were incomplete or insufficiently atomic.
- Decision: retain short answers only for factoid and finite-list questions. For every answerable
  case, store explicit answer obligations and require their union of atomic Required Claims to cover
  the whole Query. Treat an empty short-answer array as “scored by Claims”, not as absent Gold.
  Claims may use an exact Approved-DS2 necessary neighbor only when the support source and neighbor
  identity are explicit. One ERNIE procedure receives a new nearest/minimum source neighbor verified
  from raw OOXML and the frozen render; no P09 runtime output or external fact is used.
- Review inheritance: preserve the explicit Course Owner r1 all-pass attestation for the 82 unchanged
  QA and 99 unchanged Context records. Both blinded passes must re-review all 18 semantic changes;
  exact r2 approval remains a separate action.
- Compatibility/migration impact: additive evaluation Schema only; no P08 Query/Retrieval mutation,
  public API, database migration, runtime configuration, Test lock or Approved P09 artifact.

## P09-D003 — Use independent intent and retrieval-strategy route axes

- Status: accepted_owner_authorized
- Date: 2026-08-07
- Trigger: frozen product routing defines six question intents while Approved DS4 stores three
  retrieval strategies; forcing either enum into the other would change approved Gold semantics.
- Decision: retain `intent_route` as fact/definition/comparison/procedure/example_application/
  cross_section and `retrieval_strategy` as hybrid_retrieval/metadata_filtered_retrieval/
  unanswerable_audit. Each axis has its own Trace field, enum and metric. Explicit filters always
  survive Normalize, Rewrite and Retry.
- Compatibility/migration impact: additive contract fields with defaults; legacy Search decoding
  and existing Approved DS4 records remain unchanged.

## P09-D004 — Use an explicit DeepSeek capability profile and separate Q0 plain-answer baseline

- Status: accepted_owner_authorized
- Date: 2026-08-07
- Trigger: the owner authorized DeepSeek Dev Query/Context calls and selected the dual-axis
  contract. DeepSeek V4 requires an explicit non-thinking setting, while Q0 must remain a plain
  Prompt/no-abstention baseline rather than inherit the structured cited-QA contract.
- Decision: only the `deepseek_v4` capability profile sends `thinking=disabled`; unknown compatible
  Providers receive no thinking parameter. Q1-Q3 use the strict two-status Claim-Evidence JSON
  contract and one Repair. Q0 uses a separate evaluation-only plain-answer JSON contract with no
  Claim, Citation or refusal field. Provider, endpoint and model remain configuration values.
- Evaluation boundary: only 60 Approved Dev queries and bounded Context were sent; Test, Gold
  labels, complete files, identity data and Secrets were excluded. No LLM-as-a-Judge was used.
- Compatibility/migration impact: the plain contract is evaluation-only; product QA remains
  structured and fail-closed.

## P09-D005 — Keep the final P09 profile pending exact owner Freeze approval

- Status: candidate_pending_owner_approval
- Date: 2026-08-07
- Trigger: formal Dev completed with report SHA-256
  `8cf07e7026a58a8750ff455101440b9338f7713b9a51ed28dc52ad59b2f7f197`.
- Candidate: SHA-256
  `c88d7ffe2386e0c41fe393becf6f47809bc983ffee2a7e683378e42165169c3d`.
  Q3 binds every answered Claim to a resolvable Context Evidence ID and rejects all six main-Dev
  unanswerable cases, but one QA repair failure, low intent accuracy and B8 coverage regression
  remain explicit.
- Decision: do not create `default_v1`, mark P09 passed or start P10 until the course owner accepts
  this exact Candidate (or requests a separately approved correction).

## P09-D006 — Repair Answer Grounding as a joint answer-shape and Evidence-citation contract

- Status: accepted_execution_completed_protocol_failed
- Date: 2026-08-08
- Trigger: the approved Protocol r2 showed that the prior Gate Repair improved citation precision
  and recall, but Q3 short-answer token F1 remained 0.02221 below Q2, narrowly missing the allowed
  0.02 protection delta. Repeatedly tuning citation selection alone would optimize one coupled
  metric while leaving answer granularity and list completeness unstable.
- Decision: keep frozen B7 retrieval and B8 context selection unchanged, add per-Evidence Context
  Segments, classify Answer Shape into factoid/list/explanatory/comparison/procedure, require a
  bounded v3 structured Provider output, and compose each atomic Claim/list item only to Context
  Evidence. The Candidate uses one Fresh Dev run, at most one schema Repair per Case, no Test,
  no Cohere call and no post-run prompt iteration. Runtime activation remains pending an exact
  owner Freeze approval.
- Budget: separately authorized DeepSeek cap 375,000 tokens; whole P09 cap remains 2,500,000;
  additional Cohere cap is zero. The measured conservative one-pass estimate is 212,804 tokens;
  the 425,608 all-Repair theoretical bound is intentionally constrained by a fail-before-call hard
  stop rather than a budget increase.
- Execution evidence: Protocol Manifest SHA-256 `211bf746...`, Answer Grounding Profile SHA-256
  `345500b7...`, B7 Snapshot SHA-256 `d85d9603...`. The owner resumed the exact Manifest locally;
  60/60 Dev Cases completed with report SHA-256 `b04fc9b...`, conservative Answer Grounding usage
  `199,264` tokens and zero Cohere units. Protocol r2 evaluation SHA-256 `4fea2768...` failed, so no
  Freeze Candidate or default profile was written.
- Post-run finding: the runtime Composer changed citations in 25 main-Dev Cases, improved zero and
  reduced Gold Evidence overlap in nine. More importantly, the current automated metric is global
  Evidence-ID overlap, while frozen document 03 defines Claim-level support judged per Citation
  Link; the earlier Shadow Composer also selected only among Gold-mapped Evidence. A new evaluation
  contract must be approved before further Provider tuning.
- Compatibility impact: additive Pydantic fields only; no database migration, public endpoint
  removal, Gold mutation, Test access, legacy behavior change or P10 work.

## P09-D007 — Separate Evidence-ID overlap from formal human Claim-Citation scoring

- Status: accepted_implementation_at_phase1_human_checkpoint
- Date: 2026-08-09
- Trigger: the fixed Answer Grounding report used global predicted/Gold Evidence-ID overlap under
  the names Citation Precision/Recall, while frozen document 03 requires each Citation Link to be
  judged against its bound Claim. The earlier Shadow Composer also filtered candidates through a
  Gold mapping and is therefore ineligible as runtime or Freeze evidence.
- Decision: retain Evidence-ID overlap only as an explicitly named diagnostic; calculate formal
  Gold Claim Coverage, Claim correctness, Citation support and Citation P/R/F1 from Hash-bound
  human decisions. Phase 1 hides Gold Claims and asks the Course Owner to judge 150 fixed system
  Claims and 150 Citation Links. Only after those decisions are submitted and Hash-locked may a
  second Gold Claim Mapping package be generated. No label is auto-filled or auto-approved.
- Automatic-metric correction: Short Answer EM/F1 applies only to nine factoid Dev Cases; List Set
  metrics apply only to two list Cases and use structured `list_items`. Q2 and Q3 are recomputed
  under the same contract. Existing thresholds are not relaxed after observing the output.
- Evidence: fixed Package SHA-256 `ffde9da5...`, repaired review index `96b421e2...`, decision template
  `1dba5ba7...`, recovery exporter `6a0f10a0...`, Manifest `0c5e46a0...`; counts are 54 main Dev, 47 answered, six abstained, one
  failed, 150 Claims, 150 Citation Links and 117 hidden Required Gold Claims.
- Compatibility impact: evaluation-only additive Schema and tooling; no Provider call, Test read,
  Gold mutation, database/API/configuration change or runtime default activation.

## P09-D008 — Lock Phase 1 before exposing Gold Claim Mapping

- Status: accepted_at_phase2_human_checkpoint
- Date: 2026-08-09
- Trigger: the Course Owner submitted and explicitly approved Phase 1 Decisions SHA-256
  `52e0044ecc702e3ecc0cc9c0b3045a0f5a1f4c0aeaa95dc86f37c0a7b50ec314`.
- Decision: persist a deterministic approval record before generating Phase 2. Phase 2 reuses the
  exact fixed system answers and immutable Phase 1 labels, then exposes only the Approved Required
  Gold Claims and their exact source excerpts. Only Claims locked as `correct_supported` or
  `correct_but_uncited` may map to Gold. Missed Gold Claims are the exact complement of mappings.
- Evidence: approval SHA-256 `1213567444943afeb32ed41df3c5164c3a021dd6429116ec44193ef28259110c`;
  Phase 2 Package `0ad531262b39d660c580c7797712b395d6f21bfa8be5c48105df69d0c9f07ffb`;
  review index `3585c9f7e25ec8f20e319cbbf9c2bc60280e6e5975bc38f3e93efe2448d8a717`;
  exporter `3a58fefc33e25486ec51d62184e783adc8fc39e1fb744ba6c7e76dd1eb5dc3ba`.
- Compatibility impact: evaluation-only additive schemas and local static artifacts. No Test access,
  Provider call, Gold mutation, runtime behavior, database, API or configuration change.

## P09-D009 — Do not Freeze on strong Citation metrics while independent guards fail

- Status: accepted_fail_closed_result
- Date: 2026-08-10
- Trigger: owner-approved Phase 2 Decisions SHA-256
  `85cb33ebdf2d26ab7360fda3d59738746de5bf1bae6a433a26120f1e146fcd58`
  made formal Claim-Citation scoring available for the first time.
- Decision: keep formal human Citation metrics separate from corrected automatic answer metrics and
  retain every preregistered non-Citation guard. Citation P/R/F1 of `0.9600/0.8034/0.8748` does not
  override the non-zero QA failure or the Q3 factoid Short-answer F1 regression versus Q2. The
  result is Profile-Gate-failed and no Freeze Candidate/default profile is written. P10 was blocked
  at this checkpoint; P09-D011 later supersedes only that phase-progression consequence while
  retaining the failed Profile result and all metrics.
- Evidence: Phase 2 Approval `87e61b5fe9a444d3bc22ce0d4a403a0031761fb46c38cb7fd350f9e77dc354b3`;
  formal Report `652d2a08dcd1c7b175002fc5f4d32ec1beb71bbc2991a81b6a6175c746a9c392`;
  formal Manifest `341c128784bee31c8eb558f3375b45d7a83e7092099c3f2aba881ff1cb0693ba`.
- Compatibility impact: evaluation-only result and governance update. No Provider call, Test access,
  Gold mutation, database/API/configuration/runtime change or downstream phase execution.

## P09-D010 — Reject the first Generation Reliability candidate under the joint Freeze Gate

- Status: accepted_fail_closed_result
- Date: 2026-08-10
- Trigger: the preregistered 12-Case Approved-Dev delta completed under Protocol Manifest
  `52e32dbb...` and Candidate Profile `8b2c7b37...`.
- Decision: reject rather than freeze the candidate. Compact Evidence aliases and the 3,200-token
  list contract fixed the original long-list JSON failure, but the single QA failure moved to the
  task-factoid path and factoid Token F1 reached only `0.360260`, below the fixed protection floor
  `0.406108`. Local improvement in list transport cannot override the joint zero-failure and
  short-answer guards.
- Stop rule: keep the candidate disabled by default; perform no post-result Prompt tuning, second
  candidate, human delta review, Freeze Candidate or default-profile write inside P09. Any further
  P09 candidate attempt requires a new owner-approved architecture and evaluation protocol;
  independent P10 progression is governed by the later owner-approved P09-D011 classification.
- Evidence: run Report `fc7b0bbe...`, Checkpoint `0da50dcf...`, automatic Gate `a3f38797...` with
  status `failed_no_further_tuning`; 82,552/180,000 additional DeepSeek tokens, P09 cumulative
  907,286/2,500,000, Cohere zero and Test access false.
- Compatibility impact: candidate-only static-type/runtime code remains behind an explicit
  default-off flag. No database migration, public API, retrieval, Gold, Test or production-default
  behavior changed.

## P09-D011 — Separate the frozen P09 phase Exit Gate from QA Profile Freeze

- Status: accepted_owner_approved
- Date: 2026-08-10
- Trigger: the owner determined that repeatedly tuning two uneven answer-quality metrics would block
  downstream development even though the frozen P09 implementation contracts are already met.
- Decision: classify P09 as `completed_with_quality_debt`. The frozen P09 Exit Gate passes because
  Query Processing is independently ablatable, every answered Claim binds resolvable Context
  Evidence, and all six main-Dev unanswerable Cases are correctly rejected with zero false answers.
  The stricter Generation Reliability Profile Gate remains failed; Candidate `8b2c7b37...` stays
  rejected and default-off, and no failed metric or threshold is rewritten.
- Downstream boundary: mark P10 `ready_to_start` with P09-R08/R09/R20/R21 carried forward. P10 must
  preserve the hard safety/grounding guards, preregister any single Dev calibration window before
  Test, run Test only after configuration freeze, and never tune on Test. This decision authorizes
  governance reclassification only, not P10 implementation or further Provider calls.
- Evidence: formal Citation P/R/F1 `0.9600/0.8034/0.8748`, Citation resolvability and Claim-Citation
  completeness `1.0`, Claim-aware Answerability F1 `0.9895`, unanswerable recall `1.0`, false-answer
  rate zero, and complete Query Step toggle tests. The one fail-closed QA error, factoid F1
  `0.360260`, List Set F1 zero, intent accuracy `0.3958` and B8 coverage `0.7130` remain explicit
  non-hidden quality debt.
- Compatibility impact: documentation/status only. No code, API, database, configuration, Gold,
  Test, runtime default, Provider call, commit or downstream phase implementation changed.

## GOV-D001 — Adopt cross-phase quality gates and two explicit convergence points

- Status: accepted_owner_approved
- Date: 2026-08-10
- Trigger: P09 exposed a repeatable governance failure mode: a useful but stricter Profile Freeze
  guard could be mistaken for a frozen Phase Exit Gate, while coupled diagnostic metrics could
  invite repeated local tuning and block unrelated downstream work.
- Decision: adopt `QUALITY_GATE_POLICY.md` for P10—P19. Every phase separates L0 hard safety and
  contracts, at most three L1 primary metrics, L2 regression guards and L3 diagnostics; it also
  separates Phase status from Profile Freeze status. P10 is the CourseRAG convergence point and
  P18 is the CoursePilot/system convergence point.
- Tuning/Test boundary: one bounded, preregistered calibration window per phase; existing stricter
  decisions prevail. Dev is the only tuning split. Test runs only after configuration freeze and
  cannot feed the same release's tuning. Regression scope follows declared change impact rather
  than rerunning every expensive evaluation or omitting affected downstream Sentinels.
- Current application: P09 remains `completed_with_quality_debt`; Candidate `8b2c7b37...` remains
  rejected/default-off; P10 stays `ready_to_start` and must carry P09-R08/R09/R20/R21.
- Compatibility impact: governance documentation only. Frozen product decisions, code, database,
  API, config, Gold, Test lock, runtime defaults and external Provider state are unchanged.

## P10-D001 — Freeze the formal P10 input package and staged Test boundary

- Status: accepted_for_candidate_construction
- Date: 2026-08-10
- Trigger: P09 completed with quality debt and P10 required formal DS6–DS8 plus security inputs
  before implementation and convergence evaluation.
- Decision: construct DS6 as 9 scenarios/24 citation judgments with Dev/Test 5/4, DS7 as 12
  scenarios with Dev/Test 7/5, DS8 as 20 cold/warm templates, and 16 bounded Security/Fault
  controls with Dev/Test 10/6. Controlled non-semantic adversarial fixtures are permitted but
  cannot enter the course corpus or create a third semantic source.
- Gold boundary: Verified Content uses Approved Dev questions, Claims and Evidence only, with
  DOCX/PDF 7/3. DS8 binds Test only by Split Hash and must not expose Test IDs before the later
  owner-approved Test lock. Current construction performs no Provider call or P10 system run.
- Review/quality decision: first review covers all 57 records; second review covers all security,
  all ambiguous/invalid citation cases, all writeback/enrichment cases and a deterministic 20%
  remainder. L0 failures are zero-tolerance; L1 thresholds are Citation Migration 95%, theoretical
  Artifact Reuse 85% and Manifest/Resume reproducibility 100%.
- Compatibility impact: evaluation-only additive Schemas, Candidates, provenance and local ignored
  controls. No product API, database migration, runtime default, P09 Gold/Profile, Test lock or
  external state changes.

## P10-D002 — Accept conversation review attestation and exact separate approval

- Status: accepted_owner_approved
- Date: 2026-08-10
- Trigger: the Course Owner completed both review rounds, reported every item passed with no
  requested change, intentionally did not export the browser decision JSON, and subsequently
  supplied the exact approval phrase for Bundle `5b6d756a...`.
- Decision: preserve the owner's exact statement and SHA-256 as a
  `course_owner_conversation_attestation` for each required pass. The artifacts enumerate all 57
  first-review and 29 second-review IDs as passed; they do not claim to be browser exports.
- Approval result: batch `.002` produced Approval Manifest `a3886277...`, four Approved datasets
  and 57 record-level approvals bound to exact Candidate record hashes. Exact replay is idempotent.
  The earlier automated `.001` attempt that altered the owner's review statement stays invalidated
  in provenance quarantine and is not part of the valid approval chain.
- Boundary: this approves only P10 evaluation inputs. Test remains unlocked/unread, P10 has not
  run, and P09 quality debt remains visible.

## P10-D003 — Use conservative Section impact planning and reviewable citation migration

- Status: accepted_owner_approved
- Date: 2026-08-10
- Trigger: P10 requires useful incremental reuse without allowing missed changes or forced citation
  remapping to inflate performance metrics.
- Decision: match Sections by stable path/hash, unique content moves, same-path edits and unique
  structural candidates, while treating ambiguity as reprocessing. Citation migration proceeds
  through still-valid, unique exact/structural, neighborhood and unique similarity matches. The
  frozen similarity thresholds are auto `0.92`, review `0.75` and minimum margin `0.08`.
- Safety rule: Change Coverage must be 100% before reuse ratio is meaningful. Ambiguous citation
  candidates become `needs_review`; deleted/unresolvable sources become `invalid`. Chunk IDs are
  never promoted to stable citation identity.
- Compatibility impact: additive P10 facts and internal Application/Build Ports only; no existing
  public endpoint is repurposed for citation migration.

## P10-D004 — Separate verified overlay and narrow legacy whole-artifact write-back

- Status: accepted_owner_approved
- Date: 2026-08-10
- Trigger: the old review path could append entire Lesson/PPT artifacts to legacy Chroma, violating
  the frozen whitelist and Primary-source boundary.
- Decision: preserve Primary and teacher-verified indexes as separately versioned active pointers.
  Only approved question, answer explanation and lesson fragment payloads with stable Evidence may
  enter the overlay. Writes and revocations publish a validated candidate overlay atomically and
  retain immutable audit facts.
- Legacy compatibility: keep `/api/coursepilot/reviews/{id}/write-back` and its response fields;
  whole Lesson/PPT returns `requires_fragment_selection`, and legacy chunk-only references return
  `requires_evidence_migration`, both without index/database side effects. No old data is deleted.
- Deployment boundary: CourseRAG v1 uses trusted gateway claims for course/role authorization;
  the gateway must strip client identity headers and inject authenticated values. Missing or
  inconsistent claims fail closed.

## P10-D005 — Preregister one bounded Dev calibration before a separate Test lock

- Status: accepted_owner_approved_protocol_preregistered
- Date: 2026-08-10
- Trigger: P09 carried coupled Factoid/List/schema quality debt, while the cross-phase policy
  prohibits an unbounded tuning loop and any Test-driven tuning.
- Decision: use one candidate on exactly 12 Approved Dev cases, reuse the other 42 by Hash, rerun no
  retrieval, allow at most 180,000 DeepSeek tokens and zero Cohere Search Units, and prohibit
  post-result tuning. Canonical Protocol identity SHA-256 is
  `f253f3752793ee95b19d5ab106b7ce15a33ab775d7dc584442d21de382d7f6de`.
- Authorization state: the protocol records `external_data_authorized=false` and `test_access=false`.
  The Dev call requires a new explicit owner authorization. A successful Dev gate can only create
  an awaiting-lock Frozen Manifest; formal Test then requires separate exact-Hash and budget
  approval. Test results cannot tune this release.

## P10-D006 — Accept the bounded Dev result and require a combined freeze identity

- Status: accepted_dev_result_awaiting_owner_test_lock
- Date: 2026-08-10
- Trigger: the Course Owner authorized canonical Protocol
  `0dd9ff64ba94b9a0f6e3389565b17eb7e88d1ffd63b19e0e58775f7e6f462696`. An initial QA-only
  freeze artifact would not have bound the required DS6/DS7/Security Dev evidence, so it was not
  eligible to unlock Test.
- Execution result: exactly 12 Approved Dev cases were called, 42 were reused by Hash, retrieval
  was not rerun, and usage was 86,042 DeepSeek tokens plus zero Cohere Search Units. Every frozen
  QA safety/grounding check passed. Factoid Token F1 is `0.441279` versus floor `0.406108`; both
  List cases answered with cited items. The remaining List Set F1 diagnostic of `0.0` is disclosed
  as quality debt and does not trigger post-result tuning.
- Component result: DS6 Citation Migration is 15/15, DS7 Change Coverage and eligible Artifact
  Reuse are both 1.0, and Security is 10/10, with no Test access, Provider call or fallback.
- Decision: supersede the earlier QA-only preliminary identity with combined Frozen Manifest v2,
  SHA-256 `f90f4f1bf6a363106ee1185beb1274b1f914168a6de05f29ee22474b0bc0b019`. It binds QA Report
  `eed5700e...`, QA Gate `74e52ba3...`, Component Report `ca5c0f4d...`, usage audit `93a3a0c8...`,
  workspace, Profile, Approved Bundle and Test-ID file Hash.
- Boundary: this is not Test authorization. Test stays unlocked and cannot be read or transmitted
  until the Course Owner separately approves the exact v2 Manifest and formal Provider budgets.
  Formal Test results cannot tune this release.

## P10-D007 — Refreeze after formal-runner and deterministic-workspace repair

- Status: accepted_owner_approved_and_executed
- Date: 2026-08-10
- Trigger: after the owner approved Manifest `f90f4f1b...`, execution preflight found that the
  approved workspace lacked the formal Test orchestrator and included mutable Python bytecode in
  its workspace identity. Running under that identity would not be reproducible or auditable.
- Safe action taken: Test stayed unlocked and unread; no Test data or Provider call occurred. A
  Test-only loader, B3-B8/Q0-Q3 and DS6/DS7/Security orchestrator, exact Resume/usage restoration,
  fail-sample and clean-Git guards were added. Workspace hashing now excludes interpreter caches.
- Candidate result: all 540 tests pass with five gated skips, Ruff and Mypy pass, B0 smoke passes,
  Alembic remains at the single 0015 head, Component Dev remains byte-identical at `ca5c0f4d...`,
  and repeated workspace identity is `fffdd6d6...`. Repaired Frozen Manifest candidate SHA-256 is
  `cad5df9ce87fc9682bef2441ed66aa957064f467a5ffdbd209b37e358c40937a`.
- Required authority: exact owner reapproval must bind the prior 40-query and Provider budgets to
  this new identity. Because Test Lock is tracked and the generic Test guard requires a clean Git
  state, a local checkpoint commit containing the complete current P00-P10 workspace and lock is
  also required before execution. No push or PR is implied.
- Approval/execution result: the owner approved exact Manifest `cad5df9c...`, the 40-query external
  scope, Cohere 240 Units, DeepSeek 1,500,000 tokens and local checkpoint commit. Commit `3665211`
  was clean; the formal Test ran with exact Lock and no push or PR.

## P10-D008 — Record the locked formal Test L0 failure without Test-driven repair

- Status: accepted_formal_result_gate_failed
- Date: 2026-08-11
- Trigger: exact locked Test execution completed under Manifest `cad5df9c...`. Retrieval and QA
  completed 400 Case-system executions with zero Fallback, while one of six Security controls was
  not marked as prompt injection.
- Result: DS6 is 9/9; DS7 Change Coverage/Reuse are 1.0/1.0; Retrieval B5 nDCG@10 is `0.8006`;
  Q3 Citation Resolvability, Claim-Citation Completeness and Unanswerable Recall are 1.0, with zero
  False Answer, QA Failure and Fallback. Formal usage is 118/240 Cohere Units and
  404,354/1,500,000 DeepSeek tokens.
- L0 failure: the detector did not recognize the policy-override wording in
  `p10-sec-15-prompt-injection`. No artifact, database write or external call resulted, but the
  required warning was absent. Security zero tolerance therefore fails and P10 status is
  `gate_failed_formal_test_security`; P11 remains blocked.
- No-tuning decision: do not add the Test phrase to the current regex, alter thresholds, change
  Gold or rerun this release. A next-version Dev protocol must design broader multilingual
  instruction-hierarchy/policy-bypass controls, refreeze all identities, and treat this formal miss
  only as a disclosed regression Sentinel.
- Performance debt: DS8 offline cold/warm workloads were not executed and cannot be inferred from
  local tests. They remain next-release work after the L0 repair.

## P10-D009 — Repair injection marking at parsed-text boundary and require a new blind release

- Status: blind_gate_failed_frozen_no_retuning
- Date: 2026-08-11
- Trigger: the consumed P10 Test exposed one policy-bypass paraphrase that was invisible to the
  raw-binary scanner. Adding the exposed sentence to a regex would make the old Test pass without
  proving that the architecture detects the behavior family.
- Root cause: upload safety and semantic content safety were combined before PDF/DOCX
  decompression, parsing and OCR. Even observable text had no Page/Block/Span finding contract,
  and the original phrase list represented wording rather than command intent.
- Decision: retain upload MIME/ZIP/PDF/resource checks before persistence, but run a deterministic,
  versioned multilingual prompt-injection scanner after structured parsing and OCR merge. Detect
  policy override, role impersonation, secret extraction, tool coercion and light obfuscation by
  command/target combinations. Preserve source text and propagate locatable warnings through
  Evidence and Chunk audit metadata.
- Stable-identity decision: security annotations change full Artifact Hashes, but not semantic
  Evidence or Chunk identities. Chunking therefore uses an Evidence projection that excludes only
  `PROMPT_INJECTION_MARKED`; all other warning and semantic changes remain identity-sensitive.
- Evaluation governance: use a 30-case Dev set for Profile selection, treat the exposed P10 case
  only as a regression sentinel, and require an independently constructed 8-positive/4-negative
  blind Test. Implementation cannot read that Bundle before exact Manifest approval and lock.
- Current evidence: Dev recall is 20/20 with 0/10 hard-negative false positives; two real documents
  preserve 4,852 Blocks, 1,848 Evidence records and 1,048 Child Chunk semantic identities; Test
  lifecycle and DS8 evidence pass. This is not final Security L0 approval until the new blind Test
  is owner-locked and passes once without feedback into the current Profile.
- Profile Freeze approval: on 2026-08-11 the Course Owner explicitly approved Candidate SHA-256
  `ffe8f58220cf3b1b821d25e25a681a34cef039d8cf20d8ab87c929c5cb71401e`. This freezes the
  Scanner/Profile and authorizes independent Blind construction; it does not approve or lock an
  as-yet nonexistent Blind Bundle.
- Blind delivery checkpoint: Bundle `7394dfd462993c54e0b262d63c276e097c83eb2f32c99574472c81fdac0a62ee`
  and two review artifacts `a44d36b5...` / `f7cb11aa...` were received and hash-validated without
  reading Bundle content. Both reviews bind the exact Bundle and cover the same 12 unique IDs with
  12/12 pass, 8-positive/4-hard-negative distribution, distinct reviewer identities and no Scanner
  access. This is evidence delivery only; exact Bundle approval and Lock remain separate Owner acts.
- Blind result: the Course Owner separately approved and locked the exact Bundle, which was consumed
  once against Manifest `ffe8f582...`. Report `f07fc7c8660b7669c1e971b38c590fec0b97ac5d06040a083368ec84521f8d2e`
  failed with TP=1, FN=7, FP=3 and TN=1. The public Sentinel and all side-effect/provider/no-tuning
  guards passed. Decision: do not inspect raw Blind text, tune the frozen Profile or rerun this
  Bundle; retain P10/P11 blocking and require a materially new detector/version with a new release.

## P11-D001 — Keep pre-P11 material as a 37-record non-approvable Draft while P10 Gate is failed

- Status: accepted_and_implemented; dependency conclusion superseded by P10-D013
- Date: 2026-08-11
- Decision: freeze the complete P11 target as `1/9/12/18 = 40`, but materialize only the 37
  P10-independent contract records until P10's L0 Security Gate is repaired and passed.
- Boundary: the Draft is physically separate from `candidates/`, carries no approval or Bundle
  identity, does not change CoursePilot `gold_status=skeleton_no_formal_gold`, and leaves Dev/Test
  empty and Test unlocked.
- Deferred records: the two Approved Dev Query normal-path fixtures and the structural
  cross-course/stale/unresolvable fail-closed fixture are added only after the P10 gate audit is
  fully green. No CourseRAG Test or DS3 Holdout identity may be read.
- Approval meaning: a future exact approval promotes only a P11 implementation input work package,
  never formal CP-DS0—CP-DS8 Gold. The post-P11 Runtime Foundation Snapshot requires a separate
  exact approval and still does not replace the P18 formal Gold freeze.

### P11-D001 P10-D013 adaptation result — 2026-08-12

The generator now accepts only the exact owner-approved P10-D013 waiver identity while binding the
unchanged failed P10.3 report, no-Profile/default-off state, unread Blind commitment and inherited
security constraints. It produced the complete 40-record Candidate; the exact Bundle identity is
recorded in its Candidate Manifest and phase report.
This does not change the failed detector verdict and does not promote formal CP Gold.

### P11-D001 Foundation input approval result — 2026-08-12

The Course Owner approved exact Bundle
`ed28509cfbfdba2c530b91b63fa879f1dd50700bd8b4ca4858c271838fb25522` after complete 40-record first
review and fixed 27-record blind second review, both with zero returns. The promotion scope is only
`p11_foundation_input_contract_only`; it authorizes P11 implementation input but does not approve
CP-DS0—CP-DS8 formal Gold or relax the P10-D013 inherited security constraints.

## P10-D010 — Replace regex-only marking with a local semantic Prompt Guard stage

- Status: accepted_architecture_implementation_in_progress
- Date: 2026-08-11
- Trigger: the frozen P10.1 regex Profile failed its independent Blind Gate with TP=1, FN=7,
  FP=3 and TN=1. Re-running or adding Blind phrases would invalidate the release rather than repair
  the generalization failure.
- Selected option: the Course Owner selected architecture A, a local
  `meta-llama/Llama-Prompt-Guard-2-86M` classifier under the separately applicable Llama 4
  Community License. Model weights remain outside Git at
  `D:\AI\models\huggingface\meta-llama\Llama-Prompt-Guard-2-86M`; upstream license and Notice are
  retained, while repository-owned source remains MIT licensed.
- Architecture: run a separate post-OCR `security_annotation` Stage over overlapping tokenizer
  windows. The model owns the semantic attack score. Deterministic rules may refine category/span
  or confirm a middle score, but cannot independently mark content. Missing model, wrong Hash,
  timeout or CUDA failure is fail-closed and never falls back to the failed regex Profile.
- Identity boundary: Parser/OCR fingerprints no longer include the security Profile. Security
  annotation may change audit Artifact Hashes and Warning metadata but must not change source text,
  Evidence/Chunk stable identities, corpus mapping or public API payloads.
- Evaluation: use only an owner-approved 160-case Dev Candidate and one pre-registered threshold
  grid. After at most one threshold-only revision, freeze one Profile and construct a new independent
  48-case Blind Test. The consumed P10.1 Blind Bundle is never read, reused or rerun.
- Current checkpoint: implementation/Fake tests pass. Real model download is blocked by missing
  Hugging Face authentication, and Dev calibration is blocked by the required human approval of
  Candidate `d017a907...`. These are explicit checkpoints, not automatic defaults.
- Follow-up checkpoint: the owner approved exact Candidate `d017a907...`; approval artifact
  `d50315a0...` covers all 160 IDs. HF authentication now succeeds for account `nancy0929`, but
  gated content still returns 403 because the account has not yet been added to the model's
  authorized list. The locked CUDA runtime was recovered from a complete local uv cache:
  Torch `2.12.1+cu126`, Transformers `5.14.1`, CUDA available on RTX 4060. No mirror was used to
  bypass model access control.
- Dependency replacement (2026-08-12): Meta rejected the owner's gated access request. The owner
  explicitly selected the preregistered public fallback
  `protectai/deberta-v3-base-prompt-injection` at immutable revision
  `373b6af0f8d16739cff5de28be326652246bfaa3` under Apache-2.0. It reuses the same binary-score,
  window, dual-threshold, rule-consensus and fail-closed contracts; it does not change the Approved
  Dev dataset or unlock Blind. Only Safetensors/tokenizer/model-card files are allowed. A public
  mirror may transport the bytes without an HF Token, but every file must match the SHA-256
  allowlist derived from the official revision before a Manifest can be emitted. ProtectAI's
  primarily-English upstream scope is not treated as equivalent to Meta multilingual quality;
  Chinese and English must independently pass the owner-approved Dev and later Blind gates.
- Backup result checkpoint: the Hash-bound ProtectAI model loaded locally with CUDA FP16 and no
  network fallback. The approved Dev run produced report `dda19635...`, but every preregistered
  threshold failed. Best grid recall/specificity was `0.2375/0.7375`; an exhaustive read-only
  separability audit across observed scores achieved only `0.50625` balanced accuracy. The
  upstream English-focused classifier missed semantic paraphrases and indirect attacks while
  overmarking quoted/hard-negative text, especially Chinese. This is a representation/domain
  mismatch, not a threshold-range defect. No Profile was emitted, Blind stayed unread, and the
  result cannot be repaired by adding thresholds or weakening the L0 Gate.
- Second-backup checkpoint (2026-08-12): the owner explicitly approved the public multilingual
  `HikmaAI/hikmaai-mdeberta-v3-base-prompt-injection-multilingual` model at immutable revision
  `aef60fed9674e497a7ba08e43b41e8666483934e`, its FP16 ONNX artifact, and one reuse of the exact
  Approved Dev and preregistered threshold grid. The fixed snapshot is stored outside Git and
  validated by Manifest file/canonical/Bundle SHA-256 `f5332023...`/`bebebecf...`/`b1aa09e9...`;
  the upstream ONNX and tokenizer LFS SHA-256 values match `52b3cd13...` and `9ddbe35b...`.
  ONNX Runtime uses CUDA as the first execution provider, permits CPU only for required static
  shape/constant graph nodes, disables whole-session runtime fallback, and fails closed if CUDA is
  unavailable. The single Dev report `29abe241...` failed all six pairs: Recall `0.775`,
  Specificity `1.0`, English Recall `0.90`, Chinese Recall `0.65`, and tool-coercion Recall `0.50`.
  This is a remaining semantic coverage gap, not permission to add thresholds or rerun Dev. No
  Profile was emitted; Blind remains unread and P10/P11 remain blocked.
- ModelScope Meta-source checkpoint (2026-08-12): after being informed that the public
  `LLM-Research/Llama-Prompt-Guard-2-86M` repository is an uncertified `USER_UPLOAD`, that its
  license metadata is `other`, and that Hash equality cannot prove redistribution authority, the
  Course Owner explicitly accepted this provenance/license risk and authorized local use. The
  repository does include the Llama 4 Community License and Acceptable Use Policy. The fixed
  ModelScope commit `be11c20d...` was downloaded outside Git; all eight selected files match the
  ModelScope repository API SHA-256 values. Manifest file/canonical/Bundle identities are
  `292cede1...`/`fc27f708...`/`ca7df59c...`. This records an owner-accepted non-official source,
  not Meta approval and not proof of uploader redistribution authority. A two-case CUDA FP16 smoke
  passed on RTX 4060 (attack `0.999386`, benign `0.000415`, peak allocated VRAM about 552.7 MiB).
  No Dev or Blind evaluation was run at this checkpoint; default runtime remains unchanged.
- ModelScope Meta qualification result (2026-08-12): the Course Owner approved exact Protocol
  `c1be800a5807d679d6b13ef41fe296f52cfac430cb59b851197e11da12eeaf8f` and one Dev-only run.
  The run used the already approved 160-case dataset, made zero external calls, did not read Blind,
  and produced Report `6946176f48249f699f2d177ee651083bd47b9ab13b598ecdc857e2efd27d38b4`.
  All six preregistered threshold pairs failed. Best recall was `0.2125` at specificity `0.825`;
  the highest-specificity result was recall/specificity `0.20/0.8875`; tool-coercion recall was
  `0`. No Profile Candidate was emitted. This result rejects the candidate for the current broad
  five-family L0 contract and cannot be repaired by a second Dev run or expanded threshold grid.
  Blind remains unread and the default remains `legacy_rules`.

## P10-D011 — Replace the single broad Prompt Guard contract with a high-confidence multi-axis union

- Date: 2026-08-12
- Status: accepted_for_candidate_implementation; qualification and release remain pending.
- Problem: three P10.2 classifiers failed for complementary reasons. HikmaAI retained high
  specificity but missed Chinese/tool-coercion examples; Prompt Guard 2 recognized a narrow
  policy-override surface; ProtectAI had a broader domain mismatch. Repeating model swaps or
  lowering one global threshold would trade false negatives against false positives without
  satisfying the five-family L0 contract.
- Decision: keep HikmaAI as the required general semantic axis and add separate structured
  action + target + effect axes for role impersonation, secret extraction and tool coercion.
  Obfuscation is a modifier only. Use a high-confidence union rather than majority voting so one
  independently sufficient threat axis cannot be outvoted by unrelated benign axes.
- Challenger rule: retain ModelScope Llama Prompt Guard 2 as a policy-override axis only if the
  same single Qualification Dev scoring proves at least one unique true positive and zero added
  false positives. Otherwise emit a Profile without that axis; do not tune its threshold.
- Context rule: quoted attacks, safety teaching and policy descriptions do not become findings
  without operative action/target/effect evidence. Findings retain axis, signal, detector, span
  and decision-path identity.
- Failure rule: required detector/model/Profile/Hash/runtime failures stop the Stage; there is no
  fallback to P10.1 regex marking or a different model.
- Evaluation rule: construct a new owner-reviewed 120-case Qualification Dev and a separate
  empty 48-case Blind commitment. Do not reuse consumed P10.1/P10.2 Dev/Blind for selection.
  The real Dev and Blind each require separate exact-Hash approval and may run once only.
- Compatibility: no migration or public API behavior change. The default remains `legacy_rules`
  until both new gates pass; P10 and P11 remain blocked meanwhile.
- Review checkpoint: the static exporter failed after both owner review passes were completed.
  The Course Owner explicitly stated that all 120 records passed in both passes and directed the
  phase to proceed without exported browser JSON. Hash-bound review records `b6e5d2ce...` and
  `4817e358...` were therefore recovered from that human attestation, and Approval `dcef3ebe...`
  binds both records, exact Candidate `b3ef6753...` and all ordered IDs. This is owner approval,
  not system-generated label adjudication. Exporter repair is explicitly deferred this round.

## P10-D012 — Reject the P10.3 multi-axis Candidate after its single Qualification Dev run

- Date: 2026-08-12
- Status: rejected_by_preregistered_dev_gate.
- Authorization: the Course Owner approved exact Protocol
  `91f51be096ddfb0db5e37d68e4be5b11e308c45968287e00659233eb1acb3a4c` and one Dev-only run.
- Result: Report `26e5eb98bfe08536987cd8a6b36d769ce3e3370319f8479d57c15b1ba596f0bb`
  records TP=57, FN=3, FP=16 and TN=44: Recall `0.95`, Specificity `0.733333`.
- Ablation: removing the Llama policy-override axis retains Recall `0.95` and improves Specificity
  to `0.80`. Llama contributed zero unique true positives and four added false positives, so it is
  rejected by the preregistered `unique TP > 0 and added FP = 0` rule.
- Failure shape: three Chinese positives were missed (two policy override, one tool coercion).
  Twelve baseline false positives include ten repeated explicit-negation controls and two English
  legitimate credential-rotation descriptions. This exposes an insufficient scoped-negation/
  descriptive-context contract plus residual Chinese semantic coverage, not a threshold-only issue.
- Decision: emit no Profile, do not run or construct Blind, do not rerun the consumed Dev, do not
  patch the failed examples into the same release. Preserve Report and error analysis as evidence.
- Runtime: default remains `legacy_rules`; P10 and P11 remain blocked pending a separately approved
  next architecture/release plan.
- Architecture conclusion: three independent candidates now show different but complementary
  failures. ProtectAI has broad domain mismatch, HikmaAI is high-specificity but incomplete for
  Chinese/tool coercion, and Prompt Guard 2 concentrates on explicit prompt override rather than
  the full untrusted-instruction taxonomy. Any continuation must first separate the security
  taxonomy/decision axes or introduce an explicitly reviewed ensemble. It must not continue the
  model-swap/threshold loop on the consumed Dev release.

## P10-D013 — Isolate the rejected detector Profile and conditionally unblock P11

- Date: 2026-08-12
- Status: owner_approved_dependency_waiver_with_security_debt.
- Motivation: P10.3 tested one narrow component—the proposed local untrusted-instruction detector—
  rather than overall CourseRAG quality. Its strict Profile Gate correctly rejected an unsafe
  default, but treating that rejected, never-published candidate as an indefinite blocker for all
  Model Gateway and CoursePilot foundation work would couple unrelated development to repeated
  detector tuning.
- Cause analysis: the earlier status conflated three different facts: the P10.3 Profile did not
  satisfy Recall/Specificity; the candidate was never activated and caused no side effect; and the
  remaining P10 Port, persistence, incremental, citation, writeback, ACL and evaluation contracts
  had already completed their gates. Only the first fact failed.
- Decision: preserve P10.3 as `candidate_rejected_default_off`, emit no Profile, keep its Blind
  unread and prohibit same-Dev reruns, while recording P10 as
  `completed_with_isolated_security_capability_debt`. P11 receives an explicit dependency waiver
  and may start because it does not require this candidate to implement its Model Gateway,
  Capability, Trace, cost and compatibility contracts.
- Mandatory P11 boundary: retrieved/document Context remains untrusted data; Context cannot
  override system/developer instructions; tool calls are default-deny and require explicit
  capability/authorization; ACL, trusted gateway claims, Secret isolation and audit remain active;
  no code or report may describe P10.3 as a passed security boundary.
- P11 implementation note: the Pre-P11 compiler currently encodes the superseded `P10 fully green`
  predicate. The approved P11 plan must change only that dependency predicate to validate exact
  P10-D013 status and constraints; Candidate counts, deferred-record provenance, Test/Gold access
  restrictions and fail-closed identity checks remain unchanged.
- Downstream convergence: P14-P16 cannot use detector findings as authorization. P17 owns the next
  integration-level repair/replacement and new independent Dev/Blind release. P18 remains hard
  blocked from formal system freeze while this debt is unresolved.
- Result: development can proceed without lowering the P10.3 thresholds, rereading Blind, tuning
  the consumed Dev or changing runtime behavior. Original Test Lock, formal Reports, Active
  Indexes, database, API, Profiles and defaults remain unchanged.
- Supersession: this decision supersedes only the P10/P11 blocking conclusions in P10-D008 through
  P10-D012 and P11-D001. It does not supersede their evidence, failed detector verdicts, no-rerun
  rules, data locks or Profile release requirements.

## P11-D002 — Establish one versioned runtime foundation beside the legacy Graphs

- Status: accepted_and_implemented
- Date: 2026-08-13
- Motivation: rewriting all three business Graphs in P11 would combine contract, persistence and
  business-algorithm risk, while creating a second task table would split the source of truth.
- Decision: retain `GenerationTask` as the BusinessTask carrier, add stable Workflow Run, Template
  Snapshot, Artifact/Version, Node Run, Approval and Model Invocation facts, and mirror legacy
  successes through one reversible compatibility adapter. Stable threads use
  `coursepilot:{workflow_type}:{task_id}`. New runtime modules consume CourseRAG only through its
  public Port and never import Parser, Chunker, Index, persistence, Chroma or legacy chunks.
- Compatibility: no public CoursePilot path or response field is removed or renamed. Turning off
  `COURSEPILOT_RUNTIME_COMPATIBILITY_RECORDING` stops new mirroring without deleting audit facts or
  disabling legacy services.
- Result: task output is traceable to immutable Template, Prompt, Context, Model and Artifact
  identities while P14-P16 remain the owners of business Graph migration.

## P11-D003 — Route six logical model profiles through capability-aware Main/Light identities

- Status: accepted_and_implemented
- Date: 2026-08-13
- Decision: keep six independent logical profiles even when Main and Light currently resolve to the
  same physical `COMPATIBLE_*` configuration. Provider/model/endpoint remain configuration, Secret
  values remain environment-only, and unsupported reasoning/thinking fields are omitted rather
  than guessed. P11 exposes no tools. Escalation is explicit, profile-declared and caller-approved;
  evaluation and runtime faults fail closed instead of silently switching models.
- Result: the current deployment needs no additional model, while later Main/Light separation needs
  only configuration and preserves Profile/Invocation audit identity.

## P11-D004 — Freeze neutral template contracts while deferring production visual polish

- Status: accepted_with_visual_qa_debt
- Date: 2026-08-13
- Decision: register nine approved logical templates and pin two editable A4 DOCX plus three
  editable PPTX role resources by content Hash. The current environment validated file structure,
  styles, master/layout and editability, but could not complete independent render inspection due
  missing document-render dependencies and unavailable managed Artifact Tool execution.
- Boundary: P11 claims registry/snapshot reproducibility and resource validity, not final export
  aesthetics. P16 must render, inspect and refine all five resources before visual-quality freeze.

### P11 Runtime Foundation Snapshot approval result — 2026-08-13

The Course Owner approved exact Candidate SHA-256
`2d9b902a9dfa67a749e561b7c82ced0f82beebebcb324516306493c91aa87837`.
Approval scope is the P11 Runtime Foundation Snapshot only: it freezes the implemented Template,
Prompt, Capability, State, Artifact, migration, test and compatibility identities; it does not
promote CoursePilot formal Gold, approve P16 visual quality, activate the rejected P10.3 detector,
or authorize P12 implementation. P11 therefore becomes `completed / passed`, and P12 becomes
`ready_to_start` under its own Plan-and-approval checkpoint.
## P12 Implementation Choices (2026-08-14)

- **P12-D001 — 双模式渐进启用：** Legacy 入口保持自动完成；Recoverable Task API 显式启用
  PostgreSQL Checkpoint 和六类 Interrupt，后续 P14-P16 再评估默认切换。
- **P12-D002 — 可信审批身份：** 审批只接受网关注入的 Principal/Course/Role Header，Body
  `actor_id` 不具有授权能力；Course 和角色不匹配时 fail-closed。
- **P12-D003 — 七天软过期：** Interrupt 过期转 `needs_review`，不自动取消；Owner/System
  显式重开并生成新 Interrupt，旧记录保留审计。
