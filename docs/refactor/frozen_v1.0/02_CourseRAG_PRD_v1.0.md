# CourseRAG 产品需求文档（PRD）

**文档版本：** v1.0  
**文档状态：** 冻结执行版
**冻结日期：** 2026-07-22
**上位文档：** `01_CoursePilot_CourseRAG_Split_and_Refactor_Plan_v1.0.md`  
**产品定位：** 面向中文课程资料的结构化知识库、知识点资产、检索与可信引用服务  
**支持文件类型：** PDF、DOCX  
**核心使用方：** CoursePilot、教师、开发与评测人员

---

## 1. 文档目的

本文档定义 CourseRAG 要解决的问题、目标用户、产品边界、核心流程、功能需求、数据对象、验收条件和版本范围。

本文档重点回答“CourseRAG 应具备什么能力”，不详细锁定 Parser、OCR、Chunker、Embedding、BM25、Reranker、任务队列或数据库的具体实现。相关技术选型和模块级改造将在《CourseRAG 具体技术改造方案》中展开。

---

## 2. 产品背景

CoursePilot 当前已经具备教案、试卷和 PPT 初稿生成流程，但底层知识库仍存在以下限制：

1. PDF 主要按页提取文本，无法可靠恢复标题层级、段落边界、表格和跨页内容；
2. 扫描 PDF 或低文本密度 PDF 缺少 OCR 兜底；
3. DOCX 虽然天然包含一定结构，但尚未形成统一的文档中间表示；
4. 文档切分主要依据固定字符长度，Chunk 与章节、段落和原始证据的对应关系不稳定；
5. 知识点抽取存在大量串行模型调用，但其结果尚未被充分视为可持久化、可复用的课程资产；
6. 检索以稠密向量召回为主，缺少关键词检索、Query Processing、融合和重排序；
7. 引用主要绑定 Chunk，Chunker 调整后引用稳定性不足；
8. RAG 处理、知识点、检索和引用缺乏独立、可信、可重复的评测体系；
9. CoursePilot 的教学设计质量依赖课程知识点的准确识别、覆盖控制和证据检索。

CourseRAG 将从 CoursePilot 中独立出来，成为面向课程资料的可复用知识基础设施。

---

## 3. 产品愿景

CourseRAG 的愿景是：

> 将 PDF、DOCX 格式的中文课程资料转化为结构清晰、知识点明确、可准确检索、可追溯引用、可重复评测的课程知识库，并通过稳定接口为 CoursePilot 和其他 Agent 提供知识点、检索与证据服务。

CourseRAG 不只是“向量化文件”，而是完成以下转换：

```text
原始课程文件
→ 原生文本解析或 OCR
→ 可追溯的结构化文档
→ 稳定的证据单元
→ 层级 Chunk
→ 可复用的知识点体系
→ Query Processing
→ 多路召回和重排序
→ 受 Token Budget 约束的上下文
→ 可核验引用
```

---

## 4. 已确认的产品决策

### 4.1 支持文件类型

CourseRAG 仅支持：

- PDF；
- DOCX。

当前版本明确不支持：

- XLSX；
- PPTX；
- Markdown；
- HTML；
- 独立图片文件；
- 音视频；
- 网页抓取。

PDF 中嵌入的扫描页或图像页属于 PDF 解析范围，不视为独立图片上传。

### 4.2 OCR 纳入 MVP

不可直接解析、文本密度过低或主要由扫描图像构成的 PDF，必须进入 OCR 兜底流程。

OCR 在 MVP 中至少需要：

- 检测需要 OCR 的页面；
- 对受影响页面执行基本文字识别；
- 保留页码和页面坐标；
- 返回 OCR 置信度；
- 将 OCR 文本标记为 `ocr_derived`；
- 支持原生文本页和 OCR 页混合处理；
- 低置信度页面进入解析警告；
- 不因少量不可识别内容导致整份文档构建失败。

MVP 只要求基本正文识别，不承诺复杂公式、手写体和高度复杂版面的高质量恢复。

### 4.3 核心优化优先级

优先级从高到低为：

1. 提升文档解析能力；
2. 提升检索准确率；
3. 增强引用可信度。

解析结果是检索和引用的上游基础。项目不采用“先堆检索算法、后补文档结构”的路线。

### 4.4 知识点抽取定位

知识点抽取是知识库构建的必经流程，不是可选插件，也不是每次检索时重复运行的在线步骤。

其产品行为必须满足：

- 在文档首次构建或需要重新构建时执行；
- 抽取结果持久化；
- 结果与文档版本、解析版本和抽取版本关联；
- 作为 Chunk 和 Evidence 的元信息被检索与 Agent 复用；
- 支持跨 Chunk、跨章节的同义项归并；
- 每个知识点绑定原文证据；
- 支持可选人工审核、修改、合并、拆分和停用；
- 未发生相关版本变化时，不重复抽取；
- 文档局部变化时，优先只重新处理受影响范围。

知识点抽取允许付出较高的一次性时间和模型调用成本，但要求后续复用，并通过批处理、缓存和增量处理控制总成本。

### 4.5 知识点层级与关系范围

MVP 支持可选的知识点父子层级，用于表达课程组织上的上位概念和下位概念。

MVP 不要求自动抽取：

- 先修关系；
- 一般包含关系图；
- 相关关系；
- 因果关系；
- 完整知识图谱。

父子层级主要用于组织和导航，可以来源于章节结构、规则推断或人工调整，不应被描述为完整知识图谱。

### 4.6 自动发布与审核原则

知识点抽取结果不要求教师逐条确认后才能进入可用知识库。

默认规则：

- 抽取置信度阈值可配置；
- MVP 默认阈值为 `0.75`；
- 置信度达到阈值且通过确定性质量检查的知识点可自动发布；
- 低于阈值、证据不足、疑似重复或粒度异常的知识点进入 `needs_review`；
- 存在待审核知识点不阻塞知识库发布；
- 知识库可标记为 `ready_with_warnings`；
- 教师审核用于提升可信度，而不是所有知识点上线的强制门槛。

### 4.7 模型 Provider 原则

主生成模型和 Embedding 默认通过环境变量配置的 API Provider 调用。Reranker 默认使用独立的专用 Rerank API，也允许配置本地多语言 Cross-Encoder；不要求其兼容 OpenAI Chat Completions 接口。

产品层不固定具体厂商，但必须记录：

- Provider；
- 模型名称；
- 模型版本或配置；
- Endpoint 配置标识；
- 调用成本和延迟。

### 4.8 Query Processing 原则

MVP 应尽可能上线对检索效果有直接价值的 Query Processing 能力，并保证：

- 每项能力可单独启用或关闭；
- 接口返回实际启用步骤；
- 评测能够进行逐项消融；
- 始终保留原始 Query；
- 改写结果不能无痕替代原 Query。

### 4.9 评测原则

当前不使用 LLM-as-a-Judge。正式评测基于：

- 确定性程序指标；
- 人工审核的 Gold Dataset；
- 小规模人工质量检查。

LLM 可以生成候选标注和候选知识点，但不得未经审核直接作为正式 Gold。

### 4.10 基础引用 QA 纳入 MVP

MVP 同时提供基础引用问答能力，以形成完整且可独立演示的 RAG 闭环：

```text
Question
→ Query Processing
→ Retrieval / Rerank
→ Context Packing
→ 基于 Evidence 的回答生成
→ Claim-Evidence 引用
→ 证据不足时拒答
```

基础 QA 的边界为：

- 只基于当前课程知识库回答；
- 复用统一检索和 Context 流程；
- 回答必须携带 Evidence 引用；
- 证据不足时允许明确拒答；
- 不执行开放网络搜索；
- 不承担 CoursePilot 的教案、试卷或 PPT 生成职责；
- 不承诺复杂多轮对话记忆。

---

## 5. 产品目标

### G1：可靠解析课程文档

系统能够从 PDF 和 DOCX 中恢复并保存：

- 文档；
- 页或分页信息；
- 章节层级；
- 标题；
- 段落；
- 列表；
- 表格；
- OCR 文本；
- 公式或特殊块的占位与位置信息；
- 原始顺序；
- 原文范围；
- 噪声标记。

### G2：形成可复用的知识点体系

系统能够从课程文档中抽取、归并和持久化知识点，并明确：

- 知识点名称；
- 别名；
- 简要说明；
- 可选父知识点；
- 所属章节；
- 原文证据；
- 相关 Chunk；
- 内容角色；
- 抽取置信度；
- 审核状态；
- 版本信息。

### G3：提升课程检索准确率

系统能够综合利用：

- 原文；
- OCR 文本；
- 章节路径；
- 知识点元信息；
- Query 标准化；
- 知识点链接；
- 查询扩展和必要改写；
- 稠密检索；
- 稀疏检索；
- 结果融合；
- 重排序；
- 条件过滤。

### G4：提供可信引用

系统返回的检索结果和上下文必须能够定位至稳定的原文证据，而不是只能定位到随切分策略变化的 Chunk。

### G5：支持独立评测

系统能够在固定语料和固定配置下运行解析、OCR、知识点、Query Processing、检索、QA 和引用评测，并保存可复现实验结果。

### G6：提供基础引用问答

系统能够针对课程资料完成：

- 基于 Evidence 的回答生成；
- 原子 Claim 与 Evidence 关联；
- 答案引用；
- 证据不足拒答；
- QA 运行追踪；
- QA 独立评测。

### G7：作为 CoursePilot 的独立基础服务

CoursePilot 不需要了解 Parser、OCR、向量库、Embedding 或 Reranker 的具体实现，只通过稳定接口获取：

- 课程知识点；
- 检索结果；
- Context Package；
- Evidence；
- 知识库构建状态；
- 审核内容写回结果；
- 可选的基础引用 QA 结果。

---

## 6. 非目标

首版 CourseRAG 不追求：

- 通用企业知识库平台；
- 任意文件格式兼容；
- 全自动知识图谱推理；
- 自动生成复杂课程本体；
- 自动抽取完整先修、相关和因果关系网络；
- 自研 Embedding、Reranker 或 OCR 模型；
- 百万级文档和高并发 SaaS；
- 替代教师进行最终知识点审核；
- 未经审核的模型生成内容自动写回；
- 完整教学管理系统；
- 教案、试卷、PPT 的业务生成；
- 通用聊天机器人或开放域问答；
- 复杂多轮对话记忆和会话画像。

---

## 7. 用户与使用方

### 7.1 教师用户

教师主要关心：

- 文件是否成功解析；
- OCR 是否可用；
- 章节结构是否正确；
- 提取了哪些知识点；
- 哪些知识点需要审核；
- 是否可修改、合并或拆分；
- 检索结果是否来自正确资料；
- 引用能否返回原文位置。

### 7.2 CoursePilot

CoursePilot 通过接口使用：

- 课程知识点列表；
- 知识点与章节映射；
- 按知识点或章节检索；
- Context Package；
- Evidence；
- 教师审核内容写回。

### 7.3 开发与评测人员

开发人员需要：

- 查看构建阶段；
- 查看解析和 OCR 结果；
- 查看知识点抽取版本；
- 查看 Query Processing 过程；
- 切换检索配置；
- 运行消融评测；
- 比较实验结果；
- 定位解析、知识点、Query、检索和引用错误。

---

## 8. 核心使用场景

### UC-01：上传课程资料并构建知识库

教师上传 PDF 或 DOCX，系统完成文件校验、原生解析或 OCR、结构恢复、Evidence、Chunk、知识点抽取、索引构建和发布。

### UC-02：检查解析与 OCR 结果

教师或开发人员查看：

- 章节树；
- 页码；
- 段落；
- 表格；
- OCR 页面和置信度；
- 页眉、页脚或噪声内容；
- 解析警告。

### UC-03：检查和维护知识点

教师查看系统抽取的知识点，对低置信度或错误结果进行：

- 修改名称；
- 修改说明；
- 增加或删除别名；
- 设置父知识点；
- 合并重复知识点；
- 拆分过宽知识点；
- 调整证据；
- 停用错误知识点；
- 标记为审核通过。

### UC-04：CoursePilot 获取知识点

CoursePilot 在生成教学设计、试卷或 PPT 前，获取：

- 课程知识点集合；
- 指定章节知识点；
- 父子层级；
- 知识点证据；
- 审核状态；
- 别名和相关章节。

### UC-05：按 Query 检索

CoursePilot 或测试人员提交 Query。CourseRAG 执行可配置的 Query Processing，并根据课程、文档、章节、知识点或来源等级进行召回与过滤。

### UC-06：构建 Agent 上下文

CourseRAG 对检索候选进行：

- 去重；
- 父级上下文扩展；
- 相邻段落补充；
- Token Budget 控制；
- 证据边界保护；
- 上下文排序。

### UC-07：核验引用

CoursePilot 根据 `evidence_id` 获取原文证据、章节、页码、OCR 标识和文档版本。

### UC-08：文档增量更新

教师替换或新增课程资料后，系统识别变化范围，只重新处理受影响 Section、Evidence、Chunk、知识点和索引。

### UC-09：教师写回内容积累与批量知识点更新

教师确认的题目、解析或教案片段先被立即持久化，并可进入轻量检索索引；知识点抽取和归并按批次触发，不因每一条写回内容单独运行。

