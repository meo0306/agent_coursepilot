# P13 ValidationIssue 与 Targeted Repair 阶段报告

## 结果

P13-T01 至 P13-T08 已完成。新增分层 ValidationIssue、L0-L4 Validator、Issue Code Registry、RepairPlanner、受限 Patch Contract、Precondition、目标/全局复检和 P13 Pilot Runner；旧 Lesson/Exam/PPT Validator 仍保持原有布尔报告合同，并增加结构化入口。

## 数据与边界

- 复用已批准 CP-DS4/5 Pilot Bundle：`b436f6e1901bb9447359e4fd0524f27ba39bfa24742b3ec006e451ae0bec9cd0`。
- CP-DS4：30 条，Lesson/Exam/PPT 各 10 条。
- CP-DS5：15 条，Lesson/Exam/PPT 各 5 条。
- CoursePilot Dev/Test 未读取、未锁定、未推广为正式 Gold。
- 外部 Provider 调用数：0。

## 实现结果

- Issue 以 `code + scope` 匹配，Scope 保留 Artifact 类型、Item ID 和 JSONPath。
- Critical Issue 只能形成候选 Patch，不能自动发布。
- Patch 只能作用于 Planner 预先批准的 `allowed_paths`，并拒绝 `forbidden_paths`、根替换、前置条件不匹配和非法操作。
- 修复结果不覆盖源 Artifact；通过 P11 ArtifactVersion 语义创建新版本。
- 修复后重新运行目标规则和全局规则；Unauthorized Modification 与 Regression 均可计算。
- L3 只使用注入的 Resolver/Port，不导入 CourseRAG 内部实现。
- 旧 Validator 的公开字段和 Graph/API 兼容行为保持不变。

## Pilot 指标

`storage_eval/p13_validation_repair/report.json`：

- Issue Detection Recall：`1.0`
- Code Precision：`1.0`
- Scope Precision：`1.0`
- Severity Accuracy：`1.0`
- Clean False Positive：`0`
- CP-DS5 Repair Plan：`15/15`
- Path Violations：`0`
- Unauthorized Modification：`0`
- Regression：`0`
- External Calls：`0`

以上是确定性 Contract/Fake Pilot 结果，不代表真实外部模型的修复质量或成本收益。

## 验证命令

- P13 专项与批准数据：`23 passed`
- Graph/Contract/B0 Smoke：`38 passed, 1 skipped`
- Ruff 与 Mypy：通过
- Pilot Runner：通过，报告已原子写入 `storage_eval/p13_validation_repair/report.json`

## 风险与后续

- 旧 Graph 中原有整对象 Repair 路径仍作为兼容路径保留，不计入 P13 Targeted Repair 能力；P14-P16 再逐条接入业务 Graph。
- L4 教学质量仍需人工检查，不使用 LLM-as-a-Judge。
- P13 不新增数据库迁移，Alembic Head 仍为 `0017_coursepilot_checkpoint_interrupts`。

## Exit Gate

1. Issue 可定位到 item/json_path：通过。
2. 局部修复不整件重写：通过。
3. 错误检测和修复指标可计算：通过。

P13 状态为 `completed / passed`，P14 具备开始条件。
