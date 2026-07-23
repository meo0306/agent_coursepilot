# P02 Phase Report — Evaluation Data Scaffold and B0 Runner

## Scope and inputs

- Phase: P02 only. No P01 or P03+ implementation was performed.
- Start and current HEAD:
  `e3f4efab0770240752efc5f7f30ff4d69daff2a5`.
- Branch: `refactor/p00-baseline`.
- P00 was `completed/passed` before P02 began.
- The worktree was clean at P02 start; it was rechecked before implementation.
- No commit, push, PR, database migration, destructive operation, real Provider call, or formal
  Test run was performed.
- Local inputs remain one independent DOCX and one independent PDF. Source-derived candidate
  content is stored only under ignored `storage_eval/p02_local_candidates/`.

## Repository audit

- At phase start there was no `datasets/`, `src/courserag/evals/`, neutral formal Runner, or
  `tests/evals/`.
- Existing `src/coursepilot/evals/checkpoint.py` supported a loose/forced Resume path and was
  retained for compatibility; the P02 formal Runner is separate and strict.
- Existing `run_real_eval.py` derives expected legacy Chunk IDs after observing Top-K and is not
  valid for formal retrieval quality. It was not modified.
- Existing CoursePilot metrics covered legacy Chunk-ID regression signals but not Evidence Group,
  Claim/citation, ValidationIssue, Repair, or Recovery definitions from the frozen documents.
- Initial quality baseline: 157 tests passed and 4 skipped; Ruff passed; Mypy reported zero
  errors in 124 source files. Alembic remained at head
  `0007_add_async_task_queue_fields`.

## Implemented task IDs

| Task | Result |
|---|---|
| P02-T01 | Added Pydantic models/directories for CourseRAG DS0—DS8, CoursePilot CP-DS0—CP-DS8 and SYS-DS1; exported 25 versioned Schemas including batch/JSONL human scores, Run Manifest and Test lock |
| P02-T02 | Added candidate/approved trees, review logs, Pilot/Dev/Test split files, explicit approval metadata and retained-candidate/hash linkage validation |
| P02-T03 | Added safe Run Manifest, canonical identity/per-case Hashes, actual dataset Manifest/Split file Hash and identity validation, atomic reports, strict Resume, mandatory dataset root, output-boundary enforcement and persisted-error redaction |
| P02-T04 | Added B0 adapter using source identity plus page/span/text overlap; legacy Chunk ID is trace-only |
| P02-T05 | Added code/tests for Evidence Group, Claim/citation including `irrelevant`, Answer Conciseness, ValidationIssue, Repair Patch and bounded Recovery ratios |
| P02-T06 | Added strict CourseRAG/CoursePilot batch and JSONL human-score contracts, five synthetic candidate-only human-score Pilot records with complete frozen Rubrics, and local-only candidate generation from the owner inputs |
| P02-T07 | Added Test lock flags and a fail-closed Gold leakage/Test tuning guard integrated into the formal Runner |

## Key decisions

- Candidate data and Approved Gold are different physical trees. Approval requires an explicit
  human reviewer, retained candidate, candidate/result Hashes, and matching review-log entry.
- Pilot may contain candidates; Dev/Test accept only Approved records. Current Dev/Test are empty.
- No system output, Top-K result, legacy Chunk ID, or LLM judge may create formal Gold.
- Metrics with an empty denominator return `value=null` and `applicable=false`; they do not report
  a fabricated zero or perfect score.
- Resume identity excludes only `run_id` and `created_at`; changes to data, configuration,
  components, Git, seed, Fallback, or Test lock reject Resume before file mutation. The selected
  dataset `manifest.json` and Split file must also match their recorded SHA-256 and dataset
  identity on first run and Resume.
- The formal Runner accepts one mandatory dataset root under a `datasets/` directory. Checkpoint,
  partial and final reports are rejected anywhere under that directory, and raw exception
  messages are never persisted.
- Secret-key checks reject credentials while allowing legitimate token configuration such as
  `max_answer_tokens` and `token_budget`.
- Human-score records require every frozen Rubric dimension and the type-specific acceptance,
  edit-burden and critical-defect fields. Tracked Pilot scores remain synthetic candidates and
  are not quality evidence.
- The Test lock remains intentionally unlocked until human Approved Gold is available.
- The approved local-candidate option uses the existing parser only, invokes no external model,
  and never writes source text/spans into tracked paths.

## Files changed

- Neutral evaluation infrastructure:
  `src/evaluation/{contracts,datasets,io,manifest,runner,guard,cli,local_candidates,schema_export}.py`.
- CourseRAG evaluation:
  `src/courserag/evals/{schemas,formal_metrics,b0_adapter}.py`.
- CoursePilot formal evaluation:
  `src/coursepilot/evals/{formal_schemas,formal_metrics}.py`.
- Dataset skeleton:
  `datasets/schemas/v1/`,
  `datasets/courserag_eval/v1/`, and
  `datasets/coursepilot_eval/v1/`.
- Tests:
  `tests/evals/`.
- Safe local generation evidence:
  `docs/refactor/baselines/p02/01_local_candidate_generation_summary.json`.
- Governance:
  this report, `EXECUTION_STATUS.md`, `DECISION_LOG.md`, and `RISK_REGISTER.md`.

## API/database/config changes

- Public HTTP/API behavior: unchanged.
- ORM/database schema, Alembic migrations, tables, and Chroma Collections: unchanged.
- Graph nodes, edges, routes, Prompt behavior, Provider behavior, RAG build/search behavior,
  exports, and review writeback: unchanged.