### UC-10：运行基础引用 QA

教师、CoursePilot 或测试人员提交课程问题，系统检索证据、生成带引用回答；证据不足时返回明确拒答和已检索范围。

### UC-11：运行评测

开发人员选择语料版本、数据集和配置，运行解析、知识点、Query Processing、检索、QA 和引用评测。

---

## 9. 总体业务流程

### 9.1 文档构建流程

```text
上传 PDF / DOCX
    ↓
文件校验与注册
    ↓
原生文本可解析性检测
    ├─ 可解析 → 原生解析
    └─ 不可解析/低文本密度 → OCR
    ↓
结构恢复与规范化
    ↓
Evidence 生成
    ↓
层级 Chunk 构建
    ↓
知识点候选抽取
    ↓
名称规范化与跨片段归并
    ↓
知识点与 Chunk、Evidence 关联
    ↓
置信度和质量检查
    ↓
稀疏与稠密索引构建
    ↓
索引校验
    ↓
发布知识库版本
```

教师审核不是发布的强制前置步骤。

### 9.2 在线检索流程

```text
原始 Query
    ↓
标准化
    ↓
知识点名称/别名链接
    ↓
显式过滤条件解析
    ↓
查询扩展
    ↓
必要时多查询改写或二次检索
    ↓
稀疏 + 稠密召回
    ↓
结果融合
    ↓
Reranker
    ↓
Context Packing
    ↓
Evidence 返回
```

每个 Query Processing 步骤必须可独立关闭并记录运行结果。

---


### 9.3 基础引用 QA 流程

```text
Question
    ↓
Query Processing
    ↓
Retrieval / Rerank
    ↓
Context Packing
    ↓
Evidence Sufficiency Check
    ├─ 不足 → 拒答并返回检索说明
    └─ 充分 → 结构化回答生成
                 ↓
            Claim 分解与 Citation 绑定
                 ↓
            QA Response
```

QA 不维护独立的检索索引，不复制 Query Processing 或 Context Packing 逻辑。

## 10. 功能需求

### 10.1 课程知识库管理

#### FR-KB-001 创建课程知识库

系统应支持为每门课程创建独立知识库，并保存：

- `course_id`；
- 名称；
- 描述；
- 语言；
- 创建时间；
- 当前发布索引版本；
- 当前知识点版本；
- 当前状态。

#### FR-KB-002 查看知识库状态

状态至少包括：

- `empty`
- `building`
- `ready`
- `ready_with_warnings`
- `failed`
- `archived`

`needs_review` 不作为知识库主状态，而作为待审核知识点数量和告警信息。

#### FR-KB-003 版本管理

每次正式构建应产生明确的：

- 文档版本；
- OCR 配置版本；
- 解析配置版本；
- Evidence 版本；
- Chunk 配置版本；
- 知识点抽取版本；
- Embedding 版本；
- Query Processing 配置版本；
- 检索配置版本；
- 索引版本。

---

### 10.2 文件上传与校验

#### FR-DOC-001 支持 PDF 和 DOCX

系统仅接受 PDF 和 DOCX 对应 MIME 类型。

#### FR-DOC-002 文件校验

系统应检查：

- 文件扩展名和 MIME 类型；
- 文件大小；
- 文件是否损坏；
- 文件是否加密；
- 文件是否为空；
- PDF 文本密度和可解析性；
- DOCX 是否可正常打开；
- 文件 Hash 是否与已有版本重复。

#### FR-DOC-003 OCR 路由

PDF 页面满足以下任一条件时，应进入 OCR 候选：

- 无可提取文本；
- 文本字符数低于阈值；
- 提取文本乱码率过高；
- 页面主要由图像构成；
- 用户手动要求 OCR。

#### FR-DOC-004 重复文件处理

相同 Hash 文件应优先复用已有解析、OCR 和知识点结果。

#### FR-DOC-005 文件替换

替换已有文档时必须保留旧版本，并根据变化范围触发增量更新。

---

### 10.3 文档解析、OCR 与结构恢复

#### FR-PARSE-001 统一文档中间表示

PDF 原生解析、PDF OCR 和 DOCX 应转换为统一表示，包括：

- Document；
- DocumentVersion；
- Page；
- Section；
- Block；
- Paragraph；
- List；
- Table；
- Figure Placeholder；
- Formula Placeholder；
- Source Span。

#### FR-PARSE-002 章节层级

系统应尽可能恢复文档标题、一级至三级标题、标题编号和章节路径。

#### FR-PARSE-003 原始顺序

系统应保留内容在原文中的阅读顺序，避免多栏 PDF、文本框或页眉页脚导致错序。

#### FR-PARSE-004 跨页段落

系统应识别并合并被分页打断的段落，同时保留页码范围和原始 Block。

#### FR-PARSE-005 页眉页脚和噪声

噪声应被标记而不是不可逆删除，并能够在预览中查看。

#### FR-PARSE-006 表格

系统应尽可能保留表格所在章节、行列结构、单元格文本、表题、页码和原文位置。

#### FR-PARSE-007 OCR 基本能力

OCR 结果至少保存：

- `page_id`；
- 识别文本；
- 文本块坐标；
- 置信度；
- OCR Engine 和版本；
- 是否经过后处理；
- 页面图像 Hash；
- 解析警告。

#### FR-PARSE-008 混合页面处理

同一 PDF 可以同时包含原生文本页和 OCR 页。系统应按页选择来源，不应强制整份 PDF 全量 OCR。

#### FR-PARSE-009 解析预览

用户应能够查看章节树、正文、表格、OCR 标识、OCR 置信度、噪声和警告。

#### FR-PARSE-010 解析质量报告

报告至少包含：

- 页数；
- 原生解析页数；
- OCR 页数；
- 标题数量；
- 段落数量；
- 表格数量；
- 噪声块数量；
- 低置信度 OCR 页数；
- 无法处理页数；
- 是否建议人工检查。

#### FR-PARSE-011 DOCX 分页快照

DOCX 必须在固定 Renderer Profile 下生成分页快照，并保存：

- 物理页序号；
- 文档显示页码；
- Section 内页序号；
- Renderer Provider 和版本；
- Render Profile Hash；
- 渲染 PDF Hash；
- DOCX Block 与渲染页的对齐置信度；
- 字体缺失或版式异常警告。

系统不得只依赖 `python-docx` 猜测自动分页。引用应优先展示文档显示页码，并保留物理页和结构位置作为稳定定位。

---

### 10.4 Evidence 与 Chunk

#### FR-CHUNK-001 稳定 Evidence

Evidence 至少记录：

