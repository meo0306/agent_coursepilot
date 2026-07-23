# CourseRAG 技术改造方案

**文档版本：** v1.0  
**文档状态：** 冻结执行版
**冻结日期：** 2026-07-22
**上位文档：**
- `01_CoursePilot_CourseRAG_Split_and_Refactor_Plan_v1.0.md`
- `02_CourseRAG_PRD_v1.0.md`
- `03_CourseRAG_Evaluation_Dataset_and_Baseline_v1.0.md`
- `03A_CourseRAG_Evaluation_Dataset_Construction_Guide_v1.0.md`

**适用仓库：** `meo0306/agent_coursepilot`  
**改造方式：** 先在现有仓库内逻辑拆分，再形成独立 `course-rag` 仓库  
**核心优先级：** 文档解析与 OCR → 知识点资产 → 检索准确率 → 引用可信度 → 基础 QA

---

## 1. 文档目的

本文档把 CourseRAG PRD 转化为可执行的技术架构、模块拆分、数据模型、处理流水线、API、配置、迁移步骤和验收要求。

本文档重点回答：

1. 现有 `src/coursepilot/rag/` 应如何迁移；
2. PDF、DOCX、OCR、Evidence、Chunk 和知识点如何形成统一数据流；
3. 如何避免每个 Chunk 单独调用 LLM 抽取知识点；
4. 如何实现 Dense + Sparse + Fusion + Reranker；
5. Query Processing 的模块边界和启用策略是什么；
6. Context Packing 和基础引用 QA 如何实现；
7. PostgreSQL、Chroma、BM25 索引和文件系统如何保持版本一致；
8. 如何支持缓存、断点恢复、增量更新和教师写回富化；
9. 如何接入已经确定的评测数据集与 B0—B8、Q0—Q3 基线；
10. 如何在不破坏 CoursePilot 的情况下完成逻辑拆分和最终拆仓。

---

## 2. 现有实现基线

现有实现必须保留为正式 B0，不应直接删除或覆盖。

| 能力 | 当前文件 |
|---|---|
| PDF 解析 | `src/coursepilot/rag/parsers/pdf_parser.py` |
| DOCX 解析 | `src/coursepilot/rag/parsers/docx_parser.py` |
| RAG 数据类型 | `src/coursepilot/rag/types.py` |
| Chunk | `src/coursepilot/rag/chunker.py` |
| 知识点抽取 | `src/coursepilot/rag/knowledge_points.py` |
| Embedding | `src/coursepilot/rag/embeddings.py` |
| Chroma | `src/coursepilot/rag/vector_store.py` |
| Retriever | `src/coursepilot/rag/retriever.py` |
| KB 服务 | `src/coursepilot/services/kb_service.py` |
| Chunk ORM | `src/coursepilot/models/chunk.py` |
| 评测 | `src/coursepilot/evals/` |

当前行为：

- PDF 按页提取纯文本；
- DOCX 被整体扁平化；
- `ParsedDocument` 只有简单 Section 列表；
- Chunk 默认按 1000 字符和 150 字符重叠切分；
- 每个 Chunk 单独执行知识点抽取；
- 知识点仅保存为 `list[str]`；
- 检索为 Course 级 Chroma Dense Top-K；
- PostgreSQL 只保存 Chunk 预览和少量元数据；
- 重建时直接删除旧索引和数据库 Chunk 后重写；
- 已有数据库任务 Worker、任务租约和幂等机制可复用。

需要调整四个基础假设：

1. 原始文档不是纯字符串，而是有结构和坐标的版本化对象；
2. Evidence 是引用基础，Chunk 只是可替换的检索视图；
3. 知识点是课程级持久化资产，不是 Chunk 上的临时字符串；
4. 向量和稀疏索引是派生物，PostgreSQL 才是业务事实源。

---

## 3. 目标架构

```text
PDF / DOCX
    ↓
Document Registry
    ↓
Parser Router
    ├── Native PDF Parser
    ├── DOCX Structure Parser
    └── Page-level OCR Provider
    ↓
Canonical Document IR
    ├── Pages / Sections / Blocks
    ├── Tables
    └── Source Spans
    ↓
Normalizer / Noise Classifier / Section Builder
    ↓
Evidence Builder
    ↓
Parent-Child Chunker
    ↓
Knowledge Point Pipeline
    ↓
Dense + Sparse Index Builder
    ↓
Query Processing
    ↓
Hybrid Retrieval + Reranker
    ↓
Context Packing
    ↓
Citation QA
```

### 3.1 目标目录

```text
src/
├── courserag/
│   ├── api/
│   ├── application/
│   ├── domain/
│   ├── parsers/
│   │   └── ocr/
│   ├── evidence/
│   ├── chunking/
│   ├── knowledge_points/
│   ├── query/
│   ├── retrieval/
│   ├── context/
│   ├── qa/
│   ├── indexing/
│   ├── persistence/
│   ├── jobs/
│   ├── providers/
│   ├── evals/
│   └── settings.py
│
└── coursepilot/
    ├── ports/courserag.py
    ├── adapters/local_courserag.py
    └── clients/courserag_http.py
```

模块依赖约束：

- `domain/` 不依赖 FastAPI、SQLAlchemy、Chroma 或具体模型 SDK；
- `application/` 只依赖 Domain 和 Port；
- `api/` 只负责 Schema、认证、错误映射和调用 Application Service；
- CoursePilot 只依赖 `CourseRAGServicePort`；
- Local Adapter 与 HTTP Client 使用同一组 DTO；
- CoursePilot Agent 节点不得导入 Parser、Chroma 或 BM25 实现。

