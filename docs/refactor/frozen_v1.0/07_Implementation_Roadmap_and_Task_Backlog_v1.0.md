# CoursePilot / CourseRAG 分阶段开发任务清单

**文档版本：** v1.0  
**文档状态：** 冻结执行版  
**冻结日期：** 2026-07-22  
**适用仓库起点：** `meo0306/agent_coursepilot`  
**执行方式：** 一阶段一分支/PR，一阶段一验收报告；先逻辑拆分，后物理拆仓。

---

## 1. 使用规则

1. 本清单只定义“按什么顺序做、每阶段做到什么程度”；产品边界以 01/02，技术细节以 04/05，评测口径以 03/03A/06 为准。
2. 每次只授权 Codex 执行一个阶段；后续阶段只允许建立接口或 TODO，不得提前实现。
3. 每阶段先审计现状并形成计划，再修改代码；不能依据文档猜测仓库中不存在的实现。
4. 每阶段结束必须更新 `EXECUTION_STATUS.md`、`DECISION_LOG.md` 和阶段报告。
5. 任何范围变化、依赖替换或合同变更先写 ADR/Decision Log，再实施。
6. 所有真实模型评测禁用静默 Deterministic Fallback；所有 Test 数据禁止调参。
7. 任何写入、导出、索引发布和审核写回必须幂等；安全零容忍指标不得通过忽略测试规避。

## 2. 阶段总览

| 阶段 | 名称 | 轨道 | 依赖 | 复杂度 | 核心门禁 |
|---|---|---|---|---|---|
| P00 | 冻结基线与执行脚手架 | 共同基础 | 无 | M | 主测试、Lint、Type Check 通过 |
| P01 | 逻辑拆分与 CourseRAG Port | 共同基础 | P00 | L | CoursePilot 节点不新增对 Chroma/Parser 的直接导入 |
| P02 | 评测数据骨架与 B0 Runner | 评测基础 | P00 | M | Gold 与系统输出物理分离 |
| P03 | CourseRAG 持久化、版本与构建流水线 | CourseRAG | P01,P02 | XL | 相同输入可复用 Stage |
| P04 | 结构化 PDF/DOCX 解析与 DOCX 分页 | CourseRAG | P03 | XL | 相同 Renderer Profile 页码可重复 |
| P05 | OCR 页面路由与混合页合并 | CourseRAG | P04 | L | OCR Gold 可定位到页和区域 |
| P06 | Stable Evidence 与 Parent-Child Chunk | CourseRAG | P04,P05 | L | Chunker 改变不导致原文 Evidence 丢失 |
| P07 | 课程级知识点资产流水线 | CourseRAG | P06 | XL | KP 与 Evidence/Chunk N:N 显式建模 |
| P08 | Hybrid Retrieval、RRF 与专用 Reranker | CourseRAG | P06,P07 | XL | Hybrid/Rerank 可独立消融 |
| P09 | Query Processing、Context Packing 与基础引用 QA | CourseRAG | P08 | XL | 每项 Query Processing 可消融 |
| P10 | CourseRAG 增量、写回、安全与正式评测 | CourseRAG | P03-P09 | XL | Test 无 Gold 泄漏和静默 Fallback |
| P11 | CoursePilot 核心合同、Artifact、模板与模型网关 | CoursePilot | P01,P10 | XL | 任务可追溯到 Template/Prompt/Model/Artifact Version |
| P12 | PostgreSQL Checkpoint、六个 Interrupt 与审批 | CoursePilot | P11 | XL | 六个 Interrupt 均可暂停编辑恢复 |
| P13 | 分层 ValidationIssue 与 Targeted Repair | CoursePilot | P11,P12 | XL | Issue 可定位到 item/json_path |
| P14 | 教案工作流重构 | CoursePilot | P10-P13 | XL | Session Plan 可人工编辑后恢复 |
| P15 | 试卷 Blueprint、Fan-out/Fan-in 与全局修复 | CoursePilot | P10-P13 | XL | 并行不破坏全局一致性 |
| P16 | PPT Slide Architecture、模板导出与渲染检查 | CoursePilot | P10-P14,P11-P13 | XL | PPTX 可打开、渲染和编辑 |
| P17 | 系统集成、可靠性、安全与写回闭环 | 系统集成 | P10,P14-P16 | XL | 跨课程/未授权/Secret/重复副作用均为 0 |
| P18 | CoursePilot 与系统正式评测 | 评测收口 | P14-P17 | XL | 必须门槛全部达到或明确记录未达项 |
| P19 | 物理拆仓、CI/CD 与作品集收尾 | 收尾 | P10,P18 | L | 干净环境可启动 |

### 2.1 关键依赖链

```text
P00 ─┬─ P01 ─ P03 ─ P04 ─ P05 ─ P06 ─ P07 ─ P08 ─ P09 ─ P10
     └─ P02 ───────────────────────────────────────────────┘

P01 + P10 ─ P11 ─ P12 ─ P13 ─┬─ P14 ─┐
                              ├─ P15 ─┼─ P17 ─ P18 ─ P19
                              └─ P16 ─┘
```

P02 可以与 P01 并行启动，但 P03 之后的实现必须使用 P02 冻结的 Schema/Manifest。P11 不应在 CourseRAG Port 和核心合同冻结前开始大规模业务迁移。

## 3. 全局 Definition of Ready

一个阶段开始前必须满足：

- 上游阶段 Gate 已通过；
- 当前分支工作区干净，或已有明确的未提交文件清单；
- 输入文档版本和 Git Commit 已记录；
- 阶段 Prompt 中的范围、禁止项和验收命令已确认；
- 外部 Provider、字体、Renderer、数据库等依赖具备 Fake/Mock 或可跳过策略；
- 当前阶段所需 Pilot Fixture 已存在。

## 4. 全局 Definition of Done

一个阶段只有同时满足以下条件才算完成：

- 代码、迁移、配置和文档全部落库；
- 新增行为有 Unit/Contract/Integration Test；
- 旧行为若改变，兼容策略和迁移说明明确；
- `uv run pytest -q`、Ruff、Mypy 通过，或阶段报告准确列出既有非本阶段问题；
- 阶段专项评测/Smoke Test 通过；
- 无 Secret、临时调试代码、未说明的静默 Fallback；
- 更新 Execution Status、Decision Log、Risk Register 和 Phase Report；
- Codex 给出变更文件清单、测试结果、遗留项和下一阶段前置条件。

---

## P00：冻结基线与执行脚手架

**轨道：** 共同基础  
**依赖：** 无  
**相对复杂度：** M  
**主要依据文档：** 01, 03, 06

### 目标

建立不可丢失的 B0、文档执行秩序和阶段状态文件；此阶段不改变产品行为。

### 本阶段禁止

- 不得重构 RAG 或 Agent 业务逻辑。
- 不得删除旧评测、旧 Chroma Collection 或旧数据表。
- 不得修改公开 API 行为。

### 主要代码区域

- `README.md`
- `README.zh-CN.md`
- `CoursePilot_markdown_docs/`
- `tests/coursepilot/`
- `src/coursepilot/evals/`
- `compose.eval.yaml`
- `pyproject.toml`

### 任务清单

