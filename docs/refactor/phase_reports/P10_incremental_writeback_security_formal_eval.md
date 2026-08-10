# P10 CourseRAG Incremental, Write-back, Security and Formal Evaluation Report

## Phase verdict

- Implementation: P10-T01–T05 and the local portions of P10-T06–T08 are implemented inside the
  approved boundary.
- Local validation: **passed**. The final full suite reports 540 passed and five explicit gated
  skips; Ruff format/check, full Mypy, 0015 single-head, B0 sample smoke, contracts, Schemas and
  local leakage/security guards pass.
- Dev evaluation: **passed** under authorized Protocol `0dd9ff64...`. Exactly 12 cases were called,
  42 were reused by Hash, and usage was 86,042 DeepSeek tokens plus zero Cohere Search Units.
  DS6/DS7/Security Component Dev also passed without Provider or Test access.
- Formal Test: **not run**. The owner approved superseded Manifest `f90f4f1b...`, but preflight
  found that its workspace did not contain the formal runner and its workspace Hash included
  mutable Python bytecode. No Test lock or Provider call was made. Repaired Manifest v2
  `cad5df9c...` awaits exact reapproval and a clean-Git checkpoint.
- Current status: `formal_runner_refreeze_approval_and_checkpoint_pending`. P10 Exit Gate and CourseRAG
  contract freeze remain pending formal Test; P11 is not ready.
- Start/end Git commit: `b6483f5ae8a0b3c3e45858c3872b4ed86e94502d` / uncommitted at the
  same commit on `refactor/p00-baseline`.
- Scope protection: no commit, push, PR, user-database migration, old-data deletion, external
  Provider call, Test read/run, Gold rewrite, P11 work or silent fallback.

## Task results

| Task | Result | Evidence |
|---|---|---|
| P10-T01 | implemented_local_tests_passed | deterministic Section diff, neighbor/profile impact expansion, Change Coverage and verified Artifact reuse planner |
| P10-T02 | implemented_local_tests_passed | valid/exact/structural/similarity migration with explicit `needs_review` and `invalid`, stable Batch identity and candidate trace |
| P10-T03 | implemented_local_contracts_passed | whitelisted immutable VerifiedContent, independent dense/sparse overlay, atomic active pointer, idempotent write/revoke |
| P10-T04 | implemented_local_contracts_passed | manual/count/token/age trigger priority, deterministic Batch identity, row-lock selection and item retry facts |
| P10-T05 | implemented_local_fault_tests_passed | trusted-principal ACL, cross-course checks, MIME/magic, PDF/DOCX/archive/path/resource guards, injection marking and Secret redaction |
| P10-T06 | dev_passed_test_lock_pending | Approved DS6–DS8/Security reused; bounded 12-case QA and component Dev gates passed; deterministic combined Manifest produced; Test stays closed |
| P10-T07 | formal_runner_implemented_test_pending | Locked B3–B8/Q0–Q3 and DS6/DS7/Security runners, exact Resume, clean-Git and fail-closed budget guards pass locally; formal Test remains gated |
| P10-T08 | completed | CourseRAG README, API, architecture, gateway deployment, rollback and limits documentation added |

## Main changes

- Incremental and migration: `src/courserag/incremental/`,
  `src/courserag/evidence/migration.py`, `src/courserag/jobs/incremental.py`, and frozen resource
  profiles.
- Persistence: additive revision `0015_incremental_writeback_security`, predecessor and overlay
  pointers, incremental/reuse/migration/overlay tables, and expanded write-back/enrichment facts.
- Write-back: `application/writeback_service.py`, `application/enrichment_service.py`,
  `indexing/verified_overlay.py`, `jobs/enrichment.py`, repositories and contracts.
- Security/API: `security/`, trusted principal dependency, CourseRAG retrieval/QA ACL, verified
  write/revoke/enrichment routes, Remote client trusted headers, and stable error mapping.
- Compatibility: CoursePilot review write-back now delegates through the Port; whole Lesson/PPT and
  legacy chunk-only cases fail safely with explicit statuses while retaining response fields.
