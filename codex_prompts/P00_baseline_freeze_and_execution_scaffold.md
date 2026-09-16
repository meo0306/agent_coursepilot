# Codex 阶段 Prompt：P00 冻结基线与执行脚手架

请在 **Plan 模式**执行本阶段。先完成审计和计划，不要在计划获批前修改代码。

## 阶段目标

建立不可丢失的 B0、文档执行秩序和阶段状态文件；此阶段不改变产品行为。

## 前置依赖

- 阶段依赖：无
- 读取 `docs/refactor/EXECUTION_STATUS.md`，确认上游 Exit Gate 已通过。
- 检查当前 Git 状态并记录起始 Commit；不要覆盖用户未提交修改。

## 必须读取的文档

- `docs/refactor/frozen_v1.0/00_Document_Index_and_Decision_Baseline_v1.0.md`
- `docs/refactor/frozen_v1.0/07_Implementation_Roadmap_and_Task_Backlog_v1.0.md`
- `docs/refactor/frozen_v1.0/01_CoursePilot_CourseRAG_Split_and_Refactor_Plan_v1.0.md`
- `docs/refactor/frozen_v1.0/03_CourseRAG_Evaluation_Dataset_and_Baseline_v1.0.md`
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

- P00-T01: 记录当前 `main` Commit、Python/依赖锁文件、数据库迁移头、环境变量清单和启动命令。
- P00-T02: 在仓库建立 `docs/refactor/frozen_v1.0/`，复制 00—08 冻结文档；原讨论稿保留但不再作为执行依据。
- P00-T03: 建立 `docs/refactor/EXECUTION_STATUS.md`、`DECISION_LOG.md`、`RISK_REGISTER.md` 和 `phase_reports/PHASE_REPORT_TEMPLATE.md`。
- P00-T04: 为当前 PDF/DOCX 构建、Dense Search、教案、试卷、PPT、导出、审核写回建立 B0 Smoke Test。
- P00-T05: 运行并保存当前真实模型评测或至少保存可复现的 B0 Runner/Manifest；Gold 不得由 Top-K 结果反推。
- P00-T06: 记录当前 API、ORM 表、Pydantic Schema、Graph 节点、Prompt Hash 和导出文件样例。
- P00-T07: 确认 MIT License 与上游归属保留；记录后续更新包作者元数据的任务，不在本阶段删除归属信息。

## 主要代码区域

- `README.md`
- `README.zh-CN.md`
- `CoursePilot_markdown_docs/`
- `tests/coursepilot/`
- `src/coursepilot/evals/`
- `compose.eval.yaml`
- `pyproject.toml`

## 明确禁止

- 不得重构 RAG 或 Agent 业务逻辑
- 不得删除旧评测、旧 Chroma Collection 或旧数据表
- 不得修改公开 API 行为
- 不执行 P00 之后阶段的业务实现；只允许建立当前阶段必需的接口或 TODO。
- 不自行改变冻结产品决策。发现不兼容时写入 Decision Log 候选并说明最小安全默认方案。

## 必须验证

- `uv run pytest -q`
- `uv run ruff format --check`
- `uv run ruff check`
- `uv run mypy src/`
- 现有 deterministic eval 可运行并保存报告
- 运行主测试、Ruff 和 Mypy；如存在既有失败，提供证据并运行阶段专项测试。
- 检查 Secret、临时文件、未说明 Fallback 和破坏性迁移。

## Exit Gate

- 主测试、Lint、Type Check 通过
- 现有端到端 Demo 未退化
- B0 结果和输入 Hash 可追溯

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