---

## 4. 技术选型

### 4.1 保留

- FastAPI；
- SQLAlchemy + Alembic；
- PostgreSQL；
- PyMuPDF；
- `python-docx`；
- 现有 API LLM、Embedding Provider；
- Chroma 作为 MVP Dense Index；
- 现有数据库任务 Worker；
- pytest、ruff、mypy。

### 4.2 新增候选

| 能力 | 方案 |
|---|---|
| Sparse Retrieval | `bm25s` |
| 中文 Sparse Tokenizer | `jieba` 搜索模式 + 英文/符号保留 + 字符二元组兜底 |
| OCR 默认候选 | RapidOCR ONNX CPU Profile |
| OCR 兼容兜底 | PyMuPDF + Tesseract |
| OCR 准确率增强 Profile | PaddleOCR |
| 文本相似度归并 | 复用 Embedding API |
| HTTP Client | `httpx` |

OCR 默认引擎不凭经验永久锁定。应在 15 页 OCR Pilot Gold 上比较 CER、耗时、内存、安装复杂度和中英文效果，再冻结默认 Profile。

### 4.3 暂不迁移向量数据库

MVP 保留 Chroma，但通过 `DenseIndexPort` 隔离。当前优先解决解析、知识点、混合检索和引用，而不是为更换数据库而更换数据库。后续只有压测或部署约束明确证明 Chroma 不足时，再比较 Qdrant、Milvus 或 pgvector。

---

## 5. 统一文档中间表示

现有 `ParsedSection(content, page, title)` 需要替换为版本化 Document IR。

```python
class ParsedDocumentIR(BaseModel):
    document_id: str
    document_version_id: str
    source_format: Literal["pdf", "docx"]
    parser_version: str
    pages: list[PageIR]
    sections: list[SectionIR]
    warnings: list[ParseWarning]


class PageIR(BaseModel):
    page_id: str
    page_number: int | None
    width: float | None
    height: float | None
    source_mode: Literal["native_text", "ocr", "hybrid", "logical_docx"]
    blocks: list[BlockIR]
    ocr_result_id: str | None


class BlockIR(BaseModel):
    block_id: str
    block_type: str
    text: str
    order_index: int
    bbox: tuple[float, float, float, float] | None
    style: dict
    source_span: dict
    confidence: float | None


class SectionIR(BaseModel):
    section_id: str
    parent_section_id: str | None
    level: int
    title: str
    section_path: list[str]
    order_index: int
    block_ids: list[str]
    content_hash: str
```

### 5.1 PDF

原生解析使用 PyMuPDF `dict/rawdict`，保留 Block、Line、Span、字体、Bounding Box、页面尺寸和图片信息。

`PageParseModeClassifier` 按页判断：

- 原生字符数量；
- 可打印字符比例；
- 乱码比例；
- 图片覆盖；
- 文本 Block 覆盖；
- 用户是否强制 OCR。

输出：

```python
class PageParseDecision(BaseModel):
    mode: Literal["native", "ocr", "hybrid"]
    reasons: list[str]
    metrics: dict[str, float]
```

### 5.2 OCR

统一 Port：

```python
class OCRProvider(Protocol):
    def recognize(self, page_image: ImageInput) -> OCRPageResult:
        ...
```

保存 Text、Line/Block Bounding Box、Confidence、Engine、Model Version、DPI、Image Hash 和 Warnings。

混合页面处理：

1. 保留可靠原生 Block；
2. 对无文本或低质量区域 OCR；
3. 按坐标合并；
4. 去除重复文本；
5. 标记每个 Block 的来源。

页眉页脚通过跨页重复位置和文本统计识别，只标记为噪声，不不可逆删除。

跨页段落根据句末标点、字体、缩进、标题边界和列表/表格状态合并，并保留原始 Block ID。

### 5.3 DOCX

主 Parser 改用 `python-docx`，保留：

- Paragraph 与 Style；
- Heading Level；
- Runs；
- Bold/Italic；
- Numbering；
- Tables；
- Section/Page Break；
- 页眉、页脚和页码域；
- 页面尺寸、方向和页边距；
- Inline Shape Placeholder；
- 原始顺序。

#### 5.3.1 DOCX 原始页码承诺

CourseRAG 对 DOCX 必须提供可引用的页码，但需要把“原始页码”定义为：

> 在上传时使用固定、可追溯的分页渲染 Profile 对 DOCX 生成分页快照，并以该快照中的物理页和显示页码作为该文档版本的原始分页基准。

原因是 DOCX 的自动分页由版式、字体、分页规则和渲染器共同决定，`python-docx` 只能读取文档结构，不能独立恢复每个段落最终位于哪一页。

新增统一接口：

```python
class DocxPaginationProvider(Protocol):
    def render(self, document_path: str) -> DocxPaginationSnapshot:
        ...
```

MVP Profile：

1. **默认可复现 Profile：** 固定版本 LibreOffice Headless，在受控容器和固定字体包中转换 PDF；
2. **高保真可选 Profile：** Windows Worker 上的 Microsoft Word Renderer；
3. 若默认 Profile 检测到缺失字体、转换失败或文本对齐异常，文档进入 `ready_with_warnings` 或切换已配置的高保真 Profile。