- Runtime environment variables and production Compose configuration: unchanged.
- New configuration contracts are evaluation-only JSON: Run Manifest, dataset manifests,
  split files, review logs, and Test locks.
- Internal CLIs were added for Schema verification, dataset validation, and local-only candidate
  generation; they are not public service endpoints.

## Tests and commands

| Command/check | Result |
|---|---|
| `uv sync --frozen` | passed; 181 packages checked |
| Gate Repair focused Manifest/Schema/metric suite | 27 passed |
| `COURSEPILOT_RUN_P02_LOCAL_CANDIDATES=1` plus `uv run pytest -q tests/evals` | 48 passed |
| `python -m evaluation.schema_export --check` | 25 Schemas verified |
| `python -m evaluation.cli validate-datasets --root datasets` | passed; CourseRAG 5 records, CoursePilot 4 records |
| gated owner-supplied B0 Smoke | 1 passed |
| existing deterministic eval | passed; report Hash unchanged at `2f015e2f...44a35` |
| `uv run pytest -q` | 204 passed, 5 skipped |
| `uv run ruff format --check` | passed; 198 files formatted |
| `uv run ruff check` | passed |
| `uv run mypy src/` | passed; zero errors in 141 source files |

Five warnings in parser-related runs come from existing PyMuPDF SWIG types lacking
`__module__`; no P02 warning or test failure was hidden. The five full-suite skips are explicit
gates, including real/local integration paths.

## Evaluation results

- Versioned JSON Schemas: 25.
- Tracked synthetic Pilot candidates:
  - CourseRAG: 5 records across DS0/DS2/DS4/DS5;
  - CoursePilot: 4 records across CP-DS1/CP-DS4/CP-DS5/CP-DS6.
- Tracked synthetic human-score JSONL Pilot records: 5 candidate-only contract examples
  (2 CourseRAG QA, 3 CoursePilot covering Lesson/Exam/PPT); no human approval or product-quality
  claim.
- Approved Gold: 0.
- Dev/Test records: 0.
- Test locks: 2, both deliberately `locked=false`.
- Local owner-input candidates: 10 total, 5 per independent document.
- Local candidate outputs:
  - DS0 SHA-256:
    `ee1e2446daf904f7945f48d10649cb849e48d54767fc6509ebb2eb438b423865`;
  - DS2 SHA-256:
    `bf9666de55481769ee0feee6ca810cb8020a1ccef76558781a2dbe22838bf330`.
- External model calls: 0.
- Automatic approvals: 0.
- Formal Test/quality score published: no.
- Existing deterministic non-Gold regression report remained byte-reproducible with SHA-256
  `2f015e2f5651ad651ffe8c2e8a105d8fa324d3beba1e11096ced476198144a35`.

## Compatibility and migration

- No client, database, index, or data migration is required.
- Existing legacy checkpoint/eval code and B0 runtime remain available and unchanged.
- New formal outputs are always outside the canonical `datasets/` ancestor; the mandatory
  selected dataset root is identity/Hash validated before any write. Atomic writes use
  temporary siblings and `os.replace`.
- P02 modules can be removed independently without changing product runtime behavior. Dataset
  files are additive and versioned under `v1`.
- There is no downgrade operation because no schema/database mutation occurred.

## Risks and remaining work

- Formal Gold has not been manually approved. This is expected for P02 but prevents formal
  Dev/Test metrics and Test locking.
- Local source redistribution remains unverified. Source text/spans stay ignored and untracked.
- The B0 overlap adapter can produce imperfect mappings; matching is constrained by document
  identity/hash, pages, exact-first matching, explicit coverage, and short-text exact-only rules.
- Historical real-eval retrieval scores remain invalid for quality claims, and historical
  complete-workflow Fallback evidence remains unverified.
- Synthetic Pilot fixtures validate contracts only and must not be described as product quality.
- The formal Runner has at-least-once case execution semantics across a process death after the
  case function returns but before checkpoint persistence. Evaluation cases must remain
  side-effect-free or call idempotent product operations; product-side effect idempotency remains
  assigned to later workflow phases.
- P01 is not started, so P03 cannot start even though its P02 dependency is now satisfied.

## Exit Gate evidence

| Gate item | Result |
|---|---|
| Gold and system output physically separated | pass — candidate/approved trees plus mandatory trusted dataset root and non-bypassable canonical `datasets/` output rejection |
| Runner can interrupt and Resume | pass — successful cases reused, failed cases retried, config/case drift and actual Manifest/Split/identity drift rejected before mutation |
| All phase non-generic metrics have code/tests | pass — Evidence Group, Claim/citation/irrelevant, Answer Conciseness, ValidationIssue, Repair and bounded Recovery ratios |
| Gold leakage and Test tuning guard | pass — unlocked/mismatched/non-Approved Test, tuning, dirty Git and permissive Fallback rejected |
| Human-score JSONL/Pilot contract | pass — five candidate-only records validate all frozen dimensions without claiming human approval |
| Main tests/Lint/Type Check | pass — 204 tests, Ruff, zero-error Mypy |
| Existing B0/deterministic behavior not degraded | pass |
| Secret/temp/destructive migration checks | pass — legal token settings accepted, credential keys rejected and persisted exception text redacted |

**P02 Exit Gate: PASSED.** This Gate establishes trustworthy structure and execution controls;
it does not claim that formal Gold or Test quality results already exist.

## Next-phase readiness

- P01 remains ready and may begin its own Plan/audit process.
- P03 depends on both P01 and P02. Its P02 prerequisite is satisfied, but P03 remains
  `blocked_by_P01`.
- No P01, P03, formal model evaluation, Test locking, or later-stage product implementation was
  started in P02.
