# Decision Log

## P00-D001 — Existing retrieval metrics are not accepted as Gold evidence

- Status: proposed
- Date: 2026-07-23
- Trigger: `run_real_eval.py` constructs expected retrieval identifiers after observing Top-K results.
- Frozen documents affected: 03, 03A, 06, 07
- Options:
  - publish the historical Recall/MRR/nDCG values as B0 quality metrics;
  - discard the historical run entirely;
  - preserve its engineering evidence but label its retrieval quality metrics invalid.
- Minimal safe default: preserve pipeline, latency, fallback, token, database/vector, and export evidence; mark retrieval quality metrics `non_gold_invalid_for_quality_claims`.
- Candidate decision: define source-independent Gold and evidence spans in P02; do not change the legacy runner or invent Gold in P00.
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

## ADR Template

- Status: proposed / accepted / rejected / superseded
- Date:
- Trigger:
- Frozen documents affected:
- Options:
- Decision:
- Compatibility/migration impact:
- Evaluation impact:
