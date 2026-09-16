# P00 Phase Report — Baseline Freeze and Execution Scaffold

## Scope and inputs

- Phase: P00 only; no CourseRAG/Agent business refactor.
- Start and current HEAD: `eb9b3a6aa51348cf1fba0de7a21e5d073761939b`.
- Branch: `refactor/p00-baseline`.
- No commit, push, PR, migration, data deletion, or legacy Collection deletion was performed.
- The starting dirty worktree was preserved. In particular, `.env.example`,
  `src/agents/coursepilot/workflow.mmd`, the frozen documents, and prompt files supplied by the
  owner were not reset or cleaned.
- Local B0 inputs:
  - one independent DOCX, SHA-256
    `c93df4cb4bb533e381647e7591104ff06ecc6a486582d77b3e6d63511428066b`;
  - one independent PDF, SHA-256
    `15344771664d40cf190be7790be3d266eb94a2798a4c2608fcf4d1ffa8fd231d`.

The input binaries remain ignored and `local_only_unverified`; their contents are not included
in reports or committed fixtures.

## Repository audit

- Frozen documents 00—08 plus 03A were verified: 10/10 SHA-256 values match the frozen source
  set.
- Root `AGENTS.md` and `codex_prompts/00_MASTER_EXECUTION_RULES.md` have identical SHA-256
  `41bd569d97f1267c6c4eef79e8c5aebafdcbe7766df36b1177a998af494e250b`.
- Runtime snapshot: 38 service routes, including 27 CoursePilot routes; 11 CoursePilot ORM
  tables; 52 Pydantic schemas; three compiled Graphs; 14 Prompt files.
- Alembic has one head, `0007_add_async_task_queue_fields`.
- The legacy real-eval runner derives expected retrieval identifiers after observing Top-K.
  Historical retrieval scores are therefore not valid Gold evidence.
- Initial full-quality state before P00 implementation:
  - tests: 130 passed, 3 skipped via `python -m pytest`;
  - Ruff: passed;
  - Mypy: eight errors in four existing files.

## Implemented task IDs

| Task | Result |
|---|---|
| P00-T01 | Recorded Git/Python/uv/lock hashes, migration head, env-name inventory, and startup commands |
| P00-T02 | Verified and froze the 00—08/03A execution document manifest |
| P00-T03 | Established execution status, decision log, risk register, and report template |
| P00-T04 | Added and ran isolated DOCX/PDF build/search plus lesson/exam/PPT/export/review smoke |
| P00-T05 | Saved reproducible deterministic B0, corrected historical evidence, and made future real-eval Fallback auditing fail closed |
| P00-T06 | Captured API/ORM/52-Schema/Graph/Prompt hashes and six safe synthetic export samples |
| P00-T07 | Verified MIT License/upstream attribution and recorded the later author-metadata task |

## Key decisions

- Owner-supplied DOCX/PDF files are independent non-Gold inputs, not two formats of one source.
- The B0 runner is local-only: isolated SQLite/Chroma, deterministic generation/knowledge-point
  extraction, hashing embeddings, and no external Provider calls.
- Source-derived queries are used only in memory. Reports store query hashes and lengths, never
  query text.
- Historical real-eval engineering evidence is retained, while its retrieval metrics are
  explicitly invalid for quality claims and its incomplete Fallback coverage is unverified.
- The Pytest-only root path was added so the required exact `uv run pytest -q` command can import
  existing `tests.coursepilot` helpers.
- The agent registry supports the exact Lesson, Exam, and PPT compiled Graph types currently
  registered; each Graph explicitly propagates its State as its input/output contract.

## Files changed

- Governance and reports:
  `docs/refactor/{EXECUTION_STATUS,DECISION_LOG,RISK_REGISTER}.md`,
  `docs/refactor/phase_reports/`, and `docs/refactor/baselines/b0/`.
- B0 implementation:
  `src/coursepilot/evals/{b0_baseline,run_b0_smoke,capture_b0_interfaces}.py`.
- B0 tests:
  `tests/coursepilot/test_b0_*.py`.
- P00 acceptance repair:
  `src/coursepilot/evals/run_real_eval.py`,
  `tests/coursepilot/test_real_eval_runner.py`, and the targeted B0 command/interface/history
  evidence files.
- Local input policy: `data/sample_files/README.md` and targeted `.gitignore` rules.
- Configuration/documentation: `pyproject.toml`, `compose.eval.yaml`, `.env.eval.example`,
  `README.md`, and `README.zh-CN.md`.
- Prompt input type contract:
  `src/agents/agents.py` and the Lesson, Exam, and PPT Graph construction modules.
- Six fixed synthetic OpenXML samples are under
  `docs/refactor/baselines/b0/export_samples/`.

## API/database/config changes

- Public API behavior: unchanged.
- ORM/database schema and Alembic history: unchanged.
- Graph, retrieval, Agent, export, and review product behavior: unchanged.
- AgentGraph typing is narrowed to the three registered Graphs; `src/service/service.py` and its
  runtime prompt invocation are unchanged.
