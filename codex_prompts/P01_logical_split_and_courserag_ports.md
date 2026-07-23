# Codex 阶段 Prompt：P01 逻辑拆分与 CourseRAG Port

请在 **Plan 模式**执行本阶段。先完成审计和计划，不要在计划获批前修改代码。

## 阶段目标

建立 CoursePilot—CourseRAG 稳定边界，同时保持现有业务接口和行为兼容。

## 前置依赖

- 阶段依赖：P00
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

- P01-T01: 新建 `src/courserag/` 包骨架及 domain/application/api/infrastructure 分层。
- P01-T02: 实现冻结文档定义的 KnowledgeBase、Retrieval、Evidence、VerifiedContent、QA、ServiceInfo Port/DTO。
- P01-T03: DTO 中分离 RequestContext/ResponseMeta 与领域 Payload，统一错误码、UTC 时间、Request/Trace ID。
- P01-T04: 实现 `LocalCourseRAGAdapter`，内部委托旧 KnowledgeBaseService/Chroma，暂不改变检索算法。
- P01-T05: 实现 `MockCourseRAGService`，支持 Lesson/Exam/PPT 单元测试。
- P01-T06: 建立 `RemoteCourseRAGClient` 接口和 HTTP Schema，但可先用 Stub/Contract Fake。
- P01-T07: 将 CoursePilot 业务服务中的直接 RAG 调用逐步替换为 Port；保留旧 `/api/coursepilot/*` Endpoint。
- P01-T08: 建立 Local、Remote、Mock 共用 Contract Test；验证序列化、错误和幂等合同。

## 主要代码区域

- `src/courserag/`
- `src/coursepilot/ports/`
- `src/coursepilot/adapters/`
- `src/coursepilot/clients/`
- `src/coursepilot/services/kb_service.py`
- `tests/contracts/`

## 明确禁止

- 不得开始新 Parser/OCR/Hybrid Retrieval
- 不得让 CoursePilot 直接依赖新 CourseRAG 内部模块
- 不得物理拆仓
- 不执行 P01 之后阶段的业务实现；只允许建立当前阶段必需的接口或 TODO。
- 不自行改变冻结产品决策。发现不兼容时写入 Decision Log 候选并说明最小安全默认方案。

## 必须验证

- 旧 API 回归测试
- Local/Remote/Mock Contract Test
- CoursePilot 三条旧 Graph Smoke Test
- 运行主测试、Ruff 和 Mypy；如存在既有失败，提供证据并运行阶段专项测试。
- 检查 Secret、临时文件、未说明 Fallback 和破坏性迁移。

## Exit Gate

- CoursePilot 节点不新增对 Chroma/Parser 的直接导入
- 旧 API 响应兼容
- 三种实现通过同一合同测试

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
