# Codex 阶段 Prompt：P06 Stable Evidence 与 Parent-Child Chunk

请在 **Plan 模式**执行本阶段。先完成审计和计划，不要在计划获批前修改代码。

## 阶段目标

建立稳定原文证据、Evidence Resolver 和基于语义边界的层级 Chunk。

## 前置依赖

- 阶段依赖：P04,P05
- 读取 `docs/refactor/EXECUTION_STATUS.md`，确认上游 Exit Gate 已通过。
- 检查当前 Git 状态并记录起始 Commit；不要覆盖用户未提交修改。

## 必须读取的文档

- `docs/refactor/frozen_v1.0/00_Document_Index_and_Decision_Baseline_v1.0.md`
- `docs/refactor/frozen_v1.0/07_Implementation_Roadmap_and_Task_Backlog_v1.0.md`
- `docs/refactor/frozen_v1.0/02_CourseRAG_PRD_v1.0.md`
- `docs/refactor/frozen_v1.0/03_CourseRAG_Evaluation_Dataset_and_Baseline_v1.0.md`
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

- P06-T01: 实现 EvidenceRecord、PageBBox、内容 Hash 和稳定 Evidence ID。
- P06-T02: 按定义、段落、列表、步骤、表格和示例等语义单元构建 Evidence。
- P06-T03: 实现 Evidence Resolver、Batch Resolver 和 Source Preview。
- P06-T04: 实现 Parent Chunk/Child Chunk、ChunkEvidenceLink、Parent Relationship 和版本化 Chunk Profile。
- P06-T05: 切分按 Section→Block→Paragraph/List/Table→Sentence→Token Limit 执行。
- P06-T06: 实现去重、邻接、超长 Block 和 OCR Evidence 处理。
- P06-T07: 建立引用迁移接口骨架，详细迁移在 P10 完成。
- P06-T08: 运行 DS2 Pilot 和 B1/B2 对比。

## 主要代码区域

- `src/courserag/evidence/`
- `src/courserag/chunking/`
- `src/courserag/domain/evidence.py`

## 明确禁止

- 不得将 Chunk ID 作为永久引用
- 不得在固定字符位置直接截断所有语义单元
- 不执行 P06 之后阶段的业务实现；只允许建立当前阶段必需的接口或 TODO。
- 不自行改变冻结产品决策。发现不兼容时写入 Decision Log 候选并说明最小安全默认方案。

## 必须验证

- Stable Evidence ID Test
- Chunk Boundary/Overlap Test
- Evidence Resolver Test
- Chunk Profile Change Test
- 运行主测试、Ruff 和 Mypy；如存在既有失败，提供证据并运行阶段专项测试。
- 检查 Secret、临时文件、未说明 Fallback 和破坏性迁移。

## Exit Gate

- Chunker 改变不导致原文 Evidence 丢失
- 所有 Context 项可解析回原文
- 语义完整率和冗余率可计算

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
