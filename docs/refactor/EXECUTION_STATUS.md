# Refactor Execution Status

- Frozen document set: v1.0
- Baseline commit: `eb9b3a6aa51348cf1fba0de7a21e5d073761939b`
- Current branch: `refactor/p00-baseline`
- Current phase: P18 execution and human review are complete. Its formal quality Gate remains failed and immutable: Track A has 4 generation failures, 8 frozen-contract failures and 4 missing exports; Track B lacks a restorable formal CourseRAG Test Index, leaving 7/8 live Journeys blocked; human Acceptable Rate is 29.17%, mean Rubric 2.8884 and mean Edit Burden 2.625. Safety side-effect counts remain zero. By Course Owner disposition this evidence may support a clearly labelled portfolio MVP, but it is not a production release and the Test results cannot feed back into this version. P19 is authorized for portfolio-scoped physical repository separation.
- Current data checkpoint: Business remains `4ce0ac60...a869`; Quality/Recovery r2 is `d724a1c4...a082` with 18 repaired CP-DS5 contracts; Integration/Export r2 is `5d42d442...6683` with eight repaired template/fault/Journey records. Fixed LibreOffice 7.4.7.2 rendered the custom DOCX twice with identical page PNG Hash `9265d1d0...2e79`.
- Last updated: 2026-08-25

| Phase | Status | Start Commit | End Commit | Gate | Report |
|---|---|---|---|---|---|
| P00 | completed | `eb9b3a6` | uncommitted (`eb9b3a6`) | passed | `phase_reports/P00_baseline_freeze_and_execution_scaffold.md` |
| P01 | completed | `21d2cc5` | uncommitted (`21d2cc5`) | passed | `phase_reports/P01_CourseRAG_Port_Report.md` |
| P02 | completed | `e3f4efa` | uncommitted (`e3f4efa`) | passed | `phase_reports/P02_evaluation_data_scaffold_and_b0_runner.md` |
| P03 | completed | `b6483f5` | uncommitted (`b6483f5`) | passed | `phase_reports/P03_persistence_versioned_build_pipeline.md` |
| P04 | completed | `b6483f5` | uncommitted (`b6483f5`) | passed | `phase_reports/P04_structured_parsing_docx_pagination.md` |
| P05 | completed | `b6483f5` | uncommitted (`b6483f5`) | passed | `phase_reports/P05_ocr_routing_and_mixed_page_merge.md` |
| P06 | completed | `b6483f5` | uncommitted (`b6483f5`) | passed | `phase_reports/P06_stable_evidence_and_parent_child_chunk.md` |
| P07 | completed | `b6483f5` | uncommitted (`b6483f5`) | passed | `phase_reports/P07_course_level_knowledge_point_assets.md` |
| P08 | completed | `b6483f5` | uncommitted (`b6483f5`) | passed | `phase_reports/P08_hybrid_retrieval_rrf_reranker.md` |
| P09 | completed_with_quality_debt | `b6483f5` | uncommitted (`b6483f5`) | passed_core_contracts_profile_not_frozen | `phase_reports/P09_generation_reliability_gate_repair.md` |
| P10 | completed_with_isolated_security_capability_debt | `b6483f5` | `3665211` + uncommitted P10.1-P10.3 repair | core_contracts_passed_security_profile_rejected_default_off | `phase_reports/P10_3_multi_axis_untrusted_instruction_detector.md` |
| P11 | completed | `2e1a6be` | uncommitted (`2e1a6be`) | passed | `phase_reports/P11_coursepilot_runtime_template_model_gateway.md` |
| P12 | completed | `2e1a6be` | uncommitted | passed | `phase_reports/P12_postgresql_checkpoint_interrupt_approval.md` |
| P13 | completed | `b2cc47b` | uncommitted | passed | `phase_reports/P13_validation_targeted_repair.md` |
| P14 | completed_with_quality_debt | `b2cc47b` | uncommitted | passed_core_contracts_human_quality_debt_recorded | `phase_reports/P14_lesson_workflow_closure.md` |

## P12 implementation checkpoint

P12 runtime foundations are implemented with the approved choices: dual-mode rollout (Legacy
defaults unchanged, Recoverable opt-in), trusted gateway Principal identity, and seven-day soft
expiry. Alembic head is `0017_coursepilot_checkpoint_interrupts`. The Recoverable skeleton uses
stable `coursepilot:{workflow_type}:{task_id}` threads, PostgreSQL Checkpointer factories,
Interrupt/Decision/Resume/SideEffect facts, immutable edit versions, and separate export/writeback
approval scopes. The isolated Compose PostgreSQL integration and CP-DS6 runtime runner are now
complete; the default Recoverable runtime remains disabled.

P12 validation update: the full suite is green; Ruff Format/Check and
Mypy (`403` source files) pass; the migration head remains `0017_coursepilot_checkpoint_interrupts`.
The B0 compatibility projection accepts additive P12 schemas/routes while preserving all legacy
route/model snapshots. Real PostgreSQL `0016→0017→0016→0017`, restart/Resume, and runtime CP-DS6
execution pass in the isolated Compose database: migration round-trip `0016 -> 0017 -> 0016 ->
0017`, six restart/Resume/Interrupt cases, and 24 CP-DS6 structural cases with external_calls=0
and gold_promotion=false. The default Recoverable runtime remains disabled.
| P15 | completed_with_quality_debt | `b2cc47b` | uncommitted | passed_core_workflow_contracts_exam_profile_provisional | `phase_reports/P15_exam_blueprint_fanout_global_repair.md` |
| P16 | input_approved_ready_to_start | uncommitted | — | implementation_and_eval_not_run | `phase_reports/ED_PRE_P16_CPDS37_candidate_review_r2.md` |
| P16 | ready_to_start | | | P10-P14/P11-P13 passed or explicitly closed | |

## P15 CP-B0/P15 owner-review package

The approved fixed-Blueprint CP-B0 question-generation baseline is complete for all three CP-DS2
cases (45 questions). Cumulative usage, including the superseded legacy attempt, is 30 requests,
116,622 input tokens, 123,228 output tokens and CNY 0.363078, within the approved 30/130k/150k/CNY
0.45 limits. The blinded package contains six exams and 90 question decisions at
`storage_eval/p15_owner_review/`; package SHA-256 is
`44fcecfa343730253c2d535340e28b68604aa3a257721e540e85735c62c11254`. P15 remains
`gate_failed`: owner decisions are complete and identified three critical P15 question defects.

## P15 Targeted Repair Closure checkpoint

The bounded closure now models true multi-select answers, per-option correctness/evidence,
self-contained stimulus material, answer-set consistency and semantic duplicates. Its preflight
freezes exactly 17 question IDs across the three Approved P3 artifacts and leaves the other 28
question hashes untouched. The repair runner no longer redirects a failed duplicate repair to the
other side of the pair; it repairs each preflight ID at most once and then revalidates the complete
exam. A delta-only owner-review package is generated after a successful run and includes local
autosave plus independent progress/final JSON downloads.

The network-free preflight passed with 17/20 targets and an estimated 59,500 input / 85,000 output
tokens. The first managed attempt produced only `connection_error` records and zero model output;
the original 45 questions remained unchanged. A clean non-sandbox retry was then rejected by the
Codex managed-runtime usage limit before an output directory or response checkpoint was created.
This is an execution-environment blocker, not a successful quality revalidation. Local evidence is
green: full Pytest `722 passed, 12 skipped`, Ruff Format/Check, Mypy (447 source files), Alembic
single head and `git diff --check` pass. P15 stays failed and P16 remains blocked until the exact
real targeted run succeeds and the Course Owner approves its incremental review decisions.
| P16 | completed_with_quality_debt | uncommitted | — | passed_core_contracts_provider_consistency_rendering_quality_debt_recorded | `phase_reports/P16_ppt_architecture_template_rendering.md` |
| P17 | completed_with_isolated_security_automation_debt | `b2cc47b` | `3f5c415` + uncommitted P17.1-P17.3 | passed_system_integration_hard_controls_detector_rejected_default_off | `phase_reports/P17_3_tri_state_security_convergence.md` |
| P18 | completed | `3f5c415` | uncommitted | formal_quality_gate_failed_owner_portfolio_disposition | `phase_reports/P18_coursepilot_system_formal_evaluation.md` |
| P19 | in_progress | uncommitted | | portfolio_release_gate_pending | `phase_reports/P19_repository_split_ci_portfolio.md` |

## P16 Critical-only closure checkpoint

The first Course Owner review covered all 46 final slides and identified 17 `critical_defect`
pages. Under the approved one-shot boundary, the repair preflight bound the exact 17 IDs to the
source report and decision file, allowed at most one repair per page and preserved all other page
hashes. Execution completed one repair round with 9 physical Provider requests, 19,971 input
tokens, 53,342 output/Thinking tokens and estimated CNY 0.266655, within the approved
CNY 0.45 / 20 request / 130k input / 60k output limits. Eight pages used successful Provider
checkpoints; after one structured-output recovery and one timeout, the remaining nine were closed
deterministically from the approved Evidence and owner notes without another external call.

The repaired 24/12/10-page decks all reopen and render in the fixed LibreOffice/Poppler container;
automatic severe overflow, out-of-bounds and empty-slide counts are zero, CP-DS7 remains green,
and the 29 noncritical slide hashes are unchanged. The focused 17-page package is at
`storage_eval/p16_critical_repair_closure/review/index.html`. P16 remains blocked only on this
owner re-review. This is the final repair round: remaining noncritical preferences may become
quality debt, while a remaining hard defect must be reported rather than triggering another repair.

## P15 Closure Repair checkpoint

The approved no-API repair completed the runner and evidence boundary: P0/P1/P2/P3 now use
bounded evidence text, durable atomic response checkpoints, explicit experiment variants,
bounded batch size/concurrency and stable fan-in numbering. The Exam graph is fail-closed until
Blueprint Review approval. Export is staged, reopened and locally rendered before publication;
writeback binds an exact approval record and target path, and stale task/artifact versions are
rejected from the database-backed side-effect boundary.

Evidence: focused P15/offline tests `16 passed`, PostgreSQL migration/interrupt/side-effect gate
`6 passed`, Ruff and targeted Mypy passed, and all four local DOCX roles rendered to one-page
PDF/PNG outputs with no placeholders or answer leakage in Student Exam. No external Provider
call was made in this repair. P15 real Smoke and full Pilot remain pending the user's separate
fee authorization; P16 remains blocked until that decision and the P15 Gate are complete.

## P15 Targeted Repair Provider completion

The authorized second-round repair completed successfully for exactly the two residual targets:
case02 `batch-multiple_choice-01:slot-1` and case03 `batch-short_answer-01:slot-5`. The final
report is `storage_eval/p15_targeted_repair_network/report_final.json`; all three CP-DS2 cases
have `all_global_validation_passed=true`, with unchanged non-target question hashes preserved.
Cumulative repair-run accounting is 19 Provider requests, 69,606 input tokens, 80,286 output
tokens and estimated CNY 0.230178, within the approved hard caps. No additional retry, fallback,
or model switch was used. The final 17-question delta review is at
`storage_eval/p15_targeted_repair_network/review_final/review.html`, with the editable decision
template beside it. At that checkpoint P15 was `gate_pending_owner_review` and P16 was blocked by
the owner review only. This checkpoint is superseded by the completed owner-review closure below.

## P15 owner-review closure and P15.1 backlog

The Course Owner completed the final 17-question delta review. Decision file SHA-256 is
`d83ad908cf18c0317cf05ab7e461f987553ff74bc1b009ecba9a375223012aae`, bound to source report
`d95d79e787e7d5e5b0173691715bc0f16548bf929a9975e52c54c200da20c7d0`. Results are 6 `pass`,
2 `minor_edit` and 9 `major_edit`. The remaining issues are dominated by whole-exam semantic
repetition, repeated assessment targets and cross-question answer clues. They cannot be reliably
closed by another question-local repair because the approved repair scope intentionally cannot
reassign Slot KP, Evidence or Assessment Target.

Per Course Owner decision, P15 closes as `completed_with_quality_debt`; the Exam V2 Profile is
`provisional_dev_only`, remains default-off (`COURSEPILOT_EXAM_V2_ENABLED=false`), and no further
question-local Provider repair is scheduled. P15.1 records a bounded architecture improvement:
unique primary assessment-target allocation per Slot, an exam-wide used-fact/exclusion plan,
cross-question semantic/clue graph validation, and Blueprint/Batch-level regeneration when those
constraints fail. P16 may start because it is a sibling workflow; P15.1 must be resolved or
explicitly dispositioned before P17/P18 promotes the Exam Profile.

## Pre-P15 CP-DS2 Exam Pilot Candidate checkpoint