分页处理流程：

```text
python-docx 解析结构
→ 固定 Renderer 生成 PDF 分页快照
→ PyMuPDF 读取分页文本和坐标
→ 将 DOCX Paragraph/Table Block 与 PDF Block 顺序对齐
→ 为每个 DOCX Block 写入物理页和显示页码
→ 保存 Renderer Manifest 和分页快照 Hash
```

每个 DOCX Block / Evidence 至少保存：

```python
class DocxPageAnchor(BaseModel):
    physical_page_index: int
    display_page_label: str | None
    section_page_index: int | None
    renderer_provider: str
    renderer_version: str
    render_profile_hash: str
    rendered_pdf_hash: str
    alignment_confidence: float
```

其中：

- `physical_page_index` 是分页快照中的第几张物理页；
- `display_page_label` 是文档页眉/页脚展示的页码，如 `ii`、`1`、`15`；
- 页码按 Section 重新编号时，两者可能不同；
- 引用默认展示 `display_page_label`，同时保留 `physical_page_index` 用于稳定定位；
- 对齐置信度低于阈值时必须产生告警，不得静默给出错误页码。

DOCX 引用位置最终使用：

```text
display_page_label / physical_page_index
+ section_path
+ paragraph_index
+ block_id
+ char_range
```

`section_path + block_id + char_range` 仍是页码变化后的稳定兜底定位。

### 5.4 Section Builder

综合 PDF 字体层级、标题编号、DOCX Heading Style、标题正则和上下文顺序形成 Section Tree。冲突时产生 Warning，不强行猜测。

---

## 6. Evidence 与 Chunk

### 6.1 Evidence

```python
class EvidenceRecord(BaseModel):
    evidence_id: str
    document_version_id: str
    section_id: str
    block_start_id: str
    block_end_id: str
    char_start: int
    char_end: int
    text: str
    content_hash: str
    page_start: int | None
    page_end: int | None
    bboxes: list[dict]
    source_mode: str
```

`evidence_id` 推荐由文档版本、Block 范围、字符范围和文本 Hash 计算。相同版本、相同原文范围重复构建时应得到相同 ID。

Evidence 优先对应：

- 完整定义；
- 完整段落；
- 标题 + 列表；
- 完整步骤组；
- 表题 + 表格；
- 示例 + 解释；
- 公式占位 + 说明。

### 6.2 引用迁移

新文档版本创建后依次尝试：

1. Text Hash 精确匹配；
2. Section Path + 局部文本；
3. 相似度 + 邻接位置候选；
4. 高置信度标记 `migrated`；
5. 多义匹配标记 `needs_review`；
6. 无匹配标记 `invalid`。

### 6.3 Parent-Child Chunk

Parent 用于上下文：

- 约 1200～2200 Tokens；
- 不跨主要 Section；
- 长 Section 可分多个 Parent。

Child 用于召回：

- 约 250～500 Tokens；
- 以 Block/Sentence 为边界；
- 一个 Child 指向一个 Parent；
- 一个 Child 关联一个或多个 Evidence。

切分顺序：

```text
Section
→ Block Group
→ Paragraph/List/Table
→ Sentence
→ Token Limit
```

Chunk ID 可随 Chunk Profile 变化，Evidence ID 不应随之变化。

---

## 7. 知识点抽取流水线

### 7.1 抽取单位

从“每个 Child Chunk 单独抽取”改为：

```text
Section
→ 1～N 个语义完整 Extraction Window
→ 批量并发 LLM
→ Candidate KP
→ 规范化
→ 局部去重
→ 课程级归并
→ Evidence/Chunk 链接
→ 发布与审核
```

默认规则：

- 短 Section 整体输入；
- 长 Section 使用 Parent Chunk 或 1500～3000 Tokens Block Window；
- 相邻 Window 重叠一个 Block；
- Prompt 中包含 Block ID 和 Evidence ID；
- 不机械地对每个 Child Chunk 调用一次 LLM。

### 7.2 输出 Schema

```python
class KnowledgePointCandidate(BaseModel):
    canonical_name: str
    aliases: list[str]
    summary: str
    parent_name: str | None
    evidence_refs: list[KnowledgePointEvidenceRef]
    confidence: float
    ambiguity_flags: list[str]
```

Evidence 必须引用稳定 ID，不只返回自由文本。

### 7.3 调用与缓存

- Provider 从环境读取；
- Structured Output；
- 低温度；
- 并发初始上限 4；
- 指数退避；
- 单 Window 失败可单独重跑；
- 保存 Prompt Hash、Model、Token、Cost。

缓存键：

```text
hash(window_content_hash
     + evidence_ids
     + prompt_hash
     + provider
     + model
     + extractor_config_version)
```

### 7.4 规范化与归并

顺序：

1. Unicode/空白/大小写规范；
2. 特殊术语保护；
3. 标准名称精确匹配；
4. Alias 匹配；
5. Embedding 相似度生成聚类候选；
6. 边界案例进入 `needs_review`。

Embedding 相似度只用于候选归并，不自动决定 Gold。

### 7.5 父子关系

MVP 只保留可选 `parent_knowledge_point_id`：

- 优先来自明确章节层级或同批次上位概念；
- 不确定时为空；
- 不生成先修、相关、因果关系；
- 人工界面可调整。

### 7.6 发布分数

模型自报 Confidence 不能直接作为发布依据。`publish_score` 组合：

