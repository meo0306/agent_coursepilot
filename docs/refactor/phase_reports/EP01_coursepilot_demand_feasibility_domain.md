# EP-01 CoursePilot Demand and Feasibility Domain

## Status

EP-01 is complete. CoursePilot can deterministically express Lesson, Exam and PPT evidence demand
and map a CoursePilot-local Fake Adequacy snapshot to one of four business feasibility states. The
new domain is not connected to routes, workers or generation Graphs. EP-02 is ready but was not
started.

## Completed tasks

- `EP01-T01`: immutable `ArtifactDemand` with course, Artifact, target quantity, minimum viable
  scope, KP coverage, source and semantic-capacity requirements.
- `EP01-T02`: separate semantic content roles and material modalities through
  `SemanticUnitRequirement`, `SemanticUnitRole` and `MaterialType`.
- `EP01-T03`: explicit CoursePilot `FeasibilityStatus`, action, stable reason codes and validated
  `FeasibilityDecision`.
- `EP01-T04`: deterministic Lesson Demand Builder for sessions, audience, teaching focus,
  definition, example, process and application requirements.
- `EP01-T05`: deterministic Exam Demand Builder for question count, stable largest-remainder
  difficulty allocation, content roles and hard-question semantic capacity.
- `EP01-T06`: deterministic PPT Demand Builder, including the existing default slide-count rule,
  narrative roles and visual-relationship demand.
- `EP01-T07`: pure Feasibility Evaluator with no LLM, Provider, repository or CourseRAG call.
- `EP01-T08`: generate, supplement, reduce-scope and human-review outcomes with conditional
  `unresolvable` mapping.

## Files

New production modules:

- `src/coursepilot/domain/feasibility.py`
- `src/coursepilot/application/feasibility_service.py`

Modified production modules:

- `src/coursepilot/domain/__init__.py`
- `src/coursepilot/domain/runtime.py`
- `src/coursepilot/runtime/state.py`

Tests:

- `tests/coursepilot/feasibility/test_models.py`
- `tests/coursepilot/feasibility/test_service.py`
- `tests/coursepilot/domain/test_runtime_contracts.py`

Governance updates are limited to `EXECUTION_STATUS.md`, `DECISION_LOG.md`, `RISK_REGISTER.md`
and this report.

## API, database and configuration

- Public Lesson/Exam/PPT request and response schemas: unchanged.
- CourseRAG public contracts, CoursePilot Port and Capability negotiation: unchanged.
- Routes, Task Worker, Lesson/Exam/PPT Graphs and Provider behavior: unchanged.
- PostgreSQL, Alembic, indexes, prompts, model profiles and environment configuration: unchanged.
- `TaskStatus`: unchanged; feasibility is a separate domain decision.
- `CommonGraphState` only reserves optional `artifact_demand` and `feasibility_decision` fields;
  no node reads or writes them.
- Provider calls, tokens and cost: zero.

## Demand and Fake Adequacy result

- Lesson, Exam and PPT requests produce byte-stable JSON-equivalent Demand models across repeated
  construction.
- Thin Fake Adequacy with an allowed supplement maps to `needs_more_evidence`.
- A supported reduced quantity at or above the minimum viable size maps to
  `scope_reduction_required`.
- An unsupported minimum size maps to `needs_human_review`.
- Complete rich Fake Adequacy maps to `feasible` and is the only result with
  `generation_allowed=true`.
- An `adequate` label that contradicts deterministic KP, Requirement, Source or semantic counts
  maps to human review rather than generation.
- Low character count is retained as a warning and never changes an otherwise feasible result.

These are domain-contract results, not generated Lesson/Exam/PPT quality claims and not a real
CourseRAG Adequacy evaluation.

## Verification

```text
python -m pytest -q tests/coursepilot/feasibility tests/coursepilot/domain/test_runtime_contracts.py
18 passed

python -m pytest -q tests/coursepilot/feasibility tests/coursepilot/domain/test_runtime_contracts.py tests/coursepilot/runtime/test_context_resolver.py tests/coursepilot/runtime/test_import_boundary.py
22 passed

python -m pytest -q tests/coursepilot/test_lesson_api.py tests/coursepilot/test_exam_api.py tests/coursepilot/test_ppt_api.py
8 passed

python -m pytest -q
collection failed before execution: existing duplicate top-level test_schemas module identity

python -m pytest -q --import-mode=importlib
899 passed, 13 skipped

python -m ruff format --check
781 files already formatted

python -m ruff check
passed

python -m mypy src
passed, 520 source files
```

The default full-suite collection failure is caused by the pre-existing pair
`tests/evals/test_schemas.py` and `tests/evals/system_optimization/test_schemas.py`. No EP-01 file
has that basename. Importlib-mode full execution passes and the issue is recorded as EP01-R02.

## Risks, Exit Gate and rollback

- The balanced ratios are explicit first-version Dev policy, not empirically final thresholds.
  Real calibration remains for EP-02/EP-04 on approved Dev data.
- Public requests cannot yet supply KP/material hints and generation does not consume Decisions;
  this is the intentional EP-01 isolation boundary, not a hidden fallback.
- No P18 Test/Blind data, LLM-as-a-Judge or output-derived Gold was used.

EP-01 Exit Gate: **passed**. `EP01-T01`—`EP01-T08` are complete; focused, API, boundary, full
importlib-mode, Ruff and Mypy verification pass; CourseRAG and current generation behavior are
unchanged. EP-02 has the prerequisite to start, but this report does not start or authorize it.

Rollback removes the two new production modules, their exports, the two optional graph-state
fields, tests and these governance entries. No database or persisted business-data rollback is
required.