P15 input construction `ED-PRE15-CPDS2-T01` through `T08` produced three blueprint-only
Exam Pilot cases, 26 Assessment Targets, three fixed Context fixtures, and two fail-closed
contract negatives. Candidate Bundle SHA-256 is
`943dd46f873393ea139466b47f87854685ac23c69073a7194bc8490822480534`.
The Candidate was approved exactly by the Course Owner; CoursePilot Dev/Test are empty and `test.lock=false`.
Review pages and manual JSON fallbacks are under
`storage_eval/cpds2_p15_review/943dd46f873393ea139466b47f87854685ac23c69073a7194bc8490822480534/`.
No fixed question wording, real Provider call, P15 runtime output, P18 Gold, or database/API
change was used. The global manifest records P14 as `completed_gate_passed` with its existing
quality debt and P15 as `formal_eval_ready`.

Approved input is `datasets/coursepilot_eval/v1/approved/cp_ds2/p15_exam_pilot.json` with
SHA-256 `8204f687b5a03965d7d02b8c1884419f3675c3a4af6a0e3364df0218f03a0ac4`.
Approval provenance is `datasets/coursepilot_eval/v1/provenance/p15_cp_ds2_bundle_approval.json`;
the two review records are marked `conversation_exact_bundle_approval` because no exported JSON
was supplied. This approval prepares P15 input only and does not claim the P15 Exit Gate or P18
formal CP-DS2 Gold.

## P11 Runtime Foundation implementation checkpoint

P11-T01 through P11-T08 are implemented and verified without external Provider calls. Runtime,
Template, Model Gateway, migration and legacy compatibility identities are frozen in Candidate
`datasets/coursepilot_eval/v1/candidates/work_packages/p11_runtime_foundation_snapshot_r1.json`,
SHA-256 `2d9b902a9dfa67a749e561b7c82ced0f82beebebcb324516306493c91aa87837`.
The Course Owner approved this exact identity on 2026-08-13. Approval provenance is preserved in
`datasets/coursepilot_eval/v1/provenance/p11_runtime_foundation_snapshot_approval.json`. P11 is now
`completed / passed` and P12 is `ready_to_start`; P12 was not started by this approval update. The
rejected P10.3 detector remains default-off and is not represented as a passed security boundary.

## P12 CP-DS6 Pilot input checkpoint (legacy note)

Candidate `datasets/coursepilot_eval/v1/candidates/cp_ds6/p12_interrupt_recovery_r1.json`
contains 24 deterministic, course-agnostic structural cases (six Interrupt types × four
scenarios), SHA-256 `e0b854c2fe261571b6319447e9e0feabd732e67a1b509e121ddb18b3ae1701a1`.
The offline review page is under
`storage_eval/cp_ds6_p12_review/e0b854c2fe261571b6319447e9e0feabd732e67a1b509e121ddb18e9e0feabd732e67a1b509e121ddb18b3ae1701a1/index.html`.
The legacy one-case CP-DS6 Pilot remains unchanged for Schema regression. No Approved P12 file,
CoursePilot Dev/Test IDs, Test lock, database migration or runtime evaluation was changed.

## P12 Candidate review status

The P12 CP-DS6 Pilot Candidate is `datasets/coursepilot_eval/v1/candidates/cp_ds6/p12_interrupt_recovery_r1.json`,
SHA-256 `e0b854c2fe261571b6319447e9e0feabd732e67a1b509e121ddb18b3ae1701a1`, with 24 structural
records. Review entry: `storage_eval/cp_ds6_p12_review/e0b854c2fe261571b6319447e9e0feabd732e67a1b509e121ddb18b3ae1701a1/index.html`.
The exact Candidate was approved as P12 implementation input. Approved package SHA-256 is
`1def8ba6bdb774bc744e4bac2cc70793867c96cc2d8a0929efbe62d32cc4f078`; approval SHA-256 is
`a0e4e6490e8d5d53a7337946169e95d68050368fc44eb7ec29659946c356be61`. This does not promote
formal CoursePilot Gold, populate Dev/Test, lock Test, or claim a P12 Exit Gate.

## Pre-P13 CP-DS4/5 Pilot Candidate checkpoint

P13 Candidate generation produced 30 CP-DS4 Validation Fault records and 15 CP-DS5 Targeted
Repair records, with 9 valid base Artifact fixtures and 30 deterministic fault variants. The
hybrid provenance uses only Approved DS2/DS3 records from the two existing courses for grounding
references; structural faults remain deterministic and course-agnostic. Bundle SHA-256 is
`b436f6e1901bb9447359e4fd0524f27ba39bfa24742b3ec006e451ae0bec9cd0`.
Review pages are under
`storage_eval/cpds45_p13_review/b436f6e1901bb9447359e4fd0524f27ba39bfa24742b3ec006e451ae0bec9cd0/`.
The review UI now defaults to human-readable artifact summaries, before/after fault values and
expected Issue or Repair constraints; raw JSON is collapsed. Filters, progress and local decision
persistence were added without changing the Candidate files or Bundle SHA-256.
No P13 output, external Provider, CourseRAG Test/Holdout, Dev/Test split or formal CP-DS1—3 Gold
was used. The Course Owner approved the exact Bundle after 45/45 first-pass and 27/27 second-pass
reviews. Approval SHA-256 is `41ca5385a95870d251776957a6469622c834032fa0f019699f0db505eed5985c`;
P13 implementation may start, while the P18 final CoursePilot Gold freeze remains unchanged.

## Pre-P14 CP-DS1 Pilot approval checkpoint

The Course Owner approved exact Bundle SHA-256
`3e47c85c624ab0c3a751b34de38a8b1147a0d6187314ef9a27210b85cc9c1708`.
Because the original review pages had no working export channel, the two completed all-pass reviews
are preserved as conversation-attested decision files rather than requiring repeated review.
Approved Pilot SHA-256 is `4533545ca0355e6c9a1581dd7024fc008b7e7f95e71e9c73b35dc52f88340e13`;
approval SHA-256 is `f76cb89e5a0cf9c2f8ee9f06ae42a25e9e7dda3e41e3567dc24ccbad34558533`.
The review pages now autosave decisions locally and export schema-validated JSON. P14 input is
`formal_eval_ready`; this approval does not run a Provider, pass the P14 Exit Gate, populate
CoursePilot Dev/Test, lock Test, or promote the P18 final CP-DS1 Gold.

## Current data-preparation tasks

| Task | Status | Evidence |
|---|---|---|
| ED-PRE03-T01 | completed | DS0/DS1/DS2/DS5 Schema gaps filled; 27 JSON Schemas exported |
| ED-PRE03-T02 | completed | two Primary and four deterministic derived fixtures recorded under one variant group per course |
| ED-PRE03-T03 | completed | six DS0 records are candidate-only; Dev/Test and unlocked Test state unchanged |
| ED-PRE03-T04 | completed | DS1 Pilot sampling plan frozen without guessing DOCX page numbers or authoring Gold |
| ED-PRE03-T05 | completed | repeat build Hashes match; 42 PDF pages, 4,334 DOCX source-unit mappings and 128-page canonical visual QA verified |
| ED-PRE03-T06 | completed | six revised Candidate records Hash-bound to Approved DS0, ApprovalRecords and append-only review entries |
| ED-PRE04-T01 | completed_candidate | isolated `coursepilot_eval_p04` PostgreSQL is at `0009_courserag_content`; loopback port fixed at 55432 |
| ED-PRE04-T02 | completed_candidate | deterministic P03 identities persist 2 KBs, 6 documents/versions, 6 single-document inventory Builds and 6 CAS Artifacts |
| ED-PRE04-T03 | completed_candidate | non-Gold P04 work-package Candidate contains 15 native PDF pages, 10 DOCX anchors, 20 Sections, 10 tables and 15 OCR routes |
| ED-PRE04-T04 | completed | exact Candidate file Hash approved by `course_owner`; Approved package, ApprovalRecord and append-only review entry created idempotently |
| ED-PRE04-T05 | completed | source/Hash/idempotency/visual QA, 29-Schema export, 279-test regression, Ruff and Mypy pass; post-approval report emitted |
| ED-P04-DS1-T01 | completed | formal Page/DOCX pagination/Table geometry, rendered table-fragment, source-Hash, review-decision, candidate-Manifest, batch-approval and revision-history contracts exported as 33 JSON Schemas |
| ED-P04-DS1-T02 | completed_candidate | source-grounded r6 contains Page 15 / DOCX Pagination 10 / Section 20 / Table 10 / OCR 0; only returned `ds1-table-docx-020` differs from r4 and no P04 Parser prediction is used as a label |
| ED-P04-DS1-T03 | completed | owner review and exact r6 approval cover all 55 records, including the corrected rendered-visible 7x4 `ds1-table-docx-020` |
| ED-P04-DS1-T04 | completed | exact Candidate Hash was promoted to a physically separate Approved file with 55 ApprovalRecords, one batch approval and append-only review entries; replay returned identical Hashes |
| ED-P04-DS1-T05 | completed_gate_passed | formal P04/B0 Runner used Approved DS1 only; exact OOXML source-unit resolution corrected the evaluation binding, two runs reproduced 10/10 DOCX mappings and every strict Gate check passed |
| P05-T01 | completed | configurable native/ocr/hybrid routing, exact Profile Hash and route reasons; 30-page approved-label check reports precision/recall/F1 1.0 |
| P05-T02 | completed_implementation | shared OCR Provider contract and fail-closed RapidOCR, Tesseract and PaddleOCR adapters; no automatic fallback |
| P05-T03 | completed | deterministic OCR result identity, coordinates, confidence, warnings, resource metrics, Artifact extension and reversible 0010 migration |
| P05-T04 | completed | deterministic pixel-to-page conversion, native-priority overlap/text deduplication and provenance-preserving mixed-page merge |
| P05-T05 | completed | 20MP and 1.5-GiB guards plus a configurable timeout; default_v1 uses the explicitly approved 90 seconds, and all limit/empty/low-confidence outcomes remain visible as warnings |
| P05-T06 | completed | exact r3 was approved idempotently; two runs each of RapidOCR, Tesseract and PaddleOCR used the same 15 Approved PNGs, fixed resources, immutable model/image identities and no runtime network |
| P05-T07 | completed_gate_passed | owner selected RapidOCR; checked `default_v1` SHA `ca962f3b...` fixes 90 seconds and two runs reproduce all 15 semantic results with no warning/resource-limit page |
| ED-PRE06-DS2-T01 | completed | formal Evidence/BBox/source-unit/OCR-provenance, Candidate Manifest, review-decision and batch-approval contracts exported in the 38-Schema set; legacy P02 DS2 remains valid |
| ED-PRE06-DS2-T02 | completed_candidate_r7 | r7 contains DOCX 80 / PDF 40, 16/8 Sections × 5 and PDF native 30 / OCR-derived 10; all 120 records have a minimal necessary-neighbor audit |
| ED-PRE06-DS2-T03 | completed_r5_review | all four r5 groups were returned with complete decisions: 98 passed and 22 returned; exact feedback Hashes and notes are preserved in `ds2_p06_review_decisions_r5.json` |
| ED-PRE06-DS2-T04 | completed | repeated r7 generation reproduces Candidate `ebc980a4...`, neighbor audit `74b200a8...` and Manifest `3c33cafa...`; Gold content, stable IDs and source bindings remain unchanged from r6 |
| ED-PRE06-DS2-T05 | completed | source/upstream/geometry/distribution/leakage/approval-boundary checks, 29 focused tests, 352-test full suite, 38-Schema export, Ruff and full Mypy pass; no B1/B2 run was performed |
| ED-PRE06-DS2-T06 | completed_approved | exact r7 SHA-256 approval created 120 Approved Evidence records, 120 ApprovalRecords, one batch approval and 120 append-only review entries; replay was idempotent and P06 input is ready |
| P06-T01 | completed | Stable `ev1_*` Evidence identity, PageBBox, exact content/source-unit Hashes and explicit OCR provenance |
| P06-T02 | completed | Deterministic semantic-unit Builder covers headings/paragraphs/lists/steps/tables/examples/formulas, filters P05 non-body roles and preserves adjacency |
| P06-T03 | completed | Course-scoped single/batch Resolver and Source Preview validate persisted Hashes and resolve previous/next source context |
| P06-T04 | completed | Versioned Chunk Profile, ChunkSet, one-Parent-per-Child model and exact ChunkEvidence coverage links persisted by additive 0011 |
| P06-T05 | completed | Section/Evidence/sentence/token-limit splitting uses the exact checked local tokenizer and visible atomic-unit warnings |
| P06-T06 | completed | Evidence deduplication, adjacency, overlap, long-unit handling, OCR provenance and coarse DOCX page-location warnings are tested |
| P06-T07 | completed_skeleton | Citation migration interface validates stable same-version Evidence and explicitly defers legacy/cross-version repair to P10 |
| P06-T08 | completed_gate_passed | two Approved-DS2-only B1/B2 runs reproduce byte-identical system output; all non-generic P06 metrics have code and unit tests |