- 模型置信度；
- Evidence 质量；
- 名称质量；
- 跨 Window 支持；
- 歧义惩罚；
- 重复惩罚。

默认阈值 0.75，在 Dev Gold 上校准。

### 7.7 KP-Chunk 映射

先生成 `KnowledgePointEvidenceLink`，再借助 `ChunkEvidenceLink` 推导 `KnowledgePointChunkLink`。Chunker 改变时重建映射，不重新抽取知识点。

---

## 8. Query Processing

统一接口：

```python
class QueryStep(Protocol):
    name: str
    def run(self, state: QueryState) -> QueryState: ...
```

`QueryState` 保存 Raw Query、Current Query、Filters、Linked KP、Expansions、Route、Warnings 和 Step Trace。

### 8.1 Normalize

确定性执行：

- Unicode；
- 全角半角；
- 空白和标点；
- 英文大小写副本；
- `A*`、`C++` 等特殊符号保护。

始终保留 `raw_query`。

### 8.2 Filter Parser

规则优先解析：

- 文档；
- 章节；
- 页码；
- 知识点；
- Source Tier；
- “只看”“限定”“不包括”。

复杂查询可调用结构化 LLM Fallback，但不得覆盖显式过滤条件。

### 8.3 KP Linker

顺序：

1. Canonical Name 精确；
2. Alias 精确；
3. 规范化匹配；
4. Fuzzy Candidate；
5. Embedding Candidate；
6. 多义时保留候选和置信度。

### 8.4 Alias Expansion

仅使用持久化、已审核或高置信度 Alias，记录每个扩展来源，禁止无限递归。

### 8.5 Router

Route：

- `fact`
- `definition`
- `comparison`
- `procedure`
- `example_application`
- `cross_section`

Route 调整 Dense/Sparse 权重、Candidate-K、内容角色偏好、Multi-query 和 Context Expansion。规则低置信度时使用结构化 LLM。

### 8.6 Multi-query

必须实现，但按策略触发：

- Query 过长或多意图；
- Cross-section；
- 首次召回低；
- 用户显式要求。

最多 3 个 Rewrite，保留 Filter 和关键术语，失败时回退原 Query。

### 8.7 Low-recall Retry

满足以下任一条件可重试一次：

- 无候选；
- Top-1 Rerank 分数低；
- Top-K 整体低；
- 高置信度 KP 未命中；
- 结果全部来自错误 Section。

阈值只在 Dev 上确定。

---

## 9. Hybrid Retrieval 与 Context

### 9.1 Port

```python
class DenseRetrieverPort(Protocol):
    def search(self, request: DenseSearchRequest) -> list[ScoredHit]: ...

class SparseRetrieverPort(Protocol):
    def search(self, request: SparseSearchRequest) -> list[ScoredHit]: ...

class RerankerPort(Protocol):
    def rerank(self, query: str, hits: list[RetrievalHit]) -> list[RetrievalHit]: ...
```

### 9.2 Dense

Chroma Collection 命名包含：

```text
course_id + index_version_id
```

要求：

- 批量 Embedding；
- Metadata 包含 Document Version、Section、KP、Source Tier；
- 完整正文以 PostgreSQL/Artifact Store 为准；
- Chroma 只做派生索引；
- 查询结果通过 Chunk Repository 补全。

### 9.3 Sparse

BM25S 索引与 `index_version_id` 绑定，持久化：

- Sparse Matrix；
- Corpus Mapping；
- Tokenizer Config；
- Index Manifest。

中文 Tokenizer 使用搜索分词，保留英文、数字、特殊术语，并增加字符二元组兜底。

### 9.4 Fusion

默认 RRF：

```text
RRF(d) = Σ 1 / (k + rank_i(d))
```

`k` 初始 60，可配置。保留 Dense/Sparse 原始 Rank、Score、Fusion Score。

### 9.5 Reranker

Reranker 不默认使用通用聊天 LLM。MVP 优先使用专门训练的文本相关性重排模型，通过独立 Rerank API 或本地模型 Adapter 对 `query-document` 候选进行联合打分。

常见实现类型：

- Cross-Encoder：分别对 Query 与每个候选文本联合编码并输出相关性分数；
- Listwise Reranker：一次比较 Query 与多个候选，更直接建模候选之间的相对顺序；
- Late-Interaction：在精度和吞吐量之间折中；
- 通用 LLM Listwise Prompt：仅保留为实验性 Adapter，不作为默认方案。

选择专用 Reranker 而非通用 LLM 的原因：

- 输出目标就是相关性排序，不需要生成自然语言；
- 延迟、成本和结果格式更可控；
- 分数、排名和截断行为更适合自动评测；
- 避免聊天模型 Prompt、推理强度和生成随机性干扰检索实验。

定义 Provider 抽象：

```python
class RerankerPort(Protocol):
    def rerank(
        self,
        *,
        query: str,
        documents: list[RerankDocument],
        top_n: int,
    ) -> RerankResult:
        ...
```

MVP 支持的 Adapter 类型：

- `cohere`：调用 Cohere Rerank API；
- `voyage`：调用 Voyage Rerank API；
- `jina`：调用 Jina Reranker API；
- `local_cross_encoder`：部署本地多语言 Cross-Encoder；
- `disabled`：仅使用 Fusion Rank；
- `llm_listwise_experimental`：仅供消融实验，默认关闭。

