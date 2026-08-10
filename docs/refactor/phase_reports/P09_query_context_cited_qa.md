# P09 Query Processing, Context Packing and Cited QA Report

## Phase verdict

- Implementation: P09-T01 through P09-T08 are implemented within the approved boundary.
- Exit Gate: **technically satisfied, governance pending**. Query steps are independently
  ablatable; all Q3 answered Claims bind to valid Context Evidence; all 6/6 main-Dev unanswerable
  cases abstain. Exact Freeze Candidate owner approval is still required, so P09 remains
  `implementation_complete_freeze_pending` and P10 remains blocked.
- Start/end Git commit: `b6483f5ae8a0b3c3e45858c3872b4ed86e94502d` / uncommitted at the
  same commit; branch `refactor/p00-baseline`.
- Scope protection: no commit, push, PR, Test access/lock, Gold rewrite, P10 implementation,
  public CoursePilot API behavior change, open-network search or LLM-as-a-Judge.

## Task results

| Task | Result | Evidence |
|---|---|---|
| P09-T01 | completed | seven-step Query Pipeline, independent intent/strategy axes, bounded Multi-query and one Low-recall Retry |
| P09-T02 | completed | per-step toggle/hash/timing/status Trace plus immutable raw/current query and filter preservation |
| P09-T03 | completed | cross-query RRF, stable Evidence deduplication and persisted-relation Parent/Neighbor expansion |
| P09-T04 | completed | fixed Tokenizer identity, 8-item/4,000-token packing, Citation Map and Packing Report |
| P09-T05 | completed | deterministic Sufficiency Gate, structured Claim-Evidence output and programmatic Citation composer |
| P09-T06 | completed_with_measured_failure | invalid IDs/status/schema fail closed with one Repair; Q3 retains one visible repair failure |
| P09-T07 | completed_freeze_candidate_pending | Approved-Dev-only B6-B8/Q0-Q3 report and exact pending Candidate generated |
| P09-T08 | completed | Search/Context/QA v1 routes, additive contracts and explicit Versioned Runtime; Legacy behavior retained |

## Changed files

- Query/Context/QA: `src/courserag/query/`, `src/courserag/context/`,
  `src/courserag/qa/`, `src/courserag/infrastructure/query_provider.py`,
  `src/courserag/infrastructure/qa_provider.py`.
- Contracts/API/runtime: `src/courserag/contracts/retrieval.py`,
  `src/courserag/contracts/qa.py`, `src/courserag/api/retrieval_qa.py`,
  `src/courserag/api/__init__.py`, `src/service/service.py`,
  `src/coursepilot/adapters/local_courserag.py`,
  `src/coursepilot/services/courserag_runtime.py`.
- Persistence/migration: `src/courserag/persistence/models/run.py`,
  `src/courserag/persistence/repositories.py`,
  `alembic/versions/2026_08_07_0014-query-context-cited-qa.py`.
- Configuration/resources: `src/core/settings.py`, `.env.example`,
  `resources/query_profiles/`, `resources/context_profiles/`, `resources/qa_profiles/`.
- Evaluation: `src/courserag/evals/p09_metrics.py`,
  `src/evaluation/p09_dev_loader.py`, `src/evaluation/p09_corpus.py`,
  `src/evaluation/p09_systems.py`, `src/evaluation/p09_retrieval_qa_eval.py`.
- Tests: P09 Query/Context/QA, contract, migration, API/runtime and evaluation suites, plus the
  P03 revision-boundary assertion updated to exclude P09 tables/columns.

## Database, API and configuration

Revision `0014_query_context_qa` additively extends QueryProcessingRun and QARun, creates
ContextPackage, and adds stable external Claim identity/validation status. Existing P08 rows remain
readable; legacy columns are nullable where no honest backfill exists. A real PostgreSQL 16 tmpfs
database passed `base -> 0013 -> 0014 -> 0013 -> 0014`; the isolated container and network were
removed afterward. Downgrade deletes P09 facts and is therefore an explicit operator action only.

Stable v1 Search, Context and QA routes are mounted with additive defaulted fields. Versioned mode
fails closed without Active Index/Profile/Provider; default `legacy` behavior and old
`/api/coursepilot/*` endpoints are unchanged. DeepSeek thinking is disabled only through the
explicit `deepseek_v4` capability. Secrets remain blank in `.env.example` and only ignored `.env`
values are read at runtime.

## Formal Approved-Dev evaluation

- Approved Bundle SHA-256:
  `5a84bac041375310d5bb80f17f7481464d07dbcf75f9f980c6b8a030e58af0c1`.
- Final report: `storage_eval/p09_query_context_qa/run-1/report.json`, SHA-256
  `8cf07e7026a58a8750ff455101440b9338f7713b9a51ed28dc52ad59b2f7f197`.