P00, P01 and P02 remain complete and unchanged. The Pre-P03 implementation has reached its
mandatory human checkpoint: the repository retains six revised Candidate DS0 records representing
only two independent semantic sources, plus six exact Approved DS0 records, six ApprovalRecords,
and six append-only review entries approved by `course_owner`. The clean scan uses physical source
pages `21, 23, 24, 26, 30`; the superseded unapproved batch remains in candidate revision history.
No DS1–DS8 Gold was authored, Dev/Test remain empty, and Test remains unlocked. The exact full gate
reports 259 passed and 5 explicit gated skips; Ruff, full Mypy, 27-Schema export, post-approval
dataset validation, repeat-build Hash comparison, PDF page/text-layer checks, and DOCX source
mapping pass. An isolated LibreOffice/Poppler/pdf2image QA profile rendered and visually verified
all 128 structure-stress pages after correcting a two-column table overflow. Formal DOCX
pagination remains deferred to P04 because LibreOffice PDF `CreationDate` metadata is not
deterministic and the formal Renderer policy is not frozen. The Pre-P03 data Exit Gate now passes,
so P03 was ready to start before the implementation recorded below.

## P03 completion summary

P03 established 32 additive `courserag_*` fact tables under separate CourseRAG metadata, two
self-contained reversible Alembic revisions, Repository/UoW persistence access,
content-addressed atomic artifacts, deterministic Stage fingerprints and cache verification, the
explicit legacy Document/GenerationTask compatibility bridge, dense/sparse Manifest contracts,
transactional Active Index publication, and dry-run-first cleanup audit. Gate Repair removed the
cross-course Stage-cache collision, the single-Stage-per-job constraint, live-ORM migration
dependency, permissive Manifest/shard publication, unsafe raw error persistence and cleanup blind
spots for DB-less or released-staging artifacts. The public B0 build/search path was not switched
and no Chroma collection or legacy table was migrated or deleted. A dedicated real PostgreSQL run
passed `0007 -> 0009(head) -> 0007 -> 0009(head)` and confirmed the Stage attempt composite
constraint; P03 focused tests report 17 passed, the owner PDF/DOCX B0 Smoke reports 1 passed, the
full suite reports 276 passed and 5 explicit gated skips, and Ruff/Mypy pass. P03 Exit Gate passes
and P04 now has its upstream prerequisite, but P04 has not been started.

## Pre-P04 input-candidate checkpoint

The isolated evaluation database uses Compose project `coursepilot_eval_p04`, database
`coursepilot_eval`, and loopback-only `127.0.0.1:55432`. It is migrated to
`0009_courserag_content` and contains 2 KnowledgeBases, 6 SourceDocuments, 6 DocumentVersions,
6 single-document BuildJobs, 6 Build-to-version links, 6 successful inventory Stage runs and 6
content-addressed Artifacts. Repeated Seeder runs preserved every count and returned the same
identity snapshot SHA-256 `ed489003274a7e136ffe39b900e8d2a07f428a1e79176605c4d6bcc2f6765609`.

The retained P04 input Candidate has file SHA-256
`b305f328a8e76555e661e048f34c7ea7c89ed82c9fb9982f4877e1b6a80df582`. `course_owner`
explicitly approved that exact file under review `review-pre-p04-input-20260729-01`; the physically
separate Approved package has file SHA-256
`06700604f3c69724090ee6a995c2696b41278f5bf45d64e90beeddba4a484e5c`. Approval replay is
idempotent. `gold_status` remains `ds0_pilot_approved`, DS1 Gold is empty, Dev/Test are empty and
Test is unlocked. The database container is stopped while its isolated named volume is retained.
The P04 input gate passes and P04 may enter its own audit/implementation flow. See
`phase_reports/ED_PRE_P04_DS1_input_candidate.md`.

## P04 implementation and human-Gold checkpoint

P04 added the canonical structured document IR, native PDF and DOCX parsers, a fixed
LibreOffice renderer profile and font lock, deterministic canonical rendered-PDF and page
Manifest Hashes, conservative DOCX-to-rendered-page alignment, Section/noise/table structure,
parse previews and quality reports, P03 Stage/Artifact materialization, and non-Gold parsing
metrics. No OCR body text, final Chunk/KP, public API cutover, legacy Chroma replacement, or new
database migration was introduced.

The hash-bound Pilot run `p04-pilot-v1-final3` completed and resumed without recomputation. Its
Manifest SHA-256 is `e92a1b6e239defb43f0d284d8f3cdf75ca4df7f90a366ced23c6ebb339428a88` and its Report SHA-256 is
`8a7a9a7704c059a8446267da6bc167d2d162139ec1b63d4187c36b5e7a86bdbd`. The Native PDF produced
structured span/BBox/table diagnostics; all five clean-scan pages were routed to `ocr_pending`
without OCR text. Two fixed-profile renders of each DOCX produced identical canonical PDF/page
Manifest Hashes even though raw PDF metadata differed. All five selected anchors in each DOCX
were resolved and page-assigned with minimum confidence `1.0`.

The primary DOCX render also reported 18 requested-font substitutions, 636 physical pages, no
visible display-page labels, 93.20% overall page-assignment coverage and 231 unresolved/low-
confidence Blocks. That 636-page candidate conflicts with the historical file-property value
183. P04-D003 now fixes LibreOffice Headless 7.4.7.2 as the warned formal renderer baseline and
rejects 183 as a page-count source, but the selected labels remain unapproved Candidate data.

## Formal P04 DS1 Candidate checkpoint

The current immutable Candidate is
`datasets/courserag_eval/v1/candidates/ds1/p04_native_docx_r6.json`, SHA-256
`7179ce9a48be77118ad68bfa7376bbe69e030f0e69ad0faba8435b0e0ee3c3aa`. It contains exactly 55
records: 15 native PDF Page, 10 DOCX Pagination, 20 Section and 10 Table records; OCR count is
zero. Every record is `candidate` with null approval. Source labels come from independent Poppler
geometry/PDF objects, raw OOXML and fixed rendered snapshots, not P04 Parser output. The two
semantic-source limit and variant exclusion remain explicit.

The primary/stress canonical PDF Hashes are respectively
`4642e5c653b265b71bdbf9878218ca058188a9420b8b5930317cf4442c09fb95` and
`68c178e0ecb7ef615564bbef92c068037dba20ca600e418e53300b5a92cf570c`; two identical-input runs
reproduced Candidate, Manifest and offline HTML Hashes. Word 2021 Find confirmed all five primary
anchors are present, but full Word PDF export was unavailable; no Word page value is used as Gold.
The submitted r3 review artifact binds SHA-256
`abbaf5114408990783dd209c3189e5ecfa4332a00aaab8b0e02ec892bdce1ac3` and records 54 reviewed
IDs, leaving only `ds1-table-docx-020`. r4 added page fragments but incorrectly retained the
6x4 OOXML source structure as final Gold. The owner then clarified that the combined visible
table is 7x4. r6 therefore uses seven visible rows for TableGold and retains the 6x4 OOXML grid
in the Manifest/review evidence. It preserves the record Hash of every reviewed r3 record and
changes only table 020 relative to r4. The intermediate r5 was superseded before review because
its table-level provenance defaults would have changed other TableGold digests. The updated
offline pack contains 55 cards and 27 local
source images; the 54 retained records are pre-checked and only table 020 requires re-review.
r1/r2/r3/r4 remain Hash-verified superseded revisions and are excluded from active
inventory only by the explicit revision-history contract.

Two r6 generation replays reproduced Candidate SHA-256
`7179ce9a48be77118ad68bfa7376bbe69e030f0e69ad0faba8435b0e0ee3c3aa`, Manifest SHA-256
`d5f8af9fa74667ada63c3d98acbdb20360207b0488b3ac711fb6914d245c198b` and HTML SHA-256
`091af6bfc60dacfca75646a2f808424b1441ad4d3d3de9d167d86f0e24a68c91`.
The r6 focused suite reports 28 passed; the full suite reports 308 passed and 5 gated skips;
Ruff format/check, Mypy over 202 source files and the 33-Schema export check pass.

The `course_owner` explicitly approved exact Candidate SHA-256
`7179ce9a48be77118ad68bfa7376bbe69e030f0e69ad0faba8435b0e0ee3c3aa`. The physically separate
Approved file SHA-256 is
`7e12edb2b66912d915b1d1ca3b7df873edb910cb7dcaf57d07872c83d84964ea`; its batch approval SHA-256
is `e9fdc5fc6d72bf2626e98bab16435f361d8fbef4ef547d0b8fe4f128a7d285b0`. Replaying the approval
command produced the same Hashes and no duplicate review records. The Manifest now records
`gold_status=ds1_p04_native_docx_approved` and `phase_input_status.p04=formal_eval_ready`; Dev/Test
remain empty and Test remains unlocked.

## Formal P04/B0 evaluation result

The original report
`storage_eval/p04_formal_ds1_r6_verified/report.json` is retained as audit evidence but is not an
authoritative Gate result. Its 9/10 result came from an evaluation-adapter defect: the Runner used
the parent `paragraph_index` as the structure-stress fixture's actual paragraph ordinal, even
though inserted Section-break paragraphs shift later ordinals. The product aligner had already
assigned the bookmarked target.

The corrected Runner resolves every Approved `source_unit_id` directly against OOXML, maps
bookmarks to the top-level paragraph ordinal used by `StructuredDOCXParser`, verifies both the
source-reference and parser-block Hashes, and has no text-search fallback. Approved DS1, its batch
approval and all source binaries remain byte-identical.

Two independent corrected runs are authoritative:

- run 1: `storage_eval/p04_formal_ds1_r6_source_unit_fix_run1/report.json`, report SHA-256
  `a14bd1767a1970507402c270b865e29ecb089abe79f8eaa7a2f8e4d6e9240578`, Run Manifest SHA-256
  `7e2ab22c584e76d3ff84790ad5474911ac2536971ecbdcdd5dbb008b0fd2f0ad`;
- run 2: `storage_eval/p04_formal_ds1_r6_source_unit_fix_run2/report.json`, report SHA-256
  `2f05a8b11246c0670e7c50de0fdb06e94fc24ac30b2d0a3b640356dc05d4e925`, Run Manifest SHA-256
  `aed1629a3e1ca5369d642f21ad4192de3f0fb09ce4cff70c47c3198342cb59dd`.

Both runs produce identical P04/B0 metrics, 10-record pagination diagnostics and strict-Gate
decisions. P04 parses 3/3 inputs, maps PDF pages 15/15, maps DOCX physical pages 10/10, maps all
observable display and Section pages 5/5, and recalls 780/783 normalized samples (99.62%).
Heading F1 is 1.0, Section-boundary accuracy 0.15, noise F1 0.5714, table-cell F1 0.9335 and table
structure 9/10. All four named structure metrics are strictly above B0, no common metric regresses
by over two points, and both renderer identities repeat. P04 Exit Gate passes.

## P05 OCR approval and engine-selection checkpoint

P05 now provides the configurable page classifier, common Provider contract, three isolated
candidate adapters, bounded subprocess execution, deterministic OCR result Artifact, mixed-page
merge, Stage resume/cache behavior and additive `0010` persistence contract. The public API,
CoursePilot Graphs, B0 Chroma path and Active Index remain unchanged. The default Provider is
still `disabled`, and checked-in candidate model Manifests are deliberately unresolved until an
evaluation image creates and verifies exact model-file Hashes.

The owner returned r1 because headers/page numbers, QR-adjacent material, embedded-image text and
figure/text ordering could contaminate the body projection, then returned r2 because seven split
captions classified only the figure number as a caption. Both revisions remain immutable and are
marked `superseded`. Source-grounded r3 contains 15 OCR records at 200 DPI, reuses 11 exact
Approved P04 PageGold annotations and creates only four missing source-page annotations. Its
Candidate SHA-256 is `c203f05d2cccc5cd5fcf557a7a5eed19d86c4ecae181cd14d88a863792baa065`;
the Candidate Manifest SHA-256 is
`9aa1a9f0229d10455680ec9f5724b933298671b5b9f6fa8e1c747630bb680e56`.

The `course_owner` explicitly approved that exact r3 Hash. The physically separate Approved file
SHA-256 is `62824129f3525a90bcbdd3d4570d9aa6a3768c0db6949c3c2ceafa7e7ce53c51` and the batch
ApprovalRecord SHA-256 is `f81b2e71d97e75eb22e40a6f8e14790e2d72877db3b0f7d326c905c0b7669af0`.
Approval replay returned identical Hashes and no duplicate review entry. Approved raw text retains
every region, while body CER excludes headers, footers, page numbers, QR material, figures,
embedded-image text and complete figure captions. Gold is independent of all OCR outputs.

The approved P04 routing labels provide 15 OCR positives and 15 native negatives. The fixed
classifier reports precision/recall/F1 1.0. Two isolated runs per engine used the same 15 Approved
PNGs, 200 DPI, 1 CPU, one Worker, 60 seconds/page, 1.5 GiB RSS and runtime networking disabled:

- RapidOCR is the only quality-capable candidate. Run 1/2 body macro CER is 0.0761/0.00977,
  Region Recall@0.5 is 0.6872/0.7793, p50 is 54.8/50.5 seconds and peak RSS is about 704 MiB.
  `ds1-ocr-04` timed out in run 1 but completed in run 2, so semantic repeatability is false at
  the current 60-second boundary.
- Tesseract is repeatable but unsuitable: body macro CER 1.2400, Region Recall 0.0363 and six
  resource-limit pages in both runs; peak RSS is about 151 MiB.
- PaddleOCR is repeatable only in failure: the locked CPU runtime fails 15/15 pages in oneDNN/PIR,
  body CER is 1.0 and Region Recall is 0. Disabling oneDNN did not finish the first page within a
  separate 120-second diagnostic window, already beyond the frozen 60-second limit.

The selection-neutral comparison SHA-256 is
`34cb6ad407eba3b5fdfeaaa72c5fb325203ca784573fe9563a3e92245659630a`; its deployment-evidence
SHA-256 is `7dd31d3531d2c675952a617ef3918e0580eefb1a7bc0eba954fcc20b12bd6edf`.
No automatic composite score was used. The owner explicitly selected RapidOCR and approved a
90-second default limit while retaining 200 DPI, 20MP, 1.5 GiB and one Worker. The checked
`default_v1` file SHA-256 is
`ca962f3ba5f8c4053e502acfe3e36928351a24650db2fad589d153a4d6a719a0`; its resolved runtime
Profile identity is `1ead48fec1275cd9581f0079870bca60fcaabbea777c5909751a79ac2290623d`.
Two independent default runs completed 15/15 pages with no warning or resource-limit result and
matched every semantic result. Their report SHA-256 values are
`a5ebe1f16240f074a848a4db2ab4d692e79c06685fb64cc4647dde2d5ecb9418` and
`27ee9cef5aaa2c5bc5a32f7137e701ac946b626aec1f007fad24f747f463ac6e`.
P05 passes its Exit Gate and supplies the implementation prerequisite, but formal P06 work remains
held at the DS2 Course Owner approval checkpoint.

## Pre-P06 formal DS2 Candidate checkpoint

The current immutable Candidate is
`datasets/courserag_eval/v1/candidates/ds2/p06_evidence_r5.json`, SHA-256
`f4295f9783b131a8305713765907e169a83dc741d6c9af390b0b67b2f15b5bfc`. It contains exactly
120 Evidence records: DOCX 80 across 16 Sections and PDF 40 across eight Sections, with five
records per Section. The PDF subset contains 30 native-text and ten OCR-derived records on the
frozen parent pages `11, 15, 18, 21, 22, 23, 24, 26, 27, 32`. Ten records are complete tables,
including the Approved rendered-visible 7x4 DOCX table 20. All SourceSpans refer only to the two
Primary DocumentVersions; derived scans appear only in OCR provenance.

The source-incomplete terminal `1.4.1` excerpt was not padded or guessed. Following the owner's
explicit option A, it was replaced by the source-complete dense Section `1.3.7 AI＋电子支付`
spanning PDF pages 31–32. Pre-delivery r1–r4 remain immutable and explicitly superseded: they
exposed line-fragment selection, structural/body OCR concatenation, three unreadable PDF object
orders and text-only table BBoxes. None was delivered for owner review. r5 preserves original
text, rejects only exact audited malformed object sequences, uses character-range overlap to keep
native and OCR Evidence disjoint, and expands DOCX table BBoxes to the fixed renderer's vector
rules.

Two final generation runs reproduced Candidate SHA-256
`f4295f9783b131a8305713765907e169a83dc741d6c9af390b0b67b2f15b5bfc`, Candidate Manifest
SHA-256 `c75f864217481e9a2155c03b67b21b9c3bb9e691eb8938268691d3225dadb920` and review-pack
index SHA-256 `23cfafeda58a2155b617b78054105a675f41e7bb4516b25c7057ba23e27c4cbf`.
No exact or normalized duplicates were found. The focused suite reports 27 passed; the full suite
reports 350 passed and five gated skips; all 314 files pass Ruff format, Ruff check passes, Mypy
passes over 221 source files, and 38 JSON Schemas were exported.

The offline pack has four fixed groups of 30 and can export one decision JSON per group. All 120
records remain `candidate` with `approval=null`; `approved/ds2/p06_evidence.json` does not exist,
Dev/Test remain empty and Test remains unlocked. P06 B1/B2 has not run. P06 may start only after
all four groups are reviewed with no unresolved return and the owner explicitly approves the exact
r5 Candidate SHA-256.

## Pre-P06 formal DS2 r5 review and r6 correction checkpoint

The Course Owner completed all four r5 review groups. The submitted files bind the exact r5 SHA-256
and cover all 120 records without conflicts: 98 records passed and 22 were returned. The merged,
append-only decision artifact is
`datasets/courserag_eval/v1/reviews/ds2_p06_review_decisions_r5.json`; all original return notes and
the four feedback file Hashes are retained. r5 is now marked `rejected`, not silently overwritten.

The current immutable Candidate is
`datasets/courserag_eval/v1/candidates/ds2/p06_evidence_r6.json`, SHA-256
`f35292d55f6848e18f6e8067a8ca0e72cf0bedae49e92d60cd05cc1513c1b35c`. It preserves the exact
record Hash of every one of the 98 accepted r5 records. Only the 22 returned records changed; eight
received new stable Evidence IDs because their source text or source-unit identity expanded. The
other 14 retain their stable ID while correcting semantic type, `requires_parent`, or necessary
neighbors.

The returned formula and algorithm records were visually rebound to the fixed LibreOffice
7.4.7.2 render. Equations 14, 16, 18, 19 and 20 and the perceptron algorithm use the frozen
`courserag.ds2-rendered-formula-linearization.v1` rules, with BBoxes covering the visible formula
objects. Following owner review, DOCX TableGold 0 is a `procedure`, so the ten TableGold-derived
records now comprise nine semantic tables and one procedure. This is a label correction, not a
change to the source or the fixed 120-record distribution.

Repeated r6 generation reproduces Candidate SHA-256
`f35292d55f6848e18f6e8067a8ca0e72cf0bedae49e92d60cd05cc1513c1b35c` and Candidate Manifest
SHA-256 `da869005492b2107ae882afd3628c8987533a58be0352e0bdb033847f82d8b2d`. The focused suite
reports 28 passed; the full suite reports 351 passed and five gated skips; all 315 files pass Ruff
format, Ruff check passes, full Mypy reports no issues across 222 source files, and 38 JSON Schemas
were exported.

All 120 r6 records remain `candidate` with `approval=null`; Approved DS2 does not exist, Dev/Test
remain empty, Test remains unlocked and P06 B1/B2 has not run. P06 may start only after the 22 r6
delta records are reviewed with no unresolved return and the owner explicitly approves the exact
r6 Candidate SHA-256.

## Pre-P06 formal DS2 r7 all-record necessary-neighbor checkpoint

The Course Owner reported the r6 review complete and issued a global context-only correction:
every record must be checked for real necessary adjacency, and generic Section headings must not
stand in for antecedents, list/table scope, formula definitions, code scope or process context. The
owner waived another item-level review for this delegated correction, but exact batch Hash approval
remains mandatory.

The current immutable Candidate is
`datasets/courserag_eval/v1/candidates/ds2/p06_evidence_r7.json`, SHA-256
`ebc980a4f52a763001bd2169c1215aac81eac55f4f661f7320a0e600e0acdcad`. The all-record audit at
`datasets/courserag_eval/v1/provenance/ds2_p06_necessary_neighbor_audit_r7.json` covers 120/120
records: 55 require exact neighbors and 65 are independently complete. The audit finds 20 anaphora,
8 list-scope, 13 table-scope, 5 formula-symbol, 7 procedure-sequence, 5 causal/transition and 2
code-scope dependencies; records may have more than one class.

r7 changes context metadata only. Relative to r6, Gold text/content Hashes, source units/spans,
BBoxes, semantic labels, upstream Approved references and stable Evidence IDs have zero changes.
Seventy-eight record Hashes change because generic, missing or excessive neighbor metadata changed.
Only the precise `（2）R3-LIVE[23]` antecedent remains a `parent_heading`; all generic Section-title
neighbors were removed.

Three repeated generation runs reproduced Candidate SHA-256
`ebc980a4f52a763001bd2169c1215aac81eac55f4f661f7320a0e600e0acdcad`, audit SHA-256
`74b200a873a52d75a21b96aba8380a09ee9d5d1903285c8aac90388f840e29e6` and Manifest SHA-256
`3c33cafaaa23789e725d1cf0af75c9d8c25483b822ffccec371510c688366403`. The r7 focused suite
reports 28 passed. The final full suite reports 351 passed and five gated skips. The first full run
had one Streamlit `AppTest` 10-second startup timeout; that test passed alone in 5.69 seconds and the
second unchanged full run passed. All 316 files pass Ruff format and lint, 38 exported Schemas match,
and full Mypy reports no issues across 223 source files.

The Course Owner approved the exact r7 Candidate SHA-256. Promotion created
`approved/ds2/p06_evidence.json` with 120 Approved records and 120 embedded ApprovalRecords,
plus `provenance/ds2_p06_approval.json` and 120 append-only review-log entries. Replaying the same
approval produced identical Approved and batch-approval Hashes and did not append duplicate log
entries. Dev/Test remain empty, Test remains unlocked and P06 B1/B2 has not run. The Pre-P06 data
gate passes; P06 implementation and formal B1/B2 evaluation may now start, but the P06 Exit Gate
itself has not yet been evaluated.

## P06 completion summary

P06 establishes stable source-derived `ev1_*` Evidence, explicit Block/range/PageBBox/OCR
provenance, a course-scoped single/batch Resolver and Source Preview, versioned Chunk Profiles and
Chunk Sets, deterministic Parent/Child Chunking, exact Evidence coverage links, and a fail-closed
local tokenizer identity. Additive revision 0011 persists the new relationships without migrating
legacy Chunk IDs or publishing an index. The P10 citation migration skeleton rejects legacy Chunk
IDs and defers cross-version repair explicitly.

The authoritative formal runs are `storage_eval/p06_b1_b2/run-3` and `run-4`. They consume only
Approved DS2 SHA-256 `f49d84027cde8341d906e270d29cc46e7b71eb6de4da5220188cb03894436b78`,
disable tuning/fallback/LLM judging, and produce byte-identical system output SHA-256
`bfa6a41e3063520b281da4413a2bce6348b41c85dcb8180f5063fa6b76e6d396`. B2 maps 101/120
Approved semantic units, resolves 4,538/4,538 Chunk-to-Evidence links and covers 1,961/1,961
runtime Evidence records. Complete semantic-unit rate is 0.8417 versus B1 0.8333, boundary error
is 0.1583 versus B1 0.1667, and redundancy is 0.000386 versus B1 0.04252. Evidence text
consistency is 0.8417, PageBBox consistency 0.80, OCR provenance preservation 0.80 and necessary
Parent expansion 0.6364. The remaining quality gaps are recorded, not hidden by changing Gold.

Revision `0008 -> 0011 -> 0010 -> 0011` passes in the isolated migration test. The final focused
suites report 6 Evidence, 3 Chunking, 2 Stage/migration and 3 evaluation tests passed; the owner
PDF/DOCX B0 Smoke passes. The full suite reports 366 passed and five explicit gated skips; Ruff
format/check pass and full Mypy reports no issues across 239 source files. No Secret, automatic
fallback, tracked evaluation temporary file, public API change, Active Index publication or
destructive migration was introduced. P06 Exit Gate passes and P07 now meets its prerequisite;
P07 has not been started.

## Pre-P07 formal DS3 r1 Candidate checkpoint

Tasks `ED-PRE07-DS3-T01` through `ED-PRE07-DS3-T07` produced an unapproved, source-grounded
P07 Gold bundle. The DS3 Candidate contains 107 knowledge points over the frozen 24 Sections:
73 from the algorithms/systems DOCX course and 34 from the general-education PDF course. It uses
only the two owner-supplied semantic lineages. All summaries are the exact text of their primary
Approved DS2 Evidence; no P07 output, P06 retrieval hit or external fact was used.

The exact Bundle SHA-256 is
`2ebd8f96bb8bd6f0c178dce7545ef991cceb181c6cfe2a3554592bc3daf10400`; the DS3 Candidate
SHA-256 is `e5365e52cef33bcceca9d729ad29db84b03bb3f205ab3378070dfc847e564976`.
Existing Approved DS2 directly supports all 107 selected records, so the separate DS2-KP Support
Candidate is intentionally empty, SHA-256
`e94df4c8c4d79adc136b1aa14a8e09968dbf1d4a31c4a1d3a237dad6266b50d5`, rather than padded
with duplicate Evidence. The deterministic concept-family split is 75 calibration / 32 holdout;
global Dev/Test remain empty and Test remains unlocked.

