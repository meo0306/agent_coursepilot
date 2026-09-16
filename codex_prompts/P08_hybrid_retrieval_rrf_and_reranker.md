# Codex 阶段 Prompt：P08 Hybrid Retrieval、RRF 与专用 Reranker

请在 **Plan 模式**执行本阶段。先完成审计和计划，不要在计划获批前修改代码。

## 阶段目标

实现版本化 Dense + BM25 + Fusion + 专用 Reranker，并完整记录各阶段分数。

## 前置依赖

- 阶段依赖：P06,P07
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

- P08-T01: 实现 DenseRetrieverPort 和版本化 Chroma Adapter，批量 Embedding，完整正文回源 PostgreSQL/Artifact。
- P08-T02: 实现 BM25S 索引、中文搜索分词、英文/数字/特殊术语保留与字符二元组兜底。
- P08-T03: 实现 RRF 和可选加权融合，保留 Dense/Sparse Rank/Score/Fusion Trace。
- P08-T04: 实现 Cohere/Voyage/Jina/Local CrossEncoder 等统一 Reranker Port，默认通过环境 API。
- P08-T05: 实现 Candidate-K、Top-N、Batch、Truncation、Timeout、Retry 和生产/评测不同 Fallback Policy。
- P08-T06: 实现 Course/Document/Section/KP/SourceTier/Version Filter。
- P08-T07: 在 DS5 Dev 比较 B3—B5、Provider、P95 和成本；冻结模型和阈值。
- P08-T08: 完善 SearchResponse、RetrievalRun 和 Debug Trace。

## 主要代码区域

- `src/courserag/retrieval/`
- `src/courserag/indexing/`
- `src/courserag/providers/reranker.py`

## 明确禁止

- 不使用聊天 LLM 作为默认 Reranker
- 不在代码硬编码 Provider/Model
- 不直接比较不同 Provider 的绝对阈值
- 不执行 P08 之后阶段的业务实现；只允许建立当前阶段必需的接口或 TODO。
- 不自行改变冻结产品决策。发现不兼容时写入 Decision Log 候选并说明最小安全默认方案。

## 必须验证

- Dense/Sparse Index Contract
- RRF Unit Test
- Reranker Adapter Contract
- Filter Isolation
- Staging Publish
- 运行主测试、Ruff 和 Mypy；如存在既有失败，提供证据并运行阶段专项测试。
- 检查 Secret、临时文件、未说明 Fallback 和破坏性迁移。

## Exit Gate

- Hybrid/Rerank 可独立消融
- 正式 Eval 失败不静默回退
- 索引版本与查询结果一致

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