默认运行流程：

```text
Dense Top 30 + Sparse Top 30
→ RRF 合并为 Top 30
→ 专用 Reranker 批量打分
→ 返回 Top 8
```

必须保存：

- Provider 与 Model；
- 原始候选 ID 和输入顺序；
- Provider 原始相关性分数；
- Rerank Rank；
- 文档截断信息；
- Latency；
- Request Count；
- Token/计费单位与 Cost；
- Fallback Reason。

#### 9.5.1 配置原则

Rerank API 通常不属于 OpenAI Chat Completions 兼容接口，因此不能假设现有 `COMPATIBLE_BASE_URL` 同时支持 Rerank。应单独配置：

```env
COURSERAG_RERANKER_PROVIDER=jina
COURSERAG_RERANKER_BASE_URL=https://api.jina.ai/v1/rerank
COURSERAG_RERANKER_API_KEY=
COURSERAG_RERANKER_MODEL=jina-reranker-v3

COURSERAG_RERANKER_CANDIDATE_K=30
COURSERAG_RERANKER_TOP_N=8
COURSERAG_RERANKER_BATCH_SIZE=16
COURSERAG_RERANKER_MAX_DOC_TOKENS=1200
COURSERAG_RERANKER_TIMEOUT_SECONDS=30
COURSERAG_RERANKER_MAX_RETRIES=2
COURSERAG_RERANKER_TRUNCATION=true
COURSERAG_RERANKER_FALLBACK_POLICY=fusion_order
```

Provider Adapter 将差异映射为统一字段。不得在不同 Provider 之间直接比较绝对 Score；每个模型的拒检阈值和低召回阈值必须在 Dev 上单独校准。

#### 9.5.2 推荐默认选择

当前项目以中文课程资料、API 优先和低部署成本为约束，默认建议：

1. 先用支持中文/多语言的专用 Rerank API；
2. 在 DS5 Dev 上比较至少两个候选模型；
3. 以 `nDCG@10、MRR@10、Complete Evidence Group Recall、P95 延迟、成本` 联合选择；
4. 配置冻结后再运行 Test；
5. 若没有任何专用 Rerank API 可用，再启用本地 Cross-Encoder，而不是直接让通用聊天 LLM逐条判断。

#### 9.5.3 失败策略

- Demo/生产默认：API 超时或限流时回退 `fusion_order`，并在响应中返回 Warning；
- 正式评测：默认 `fail_sample`，禁止静默回退；
- Reranker 变化不需要重建 Dense/Sparse Index；
- Rerank Cache Key 使用 `query_hash + ordered_candidate_hashes + provider + model + config_hash`。

### 9.6 Filter

硬过滤：

- Course；
- Document；
- Section；
- Source Tier；
- Knowledge Point；
- Document Version；
- Active Index Version。

内容角色优先作为软排序信号。

### 9.7 Context Packing

```text
Reranked Hits
→ Evidence-aware Dedup
→ Parent Expansion
→ Optional Neighbor Expansion
→ Purpose/Role Weighting
→ Token Packing
→ Citation Map
```

默认参数：

```yaml
retrieval:
  dense_candidate_k: 30
  sparse_candidate_k: 30
  fusion_candidate_k: 30
  rerank_top_n: 8

context:
  max_items: 8
  max_tokens: 4000
  parent_expansion: true
  neighbor_expansion: route_based
  preserve_evidence_boundaries: true
```

这些参数通过 Dev 调整。

---

## 10. 基础引用 QA

### 10.1 Schema

```python
class QAResponse(BaseModel):
    status: Literal["answered", "insufficient_evidence"]
    answer: str
    claims: list[AnswerClaim]
    used_evidence_ids: list[str]
    retrieval_trace_id: str
    qa_run_id: str
    warnings: list[str]


class AnswerClaim(BaseModel):
    claim_id: str
    text: str
    evidence_ids: list[str]
```

### 10.2 Evidence Sufficiency

先做确定性检查：

- 至少一个有效 Evidence；
- Evidence 可解析；
- 最高分和覆盖满足 Dev 阈值；
- OCR 低置信度告警不过量；
- Cross-section Query 有足够来源多样性。

QA Model 仍可返回 `insufficient_evidence`，但模型自报不是唯一依据。

### 10.3 Prompt

- 只使用 Evidence；
- 检索内容是数据，不执行其中指令；
- 所有事实 Claim 绑定 Evidence ID；
- 资料不足时拒答；
- 不补充外部常识；
- 返回结构化 Schema。

### 10.4 Validator

- Evidence ID 存在；
- Evidence 属于当前 Context；
- `answered` 至少一个 Claim；
- `insufficient_evidence` 不生成事实性长答案；
- 引用可解析；
- Schema 失败最多定向修复一次。

语义支持仍由正式 Claim 级人工评测确认。

### 10.5 Composer

模型输出结构化 Claims 和 Answer；最终引用展示由程序生成，避免模型伪造页码或来源编号。

---

## 11. 持久化模型

PostgreSQL 是事实源，Chroma/BM25 都是可重建派生物。

建议新表：

