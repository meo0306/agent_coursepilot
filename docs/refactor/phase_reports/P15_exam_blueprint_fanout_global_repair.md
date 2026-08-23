# P15 Exam Blueprint、Fan-out/Fan-in 与全局修复阶段报告

## 当前结果

- 强类型 Exam Blueprint、Slot、Batch、Question、Artifact 和 Global Report；
- Batch 有界并发、稳定 Fan-in、Fingerprint 和成功 Batch 复用；
- Blueprint/Batch/Global 校验、重复检测、答案泄漏检测和 Question-scoped Repair Plan；
- 四类版本化 DOCX 导出和题目/解析级写回接口；
- P15 专项离线 Runner 与真实 Provider 预算预检。

## 验证证据

P15 Domain/Workflow/Validation 专项测试、P13 Validation/Repair 回归、CP-DS2 Approved Bundle
验证均通过；全量测试为 686 passed、12 skipped。P15 新增模块 Ruff、Format Check 和 Mypy 通过。预算预检为 34 requests、160,000
input tokens、220,000 output/thinking tokens、预计 CNY 0.60，未超过 CNY 0.80 上限。

## 未完成项与边界

真实 EX-P0--P3 Provider Pilot 已尝试一次：受控沙箱首个请求在发送前失败；授权网络重试
在五分钟内未返回，当前请求状态可能已发送但未确认，因此按规则停止，不自动重试。需先在
Provider 控制台核对用量后才能决定是否继续。四文件渲染视觉检查、PostgreSQL 端到端
Export/Writeback、人工 Global Review 和阶段 Exit Gate 尚未完成。P15 V2 默认关闭，Legacy
Exam API/Graph 保持不变；未执行 Test、Gold 推广、P16 或 commit/push/PR。
# P15 Closure Repair (no external API)

## Problem -> cause -> repair -> result

1. The old evaluator only ran one sequential path, sent Evidence IDs without bounded text, and
   had no durable checkpoint. The repair adds bounded Evidence payloads, atomic request-response
   checkpoints, explicit P0/P1/P2/P3 variants, bounded batch sizes, cache-aware resume, and stable
   fan-in numbering. Offline fake-provider coverage now runs all four variants with zero Provider
   calls (P0/P1/P2: 5/5/5 logical requests; P3: 17).

2. The graph previously generated before Blueprint Review and side effects did not bind exact
   approval target paths or refresh the current task version. The graph now fails closed at
   `blueprint_review`; writeback binds the exact approval record and JSON path; decision and side
   effect execution reject stale task/artifact versions. The isolated PostgreSQL gate passes all 6
   migration, restart/resume, stale-version, approval-scope and idempotency cases.

3. DOCX export used a blank document and could publish placeholders or overwrite an existing
   operation directory. The exporter now uses the approved physical template, stages and reopens
   every file before guarded publication, removes student answers/explanations, cleans failures,
   and renumbers questions after fan-in. Local LibreOffice/Poppler rendered all four roles to one
   page with no placeholders and no answer leakage in Student Exam.

## Verification boundary

- Focused P15/offline tests: **16 passed**; targeted Ruff and Mypy: **passed**.
- PostgreSQL gate: **6 passed**; CP-DS6 structural runner reports `external_calls=0` and
  `gold_promotion=false`.
- No Cohere/DeepSeek or other external Provider call was made during this repair.
- Real Smoke and full Pilot remain separately authorized; P15 is currently
  `closure_repair_complete_provider_pending` and P16 cannot start until that gate is closed.
## Real Provider Smoke/Pilot result

The separately authorized P15 Smoke/Pilot used the approved CP-DS2 Dev bundle and the same
`deepseek-v4-flash` Model Gateway. It never read Test, promoted Gold, switched models, retried an
ambiguous request, or used a deterministic fallback. The durable checkpoint and report are
`storage_eval/p15_provider_smoke/checkpoint/` and `storage_eval/p15_provider_smoke/pilot_report.json`.

The hard budget was respected: **32/34 provider requests**, **64,436/200,000 input tokens**,
**59,794/300,000 output/thinking tokens**, and **CNY 0.184024/0.80** based on Provider usage.
The failed attempt's usage is retained rather than discarded.

The result is not a passed Exit Gate. Smoke/P3 produced one duplicate-question pair and two
cross-answer leakage findings. The P0 pressure run produced answer/cross-answer leakage, P1 still
produced cross-answer leakage, and P2 still produced a duplicate-question finding. The remaining
P3 pressure case failed closed when the Provider returned `null` for a structured `ProviderBatch`
(`structured_parse_error`, request `fb17dd665ef3ed1f607bf7772648ece6632d358b32394a6658d4e593b677c84b`);
the Provider had supplied 1,984 input and 1,781 output tokens, so billing remains
`unknown_pending_reconciliation`. No automatic retry was made.