The offline review bundle provides four six-Section groups, 107 source-page/BBox assets, a complete
first-pass page and an independent second-pass page for 37 Alias/OCR/formula/high-risk or stable
20% sample records. Five source boundaries require explicit attention: the four newly introduced
DOCX Sections and independently bounded PDF `1.3.7`. No Approved DS3 file exists. P07 remains
`not_started`; formal P07 evaluation requires both review passes to have no returns and exact
Course Owner approval of the Bundle Hash.

Deterministic regeneration reproduced Candidate and Bundle Manifest byte-for-byte. The final focused
suite reports 22 passed; the full suite reports 372 passed and five gated skips. All 345 files pass
Ruff format/check, all 43 exported Schemas match, full Mypy reports no issues across 242 source
files, and `git diff --check` reports no whitespace error.

## Pre-P07 formal DS3 approval checkpoint

On 2026-08-05 the Course Owner explicitly attested that all 107 first-pass records and all 37
second-pass records had been reviewed, all passed and none were returned, then approved exact P07
Gold Bundle SHA-256 `2ebd8f96bb8bd6f0c178dce7545ef991cceb181c6cfe2a3554592bc3daf10400`.
The attestation was materialized as two Hash-bound review-decision files rather than inferred by the
system.

Promotion created 107 Approved DS3 records with embedded ApprovalRecords at
`approved/ds3/p07_knowledge_points.json`, SHA-256
`339a51f6f8f8fedeb533b6cbe0efa3ad96783dbae9580a4309924b63358b9566`. The intentionally empty
Approved DS2-KP support file retains SHA-256
`e94df4c8c4d79adc136b1aa14a8e09968dbf1d4a31c4a1d3a237dad6266b50d5`. Batch approval SHA-256
is `db180e9cc043f8c13e90b1c203089c12ab276ddb6d122a76b6d7b0cb4c23783c`.

An identical approval replay produced the same hashes and kept P07 review-log entries at 107.
Manifest status is `ds3_p07_knowledge_points_approved`, P07 is `formal_eval_ready`, global Dev/Test
remain empty and Test remains unlocked. The Pre-P07 data gate now passes; this approval does not
claim that the P07 implementation or Exit Gate has passed.

## P07 implementation checkpoint

P07 now has deterministic Section/Evidence Window building, an OpenAI-compatible structured
Provider, bounded concurrency/retry and identity-bound Window caching, exact course-scoped
normalization/deduplication, a five-component deterministic publish score, persistent
KnowledgePoint/Alias/Evidence/Chunk/Review facts, and versioned reviewer APIs. Migration 0012 is
additive on upgrade and has an isolated `0011 -> 0012 -> 0011 -> 0012` test. Existing CoursePilot
routes and B0 responses remain compatible; the B0 snapshot assertion now treats later public
routes as additive while requiring every frozen B0 route to remain byte-for-byte described.

| Task | Status | Evidence |
|---|---|---|
| P07-T01 | completed | 24 Section scopes build 27 checked-token Windows with one-Evidence overlap and no oversized Window |
| P07-T02 | completed_implementation | configured Provider, bounded concurrency/retry, Prompt/Model/Window Hash cache and failed-Window rerun; no automatic fallback |
| P07-T03 | completed | deterministic invalid-candidate filtering, NFKC name/Alias normalization, exact Section deduplication and course-scoped consolidation |
| P07-T04 | completed | KnowledgePoint, Alias, Evidence N:N, derived Chunk N:N, optional Parent and append-only Review facts persist under 0012 |
| P07-T05 | completed | versioned evidence/naming/cross-window/ambiguity/duplicate score; model self-confidence is trace-only |
| P07-T06 | completed | exact Threshold Candidate approved; 0.75 frozen before Holdout and no threshold/Profile change applied |
| P07-T07 | completed | authenticated list/detail/modify/approve/reject/deprecate/merge/split API with If-Match and Idempotency-Key contracts |
| P07-T08 | completed | Calibration 19 calls + unique Holdout 8 calls = 27 vs 1,327 B0 proxy (97.9653% reduction); Holdout all-Gold F1 0.069565 |

The local call plan is 27 Section-Window requests versus the P06 Child-Chunk proxy of 1,327,
a projected 97.9653% reduction. This is architecture evidence, not a completed Provider-run metric.
The real Pilot has not started. The owner explicitly authorized transmission of the two textbooks'
derived Evidence to the configured compatible endpoint and selected P07-D003 option A. A
deterministic Section/Provider-Window-isolated r2 Split now preserves the 107 Approved Gold records
byte-for-byte, keeps the prior split, produces 75 calibration / 32 holdout records and has zero
mixed Scopes. Its exact protocol Bundle SHA-256 is
`7261cb63b81f5b2e260a6a578383bd41df55c690aae999891d479146395b215b`; calibration and holdout
remain blocked until that exact Candidate receives a separate owner approval.

Local verification is clean: 39 P07/DS3/API/migration focused tests pass; the user DOCX/PDF B0
Smoke passes; the final suite reports 396 passed and 5 gated skips; Ruff format/check and Mypy
(257 source files) pass; Alembic has the single `0012_knowledge_point_assets` head. Therefore the
first and third structural Exit Gates pass, but the actual call-count Pilot and threshold
This historical implementation checkpoint was superseded by the approved r2 Calibration and
single Holdout recorded above. Overall P07 Gate is **passed**, and P08 is ready to start.

The post-approval full regression reports 372 passed and five gated skips. The only first-run
failure was an obsolete DS2 test that required the top-level governance status never to advance;
it now verifies the DS2 component remains Approved and P06 remains Gate-passed while allowing the
approved DS3 governance state.

## Pre-P08 formal DS4/DS5 Retrieval Candidate checkpoint

Tasks `ED-PRE08-DS45-T01` through `ED-PRE08-DS45-T08` produced an unapproved, retrieval-only
P08 Gold bundle. Ten Source Packages cover all 24 Approved DS3 Sections and bind only the two
Primary semantic lineages. DS4 contains 60 Query Processing records, five capabilities at 12 each
and a 42/18 DOCX/PDF split. DS5 contains 100 Retrieval records with the frozen eight-type
distribution, Dev 60 / Test 40, DOCX/PDF 70/30 and explicit 2/1/0 Evidence judgments plus three to
five same-course hard negatives per Query.

The exact Bundle SHA-256 is
`329433b38981be2f5bb0608cc38146d6f4c29e902cf624065e6ef1e716e4354d`.
The diagnostic overlay is 90 `retrieval_main` records (Dev 54 / Test 36) plus 10
`upstream_gap_diagnostic` records (Dev 6 / Test 4) bound to ten distinct members of the frozen
19/120 P06 mapping gap. Query text and relevance labels come only from Approved DS2/DS3; P06
runtime output is used only to mark the diagnostic stratum. All QA Claims, Short Answers,
Forbidden Claims and answer variants remain empty with `qa_gold_status=pending_p09`.

Both Candidate files, Source Packages, proposed Split and two offline review pages regenerate
byte-for-byte. The focused DS4/DS5/Schema/boundary suites report 30 passed; the full suite reports
415 passed and five gated skips. All 380 files pass Ruff format/check, all 48 exported Schemas
match, full Mypy reports no issues across 262 source files, and `git diff --check` reports no
whitespace error. No Approved DS4/DS5 files or global Dev/Test IDs
have been written, and `test.lock.json` remains unlocked. P07 governance is corrected to
`completed_gate_passed`; P08 is `candidate_review_pending`. P08 formal Dev evaluation is blocked
until all 160 first-pass records, all 132 second-pass records and the exact Bundle Hash receive
Course Owner approval.

### Pre-P08 r2 systemic-audit checkpoint

The r1 Bundle `329433b38981be2f5bb0608cc38146d6f4c29e902cf624065e6ef1e716e4354d`
is preserved but superseded after the Course Owner identified an opaque-ID review defect and two
incorrectly assigned relevance/linking examples. A complete rule audit found 30 heuristic DS4 edge
cases, 90 DS5 cases with an unverified heuristic one-point label, 78 DS5 cases whose selected zero
label shared a Source Package with Required Evidence, 15 template paraphrases and 10 meta-level
procedure prompts. The source-readable r2 replaces these categories without modifying r1.

The exact r2 Bundle SHA-256 is
`7f6b22556e3261d242dbd2b425812eeb18489dc75f6086697d808bbffbfbdf52`.
All 160 cards now resolve each Knowledge Point ID to its name, Summary, primary Approved Evidence
text, necessary adjacency, Section, page, BBox and overlay, and resolve each DS5 Evidence judgment
to exact Approved source text. R2 has no automatically inferred one-point labels; every answerable
Query's Required Evidence is linked directly to its expected Approved Knowledge Point, with no
unlisted same-KP Evidence silently defaulting to zero. Candidate and Approved remain physically
separate, QA remains `pending_p09`, Test remains unlocked, and P08 remains
`candidate_review_pending` until the owner completes both r2 review passes and approves the exact
r2 Bundle Hash.

R2 regenerated twice with the same Bundle identity. The DS4/DS5 plus dataset-boundary focused
suite reports 15 passed; the final full suite reports 416 passed and five gated skips. All 48
exported Schemas, Ruff format/check across 381 files, and full Mypy across 263 source files pass.
`git diff --check` reports no whitespace error (only existing Windows LF/CRLF notices).

### Pre-P08 r3 Course Owner feedback adjudication checkpoint

The Course Owner completed the r2 first pass: all 160 records were decided and 25 were returned,
but the r2 browser exporter omitted textarea notes from its JSON artifact. The exact returned-ID
set is preserved. Independent source/test-purpose adjudication accepts 17 returns and retains eight
intentional boundary cases; each retained case and rationale is recorded in
`p08_r2_first_review_adjudication.json` and is shown again in the r3 first-pass UI.

Option B produced the comprehensive r3 Candidate. All 15 cross-Section prompts now ask for the two
source-supported descriptions without asserting an unsupported relationship. All 100 DS5 records
were rerun through exact-text containment checks and a same-course confounder ranking; 118 complete
2-point judgments, one source-proven partial 1-point judgment and 400 explicit zero judgments are
present. Every case has four reviewable hard negatives, and its full top-eight audit is retained in
`p08_r3_relevance_audit.json`. No hard negative is also positive or linked to an expected KP.

The exact r3 Bundle SHA-256 is
`ff64abba71d392496e7ce530f7de5c612794616557b65a7aa11e739e20759396`.
The changed-record first pass contains 117 visible cards; 43 exact-hash unchanged r2 passes are
carried through the adjudication artifact. The blinded second pass remains all 100 DS5 records plus
32 DS4 records. Review export now preserves per-record notes, reviewer and timestamp and refuses a
returned record without a reason. Candidate, Approved, global Dev/Test and Test Lock remain
unchanged in governance meaning: r3 is unapproved, Test is unlocked and P08 formal Dev evaluation
remains blocked pending both r3 review artifacts and exact Bundle approval.

R3 regenerated in two independent Python processes with the same Bundle identity. The focused
DS4/DS5/Schema/boundary suites report 33 passed; the final full suite reports 418 passed and five
gated skips. All 48 exported Schemas match, Ruff format/check passes across 383 files, and full
Mypy reports no issues across 265 source files. `git diff --check` reports no whitespace error
(only existing Windows LF/CRLF notices).

### Pre-P08 r3 Course Owner review attestation

On 2026-08-06 the Course Owner explicitly stated in this conversation that review was complete,
all records passed and browser-exported JSON was unnecessary. That statement is materialized as
two immutable `course_owner_conversation_attestation` review artifacts: the first covers exactly
all 160 manifest IDs and the second covers exactly all 132 blinded-review IDs; both have zero
returns and bind Bundle
`ff64abba71d392496e7ce530f7de5c612794616557b65a7aa11e739e20759396`.
This records review completion only. DS4/DS5 remain Candidate, P08 remains
`candidate_review_pending`, and promotion still requires the separately specified literal Bundle
approval from the Course Owner.

### Pre-P08 r3 exact Bundle approval checkpoint

The Course Owner explicitly approved exact Bundle
`ff64abba71d392496e7ce530f7de5c612794616557b65a7aa11e739e20759396` on 2026-08-06.
The approval tool revalidated all Candidate, review, Split, upstream Approved and preserved report
hashes, then promoted 60 DS4 plus 100 DS5 Retrieval records. Approved DS4 SHA-256 is
`22279c07b74166788b96300a589b494758210bec69a2b19a6062f5aa08cffb2a`; Approved DS5 SHA-256 is
`ff266ec674490ae69480b1b119cc157cc7f70006e4efc8335a8b2cd44e1e9afd`.