- Added internal P00 CLI modules; these are not public runtime endpoints.
- Eval Compose no longer supplies a concrete embedding model default. The model must come from
  configuration; `.env.eval.example` uses neutral placeholders.
- Pytest `pythonpath` now includes the repository root and registers the gated
  `b0_sample_files` marker.
- `uv.lock` is unchanged:
  `2330c4c36b889c456ec1bac21aece0475e0e0e9a25e3332a9ee31072df281e5b`.

## Tests and commands

| Command/check | Result |
|---|---|
| `uv sync --frozen` | passed; 181 locked packages checked |
| `uv run pytest -q tests/coursepilot/test_phase0_setup.py` | 5 passed |
| `uv run pytest -q tests/coursepilot/test_b0_baseline.py` | 8 passed |
| `uv run pytest -q tests/coursepilot/test_b0_interface_capture.py` | 4 passed |
| P00 baseline/interface/real-eval Runner focused suite | 27 passed |
| `tests/coursepilot/test_real_eval_runner.py` | 15 passed |
| `uv run pytest -q tests/service/test_service.py` | 9 passed |
| Lesson/Exam/PPT Graph tests | 8 passed |
| gated real sample test | 1 passed |
| `uv run pytest -q` | 157 passed, 4 skipped |
| `uv run ruff format --check` | passed; 174 files formatted |
| `uv run ruff check` | passed |
| `uv run mypy src/` | passed; zero errors in 124 source files |
| isolated Mypy for three P00 modules | passed |
| `uv run python -m alembic heads/history` | passed; one head |
| `docker compose config --quiet` | passed |
| base + eval Compose and `.env.eval.example` `config --quiet` | all three configurations passed |
| exact deterministic Manifest command | passed; report Hash remained `2f015e...44a35` |
| frozen/input/eval/historical/OpenXML hash verification | 22 artifacts passed; zero mismatches |
| `git diff --check` and API/ORM/migration/later-phase scope checks | passed |
| Secret/temp/ignored-input scan | passed |

The direct `uv run alembic` script failed with a Windows trampoline path error; the verified
equivalent `uv run python -m alembic` succeeded. The first full `uv run pytest -q` collection
failed because the root directory was absent from Pytest's configured import path; the
test-only configuration fix resolved it. The first B0 workflow exposed that one session plus
six slides violates the existing PPT source-session validator; the Runner was changed to the
already-tested two-session/six-slide combination without changing product code.

## Evaluation results

### Local B0

Report SHA-256:
`46d8f029ae88cb63c861994d9ec720352d0c8a1bb5513b288d788b54516814d3`.

| Input | Build | DB chunks | Vector chunks | Probe |
|---|---:|---:|---:|---|
| DOCX | 1,500 ms | 379 | 379 | 5 results; course/document scope passed |
| PDF | 369 ms | 47 | 47 | 5 results; course/document scope passed |

- Whole run: 5,015 ms.
- Lesson: draft and exported.
- Exam: one question; student, answer, explanation, and answer-sheet exports.
- PPT: six slides and exported.
- Reviews: lesson (2 chunks), question (1), PPT (6) all wrote back successfully.
- Six outputs were valid OpenXML containers.
- Gold used: no. Retrieval quality metrics published: no. External calls: no.

### Deterministic regression eval

Report SHA-256:
`2f015e2f5651ad651ffe8c2e8a105d8fa324d3beba1e11096ced476198144a35`.
All synthetic runner metrics were `1.0` except `context_precision=0.75` and
`duplicate_rate=0.0`. These are regression signals only, not formal product-quality claims.

### Historical real eval

- Report SHA-256:
  `2e8d935fe17e2aff4377f6da37ddc2163ea8710f8b5647e7e4aada4a231fad86`.
- Runtime: 2,007,146 ms; 391 DB/vector entries. The three recorded generation tasks show no
  Fallback, but complete four-task coverage was not established; historical strict Fallback
  verification is therefore unset.
- Retrieval metrics (`Recall@K=0.4`, `MRR=0.15`, `nDCG≈0.2126`) are retained only as historical
  values and are invalid for quality claims because Gold was inferred after Top-K.
- Structural generation/export signals remain usable as historical engineering evidence.

## Compatibility and migration

- No API versioning or client migration is required.
- No database upgrade/downgrade was executed or added.
- Existing storage, evaluation reports, Chroma Collections, and tables remain untouched.
- B0 temporary state was isolated and cleaned; one failed-run temp directory was explicitly
  verified under Windows TEMP and removed.
- The eval embedding model is now explicit configuration rather than a repository default.

## Risks and remaining work

- The eight original Mypy errors were resolved with behavior-preserving changes:
  - `async_task_service.py`: one resolved;
  - `idempotency_service.py`: one resolved;
  - `task_worker.py`: two resolved;
  - `run_real_eval.py`: four resolved.