The interpretation is architectural rather than a budget problem: per-batch schema success does
not guarantee global uniqueness or answer isolation, and the real Provider can still violate the
structured-output contract. P15 remains `gate_failed_quality_and_provider`; further work must first
repair duplicate/answer-leakage handling offline and reconcile the failed Provider request. The
two unused request slots are intentionally not consumed automatically.
## Closure Repair v2 after the real Provider run

### Problem and root cause

The first real run showed three separate functional gaps. A schema/parse exception in one Batch
escaped `asyncio.gather` and stopped the remaining case. Duplicate and answer-leakage validation
produced strings but the workflow never consumed them as a RepairPlan. Leakage target IDs were
also encoded with `:` even though P15 question IDs contain `:`, so a string-splitting repair path
could not reliably identify the affected question. Concurrent evaluation accounting inspected the
last shared collector record, which was unsafe when several requests completed out of order.

### Implemented repair

- Batch generation exceptions are isolated as explicit failed Batch results; successful sibling
  Batches and their stable order are retained, and the exam enters `needs_review` rather than
  aborting the whole run.
- `ExamGlobalReport` now carries typed direct-leakage IDs and cross-answer leakage pairs. The
  RepairPlanner preserves the first duplicate and selects only the later question, combines all
  issues for one target, and exposes only its stem/options/answer/explanation paths.
- P3 executes at most four one-question repairs through `content_repair_main`, supplies existing
  stems/answers as forbidden overlap, preserves identity/score/difficulty/KP/Evidence fields, and
  reruns the complete Global Validation after every accepted replacement.
- The Provider checkpoint now implements an atomic durable pre-dispatch reservation. Concurrent
  calls cannot exceed request/token/cost caps; a crash leaves an ambiguous reservation that blocks
  automatic replay; success or failure audit releases the reservation while retaining actual
  Provider usage. Experiment-qualified case keys prevent P0/P1/P2/P3 results from overwriting one
  another.

### Verification result

Focused P15 workflow/evaluator tests pass (`28 passed` in the broader P15 group), Contract/P12
compatibility passes (`32 passed`), B0 sample smoke passes, and the full suite passes
`699 passed, 12 skipped`. Ruff Format, Ruff Check, Mypy, Alembic single head and `git diff --check`
all pass. No external Provider was called during this repair. P15 is therefore functionally ready
for a bounded real revalidation, but the Exit Gate remains pending until that run proves duplicate
and leakage errors are removed and the structured-output failure path remains isolated.
## Final P3 Provider revalidation

After the offline repair, the owner-authorized P3 revalidation reused the original response
Checkpoint. Cached Planner/Batch responses were not resent. One provider-contract defect was first
found: the new repair prompt did not contain the literal `json` keyword required by DeepSeek JSON
mode, so those repair calls failed at the request boundary. Adding the explicit JSON instruction
fixed the contract. A second offline scheduling defect was then found and fixed: a no-op repair
could leave a newly exposed duplicate pair without selecting an alternate target.

The final cached revalidation completed all three approved Dev cases with zero Batch failures and
zero global validation errors. The final cumulative ledger is **53/70 provider requests**,
**121,069 input tokens**, **106,417 output/thinking tokens**, and **CNY 0.333903**, all within the
approved cumulative limits. Test remained unread, Gold was not promoted, and no model switch,
fallback or automatic retry occurred. Historical failed attempts remain preserved in the audit for
billing reconciliation; they do not affect the final case status.

The functional P15 Gate is now green for the three-case Provider revalidation. Final phase status
is `gate_pending_owner_review` because the approved CP-DS2 human comparison/review package still
requires Course Owner confirmation. No additional Provider call is needed for this step.

## CP-B0/P15 human-review package

The owner selected a controlled comparison rather than the unstable full legacy pipeline. The
legacy question generator therefore received the same Approved CP-DS2 Blueprint and bounded
Evidence as P15, while the legacy Planner and whole-exam repair loop were excluded. This isolates
question quality from a confirmed legacy defect where duplicate Planner groups caused repeated
generation and repair calls.

Two provider-shape compatibility defects were fixed without changing question semantics:
multi-select keys such as `AB` normalize to `A,B` only when every character is a declared option,
and judgement keys such as `A` normalize only through an explicit option label such as `A=正确`.
A billed judgement response rejected by the former Schema was recovered from the local audit and
revalidated instead of being resent. Approved Batches of the same question type are consolidated
into one legacy generation group.

