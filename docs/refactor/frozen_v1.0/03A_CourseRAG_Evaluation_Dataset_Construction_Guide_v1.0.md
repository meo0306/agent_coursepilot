# CourseRAG 评测数据集构造指南

**文档版本：** v1.0  
**文档状态：** 冻结执行版  
**冻结日期：** 2026-07-22
**配套文档：** `03_CourseRAG_Evaluation_Dataset_and_Baseline_v1.0.md`

---

## 1. 你最终需要构造哪些数据集

你不需要为每一个指标重新制作一套互不相关的数据。推荐构造 8 组相互复用的数据资产。

| 编号 | 数据集 | 正式建议规模 | 主要评测对象 | 是否可用 GPT 生成候选 |
|---|---|---:|---|---|
| DS0 | Corpus Manifest | 6 份文档 | 语料版本与复现 | 否 |
| DS1 | Parsing & OCR Gold | 40 页解析、15 页 OCR、20 个 Section、10 张表 | Parser、OCR、结构 | 仅辅助，不建议主生成 |
| DS2 | Evidence & Chunk Gold | 约 80–120 个 Evidence / 语义单元 | Evidence、Chunk、Parent-Child | 可辅助抽取证据，必须人工核对 |
| DS3 | Knowledge Point Gold | 20–24 个 Section，约 80–120 个 KP | 知识点抽取、映射、阈值 | 是 |
| DS4 | Query Processing Unit Set | 60 条 | Normalize、Link、Filter、Router、Rewrite | 是，人工补边界案例 |
| DS5 | Retrieval + QA Gold | 100 条，Dev 60 / Test 40 | Retrieval、Context、QA、拒答、引用 | 是 |
| DS6 | Citation Migration Set | 7–10 个文档更新场景 | 引用有效、迁移、失效 | 否，人工设计 |
| DS7 | Incremental / Writeback Set | 8–12 个更新和写回场景 | 增量构建、复用、批量富化 | 否，人工设计 |
| DS8 | Performance Workload Set | 固定构建任务 + 100 Query 重放 | 耗时、吞吐、Token、成本 | 脚本生成 |

其中 DS5 是最重要的复用数据集，同一条 Query 同时包含：

- Query Processing Gold；
- Gold Knowledge Points；
- Gold Evidence Groups；
- Gold Answer Type；
- Gold Short Answers（适用时）；
- Gold Claims；
- Claim-Evidence 关系；
- Answerable / Unanswerable；
- Query 类型和难度。

---

## 2. 推荐构造顺序

```text
DS0 冻结语料
    ↓
DS1 解析 / OCR Gold
    ↓
DS2 Evidence / Chunk Gold
    ↓
DS3 Knowledge Point Gold
    ↓
DS4 Query Processing Unit Set
    ↓
DS5 Retrieval + QA Gold
    ↓
DS6 Citation Migration
    ↓
DS7 Incremental / Writeback
    ↓
DS8 Performance Workload
```

不能先让 Retriever 跑一遍再从结果中生成 DS2 或 DS5 Gold。

---

## 3. DS0：Corpus Manifest

### 3.1 需要准备什么

选择至少 6 份文件：

1. 主教材原生文本 PDF；
2. 课程大纲 DOCX；
3. 教学讲义 DOCX；
4. 扫描 PDF；
5. 原生文本和扫描页混合 PDF；
6. 结构压力文档。

### 3.2 构造流程

1. 确认文件可以合法用于个人项目测试；
2. 统一文件名和 `document_id`；
3. 计算 SHA-256；
4. 记录文件类型、页数、用途和版本；
5. 将正式版本设为只读；
6. 后续修改文件时创建新版本，不覆盖原文件。

### 3.3 输出

- `corpus_manifest.jsonl`
- `manifest.yaml`

---

## 4. DS1：Parsing & OCR Gold

### 4.1 采样方式

从 6 份文档中人工挑选，而不是完全随机：

- 普通正文页；
- 标题密集页；
- 跨页段落；
- 列表；
- 表格；
- 多栏页；
- 页眉页脚明显页；
- 纯扫描页；
- 混合页；
- OCR 困难页。

### 4.2 构造流程

