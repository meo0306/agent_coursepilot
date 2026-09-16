# Codex 阶段 Prompt：P13 分层 ValidationIssue 与 Targeted Repair

请在 **Plan 模式**执行本阶段。先完成审计和计划，不要在计划获批前修改代码。

## 阶段目标

将布尔校验和整件重生成改造成可定位、分级、规划和无回归的局部修复系统。

## 前置依赖

- 阶段依赖：P11,P12
- 读取 `docs/refactor/EXECUTION_STATUS.md`，确认上游 Exit Gate 已通过。
- 检查当前 Git 状态并记录起始 Commit；不要覆盖用户未提交修改。

## 必须读取的文档

- `docs/refactor/frozen_v1.0/00_Document_Index_and_Decision_Baseline_v1.0.md`
- `docs/refactor/frozen_v1.0/07_Implementation_Roadmap_and_Task_Backlog_v1.0.md`
- `docs/refactor/frozen_v1.0/05_CoursePilot_Agent_Engineering_Upgrade_Plan_v1.0.md`
- `docs/refactor/frozen_v1.0/06_CoursePilot_and_System_Evaluation_Plan_v1.0.md`
- `docs/refactor/DECISION_LOG.md`
- `docs/refactor/RISK_REGISTER.md`
- `codex_prompts/00_MASTER_EXECUTION_RULES.md` 或仓库根目录 `AGENTS.md`

## 先做只读审计

1. 找出本阶段相关代码、测试、配置、迁移、API 和调用链。
2. 对照冻结文档，列出“已满足、部分满足、未满足、文档与代码冲突”。
3. 识别兼容、数据迁移、Provider、性能、安全和回滚风险。
4. 检查本阶段 Pilot Fixture、Fake/Mock 和验收命令是否具备。
5. 给出文件级实施计划和提交/PR 拆分建议；不要提前实现后续阶段。

## 本阶段任务

- P13-T01: 实现 ValidationIssue、IssueScope、ValidationReport、Severity、Issue Code Registry。
- P13-T02: 实现 L0 Schema、L1 确定性、L2 跨字段、L3 Grounding、L4 教学/业务校验接口。
- P13-T03: 将 Lesson/Exam/PPT 旧 Validator 分步迁移，先保持原规则再增加精确 Scope。
- P13-T04: 实现 RepairPlanner、RepairPlan、allowed_paths、Patch Contract、Precondition 和 Model Profile Route。
- P13-T05: L0/L1 规则修复；低风险 L2 用 Light；Grounding/教学问题用 Main。
- P13-T06: 修复后重新校验目标对象和全局约束，计算 Unauthorized Modification 和 Regression。
- P13-T07: 构造 CP-DS4 Pilot（各 10）和 CP-DS5 Pilot（各 5）。
- P13-T08: 输出 Validator/Repair 专项报告。

## 主要代码区域

- `src/coursepilot/validation/`
- `src/coursepilot/repair/`
- `tests/coursepilot/faults/`
- `datasets/coursepilot_eval/validation/`

## 明确禁止

- 不得仅返回字符串错误
- 不得让 LLM 自己决定允许修改范围
- 不得用修复掩盖 Critical Issue 的人工审核
- 不执行 P13 之后阶段的业务实现；只允许建立当前阶段必需的接口或 TODO。
- 不自行改变冻结产品决策。发现不兼容时写入 Decision Log 候选并说明最小安全默认方案。

## 必须验证

- Issue Match/Scope/Severity
- Patch Apply/Precondition
- Preservation/Regression
- Fault/Repair Pilot
- 运行主测试、Ruff 和 Mypy；如存在既有失败，提供证据并运行阶段专项测试。
- 检查 Secret、临时文件、未说明 Fallback 和破坏性迁移。

## Exit Gate

- Issue 可定位到 item/json_path
- 局部修复不整件重写
- 错误检测和修复指标可计算

## 计划输出格式

请按以下结构输出计划：

1. 仓库现状与差距；
2. 关键设计选择；
3. 文件级变更计划；
4. 数据库/API/配置和兼容策略；
5. 测试与专项评测计划；
6. 风险与回滚；
7. 任务 ID 到变更的映射；
8. 预计在本阶段明确不做的内容。

计划获批后，再按计划执行。执行结束时更新状态、风险和阶段报告，并逐项判断 Exit Gate。