- [ ] P00-T01 记录当前 `main` Commit、Python/依赖锁文件、数据库迁移头、环境变量清单和启动命令。
- [ ] P00-T02 在仓库建立 `docs/refactor/frozen_v1.0/`，复制 00—08 冻结文档；原讨论稿保留但不再作为执行依据。
- [ ] P00-T03 建立 `docs/refactor/EXECUTION_STATUS.md`、`DECISION_LOG.md`、`RISK_REGISTER.md` 和 `phase_reports/PHASE_REPORT_TEMPLATE.md`。
- [ ] P00-T04 为当前 PDF/DOCX 构建、Dense Search、教案、试卷、PPT、导出、审核写回建立 B0 Smoke Test。
- [ ] P00-T05 运行并保存当前真实模型评测或至少保存可复现的 B0 Runner/Manifest；Gold 不得由 Top-K 结果反推。
- [ ] P00-T06 记录当前 API、ORM 表、Pydantic Schema、Graph 节点、Prompt Hash 和导出文件样例。
- [ ] P00-T07 确认 MIT License 与上游归属保留；记录后续更新包作者元数据的任务，不在本阶段删除归属信息。

### 必须测试

- [ ] `uv run pytest -q`
- [ ] `uv run ruff format --check`
- [ ] `uv run ruff check`
- [ ] `uv run mypy src/`
- [ ] 现有 deterministic eval 可运行并保存报告

### 阶段交付物

- [ ] B0 Baseline Manifest
- [ ] 执行状态与决策日志模板
- [ ] 当前 API/DB/Graph 快照
- [ ] B0 评测报告或可重复 Runner

### Exit Gate

- [ ] 主测试、Lint、Type Check 通过
- [ ] 现有端到端 Demo 未退化
- [ ] B0 结果和输入 Hash 可追溯

### 阶段报告至少包含

- 实际变更与原计划差异；
- 关键设计选择及替代方案；
- 数据库/API/Schema 兼容影响；
- 运行过的命令和完整结果摘要；
- 专项指标或 Pilot 结果；
- 已知风险、未完成项和下一阶段前置条件。

---

## P01：逻辑拆分与 CourseRAG Port

**轨道：** 共同基础  
**依赖：** P00  
**相对复杂度：** L  
**主要依据文档：** 01, 04, 05

### 目标

建立 CoursePilot—CourseRAG 稳定边界，同时保持现有业务接口和行为兼容。

### 本阶段禁止

- 不得开始新 Parser/OCR/Hybrid Retrieval。
- 不得让 CoursePilot 直接依赖新 CourseRAG 内部模块。
- 不得物理拆仓。

### 主要代码区域

- `src/courserag/`
- `src/coursepilot/ports/`
- `src/coursepilot/adapters/`
- `src/coursepilot/clients/`
- `src/coursepilot/services/kb_service.py`
- `tests/contracts/`

### 任务清单

- [ ] P01-T01 新建 `src/courserag/` 包骨架及 domain/application/api/infrastructure 分层。
- [ ] P01-T02 实现冻结文档定义的 KnowledgeBase、Retrieval、Evidence、VerifiedContent、QA、ServiceInfo Port/DTO。
- [ ] P01-T03 DTO 中分离 RequestContext/ResponseMeta 与领域 Payload，统一错误码、UTC 时间、Request/Trace ID。
- [ ] P01-T04 实现 `LocalCourseRAGAdapter`，内部委托旧 KnowledgeBaseService/Chroma，暂不改变检索算法。
- [ ] P01-T05 实现 `MockCourseRAGService`，支持 Lesson/Exam/PPT 单元测试。
- [ ] P01-T06 建立 `RemoteCourseRAGClient` 接口和 HTTP Schema，但可先用 Stub/Contract Fake。
- [ ] P01-T07 将 CoursePilot 业务服务中的直接 RAG 调用逐步替换为 Port；保留旧 `/api/coursepilot/*` Endpoint。
- [ ] P01-T08 建立 Local、Remote、Mock 共用 Contract Test；验证序列化、错误和幂等合同。

### 必须测试

- [ ] 旧 API 回归测试
- [ ] Local/Remote/Mock Contract Test
- [ ] CoursePilot 三条旧 Graph Smoke Test

### 阶段交付物

- [ ] `src/courserag` 骨架
- [ ] Port/DTO/Adapter/Client
- [ ] 兼容层
- [ ] 合同测试报告

### Exit Gate

- [ ] CoursePilot 节点不新增对 Chroma/Parser 的直接导入
- [ ] 旧 API 响应兼容
- [ ] 三种实现通过同一合同测试

### 阶段报告至少包含

- 实际变更与原计划差异；
- 关键设计选择及替代方案；
- 数据库/API/Schema 兼容影响；
- 运行过的命令和完整结果摘要；
- 专项指标或 Pilot 结果；
- 已知风险、未完成项和下一阶段前置条件。

---

## P02：评测数据骨架与 B0 Runner

**轨道：** 评测基础  
**依赖：** P00  
**相对复杂度：** M  
**主要依据文档：** 03, 03A, 06

### 目标

在大规模重构前固定 Gold Schema、数据目录、Run Manifest 和旧系统适配器。

### 本阶段禁止

- 不要求一次完成人工正式 Gold。
- 不得把当前 Chunk ID 当作 Gold 主标识。
- 不得使用 LLM-as-a-Judge。

### 主要代码区域

- `datasets/`
- `src/courserag/evals/`
- `src/coursepilot/evals/`
- `tests/evals/`

### 任务清单

- [ ] P02-T01 建立 CourseRAG DS0—DS8 和 CoursePilot CP-DS0—CP-DS8、SYS-DS1 目录及 JSON Schema/Pydantic Model。
- [ ] P02-T02 建立 Pilot/Dev/Test Split 文件、人工审核状态、候选与 Approved Gold 分离机制。
- [ ] P02-T03 实现 Run Manifest、Hash 校验、Checkpoint/Resume、原子报告写入和配置差异拒绝。
- [ ] P02-T04 实现 B0 Evaluation Adapter：通过文本/span overlap 将旧 Chunk 结果映射到 Gold Evidence，而不是修改 B0 Runtime。
- [ ] P02-T05 建立指标函数单元测试，尤其是 Evidence Group、Claim、ValidationIssue、Repair Patch 和 Recovery 指标。
- [ ] P02-T06 建立人工评分表/JSONL Schema，但本阶段只完成少量 Pilot 样例。
- [ ] P02-T07 建立测试集锁定标志，Runner 禁止在 Test 上自动调参。

### 必须测试

- [ ] Metrics Unit Test
- [ ] Manifest Hash/Resume Test
- [ ] Gold Leakage Guard Test
- [ ] B0 Adapter Test

### 阶段交付物

- [ ] 数据集目录骨架
- [ ] Schema 与指标库
- [ ] B0 Runner
- [ ] Pilot 示例与标注模板

### Exit Gate

- [ ] Gold 与系统输出物理分离
- [ ] Runner 可中断恢复
- [ ] 所有非通用指标有代码和测试

### 阶段报告至少包含

- 实际变更与原计划差异；
- 关键设计选择及替代方案；
- 数据库/API/Schema 兼容影响；
- 运行过的命令和完整结果摘要；
- 专项指标或 Pilot 结果；
- 已知风险、未完成项和下一阶段前置条件。

---

## P03：CourseRAG 持久化、版本与构建流水线

**轨道：** CourseRAG  
**依赖：** P01,P02  
**相对复杂度：** XL  
**主要依据文档：** 02, 04

### 目标

建立 PostgreSQL 事实源、文档版本、构建 Stage、Artifact Cache 和 Index Version 原子发布能力。

### 本阶段禁止

- 不实现最终 Parser/OCR 算法。
- 不迁移旧 Chunk 为 Evidence。
- 不替换 Chroma。

### 主要代码区域

- `src/courserag/persistence/`
- `src/courserag/jobs/`
- `alembic/`
- `src/courserag/indexing/version_manager.py`

### 任务清单

- [ ] P03-T01 实现 KnowledgeBase、SourceDocument、DocumentVersion、ParsedDocument、BuildJob、BuildStageRun、IndexVersion 等 ORM。
- [ ] P03-T02 实现 Section/Block/Evidence/Chunk/KP/Writeback/Run 所需表的第一版迁移和索引。
- [ ] P03-T03 建立 Repository 层，不允许 Application Service 散落 SQLAlchemy 查询。
- [ ] P03-T04 实现 BuildStage 接口、Fingerprint、Artifact URI/Hash、Cache Hit、Retry 和 Stage 状态。
- [ ] P03-T05 复用当前数据库 Worker/Lease/Idempotency，支持 Stage 级恢复和手动重跑。
- [ ] P03-T06 实现 Staging Dense/Sparse Manifest、校验和 Active Pointer 事务切换；失败不影响旧 Active Index。
- [ ] P03-T07 实现 Artifact/孤儿 Staging 清理策略和审计日志。
- [ ] P03-T08 为旧 `Document`/Task 建立兼容映射，但新事实表使用 `courserag_*` 命名。

### 必须测试

- [ ] Alembic upgrade/downgrade Test
- [ ] Stage Fingerprint/Cache Test
- [ ] Worker Lease Recovery Test
- [ ] Index Active Pointer Atomicity Test

### 阶段交付物

- [ ] 数据库迁移
- [ ] Repository/Job 框架
- [ ] Stage Runner
- [ ] Index Version Publisher

### Exit Gate

- [ ] 相同输入可复用 Stage
- [ ] 构建失败不破坏 Active Index
- [ ] Worker 崩溃可接管且不重复副作用

### 阶段报告至少包含

- 实际变更与原计划差异；
- 关键设计选择及替代方案；
- 数据库/API/Schema 兼容影响；
- 运行过的命令和完整结果摘要；
- 专项指标或 Pilot 结果；
- 已知风险、未完成项和下一阶段前置条件。

---

## P04：结构化 PDF/DOCX 解析与 DOCX 分页

**轨道：** CourseRAG  
**依赖：** P03  
**相对复杂度：** XL  
**主要依据文档：** 02, 03, 04

### 目标

实现 Canonical Document IR、Section Tree、结构化 PDF/DOCX 和可复现 DOCX 原始页码快照。

### 本阶段禁止

- 不接 OCR 识别正文，OCR 页面仅输出待处理决策。
- 不做最终 Chunk/KP。
- 不伪造 DOCX 页码。

### 主要代码区域

- `src/courserag/parsers/`
- `src/courserag/domain/document.py`
- `resources/renderers/`
- `tests/courserag/parsers/`

### 任务清单

- [ ] P04-T01 实现 ParsedDocumentIR、PageIR、BlockIR、SectionIR、TableRecord、SourceSpan 和 ParseWarning。
- [ ] P04-T02 PDF 使用 PyMuPDF dict/rawdict 保留 Block/Line/Span、字体、BBox、图片和阅读顺序。
- [ ] P04-T03 DOCX 使用 python-docx 解析 Paragraph、Run、Heading、Numbering、Table、Break 和 Inline Shape。
- [ ] P04-T04 实现固定 LibreOffice Headless Renderer Profile、字体包清单、PDF Snapshot Hash 和版本记录。
- [ ] P04-T05 将 DOCX Block 对齐到渲染 PDF，保存 physical_page_index、display_page_label、section_page_index 和 alignment_confidence。
- [ ] P04-T06 实现标题层级、目录辅助、页眉页脚/页码噪声标记、跨页段落合并和表格结构。
- [ ] P04-T07 实现 Parse Preview/Quality Report 和低置信度 Warning。
- [ ] P04-T08 使用 DS1 Pilot 的 Native PDF、DOCX 和布局压力页进行评测。

### 必须测试

- [ ] Parser Unit/Golden Fixture
- [ ] DOCX Pagination Reproducibility
- [ ] Section Boundary/Heading Pilot
- [ ] 缺字体和低对齐置信度 Test

### 阶段交付物

- [ ] Canonical IR
- [ ] PDF/DOCX Parser
- [ ] DOCX Renderer/Anchor
- [ ] DS1 Pilot 报告

### Exit Gate

- [ ] 相同 Renderer Profile 页码可重复
- [ ] DOCX 引用同时保留分页和结构 Anchor
- [ ] 结构化解析优于 B0 且无严重回归

### 阶段报告至少包含

- 实际变更与原计划差异；
- 关键设计选择及替代方案；
- 数据库/API/Schema 兼容影响；
- 运行过的命令和完整结果摘要；
- 专项指标或 Pilot 结果；
- 已知风险、未完成项和下一阶段前置条件。

---

## P05：OCR 页面路由与混合页合并

**轨道：** CourseRAG  
**依赖：** P04  
**相对复杂度：** L  
**主要依据文档：** 02, 03, 04

### 目标

实现按页 OCR 决策、Provider 抽象、坐标和置信度保留，以及混合页面去重合并。

### 本阶段禁止

- 不在无 Gold 情况下永久锁定 OCR 引擎。
- 不承诺公式、手写和极复杂版式完全正确。

### 主要代码区域

- `src/courserag/parsers/page_classifier.py`
- `src/courserag/parsers/ocr/`
- `src/courserag/parsers/normalizer.py`

### 任务清单

- [ ] P05-T01 实现 native/ocr/hybrid PageParseDecision 与可配置阈值。
- [ ] P05-T02 实现 OCRProvider、至少一个轻量 Adapter，并为其他候选提供可插拔接口。
- [ ] P05-T03 保存 Engine/Model/DPI/Image Hash、文本、BBox、Confidence 和 Warning。
- [ ] P05-T04 实现原生 Block 与 OCR Block 坐标合并、重复文本去除和来源标记。
- [ ] P05-T05 实现 OCR 失败、低置信度和资源上限的 `ready_with_warnings` 处理。
- [ ] P05-T06 在 15 页 OCR Pilot 上比较候选引擎的 CER、路由、延迟、内存和部署复杂度。
- [ ] P05-T07 冻结默认 OCR Profile，并在 Manifest 记录。

### 必须测试

- [ ] OCR Routing Precision/Recall
- [ ] CER Calculator
- [ ] Mixed Page Merge Test
- [ ] Resource Limit/Timeout Test

### 阶段交付物

- [ ] OCR Port/Adapter
- [ ] Page Classifier
- [ ] Hybrid Merger
- [ ] OCR 选型报告

### Exit Gate

- [ ] OCR Gold 可定位到页和区域
- [ ] 低置信度不静默通过
- [ ] 默认引擎选择有 Pilot 证据

### 阶段报告至少包含

- 实际变更与原计划差异；
- 关键设计选择及替代方案；
- 数据库/API/Schema 兼容影响；
- 运行过的命令和完整结果摘要；
- 专项指标或 Pilot 结果；
- 已知风险、未完成项和下一阶段前置条件。

---

## P06：Stable Evidence 与 Parent-Child Chunk

**轨道：** CourseRAG  
**依赖：** P04,P05  
**相对复杂度：** L  
**主要依据文档：** 02, 03, 04

### 目标

建立稳定原文证据、Evidence Resolver 和基于语义边界的层级 Chunk。

### 本阶段禁止

- 不得将 Chunk ID 作为永久引用。
- 不得在固定字符位置直接截断所有语义单元。

### 主要代码区域

- `src/courserag/evidence/`
- `src/courserag/chunking/`
- `src/courserag/domain/evidence.py`

### 任务清单

- [ ] P06-T01 实现 EvidenceRecord、PageBBox、内容 Hash 和稳定 Evidence ID。
- [ ] P06-T02 按定义、段落、列表、步骤、表格和示例等语义单元构建 Evidence。
- [ ] P06-T03 实现 Evidence Resolver、Batch Resolver 和 Source Preview。
- [ ] P06-T04 实现 Parent Chunk/Child Chunk、ChunkEvidenceLink、Parent Relationship 和版本化 Chunk Profile。
- [ ] P06-T05 切分按 Section→Block→Paragraph/List/Table→Sentence→Token Limit 执行。
- [ ] P06-T06 实现去重、邻接、超长 Block 和 OCR Evidence 处理。
- [ ] P06-T07 建立引用迁移接口骨架，详细迁移在 P10 完成。
- [ ] P06-T08 运行 DS2 Pilot 和 B1/B2 对比。

### 必须测试

- [ ] Stable Evidence ID Test
- [ ] Chunk Boundary/Overlap Test
- [ ] Evidence Resolver Test
- [ ] Chunk Profile Change Test

### 阶段交付物

- [ ] Evidence Builder/Resolver
- [ ] Hierarchical Chunker
- [ ] Link Tables
- [ ] DS2 Pilot 报告

### Exit Gate

- [ ] Chunker 改变不导致原文 Evidence 丢失
- [ ] 所有 Context 项可解析回原文
- [ ] 语义完整率和冗余率可计算

### 阶段报告至少包含

- 实际变更与原计划差异；
- 关键设计选择及替代方案；
- 数据库/API/Schema 兼容影响；
- 运行过的命令和完整结果摘要；
- 专项指标或 Pilot 结果；
- 已知风险、未完成项和下一阶段前置条件。

---

## P07：课程级知识点资产流水线

**轨道：** CourseRAG  
**依赖：** P06  
**相对复杂度：** XL  
**主要依据文档：** 02, 03, 03A, 04

### 目标

将每 Chunk 临时关键词改造成 Section Window 级、持久化、可审核、可复用的知识点资产。

### 本阶段禁止

- 不构建完整知识图谱。
- 不把模型自报 confidence 直接当发布概率。
- 普通在线检索不得触发 KP 抽取。

### 主要代码区域

- `src/courserag/knowledge_points/`
- `src/courserag/application/knowledge_point_service.py`
- `src/courserag/api/knowledge_points.py`

### 任务清单

- [ ] P07-T01 实现 Section/Parent Window Builder 和批量结构化抽取 Schema。
- [ ] P07-T02 实现 Provider 并发、重试、Prompt/Model/Window Hash 缓存和失败窗口重跑。
- [ ] P07-T03 实现名称规范化、Alias、无效候选过滤、Section 内去重和课程级归并候选。
- [ ] P07-T04 实现 KnowledgePoint、EvidenceLink、ChunkLink、ReviewAction 和可选 Parent。
- [ ] P07-T05 实现由 evidence/naming/cross-window/ambiguity/duplicate 组成的 publish_score。
- [ ] P07-T06 在 Dev Gold 校准默认 0.75 阈值，保留 unreviewed/needs_review/approved/rejected/deprecated。
- [ ] P07-T07 实现列表、详情、批准、拒绝、合并、拆分和修改 API。
- [ ] P07-T08 完成 DS3 Pilot、调用次数/成本对比，验证不再按 Child Chunk 单独调用。

### 必须测试

- [ ] KP Cache/Idempotency
- [ ] Normalize/Deduplicate
- [ ] Evidence Link Integrity
- [ ] Threshold Report

### 阶段交付物

- [ ] KP Pipeline
- [ ] KP API/Review
- [ ] 缓存和分数
- [ ] DS3 Pilot 报告

### Exit Gate

- [ ] KP 与 Evidence/Chunk N:N 显式建模
- [ ] 抽取调用数相对 B0 明显下降
- [ ] 正式 Gold 由人工批准

### 阶段报告至少包含

- 实际变更与原计划差异；
- 关键设计选择及替代方案；
- 数据库/API/Schema 兼容影响；
- 运行过的命令和完整结果摘要；
- 专项指标或 Pilot 结果；
- 已知风险、未完成项和下一阶段前置条件。

---

## P08：Hybrid Retrieval、RRF 与专用 Reranker

**轨道：** CourseRAG  
**依赖：** P06,P07  
**相对复杂度：** XL  
**主要依据文档：** 02, 03, 04

### 目标

实现版本化 Dense + BM25 + Fusion + 专用 Reranker，并完整记录各阶段分数。

### 本阶段禁止

- 不使用聊天 LLM 作为默认 Reranker。
- 不在代码硬编码 Provider/Model。
- 不直接比较不同 Provider 的绝对阈值。

### 主要代码区域

- `src/courserag/retrieval/`
- `src/courserag/indexing/`
- `src/courserag/providers/reranker.py`

### 任务清单

- [ ] P08-T01 实现 DenseRetrieverPort 和版本化 Chroma Adapter，批量 Embedding，完整正文回源 PostgreSQL/Artifact。
- [ ] P08-T02 实现 BM25S 索引、中文搜索分词、英文/数字/特殊术语保留与字符二元组兜底。
- [ ] P08-T03 实现 RRF 和可选加权融合，保留 Dense/Sparse Rank/Score/Fusion Trace。
- [ ] P08-T04 实现 Cohere/Voyage/Jina/Local CrossEncoder 等统一 Reranker Port，默认通过环境 API。
- [ ] P08-T05 实现 Candidate-K、Top-N、Batch、Truncation、Timeout、Retry 和生产/评测不同 Fallback Policy。
- [ ] P08-T06 实现 Course/Document/Section/KP/SourceTier/Version Filter。
- [ ] P08-T07 在 DS5 Dev 比较 B3—B5、Provider、P95 和成本；冻结模型和阈值。
- [ ] P08-T08 完善 SearchResponse、RetrievalRun 和 Debug Trace。

### 必须测试

- [ ] Dense/Sparse Index Contract
- [ ] RRF Unit Test
- [ ] Reranker Adapter Contract
- [ ] Filter Isolation
- [ ] Staging Publish

### 阶段交付物

