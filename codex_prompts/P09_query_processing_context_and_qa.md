# Codex 阶段 Prompt：P09 Query Processing、Context Packing 与基础引用 QA

请在 **Plan 模式**执行本阶段。先完成审计和计划，不要在计划获批前修改代码。

## 阶段目标

完成可配置 Query Pipeline、Evidence-aware Context 和结构化 Claim-Evidence QA。

## 前置依赖

- 阶段依赖：P08
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

- P09-T01: 实现 Normalize、Filter Parser、KP Link、Alias Expansion、Router、可选 Multi-query、Low-recall Retry。
- P09-T02: 每个 QueryStep 可配置、可关闭、保留 Raw Query、Filter 和 Step Trace。
- P09-T03: 实现 Dense/Sparse Candidate 聚合、Evidence 去重、Parent/Neighbor Expansion 和 Purpose Policy。
- P09-T04: 实现 Token Budget Packing、Citation Map 和 Packing Report。
- P09-T05: 实现 Evidence Sufficiency Gate、QA Structured Output、AnswerClaim 和程序化 Citation Composer。
- P09-T06: 实现拒答、引用 ID 验证、Context 内证据校验和一次定向 Schema Repair。
- P09-T07: 完成 DS4/DS5 Pilot，运行 B6—B8 和 Q0—Q3。
- P09-T08: 输出 Search、Context、QA 三类稳定 API。

## 主要代码区域

- `src/courserag/query/`
- `src/courserag/context/`
- `src/courserag/qa/`

## 明确禁止

- 不做开放网络搜索
- 不做通用聊天或复杂多轮记忆
- 不使用 LLM-as-a-Judge
- 不执行 P09 之后阶段的业务实现；只允许建立当前阶段必需的接口或 TODO。
- 不自行改变冻结产品决策。发现不兼容时写入 Decision Log 候选并说明最小安全默认方案。

## 必须验证

- Query Step Unit/Toggle Test
- Filter Preserve/Rewrite Guard
- Context Token/Dedup Test
- QA Citation/Abstention Test
- 运行主测试、Ruff 和 Mypy；如存在既有失败，提供证据并运行阶段专项测试。
- 检查 Secret、临时文件、未说明 Fallback 和破坏性迁移。

## Exit Gate

- 每项 Query Processing 可消融
- QA Claim 均绑定有效 Evidence
- 不可回答样本可正确拒答

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