- Freeze Candidate: `storage_eval/p09_query_context_qa/freeze_candidate.json`, SHA-256
  `c88d7ffe2386e0c41fe393becf6f47809bc983ffee2a7e683378e42165169c3d`.
- Superseded pre-contract-fix report/candidate remain retained with SHA-256 `c12cde74...` and
  `e2ceabda...`; neither is eligible for approval.
- Exactly 60 Dev cases were loaded: 54 `retrieval_main` and 6
  `upstream_gap_diagnostic`. Test remained unlocked and unread.

| System | Evidence coverage | Complete-group coverage | Citation P/R | False abstention | Unanswerable recall | QA failure |
|---|---:|---:|---:|---:|---:|---:|
| B6 | 0.7870 | 0.7500 | n/a | n/a | n/a | n/a |
| B7 | 0.7963 | 0.7685 | n/a | n/a | n/a | n/a |
| B8 | 0.7130 | 0.6759 | n/a | n/a | n/a | n/a |
| Q0 plain/no-refusal | 0.5741 | 0.5093 | 0 / 0 | 0 | 0 | 0 |
| Q1 | 0.7870 | 0.7500 | 0.7301 / 0.8617 | 0.0208 | 1.0 | 0 |
| Q2 | 0.7130 | 0.6759 | 0.7464 / 0.8370 | 0.0417 | 1.0 | 0 |
| Q3 | 0.7037 | 0.6574 | 0.7259 / 0.8333 | 0.0625 | 1.0 | 0.0185 |

Q3 produced 49 answered, 10 abstained and 1 failed result over all 60 Dev cases. Every answered
Claim has at least one Context Evidence ID, and both Claim citation completeness and Citation
resolvability are 1.0. All six main-Dev unanswerable cases abstained; false-answer rate is 0.
Intent accuracy is only 0.3958, and B8 coverage regresses from B7; both remain visible candidate
quality risks rather than being tuned against Test.

Cohere reached the approved 180 Search Unit hard boundary across initial/resumed retrieval work and
was not called during the final QA-only resumes. Final per-system reports use incremental or
cumulative-aware Usage. Across superseded and final QA attempts, a conservative Context-based
upper bound is below 1.77M DeepSeek tokens, below the approved 2.5M limit. No automatic payment,
budget expansion or silent fallback occurred.

## Verification

| Command/check | Result |
|---|---|
| `uv sync --frozen` | passed for the base environment; optional local CUDA Embedding packages are intentionally extra-only |
| P09 Query/Context/QA/Migration focused | 15 passed |
| Contracts + P09 metrics/Runner/data guard | 40 passed |
| owner PDF/DOCX B0 Smoke | 1 passed |
| final full `uv run pytest -q` | 475 passed, 5 gated skips, 6 dependency warnings |
| `uv run ruff format --check` | 450 files already formatted |
| `uv run ruff check` | passed |
| `uv run mypy src/` | 0 errors in 308 source files |
| `uv run python -m alembic heads` | `0014_query_context_qa (head)` |
| real PostgreSQL migration | `0013 -> 0014 -> 0013 -> 0014` passed |
| `git diff --check` | passed; Windows LF/CRLF notices only |
| fallback/data boundary | zero formal fallback; Approved Dev only; Test/Gold labels excluded from Provider payloads |

## Risks and rollback

- One Q3 result remains failed after the single allowed Repair; it emits no partial answer.
- B8 packing loses coverage relative to B7, and the heuristic intent Router is low-accuracy. These
  are freeze-quality risks, not hidden implementation success criteria.
- Roll back runtime by disabling Query/QA Providers or selecting the unchanged Legacy backend.
  P08 Active Index, legacy Chroma, Approved Gold and P09 reports remain retained.
- Downgrade 0014 only after writes stop and Context/QA audit facts are exported.
- A future real local-Embedding rerun must use `uv sync --frozen --extra
  local-embedding-cu126`; the base environment intentionally omits this optional GPU stack.

## Exit Gate

| Gate | Result | Evidence |
|---|---|---|
| Every Query Processing item is independently ablatable | passed | toggle/unit tests and explicit `skipped_disabled` traces |
| Every answered QA Claim binds valid Evidence | passed | Q3 Claim completeness and Citation resolvability both 1.0; invalid IDs fail closed |
| Unanswerable samples abstain correctly | passed | 6/6 main-Dev unanswerable cases; false-answer rate 0 |
| Owner Profile Freeze | pending | exact Candidate `c88d7ffe...` requires explicit approval |

Overall P09 Gate: **pending owner Freeze approval**. P10 does not yet meet its phase prerequisite.

## Answer Grounding Gate Repair follow-up

The earlier Freeze Candidate is no longer eligible for direct approval after Protocol r2 exposed a
coupled answer-quality miss. The approved joint repair, its exact input identities, local results
and current external-environment blocker are documented in
`phase_reports/P09_answer_grounding_gate_repair.md`. P09 remains pending; P10 is still blocked.