- 文档 ID 和版本；
- 章节路径；
- 页码范围；
- Block 范围；
- 字符范围；
- 页面坐标；
- 原文文本；
- 内容 Hash；
- 内容来源：`native_text` 或 `ocr_derived`；
- OCR 置信度（如适用）。

#### FR-CHUNK-002 层级 Chunk

系统应支持 Parent Chunk、Child Chunk，并维护 Chunk 与 Evidence、知识点的多对多关系。

#### FR-CHUNK-003 语义边界

Chunk 应优先尊重章节、小节、段落、列表、表格、句子、定义、示例和步骤边界。

#### FR-CHUNK-004 Chunk 元信息

每个 Chunk 至少包含：

- `chunk_id`
- `parent_chunk_id`
- `document_id`
- `document_version`
- `section_id`
- `section_path`
- 页码范围；
- Evidence IDs；
- 内容类型；
- Knowledge Point IDs；
- Token 数；
- Chunk 配置版本。

---

### 10.5 知识点抽取与知识点库

#### FR-KP-001 强制执行知识点抽取

正式文档构建必须执行知识点抽取。整体抽取失败时不得将知识库标记为正常 `ready`。

#### FR-KP-002 离线抽取与复用

普通检索、Context 构建和 CoursePilot 生成任务不得重复执行完整知识点抽取。

#### FR-KP-003 知识点对象

```json
{
  "knowledge_point_id": "kp_001",
  "canonical_name": "启发式搜索",
  "aliases": ["有信息搜索"],
  "summary": "利用启发信息指导搜索方向的方法。",
  "parent_knowledge_point_id": "kp_search",
  "course_id": "course_001",
  "section_ids": ["section_034"],
  "confidence": 0.91,
  "origin": "auto_extracted",
  "review_status": "unreviewed",
  "extractor_version": "kp_extract_v2",
  "document_versions": {
    "doc_001": "v3"
  }
}
```

知识点对象本身不直接嵌入全部 Evidence 和 Chunk，而通过映射对象维护关系。

#### FR-KP-004 知识点粒度

知识点应尽量具有可讲授性、可解释性、可测量性、明确证据和合理粒度。

#### FR-KP-005 候选抽取单位

知识点应基于语义完整且大小合适的片段抽取。具体单位可以是 Section、Parent Chunk 或二者组合，但不得机械地对每个小 Chunk 单独发起一次抽取。

#### FR-KP-006 同义项归并

系统应归并不同片段中的同一知识点，并保留标准名称、别名、全部证据和所在章节。

#### FR-KP-007 可选父子层级

知识点可以具有一个可选父知识点。MVP 不强制自动生成多种语义关系边。

#### FR-KP-008 内容角色

`KnowledgePointEvidenceLink` 和 `KnowledgePointChunkLink` 应支持：

- `definition`
- `principle`
- `procedure`
- `example`
- `comparison`
- `formula`
- `application`
- `limitation`
- `exercise`
- `summary`

#### FR-KP-009 自动发布阈值

- 阈值可配置；
- 默认值为 `0.75`；
- 达标且通过质量规则的结果自动进入可用知识点版本；
- 未达标或存在冲突的结果进入 `needs_review`；
- 低置信度结果默认不参与强过滤，但可以作为弱元信息使用。

#### FR-KP-010 审核状态

知识点审核状态使用：

- `unreviewed`
- `needs_review`
- `approved`
- `rejected`
- `deprecated`

知识点来源使用独立字段：

- `auto_extracted`
- `manual_created`
- `imported`

不再使用 `teacher_verified` 作为知识点审核状态。

#### FR-KP-011 简化审核界面

MVP 审核界面应支持：

- 按章节浏览；
- 搜索和过滤；
- 查看名称、摘要、置信度、证据和 Chunk；
- 修改名称、摘要和别名；
- 设置父知识点；
- 合并、拆分、通过、拒绝和停用；
- 批量通过高置信度结果；
- 清晰展示待审核原因。

不要求复杂知识图谱可视化。

#### FR-KP-012 版本与缓存

知识点结果应关联文档、解析、Evidence、Prompt、模型和抽取配置版本，仅在相关输入变化时重新抽取。

#### FR-KP-013 文档增量更新

文档变化的默认最小重处理粒度为 `Section`。

系统应：

- 基于 Section 或 Block Hash 检测变化；
- 重新生成变化 Section 及边界相邻 Section 的 Evidence 和 Chunk；
- 仅重抽受影响 Section 的知识点候选；
- 将新候选与课程级知识点库做局部归并；
- 保留未受影响知识点及审核记录。

若 Parser、Chunker 或 Extractor 的版本变化影响全局语义，则允许扩大到文档级重建。

#### FR-KP-014 CoursePilot 查询接口

CoursePilot 至少能够：

- 获取全课程知识点；
- 按章节获取知识点；
- 获取父子层级；
- 按名称或别名搜索；
- 获取 Evidence；
- 获取关联 Chunk；
- 获取置信度和审核状态；
- 获取知识点版本。

---

### 10.6 Query Processing 与检索

#### FR-QP-001 Query 标准化

MVP 必须支持：

- 去除异常空白；
- 全角半角归一；
- 英文大小写归一；
- 标点规范化；
- 保留原始 Query；
- 避免删除具有教学意义的短词和符号。

#### FR-QP-002 知识点链接

系统应根据知识点标准名称和别名识别 Query 中显式或高置信度知识点，并返回匹配结果。

#### FR-QP-003 过滤条件解析

系统应识别明确的章节、文档、页码、知识点和来源等级要求，并转换为结构化过滤条件。

#### FR-QP-004 查询扩展

系统应使用以下受控来源扩展 Query：

- 知识点别名；
- 章节标题；
- 术语规范名称；
- 已审核同义表达。

扩展词必须可追踪，不能无限扩展。

#### FR-QP-005 轻量 Query Router

MVP 应至少区分：

- 精确事实或术语；
- 概念定义；
- 比较；
- 过程或步骤；
- 示例或应用；
- 跨章节综合。

Router 用于调整 Dense/Sparse 权重、候选数和内容角色偏好，不直接决定最终答案。

#### FR-QP-006 多查询改写

对于表达冗长、歧义明显或首次召回不足的 Query，可通过环境配置的 API 模型生成有限数量改写。

默认约束：

- 保留原 Query；
- 改写数量可配置；
- 默认不超过 3 个；
- 可关闭；
- 改写失败时回退原 Query；
- 不得替换用户显式过滤条件。

#### FR-QP-007 低召回二次检索

当首次检索无结果或低于配置阈值时，可以执行一次受限的扩展或改写后重试，并记录触发原因。

#### FR-QP-008 可配置与可消融

Query Processing 配置至少包含：