1. 为每个页面建立 `page_gold`；
2. 标记是否需要 OCR、页面类型和阅读顺序；
3. 标出标题、正文、表格、噪声区域；
4. 对 15 个 OCR 页面人工转录规范化全文；
5. 对 20 个 Section 标题、层级、父节点和起止范围；
6. 对 10 张表记录行列和单元格文本；
7. 第二轮抽样复核页码和标题层级。

### 4.3 GPT 的作用

GPT 可以帮助：

- 根据人工转录文本识别疑似标题；
- 检查 JSON Schema；
- 发现可能漏标的列表或表格。

GPT 不适合替代：

- OCR Gold 转录；
- 页面坐标；
- 阅读顺序；
- 最终标题层级判断。

---

## 5. DS2：Evidence & Chunk Gold

### 5.1 数据来源

优先从 DS3 和 DS5 将使用的原文范围中建立 Evidence，这样一份 Evidence 可同时用于知识点、检索、QA 和引用。

### 5.2 构造流程

1. 选择能够完整表达定义、原理、步骤、比较、示例的原文范围；
2. 复制逐字 Evidence Text；
3. 记录文档、章节、页码和 Block 范围；
4. 计算规范化内容 Hash；
5. 标记语义单元类型；
6. 标记是否需要 Parent 或相邻段落才能完整理解；
7. 人工确认 Evidence 不过短也不过宽；
8. 生成稳定 `gold_evidence_id`。

### 5.3 注意

- Evidence 不等于 Chunk；
- 一个 Chunk 可以覆盖多个 Evidence；
- 一个 Evidence 也可能被不同 Chunker 版本映射到不同 Chunk；
- Gold 中不要保存当前系统 Chunk ID。

---

## 6. DS3：Knowledge Point Gold

### 6.1 Section 选择

选择 20–24 个 Section，覆盖定义、原理、流程、公式、比较、应用、OCR 和上下位概念。

### 6.2 候选生成流程

1. 从 DS1/DS2 导出带页码、章节和段落编号的原文；
2. 每次向网页版 GPT 提供 1–3 个语义相关 Section；
3. 使用评测方案中的知识点候选 Prompt；
4. 保存原始候选为 `candidate`；
5. 运行 JSON Schema 检查；
6. 人工逐条回到原文确认；
7. 合并同义项；
8. 调整粒度；
9. 绑定 Gold Evidence；
10. 可选设置父知识点；
11. 标记 importance 和 role；
12. 批准为 Gold。

### 6.3 人工重点

- GPT 很容易把章节标题、普通名词和描述性短语都当作知识点；
- GPT 也容易过度归并相近但不同的概念；
- Parent 关系没有明确依据时保持 null；
- 不需要标注先修、相关、因果等知识图谱关系。

---

## 7. DS4：Query Processing Unit Set

### 7.1 五类案例

各准备约 12 条：

1. Query 标准化；
2. Knowledge Point Linking；
3. Filter Parsing；
4. Query Router；
5. Expansion / Rewrite Constraints。

### 7.2 构造流程

1. 从 DS3 知识点名称、Alias 和 Section 标题采样；
2. 人工制造空格、全角半角、英文大小写和标点变体；
3. 构造带章节、页码、文档、知识点限制的 Query；
4. 构造定义、比较、过程、应用、跨章节类型；
5. 标记 Must-Preserve Terms；
6. 标记允许扩展词和禁止扩展词；
7. 用 GPT 生成自然语言改写候选；
8. 人工确认意图和过滤条件没有改变；
9. 批准为 Gold。

### 7.3 需要人工专门补充的边界案例

- `A*`、`C++`、公式符号等不可被标准化破坏的术语；
- “只看第 3 章”等强过滤；
- 同名但不同章节的概念；
- 含英文缩写和中文别名的 Query；
- 改写后容易扩大范围的问题。

---

## 8. DS5：Retrieval + QA Gold

### 8.1 为什么合并构造

同一条问题的 Gold Evidence 是检索和 QA 的共同基础。分开构造会产生：

- 问题重复；
- Evidence 不一致；
- 人工工作量增加；
- QA 与 Retrieval 结论难以对齐。

### 8.2 100 条组成

- 精确事实 15；
- 定义 15；
- 同义改写 15；
- 比较 10；
- 过程 10；
- 示例或应用 10；
- 跨 Section 15；
- 不可回答 10。

### 8.3 构造流程