- Evaluation/governance: `p10_metrics.py`, `evaluation/p10_eval.py`,
  `evaluation/p10_formal_eval.py`, the single candidate profile, local/formal protocols, tests,
  this report, status, decisions and risks.
- Documentation: `docs/courserag/` plus root README links.

## Database, API and configuration

Revision 0015 is additive and is the only Alembic head. It adds immutable version predecessor,
incremental plan/impact/reuse, citation migration, verified overlay version, approval/revoke and
enrichment execution facts. Existing verified rows are honestly marked `legacy_incomplete`; they
are not silently indexed. Downgrade removes P10 audit facts and is an explicit stop-write/export
operator action.

Stable v1 Search/Context/QA routes now require trusted `reader+` claims. Verified write requires
`editor+`; revoke and manual enrichment require `owner+`. Path/body/header/entity course identity
must agree. The gateway must remove client-supplied identity headers before injecting authenticated
claims. Versioned services and overlay publication fail closed when required configuration is
missing.

P10 settings include frozen incremental/migration profiles, 0.92/0.75/0.08 migration thresholds,
write-back/overlay switches, 10/3000/24h batch thresholds, required ACL, bounded document limits,
and 180,000/0 Dev budgets. `.env.example` contains no non-empty API key, Secret, password or Token
example.

## Validation evidence

| Command/check | Result |
|---|---|
| `uv sync --frozen` | passed; 182 packages checked |
| Incremental / citation / write-back / security / 0015 suites | 4 / 3 / 5 / 3 / 1 passed |
| Contract suite | 30 passed |
| P10 focused implementation/Dev suite | 52 passed |
| B0 sample PDF/DOCX smoke | 1 passed |
| Full `uv run pytest -q` | 540 passed, 5 gated skips |
| `uv run ruff format --check` | 497 files already formatted |
| `uv run ruff check` | all checks passed |
| `uv run mypy src/` | success across 337 source files |
| `uv run python -m alembic heads` | `0015_incremental_writeback_security (head)` |
| Schema/data-boundary/P10-input/security guard subset | 32 passed |
| `.env.example` Secret-value check | zero non-empty secret examples |
| P10 atomic temporary-file check | zero `.p10-*` remnants |
| `git diff --check` | no whitespace error; Windows LF/CRLF notices only |

The first full run exposed one historical P03 table-boundary assertion that excluded P06–P09 but
not P10. The test was extended with explicit P10 table/column exclusions; the migration round-trip
then passed and the final full run was clean. Runtime and migration behavior were not weakened.

## Evaluation checkpoint

The authorized protocol canonical SHA-256 is `0dd9ff64ba94b9a0f6e3389565b17eb7e88d1ffd63b19e0e58775f7e6f462696`.
The QA Report/Gate SHA-256 values are `eed5700e...` / `74e52ba3...`; all fixed QA checks pass.
The 12 fresh cases consumed 86,042 DeepSeek tokens within the 180,000 cap and zero Cohere Search
Units. Main-54 Factoid Token F1 is 0.441279, Citation Resolvability and Claim-Citation Completeness
are 1.0, Unanswerable Recall is 1.0, and QA failure/false-answer/fallback rates are zero. The two
List cases satisfy the preregistered answered-with-cited-items contract; List Set F1 remains a
visible 0.0 L3 diagnostic.

Component Report `ca5c0f4d...` records DS6 15/15, DS7 Change Coverage/eligible Reuse 1.0/1.0 and
Security 10/10 with Test access false and no Provider calls. Repaired combined Frozen Manifest v2
is `storage_eval/p10/frozen_manifest.json`, exact SHA-256
`cad5df9ce87fc9682bef2441ed66aa957064f467a5ffdbd209b37e358c40937a`.

## Calibration problem analysis and repair record

1. **Observed coupling:** the existing generation-reliability switch applied the long-list output
   contract to both List and a task-style Factoid. That conflicted with the preregistered P10
   candidate, which intentionally retained the reliable List transport but restored the concise Q2
   Factoid contract. **Cause:** one Boolean represented two answer-shape policies. **Repair:** add a
   backward-compatible Factoid-specific toggle and disable only that branch for P10. **Result:**
   both List cases meet the cited-item contract while Factoid Token F1 rises above its fixed floor;
   grounding, abstention and citation safety remain unchanged.