- [ ] Hybrid Retriever
- [ ] Reranker Providers
- [ ] Score Trace
- [ ] B3—B5 Dev 报告

### Exit Gate

- [ ] Hybrid/Rerank 可独立消融
- [ ] 正式 Eval 失败不静默回退
- [ ] 索引版本与查询结果一致

### 阶段报告至少包含

- 实际变更与原计划差异；
- 关键设计选择及替代方案；
- 数据库/API/Schema 兼容影响；
- 运行过的命令和完整结果摘要；
- 专项指标或 Pilot 结果；
- 已知风险、未完成项和下一阶段前置条件。

---

## P09：Query Processing、Context Packing 与基础引用 QA

**轨道：** CourseRAG  
**依赖：** P08  
**相对复杂度：** XL  
**主要依据文档：** 02, 03, 04

### 目标

完成可配置 Query Pipeline、Evidence-aware Context 和结构化 Claim-Evidence QA。

### 本阶段禁止

- 不做开放网络搜索。
- 不做通用聊天或复杂多轮记忆。
- 不使用 LLM-as-a-Judge。

### 主要代码区域

- `src/courserag/query/`
- `src/courserag/context/`
- `src/courserag/qa/`

### 任务清单

- [ ] P09-T01 实现 Normalize、Filter Parser、KP Link、Alias Expansion、Router、可选 Multi-query、Low-recall Retry。
- [ ] P09-T02 每个 QueryStep 可配置、可关闭、保留 Raw Query、Filter 和 Step Trace。
- [ ] P09-T03 实现 Dense/Sparse Candidate 聚合、Evidence 去重、Parent/Neighbor Expansion 和 Purpose Policy。
- [ ] P09-T04 实现 Token Budget Packing、Citation Map 和 Packing Report。
- [ ] P09-T05 实现 Evidence Sufficiency Gate、QA Structured Output、AnswerClaim 和程序化 Citation Composer。
- [ ] P09-T06 实现拒答、引用 ID 验证、Context 内证据校验和一次定向 Schema Repair。
- [ ] P09-T07 完成 DS4/DS5 Pilot，运行 B6—B8 和 Q0—Q3。
- [ ] P09-T08 输出 Search、Context、QA 三类稳定 API。

### 必须测试

- [ ] Query Step Unit/Toggle Test
- [ ] Filter Preserve/Rewrite Guard
- [ ] Context Token/Dedup Test
- [ ] QA Citation/Abstention Test

### 阶段交付物

- [ ] Query Pipeline
- [ ] Context Service
- [ ] QA Service
- [ ] B6—B8/Q0—Q3 Pilot 报告

### Exit Gate

- [ ] 每项 Query Processing 可消融
- [ ] QA Claim 均绑定有效 Evidence
- [ ] 不可回答样本可正确拒答

### 阶段报告至少包含

- 实际变更与原计划差异；
- 关键设计选择及替代方案；
- 数据库/API/Schema 兼容影响；
- 运行过的命令和完整结果摘要；
- 专项指标或 Pilot 结果；
- 已知风险、未完成项和下一阶段前置条件。

---

## P10：CourseRAG 增量、写回、安全与正式评测

**轨道：** CourseRAG  
**依赖：** P03-P09  
**相对复杂度：** XL  
**主要依据文档：** 02, 03, 03A, 04

### 目标

完成 Section 级增量、Citation Migration、Verified Content、完整安全控制和 CourseRAG 冻结评测。

### 本阶段禁止

- 不得将整份教案/试卷/PPT 任意写回。
- 不得覆盖 Primary Source。
- 不得在看完 Test 后调阈值。

### 主要代码区域

- `src/courserag/jobs/`
- `src/courserag/evidence/migration.py`
- `src/courserag/application/writeback_service.py`
- `src/courserag/security/`
- `datasets/courserag_eval/`

### 任务清单

- [ ] P10-T01 实现 DocumentVersion/Section Diff 和变更影响范围规划。
- [ ] P10-T02 实现 Evidence 精确/结构/相似候选迁移及 valid/migrated/needs_review/invalid。
- [ ] P10-T03 实现白名单 VerifiedContent、独立 SourceTier、即时轻量索引、撤销和幂等。
- [ ] P10-T04 实现 10 条/3000 Tokens/24h/人工触发的 Enrichment Batch 和 KP 归并。
- [ ] P10-T05 实现 MIME、ZIP Bomb、加密 PDF、路径、页数/DPI/Timeout、ACL、跨课程隔离和 Prompt Injection 标记。
- [ ] P10-T06 完成 DS0—DS8 正式数据，Dev 调参后冻结 Test。
- [ ] P10-T07 运行 B0—B8、Q0—Q3、增量、性能、安全和错误分析。
- [ ] P10-T08 更新 CourseRAG README、API、架构图和限制说明。

### 必须测试

- [ ] Citation Migration
- [ ] Incremental Reuse
- [ ] Writeback/Revoke/Batch
- [ ] Security/Fault Injection
- [ ] Locked Test

### 阶段交付物

- [ ] 完整 CourseRAG MVP
- [ ] 正式评测报告
- [ ] 错误案例与指标
- [ ] 冻结 CourseRAG API/Contract

### Exit Gate

- [ ] Test 无 Gold 泄漏和静默 Fallback
- [ ] 安全零容忍指标为 0
- [ ] CourseRAG Port/Contract 冻结供 CoursePilot 使用

### 阶段报告至少包含

- 实际变更与原计划差异；
- 关键设计选择及替代方案；
- 数据库/API/Schema 兼容影响；
- 运行过的命令和完整结果摘要；
- 专项指标或 Pilot 结果；
- 已知风险、未完成项和下一阶段前置条件。

---

## P11：CoursePilot 核心合同、Artifact、模板与模型网关

**轨道：** CoursePilot  
**依赖：** P01,P10  
**相对复杂度：** XL  
**主要依据文档：** 05, 06

### 目标

建立 CoursePilot 新运行时的 Typed State、Artifact Version、Template Registry 和 Main/Light Model Gateway。

### 本阶段禁止

- 不立即重写三条业务 Graph。
- 不再在 CoursePilot 内抽取课程知识点。
- 不硬编码 reasoning/thinking 参数。

### 主要代码区域

- `src/coursepilot/domain/`
- `src/coursepilot/runtime/`
- `src/coursepilot/templates/`
- `src/coursepilot/models_gateway/`
- `resources/templates/`

### 任务清单

- [ ] P11-T01 将 CourseRAG Port 接入 CoursePilot，移除新代码对旧 Rag/Chroma 的直接依赖。
- [ ] P11-T02 实现 BusinessTask、ArtifactRef/Version、NodeResult、CommonGraphState、RunContext。
- [ ] P11-T03 建立 Task/Artifact/NodeRun/Approval/TemplateSnapshot/ModelInvocation ORM 与迁移。
- [ ] P11-T04 实现 TemplateDefinition、Registry、Snapshot、9 个内置逻辑模板及默认 DOCX/PPTX 资源骨架。
- [ ] P11-T05 实现 ModelGateway、Provider Capability、Main/Light Profile、Prompt Hash、Usage/Cost 和显式 Escalation。
- [ ] P11-T06 对不支持 reasoning/thinking 的 Provider 不发送参数；正式 Eval 禁止静默模型切换。
- [ ] P11-T07 实现 ContextPackageRef 和 State Compaction 基础设施。
- [ ] P11-T08 为现有服务提供兼容 Adapter，使旧 API 在迁移期间仍可运行。