1. 从 DS2 Evidence 和 DS3 知识点选择 8–12 个原文包；
2. 每个原文包使用网页版 GPT 生成约 12 条候选；
3. 合并所有候选；
4. 运行 JSON Schema 和去重检查；
5. 人工审核 Query 是否自然；
6. 核验 Answerable；
7. 核验并补全 Gold Evidence Groups；
8. 标注 Graded Relevance；
9. 标注 Query Type、Difficulty 和 Properties；
10. 为可回答问题标注 Gold Answer Type；
11. Factoid/List 问题补充 Gold Short Answers；
12. 将解释性答案拆成 Required / Optional Gold Claims；
13. 为每个 Gold Claim 绑定 Required Evidence；
14. 补充 Forbidden Claims；
15. 对不可回答问题执行全语料搜索和人工确认；
16. 去除重复和过于机械的问题；
17. 分层抽样划分 Dev 60 / Test 40；
18. 锁定 Test。

### 8.4 GPT 可以生成什么

- 候选 Query；
- 候选 Gold Answer；
- 候选 Gold Claims；
- 候选 Evidence Text；
- Query Type 和 Difficulty；
- 候选不可回答问题。

### 8.5 必须人工确认什么

- Evidence 是否逐字来自原文；
- Evidence 是否完整；
- 是否存在替代 Evidence；
- Gold Claim 是否真的由 Evidence 支持；
- 不可回答问题是否全语料无答案；
- Forbidden Claim 是否确实错误；
- 问题是否泄漏原文关键词而过于简单。

---

## 9. DS6：Citation Migration Set

### 构造流程

从正式语料复制测试版本，依次制造：

1. 只改文档名称；
2. 修改一个段落；
3. 插入新页；
4. 替换扫描页；
5. 删除原 Evidence；
6. 修改 Parser 配置；
7. 修改 Chunker 配置。

每个场景人工标注旧引用预期状态：

- `valid`
- `migrated`
- `needs_review`
- `invalid`

保存变更前后文件 Hash 和变更清单。

---

## 10. DS7：Incremental / Writeback Set

### 构造流程

建立固定操作脚本：

- 修改一个 Section；
- 新增 Section；
- 删除 Section；
- 替换 OCR 页；
- 修改 Chunker；
- 修改 KP Prompt；
- 修改 Embedding；
- 修改 Reranker；
- 写回 1 条 Verified Content；
- 写回达到 10 条；
- 达到 3000 Token；
- 人工触发 Enrichment。

每个场景标注：

- 应重处理哪些 Section；
- 应复用哪些产物；
- 是否应触发知识点抽取；
- 是否应创建新 Index Version；
- 旧审核状态是否应保留。

---

## 11. DS8：Performance Workload Set

### 11.1 构建负载

固定：

- 全量 6 文档构建；
- 单文档构建；
- 单 Section 更新；
- 15 页 OCR；
- 写回富化批次。

### 11.2 在线负载

固定重放 DS5 的 100 条 Query，分别运行：

- Search；
- Search + Rerank；
- Context Packing；
- QA；
- QA + Abstention。

### 11.3 构造方式

由脚本从正式 ID 列表生成，不需要人工编写新问题。冷启动和热缓存分开运行。

---

## 12. 实际人工工作量估算

| 工作 | 预计人工量 |
|---|---|
| 冻结和登记 6 份文档 | 1–2 小时 |
| 40 页解析结构标注 | 4–6 小时 |
| 15 页 OCR 转录 | 3–5 小时，取决于页密度 |
| 20–24 Section 知识点审核 | 5–8 小时 |
| 60 条 QP 案例 | 2–4 小时 |
| 100 条 Retrieval + QA 审核 | 8–12 小时 |
| Citation / Incremental 场景 | 2–4 小时 |
| Test 40 条系统答案 Claim 评分 | 每个正式版本约 2–4 小时 |

这些工作不需要一次完成。推荐先完成 Pilot，再分批扩充。

---

## 13. 最小启动版本

正式大规模标注前先做：

- 2 份文档；
- 10 页解析；
- 5 页 OCR；
- 5 个 Section 知识点；
- 15 条 QP；
- 20 条 Retrieval + QA。

验证 Schema、脚本和人工流程无明显问题后，再扩充为正式规模。
