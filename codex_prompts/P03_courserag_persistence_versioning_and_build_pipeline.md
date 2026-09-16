# Codex 阶段 Prompt：P03 CourseRAG 持久化、版本与构建流水线

请在 **Plan 模式**执行本阶段。先完成审计和计划，不要在计划获批前修改代码。

## 阶段目标

建立 PostgreSQL 事实源、文档版本、构建 Stage、Artifact Cache 和 Index Version 原子发布能力。

## 前置依赖

- 阶段依赖：P01,P02
- 读取 `docs/refactor/EXECUTION_STATUS.md`，确认上游 Exit Gate 已通过。
- 检查当前 Git 状态并记录起始 Commit；不要覆盖用户未提交修改。

## 必须读取的文档

- `docs/refactor/frozen_v1.0/00_Document_Index_and_Decision_Baseline_v1.0.md`
- `docs/refactor/frozen_v1.0/07_Implementation_Roadmap_and_Task_Backlog_v1.0.md`
- `docs/refactor/frozen_v1.0/02_CourseRAG_PRD_v1.0.md`
- `docs/refactor/frozen_v1.0/04_CourseRAG_Technical_Refactor_Plan_v1.0.md`
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

- P03-T01: 实现 KnowledgeBase、SourceDocument、DocumentVersion、ParsedDocument、BuildJob、BuildStageRun、IndexVersion 等 ORM。
- P03-T02: 实现 Section/Block/Evidence/Chunk/KP/Writeback/Run 所需表的第一版迁移和索引。
- P03-T03: 建立 Repository 层，不允许 Application Service 散落 SQLAlchemy 查询。
- P03-T04: 实现 BuildStage 接口、Fingerprint、Artifact URI/Hash、Cache Hit、Retry 和 Stage 状态。
- P03-T05: 复用当前数据库 Worker/Lease/Idempotency，支持 Stage 级恢复和手动重跑。
- P03-T06: 实现 Staging Dense/Sparse Manifest、校验和 Active Pointer 事务切换；失败不影响旧 Active Index。
- P03-T07: 实现 Artifact/孤儿 Staging 清理策略和审计日志。
- P03-T08: 为旧 `Document`/Task 建立兼容映射，但新事实表使用 `courserag_*` 命名。

## 主要代码区域

- `src/courserag/persistence/`
- `src/courserag/jobs/`
- `alembic/`
- `src/courserag/indexing/version_manager.py`

## 明确禁止

- 不实现最终 Parser/OCR 算法
- 不迁移旧 Chunk 为 Evidence
- 不替换 Chroma
- 不执行 P03 之后阶段的业务实现；只允许建立当前阶段必需的接口或 TODO。
- 不自行改变冻结产品决策。发现不兼容时写入 Decision Log 候选并说明最小安全默认方案。

## 必须验证

- Alembic upgrade/downgrade Test
- Stage Fingerprint/Cache Test
- Worker Lease Recovery Test
- Index Active Pointer Atomicity Test
- 运行主测试、Ruff 和 Mypy；如存在既有失败，提供证据并运行阶段专项测试。
- 检查 Secret、临时文件、未说明 Fallback 和破坏性迁移。

## Exit Gate

- 相同输入可复用 Stage
- 构建失败不破坏 Active Index
- Worker 崩溃可接管且不重复副作用

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
