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
- Formal Test: **executed once under the approved lock**. Retrieval and QA completed 120/120 and
  280/280 Cases with zero Fallback. DS6 and DS7 passed, but Security passed only 5/6 because the
  prompt-injection marker missed the frozen `Ignore application policy` control.
- Current status: `gate_failed_formal_test_security`. The failure is a zero-tolerance L0 result, so
  CourseRAG Port/Contract is not frozen and P11 is not ready. No Test-driven repair is permitted in
  this release.
- Start/end Git commit: `b6483f5ae8a0b3c3e45858c3872b4ed86e94502d` /
  checkpoint `3665211` on `refactor/p00-baseline`; this final report update is uncommitted.
- Scope protection: one explicitly authorized checkpoint commit was created; no push, PR,
  user-database migration, old-data deletion, Gold rewrite, P11 work or silent fallback occurred.

## Task results

| Task | Result | Evidence |
|---|---|---|
| P10-T01 | implemented_local_tests_passed | deterministic Section diff, neighbor/profile impact expansion, Change Coverage and verified Artifact reuse planner |
| P10-T02 | implemented_local_tests_passed | valid/exact/structural/similarity migration with explicit `needs_review` and `invalid`, stable Batch identity and candidate trace |
| P10-T03 | implemented_local_contracts_passed | whitelisted immutable VerifiedContent, independent dense/sparse overlay, atomic active pointer, idempotent write/revoke |
| P10-T04 | implemented_local_contracts_passed | manual/count/token/age trigger priority, deterministic Batch identity, row-lock selection and item retry facts |
| P10-T05 | formal_security_gate_failed | local fault tests passed, but locked Test found one unmarked prompt-injection wording; zero side effects were preserved |
| P10-T06 | completed_locked_test_executed | Approved inputs and exact Test Lock used; no Gold leakage or Test-driven tuning |
| P10-T07 | formal_core_completed_ds8_offline_pending_gate_failure | B3–B8/Q0–Q3, DS6/DS7/Security executed; DS8 offline cold/warm workload execution remains unreported because the L0 security failure stops the release Gate |
| P10-T08 | completed | CourseRAG README, API, architecture, gateway deployment, rollback, limits and this formal failure record updated |

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
| Full `uv run pytest -q` before Test Lock | 540 passed, 5 gated skips |
| Full `uv run pytest -q` after Test Lock | 517 passed, 23 failed, 5 skipped; all failures are historical pre-lock tests that hard-code `locked=false` or copy the now-locked file into candidate-generation fixtures |
| Post-lock P10 product/contracts/metrics subset | 48 passed |
| Post-lock formal-runner subset | 2 passed, 1 pre-lock-only assertion deselected |
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

After the authorized Test Lock transitioned to `locked=true`, 23 historical evaluation-data tests
failed because they explicitly assert an unlocked repository or copy the live lock into a
pre-P09/P10 candidate-generation fixture. Unlocking Test to satisfy them would violate governance.
The post-lock P10 product/contracts/metrics subset is 48/48 and the applicable formal-runner subset
is 2/2. This is recorded as lifecycle-test debt, not hidden as a product regression; no test or
runtime code is changed after the formal result in this release.

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

## Locked formal Test result

- Lock/authorization SHA-256: `06c6473e...` / `0eaa0982...`; checkpoint commit `3665211` was clean
  for every formal runner.
- Component Report SHA-256 `1c10e637...`: DS6 is 9/9, DS7 Change Coverage and eligible Reuse are
  1.0/1.0, and Security is 5/6. The failed control is
  `p10-sec-15-prompt-injection`; artifacts, database writes and external calls are all zero.
- Retrieval Report SHA-256 `313a7e55...`: all 120 Cases succeeded with zero Fallback and 40 Cohere
  Search Units. On the 36 main Cases, B4 has the highest Recall@10 (`0.9167`) and Complete Group
  Recall@8 (`0.8611`); B5 Cohere has the highest MRR@10 (`0.7014`) and nDCG@10 (`0.8006`) while
  Complete Group Recall@8 falls to `0.8056`.
