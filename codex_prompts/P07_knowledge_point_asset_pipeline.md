# Codex 阶段 Prompt：P07 课程级知识点资产流水线

请在 **Plan 模式**执行本阶段。先完成审计和计划，不要在计划获批前修改代码。

## 阶段目标

将每 Chunk 临时关键词改造成 Section Window 级、持久化、可审核、可复用的知识点资产。

## 前置依赖

- 阶段依赖：P06
- 读取 `docs/refactor/EXECUTION_STATUS.md`，确认上游 Exit Gate 已通过。
- 检查当前 Git 状态并记录起始 Commit；不要覆盖用户未提交修改。

## 必须读取的文档

- `docs/refactor/frozen_v1.0/00_Document_Index_and_Decision_Baseline_v1.0.md`
- `docs/refactor/frozen_v1.0/07_Implementation_Roadmap_and_Task_Backlog_v1.0.md`
- `docs/refactor/frozen_v1.0/02_CourseRAG_PRD_v1.0.md`
- `docs/refactor/frozen_v1.0/03_CourseRAG_Evaluation_Dataset_and_Baseline_v1.0.md`
- `docs/refactor/frozen_v1.0/03A_CourseRAG_Evaluation_Dataset_Construction_Guide_v1.0.md`
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

- P07-T01: 实现 Section/Parent Window Builder 和批量结构化抽取 Schema。
- P07-T02: 实现 Provider 并发、重试、Prompt/Model/Window Hash 缓存和失败窗口重跑。
- P07-T03: 实现名称规范化、Alias、无效候选过滤、Section 内去重和课程级归并候选。
- P07-T04: 实现 KnowledgePoint、EvidenceLink、ChunkLink、ReviewAction 和可选 Parent。
- P07-T05: 实现由 evidence/naming/cross-window/ambiguity/duplicate 组成的 publish_score。
- P07-T06: 在 Dev Gold 校准默认 0.75 阈值，保留 unreviewed/needs_review/approved/rejected/deprecated。
- P07-T07: 实现列表、详情、批准、拒绝、合并、拆分和修改 API。
- P07-T08: 完成 DS3 Pilot、调用次数/成本对比，验证不再按 Child Chunk 单独调用。

## 主要代码区域

- `src/courserag/knowledge_points/`
- `src/courserag/application/knowledge_point_service.py`
- `src/courserag/api/knowledge_points.py`

## 明确禁止

- 不构建完整知识图谱
- 不把模型自报 confidence 直接当发布概率
- 普通在线检索不得触发 KP 抽取
- 不执行 P07 之后阶段的业务实现；只允许建立当前阶段必需的接口或 TODO。
- 不自行改变冻结产品决策。发现不兼容时写入 Decision Log 候选并说明最小安全默认方案。

## 必须验证

- KP Cache/Idempotency
- Normalize/Deduplicate
- Evidence Link Integrity
- Threshold Report
- 运行主测试、Ruff 和 Mypy；如存在既有失败，提供证据并运行阶段专项测试。
- 检查 Secret、临时文件、未说明 Fallback 和破坏性迁移。

## Exit Gate

- KP 与 Evidence/Chunk N:N 显式建模
- 抽取调用数相对 B0 明显下降
- 正式 Gold 由人工批准

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
