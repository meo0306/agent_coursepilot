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

## ADR Template

- Status: proposed / accepted / rejected / superseded
- Date:
- Trigger:
- Frozen documents affected:
- Options:
- Decision:
- Compatibility/migration impact:
- Evaluation impact:
