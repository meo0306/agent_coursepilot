# Codex 阶段 Prompt：P15 试卷 Blueprint、Fan-out/Fan-in 与全局修复

请在 **Plan 模式**执行本阶段。先完成审计和计划，不要在计划获批前修改代码。

## 阶段目标

实现 Blueprint 审核、Question Batch 并行、全局校验、局部重生成和题目级写回。

## 前置依赖

- 阶段依赖：P10-P13
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

- P15-T01: 实现 Evidence/KP 驱动 Exam Blueprint、题型/分值/难度/内容角色/Batch Plan。
- P15-T02: 接入 Blueprint Review 和人工修改。
- P15-T03: 使用 LangGraph Send 或等价机制按 Question Batch Fan-out，设置并发和 Provider 限流。
- P15-T04: Fan-in 后重新编号并执行总分、题量、覆盖、重复、答案泄漏和引用全局校验。
- P15-T05: 实现题目、答案、解析和 Batch 级定向 Repair/Regenerate。
- P15-T06: 接入 Global Review，导出和题目/解析写回分别授权。
- P15-T07: 实现 Student Exam、Answer Key、Detailed Explanation、Answer Sheet 四类 DOCX 模板。
- P15-T08: 运行 EX-P0—P3 并行实验和 CP-DS2 Pilot。

## 主要代码区域

- `src/agents/coursepilot/exam/`
- `src/coursepilot/application/exam_service.py`
- `resources/templates/exam/`

## 明确禁止

- 不得按所有题目无限并发
- 不得在 Blueprint 未确认时生成题目
- 不得用局部 Batch 校验替代全局校验
- 不执行 P15 之后阶段的业务实现；只允许建立当前阶段必需的接口或 TODO。
- 不自行改变冻结产品决策。发现不兼容时写入 Decision Log 候选并说明最小安全默认方案。

## 必须验证

- Blueprint Gate
- Fan-out/Fan-in/Concurrency
- Global Validation/Duplicate
- Four-file Export/Writeback
- 运行主测试、Ruff 和 Mypy；如存在既有失败，提供证据并运行阶段专项测试。
- 检查 Secret、临时文件、未说明 Fallback 和破坏性迁移。

## Exit Gate

- 并行不破坏全局一致性
- Global Review 前无正式导出
- 仅批准题目/解析可写回

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