2. **Observed Resume stop:** the first resumed run reported that the DeepSeek cap would be exceeded
   even though only one fresh case remained. **Cause:** Resume initialized its budget from all 54
   checkpoint results, including 42 historical Hash-reused cases that created no P10 Provider
   usage. **Repair:** count only successful IDs in the exact 12-case fresh set. **Result:** the same
   Manifest resumed without replay, total fresh usage remained 86,042/180,000, and no budget or
   Test boundary was relaxed.
3. **Observed freeze incompleteness:** a QA-only preliminary artifact could pass before the required
   DS6/DS7/Security evidence existed. **Cause:** freeze creation was originally attached directly to
   the QA runner. **Repair:** require a second deterministic Component Report and generate combined
   Manifest v2 only after both gates pass. **Result:** the final `f90f4f1b...` identity binds every
   Dev gate, usage audit and workspace Hash; the QA-only preliminary identity is superseded and
   cannot authorize Test.
4. **Observed security integration gap:** the document security policy had unit tests but the
   legacy upload route did not invoke it. **Cause:** policy construction and ingestion orchestration
   were separate. **Repair:** inspect PDF/DOCX bytes, MIME/magic, archive and path constraints before
   creating a directory, file or database row. **Result:** the new API regression proves a spoofed
   PDF returns `MIME_MISMATCH` and leaves the course document list empty; B0 PDF/DOCX smoke remains
   passing.
5. **Observed formal-freeze incompleteness:** after the owner approved `f90f4f1b...`, preflight
   found no executable formal Test orchestrator inside the frozen workspace. **Cause:** v2 bound
   Dev evidence but assumed the later Test path could be assembled after approval, which would
   make executed code differ from the approved workspace. **Repair:** add a locked Test-only loader
   and formal CLI for B3–B8/Q0–Q3 plus DS6/DS7/Security, with exact Resume, restored usage
   accounting, fail-sample policy and clean-Git enforcement. **Result:** 17 focused formal/P10/P08
   tests pass and Test remains unopened; the old Manifest cannot authorize execution.
6. **Observed nondeterministic workspace identity:** `_workspace_sha256` included generated
   `*.pyc` files under `src/**/__pycache__`. **Cause:** recursive selection did not distinguish
   source artifacts from interpreter caches. **Repair:** exclude `__pycache__`, `.pyc` and `.pyo`,
   and add a bytecode-mutation regression. **Result:** repeated imports produce stable workspace
   Hash `fffdd6d6...`; repaired Frozen Manifest is `cad5df9c...`.

## Exit Gate

1. **Test has no Gold leakage or silent fallback:** local guards pass, but formal Test has not been
   locked or run; final judgment is pending.
2. **Security zero-tolerance metrics are zero:** Dev Security is 10/10 with zero side effects;
   formal locked Test remains pending.
3. **CourseRAG Port/Contract is frozen for CoursePilot:** Local/Remote/Mock contracts pass, but the
   formal P10 convergence report and owner-approved Test evidence remain pending.

Therefore P10 is not `completed` or `completed_with_quality_debt` yet. Its correct status is
`formal_runner_refreeze_approval_and_checkpoint_pending`, and P11 remains blocked by P10.

## Remaining approvals and risks

- The owner must approve exact repaired Frozen Manifest `cad5df9c...`, bind the already stated
  40-query/Cohere-240/DeepSeek-1,500,000 authorization to it, and authorize a local checkpoint
  commit. The lock changes a tracked file, so formal execution cannot satisfy the existing
  clean-Git guard until that state is committed. No push or PR is requested.
- Trusted headers are secure only when the deployment gateway strips client values and direct
  service access is blocked; complete IAM remains P17 scope.
- Dev migration, reuse, QA and security evidence has passed; formal DS6–DS8 and Test metrics must
  not be inferred before the separately locked run.