```json
{
  "normalize": true,
  "link_knowledge_points": true,
  "extract_filters": true,
  "expand_aliases": true,
  "route_query": true,
  "multi_query_rewrite": false,
  "low_recall_retry": true
}
```

接口响应和评测记录必须保存各步骤是否启用、输入、输出和耗时。

#### FR-RET-001 检索模式

MVP 支持：

- 稠密检索；
- 稀疏检索；
- 混合检索。

#### FR-RET-002 知识点增强检索

系统应支持知识点名称、别名、摘要、内容角色和审核状态参与召回、过滤或排序。

#### FR-RET-003 重排序

系统应保存原始召回排名、各路分数、融合分数、Rerank 分数和最终排名。

#### FR-RET-004 默认 Provider

Embedding 使用环境变量配置的 API Provider。Reranker 使用独立 Provider 配置，可选择专用 Rerank API、本地 Cross-Encoder 或显式关闭；若配置不可用，应按运行 Profile 返回明确错误或带 Warning 回退 Fusion Rank，不得静默切换未知模型。

#### FR-RET-005 结果可解释性

每个结果至少返回：

- 文档；
- 章节；
- 页码；
- Evidence；
- 关联知识点；
- 内容角色；
- 来源等级；
- Query Processing 记录；
- 检索配置版本；
- 索引版本。

---

### 10.7 Context 构建

#### FR-CTX-001 独立 Context 服务

Context 构建必须与基础检索分开，以便独立观测和评测。

#### FR-CTX-002 Context 处理

至少支持：

- 候选去重；
- Parent Chunk 扩展；
- 相邻段落补充；
- Evidence 边界保护；
- Token Budget；
- 最大 Context 数量；
- 排序；
- 截断记录。

#### FR-CTX-003 Purpose

至少支持：

- `lesson_generation`
- `exam_generation`
- `ppt_generation`
- `knowledge_point_review`

`question_answering` 在下一阶段启用。

#### FR-CTX-004 Packing Report

Context Package 应返回候选数、选择数、去重数、预算丢弃数、Token 数、截断状态和 Evidence Map。

---

### 10.8 引用与证据

#### FR-CITE-001 稳定引用

CourseRAG 对外返回稳定的 `evidence_id`，不要求 CoursePilot 直接引用 Chunk ID。

#### FR-CITE-002 引用读取

通过 `evidence_id` 能够获取原文、文档版本、章节、页码、页面坐标、Source Span、内容 Hash 和 OCR 标识。

#### FR-CITE-003 引用失效检测

文档更新后，应识别引用仍有效、已迁移、需复核或已失效。

#### FR-CITE-004 引用完整性

所有正式 Context Item 必须包含至少一个有效 Evidence。

#### FR-CITE-005 原文预览

教师可从引用跳转至原文片段、所在页和相邻上下文。

---

### 10.9 教师审核内容写回

#### FR-WB-001 写回内容与知识点审核分离

知识点审核和 CoursePilot 生成内容写回是两条不同流程：

- 知识点审核修改 `KnowledgePoint.review_status`；
- 生成内容写回创建 `VerifiedContentRecord`；
- 二者使用不同接口、数据表和状态字段。

#### FR-WB-002 MVP 写回类型白名单

MVP 仅支持：

- `verified_question`
- `verified_answer_explanation`
- `verified_lesson_fragment`

暂不支持整份教案、整套试卷、整份 PPT 或任意自由文本整体写回。

#### FR-WB-003 来源等级

经教师确认的写回内容使用：

- `source_tier = teacher_verified`

该字段表示内容来源可信等级，不表示知识点审核状态。

#### FR-WB-004 写回要求

每条写回内容必须记录：

- 内容类型；
- 内容 Hash；
- 审批人；
- 审批时间；
- CoursePilot Task ID；
- Approval Record ID；
- 原始 Evidence IDs；
- 关联知识点 IDs；
- 幂等键；
- 当前状态。

#### FR-WB-005 即时存储与批量富化

教师批准后：

1. 内容立即持久化；
2. 可立即进入独立的 `teacher_verified` 轻量检索索引；
3. 不立即触发完整知识点抽取；
4. 进入待富化批次；
5. 达到阈值后统一执行知识点抽取、关联和归并。

默认批量触发条件满足任一即可：

- 累计 10 条；
- 累计 3000 Token；
- 首条待处理内容已等待 24 小时；
- 用户手动触发。

所有阈值可配置。

#### FR-WB-006 撤销

写回内容支持撤销，并同步从正式检索索引中停用，但保留审计记录。

---

### 10.10 构建任务与状态

#### FR-JOB-001 异步构建

解析、OCR、知识点抽取和索引构建属于长任务，应返回 `job_id`。

#### FR-JOB-002 构建阶段

至少显示：

- `validating_file`
- `detecting_parse_mode`
- `parsing`
- `ocr`
- `normalizing`
- `building_evidence`
- `chunking`
- `extracting_knowledge_points`
- `consolidating_knowledge_points`
- `embedding`
- `building_sparse_index`
- `validating_index`
- `publishing`

#### FR-JOB-003 进度与错误

用户应能看到当前阶段、完成比例、已处理数量、总数量、警告、可重试错误和失败原因。

#### FR-JOB-004 阶段恢复

系统应从最近合理阶段恢复，避免重复 OCR、知识点抽取和 Embedding 等高成本步骤。

---

### 10.11 评测与实验

#### FR-EVAL-001 固定版本

每次评测必须记录：

- 文档版本；
- OCR 配置；
- Parser；
- Evidence；
- Chunk；
- 知识点；
- Query Processing；
- Embedding；
- Reranker；
- 检索配置；
- 数据集版本。

#### FR-EVAL-002 解析与 OCR 评测

支持评估：

- 章节结构；
- 正文顺序；
- 页码映射；
- 跨页段落；
- 表格；
- 噪声过滤；
- OCR 可用页比例；
- OCR 抽样字符准确性；
- Evidence 定位。

#### FR-EVAL-003 知识点评测

支持评估：

- 候选准确率；
- 重要知识点召回率；
- 重复率；
- 粒度合理性；
- Evidence 绑定；
- Chunk 关联；
- 同义项归并；
- 父子层级合理性；
- 阈值分层表现。

#### FR-EVAL-004 Query Processing 消融

至少比较：

- 原始 Query；
- + 标准化；
- + 知识点链接和别名扩展；
- + Router；
- + 多查询改写；
- + 低召回重试。

#### FR-EVAL-005 检索评测

至少支持：

- Recall@5/10；
- Hit@5/10；
- MRR@10；
- nDCG@10；
- Precision@5；
- 过滤准确性。

#### FR-EVAL-006 引用评测

至少支持：

- Evidence 命中率；
- 引用可解析率；
- 原文一致性；
- 失效引用比例；
- 页码准确性。

