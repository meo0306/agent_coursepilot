# Codex 阶段 Prompt：P19 两仓物理拆分、CI/CD 与作品集发布

请先审计再实施。本阶段已经获得 Course Owner 对公开两仓、干净基线和 PostgreSQL 双
Schema 的批准；不得把作品集发布解释为 P18 正式质量 Gate 通过。

## 阶段目标

从当前 Monorepo 的精确检查点形成公开的 `meo0306/course-rag` 和
`meo0306/course-pilot`，使两个项目可独立安装、测试和构建，并能通过 HTTP 在同一
PostgreSQL 实例上完成可演示闭环。

## 前置状态

- P10 和 P17 核心工程/安全硬控制已完成；自动 Prompt Injection Profile 仍 rejected/default-off。
- P18 正式执行和人工审核已完成，但正式质量 Gate 失败且结果不可回流调参。
- Owner Disposition：`portfolio_release_with_known_limitations`；Production Release 继续阻塞。
- 拆仓前记录 Git 状态并形成只包含必要 P17/P18/P19 文件的 Source Checkpoint。

## 必须读取

- `AGENTS.md`
- `docs/refactor/EXECUTION_STATUS.md`
- `docs/refactor/QUALITY_GATE_POLICY.md`
- `docs/refactor/frozen_v1.0/01_CoursePilot_CourseRAG_Split_and_Refactor_Plan_v1.0.md`
- `docs/refactor/frozen_v1.0/04_CourseRAG_Technical_Refactor_Plan_v1.0.md`
- `docs/refactor/frozen_v1.0/05_CoursePilot_Agent_Engineering_Upgrade_Plan_v1.0.md`
- `docs/refactor/phase_reports/P18_coursepilot_system_formal_evaluation.md`

## 任务

- P18-CLOSE：记录 `execution_status=completed`、`formal_quality_gate=failed` 和作品集处置。
- P19-T01：从精确 Source Commit 创建两个干净 Git 仓库和 `PROVENANCE.md`。
- P19-T02：移除运行时跨仓 Python 导入；CoursePilot 默认 Remote HTTP，Unit Test 使用 Mock。
- P19-T03：共享 PostgreSQL Database，但使用 `coursepilot`/`courserag` 双 Schema、双 Role、双 Alembic Baseline。
- P19-T04：建立 OpenAPI v1、跨仓 Contract、两仓 CI、Docker Cold Start 和 Release Smoke。
- P19-T05：作者更新为 `meo0306`，保留原 MIT License 和上游 Attribution。
- P19-T06：完成两个 README、Quickstart、Demo、指标来源、安全和 Known Limitations。
- P19-T07：旧 CoursePilot 内部 RAG 设为可选 Deprecated 兼容能力，默认安装和运行路径不使用。
- P19-T08：输出面试材料、架构图、GHCR 镜像和公开 `v0.1.0` Release。

## 强制边界

- 不修改、重跑或根据已消费 P18 Test 调参。
- 不宣称 P18、自动 Prompt Injection Detector 或生产发布通过。
- 不共享 ORM、Session 或数据库表访问；跨服务只允许 HTTP。
- 不自动迁移或删除旧 `public` Schema 数据。
- 不提交 Secret、模型权重、Provider Cache、完整教材或无再分发许可的数据。
- 不移除 MIT License 或原作者 Attribution。
- 不静默切换 Remote/Local、Provider、模型、索引或 Fallback。

## Exit Gate

- 两个公开仓库可从干净 Checkout 安装、测试和构建；
- CoursePilot 不安装 CourseRAG Server 包也能通过 Remote Contract；
- 同库双 Schema 和跨 Role 拒绝验证通过；
- Docker 冷启动和主 Demo Journey 通过；
- README 的指标、失败项和限制均可追溯；
- 发布明确标记为 Portfolio/Engineering MVP，而非 Production Release。

阶段完成后更新状态、风险和本阶段报告，并输出两个 GitHub 地址和 Release 地址。