### 必须测试

- [ ] Typed State/Artifact Version
- [ ] Template Snapshot Reproducibility
- [ ] Model Capability/Route
- [ ] 旧 Service Compatibility

### 阶段交付物

- [ ] CoursePilot Runtime Foundation
- [ ] Template Registry
- [ ] Model Gateway
- [ ] 数据库迁移

### Exit Gate

- [ ] 任务可追溯到 Template/Prompt/Model/Artifact Version
- [ ] Main/Light 可映射同一或不同模型
- [ ] 现有 API 未中断

### 阶段报告至少包含

- 实际变更与原计划差异；
- 关键设计选择及替代方案；
- 数据库/API/Schema 兼容影响；
- 运行过的命令和完整结果摘要；
- 专项指标或 Pilot 结果；
- 已知风险、未完成项和下一阶段前置条件。

---

## P12：PostgreSQL Checkpoint、六个 Interrupt 与审批

**轨道：** CoursePilot  
**依赖：** P11  
**相对复杂度：** XL  
**主要依据文档：** 05, 06

### 目标

把随机 Thread 和裸 Graph 编译改为可恢复、可编辑、可审计的业务工作流。

### 本阶段禁止

- 不得把导出批准和写回批准合并。
- 不得在 Resume 时直接篡改历史 Checkpoint。
- 不得重复高成本节点和副作用。

### 主要代码区域

- `src/coursepilot/runtime/checkpoint/`
- `src/coursepilot/runtime/interrupts/`
- `src/coursepilot/api/tasks.py`
- `src/coursepilot/api/approvals.py`

### 任务清单

- [ ] P12-T01 使用 PostgreSQL Checkpointer 编译 Graph，Thread ID 稳定关联 Task/Artifact。
- [ ] P12-T02 实现六个 Interrupt Payload：Lesson Plan/Final、Exam Blueprint/Global、PPT Architecture/Final。
- [ ] P12-T03 实现 Approve、Edit+Resume、Replan/Regenerate、Reject/Cancel 和过期处理。
- [ ] P12-T04 人工修改创建新 Artifact Version，再通过 Command resume 恢复。
- [ ] P12-T05 实现导出、写回和白名单内容的独立 Approval Scope。
- [ ] P12-T06 实现 Task/Interrupt/Resume API、状态查询和幂等 Decision。
- [ ] P12-T07 注入 Worker/服务重启、重复 Resume、版本变化和长时间暂停场景。
- [ ] P12-T08 完成 CP-DS6 Pilot。

### 必须测试

- [ ] Checkpoint/Resume
- [ ] Edit Preservation
- [ ] Duplicate Decision/Side Effect
- [ ] Stale Version Detection

### 阶段交付物

- [ ] Checkpoint Runtime
- [ ] Interrupt/Approval API
- [ ] CP-DS6 Pilot 报告

### Exit Gate

- [ ] 六个 Interrupt 均可暂停编辑恢复
- [ ] Completed Node Reuse 可测
- [ ] 重复副作用为 0

### 阶段报告至少包含

- 实际变更与原计划差异；
- 关键设计选择及替代方案；
- 数据库/API/Schema 兼容影响；
- 运行过的命令和完整结果摘要；
- 专项指标或 Pilot 结果；
- 已知风险、未完成项和下一阶段前置条件。

---

## P13：分层 ValidationIssue 与 Targeted Repair

**轨道：** CoursePilot  
**依赖：** P11,P12  
**相对复杂度：** XL  
**主要依据文档：** 05, 06

### 目标

将布尔校验和整件重生成改造成可定位、分级、规划和无回归的局部修复系统。

### 本阶段禁止

- 不得仅返回字符串错误。
- 不得让 LLM 自己决定允许修改范围。
- 不得用修复掩盖 Critical Issue 的人工审核。

### 主要代码区域

- `src/coursepilot/validation/`
- `src/coursepilot/repair/`
- `tests/coursepilot/faults/`
- `datasets/coursepilot_eval/validation/`

### 任务清单

- [ ] P13-T01 实现 ValidationIssue、IssueScope、ValidationReport、Severity、Issue Code Registry。
- [ ] P13-T02 实现 L0 Schema、L1 确定性、L2 跨字段、L3 Grounding、L4 教学/业务校验接口。
- [ ] P13-T03 将 Lesson/Exam/PPT 旧 Validator 分步迁移，先保持原规则再增加精确 Scope。
- [ ] P13-T04 实现 RepairPlanner、RepairPlan、allowed_paths、Patch Contract、Precondition 和 Model Profile Route。
- [ ] P13-T05 L0/L1 规则修复；低风险 L2 用 Light；Grounding/教学问题用 Main。
- [ ] P13-T06 修复后重新校验目标对象和全局约束，计算 Unauthorized Modification 和 Regression。
- [ ] P13-T07 构造 CP-DS4 Pilot（各 10）和 CP-DS5 Pilot（各 5）。
- [ ] P13-T08 输出 Validator/Repair 专项报告。

### 必须测试

- [ ] Issue Match/Scope/Severity
- [ ] Patch Apply/Precondition
- [ ] Preservation/Regression
- [ ] Fault/Repair Pilot

### 阶段交付物

- [ ] Layered Validator
- [ ] Repair Planner/Patch
- [ ] CP-DS4/5 Pilot 报告

### Exit Gate

- [ ] Issue 可定位到 item/json_path
- [ ] 局部修复不整件重写
- [ ] 错误检测和修复指标可计算

### 阶段报告至少包含

- 实际变更与原计划差异；
- 关键设计选择及替代方案；
- 数据库/API/Schema 兼容影响；
- 运行过的命令和完整结果摘要；
- 专项指标或 Pilot 结果；
- 已知风险、未完成项和下一阶段前置条件。

---

## P14：教案工作流重构

**轨道：** CoursePilot  
**依赖：** P10-P13  
**相对复杂度：** XL  
**主要依据文档：** 05, 06

### 目标

实现证据驱动的 Lesson Blueprint、Session 生成、两次人工审核和局部修订。

### 本阶段禁止

- 不得从检索 Context 再调用 Lesson KP Extractor。
- 不得把未审核完整教案写回。
- 不得绕过 Session Plan Interrupt。

### 主要代码区域

- `src/agents/coursepilot/lesson/`
- `src/coursepilot/application/lesson_service.py`
- `resources/templates/lesson/`

### 任务清单

- [ ] P14-T01 从 CourseRAG 获取 KP Snapshot 和 purpose=`lesson_generation` ContextPackage。
- [ ] P14-T02 实现 Lesson Blueprint/SessionPlan，知识点、Evidence、目标、时间和活动显式绑定。
- [ ] P14-T03 接入 Session Plan Review，支持字段级修改和重新规划。
- [ ] P14-T04 实现按 Session 受控生成；可试验并行，但先确保跨课时顺序和共享约束。
- [ ] P14-T05 实现全局知识覆盖、时间、重复、Evidence 和教学逻辑校验。
- [ ] P14-T06 按 ValidationIssue 对单 Session/字段定向 Repair。
- [ ] P14-T07 接入 Final Review，分别批准导出和 verified_lesson_fragment 写回。
- [ ] P14-T08 实现版本化 Lesson DOCX Export 和 Revision Diff。
- [ ] P14-T09 完成 CP-DS1 Pilot 和 CP-B0 对比。

