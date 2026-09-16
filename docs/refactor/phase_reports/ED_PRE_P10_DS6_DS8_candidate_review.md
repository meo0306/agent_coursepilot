# ED-PRE10 DS6–DS8 与 Security Candidate 审核报告

- Bundle SHA-256：`5b6d756a39c988f952536ec93d2aa23b9c593908c3ea24c6af6816cff92b6702`
- DS6 Candidate：`datasets/courserag_eval/v1/candidates/ds6/p10_citation_migration_r1.json`，SHA-256 `38d90246321af245eb4fae361f272ffac7ffeda534088dba9711c296ea66edc4`。
- DS7 Candidate：`datasets/courserag_eval/v1/candidates/ds7/p10_incremental_writeback_r1.json`，SHA-256 `54597bb55719124f3a2b9f5e7b88ea8698805acbf3f17ad256568433fabfa358`。
- DS8 Candidate：`datasets/courserag_eval/v1/candidates/ds8/p10_performance_workloads_r1.json`，SHA-256 `ec8be5d3eb4e49a23d342ac511c5c143db15a2bc91f3b60be3fa4a1bd7bd16cb`。
- Security Candidate：`datasets/courserag_eval/v1/candidates/security/p10_security_fault_r1.json`，SHA-256 `2fa925d212e77e96c773ace124b3ae9404f7642d1cf6c8a8f7d2cb63f9dcfb87`。
- DS6：9 个场景、24 个引用判断，Dev/Test = 5/4。
- DS7：12 个场景，Dev/Test = 7/5。
- DS8：20 个冷热态模板；Test 只绑定 Split Hash，未展开 ID。
- Security：16 个非语义控制场景，Dev/Test = 10/6。
- 语义来源数：2；派生变体和安全控制均不可检索。
- 审核页面版本：v2；DS7/DS8/Security 默认展开人类可读影响矩阵、输入和通过/退回条件。
- 首轮审核：`storage_eval/p10_input_review/5b6d756a39c988f952536ec93d2aa23b9c593908c3ea24c6af6816cff92b6702/index.html`（57 条）。
- 二轮复核：`storage_eval/p10_input_review/5b6d756a39c988f952536ec93d2aa23b9c593908c3ea24c6af6816cff92b6702/second_review.html`（29 条）。

## 人工审核重点

页面中的“完整 Gold JSON”只用于技术追溯，不再作为人工审核的主要界面。

1. DS6：逐条比较旧原文、变更清单和 `valid/migrated/needs_review/invalid`；特别检查
   重复原文、部分删除及删除 Evidence 的保守状态。
2. DS7：确认受影响范围没有漏算、无关产物可以复用；十条写回内容必须逐字来自
   Approved Dev Gold，课程分布为 DOCX 7 / PDF 3；撤销和重放不得生成重复记录。
3. DS8：确认工作负载、冷热态、重复次数和指标合理；页面不得显示 Test 40 的 ID。
4. Security：确认输入是有界非语义控制，预期行为 fail closed；Prompt Injection 只能保留并
   标记，伪 Secret 不得出现在日志、Trace、报告或 Manifest。
5. 全局：Primary 与派生版本互斥，六文件仍只有两个语义来源；不得新增课程事实。

当前没有无法唯一定位的源记录。需要人工裁定的是 DS6 状态及影响范围是否符合课程所有者
对“安全迁移”的判断，以及 DS7 写回内容是否适合作为正式控制样本。

## 自动验证

- 两次完整生成的八个 Candidate/Provenance 文件及 Bundle 字节级一致。
- P10 专项测试：5 passed。
- 全量测试：510 passed，5 skipped（均为既有显式 gated skip）。
- 69 份 JSON Schema 导出与 `--check` 一致。
- Ruff：466 files already formatted，Ruff Check passed。
- Mypy：317 source files，zero issues。
- `git diff --check`：无 whitespace error，仅有既有 Windows LF/CRLF 提示。

## 审批边界

当前全部记录均为 Candidate，Approved DS6–DS8/Security 尚未生成。`test.lock.json` 仍为
`locked=false`，未运行 P10、Dev 校准、Provider 或正式 Test。正式批准口令必须为：

`批准正式 P10 Input Gold Bundle 5b6d756a39c988f952536ec93d2aa23b9c593908c3ea24c6af6816cff92b6702`

## Owner review and exact approval checkpoint

On 2026-08-10, the Course Owner explicitly attested that every record in both review rounds passed,
requested no Candidate change and intentionally omitted browser JSON exports. The owner then
supplied the separately required exact Bundle approval phrase.

The repository records this as two `course_owner_conversation_attestation` artifacts covering
57 first-review and 29 second-review IDs. The verbatim statement SHA-256 is
`876279be2d5c02cc770fefdc63a8fb6e09b34fbe9d18cddcbbf4065e549eabc7`; these artifacts are not
represented as browser exports. An earlier automated attempt appended approval text that the owner
did not say and prematurely generated Approved outputs. That `.001` attempt remains invalid and is
preserved under provenance quarantine. The later exact owner approval produced valid batch `.002`:

- Approval Manifest: `a3886277f2bbfcc899446154302b13c7a9ffb2d80c3d4c461379f2f1b391d7f3`.
- Approved DS6: `820a575e857fd7553c0c5696a6cec6ea55093c458395e7a95d9acb47f64d059d`.
- Approved DS7: `3a78f2a4eff4a650b06418558179e831da9ae889fae786d29657941f6cd8894e`.
- Approved DS8: `72b97fece8218bebf2520e6cd006d145675fdc5d0057f65be5a075a3b5e7d980`.
- Approved Security: `fb2bdc2aed6d29e75f3c82560f82997d9dd6e1be924a8db8441ec43ed8636bc8`.

Exact replay reproduced every hash and added no duplicate `.002` review-log rows. P10 formal Dev
evaluation input is ready. Test remains `locked=false`; P10 implementation and its Exit Gate
evaluation have not started.