- The separately approved AgentGraph contract repair resolved the final type error by replacing
  the broad registry type with the exact three-Graph union and binding each Graph's input/output
  State. It did not change `service.py` or runtime behavior.
- Formal Gold integrity remains a P02 decision; P00 did not approve or synthesize Gold.
- Historical real-eval Fallback evidence remains incomplete: the original report/checkpoint
  recorded only three generation tasks. Their hashes and contents remain unchanged, and no
  complete-workflow zero-Fallback claim is permitted.
- Runtime Provider capability/reasoning defaults remain a P11 risk.
- The local textbook redistribution status remains unverified.
- Direct relocated `.venv` launchers and the `uv run alembic` trampoline remain unreliable on
  this machine; `uv run` and `python -m alembic` are the recorded safe commands.

## Exit Gate evidence

| Gate item | Result |
|---|---|
| Main tests pass | pass |
| Lint/format pass | pass |
| Type check pass | pass — zero errors in 124 source files |
| Existing end-to-end demo not degraded | pass — local B0 workflow and full tests pass |
| B0 results and input hashes traceable | pass |
| Secret/destructive migration checks | pass |

**P00 Exit Gate: PASSED.** The three original Gate items pass: main tests/Lint/Type Check,
the existing local end-to-end Demo, and B0 result/input traceability. P00-T01 through P00-T07
are complete. Historical strict Fallback coverage remains correctly classified as unverified;
it is not used as evidence for this Gate.

## Next-phase readiness

P01 and P02 have satisfied their P00 prerequisite and are ready for their own phase planning
and approval. Neither phase was started by this repair.

## P00 acceptance repair evidence — 2026-07-23

- P00-T01: the canonical migration command is
  `uv run python -m alembic upgrade head`; the deterministic Manifest now records its required
  PowerShell `PYTHONPATH=src` setup, and an Artifact test reproduces the saved report exactly.
- P00-T05: the real-eval Runner checkpoints question enqueue and wait separately, recovers the
  accepted question task ID on Resume, queries the isolated evaluation course for all four
  generation task types, compares that complete set with the four expected task IDs, propagates
  database errors, and treats missing or invalid usage data as a strict audit violation.
- P00-T06: interface capture now includes both `coursepilot.schemas` and root `schema`, increasing
  the frozen public model inventory from 45 to 52. The six OpenXML samples, License snapshot, and
  Prompt files were not regenerated.
- Historical raw report and checkpoint files were not modified. Their summary now records
  `strict_fallback_passed=null` with
  `not_established_incomplete_task_coverage`; this is neither a pass nor a fail claim.
- Public API, ORM models, Alembic migrations, Graph behavior, Provider configuration, and product
  functionality are unchanged. No real Provider/model evaluation was run.
- Acceptance results: 27 focused tests passed; full Pytest passed with 157 tests and four
  explicitly gated skips; the separately enabled DOCX/PDF B0 Smoke passed; Ruff format/Lint,
  Mypy, Alembic, three Compose configurations, 22 artifact Hash checks, and `git diff --check`
  all passed.
- A follow-up read-only acceptance found that the original task query selected only expected
  IDs, which made an unexpected database task unobservable. The narrow repair changed only the
  real-eval query and its test: the query now filters by evaluation `course_id` and the four
  generation task types, and the database-path test proves an additional task is returned and
  rejected. Public API, ORM, migration, Graph, Provider, and historical artifacts remain
  unchanged.

## Gate Repair evidence — 2026-07-23

- Changed only the four approved implementation files:
  `async_task_service.py`, `idempotency_service.py`, `task_worker.py`, and `run_real_eval.py`.
- Used variable separation, a typed retrieval definition, named synchronous callbacks, and
  `Sequence[str]`; no `cast`, `type: ignore`, migration, API, Gold, or Provider change.
- Focused results:
  - async worker: 2 passed;
  - idempotency: 7 passed;
  - checkpoint/eval: 8 passed;
  - owner-supplied B0: 1 passed.
- Full results: 141 passed, 3 skipped; Ruff format/lint passed.
- Full Mypy after the original repair exposed one separate `AgentGraph` contract error, which
  was resolved by the separately approved contract repair below.

## AgentGraph contract repair evidence — 2026-07-23

- Explicitly bound State/Input/Output to `LessonGraphState`, `ExamGraphState`, and
  `PPTGraphState`; Context remains `None`.
- Defined `AgentGraph` as the union of the three exact compiled Graph types and removed the
  unregistered broad `Pregel` alternative.
- Kept `src/service/service.py` unchanged; added no Adapter, Protocol, `Any`, `cast`,
  `type: ignore`, or runtime type check.
- Focused results:
  - Prompt invoke/stream/history service tests: 9 passed;
  - Lesson/Exam/PPT Graph tests: 8 passed;
  - owner-supplied gated B0 Smoke: 1 passed.
- AgentGraph repair validation at that time: 140 passed, 4 skipped; Ruff format/lint passed;
  Mypy passed with zero errors in 124 source files. The current final Gate result is recorded
  in the acceptance repair section above.