The completed fixed-Blueprint baseline contains 45 questions. Cumulative usage, including the
superseded full-legacy attempt, is **30 requests**, **116,622 input tokens**, **123,228 output
tokens**, and **CNY 0.363078**, within the approved 30/130k/150k/CNY 0.45 caps. The blinded package
at `storage_eval/p15_owner_review/` contains six exams and 90 question decisions; package SHA-256
is `44fcecfa343730253c2d535340e28b68604aa3a257721e540e85735c62c11254`. Its HTML provides
local autosave, JSON validation/download, and a standalone manual JSON template. The current agent
runtime exposed no connected browser, so real-click verification could not be performed here;
event binding and Blob download logic are covered by the local package tests. P15 remains
`gate_pending_owner_review` until the Course Owner returns the decision JSON.

## Owner-review result

The Course Owner returned all 90 decisions. The file is bound to package
`44fcecfa343730253c2d535340e28b68604aa3a257721e540e85735c62c11254`; decision SHA-256 is
`f784011c2f76f102f1c99aefc272a82a97354732c04d756d782b2f754f91c408`. No item is missing or
duplicated.

P15 improves the overall rubric mean from **3.122 to 3.524** and lowers mean Edit Burden from
**1.667 to 1.311**. Evidence grounding improves strongly (E-H9 **2.756 → 4.822**). However,
human-acceptable rate is lower (**0.6444 → 0.4889**) and the owner found three critical P15
defects:

1. case 01 q04 has an internally inconsistent transmissivity definition, a single-answer
   multi-select contract, and substantial duplication;
2. case 03 q12 has an incorrect answer set despite its own explanation acknowledging another true
   option;
3. case 03 q22 requires an omitted table, so the student cannot solve the question from the exam.

These are correctness/self-containment failures, not minor style variation. Under the approved P15
Gate, any critical P15 defect fails the phase. Final status is therefore `gate_failed`; P16 remains
blocked. The appropriate next action is a bounded P15 targeted-repair closure for answer-set
entailment, multi-select validity and stimulus self-containment, not another broad prompt-tuning
loop.

## Targeted Repair Closure implementation

### Repair motivation and root cause

The owner findings exposed a contract gap rather than a general model-quality problem. The prior
schema accepted a `multiple_choice` question with a single answer, did not require the model to
classify every option, and could not prove that the answer set agreed with its own explanation.
The question model also had no bounded `stimulus`, so references such as “according to the table”
could pass while the table was absent. Duplicate detection was primarily lexical and did not
combine shared Assessment Target/Evidence with answer semantics. Consequently the global report
could be green while three questions remained unusable.

The first closure draft also revealed an orchestration error: the reusable Repair Planner can
choose the later item in a duplicate pair. If that call fails, replanning may select the other side,
which makes a closure run depart from its preflight Question-ID set. That behavior is valid for a
general repair loop but invalid for an owner-approved bounded correction.

### Implemented solution

- `ExamQuestion` now supports a bounded stimulus and typed per-option assessments. Global
  validation checks single/multiple-choice cardinality, assessment-to-answer consistency,
  Evidence membership and answer/explanation agreement.
- Missing or explicitly omitted table/figure/data/material references are typed issues. The DOCX
  exporter renders the supplied stimulus before the stem.
- Duplicate detection adds a conservative same-Target/Evidence semantic path while retaining the
  original normalized text similarity path.
- Repair actions expose only stimulus, stem, options, option assessments, answer and explanation.
  Identity, score, slot, KP and Evidence remain immutable.
- The closure preflight found exactly 17 targets. Its runner freezes these IDs, calls each at most
  once and revalidates all 45 questions; it does not dynamically repair an unapproved counterpart,
  rerun CP-B0, or regenerate a whole exam.
- Provider accounting now counts physical potentially billable attempts and excludes connection
  failures explicitly classified as `not_sent` from Provider consumption.
- A delta review page shows only changed questions side by side. It autosaves locally and has
  independently bound progress/final JSON download buttons plus a standalone decision template.

### Execution result and current blocker

The final no-network preflight is 17/20 targets, with an estimate of 59,500 input tokens, 85,000
output tokens and CNY 0.2295 under the retained CNY 0.50 cap. The first managed real attempt
returned only connection errors and no structured model output, so all 45 source question hashes
were preserved. Its old report's estimated input value must not be interpreted as confirmed
Provider consumption; the corrected audit logic classifies those attempts as `not_sent`.

A second clean run was prepared under `storage_eval/p15_targeted_repair_network/`, but the Codex
managed runtime rejected the external execution due to its own usage limit before creating a
process, output directory or checkpoint. No workaround or duplicate external request was made.
Thus the functional implementation is complete, but the three owner-found defects have not yet
been replaced by successful Provider outputs.