The global Split now intentionally contains Dev 60 / Test 40, while `test.lock.json` remains
unlocked. The fail-closed P08 tuning loader exposes only the 54 `retrieval_main` Dev records and
rejects Test IDs. All DS5 QA fields remain empty with `qa_gold_status=pending_p09`. Manifest status
is `ds5_p08_retrieval_approved`, and `phase_input_status.p08=formal_dev_eval_ready`.

Approval replay is idempotent: the review log contains exactly 160 unique record approvals. The
final full suite reports 419 passed and five gated skips; Ruff format/check passes across 383 files,
Mypy reports no issues across 265 source files, all 48 Schemas match, and `git diff --check` has no
whitespace errors (only existing Windows LF/CRLF notices). The Pre-P08 data gate is **passed**;
P08 formal Dev evaluation may start. P08 itself has not run and its Exit Gate is not yet evaluated.

## P08 implementation checkpoint

P08-T01 through P08-T06 and P08-T08 are implemented and locally verified. The owner selected the
local/offline path for P08-D008. `Qwen/Qwen3-Embedding-0.6B` is installed under `D:\AI\models`,
bound to complete bundle SHA-256 `1db2c971...` and weights SHA-256 `0437e45c...`, and executed with
CUDA 12.6, BF16, SDPA, 2,048-token maximum and query prompt `query`. Formal B3/B4/B5 ran on the
exact 54 Approved `retrieval_main` Dev cases. Two Run result Hash sets are identical; Run 2 reused
54 Jina and 54 Cohere cache entries without Provider requests. Freeze Candidate SHA-256 is
`5b5d973ebf70d32cc10fa0ad4103261eee745dc4604f9e9f1a693817d3c3c95f` and remains pending explicit
course-owner Reranker/default-threshold approval.

| P08 task | Status | Evidence |
|---|---|---|
| P08-T01 | completed_implementation | versioned Chroma Adapter, independent Embedding Port, batching, Active Index pinning and Repository hydration boundary |
| P08-T02 | completed | BM25S persistence, Chinese search tokenization, protected terms and explicit character-bigram zero-term fallback |
| P08-T03 | completed | deterministic equal/weighted RRF with original Dense/Sparse Rank/Score and stable tie-break |
| P08-T04 | completed_implementation | Jina/Cohere/Voyage HTTP Contracts, optional fail-closed local CrossEncoder and disabled mode |
| P08-T05 | completed | Candidate-K/Top-N, truncation, retry, timeout, cache, production warning fallback, evaluation fail-sample and hard budgets |
| P08-T06 | completed | Course/Document/DocumentVersion/Section/KP/SourceTier/IndexVersion isolation |
| P08-T07 | completed_gate_passed | exact 54-case Dev Runner completed B3/B4/B5 twice; owner approved Candidate `5b5d973e...`, Cohere `rerank-v4.0-pro`, threshold `0.7502601`; checked `default_v1` SHA is `dc4109b1...` |
| P08-T08 | completed | additive Search Rank/Trace, full RetrievalRun identity/usage/fallback fields and 0013 persistence |
| P09-T01 | completed | configurable Normalize/Filter/KP/Alias/dual-axis Router/Multi-query/one-Retry Query Pipeline |
| P09-T02 | completed | immutable raw/current query, filter preservation, per-step toggle/hash/timing/warning Trace and 0014 persistence |
| P09-T03 | completed | cross-query RRF aggregation, stable Evidence deduplication and relation-bound Parent/Neighbor expansion |
| P09-T04 | completed | fixed local Tokenizer identity, 8-item/4,000-token packing, Citation Map and full Packing Report |
| P09-T05 | completed | deterministic Sufficiency Gate, structured Claim-Evidence QA and programmatic Citation composition |
| P09-T06 | answer_grounding_repair_implemented_and_measured | type-aware Answer Shape, Evidence-segment validation, Context-only Citation composition and one directed Repair pass; Fresh Dev completed but its original automated Citation contract is invalid for Freeze |
| P09-T07 | fresh_dev_completed_protocol_failed | 60/60 Dev Cases completed from Protocol `211bf746...` and B7 Snapshot `d85d9603...`; report `b04fc9b...` failed Protocol r2, so no Freeze Candidate exists |
| P09-T08 | completed | stable Search/Context/QA v1 routes and Local/Remote/Mock-compatible additive contracts; Legacy behavior unchanged |
| P09-CCR-T01 | completed | fixed exact Report `b04fc9b...`, Checkpoint `2a53b269...`, Approved Bundle `5a84bac0...` and 54/47/6/1 main-Dev scope |
| P09-CCR-T02 | completed_implementation | Evidence-ID overlap moved to an explicit diagnostic namespace; Gold Claim Coverage and Claim-aware Answerability contracts corrected |
| P09-CCR-T03 | completed_implementation | automatic applicability fixed to nine factoid and two list Cases; Q2/Q3 must be recomputed symmetrically |
| P09-CCR-T04 | completed_owner_approved | blinded phase-1 Package `ffde9da5...` was reviewed and recovered without re-entry; submitted Decisions `52e0044e...` passed exact 54/150/150 identity checks and were explicitly owner-approved |
| P09-CCR-T05 | completed_owner_approved | Phase 2 Package `0ad53126...` Decisions `85cb33eb...` passed all 54-Case identity, valid-label mapping and exact missed-Gold complement checks and were explicitly owner-approved |
| P09-CCR-T06 | completed_formal_scoring | Approval `87e61b5f...` produced formal Claim/Citation metrics from fixed outputs with zero Provider/Test access; Report SHA is `652d2a08...` |
| P09-CCR-T07 | completed_gate_failed | 17/19 checks pass; `qa_failure_rate_0` and `short_answer_token_f1_q2_delta` fail, so no Freeze Candidate/default profile is generated and P10 stays blocked |
| P09-CCR-T08 | completed_reported | complete problem/cause/contract/two-pass human review/formal result report written with risks and next-decision boundary |
| P09-GR-T01 | completed | preregistered exact 12-Case Approved-Dev delta, fixed 48-case reuse, 180,000-token DeepSeek cap, zero Cohere and no-Test boundary |
| P09-GR-T02 | completed | compact Evidence aliases, 3,200-token list contract, list summary and explicit task-factoid answer shape implemented behind a default-off evaluation flag |
| P09-GR-T03 | completed | strict alias restoration, schema/citation validation, safe completion metadata and one fail-closed directed Repair pass |
| P09-GR-T04 | completed_real_run | 12/12 fresh Cases completed; DeepSeek usage 82,552/180,000 and P09 cumulative usage 907,286/2,500,000; Cohere 0 and Test unread |
| P09-GR-T05 | completed_gate_failed | original 36-item long-list failure fixed, but Q3 retained one schema failure and factoid F1 `0.360260` stayed below floor `0.406108`; Gate `a3f38797...` failed with no further tuning |
| P09-GR-T06 | completed_fail_closed | candidate remains disabled by default; no human delta review, Freeze Candidate, default profile, P10 work or post-result Provider call was performed |
| P09-GOV-T01 | completed_owner_approved | frozen P09 core Exit Gate and stricter QA Profile Freeze are now tracked separately; core Gate passes, failed candidate remains rejected/default-off, and P10 inherits explicit quality debt without retroactively relaxing metrics |
| P09-GOV-T02 | completed_owner_approved | `QUALITY_GATE_POLICY.md` freezes L0—L3 metrics, phase/Profile status separation, one bounded calibration window, Test-only-after-freeze, impact-based regression and P10/P18 convergence points for P10—P19 |
| ED-PRE10-DS678-T01 | completed | additive formal-v1 DS6/DS7/DS8/Security, Fixture, Split, Review and Bundle/Approval Schemas retain legacy Pilot compatibility |
| ED-PRE10-DS678-T02 | completed_candidate | 7 deterministic semantic variants and 8 bounded file controls are Hash-bound; every variant is non-searchable and the semantic-source count remains two |
| ED-PRE10-DS678-T03 | completed_candidate | DS6 freezes 9 scenarios, 24 citation judgments and exact 5/11/6/2 valid/migrated/review/invalid distribution |
| ED-PRE10-DS678-T04 | completed_candidate | DS7 freezes 12 incremental/writeback scenarios, Approved-Dev-derived 7/3 writeback content and 10/3000/24h/manual boundaries |
| ED-PRE10-DS678-T05 | completed_candidate | DS8 freezes 20 cold/warm templates without enumerating Test IDs; 16 non-semantic Security/Fault controls are isolated |
| ED-PRE10-DS678-T06 | completed_owner_attested | Course Owner explicitly attested all 57 first-review and 29 second-review records passed; the exact statement and its SHA-256 replace, rather than simulate, browser JSON exports |
| ED-PRE10-DS678-T07 | completed_approved | exact Bundle `5b6d756a...` promoted DS6/DS7/DS8/Security atomically in batch `.002`; 57 record approvals were emitted and exact replay was idempotent |
| ED-PRE10-DS678-T08 | completed_validation | Candidate replay and Schema checks remain stable; approval integrity, record counts, unlocked Test and focused quality suites pass |

Formal Run 1 used 224,207 Jina tokens across 66 requests and 54 Cohere Search Units across 56
requests, below the 8M/500 hard limits; both had zero Fallback and zero warnings. Cohere produced
Recall@10 0.8858, MRR@10 0.7384 and nDCG@10 0.8259, versus Jina 0.7593/0.5537/0.6664. The owner
approved Cohere and threshold `0.7502601`; P08 is `completed/passed` and P09 is ready to start.

Final verification after restoring the local CUDA extra and freezing `default_v1`: 446 tests
passed with five gated skips;
P08 focused suites passed 63 tests; B0 sample Smoke passed; Ruff passed; Mypy found zero issues in
283 source files; `0013_hybrid_retrieval` is the sole Alembic head; Secret/temp/Hash guards passed.

## Pre-P09 formal DS5 QA/Context Candidate checkpoint

Tasks `ED-PRE09-DS5QA-T01` through `ED-PRE09-DS5QA-T08` produced independent QA and Context
overlays for the exact 100 Approved P08 DS5 Queries. The Retrieval file, its 100 records, Dev/Test
assignments and P08 B3-B5 artifacts remain Hash-bound and unchanged. The Candidate contains 90
answerable and 10 unanswerable cases, 218 source-verbatim Required Claims, nine grounded comparison
Forbidden Claims and 64 Approved-DS2 necessary-neighbor constraints. Optional Claim count is zero
because no source-supported fact was necessary only for embellishment.

Context Gold is constraint-based rather than a single ideal order: complete Evidence Groups,
relevant Evidence, exact necessary neighbors, hard negatives, boundary preservation and the 8-item /
4,000-token profile are frozen. The first review contains all 100 QA/Context cards; the deterministic
risk-layered blinded review contains 67. Every opaque KP/Evidence/Claim ID is accompanied by readable
source text, location and Hash. Two records carry an explicit yellow owner-adjudication warning: the
speech-synthesis-risk Evidence does not enumerate the claimed risks, and the perceptron-distance
Evidence ends before the displayed formula.

Two independent generations reproduced QA Candidate SHA-256
`5f5ca0d61a8c1950b93e0bbf7d8d56497219aa3dd7e1afa76df0643d5a78c4f9`, Context Candidate SHA-256
`f8940c2ed0ddfd6f230c3254775d3b813e9d2eb1575fe3796824d83486275762` and exact Bundle SHA-256
`0634c618279e8c4ddd432eeff2a20974924c06ddfe641f48da528d8311bb30e0`. Candidate/Approved remain
physically separate; no P09 Approved artifact, review decision or review-log entry was written.
Test remains unlocked. P09 is blocked until both review passes complete with zero unresolved returns
and the Course Owner approves the exact Bundle Hash.

Verification: P09/Schema/boundary focused suites report 27 passed; the P08-governance compatibility
and P09 focused rerun reports seven passed. The final full suite reports 451 passed and five gated
skips. Ruff format/check pass across 415 files, all 53 exported Schemas match, full Mypy reports no
issues across 287 source files, and `git diff --check` reports no whitespace error (only existing
Windows LF/CRLF notices).

## Pre-P09 formal DS5 QA/Context Candidate r2 checkpoint

The Course Owner's r1 review-complete statement is preserved as two immutable conversation
attestations, but the r1 Bundle is not eligible for approval after a systematic answer-obligation
audit found incomplete or non-atomic coverage in 18 answerable cases. Candidate r2 keeps all 100
P08 Query identities, texts, courses, Splits and Retrieval record Hashes unchanged. It changes 18
QA records, leaves the other 82 QA record Hashes unchanged, changes one ERNIE Context record and
leaves 99 Context record Hashes unchanged.

