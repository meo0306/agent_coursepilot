# CoursePilot / CourseRAG 冻结文档索引与决策基线

**文档版本：** v1.0  
**文档状态：** 冻结执行版  
**冻结日期：** 2026-07-22  
**适用仓库起点：** `meo0306/agent_coursepilot`

---

## 1. 冻结文档集

| 编号 | 文件 | 权威范围 |
|---|---|---|
| 01 | `01_CoursePilot_CourseRAG_Split_and_Refactor_Plan_v1.0.md` | 项目边界、数据所有权、服务合同、拆分与部署原则 |
| 02 | `02_CourseRAG_PRD_v1.0.md` | CourseRAG 产品目标、功能范围、MVP 和验收 |
| 03 | `03_CourseRAG_Evaluation_Dataset_and_Baseline_v1.0.md` | CourseRAG Gold、指标、基线、消融和测试口径 |
| 03A | `03A_CourseRAG_Evaluation_Dataset_Construction_Guide_v1.0.md` | DS0—DS8 的人工/候选数据构造流程 |
| 04 | `04_CourseRAG_Technical_Refactor_Plan_v1.0.md` | CourseRAG 模块、数据模型、任务流、API 和迁移 |
| 05 | `05_CoursePilot_Agent_Engineering_Upgrade_Plan_v1.0.md` | Agent Runtime、Graph、Interrupt、Validation、Repair、模板和模型路由 |
| 06 | `06_CoursePilot_and_System_Evaluation_Plan_v1.0.md` | CoursePilot 与系统级数据、基线、人工 Rubric 和验收 |
| 07 | `07_Implementation_Roadmap_and_Task_Backlog_v1.0.md` | 具体阶段顺序、任务、测试、交付物和 Exit Gate |
| 08 | `08_Codex_Execution_Guide_and_Phase_Prompts_v1.0.md` | 如何把文档交给 Codex，以及逐阶段执行方式 |

## 2. 冲突处理优先级

当文档之间看起来存在冲突时，按以下顺序处理：

1. 本文档的冻结决策和明确 Change Control；
2. 01 中的项目边界、数据所有权和跨服务合同；
3. 02 中的 CourseRAG 产品需求和非目标；
4. 04、05 中的具体技术设计；
5. 03、03A、06 中的评测口径；
6. 07 中的执行顺序和阶段范围；
7. 08 中的 Codex 操作方法。

代码现状是迁移起点和事实证据，但不能覆盖已冻结的目标设计。若目标设计与仓库事实不兼容，应记录 ADR 和迁移方案，而不是静默改变需求。

## 3. 已冻结的关键决策

### 项目边界

- 先在当前仓库逻辑拆分，最后物理拆为 CourseRAG 与 CoursePilot 两个仓库；
- CoursePilot 只通过稳定 Port/HTTP Client 使用 CourseRAG；
- CoursePilot 不直接导入 Parser、Chunker、Vector Store 或 Sparse Index 内部实现；
- PostgreSQL 保存事实数据，Dense/Sparse Index 是可重建派生物；
- CoursePilot 拥有业务 Course，CourseRAG 将其作为外部 Namespace/Course ID。

### CourseRAG

- MVP 只支持 PDF、DOCX；
- OCR 按页路由并保留坐标、置信度和来源；
- DOCX 通过固定 Renderer Profile 形成可复现分页快照，并同时保留结构 Anchor；
- Evidence 先于 Chunk，引用绑定 Evidence，不绑定当前 Chunk ID；
- 使用 Parent-Child Chunk；
- 知识点按 Section/Parent Window 离线抽取、缓存、持久化和人工审核；
- 不在 MVP 构建完整知识图谱，只支持 Alias 和可选 Parent；
- 默认知识点发布阈值 0.75，但必须在 Dev Gold 校准；
- Chroma 在 MVP 保留并通过 Port 隔离；
- Sparse 默认 BM25S，Fusion 默认 RRF；
- Reranker 默认使用专用 Rerank 模型/API，不使用通用聊天 LLM；
- Query Processing 可配置、可追踪、可消融；
- 基础引用 QA 纳入 MVP，输出 Claim—Evidence 并支持拒答；
- Verified Writeback 只允许 `verified_question`、`verified_answer_explanation`、`verified_lesson_fragment`；
- 写回立即持久化，知识点富化按 10 条、3000 Tokens、24 小时或人工触发批处理。

### CoursePilot

- 教案、试卷、PPT 使用 workflow-first LangGraph；
- 使用 PostgreSQL Checkpointer、稳定 Thread 和 Artifact Version；
- 六个正式 Interrupt：Lesson Plan/Final、Exam Blueprint/Global、PPT Architecture/Final；
- 导出批准和写回批准分离；
- Validation 使用 L0—L4 分层 `ValidationIssue`；
- Repair 使用允许路径和 Targeted Patch，不默认整件重写；
- 试卷按 Question Batch Fan-out/Fan-in，并在聚合后做全局校验；
- 系统提供 9 个逻辑内置模板和默认 DOCX/PPTX 资源；用户模板不是启动前置条件；
- MVP 只要求 Main/Light 两类实际模型，多个逻辑 Profile 可映射到两者；
- 不无条件发送 `reasoning_effort` 或 `thinking`，按 Provider Capability 配置；
- PPT 目标是可编辑教学初稿，不承诺商业级视觉成品；
- 完整教案、整套试卷和整份 PPT 不得直接作为写回对象。

### 评测

- 不使用 LLM-as-a-Judge；
- GPT 可生成候选，但正式 Gold 必须人工批准；
- CourseRAG Gold 绑定原文 Span/Evidence；
- CoursePilot 使用约束 + Evidence + 人工 Rubric，不构造唯一全文 Gold；
- Agent-Isolated 与 Integrated System 分轨评测；
- 正式模型评测禁用静默 Deterministic Fallback；
- Pilot、Dev、Test 分离，Test 不用于调参；
- 只有锁定 Test、真实模型和人工审核结果可以用于 README/简历。

## 4. Change Control

冻结文档在执行期间原则上只读。需要改变产品边界、合同、Gold 口径或阶段范围时：

1. 在 `docs/refactor/DECISION_LOG.md` 建立编号决策；
2. 说明触发原因、受影响文档、备选方案、兼容和迁移影响；
3. 经人工确认后发布 v1.1 或更高版本；
4. 更新本索引、文件 Hash 和后续阶段 Prompt；
5. 不直接覆盖 v1.0 文件。

普通代码实现细节、参数调优结果和无合同影响的重构，只记录在阶段报告，不需要修改冻结文档。

## 5. 人工责任边界

Codex 可以实现工具、生成候选和准备报告，但以下事项必须保留人工确认：

- 正式 Gold Dataset 的批准；
- Knowledge Point 的正式 Gold、合并/拆分边界和重要性；
- CoursePilot 教案、试题和 PPT 的人工 Rubric；
- OCR、Reranker、Main/Light 模型最终选型；
- 用户自定义 DOCX/PPTX 模板字段映射；
- Interrupt 中的业务批准；
- Test 结果是否可用于简历或公开材料。

## 6. 不得提前实施的事项

- P19 前不得物理拆仓；
- P10 接口冻结前不得让 CoursePilot 大规模依赖未稳定的 CourseRAG 内部实现；
- 未建立 Gold/Runner 前不得声称检索或 Agent 质量提升；
- 未经明确授权不得提交、推送、创建 PR、删除数据或执行破坏性迁移；
- 不得用占位输出、静默 Fallback 或跳过测试让阶段 Gate 看似通过。
