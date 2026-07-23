# Codex 阶段 Prompt：P11 CoursePilot 核心合同、Artifact、模板与模型网关

请在 **Plan 模式**执行本阶段。先完成审计和计划，不要在计划获批前修改代码。

## 阶段目标

建立 CoursePilot 新运行时的 Typed State、Artifact Version、Template Registry 和 Main/Light Model Gateway。

## 前置依赖

- 阶段依赖：P01,P10
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

- P11-T01: 将 CourseRAG Port 接入 CoursePilot，移除新代码对旧 Rag/Chroma 的直接依赖。
- P11-T02: 实现 BusinessTask、ArtifactRef/Version、NodeResult、CommonGraphState、RunContext。
- P11-T03: 建立 Task/Artifact/NodeRun/Approval/TemplateSnapshot/ModelInvocation ORM 与迁移。
- P11-T04: 实现 TemplateDefinition、Registry、Snapshot、9 个内置逻辑模板及默认 DOCX/PPTX 资源骨架。
- P11-T05: 实现 ModelGateway、Provider Capability、Main/Light Profile、Prompt Hash、Usage/Cost 和显式 Escalation。
- P11-T06: 对不支持 reasoning/thinking 的 Provider 不发送参数；正式 Eval 禁止静默模型切换。
- P11-T07: 实现 ContextPackageRef 和 State Compaction 基础设施。
- P11-T08: 为现有服务提供兼容 Adapter，使旧 API 在迁移期间仍可运行。

## 主要代码区域

- `src/coursepilot/domain/`
- `src/coursepilot/runtime/`
- `src/coursepilot/templates/`
- `src/coursepilot/models_gateway/`
- `resources/templates/`

## 明确禁止

- 不立即重写三条业务 Graph
- 不再在 CoursePilot 内抽取课程知识点
- 不硬编码 reasoning/thinking 参数
- 不执行 P11 之后阶段的业务实现；只允许建立当前阶段必需的接口或 TODO。
- 不自行改变冻结产品决策。发现不兼容时写入 Decision Log 候选并说明最小安全默认方案。

## 必须验证

- Typed State/Artifact Version
- Template Snapshot Reproducibility
- Model Capability/Route
- 旧 Service Compatibility
- 运行主测试、Ruff 和 Mypy；如存在既有失败，提供证据并运行阶段专项测试。
- 检查 Secret、临时文件、未说明 Fallback 和破坏性迁移。

## Exit Gate

- 任务可追溯到 Template/Prompt/Model/Artifact Version
- Main/Light 可映射同一或不同模型
- 现有 API 未中断

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