The r2 audit contains all 100 cases: 90 answerable cases are `complete`, ten unanswerable cases are
`not_applicable_unanswerable`, and zero answer obligations are uncovered. Claims increase from 218
to 243. The ERNIE procedure case adds one nearest/minimum source neighbor independently verified
against raw OOXML and fixed-renderer physical page 272. Empty short-answer arrays remain valid for
explanatory, comparison and procedure cases because those cases are scored through complete atomic
Required Claims; the review UI now states this explicitly instead of presenting an unexplained
empty field.

Two independent generations reproduced QA SHA-256 `e2cd2853...`, Context SHA-256 `abf6b1d6...`,
coverage-audit SHA-256 `2ce71cbb...` and exact Bundle SHA-256 `5a84bac0...`. The focused
P09/Schema/metrics suite reports 23 passed; the final full suite reports 453 passed and five gated
skips. Ruff format/check pass across 417 files, all 54 exported Schemas match, and full Mypy reports
no issues across 289 source files. `git diff --check` has no whitespace errors (only existing
Windows LF/CRLF notices). r2 remains Candidate: both 18-record difference review passes and literal
Bundle approval are still required; no Approved P09 artifact, Test lock, review-log promotion or
P09 evaluation was performed.

### Pre-P09 r2 exact Bundle approval checkpoint

On 2026-08-07 the Course Owner explicitly confirmed completion of both 18-record r2 difference
reviews and approved exact Bundle
`5a84bac041375310d5bb80f17f7481464d07dbcf75f9f980c6b8a030e58af0c1`. The statement is retained
as two Bundle-bound `course_owner_conversation_attestation` artifacts. The approval path revalidated
the Bundle, all Candidate and upstream Hashes, the 100-case obligation audit, both review sets,
Dev/Test identities and the unlocked Test policy.

Approved QA SHA-256 is `d3460b0831b5ce7567e0c97c82b0574c2aeb31776944fba9982e3f21d84d62c7`;
Approved Context SHA-256 is
`0f23da3eba8b76e29040e4a5a8632f24b170e65e8fd792d7a98a6633c51ee330`. All 200 records have
record-level ApprovalRecords and exactly 200 unique append-only review-log entries. Approval replay
returns identical Hashes without duplicate audit rows. The fail-closed P09 loader exposes Dev 60
(54 retrieval-main plus six upstream-gap diagnostics); Test remains unlocked and unreadable by P09.
Governance is `ds5_p09_qa_context_approved` / `formal_dev_eval_ready`. Pre-P09 data gate is passed;
P09 may start, but P09 Exit Gate has not been evaluated.

## Pre-P10 DS6–DS8/Security Candidate checkpoint

The deterministic P10 input generator produced DS6 9 scenarios with 24 citation-level judgments,
DS7 12 incremental/writeback scenarios, DS8 20 cold/warm workload templates and 16 bounded
Security/Fault controls. DS6 status counts are valid 5, migrated 11, needs-review 6 and invalid 2.
The DS7 Verified Content samples are mechanical assemblies of Approved Dev Gold only, distributed
DOCX/PDF 7/3. No new course fact, Provider output or P10 prediction was used as Gold.

Seven semantic variants are derived from the two Primary documents, and eight binary Security
controls are explicitly non-semantic. Every fixture is non-searchable; parent and variant remain
mutually exclusive. Repeated generation reproduces Candidate, fixture, Split, review set and
Bundle identities. DS8 stores only the existing Dev/Test Split hashes, resolves Dev count 60 and
keeps Test count zero until a separately approved future Test lock.

Exact Bundle SHA-256 is
`5b6d756a39c988f952536ec93d2aa23b9c593908c3ea24c6af6816cff92b6702`. The offline first review
contains all 57 records; the blinded risk-layered second review contains 29. Review UI v2 replaces
the initial JSON-first cards: DS7 now exposes the complete impact/reuse matrix and enrichment
probes, DS8 exposes workload/cache/Test-isolation contracts, and Security exposes expected side
effects plus pass/return conditions. The complete JSON remains available only for traceability.
The Course Owner explicitly reported that both review rounds passed with no requested change and
intentionally omitted the browser JSON exports. Two audit artifacts preserve that verbatim
conversation statement (SHA-256 `876279be...`) and the complete 57/29 all-pass sets, independently
bound to Bundle `5b6d756a...`. The owner then supplied the required exact approval phrase. Approval
batch `.002` promoted 57 records; exact replay reproduced Approval Manifest `a3886277...` and the
four Approved hashes without duplicate `.002` log entries. The earlier invalid `.001` attempt
remains explicitly quarantined and does not authorize Gold. Test remains `locked=false`; no P10
implementation, Dev calibration, external call or formal Test was performed.

Two complete generations are byte-identical. The focused suite reports 5 passed; the full suite
reports 510 passed and five existing gated skips. All 69 Schemas match, Ruff reports 466 files
formatted plus zero lint errors, Mypy reports zero issues across 317 source files, and
`git diff --check` has no whitespace errors beyond existing LF/CRLF notices.

## P10 Dev calibration and freeze checkpoint

The Course Owner authorized the exact 12-case Dev Protocol with canonical SHA-256
`0dd9ff64ba94b9a0f6e3389565b17eb7e88d1ffd63b19e0e58775f7e6f462696`. The runner executed only
the 12 preregistered Approved Dev cases, reused the other 42 main results by Hash, did not rerun
retrieval, resolved no Test ID, and consumed 86,042 of 180,000 authorized DeepSeek tokens and zero
Cohere Search Units. All QA automatic gates passed: zero false answers, invalid citations, QA
failures and silent fallbacks; citation resolvability, claim-citation completeness and
unanswerable recall are 1.0; Factoid Token F1 is 0.441279, above the fixed 0.406108 floor; both List
cases answered with cited items. `list_set_f1=0.0` remains an explicit L3 diagnostic and was not
used to relax or replace the preregistered list contract.

The independent local Component Dev run used only the Approved Dev splits and made zero Provider
calls. DS6 Citation Migration is 15/15 (1.0) with zero stale citations; DS7 Change Coverage and
eligible Artifact Reuse are both 1.0 with zero missed changes; all ten Security/Fault controls
pass with zero database, artifact and external-call side effects. Component Report SHA-256 is
`ca5c0f4db2c60684460329b24a58af401b0b58a5338093a26c1aa758b3bdcf1a`.

The combined v2 Frozen Manifest binds the authorized Protocol, QA Report/Gate, Component Report,
usage audit, final workspace, approved Bundle, Profile and Test-ID file Hash while preserving
`test_access=false` and `fallback_count=0`. Its exact file SHA-256 is
`f90f4f1bf6a363106ee1185beb1274b1f914168a6de05f29ee22474b0bc0b019`. This is an
awaiting-owner-lock candidate only: Test remains unlocked and unexecuted, and P10/P11 remain
blocked until the owner separately approves this exact Manifest, formal Test data transmission
scope and Provider budgets.

## Pre-P11 Foundation input Draft checkpoint

The P11 foundation input pipeline now defines the complete 40-record contract target: one
Foundation Manifest, nine built-in Template Contracts, twelve Fake-Provider Model Gateway cases
and eighteen Runtime/Compatibility cases. Because the locked P10 formal Test ended in the L0
prompt-injection marking failure, only the 37 P10-independent records were materialized under
`datasets/coursepilot_eval/v1/drafts/p11/`. The three CourseRAG Port/Context cases remain explicit
missing IDs. No Candidate, review UI, Bundle SHA-256, approval, formal CP Gold, Dev/Test entry or
Test lock was generated.

At this checkpoint the Draft compiler audited P10 on every run and failed closed unless the formal
Exit Gate was passed and the authorization, Test lock, final runs, Frozen Manifest and CourseRAG
Port identities remained resolvable. Two generations were byte-identical. Evaluation-only Schemas
covered Draft, full Candidate, two review passes, work-package approval and the post-P11 Runtime
Foundation Snapshot; the legacy CP-DS0 Schema remained backward compatible while rejecting
invented future runtime Hashes. P11 was `not_started` and `blocked_by_P10` at that checkpoint;
P10-D013 later supersedes only this dependency conclusion, not the Draft evidence or guards.

### Pre-P11 P10-D013 Candidate completion

The pre-P11 compiler now validates the exact owner-approved P10-D013 dependency waiver instead of
claiming the rejected P10.3 Profile passed. It binds failed report `26e5eb98...`, the empty/unread
Blind commitment, `candidate_rejected_default_off`, the unchanged `legacy_rules` runtime default,
the original Frozen Manifest/Test identity, the CourseRAG consumer Port and eight inherited
Context/tool/ACL/Secret/audit constraints. All checks pass.

The three deferred CourseRAG records were added using only the two preregistered Approved Dev Query
IDs plus one content-free structural failure fixture. The complete Candidate is now 40 records with
exact `1/9/12/18` distribution. Candidate SHA-256 is `357a9c0d...`; the exact Bundle SHA-256 is
recorded in the Candidate Manifest and phase report. Two generations reproduce Candidate, Manifest
and both review pages byte-for-byte.
The Course Owner completed the 40-record first review and fixed 27-record blind second review with
zero returns, then approved exact Bundle
`ed28509cfbfdba2c530b91b63fa879f1dd50700bd8b4ca4858c271838fb25522`. Approved work-package SHA-256
is `357a9c0d242bd28c9c574086ace6c7a93383643f497364e728a0f2af9eebe3dd`; Approval SHA-256 is
`09b2525848469d219590c373095415dc454de7d37590aeb2ab68990dce4fc234`. P11 input status is now
`approved_for_implementation` while P11 execution remains `not_started`. This approval does not
promote formal CP Gold: Dev/Test remain empty, Test remains unlocked and
`gold_status=skeleton_no_formal_gold`.

## P10.1 Security Gate repair checkpoint

| Task | Status | Evidence |
|---|---|---|
| P10.1-T01 | completed | parsed/OCR-text Scanner, locatable Finding, Warning propagation and stable identity tests pass |
| P10.1-T02 | completed_blind_consumed_gate_failed | Bundle `7394dfd4...` and both 12/12-pass reviews were owner-approved/locked; the one permitted run produced TP=1, FN=7, FP=3, TN=1 and Report `f07fc7c8...` |
| P10.1-T03 | completed | 23 lifecycle failures eliminated with pre-lock/locked/consumed fixtures; formal Lock unchanged |
| P10.1-T04 | completed | ten Approved DS8 offline templates pass in five process-isolated Cold/Warm pairs |
| P10.1-T05 | completed_profile_freeze_approved | semantic equivalence and immutable P10 bindings pass; Candidate `ffe8f582...` is owner-approved, while the separate Blind Bundle is still pending |

The repair moves prompt-injection detection from raw PDF/DOCX bytes to parsed and OCR-merged
Block text. The versioned scanner normalizes Unicode/zero-width/whitespace variants and detects
five behavior-intent families in Chinese and English. Findings retain page, Block and character
spans; source text is preserved and the warning propagates to Evidence and Chunk metadata. The
full Evidence Artifact hash remains audit-sensitive, while the Chunk identity projection excludes
only the new non-semantic warning. On both real sample documents, 4,852 Blocks, 1,848 Evidence
records and 1,048 Child Chunks preserve exact text, source identity, Evidence/Chunk IDs and corpus
mapping.

The new 30-case Dev set passes with 20/20 positive recall and 0/10 hard-negative false positives.
The exposed P10 control is retained only as a regression sentinel. The independent 12-case Blind
Test remains a hash-only commitment with no visible content; the runner refuses before reading a
Bundle unless an exact Course Owner-approved Manifest and lock are present.

Test lifecycle isolation replaces repository-global `locked=false` assumptions with explicit
pre-lock and locked fixtures. The evaluation suite moved from 23 historical failures to 196 passed
and one gated skip without changing Test Lock `06c6473e...` or the consumed Component/Retrieval/QA
reports. The full repository suite reports 563 passed and five gated skips; B0 sample Smoke,
Ruff, Mypy and Alembic head `0015_incremental_writeback_security` pass.

Approved DS8 offline execution completed all ten Cold/Warm templates in five process-isolated
pairs. Warm Stage Reuse is 5/5 and external Provider calls are zero. Cold means are 58.114 seconds
for Full Build, 8.986 seconds for a single document, 0.008 seconds for a Section update,
924.868 seconds for a 15-page OCR batch and 0.008 seconds for Enrichment orchestration. OCR's
per-page process/model initialization is recorded as an L2/L3 performance debt; it does not relax
security or start a tuning loop.

At the P10.1 checkpoint the repair was incomplete: P10 remained blocked at the new independent
blind-test checkpoint, and P11 was `not_started / blocked_by_P10`. The original formal 40-case
Retrieval/QA Test was not rerun and no Cohere/DeepSeek call occurred. P10-D013 later changes only
the cross-phase dependency treatment; the failed Blind verdict remains immutable.

## P10.2 semantic Prompt Guard upgrade checkpoint