#### FR-EVAL-007 基础 QA 评测

至少支持：

- 短答案 Exact Match / Token F1；
- Gold Claim Coverage；
- Correct Claim Precision；
- Unsupported Claim Rate；
- Contradictory Claim Rate；
- Answerability Precision / Recall / F1；
- False Answer Rate；
- False Abstention Rate；
- Citation Claim Support Rate；
- Citation Precision / Recall。

#### FR-EVAL-008 运行指标

记录全量和增量构建时间、各阶段耗时、模型调用数、Token、成本、缓存命中率、Query Processing 延迟、检索延迟、Rerank 延迟和 QA 延迟。

---

### 10.12 基础引用问答

#### FR-QA-001 统一检索链路

QA 必须复用 CourseRAG 的 Query Processing、Retrieval、Rerank 和 Context Packing，不得维护隐藏的第二套检索流程。

#### FR-QA-002 回答范围

回答只能使用当前 Context Package 中的 Evidence，不调用开放网络，也不使用未进入 Context 的模型记忆补充课程事实。

#### FR-QA-003 结构化回答

QA Response 至少包含：

- `answer_status`；
- `answer`；
- 原子化 Claims；
- 每个 Claim 的 Evidence IDs；
- Citations；
- Context Package ID；
- Retrieval Trace ID；
- 模型和 Prompt 版本；
- Token、延迟和成本信息。

#### FR-QA-004 引用要求

每个事实性 Claim 至少绑定一个有效 Evidence。无引用的事实性 Claim 应被校验器拦截、修复或导致回答降级。

#### FR-QA-005 拒答

证据不足、问题超出资料范围或检索结果低于阈值时，应返回明确状态：

- `abstained_insufficient_evidence`
- `abstained_out_of_scope`

拒答不得伪造答案，也不得返回看似确定但无证据支持的内容。

#### FR-QA-006 答案风格

MVP 支持简洁、解释性两种基本回答风格；回答长度、最大 Token 和引用样式可配置。

#### FR-QA-007 失败隔离

生成模型不可用或 QA 节点失败时，基础 Search、Context 和 Evidence API 仍应可用。

#### FR-QA-008 可观测与可评测

系统应保存问题、Query Processing、检索结果、Context、Prompt、模型输出、Claims、引用、拒答原因、耗时和成本。

---

## 11. 核心数据对象

### 11.1 CourseKnowledgeBase

表示一门课程知识库及其当前发布的文档、知识点和索引版本。

### 11.2 SourceDocument

表示教师上传的逻辑文档。

### 11.3 DocumentVersion

表示某个文件版本，包含 Hash、存储位置、MIME、创建时间和版本状态。

### 11.4 ParsedDocument

表示原生解析或 OCR 后的统一文档结果及解析配置。

### 11.5 DocumentSection

表示章节和层级结构，包含父 Section、章节路径和顺序。

### 11.6 DocumentBlock

表示标题、段落、列表、表格占位、公式占位等基础结构单元。

### 11.7 TableRecord

表示结构化表格及其单元格、标题和位置。

### 11.8 OCRPageResult

表示页面 OCR 文本、坐标、置信度、引擎和警告。

### 11.9 EvidenceRecord

表示稳定、可引用的原文范围。

### 11.10 ChunkRecord

表示供检索使用的 Parent 或 Child Chunk。

### 11.11 ChunkEvidenceLink

表示 Chunk 与 Evidence 的多对多映射，并保存 Evidence 在 Chunk 中的顺序和覆盖范围。

### 11.12 KnowledgePoint

表示课程知识点、别名、摘要、可选父知识点、置信度、来源和审核状态。

### 11.13 KnowledgePointEvidenceLink

表示知识点与 Evidence 的多对多关系，保存：

- 内容角色；
- 关联强度；
- 是否主要证据；
- 来源抽取批次；
- 审核状态。

### 11.14 KnowledgePointChunkLink

表示知识点与 Chunk 的多对多关系，保存：

- 内容角色；
- 关联强度；
- 是否用于过滤或仅用于排序。

### 11.15 KnowledgePointReviewAction

表示教师对知识点执行的通过、修改、合并、拆分、拒绝或停用操作。

### 11.16 QueryProcessingRun

表示一次 Query Processing 的原始 Query、各步骤开关、中间 Query、知识点链接、过滤条件、耗时和错误。

### 11.17 RetrievalRun

表示一次检索调用及其配置、候选、分数、排名和索引版本。

### 11.18 RetrievalHitRecord

表示单条检索结果在 Dense、Sparse、Fusion 和 Rerank 阶段的分数与排名。

### 11.19 ContextPackageRecord

表示一次 Context Packing 结果和预算报告。

### 11.20 ContextItemEvidenceLink

表示 Context Item 与 Evidence 的映射及展示顺序。

### 11.21 VerifiedContentRecord

表示经教师确认并写回的题目、答案解析或教案片段。

### 11.22 VerifiedContentEvidenceLink

表示写回内容与原始 Evidence 的多对多关系。

### 11.23 VerifiedContentKnowledgePointLink

表示写回内容与知识点的多对多关系。

### 11.24 EnrichmentBatch

表示等待批量知识点抽取和归并的教师写回内容集合。

### 11.25 IndexVersion

表示可发布、可回滚的稠密索引、稀疏索引和元数据版本。

### 11.26 BuildJob

表示知识库构建任务。

### 11.27 BuildStageRun

表示单个构建阶段的输入、输出、耗时、缓存、重试和状态。

### 11.28 EvaluationDataset

表示正式评测数据集及版本。

### 11.29 EvaluationCase

表示查询、Gold Evidence、类型、难度和审核状态。

### 11.30 EvaluationRun

表示一次可复现评测运行及其配置和结果。


### 11.31 QARequestRecord

表示一次基础 QA 请求及其过滤条件、检索配置和回答配置。

### 11.32 QARun

表示一次完整 QA 运行，关联 QueryProcessingRun、RetrievalRun、ContextPackageRecord、模型、Prompt、回答状态、延迟和成本。

### 11.33 AnswerClaimRecord

表示系统回答中的原子事实性 Claim，保存 Claim 文本、顺序、类型和校验状态。

### 11.34 AnswerClaimEvidenceLink

表示 Answer Claim 与 Evidence 的多对多映射，保存引用顺序、是否主要证据和支持状态。

### 11.35 QAReviewRecord

表示人工 QA 评测结果，包括 Claim 正确性、Gold Claim 覆盖、拒答正确性和引用支持情况。

### 11.36 关键关系