### 必须测试

- [ ] Lesson Graph/Interrupt
- [ ] Coverage/Time/Grounding
- [ ] Targeted Revision
- [ ] DOCX Export

### 阶段交付物

- [ ] 新 Lesson Graph/Service
- [ ] Lesson Templates/Exporter
- [ ] CP-DS1 Pilot 报告

### Exit Gate

- [ ] Session Plan 可人工编辑后恢复
- [ ] 所有事实引用 Evidence
- [ ] 完整教案不会整件写回

### 阶段报告至少包含

- 实际变更与原计划差异；
- 关键设计选择及替代方案；
- 数据库/API/Schema 兼容影响；
- 运行过的命令和完整结果摘要；
- 专项指标或 Pilot 结果；
- 已知风险、未完成项和下一阶段前置条件。

---

## P15：试卷 Blueprint、Fan-out/Fan-in 与全局修复

**轨道：** CoursePilot  
**依赖：** P10-P13  
**相对复杂度：** XL  
**主要依据文档：** 05, 06

### 目标

实现 Blueprint 审核、Question Batch 并行、全局校验、局部重生成和题目级写回。

### 本阶段禁止

- 不得按所有题目无限并发。
- 不得在 Blueprint 未确认时生成题目。
- 不得用局部 Batch 校验替代全局校验。

### 主要代码区域

- `src/agents/coursepilot/exam/`
- `src/coursepilot/application/exam_service.py`
- `resources/templates/exam/`

### 任务清单

- [ ] P15-T01 实现 Evidence/KP 驱动 Exam Blueprint、题型/分值/难度/内容角色/Batch Plan。
- [ ] P15-T02 接入 Blueprint Review 和人工修改。
- [ ] P15-T03 使用 LangGraph Send 或等价机制按 Question Batch Fan-out，设置并发和 Provider 限流。
- [ ] P15-T04 Fan-in 后重新编号并执行总分、题量、覆盖、重复、答案泄漏和引用全局校验。
- [ ] P15-T05 实现题目、答案、解析和 Batch 级定向 Repair/Regenerate。
- [ ] P15-T06 接入 Global Review，导出和题目/解析写回分别授权。
- [ ] P15-T07 实现 Student Exam、Answer Key、Detailed Explanation、Answer Sheet 四类 DOCX 模板。
- [ ] P15-T08 运行 EX-P0—P3 并行实验和 CP-DS2 Pilot。

### 必须测试

- [ ] Blueprint Gate
- [ ] Fan-out/Fan-in/Concurrency
- [ ] Global Validation/Duplicate
- [ ] Four-file Export/Writeback

### 阶段交付物

- [ ] 新 Exam Graph/Service
- [ ] Batch Parallelism
- [ ] Exam Templates
- [ ] 并行与 CP-DS2 Pilot 报告

### Exit Gate

- [ ] 并行不破坏全局一致性
- [ ] Global Review 前无正式导出
- [ ] 仅批准题目/解析可写回

### 阶段报告至少包含

- 实际变更与原计划差异；
- 关键设计选择及替代方案；
- 数据库/API/Schema 兼容影响；
- 运行过的命令和完整结果摘要；
- 专项指标或 Pilot 结果；
- 已知风险、未完成项和下一阶段前置条件。

---

## P16：PPT Slide Architecture、模板导出与渲染检查

**轨道：** CoursePilot  
**依赖：** P10-P14,P11-P13  
**相对复杂度：** XL  
**主要依据文档：** 05, 06

### 目标

生成可编辑教学 PPT 初稿，支持 Slide Architecture、Master/Layout、Notes、引用和渲染后校验。

### 本阶段禁止

- 不以商业级视觉设计为验收目标。
- 不得继续只用默认 Title/Content Layout。
- 不得把整份 PPT 大纲写回。

### 主要代码区域

- `src/agents/coursepilot/ppt/`
- `src/coursepilot/exporters/pptx/`
- `resources/templates/ppt/`
- `src/coursepilot/rendering/`

### 任务清单

- [ ] P16-T01 实现 Slide Architecture：页型、课时来源、KP/Evidence、Layout、素材占位和页数预算。
- [ ] P16-T02 接入 Architecture Review，支持增删、调整页序、页型和 Layout。
- [ ] P16-T03 实现逐页内容、Speaker Notes、引用和素材 Placeholder 生成。
- [ ] P16-T04 实现至少三套 PPTX Master/Layout 资源及 SlideType→Layout 映射。
- [ ] P16-T05 实现表格、图形/图片占位、引用 Notes 和 Reference Slide。
- [ ] P16-T06 实现 Overflow、Shape Boundary、Empty Placeholder、Font、可编辑对象和 Render Snapshot 检查。
- [ ] P16-T07 按页面/字段定向 Repair，接入 Final PPT Review。
- [ ] P16-T08 仅允许 verified_lesson_fragment 等白名单片段写回。
- [ ] P16-T09 完成 CP-DS3、CP-DS7 Pilot 和一个用户模板导入验证。

### 必须测试

- [ ] Slide Architecture/Interrupt
- [ ] Layout/Placeholder Mapping
- [ ] PPTX Open/Render/Overflow
- [ ] Editable Object/Reference

### 阶段交付物

- [ ] 新 PPT Graph/Exporter
- [ ] 内置 PPT 模板
- [ ] Renderer/Validator
- [ ] CP-DS3/7 Pilot 报告

### Exit Gate

- [ ] PPTX 可打开、渲染和编辑
- [ ] 严重溢出为 0
- [ ] 页面引用可解析

### 阶段报告至少包含

- 实际变更与原计划差异；
- 关键设计选择及替代方案；
- 数据库/API/Schema 兼容影响；
- 运行过的命令和完整结果摘要；
- 专项指标或 Pilot 结果；
- 已知风险、未完成项和下一阶段前置条件。

---

## P17：系统集成、可靠性、安全与写回闭环

**轨道：** 系统集成  
**依赖：** P10,P14-P16  
**相对复杂度：** XL  
**主要依据文档：** 01, 04, 05, 06

### 目标

连接真实 CourseRAG，验证端到端 Version/Trace、错误隔离、写回闭环和安全零容忍指标。

### 本阶段禁止

- 不把 Track B 问题混作 Agent 单独质量。
- 不得共享数据库绕过 API/Port。
- 不得允许跨课程 Evidence。

### 主要代码区域

- `compose.yaml`
- `src/coursepilot/integration/`
- `src/courserag/api/`
- `tests/system/`
- `observability/`

### 任务清单

