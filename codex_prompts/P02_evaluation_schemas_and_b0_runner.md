# Codex 阶段 Prompt：P02 评测数据骨架与 B0 Runner

请在 **Plan 模式**执行本阶段。先完成审计和计划，不要在计划获批前修改代码。

## 阶段目标

在大规模重构前固定 Gold Schema、数据目录、Run Manifest 和旧系统适配器。

## 前置依赖

- 阶段依赖：P00
- 读取 `docs/refactor/EXECUTION_STATUS.md`，确认上游 Exit Gate 已通过。
- 检查当前 Git 状态并记录起始 Commit；不要覆盖用户未提交修改。

## 必须读取的文档

- `docs/refactor/frozen_v1.0/00_Document_Index_and_Decision_Baseline_v1.0.md`
- `docs/refactor/frozen_v1.0/07_Implementation_Roadmap_and_Task_Backlog_v1.0.md`
- `docs/refactor/frozen_v1.0/03_CourseRAG_Evaluation_Dataset_and_Baseline_v1.0.md`
- `docs/refactor/frozen_v1.0/03A_CourseRAG_Evaluation_Dataset_Construction_Guide_v1.0.md`
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

- P02-T01: 建立 CourseRAG DS0—DS8 和 CoursePilot CP-DS0—CP-DS8、SYS-DS1 目录及 JSON Schema/Pydantic Model。
- P02-T02: 建立 Pilot/Dev/Test Split 文件、人工审核状态、候选与 Approved Gold 分离机制。
- P02-T03: 实现 Run Manifest、Hash 校验、Checkpoint/Resume、原子报告写入和配置差异拒绝。
- P02-T04: 实现 B0 Evaluation Adapter：通过文本/span overlap 将旧 Chunk 结果映射到 Gold Evidence，而不是修改 B0 Runtime。
- P02-T05: 建立指标函数单元测试，尤其是 Evidence Group、Claim、ValidationIssue、Repair Patch 和 Recovery 指标。
- P02-T06: 建立人工评分表/JSONL Schema，但本阶段只完成少量 Pilot 样例。
- P02-T07: 建立测试集锁定标志，Runner 禁止在 Test 上自动调参。

## 主要代码区域

- `datasets/`
- `src/courserag/evals/`
- `src/coursepilot/evals/`
- `tests/evals/`

## 明确禁止

- 不要求一次完成人工正式 Gold
- 不得把当前 Chunk ID 当作 Gold 主标识
- 不得使用 LLM-as-a-Judge
- 不执行 P02 之后阶段的业务实现；只允许建立当前阶段必需的接口或 TODO。
- 不自行改变冻结产品决策。发现不兼容时写入 Decision Log 候选并说明最小安全默认方案。

## 必须验证

- Metrics Unit Test
- Manifest Hash/Resume Test
- Gold Leakage Guard Test
- B0 Adapter Test
- 运行主测试、Ruff 和 Mypy；如存在既有失败，提供证据并运行阶段专项测试。
- 检查 Secret、临时文件、未说明 Fallback 和破坏性迁移。

## Exit Gate

- Gold 与系统输出物理分离
- Runner 可中断恢复
- 所有非通用指标有代码和测试

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
