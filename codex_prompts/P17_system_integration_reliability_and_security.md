# Codex 阶段 Prompt：P17 系统集成、可靠性、安全与写回闭环

请在 **Plan 模式**执行本阶段。先完成审计和计划，不要在计划获批前修改代码。

## 阶段目标

连接真实 CourseRAG，验证端到端 Version/Trace、错误隔离、写回闭环和安全零容忍指标。

## 前置依赖

- 阶段依赖：P10,P14-P16
- 读取 `docs/refactor/EXECUTION_STATUS.md`，确认上游 Exit Gate 已通过。
- 检查当前 Git 状态并记录起始 Commit；不要覆盖用户未提交修改。

## 必须读取的文档

- `docs/refactor/frozen_v1.0/00_Document_Index_and_Decision_Baseline_v1.0.md`
- `docs/refactor/frozen_v1.0/07_Implementation_Roadmap_and_Task_Backlog_v1.0.md`
- `docs/refactor/frozen_v1.0/01_CoursePilot_CourseRAG_Split_and_Refactor_Plan_v1.0.md`
- `docs/refactor/frozen_v1.0/04_CourseRAG_Technical_Refactor_Plan_v1.0.md`
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

- P17-T01: 实现 RemoteCourseRAGClient 完整 HTTP 调用、Timeout/Retry/Request ID 和错误映射。
- P17-T02: CoursePilot Task 保存 CourseRAG Retrieval/Context Trace、Index Version、Evidence Version。
- P17-T03: 实现 Stale Evidence/Index 检测，导出或写回前不兼容则要求重审。
- P17-T04: 打通 Approval→VerifiedContent→Enrichment Batch→新 Index→后续任务检索闭环。
- P17-T05: 实现 CourseRAG/Model/Graph/Validator/Exporter/Writeback 错误隔离和用户错误码。
- P17-T06: 实现 Prompt Injection、跨课程、未授权写回、Secret Trace、路径穿越和超长反馈测试。
- P17-T07: 实现 Worker/Checkpoint/Export/Writeback 故障注入和幂等恢复。
- P17-T08: 运行 SYS-DS1 Pilot Journey。

## 主要代码区域

- `compose.yaml`
- `src/coursepilot/integration/`
- `src/courserag/api/`
- `tests/system/`
- `observability/`

## 明确禁止

- 不把 Track B 问题混作 Agent 单独质量
- 不得共享数据库绕过 API/Port
- 不得允许跨课程 Evidence
- 不执行 P17 之后阶段的业务实现；只允许建立当前阶段必需的接口或 TODO。
- 不自行改变冻结产品决策。发现不兼容时写入 Decision Log 候选并说明最小安全默认方案。

## 必须验证

- Remote Contract
- Trace/Version Continuity
- Writeback Loop
- Fault/Security/Idempotency
- 运行主测试、Ruff 和 Mypy；如存在既有失败，提供证据并运行阶段专项测试。
- 检查 Secret、临时文件、未说明 Fallback 和破坏性迁移。

## Exit Gate

- 跨课程/未授权/Secret/重复副作用均为 0
- Trace 可跨服务追踪
- 写回来源完整

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