- [ ] P17-T01 实现 RemoteCourseRAGClient 完整 HTTP 调用、Timeout/Retry/Request ID 和错误映射。
- [ ] P17-T02 CoursePilot Task 保存 CourseRAG Retrieval/Context Trace、Index Version、Evidence Version。
- [ ] P17-T03 实现 Stale Evidence/Index 检测，导出或写回前不兼容则要求重审。
- [ ] P17-T04 打通 Approval→VerifiedContent→Enrichment Batch→新 Index→后续任务检索闭环。
- [ ] P17-T05 实现 CourseRAG/Model/Graph/Validator/Exporter/Writeback 错误隔离和用户错误码。
- [ ] P17-T06 实现 Prompt Injection、跨课程、未授权写回、Secret Trace、路径穿越和超长反馈测试。
- [ ] P17-T07 实现 Worker/Checkpoint/Export/Writeback 故障注入和幂等恢复。
- [ ] P17-T08 运行 SYS-DS1 Pilot Journey。

### 必须测试

- [ ] Remote Contract
- [ ] Trace/Version Continuity
- [ ] Writeback Loop
- [ ] Fault/Security/Idempotency

### 阶段交付物

- [ ] 完整集成系统
- [ ] SYS-DS1 Pilot 报告
- [ ] 安全/恢复报告

### Exit Gate

- [ ] 跨课程/未授权/Secret/重复副作用均为 0
- [ ] Trace 可跨服务追踪
- [ ] 写回来源完整

### 阶段报告至少包含

- 实际变更与原计划差异；
- 关键设计选择及替代方案；
- 数据库/API/Schema 兼容影响；
- 运行过的命令和完整结果摘要；
- 专项指标或 Pilot 结果；
- 已知风险、未完成项和下一阶段前置条件。

---

## P18：CoursePilot 与系统正式评测

**轨道：** 评测收口  
**依赖：** P14-P17  
**相对复杂度：** XL  
**主要依据文档：** 03, 03A, 06

### 目标

完成 Agent-Isolated 和 Integrated System 冻结评测，形成可用于 README/简历的可信结果。

### 本阶段禁止

- 不得使用 Test 调参。
- 不得填造 X/Y 指标。
- 不得使用 LLM-as-a-Judge。
- 不得将 Fallback 样本计入真实质量。

### 主要代码区域

- `datasets/coursepilot_eval/`
- `src/coursepilot/evals/`
- `reports/`
- `human_review/`

### 任务清单

- [ ] P18-T01 完成 CP-DS0—CP-DS8、SYS-DS1 正式数据；Lesson/Exam/PPT 各 10，Dev 18/Test 12。
- [ ] P18-T02 冻结 CourseRAG ContextPackage/KP/Evidence Fixtures，运行 Track A。
- [ ] P18-T03 运行 CP-B0 与 CP-B10、Validation/Repair、Interrupt、Export、Model Routing 和 Exam Parallel。
- [ ] P18-T04 执行盲化人工评分、Edit Burden、题目状态和 PPT 页面检查；记录评审一致性。
- [ ] P18-T05 连接正式 CourseRAG Test Index，运行 Track B Journey、故障和安全场景。
- [ ] P18-T06 汇总 P50/P95、Token、成本、人工分钟、Recovery、Trace 和错误分类。
- [ ] P18-T07 生成完整报告、错误案例、限制和可追溯 Manifest。
- [ ] P18-T08 从锁定结果提取 README/简历可用指标，不夸大。

### 必须测试

- [ ] Locked Test Guard
- [ ] Report Reproducibility
- [ ] Human Review Completeness
- [ ] Metric Cross-check

### 阶段交付物

- [ ] CoursePilot/System 正式评测报告
- [ ] 锁定输出与人工评分
- [ ] README/简历指标候选

### Exit Gate

- [ ] 必须门槛全部达到或明确记录未达项
- [ ] Test 配置冻结
- [ ] 所有公开指标可追溯

### 阶段报告至少包含

- 实际变更与原计划差异；
- 关键设计选择及替代方案；
- 数据库/API/Schema 兼容影响；
- 运行过的命令和完整结果摘要；
- 专项指标或 Pilot 结果；
- 已知风险、未完成项和下一阶段前置条件。

---

## P19：物理拆仓、CI/CD 与作品集收尾

**轨道：** 收尾  
**依赖：** P10,P18  
**相对复杂度：** L  
**主要依据文档：** 01, 04, 05

### 目标

在逻辑边界和接口稳定后形成独立 CourseRAG/CoursePilot 仓库和可演示部署。

### 本阶段禁止

- 不得在合同未冻结前拆仓。
- 不得破坏 MIT License/上游归属。
- 不得删除迁移说明和旧版本兼容记录。

### 主要代码区域

- `course-rag repo`
- `course-pilot repo`
- `compose.yaml`
- `.github/workflows/`
- `README`
- `LICENSE`
- `pyproject.toml`

### 任务清单

- [ ] P19-T01 提取 CourseRAG 独立仓库、迁移历史或保留清晰来源记录。
- [ ] P19-T02 CoursePilot 生产 Profile 使用 Remote Client，Demo/Test 可使用 Local/Mock。
- [ ] P19-T03 建立独立 PostgreSQL Schema/Database、Worker、Storage、Chroma/BM25 和 Docker Compose。
- [ ] P19-T04 建立两仓 Contract Test、API Schema 兼容检查和端到端 CI。
- [ ] P19-T05 更新 Package Name/Author 为当前项目作者，同时保留 MIT License 和上游 Attribution。
- [ ] P19-T06 完善 README：架构、Quickstart、Demo、评测、限制、安全、截图和数据构造说明。
- [ ] P19-T07 标记旧内部 RAG 代码 Deprecated，给出删除条件，不在无迁移路径时立即删除。
- [ ] P19-T08 输出面试讲解材料、架构图和最终 Release Tag。

### 必须测试

- [ ] 两仓 Unit/Contract/Integration
- [ ] Docker Cold Start
- [ ] CI Clean Checkout
- [ ] Release Smoke Test

### 阶段交付物

- [ ] 独立 CourseRAG/CoursePilot 仓库
- [ ] Docker/CI
- [ ] Release 文档
- [ ] 作品集材料

### Exit Gate

- [ ] 干净环境可启动
- [ ] 合同测试跨仓通过
- [ ] 最终指标和限制公开可信

### 阶段报告至少包含

- 实际变更与原计划差异；
- 关键设计选择及替代方案；
- 数据库/API/Schema 兼容影响；
- 运行过的命令和完整结果摘要；
- 专项指标或 Pilot 结果；
- 已知风险、未完成项和下一阶段前置条件。

---

## 5. 建议的分支与阶段报告命名

```text
branch: refactor/p00-baseline
branch: refactor/p01-courserag-port
...
branch: refactor/p19-repo-extraction

docs/refactor/phase_reports/P00_Baseline_Report.md
docs/refactor/phase_reports/P01_CourseRAG_Port_Report.md
...
```

## 6. 阶段完成状态模板

```markdown
## Pxx — 阶段名称

- 状态：not_started / in_progress / blocked / completed
- 分支：
- 起始 Commit：
- 完成 Commit：
- 输入文档：
- 关键决策：
- 测试：
- 专项评测：
- 遗留项：
- 下一阶段可开始：yes/no
```

## 7. 执行优先级结论

1. P00—P02 是后续可信改造的前提，不应跳过。
2. P03—P10 完成 CourseRAG MVP 和冻结接口。
3. P11—P16 完成 CoursePilot Agent 工程化。
4. P17—P18 完成系统闭环和正式评测。
5. P19 只在逻辑边界、合同和评测结果稳定后执行。