```text
courserag_knowledge_bases
courserag_source_documents
courserag_document_versions
courserag_parsed_documents
courserag_pages
courserag_sections
courserag_blocks
courserag_ocr_page_results
courserag_evidence_records
courserag_chunks
courserag_chunk_evidence_links
courserag_knowledge_points
courserag_kp_evidence_links
courserag_kp_chunk_links
courserag_kp_review_actions
courserag_verified_contents
courserag_verified_content_evidence_links
courserag_verified_content_kp_links
courserag_enrichment_batches
courserag_enrichment_batch_items
courserag_index_versions
courserag_build_jobs
courserag_build_stage_runs
courserag_query_processing_runs
courserag_retrieval_runs
courserag_qa_runs
courserag_answer_claims
courserag_answer_claim_evidence_links
```

高数量 Retrieval Hits、Context Items 第一版可存 JSONB 摘要或 Artifact 文件，正式评测保存 JSONL。

状态必须分离：

```text
KnowledgePoint.origin:
auto_extracted / manual_created / imported

KnowledgePoint.review_status:
unreviewed / needs_review / approved / rejected / deprecated

VerifiedContent.source_tier:
teacher_verified

VerifiedContent.content_type:
verified_question / verified_answer_explanation / verified_lesson_fragment

VerifiedContent.status:
active / revoked / pending_enrichment / enriched
```

不得用 `teacher_verified` 表示知识点审核状态。

---

## 12. 索引版本、构建任务与增量更新

### 12.1 原子发布

```text
创建 IndexVersion(building)
→ 构建 Chroma Staging Collection
→ 构建 BM25 Staging Directory
→ 校验 ID、数量和抽样查询
→ IndexVersion(validating)
→ PostgreSQL 事务切换 active_index_version_id
→ 新版本 active
→ 旧版本 retired
```

失败时不切换 Active Pointer，旧索引继续服务。

发布前检查：

- Active Document Version 完整；
- Chunk、Evidence、Mapping 数量；
- Dense ID 与数据库 Chunk ID；
- Sparse Corpus Mapping；
- KP Links 无孤儿；
- 抽样 Search；
- Index Manifest Hash。

### 12.2 Build Stage

```text
validate_file
detect_parse_mode
parse_native
ocr_pages
normalize_blocks
build_sections
build_evidence
build_chunks
extract_knowledge_points
consolidate_knowledge_points
build_dense_index
build_sparse_index
validate_index
publish_index
```

每个 Stage 实现：

```python
class BuildStage(Protocol):
    name: str
    def fingerprint(self, context: BuildContext) -> str: ...
    def run(self, context: BuildContext) -> StageResult: ...
```

`StageResult` 保存 Artifact URI/Hash、Count、Warnings、Duration、Provider Usage 和 Status。

### 12.3 缓存与恢复

缓存键包含上游 Artifact Hash、Stage Version、配置、Provider/Model、Prompt Hash。

复用现有 Worker：

- Build Job 只创建一次；
- Stage 单独状态；
- Lease 过期可接管；
- Fingerprint 未变则跳过；
- 可从指定 Stage 重跑；
- 副作用幂等。

### 12.4 增量范围

| 变化 | 重处理 |
|---|---|
| 文档显示名称 | Metadata |
| 单 Section 内容 | 当前 Section + 相邻边界 |
| 新增/删除 Section | 相关 Section + KP 归并 |
| OCR 页替换 | 当前页与所属 Section |
| Parser 版本 | 当前 Document |
| Chunker 变化 | Chunk、KP-Chunk、Index |
| KP Prompt/Model | 指定 Section 或 Document |
| Embedding 变化 | Dense Index |
| BM25 Tokenizer | Sparse Index |
| Reranker/QA Prompt | 不重建 Index |

### 12.5 教师写回

1. 立即创建 `VerifiedContentRecord`；
2. 进入独立 Verified 检索段；
3. 标记 `pending_enrichment`；
4. 达到 10 条、3000 Tokens、24 小时或手动触发时创建 Batch；
5. 批量抽取知识点；
6. 归并课程 KP；
7. 发布新 Index Version。

阈值可配置。

---

## 13. API 与兼容层

统一前缀：

```text
/api/courserag/v1
```

主要 Endpoint：

```text
POST   /knowledge-bases
GET    /knowledge-bases/{course_id}

POST   /knowledge-bases/{course_id}/documents
GET    /documents/{document_id}/versions

POST   /documents/{document_id}/builds
GET    /builds/{job_id}
POST   /builds/{job_id}/retry
GET    /builds/{job_id}/events

GET    /knowledge-bases/{course_id}/knowledge-points
PATCH  /knowledge-points/{kp_id}
POST   /knowledge-points/{kp_id}/approve
POST   /knowledge-points/merge

POST   /knowledge-bases/{course_id}/search
POST   /knowledge-bases/{course_id}/contexts
POST   /knowledge-bases/{course_id}/qa

GET    /evidence/{evidence_id}
POST   /evidence/batch

POST   /knowledge-bases/{course_id}/verified-content
POST   /verified-content/{content_id}/revoke
POST   /knowledge-bases/{course_id}/enrichment-batches
```

现有接口暂时保留：

```text
POST /api/coursepilot/documents/{document_id}/build-kb
POST /api/coursepilot/courses/{course_id}/kb/search
```

内部改为调用 `LocalCourseRAGAdapter`，直到 CoursePilot Client 迁移完毕。

---

## 14. 配置与可观测性

建议新增 `COURSERAG_*` 配置，核心包括：