| Task | Status | Evidence |
|---|---|---|
| P10.2-T01 | completed | model-independent Detector/Score/Window/Finding contracts and fail-closed policy tests pass |
| P10.2-T02 | completed | 448-token/128-overlap cross-Block windows preserve reversible Page/Block/character mapping |
| P10.2-T03 | completed_candidate_runtimes | ProtectAI, HikmaAI and the owner-risk-accepted ModelScope `LLM-Research/Llama-Prompt-Guard-2-86M@be11c20d...` snapshots are stored outside Git with fixed identities. The ModelScope Manifest file/canonical/Bundle SHA-256 values are `292cede1...`/`fc27f708...`/`ca7df59c...`; its CUDA FP16 smoke passes on RTX 4060, but its `USER_UPLOAD` provenance remains explicitly non-official |
| P10.2-T04 | completed | regex rules are auxiliary only and cannot independently mark; model-high and model/rule-consensus paths are separate |
| P10.2-T05 | completed | `security_annotation` is independent from Parser/OCR fingerprints and preserves parser/OCR bundle assets |
| P10.2-T06 | all_three_candidates_failed_no_profile | ProtectAI and HikmaAI remained rejected. The owner separately approved exact ModelScope Meta Protocol `c1be800a...` and one Dev-only qualification. Its single 160-case run failed all six preregistered pairs: best recall was `0.2125` at specificity `0.825`, while the highest-specificity pair had recall/specificity `0.20/0.8875`; tool-coercion recall was `0`. Report SHA-256 is `6946176f...`. No Profile Candidate was emitted, no rerun is permitted and Blind stayed unread |
| P10.2-T07 | pending | new 48-case Blind commitment exists without content; it cannot be constructed or unlocked before Dev/Profile freeze |
| P10.2-T08 | completed_verification_architecture_blocked | P10.2/security专项 24 passed；全量 580 passed/5 skipped；Ruff、Mypy、Alembic head 和 diff check 通过。候选运行时与治理证据完整，但三个模型均未通过冻结发布标准；默认仍为 `legacy_rules`，继续工作需另行批准新的安全分类架构 |

The default provider remains `legacy_rules`; the failed P10.1 Profile is not presented as a passed
security boundary. At this checkpoint P10/P11 remained blocked. No P10.1 Blind content was read or reused, no formal
40-case semantic Test was rerun, and no Cohere/DeepSeek or external safety API call occurred.

The ModelScope run used approved Protocol `c1be800a5807d679d6b13ef41fe296f52cfac430cb59b851197e11da12eeaf8f`
exactly once. It read the same owner-approved Dev labels, made zero external calls and did not read
Blind. The failure is not a missing threshold: all six fixed pairs cluster at only `0.20-0.2125`
recall. Category recall at a representative best-recall pair is policy override `0.25`, role
impersonation `0.125`, secret extraction `0.125`, tool coercion `0`, and obfuscation `0.5625`.
This demonstrates a contract mismatch between a narrow prompt-override classifier and the broader
five-family untrusted-instruction L0 obligation. Repeating model swaps or threshold search on this
consumed Dev set is prohibited.

## P10.3 multi-axis security architecture checkpoint

| Task | Status | Evidence |
|---|---|---|
| P10.3-T01 | completed | explicit threat-axis signal and detector contracts; HikmaAI is the required general semantic axis |
| P10.3-T02 | completed | role, secret and tool composite axes require action + protected target + effect; Context Guard separates quoted/educational text |
| P10.3-T03 | completed | obfuscation is a non-decision modifier; high-confidence union replaces majority voting |
| P10.3-T04 | completed_candidate | Llama Prompt Guard 2 is an explicit policy-override challenger with a pre-registered retain/drop ablation |
| P10.3-T05 | completed_candidate | isolated security annotation Stage records axis/signal/decision path and fails closed for required-axis faults |
| P10.3-T06 | completed_owner_attested_approved | Course Owner explicitly attested both completed review passes were 120/120 PASS after the browser exporter failed; recovered review Hashes `b6e5d2ce...`/`4817e358...` bind Candidate `b3ef6753...`, and Approval `dcef3ebe...` covers all ordered IDs |
| P10.3-T07 | not_run_dev_gate_failed | independent 48-case Blind commitment `c3f662d0...` remains empty and unread because Dev did not freeze a Profile |
| P10.3-T08 | qualification_failed_no_profile | exact Protocol `91f51be0...` ran once: Report `26e5eb98...`; Recall `0.95`, Specificity `0.7333`; baseline without Llama is `0.95/0.80`; no Profile Candidate was emitted |

P10.3 addresses P10.2's contract mismatch rather than performing a fourth model-swap or threshold
loop. One broad classifier no longer owns all five threat families. HikmaAI covers general semantic
risk; deterministic composite axes cover role impersonation, secret extraction and tool coercion;
obfuscation only raises diagnostic evidence; and Llama Prompt Guard 2 must prove unique value with
zero added false positives before it can remain in a release Profile. Any high-confidence required
axis can mark a finding. Missing model/runtime/Profile identity fails closed.

The Candidate labels and exact Qualification Protocol `91f51be0...` were owner-approved. The
Protocol ran exactly once and produced failed Report `26e5eb98...`; no release Profile exists.
The consumed P10.1/P10.2 Dev and Blind artifacts remain immutable and were not selection inputs.
The original formal Retrieval/QA Test was not rerun, no external Provider was called, Blind/Test
access and Fallback remained zero, and runtime default remains `legacy_rules`. The component-level
Security L0/Profile Gate remains failed; P10-D013 later isolates that default-off failure from the
P11 foundation dependency without changing the verdict.

## P10.3 gate-scope adjustment checkpoint

The Course Owner approved separating the rejected P10.3 Profile release Gate from the completed
P10 CourseRAG core contracts so that an isolated, default-off candidate does not indefinitely block
unrelated foundation work. This is an explicit dependency waiver, not a metric waiver:

- Report `26e5eb98...` remains failed and immutable; no Profile was emitted and the consumed Dev
  cannot be rerun or patched into the same release.
- `multi_axis_local` remains candidate-only/default-off and must not be selected implicitly or
  represented as a passed Prompt Injection boundary.
- P11 may start Model Gateway/contract work only if Context remains untrusted data, tool execution
  is default-deny, system/developer instructions cannot be overridden by retrieved content, and
  ACL/Secret isolation/audit controls remain active.
- P11 planning must treat its existing `P10 fully green` Draft/Candidate compiler guard as the
  first governance adaptation: replace only the dependency predicate with an exact P10-D013 waiver
  check while preserving formal Test/Gold isolation, deferred-record provenance and fail-closed
  behavior. That is P11 work and is not implemented by this P10 documentation adjustment.
- P14-P16 may consume only the frozen CourseRAG Port contracts; they must not depend on P10.3
  findings for authorization or safe side effects.
- P17 must resolve or replace this detector debt with a new owner-approved Dev/Blind release, and
  P18 cannot pass the system Security L0 Gate while the debt remains open.

Accordingly P10 is `completed_with_isolated_security_capability_debt` and P11 is
`ready_to_start`. The original formal Test, Test Lock, Profiles, runtime defaults, database,
public API and indexes are unchanged.

## P15 exam workflow implementation checkpoint

P15 implementation is complete but its real-provider gate is failed. Strict Exam Blueprint/Slot/Batch/Question/Artifact contracts, bounded
Fan-out/Fan-in orchestration, deterministic duplicate and answer-leakage checks, question-scoped
RepairPlan generation, versioned four-role DOCX export, and additive exam export/writeback routes
are implemented behind `COURSEPILOT_EXAM_V2_ENABLED=false`. The approved CP-DS2 input bundle is
reused without constructing new Gold/Test data. Offline preflight estimates 34 requests, 160k
input tokens, 220k output/thinking tokens and CNY 0.60 within the approved CNY 0.80 cap.
Focused P15 and upstream Validation/Repair tests pass. The later owner-authorized real Provider
Smoke/Pilot is recorded in the checkpoint below; its usage stayed within the hard cap, but global
duplicate/answer-leakage checks and one structured-output failure keep the final Exit Gate failed.
## P15 real Provider Smoke/Pilot checkpoint

The owner-authorized Smoke/Pilot was executed once with the approved hard caps (CNY 0.80,
200,000 input tokens, 300,000 output/thinking tokens, 34 provider requests). The durable
checkpoint and consolidated report are under `storage_eval/p15_provider_smoke/`. Actual usage
was 32 provider requests, 64,436 input tokens, 59,794 output tokens and an actual-usage cost
estimate of CNY 0.184024; no fallback, model switch, retry, Test access or Gold promotion occurred.

The gate is not passed: the Smoke/P3 path reported duplicate questions and cross-answer leakage;
P0/P1 reported answer leakage; P2 reported duplicate questions; and one P3 pressure-case request
returned a structured-parse failure after the Provider had supplied usage (request hash
`fb17dd665ef3ed1f607bf7772648ece6632d358b32394a6658d4e593b677c84b`, billing status
`unknown_pending_reconciliation`). The request was not retried and no fallback was used. P15
therefore remains `gate_failed_quality_and_provider`; P16 is blocked pending offline repair and a
separately authorized follow-up, with the remaining two request slots not consumed automatically.

## P16 pre-data checkpoint

The renderer-backed P16 r2 CP-DS3/CP-DS7 Pilot candidates are generated from the owner-reviewed
P14 Lesson artifacts and Approved CourseRAG DS2/DS3/P05 records. The bundle contains 3 decks with
exactly 46 slide targets (24/12/10), 4 template positives (three built-in roles and the pinned
CC0 Velis template) and 2 contract negatives. Candidate hashes are
`7001ec09dcf7ca782fadb2468a39fb5b0a51b81dc8be35d8f14e4d57bdd5b039` and
`ef6ec83bba30a1ddb02bc93437421034eaab87acbc5b6e54dc4fa316d02fccb9`; Bundle hash is
`e8fa261a4bc8066432072255f18ed7e4fb3d607eeee74ffde29b840e212f4f91`.

The external source is `lrkrol/powerpoint` commit
`0f18f3f1fe2d76413c45b0106e7585d64beb920d`, CC0, with source SHA
`54f58da18846a40976c2b2aa13950343d4b24d112b5a0b64f1f8efbe251dcbcd`. Because the public npm
registry does not contain `@oai/artifact-tool`, the Course Owner authorized PowerPoint 2021 COM
automation for the editable Velis smoke. The frozen Docker renderer remains LibreOffice 7.4.7.2:
all 17 pages reproduced byte-identical PNG hashes across two passes. The new review package exposes
55 first-pass and 23 blind second-pass decisions, all evidence text and 17 previews, and validated
local autosave/export. At Candidate generation time no Approved P16 files were written; exact owner
review and approval were still required.

The Course Owner subsequently supplied the exact 55-record first-pass and 23-record blind
second-pass exports; both were complete and all PASS. Exact Bundle
`e8fa261a4bc8066432072255f18ed7e4fb3d607eeee74ffde29b840e212f4f91` was approved as P16 Pilot
input. Final approval artifact SHA is `e9017dd61a02843750036d2112515c8c47e93f36fcc764b17f5d8a9e6eda6d58`;
Approved CP-DS3/CP-DS7 dataset hashes are `19869521...` and `2e923d29...`. Two superseded approval
artifacts retain the pre-validation record-hash/review-ID corrections for audit. This makes P16 formal
evaluation input ready but does not pass the P16 Exit Gate or approve generated slide quality.

## P17 implementation checkpoint

P17 implementation has started with the approved 1A dual-process boundary and 2A
scope-first security decision. RemoteCourseRAGClient now supports explicit bearer
authentication, deadlines, classified bounded retries, idempotency-aware retry rules,
query parameters for reads and structured transport errors. CoursePilot runtime selection
supports explicit local/remote/mock modes and never falls back from remote to local.
Context bindings now retain retrieval trace, verified overlay/snapshot identity and per-
Evidence content hashes. The PPT workflow no longer builds the same Context package twice.
CourseRAG exposes Health/Capabilities and enrichment status routes; the enrichment worker
claims leased items idempotently and records completion without inventing KP assets.
The security ensemble includes an opt-in scope-aware action/target/effect consensus mode;
legacy union profiles remain compatible and default-off.

Focused contracts, security and writeback tests: 66 passed. Full system Pilot, independent
Security Qualification Dev/Blind release, and final Exit Gate remain pending.

P17 follow-up implementation checkpoint

P17-T01 HTTP boundary completion is in place for the local/contract scope: document/build,
evidence, health/capabilities, enrichment status and context-binding validation routes are
mounted; RemoteCourseRAGClient calls the binding endpoint with bearer, principal, request and
trace identity. Evidence responses resolve persisted document-version IDs/source tiers where
available. Trace/version and writeback-loop focused validation passed 62 tests; the broader
affected contract/security/writeback/runtime set passed 108 tests. No external provider, Blind
data, migration or commit was used. SYS-DS1, 34 fault/security variants and the independent
security release remain pending, so P17 is not yet completed and P18 remains blocked.
