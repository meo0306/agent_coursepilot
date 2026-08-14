# P11 CoursePilot Runtime, Template and Model Gateway Phase Report

- Phase: P11
- Starting commit: `2e1a6bef2c763a88772ccd1b3af6d9d7b041bc09`
- Foundation input Bundle: `ed28509cfbfdba2c530b91b63fa879f1dd50700bd8b4ca4858c271838fb25522`
- Runtime Snapshot status: candidate pending Course Owner approval

## Outcome

P11 established the CoursePilot runtime foundation without replacing the Lesson, Exam or PPT
Graphs. Legacy requests keep their public wire contracts and now mirror successful work into
stable Thread, Template Snapshot, Workflow Run, immutable Artifact Version, Node Run and Model
Invocation facts. New runtime modules depend on the CourseRAG consumer Port only; an AST boundary
test prohibits Parser, Chunker, Index, persistence, Chroma and legacy RAG imports.

The capability-aware Model Gateway contains six logical Main/Light Profiles. Main and Light may
resolve to the same configured model today without losing logical identity, and may be split later
through configuration. Reasoning and Thinking fields are sent only when the selected Capability
Manifest explicitly supports them. Tool requests are always denied in P11, evaluation capability
failures are fail-closed, and runtime faults do not trigger model switching. Estimated legacy usage
is not written as known provider usage or cost.

The Template Registry pins nine logical templates and five editable resources. Two A4 DOCX
skeletons were generated with real Word styles and editable placeholders. Three PPTX roles use the
existing editable B0 master/layout deck as a neutral compatibility skeleton. Structural open/edit
tests pass for all five resources. Visual rendering could not be completed because the managed
document renderer lacks `pdf2image`/LibreOffice and the required Artifact Tool Node execution was
denied by the platform approval service after its usage limit was reached. This is a template
visual-quality debt, not an API/runtime contract failure; P16 remains responsible for final visual
quality.

## Task results

| Task | Result | Evidence |
|---|---|---|
| P11-T01 | completed | ContextResolver uses `CourseRAGServicePort`; import-boundary and fail-closed identity tests pass |
| P11-T02 | completed | BusinessTask, ArtifactRef/Version, NodeResult, CommonGraphState and RunContext implemented |
| P11-T03 | completed | seven runtime fact tables, task extensions and reversible 0016 migration implemented |
| P11-T04 | completed_with_visual_qa_debt | nine definitions, Registry/Snapshot and five editable resources implemented; structural QA 5/5 |
| P11-T05 | completed | six profiles, capability-aware route, prompt/resource/profile Hash and invocation facts implemented |
| P11-T06 | completed | unsupported fields omitted; tool/default model switch prohibited; evaluation fails closed |
| P11-T07 | completed | ContextPackageRef, input fingerprint, safe node reuse and bounded State Compaction implemented |
| P11-T08 | completed | legacy service responses/routes remain compatible while runtime facts are mirrored |

## Database, API and configuration

- Alembic head is `0016_coursepilot_runtime_foundation`.
- Migration is additive and passed `0015 → 0016 → 0015 → 0016`.
- Public CoursePilot route count remains 27; no public request/response field was removed or renamed.
- New configuration covers Template Registry, six model Profiles, Capability Manifest, gateway mode,
  independent Main/Light provider settings and compatibility recording. Example Secret values are
  empty. Blank Main inherits `COMPATIBLE_*`; blank Light inherits Main.
- Legacy rows are not assigned invented historic Snapshot/Prompt/Model facts.

## Verification

- `uv sync --frozen`: passed, 182 packages checked.
- P11 focused API/Graph/runtime/template/gateway/eval/migration suite: 52 passed.
- Additional runtime/gateway/template/schema suite: 26 passed.
- Full `uv run pytest -q`: 631 passed, 6 skipped.
- Gated owner sample B0 smoke: 1 passed.
- `uv run ruff format --check`: 577 files formatted.
- `uv run ruff check`: passed.
- `uv run mypy src/`: 390 source files, no issues.
- `uv run python -m alembic heads`: one head, `0016_coursepilot_runtime_foundation`.
- `git diff --check`: passed; only repository CRLF conversion notices.
- External Provider calls and token cost: 0.

## Metrics and gates

| Metric | Result |
|---|---|
| Approved Foundation Contract | 40/40 |
| Template Snapshot reproducibility | 1.0 |
| Fake Profile route accuracy | 1.0 (6/6) |
| Runtime Trace fact coverage | 1.0 for mirrored successful workflows |
| Secret leakage | 0 |
| Silent model switch/fallback | 0 in Model Gateway |
| Legacy API route regression | 0 |
| Physical resource structural open/edit | 5/5 |
| Physical resource render QA | blocked by local renderer/runtime environment |

The three P11 Exit Gate capabilities are implemented: tasks trace to Template/Prompt/Model/Artifact
versions; Main/Light support same or distinct models; existing API routes and Graph smoke remain
operational. Per the approved plan, the phase remains
`gate_pending_owner_snapshot_approval` until the Course Owner approves the exact Runtime Foundation
Snapshot Candidate SHA-256. P12 therefore remains blocked only by that approval checkpoint.

## Risk and rollback

- P10.3 remains `candidate_rejected_default_off`; P11 does not use detector output as authorization.
  Context stays untrusted, tools are denied, Secret material is excluded from State and Trace, and
  full audit identity is retained.
- Disable `COURSEPILOT_RUNTIME_COMPATIBILITY_RECORDING` to stop future mirroring; legacy services
  remain available. Existing audit/version facts are retained.
- Before downgrading 0016, stop P11 writes and export runtime facts. Downgrade removes P11 audit
  tables but leaves the pre-P11 business tables and public API intact.
- Final DOCX/PPTX visual polish and render quality are intentionally not claimed in P11 and remain
  P16 work. The local rendering blocker should be resolved before P16 starts.