```text
SourceDocument 1 ── N DocumentVersion
DocumentVersion 1 ── 1 ParsedDocument
ParsedDocument 1 ── N DocumentSection
DocumentSection 1 ── N DocumentBlock
Page 1 ── 0..1 OCRPageResult

EvidenceRecord N ── N ChunkRecord
KnowledgePoint N ── N EvidenceRecord
KnowledgePoint N ── N ChunkRecord
KnowledgePoint 0..1 ── N KnowledgePoint

VerifiedContentRecord N ── N EvidenceRecord
VerifiedContentRecord N ── N KnowledgePoint
EnrichmentBatch 1 ── N VerifiedContentRecord

RetrievalRun 1 ── N RetrievalHitRecord
ContextPackageRecord N ── N EvidenceRecord
QARun 1 ── 1 QueryProcessingRun
QARun 1 ── 1 RetrievalRun
QARun 1 ── 1 ContextPackageRecord
QARun 1 ── N AnswerClaimRecord
AnswerClaimRecord N ── N EvidenceRecord
```

所有多对多关系必须通过显式映射对象保存，不应只在 JSON 字段中存放无法约束的 ID 列表。

---

## 12. 知识点生命周期

```text
语义完整片段
    ↓
候选知识点抽取
    ↓
名称规范化和别名识别
    ↓
跨 Evidence 聚合
    ↓
重复项归并
    ↓
可选父子层级
    ↓
Evidence / Chunk 关系生成
    ↓
置信度和质量规则
    ├─ 达标 → 自动发布，unreviewed
    └─ 不达标 → needs_review
    ↓
可选教师审核
    ↓
approved / rejected / deprecated
```

### 12.1 重新抽取触发条件

触发：

- 新文档首次构建；
- 文档内容变化；
- 解析或 Evidence 变化；
- 抽取 Prompt、模型或配置升级并选择重建；
- 用户主动重新抽取；
- 教师写回内容达到富化批次阈值。

不触发：

- 普通检索；
- 修改 Top-K；
- 修改 Reranker；
- 创建 CoursePilot 任务；
- 切换生成模板；
- 单条教师写回刚刚产生。

### 12.2 文档增量更新默认策略

“最小粒度”指发生变化后，系统最小重新处理到哪一级，而不是整个课程全量重建。

默认规则：

| 变化 | 默认重处理范围 |
|---|---|
| 仅文档业务名称变化 | 只更新元数据 |
| Section 内容变化 | 当前 Section + 边界相邻 Section |
| 表格或段落局部变化 | 所属 Section |
| Parser/OCR 配置重大变化 | 当前文档 |
| Chunker 配置变化 | 当前文档的 Chunk 与索引 |
| 知识点抽取模型/Prompt 变化 | 当前文档或明确指定 Section |
| Embedding 模型变化 | 全部受影响 Chunk 的向量索引 |
| Reranker 变化 | 无需重建文档和索引 |
| 教师写回 | 立即保存；批量知识点富化 |

---

## 13. CoursePilot 集成要求

### 13.1 教案

- 获取章节知识点和层级；
- 按知识点检索定义、原理、示例和应用；
- 检查教学目标和活动覆盖。

### 13.2 试卷

- 按知识点分配题量和分值；
- 检索适合出题的内容角色；
- 计算覆盖度；
- 检查答案证据。

### 13.3 PPT 初稿

- 按章节和知识点生成结构；
- 为每页选择证据；
- 生成引用和讲者备注；
- 检查重复和遗漏。

### 13.4 审核写回

- 仅写回白名单类型；
- 记录 Evidence 和知识点；
- 标记 `source_tier=teacher_verified`；
- 进入独立 Verified Content 流程；
- 不修改知识点审核状态。

---

## 14. 非功能需求

### NFR-001 可追溯性

任何 OCR、Chunk、知识点、Context 和引用都可追溯至原文和处理版本。

### NFR-002 可重复性

评测必须记录所有影响结果的模型和配置。

### NFR-003 可恢复性

高成本阶段失败后应从最近合理阶段恢复。

### NFR-004 幂等性

文档注册、构建、发布、写回和撤销支持幂等。

### NFR-005 可观测性

记录输入规模、输出规模、耗时、模型调用、Token、缓存、重试、警告和错误。

### NFR-006 可替换性

OCR、Embedding、Reranker 和模型 Provider 可配置替换。

### NFR-007 安全性

不得在日志或 Trace 中保存 Secret。

### NFR-008 性能

知识点抽取和 OCR 允许较高的一次性构建时间，但在线 Query Processing、检索、Context 构建和基础 QA 必须可用。具体目标值在基线后确定。

---

## 15. MVP 范围

### 15.1 MVP 必须包含

- PDF、DOCX 上传；
- 文件校验；
- 扫描 PDF 检测；
- 按页 OCR；
- 原生文本与 OCR 混合解析；
- 统一文档中间表示；
- 章节、段落和基础表格结构恢复；
- 页眉页脚噪声处理；
- 稳定 Evidence；
- 层级 Chunk；
- 强制知识点抽取；
- 知识点持久化和版本化；
- 可选知识点父子层级；
- KnowledgePoint-Evidence 和 KnowledgePoint-Chunk 显式映射；
- 默认 0.75 可配置发布阈值；
- 简化知识点审核界面；
- Query 标准化；
- 知识点链接；
- 过滤条件解析；
- 别名扩展；
- 轻量 Router；
- 可选多查询改写；
- 低召回二次检索；
- 稠密、稀疏和混合检索；
- API Embedding；
- API Reranker；
- Context 构建；
- 引用读取；
- 基础引用 QA；
- Claim-Evidence 映射；
- 证据不足拒答；
- QA 运行追踪；
- 白名单教师写回；
- 批量写回富化；
- 构建任务状态；
- 增量更新；
- 版本记录；
- 独立评测入口；
- CoursePilot 适配接口。

### 15.2 下一阶段

- 多轮 QA；
- 对话记忆；
- 更复杂的答案规划和长答案综合；
- MCP Server；
- 更复杂的 Query Router；
- 更完善的 OCR 版面恢复；
- 图片语义理解；
- 复杂公式识别；
- 多用户权限体系；
- 完整可视化评测平台。

---

## 16. 产品验收条件

### 16.1 文件、OCR 与解析

- 系统只接受 PDF 和 DOCX；
- 原生文本 PDF、扫描 PDF 和 DOCX 测试文件均可进入正确处理流程；
- DOCX 能生成可复现分页快照，Evidence 同时具有物理页、显示页码和结构位置；
- 扫描页能够得到基础 OCR 文本；
- OCR 页保留页码、坐标、置信度和来源标记；
- 解析结果可查看章节、正文、OCR 和警告；
- 原文位置可追溯；
- 单页 OCR 失败不导致整份文档无条件失败。

### 16.2 Evidence 与 Chunk

