# Codex 阶段 Prompt：P19 物理拆仓、CI/CD 与作品集收尾

请在 **Plan 模式**执行本阶段。先完成审计和计划，不要在计划获批前修改代码。

## 阶段目标

在逻辑边界和接口稳定后形成独立 CourseRAG/CoursePilot 仓库和可演示部署。

## 前置依赖

- 阶段依赖：P10,P18
- 读取 `docs/refactor/EXECUTION_STATUS.md`，确认上游 Exit Gate 已通过。
- 检查当前 Git 状态并记录起始 Commit；不要覆盖用户未提交修改。

## 必须读取的文档

- `docs/refactor/frozen_v1.0/00_Document_Index_and_Decision_Baseline_v1.0.md`
- `docs/refactor/frozen_v1.0/07_Implementation_Roadmap_and_Task_Backlog_v1.0.md`
- `docs/refactor/frozen_v1.0/01_CoursePilot_CourseRAG_Split_and_Refactor_Plan_v1.0.md`
- `docs/refactor/frozen_v1.0/04_CourseRAG_Technical_Refactor_Plan_v1.0.md`
- `docs/refactor/frozen_v1.0/05_CoursePilot_Agent_Engineering_Upgrade_Plan_v1.0.md`
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

- P19-T01: 提取 CourseRAG 独立仓库、迁移历史或保留清晰来源记录。
- P19-T02: CoursePilot 生产 Profile 使用 Remote Client，Demo/Test 可使用 Local/Mock。
- P19-T03: 建立独立 PostgreSQL Schema/Database、Worker、Storage、Chroma/BM25 和 Docker Compose。
- P19-T04: 建立两仓 Contract Test、API Schema 兼容检查和端到端 CI。
- P19-T05: 更新 Package Name/Author 为当前项目作者，同时保留 MIT License 和上游 Attribution。
- P19-T06: 完善 README：架构、Quickstart、Demo、评测、限制、安全、截图和数据构造说明。
- P19-T07: 标记旧内部 RAG 代码 Deprecated，给出删除条件，不在无迁移路径时立即删除。
- P19-T08: 输出面试讲解材料、架构图和最终 Release Tag。

## 主要代码区域

- `course-rag repo`
- `course-pilot repo`
- `compose.yaml`
- `.github/workflows/`
- `README`
- `LICENSE`
- `pyproject.toml`

## 明确禁止

- 不得在合同未冻结前拆仓
- 不得破坏 MIT License/上游归属
- 不得删除迁移说明和旧版本兼容记录
- 不执行 P19 之后阶段的业务实现；只允许建立当前阶段必需的接口或 TODO。
- 不自行改变冻结产品决策。发现不兼容时写入 Decision Log 候选并说明最小安全默认方案。

## 必须验证

- 两仓 Unit/Contract/Integration
- Docker Cold Start
- CI Clean Checkout
- Release Smoke Test
- 运行主测试、Ruff 和 Mypy；如存在既有失败，提供证据并运行阶段专项测试。
- 检查 Secret、临时文件、未说明 Fallback 和破坏性迁移。

## Exit Gate

- 干净环境可启动
- 合同测试跨仓通过
- 最终指标和限制公开可信

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
