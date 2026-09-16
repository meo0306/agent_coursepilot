# Codex 阶段 Prompt：P10 CourseRAG 增量、写回、安全与正式评测

请在 **Plan 模式**执行本阶段。先完成审计和计划，不要在计划获批前修改代码。

## 阶段目标

完成 Section 级增量、Citation Migration、Verified Content、完整安全控制和 CourseRAG 冻结评测。

## 前置依赖

- 阶段依赖：P03-P09
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

- P10-T01: 实现 DocumentVersion/Section Diff 和变更影响范围规划。
- P10-T02: 实现 Evidence 精确/结构/相似候选迁移及 valid/migrated/needs_review/invalid。
- P10-T03: 实现白名单 VerifiedContent、独立 SourceTier、即时轻量索引、撤销和幂等。
- P10-T04: 实现 10 条/3000 Tokens/24h/人工触发的 Enrichment Batch 和 KP 归并。
- P10-T05: 实现 MIME、ZIP Bomb、加密 PDF、路径、页数/DPI/Timeout、ACL、跨课程隔离和 Prompt Injection 标记。
- P10-T06: 完成 DS0—DS8 正式数据，Dev 调参后冻结 Test。
- P10-T07: 运行 B0—B8、Q0—Q3、增量、性能、安全和错误分析。
- P10-T08: 更新 CourseRAG README、API、架构图和限制说明。

## 主要代码区域

- `src/courserag/jobs/`
- `src/courserag/evidence/migration.py`
- `src/courserag/application/writeback_service.py`
- `src/courserag/security/`
- `datasets/courserag_eval/`

## 明确禁止

- 不得将整份教案/试卷/PPT 任意写回
- 不得覆盖 Primary Source
- 不得在看完 Test 后调阈值
- 不执行 P10 之后阶段的业务实现；只允许建立当前阶段必需的接口或 TODO。
- 不自行改变冻结产品决策。发现不兼容时写入 Decision Log 候选并说明最小安全默认方案。

## 必须验证

- Citation Migration
- Incremental Reuse
- Writeback/Revoke/Batch
- Security/Fault Injection
- Locked Test
- 运行主测试、Ruff 和 Mypy；如存在既有失败，提供证据并运行阶段专项测试。
- 检查 Secret、临时文件、未说明 Fallback 和破坏性迁移。

## Exit Gate

- Test 无 Gold 泄漏和静默 Fallback
- 安全零容忍指标为 0
- CourseRAG Port/Contract 冻结供 CoursePilot 使用

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