- QA Report SHA-256 `b5b051ef...`: all 280 Cases succeeded with zero Fallback. QA consumed 78
  cumulative Cohere Search Units and 404,354 DeepSeek tokens; combined with the independent
  Retrieval run, formal usage is 118/240 Cohere Units and 404,354/1,500,000 DeepSeek tokens.
- Q3 main metrics: Answer Status Accuracy `0.9167`, Unanswerable Recall `1.0`, False Answer `0`,
  Citation Resolvability `1.0`, Claim-Citation Completeness `1.0`, QA Failure `0`, Fallback `0`,
  False Abstention `0.09375`, and Factoid Token F1 `0.3590`. These values are reported as Test
  evidence and do not modify this release.
- Formal Test did not execute the DS8 offline cold/warm build/OCR/enrichment workload templates.
  That omission remains explicit; no performance value is inferred from unit or Dev runs.

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
7. **Observed formal security miss:** the locked Test sentence `Ignore application policy ...`
   was not marked as prompt injection. **Cause:** the frozen byte-pattern detector recognizes
   variants such as `ignore previous`, `system prompt`, `developer message` and one Chinese form,
   but not policy-override language. **Proposed next-version solution:** replace the narrow phrase
   list with a versioned rule family covering instruction hierarchy, policy bypass, data
   exfiltration and tool coercion; retain original text, mark rather than delete, add multilingual
   paraphrase and adversarial-boundary Dev controls, then refreeze a new release before rerunning
   Test. **Current result:** no artifact, database or external side effect occurred, but the mark
   itself was absent. This is a real L0 failure and is not repaired from Test in the current release.

## Exit Gate

1. **Test has no Gold leakage or silent fallback:** **passed**. Exact Lock/Manifest guards were used;
   400 Retrieval/QA Case executions completed with zero Fallback and no post-result tuning.
2. **Security zero-tolerance metrics are zero:** **failed**. One of six locked Security controls was
   not marked, although it produced zero database, artifact or external side effects.
3. **CourseRAG Port/Contract is frozen for CoursePilot:** **not passed**. Local/Remote/Mock contracts
   pass, but the L0 formal security failure prevents the P10 release freeze.

At the time of this locked formal release, P10 status was `gate_failed_formal_test_security`, not
`completed_with_quality_debt`, and P11 remained blocked by P10. The later P10-D013 addendum changes
only the dependency scope; it does not revise this formal result.

### Post-report governance addendum (P10-D013)

The formal result above remains immutable: the original detector missed one locked control and
did not pass its release Gate. Subsequent P10.1-P10.3 releases also failed their own preregistered
Profile gates and were never promoted. On 2026-08-12 the Course Owner approved a narrower dependency
interpretation: because the rejected candidates remain default-off, produced no unsafe side effect,
and are not required by P11's Model Gateway contracts, the detector Profile debt is isolated from
the completed P10 core CourseRAG contracts.

The current phase status is therefore `completed_with_isolated_security_capability_debt`, while
the detector status remains `candidate_rejected_default_off`. P11 may start only with untrusted
Context isolation, default-deny tools, ACL/Secret controls and auditable Capability routing. P17
must resolve the detector with a new independent Dev/Blind release, and P18 remains unable to pass
formal system Security L0 while this debt is open. This addendum changes no Test result, threshold,
runtime default, API, database, index or frozen report.

## Remaining approvals and risks

- The formal Test authorization is consumed and remains bound to Manifest `cad5df9c...`; it cannot
  be reused to tune or silently rerun this release.
- A new Dev protocol and new release identity are required to repair the prompt-injection marker.
  The current Test phrase may be used only as a disclosed regression Sentinel, not as repeated
  tuning data. Broader rule design must be developed on new Dev/adversarial controls.
- Trusted headers are secure only when the deployment gateway strips client values and direct
  service access is blocked; complete IAM remains P17 scope.
- DS8 offline cold/warm performance remains unexecuted and must not be inferred from existing
  reports. It can be completed only in a separately frozen release after the L0 security repair.