```env
COURSERAG_DATABASE_URL=
COURSERAG_STORAGE_DIR=
COURSERAG_INDEX_DIR=

COURSERAG_OCR_PROVIDER=rapidocr
COURSERAG_OCR_DPI=200
COURSERAG_OCR_MIN_NATIVE_CHARS=30

COURSERAG_PARENT_CHUNK_MAX_TOKENS=1800
COURSERAG_CHILD_CHUNK_MAX_TOKENS=400

COURSERAG_KP_PROVIDER=openai-compatible
COURSERAG_KP_MODEL=
COURSERAG_KP_CONCURRENCY=4
COURSERAG_KP_PUBLISH_THRESHOLD=0.75

COURSERAG_EMBEDDING_PROVIDER=openai-compatible
COURSERAG_EMBEDDING_MODEL=
COURSERAG_EMBEDDING_BATCH_SIZE=32

COURSERAG_SPARSE_PROVIDER=bm25s
COURSERAG_RRF_K=60

COURSERAG_RERANKER_PROVIDER=jina
COURSERAG_RERANKER_BASE_URL=https://api.jina.ai/v1/rerank
COURSERAG_RERANKER_API_KEY=
COURSERAG_RERANKER_MODEL=jina-reranker-v3
COURSERAG_RERANKER_CANDIDATE_K=30
COURSERAG_RERANKER_TOP_N=8
COURSERAG_RERANKER_BATCH_SIZE=16
COURSERAG_RERANKER_TIMEOUT_SECONDS=30
COURSERAG_RERANKER_MAX_RETRIES=2
COURSERAG_RERANKER_FALLBACK_POLICY=fusion_order

COURSERAG_QUERY_MULTI_REWRITE=route_based
COURSERAG_QUERY_LOW_RECALL_RETRY=true

COURSERAG_QA_PROVIDER=openai-compatible
COURSERAG_QA_MODEL=
COURSERAG_QA_MAX_CONTEXT_TOKENS=4000
```

Build 记录 Stage、Count、Hash、Cache、Duration、Retry、Token、Cost。Retrieval 记录 Query Steps、Dense/Sparse、Fusion、Rerank、Context 和 Index Version。QA 在 LangSmith 中记录 Prompt、Context、Claims、Evidence、Repair 和 Abstention；PostgreSQL 保存业务摘要和 Trace ID。

Secret 不进入日志、Run Manifest 或 Trace Metadata。

---

## 15. 安全与测试

### 15.1 文件安全

- 只允许 PDF/DOCX；
- MIME 与后缀双检；
- 文件大小限制；
- PDF 加密检测；
- DOCX ZIP Bomb 检测；
- 路径穿越防护；
- OCR 页数、DPI、CPU/内存限制。

### 15.2 Prompt Injection

- 检索内容视为不可信数据；
- System Prompt 不执行资料中的指令；
- Context 使用明确边界；
- 疑似注入内容只标记，不擅自删除原文；
- QA 只返回结构化 Schema；
- CourseRAG QA 不具备工具执行权限。

### 15.3 测试

Unit：

- Page Classifier；
- Section Builder；
- Evidence ID；
- Chunk Boundary；
- KP Normalize/Cache；
- Filter Parser；
- KP Linker；
- RRF；
- Context Budget；
- QA Validator；
- Incremental Diff。

Contract：

- Local Adapter；
- Remote Client；
- Mock Service。

Integration：

- Native PDF；
- Scanned PDF；
- Mixed PDF；
- DOCX；
- Staging Publish；
- Search；
- QA；
- Writeback；
- Batch Enrichment；
- Worker Recovery。

Evaluation：

- DS0—DS8；
- B0—B8；
- Q0—Q3。

模块完成后跑 Pilot，阶段完成后跑 Dev，配置冻结后才跑 Test。

---

## 16. 迁移策略

### 16.1 旧 Chunk 不迁移为新 Evidence

旧 `coursepilot_chunks` 只有预览、简单页码和知识点字符串，不足以可靠反推 Evidence。

因此：

- 旧数据保留为 B0；
- 新系统从原始 PDF/DOCX 重建；
- 原 Chroma Collection 标记 Legacy；
- 新 Index 使用版本化 Collection；
- 不从旧 Chunk 生成新 Gold。

### 16.2 文件类型

产品上传层只注册 PDF 和 DOCX。TXT、Markdown、XLSX Parser 可暂时保留代码，但不进入 Product API、Sample、MVP 和正式测试，拆仓时删除或移入 Legacy。

### 16.3 旧写回内容

- 类型和来源明确的迁移到 `VerifiedContentRecord`；
- 类型不明确的标记 Legacy；
- 不迁移为 `approved KnowledgePoint`；
- 不覆盖 Primary Source。

---

## 17. 分阶段实施

### Phase 0：冻结 B0

- 保存 Commit、环境和旧报告；
- 正式 Gold 不再从 Top-K 反推；
- 增加阶段计时。

**验收：** B0 可重复运行。

### Phase 1：Port 与 Package

- 新建 `src/courserag`；
- Domain DTO、Port、Local Adapter；
- 旧 KB Service 调 Adapter；
- Contract Test。

**验收：** CoursePilot 不直接依赖 Chroma，旧 API 不变。

### Phase 2：数据与版本

- Alembic；
- Document Version、Evidence、Index、Build Stage；
- Repository；
- Active Index Pointer。

**验收：** 新版本不覆盖旧版本，索引可 Staging/Active/Retired。

### Phase 3：Parser 与 OCR

- PDF Block；
- DOCX Structure；
- Page Classifier；
- OCR；
- Noise；
- Section Tree；
- Parse Report。

