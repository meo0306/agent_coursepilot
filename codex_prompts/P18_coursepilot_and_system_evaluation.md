# Codex 阶段 Prompt：P18 CoursePilot 与系统正式评测

请在 **Plan 模式**执行本阶段。先完成审计和计划，不要在计划获批前修改代码。

## 阶段目标

完成 Agent-Isolated 和 Integrated System 冻结评测，形成可用于 README/简历的可信结果。

## 前置依赖

- 阶段依赖：P14-P17
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

- P18-T01: 完成 CP-DS0—CP-DS8、SYS-DS1 正式数据；Lesson/Exam/PPT 各 10，Dev 18/Test 12。
- P18-T02: 冻结 CourseRAG ContextPackage/KP/Evidence Fixtures，运行 Track A。
- P18-T03: 运行 CP-B0 与 CP-B10、Validation/Repair、Interrupt、Export、Model Routing 和 Exam Parallel。
- P18-T04: 执行盲化人工评分、Edit Burden、题目状态和 PPT 页面检查；记录评审一致性。
- P18-T05: 连接正式 CourseRAG Test Index，运行 Track B Journey、故障和安全场景。
- P18-T06: 汇总 P50/P95、Token、成本、人工分钟、Recovery、Trace 和错误分类。
- P18-T07: 生成完整报告、错误案例、限制和可追溯 Manifest。
- P18-T08: 从锁定结果提取 README/简历可用指标，不夸大。

## 主要代码区域

- `datasets/coursepilot_eval/`
- `src/coursepilot/evals/`
- `reports/`
- `human_review/`

## 明确禁止

- 不得使用 Test 调参
- 不得填造 X/Y 指标
- 不得使用 LLM-as-a-Judge
- 不得将 Fallback 样本计入真实质量
- 不执行 P18 之后阶段的业务实现；只允许建立当前阶段必需的接口或 TODO。
- 不自行改变冻结产品决策。发现不兼容时写入 Decision Log 候选并说明最小安全默认方案。

## 必须验证

- Locked Test Guard
- Report Reproducibility
- Human Review Completeness
- Metric Cross-check
- 运行主测试、Ruff 和 Mypy；如存在既有失败，提供证据并运行阶段专项测试。
- 检查 Secret、临时文件、未说明 Fallback 和破坏性迁移。

## Exit Gate

- 必须门槛全部达到或明确记录未达项
- Test 配置冻结
- 所有公开指标可追溯

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
