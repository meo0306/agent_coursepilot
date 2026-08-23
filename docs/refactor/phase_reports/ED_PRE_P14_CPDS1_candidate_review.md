# Pre-P14 CP-DS1 Lesson Pilot Candidate Review

任务：`ED-PRE14-CPDS1-T01` 至 `ED-PRE14-CPDS1-T08`

本批生成 3 条 CP-DS1 Pilot Gold Candidate 和 1 条非 Gold 证据不足合同负例。语义来源仍只有两个 Approved CourseRAG Primary 课程，未调用 Provider，未读取 Test/Holdout，未生成系统教案输出。

- Pilot Candidate SHA-256：`73d1d3e15285b35d3528ffdfd7427ef9d0f7c8eb7e0ed91e602a89ea705caaf3`
- Fixture SHA-256：`18284e62471d918be65900150c3cba3c9eefa61465d74dd3f5b3ef15eea97d57`
- Bundle SHA-256：`3e47c85c624ab0c3a751b34de38a8b1147a0d6187314ef9a27210b85cc9c1708`
- 记录：3 条 Gold Pilot、4 个 Context Fixture、1 条负例
- 审核入口：`storage_eval/cpds1_p14_review/3e47c85c624ab0c3a751b34de38a8b1147a0d6187314ef9a27210b85cc9c1708/index.html`
- 二轮入口：`storage_eval/cpds1_p14_review/3e47c85c624ab0c3a751b34de38a8b1147a0d6187314ef9a27210b85cc9c1708/second_review.html`

Candidate 文件本身保持 `candidate`，Approved 副本仅在精确 Bundle 审批后另行生成。审核重点为任务目标/课时、KP 与 Evidence 的对应、必要邻接、禁止事实和审核动作。

## 审批结果

该精确 Bundle 已由 `course_owner` 批准。因原审核页缺少导出渠道，两轮全通过决定由对话中的精确 Bundle 批准补录；无需重新审核。Approved Pilot 和审批文件分别位于 `approved/cp_ds1/p14_lesson_pilot.json` 与 `provenance/p14_cp_ds1_bundle_approval.json`。当前 P14 输入状态为 `formal_eval_ready`，但 P14 Exit Gate 尚未运行。