**验收：** DS1 Pilot。

### Phase 4：Evidence 与 Chunk

- Evidence Builder；
- Stable ID；
- Parent-Child；
- Resolver；
- Citation Preview。

**验收：** DS2 Pilot，Chunker 变化不破坏 Evidence。

### Phase 5：知识点

- Section Window；
- Structured Extractor；
- Cache；
- Dedup；
- Mapping；
- Confidence；
- Review UI/API。

**验收：** DS3 Pilot，不再每 Child Chunk 调一次 LLM。

### Phase 6：Hybrid Retrieval

- Versioned Chroma；
- BM25S；
- Tokenizer；
- RRF；
- Reranker；
- Score Trace。

**验收：** B4/B5。

### Phase 7：Query Processing

- Normalize、Filter、KP Link、Alias、Router、Multi-query、Retry。

**验收：** DS4 Pilot，B6/B7 可消融。

### Phase 8：Context 与 QA

- Dedup、Expansion、Packing；
- Sufficiency；
- Structured QA；
- Claim Validator；
- Abstention。

**验收：** DS5 Pilot，Q0—Q3。

### Phase 9：增量与写回

- Section Diff；
- Artifact Reuse；
- Citation Migration；
- Writeback 白名单；
- Enrichment Batch。

**验收：** DS6/DS7 Pilot。

### Phase 10：正式评测

- DS0—DS8；
- Dev 调参；
- Test 冻结；
- 报告与 README。

**验收：** B0—B8、Q0—Q3 可复现。

### Phase 11：物理拆仓

- 独立 Repository、API、Worker、Database、Docker、CI；
- CoursePilot 使用 HTTP Client。

**验收：** Full Profile 与 Demo Profile 通过相同 Contract。

---

## 18. 推荐 PR 序列

```text
PR-01  Freeze B0 and evaluation contracts
PR-02  Add courserag package, ports, adapters
PR-03  Add database version and build-stage models
PR-04  Implement canonical PDF/DOCX IR
PR-05  Add OCR provider and page routing
PR-06  Add evidence and hierarchical chunking
PR-07  Refactor knowledge-point pipeline
PR-08  Add sparse index and hybrid retrieval
PR-09  Add reranker and score tracing
PR-10  Add query processing pipeline
PR-11  Add context packing
PR-12  Add citation QA and abstention
PR-13  Add incremental rebuild and citation migration
PR-14  Add verified writeback enrichment
PR-15  Complete evaluation and compatibility migration
PR-16  Extract physical course-rag repository
```

每个 PR 必须：

- 保持测试通过；
- 有回滚路径；
- 更新 Run Manifest；
- 标明对应数据集和基线；
- 不同时引入多个无法独立评测的大模块。

---

## 19. Definition of Done

### 架构

- CoursePilot 只依赖 Port；
- Local/Remote/Mock 通过同一 Contract；
- CourseRAG 可独立启动；
- PostgreSQL 是事实源；
- Dense/Sparse 可重建。

### 解析

- Native PDF、Scanned PDF、Mixed PDF、DOCX；
- Page-level OCR；
- Canonical IR；
- Section Tree；
- Stable Evidence；
- DOCX 通过固定 Renderer Profile 生成分页快照，同时保存物理页、显示页码和对齐置信度。

### 知识点

- Section Window 抽取；
- 持久化、缓存、归并；
- Evidence Link；
- 可选 Parent；
- Review；
- 0.75 可配置。

### 检索

- Dense、BM25、Fusion、Reranker；
- Query Processing；
- Score Trace；
- Context Packing。

### QA

- Evidence Sufficiency；
- Structured Claims；
- Claim-Evidence；
- Abstention；
- Q0—Q3。

### 可靠性

- Staging Publish；
- Index Rollback；
- Stage Cache；
- Worker Recovery；
- Section Incremental；
- Writeback Batch；
- Idempotency。

### 评测

- DS0—DS8；
- B0—B8；
- Q0—Q3；
- Dev/Test 隔离；
- 无 Gold 泄漏；
- 结果、延迟和成本可复现。

---

## 20. 当前默认技术结论

- 新建 `src/courserag`，不继续扩大 `src/coursepilot/rag`；
- 保留旧实现为 B0；
- PDF 使用 PyMuPDF 结构化 Block；
- DOCX 使用 `python-docx` 解析结构，并使用固定 Renderer Profile 承诺可追溯页码；
- OCR 按页路由，默认引擎由 Pilot 决定；
- Evidence 先于 Chunk；
- Parent-Child Chunk；
- 知识点按 Section Window 抽取并缓存；
- 不构建完整知识图谱；
- 默认发布阈值 0.75；
- Chroma 暂时保留并版本化；
- Sparse 使用 BM25S；
- Fusion 默认 RRF；
- Reranker 默认使用独立的多语言专用 Rerank API，不使用通用聊天 LLM；
- Query Processing 全模块可配置和消融；
- Multi-query 按 Route 或低召回触发；
- 默认 Retrieve 30 → Rerank 8 → Pack 4000 Tokens；
- QA 输出结构化 Claim 与 Evidence；
- PostgreSQL 是事实源；
- Index 使用 Staging + Active Pointer；
- 构建复用现有数据库 Worker；
- 文档增量默认 Section 粒度；
- 教师写回立即保存、批量富化；
- 最后再物理拆仓。