### Verification

- P15/repair focused groups pass (including 15 closure/runner/workflow tests, Exam 11,
  Validation/Repair 4, evaluation/review 19, Contract 31 and exporter 6).
- B0 sample-file smoke passes.
- Full suite: **722 passed, 12 skipped**.
- Ruff Format, Ruff Check and Mypy (**447 source files**) pass.
- Alembic remains `0017_coursepilot_checkpoint_interrupts (head)`; no migration was added.
- `git diff --check` passes apart from informational line-ending warnings.

### Exit Gate — historical pre-revalidation state

At the first closure attempt P15 was `gate_failed_targeted_repair_provider_blocked`; that
historical state is retained above to explain the managed-runtime connection failure. The
subsequent authorized second round below completed the Provider revalidation and moved the phase
to `gate_pending_owner_review`.

## Targeted Repair Closure — authorized second round completed

The two explicitly authorized residual repairs were executed once:

- case02 `batch-multiple_choice-01:slot-1` (duplicate-question residual);
- case03 `batch-short_answer-01:slot-5` (cross-answer leakage residual).

The run completed from the durable checkpoint and produced
`storage_eval/p15_targeted_repair_network/report_final.json`. All three CP-DS2 cases now pass
complete global validation (`all_global_validation_passed=true`). The non-target question hashes
remain unchanged. Cumulative usage for the repair run is 19 requests, 69,606 input tokens,
80,286 output tokens and estimated CNY 0.230178; the CNY 0.50 / 100,000-input / 150,000-output /
20-request caps were not exceeded. No fallback, model switch or additional retry was used.

The final 17-question owner delta package is under
`storage_eval/p15_targeted_repair_network/review_final/`:
`review.html`, `review_items.json`, `review_decisions_template.json` and `package_manifest.json`.
Its source report SHA-256 is `d95d79e787e7d5e5b0173691715bc0f16548bf929a9975e52c54c200da20c7d0`.
P15 is now `gate_pending_owner_review`: the implementation and automatic gates are green, but
the Course Owner must approve the changed questions before P16 can start. No further Provider
call is authorized or required for this closure.

Post-run verification: focused repair/workflow tests **23 passed**; full Pytest **722 passed,
12 skipped**; full Ruff Format/Check passed; `git diff --check` has only existing line-ending
warnings. The previously recorded Mypy baseline remains successful on the same source tree; the
fresh full Mypy invocation exceeded the local 180-second wrapper without emitting a type error.

## Final owner review and phase closure

The Course Owner completed the final delta review in
`storage_eval/p15_targeted_repair_network/review_final/review_decisions.json`. Its SHA-256 is
`d83ad908cf18c0317cf05ab7e461f987553ff74bc1b009ecba9a375223012aae`, and it is bound to source
report `d95d79e787e7d5e5b0173691715bc0f16548bf929a9975e52c54c200da20c7d0`. Of the 17 changed
questions, 6 are `pass`, 2 are `minor_edit`, and 9 are `major_edit`.

The first closure solved the concrete contract failures: true multi-select answer sets,
per-option assessment, missing stimulus/table material, answer/explanation consistency and the two
registered residual duplicate/leakage pairs. The remaining owner findings are different in kind:
multiple Slots repeatedly measure the same fact, options paraphrase the same textbook statement,
and earlier questions reveal reasoning or facts needed by later questions. These are whole-exam
Blueprint and measurement-diversity failures. A question-local Patch cannot safely solve them
because its allowed paths deliberately exclude KP, Evidence, Slot identity and Assessment Target.
Continuing the same repair loop would churn wording without changing the exam design.

P15 therefore closes as `completed_with_quality_debt`. The core workflow Exit Gate is satisfied:
bounded parallelism preserves stable Fan-in/global structure, no formal export occurs before Global
Review, and writeback remains question/explanation-scoped with separate approval. The current Exam
V2 Profile is `provisional_dev_only` and remains default-off. No further Provider repair is planned
in this phase.

P15.1 backlog before P17/P18 promotion:

- allocate a unique primary assessment target and explicit content role to every Blueprint Slot;
- pass an exam-wide used-fact, used-answer and exclusion plan to every Batch generator;
- construct a cross-question semantic/clue graph, not only pairwise lexical similarity;
- resolve conflicts by replanning/regenerating the affected Slot or Batch, not by repeated local
  wording patches.

P16 may start as the sibling PPT workflow. P15.1 does not block P16, but it must be resolved or
explicitly dispositioned before the Exam Profile is promoted in P17/P18.