- Evidence 与 Chunk 分离；
- Chunk-Evidence 使用显式映射对象；
- 修改 Chunker 不直接破坏 Evidence；
- Chunk 可返回关联知识点和内容角色。

### 16.3 知识点

- 每次正常文档构建执行知识点抽取；
- 普通检索和 Agent 任务不重复完整抽取；
- 知识点结果持久化并版本化；
- KnowledgePoint-Evidence 与 KnowledgePoint-Chunk 关系完整；
- 默认阈值为 0.75 且可配置；
- 达标知识点无需教师审核即可发布；
- 待审核知识点不阻塞知识库发布；
- 教师可执行通过、修改、合并、拆分、拒绝和停用；
- 知识点支持可选父子层级；
- 不要求生成完整知识图谱；
- 文档局部变化可按 Section 重处理。

### 16.4 Query Processing 与检索

- Query Processing 各步骤可独立启用或关闭；
- 返回各步骤实际输入、输出和耗时；
- 原始 Query 始终保留；
- 支持标准化、知识点链接、过滤解析、别名扩展、Router、可选改写和低召回重试；
- 支持稠密、稀疏和混合检索；
- 支持章节、知识点和来源等级过滤；
- 返回各阶段分数和排名；
- Embedding 与独立 Reranker Provider 从环境配置读取；
- 可对 Query Processing 进行消融评测；
- Gold Evidence 不依赖当前检索结果生成。

### 16.5 引用

- 所有正式 Context Item 均包含有效 Evidence；
- Evidence 可定位原文、章节、页码、坐标和 OCR 来源；
- 文档更新后能够识别引用失效或迁移。

### 16.6 教师写回

- 知识点审核状态与写回来源等级完全分离；
- MVP 只允许题目、答案解析和教案片段写回；
- 写回内容保存审批、Evidence、知识点和幂等信息；
- 写回内容立即保存，但知识点抽取按批次触发；
- 写回可撤销；
- 整份教案、整套试卷和整份 PPT 不进入 MVP 自动写回。

### 16.7 CoursePilot 集成

- CoursePilot 可获取知识点和父子层级；
- 可按知识点检索；
- 可获取 Context Package；
- 可读取 Evidence；
- 可写回白名单内容；
- CoursePilot 不直接依赖 CourseRAG 内部向量库或 ORM。

---


### 16.8 基础引用 QA

- QA 复用统一检索和 Context 链路；
- 回答能够返回原子 Claims 和 Evidence 引用；
- 每个事实性 Claim 至少有一个有效 Evidence；
- 可回答问题能够生成基于资料的回答；
- 不可回答问题能够明确拒答；
- QA 失败不会导致基础 Search API 不可用；
- QA Run 保存模型、Prompt、检索、Context、Token、延迟和成本；
- 能使用人工 Gold Claims 和 Gold Evidence 独立评测。

## 17. 产品成功指标

### 17.1 解析与 OCR

- 文档构建成功率；
- 章节识别准确率；
- 正文顺序准确率；
- 页码映射准确率；
- 表格可用率；
- OCR 可用页比例；
- OCR 抽样字符准确率；
- 低置信度 OCR 页比例；
- Evidence 定位准确率。

### 17.2 知识点

- 候选准确率；
- 重要知识点召回率；
- 重复率；
- 粒度合理率；
- Evidence 绑定准确率；
- Chunk 关联准确率；
- 同义项归并准确率；
- 父子层级合理率；
- 教师修改率；
- 低置信度比例；
- 不同阈值下的 Precision/Recall。

### 17.3 Query Processing 与检索

- 各步骤启用前后的 Recall@K、MRR 和 nDCG；
- Knowledge Point Linking 准确率；
- Filter Parsing 准确率；
- Query Rewrite 有效率；
- 低召回重试改善率；
- Recall@5/10；
- Hit@5/10；
- MRR@10；
- nDCG@10；
- Precision@5。

### 17.4 引用

- 引用可解析率；
- Evidence 命中率；
- 页码和坐标准确率；
- 原文一致性；
- 失效引用率。

### 17.5 基础引用 QA

- Answer Exact Match / Token F1（适用于短答案子集）；
- Gold Claim Coverage；
- Correct Claim Precision；
- Unsupported Claim Rate；
- Answerability Precision / Recall / F1；
- Citation Claim Support Rate；
- Citation Precision / Recall；
- 拒答准确率；
- QA P50/P95；
- 每次回答 Token 和成本。

### 17.6 工程

- 全量构建时间；
- 增量构建时间；
- OCR 耗时；
- 知识点抽取耗时；
- 模型调用数量；
- Token 和成本；
- 缓存命中率；
- Query Processing P50/P95；
- 检索 P50/P95；
- Rerank P50/P95；
- 构建失败恢复率。

---

## 18. 后续技术方案需确定的事项

1. OCR 引擎组合和降级链；
2. OCR 触发阈值；
3. PDF 复杂表格支持边界；
4. 知识点抽取的默认语义单元；
5. 知识点归并算法；
6. 0.75 阈值如何校准；
7. Query Router 的规则和模型分工；
8. 多查询改写默认是否开启；
9. API Embedding 和 Reranker 的具体配置；
10. Section Hash 和边界相邻 Section 的实现；
11. 教师写回轻量索引与主索引的合并策略；
12. QA Evidence Sufficiency 阈值、固定 Prompt 和生成模型配置；
13. Claim 分解和引用绑定的实现方式；
14. 拒答阈值的 Dev 校准方法。

---

## 19. 当前默认方案

- 仅支持 PDF 和 DOCX；
- OCR 纳入 MVP；
- PDF 按页判断是否需要 OCR；
- OCR 只承诺基本内容识别；
- 知识点抽取是强制离线构建阶段；
- 知识点结果持久化并版本化；
- 知识点与 Evidence、Chunk 使用显式映射对象；
- 支持可选父子层级；
- 不抽取完整先修、包含和相关关系图；
- 自动发布阈值默认 0.75，可配置；
- 知识点审核不是发布强制门槛；
- 知识点审核状态使用 `approved` 等值；
- `teacher_verified` 只用于教师写回内容的来源等级；
- 写回类型限定为题目、答案解析和教案片段；
- 写回立即保存，知识点富化批量执行；
- Query Processing 必须进入 MVP；
- Query Processing 全部可配置、可追踪、可消融；
- Embedding 使用 API；Reranker 默认使用独立多语言专用 Rerank API，也可配置本地 Cross-Encoder；
- MVP 完成检索、Context、引用和基础 QA；
- QA 复用统一检索链路并支持 Claim-Evidence 引用与拒答；
- 文档增量更新默认以 Section 为最小重处理粒度；
- 当前不使用 LLM-as-a-Judge。
