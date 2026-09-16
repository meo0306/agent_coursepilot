# CourseRAG 评测数据集与基线方案

**文档版本：** v1.0  
**文档状态：** 冻结执行版
**冻结日期：** 2026-07-22
**上位文档：**
- `01_CoursePilot_CourseRAG_Split_and_Refactor_Plan_v1.0.md`
- `02_CourseRAG_PRD_v1.0.md`

**评测范围：**
- PDF / DOCX 解析；
- PDF OCR；
- Evidence 与 Chunk；
- 知识点抽取；
- Query Processing；
- 检索与重排序；
- Context Packing；
- 基础引用 QA；
- 引用可信度；
- 构建和在线运行效率。

**暂不包含：**
- LLM-as-a-Judge；
- CoursePilot 教案、试卷、PPT 内容质量。

---

## 1. 文档目的

本文档用于确定 CourseRAG 的正式评测数据集、人工标注流程、基线系统、消融实验、指标口径和报告格式。

本文档需要解决以下问题：

1. 解析、OCR、知识点、检索和引用分别需要什么 Gold 数据；
2. 如何使用网页版 GPT 生成候选标注，同时避免将未经审核的结果直接当作 Gold；
3. 如何避免当前评测中“从检索结果反推相关 Chunk”的数据泄漏；
4. Chunker、Parser 或索引变化后，Gold 如何继续有效；
5. Query Processing 各模块如何独立启用、关闭和比较；
6. 如何形成可重复、可解释、可用于简历的真实指标；
7. 如何控制人工标注量，使评测既可信又可完成。

---

## 2. 核心原则

### 2.1 Gold 必须独立于被测系统

正式 Gold 不得由当前 Retriever、Chunker 或知识点抽取结果直接生成。

允许：

```text
原始课程文本
→ 网页版 GPT 生成候选
→ 人工回到原文审核
→ 正式 Gold
```

不允许：

```text
运行当前 Retriever
→ 从 Top-K 结果中挑含关键词的 Chunk
→ 将这些 Chunk 设为 Gold
```

后一种方法无法识别系统漏掉的相关证据，也会使 Recall、MRR 和 nDCG 失去意义。

### 2.2 Gold 绑定 Evidence Span，不绑定 Chunk ID

Gold 应保存：

- 文档；
- 文档版本；
- 章节；
- 页码；
- Block 或字符范围；
- 原文证据；
- 内容 Hash。

不得将 `chunk_id` 作为唯一 Gold 标识。

Chunker 发生变化后，通过 `EvidenceRecord` 与 `ChunkEvidenceLink` 判断新 Chunk 是否覆盖 Gold Evidence。

### 2.3 候选生成与正式标注分离

所有 LLM 生成结果初始状态只能为：

```text
candidate
```

人工确认后才能成为：

```text
approved
```

被拒绝或修改的候选应保留审计记录，便于发现候选生成 Prompt 的系统性问题。

### 2.4 调参集与最终测试集分离

正式数据集至少分为：

- `pilot`：验证 Schema、标注指南和脚本，不进入最终报告；
- `dev`：调整阈值、Top-K、RRF 权重、Rerank Top-N 和 Query Processing；
- `test`：锁定后只用于最终报告。

不得根据 Test 结果反复修改参数再重新报告同一 Test。

### 2.5 逐层评测，不只看端到端结果

CourseRAG 的错误可能来自：

- 解析；
- OCR；
- Evidence；
- Chunk；
- 知识点；
- Query Processing；
- 召回；
- Rerank；
- Context Packing；
- 引用映射。

必须分别报告，否则无法解释提升来自哪里。

### 2.6 不使用 LLM-as-a-Judge

当前版本所有正式指标来自：

- 字符或结构对齐；
- 人工 Gold；
- 排名指标；
- 显式人工 Checklist；
- 运行日志。

LLM 可以辅助生成候选问题、候选知识点和候选证据，但不负责最终评分。

---

## 3. 评测层级

CourseRAG 评测分为七层。

| 层级 | 被测对象 | 主要问题 |
|---|---|---|
| E1 | 文档解析与 OCR | 是否正确恢复原文、章节、顺序、表格和页码 |
| E2 | Evidence 与 Chunk | 是否稳定定位原文，切分是否保留语义 |
| E3 | 知识点抽取 | 是否抽对、抽全、粒度合理、证据绑定正确 |
| E4 | Query Processing | 标准化、链接、过滤、路由、改写是否有效 |
| E5 | Retrieval / Rerank / Context | 是否召回正确证据并合理排序、打包 |
| E6 | 基础引用 QA | 回答是否正确、完整、可拒答且 Claims 有证据支持 |
| E7 | 引用与工程性能 | 引用是否可解析，构建和在线调用是否可接受 |

最终报告同时提供：

- 各层独立指标；
- 最终集成配置指标；
- 相对当前基线的变化；
- 代价变化；
- 错误案例。

---

## 4. 评测语料设计

## 4.1 语料选择原则

语料应来自 CoursePilot 的真实使用场景，并覆盖：

- 原生文本 PDF；
- 扫描 PDF；
- 原生文本与扫描页混合 PDF；
- 结构良好的 DOCX；
- 样式不规范但可打开的 DOCX；
- 章节标题；
- 跨页段落；
- 列表；
- 表格；
- 中英文混合术语；
- 缩写和别名；
- 定义、原理、步骤、示例、比较和应用。

不要求为了评测收集大量无关学科文件。可以围绕一门主课程建立核心语料，再增加少量结构压力文件。

## 4.2 MVP 建议语料组成

建议至少包含 6 份文档：

| 编号 | 文档类型 | 主要作用 |
|---|---|---|
| D1 | 原生文本教材 PDF | 主检索与知识点语料 |
| D2 | 课程大纲 DOCX | 章节、目标、知识点和过滤 |
| D3 | 教学讲义 DOCX | 列表、表格和样式结构 |
| D4 | 扫描 PDF | OCR 基本能力 |
| D5 | 原生文本与扫描页混合 PDF | OCR 路由和混合解析 |
| D6 | 结构压力文档 | 多栏、页眉页脚、异常标题或复杂表格 |

D6 可以是从真实文档抽取并重新排版的测试夹具，不需要扩展产品支持的文件类型。

## 4.3 版本冻结

每份文档进入正式评测前保存：

```json
{
  "document_id": "doc_textbook",
  "filename": "人工智能导论.pdf",
  "mime_type": "application/pdf",
  "sha256": "...",
  "document_version": "eval_v1",
  "page_count": 312,
  "included_in": ["parse", "knowledge_point", "retrieval"]
}
```

正式 Test 运行时必须验证 Hash。文件变化后创建新数据集版本，不覆盖旧版本。

---

## 5. 数据集目录结构

```text
datasets/
└── courserag_eval/
    └── v1/
        ├── manifest.yaml
        ├── corpus/
        │   └── corpus_manifest.jsonl
        ├── parsing/
        │   ├── page_gold.jsonl
        │   ├── section_gold.jsonl
        │   ├── table_gold.jsonl
        │   └── ocr_gold.jsonl
        ├── knowledge_points/
        │   ├── kp_gold.jsonl
        │   ├── kp_links_gold.jsonl
        │   └── kp_candidates_raw.jsonl
        ├── query_processing/
        │   └── qp_cases.jsonl
        ├── retrieval/
        │   ├── retrieval_cases.jsonl
        │   ├── qa_cases.jsonl
        │   ├── evidence_gold.jsonl
        │   └── unanswerable_cases.jsonl
        ├── qa/
        │   ├── qa_review_scores.jsonl
        │   └── claim_matching_log.jsonl
        ├── splits/
        │   ├── pilot_ids.txt
        │   ├── dev_ids.txt
        │   └── test_ids.txt
        ├── reviews/
        │   ├── review_log.jsonl
        │   └── rejection_reasons.json
        └── reports/
```

正式数据使用 JSONL，便于版本控制、逐条审核和脚本处理。

---

## 6. 数据规模与分配

## 6.1 总体分阶段规模

### Pilot

用于验证标注流程：

- 解析页：10 页；
- OCR 页：5 页；
- 知识点 Section：5 个；
- Query Processing：15 条；
- Retrieval Query：20 条。

Pilot 不进入最终简历指标。

### MVP 正式数据集

建议规模：

| 子集 | 建议规模 |
|---|---:|
| 解析页 | 40 页，其中至少 10 页来自 DOCX 分页快照 |
| OCR 人工转录页 | 15 页 |
| 章节结构 | 20 个 Section 树片段 |
| 表格 | 10 张 |
| 知识点 Gold | 20–24 个 Section，约 80–120 个知识点 |
| Query Processing 单元案例 | 60 条 |
| Retrieval + QA Query | 100 条，共用问题与 Evidence |
| QA Gold Claims | 90 条可回答 Query 配套，Test 40 条全部人工评分 |
| 引用核验案例 | 与 100 条 Retrieval + QA Query 共用 |
| 增量更新案例 | 8–12 个变更场景 |

### Retrieval Split

100 条正式 Retrieval Query 建议分为：

- Dev：60 条；
- Test：40 条。

Test 中每一种主要 Query 类型至少保留 4 条，避免某一类型完全缺失。

## 6.2 Retrieval Query 类型分布

100 条正式 Query 的主类型建议为：

| 类型 | 数量 |
|---|---:|
| 精确事实 | 15 |
| 概念定义 | 15 |
| 同义改写或自然语言转述 | 15 |
| 概念比较 | 10 |
| 过程或步骤 | 10 |
| 示例或应用 | 10 |
| 跨段或跨 Section 综合 | 15 |
| 不可回答 | 10 |

额外属性可以重叠标记：

- `uses_ocr_source`
- `requires_section_filter`
- `requires_knowledge_point_alias`
- `requires_multiple_evidence`
- `contains_english_term`
- `hard_negative_present`

建议至少：

- 10 条涉及 OCR 来源；
- 20 条带显式过滤条件；
- 20 条涉及知识点别名；
- 10 条需要多个 Evidence；
- 10 条包含易混淆 Hard Negative。

---

## 7. 解析与 OCR Gold

## 7.1 Page Gold Schema

```json
{
  "case_id": "parse_page_001",
  "document_id": "doc_textbook",
  "document_version": "eval_v1",
  "page_number": 67,
  "page_type": "native_text",
  "needs_ocr": false,
  "reading_order": [
    "block_title_01",
    "block_para_01",
    "block_para_02",
    "block_table_01"
  ],
  "noise_regions": [
    {
      "type": "page_number",
      "text": "67"
    }
  ],
  "review_status": "approved"
}
```

### `page_type`

- `native_text`
- `scanned`
- `hybrid`
- `complex_layout`

## 7.2 Section Gold Schema

```json
{
  "case_id": "section_001",
  "document_id": "doc_textbook",
  "section_id": "gold_sec_034",
  "title": "3.4 启发式搜索",
  "level": 2,
  "parent_section_id": "gold_sec_030",
  "page_start": 67,
  "page_end": 73,
  "first_text": "启发式搜索利用问题相关信息……",
  "last_text": "本节小结……",
  "review_status": "approved"
}
```

## 7.3 DOCX Pagination Gold Schema

```json
{
  "case_id": "docx_page_001",
  "document_id": "doc_syllabus",
  "document_version": "eval_v1",
  "render_profile": {
    "provider": "libreoffice",
    "renderer_version": "fixed_version",
    "font_manifest_hash": "...",
    "profile_hash": "..."
  },
  "block_id": "docx_block_034",
  "paragraph_index": 18,
  "expected_physical_page_index": 4,
  "expected_display_page_label": "1",
  "expected_section_page_index": 1,
  "rendered_pdf_hash": "...",
  "review_status": "approved"
}
```

DOCX Gold 同时区分：

- `physical_page_index`：分页快照中的物理页序号；
- `display_page_label`：文档实际展示的页码，可为罗马数字或按 Section 重启；
- `section_page_index`：当前 Section 内的页序号；
- 结构兜底位置：`section_path + paragraph_index + block_id + char_range`。

同一正式数据集必须固定 Renderer、版本和字体 Manifest。

## 7.3 OCR Gold Schema

```json
{
  "case_id": "ocr_001",
  "document_id": "doc_scan",
  "page_number": 12,
  "image_hash": "...",
  "gold_text": "人工审核后的规范化页面文字……",
  "normalization": {
    "remove_spaces_between_chinese": true,
    "normalize_full_width": true,
    "ignore_line_break_difference": true
  },
  "regions": [
    {
      "region_id": "r1",
      "bbox": [86, 120, 1132, 428],
      "gold_text": "……"
    }
  ],
  "review_status": "approved"
}
```

## 7.4 解析指标

### 必选指标

- 文档解析成功率；
- 标题检测 Precision / Recall / F1；
- 标题层级准确率；
- Section 边界准确率；
- PDF 页码映射准确率；
- DOCX 物理页映射准确率；
- DOCX 显示页码准确率；
- OCR 路由 Precision / Recall；
- OCR Character Error Rate；
- 噪声识别 Precision / Recall；
- Evidence 原文定位准确率。

### 可选增强指标

- 阅读顺序 Kendall Tau；
- 段落边界 F1；
- 表格行列结构准确率；
- Bounding Box IoU。

## 7.5 OCR Character Error Rate

对中文文本做统一规范化后计算：

```text
CER = (Substitutions + Deletions + Insertions) / Gold Characters
```

需要固定：

- 是否忽略空格；
- 是否统一全角半角；
- 是否统一换行；
- 是否保留标点。

同一报告中不得改变规范化规则。

---

## 8. Evidence 与 Chunk 评测

## 8.1 目标

该层不直接评价“回答好不好”，而是评价：

- Evidence 是否稳定；
- Chunk 是否覆盖完整语义；
- Chunk 是否能够追溯 Evidence；
- Parent-Child 是否合理；
- Chunker 更新后 Gold 是否仍可映射。

## 8.2 Evidence Gold Schema

```json
{
  "evidence_id": "gold_ev_001",
  "document_id": "doc_textbook",
  "document_version": "eval_v1",
  "section_path": ["第3章", "3.4 启发式搜索"],
  "page_start": 67,
  "page_end": 67,
  "source_type": "native_text",
  "gold_text": "启发式搜索利用与问题相关的启发信息指导搜索方向。",
  "block_start": "gold_block_451",
  "block_end": "gold_block_451",
  "content_hash": "...",
  "review_status": "approved"
}
```

## 8.3 指标

- Evidence Resolving Rate：Gold Evidence 是否能够被系统解析和读取；
- Evidence Text Consistency：系统 Evidence 文本与 Gold 原文是否一致；
- Evidence Page Accuracy；
- Chunk Evidence Coverage；
- Complete Semantic Unit Rate；
- Cross-boundary Split Error Rate；
- Parent Expansion Sufficiency；
- Chunk Redundancy Rate。

### Complete Semantic Unit Rate

人工检查抽样 Chunk 是否出现：

- 定义前半句与后半句被拆开；
- 列表标题与列表项分离；
- 表题与表格分离；
- 步骤序列被截断；
- 示例脱离其解释。

该项采用人工 Checklist，不使用 LLM Judge。

---

## 9. 知识点 Gold 数据集

## 9.1 标注范围

知识点 Gold 不需要覆盖整本教材。选择 20–24 个代表性 Section，覆盖：

- 定义密集型；
- 原理型；
- 流程型；
- 公式型；
- 比较型；
- 示例与应用型；
- OCR 来源；
- 跨段重复概念；
- 上下位概念。

## 9.2 Knowledge Point Gold Schema

```json
{
  "gold_kp_id": "gold_kp_001",
  "course_id": "course_001",
  "canonical_name": "启发式搜索",
  "aliases": ["有信息搜索"],
  "summary": "利用问题相关启发信息指导搜索方向的方法。",
  "parent_gold_kp_id": "gold_kp_search",
  "section_ids": ["gold_sec_034"],
  "evidence_ids": ["gold_ev_001", "gold_ev_002"],
  "roles": ["definition", "principle"],
  "importance": "core",
  "granularity": "atomic",
  "review_status": "approved",
  "review_notes": ""
}
```

### `importance`

- `core`
- `supporting`
- `optional`

### `granularity`

- `atomic`
- `composite`
- `too_broad`
- `too_narrow`

正式 Gold 中原则上只保留 `atomic` 或经人工认可的 `composite`。

## 9.3 KnowledgePointEvidenceLink Gold

```json
{
  "gold_kp_id": "gold_kp_001",
  "evidence_id": "gold_ev_001",
  "role": "definition",
  "is_primary": true,
  "review_status": "approved"
}
```

## 9.4 知识点指标

### 抽取正确性

- Knowledge Point Precision；
- Knowledge Point Recall；
- F1；
- Core Knowledge Point Recall。

### 粒度与重复

- Granularity Acceptance Rate；
- Duplicate Rate；
- Over-merge Rate；
- Under-merge Rate。

### 关系和证据

- Evidence Binding Accuracy；
- Section Assignment Accuracy；
- Alias Accuracy；
- Parent-Child Accuracy；
- KnowledgePoint-Chunk Link Accuracy。

### 发布阈值

在 Dev 上比较：

```text
0.60 / 0.70 / 0.75 / 0.80 / 0.85
```

每个阈值报告：

- 自动发布 Precision；
- 自动发布 Recall；
- `needs_review` 比例；
- 高重要度知识点漏审数量；
- 教师修改率。

默认 0.75 只是初始配置，不得在未评测情况下宣称最优。

## 9.5 知识点匹配规则

系统预测知识点与 Gold 的匹配按以下顺序：

1. 人工确认的完全匹配；
2. 标准名称规范化后匹配；
3. Gold Alias 匹配；
4. 人工确认的语义等价；
5. 否则不匹配。

不得只依赖 Embedding 相似度自动判定最终正确性。

---

## 10. Query Processing 数据集

## 10.1 单元案例规模

建议 60 条，分为：

| 子能力 | 数量 |
|---|---:|
| Query 标准化 | 12 |
| 知识点链接 | 12 |
| 过滤条件解析 | 12 |
| Query Router | 12 |
| 查询扩展与改写约束 | 12 |

一条案例可同时覆盖多个能力，但每类必须有足够独立案例。

## 10.2 Query Processing Case Schema

```json
{
  "case_id": "qp_001",
  "raw_query": "请只在第3章里找一下 A* 搜索 的定义",
  "expected": {
    "normalized_query": "请只在第3章里找一下 A* 搜索的定义",
    "linked_knowledge_points": ["kp_astar"],
    "filters": {
      "section_prefix": "第3章"
    },
    "route": "definition",
    "allowed_expansions": ["A星搜索", "A-star search"],
    "must_preserve_terms": ["A*"],
    "must_preserve_filters": true
  },
  "review_status": "approved"
}
```

## 10.3 Query Processing 指标

### 单元正确性

- Normalization Exact Match；
- Knowledge Point Linking Precision / Recall / F1；
- Filter Parsing Exact Match；
- Route Accuracy；
- Must-Preserve Constraint Pass Rate；
- Rewrite Failure Rate。

### 检索收益

对同一 Retrieval Dataset 比较：

- 无 Query Processing；
- + 标准化；
- + 知识点链接和别名扩展；
- + Router；
- + 多查询改写；
- + 低召回重试。

报告：

- Recall@K 变化；
- MRR 变化；
- nDCG 变化；
- P50/P95 延迟变化；
- API 调用数；
- Token 和成本；
- 无收益改写比例；
- 负收益改写比例。

---

## 11. Retrieval Gold 数据集

## 11.1 Retrieval Case Schema

```json
{
  "case_id": "ret_001",
  "query": "什么是启发式搜索，它与无信息搜索的主要区别是什么？",
  "query_type": "comparison",
  "answerable": true,
  "difficulty": "medium",
  "gold_answer_type": "explanatory",
  "gold_short_answers": [],
  "gold_claims": [
    {
      "claim_id": "gold_claim_001",
      "claim_text": "启发式搜索利用问题相关启发信息指导搜索。",
      "required_evidence_ids": ["gold_ev_heuristic_definition"],
      "importance": "required"
    }
  ],
  "expected_knowledge_points": [
    "gold_kp_heuristic_search",
    "gold_kp_uninformed_search"
  ],
  "filters": {},
  "gold_evidence_groups": [
    {
      "group_id": "g1",
      "sufficiency": "complete",
      "required_evidence_ids": [
        "gold_ev_heuristic_definition",
        "gold_ev_uninformed_definition"
      ]
    }
  ],
  "supporting_evidence_ids": [
    "gold_ev_search_comparison_summary"
  ],
  "properties": {
    "requires_multiple_evidence": true,
    "uses_ocr_source": false,
    "requires_alias": false,
    "hard_negative_present": true
  },
  "candidate_source": "gpt_assisted",
  "review_status": "approved",
  "review_notes": ""
}
```

## 11.2 不可回答案例

```json
{
  "case_id": "ret_unanswerable_001",
  "query": "教材是否介绍了量子强化学习的具体算法？",
  "query_type": "unanswerable",
  "answerable": false,
  "gold_evidence_groups": [],
  "supporting_evidence_ids": [],
  "expected_behavior": "no_relevant_evidence",
  "review_status": "approved"
}
```

QA 不在 MVP，因此不可回答案例当前主要用于评价：

- 是否返回明显无关内容；
- Top-1/Top-K 最高分是否低于拒检阈值；
- 低召回重试是否产生伪相关结果。

## 11.3 Graded Relevance

用于 nDCG 的等级：

| 等级 | 含义 |
|---|---|
| 2 | 可以直接、充分支撑 Query |
| 1 | 有帮助但不完整，只能作为补充 |
| 0 | 无关或误导 |

Gold Evidence Group 中的主要 Evidence 为 2；Supporting Evidence 通常为 1。

## 11.4 多证据问题

跨段或比较问题不能只判断“是否命中任意一个 Evidence”。

同时报告：

- Any Evidence Hit@K；
- Complete Evidence Group Recall@K；
- Required Evidence Coverage@K。

---


## 11.5 QA Gold 扩展

QA 与 Retrieval 共用同一批 Query 和 Gold Evidence，避免重复构造两套问题集。可回答案例额外标注：

- `gold_answer_type`；
- `gold_short_answers`；
- `gold_claims`；
- Claim 对应的 Required Evidence；
- Claim 重要度；
- 允许的回答变体；
- 禁止出现的错误结论。

### Gold Answer Type

- `factoid`：短事实，可计算 Exact Match 和 Token F1；
- `list`：有限列表，可计算集合 Precision / Recall / F1；
- `explanatory`：解释性回答，以人工 Claim 级指标为主；
- `comparison`：比较多个对象，要求覆盖各比较维度；
- `procedure`：步骤型答案，要求步骤覆盖与顺序；
- `unanswerable`：资料不足，应拒答。

### QA Case 示例

```json
{
  "case_id": "qa_001",
  "query": "启发式搜索与无信息搜索有什么区别？",
  "answerable": true,
  "gold_answer_type": "comparison",
  "gold_short_answers": [],
  "gold_claims": [
    {
      "claim_id": "gc_001",
      "claim_text": "启发式搜索利用问题相关启发信息指导搜索。",
      "importance": "required",
      "required_evidence_ids": ["gold_ev_heuristic_definition"]
    },
    {
      "claim_id": "gc_002",
      "claim_text": "无信息搜索只利用问题定义提供的信息。",
      "importance": "required",
      "required_evidence_ids": ["gold_ev_uninformed_definition"]
    }
  ],
  "forbidden_claims": [
    "无信息搜索不使用任何搜索策略"
  ],
  "review_status": "approved"
}
```

不可回答案例不构造虚假的 Gold Answer，只保存：

```json
{
  "answerable": false,
  "gold_answer_type": "unanswerable",
  "gold_claims": [],
  "expected_answer_status": "abstained_insufficient_evidence"
}
```


### QA 人工评分 Schema

```json
{
  "run_id": "qa_run_001",
  "case_id": "qa_001",
  "answer_status_correct": true,
  "system_claims": [
    {
      "system_claim_id": "sc_001",
      "claim_text": "启发式搜索利用问题相关信息指导搜索。",
      "label": "correct_supported",
      "matched_gold_claim_ids": ["gc_001"],
      "citation_support": [
        {
          "evidence_id": "gold_ev_heuristic_definition",
          "supports_claim": true
        }
      ]
    }
  ],
  "missed_gold_claim_ids": [],
  "conciseness_pass": true,
  "reviewer_notes": "",
  "review_status": "approved"
}
```

每个正式 Test Run 都应单独生成评分文件，不能覆盖 Gold Dataset。

## 12. Retrieval、Context 与 QA 指标

## 12.1 Retrieval 指标

### Hit@K

Top-K 中至少出现一个相关 Evidence 的 Query 比例。

### Recall@K

对每条 Query：

```text
命中的 Gold Evidence 数 / Gold Evidence 总数
```

再对 Query 取平均。

### MRR@K

第一个高度相关结果的倒数排名均值。

### nDCG@K

使用 0/1/2 Graded Relevance 计算。

### Precision@K

Top-K 中相关结果比例。

### Complete Evidence Group Recall@K

至少完整覆盖一个 `complete` Evidence Group 的 Query 比例。

### Filter Accuracy

显式章节、文档或知识点过滤条件是否被正确执行。

## 12.2 Context Packing 指标

- Gold Evidence Coverage；
- Context Precision；
- Token Budget Compliance；
- Duplicate Context Rate；
- Truncation Rate；
- Complete Evidence Group Coverage；
- Evidence Boundary Preservation；
- Parent Expansion Utility。

### Context Precision

进入最终 Context 的 Token 中，来自相关 Evidence 或必要相邻上下文的比例。

MVP 可采用基于 Evidence 标记的近似值，不要求逐 Token 人工标注全部上下文。


## 12.3 基础引用 QA 指标

QA 指标分为自动指标和人工 Claim 级指标。

### 自动指标

- Exact Match；
- Token F1；
- List Set Precision / Recall / F1；
- Answerability Precision / Recall / F1；
- Answer Status Accuracy；
- Citation Resolvability；
- QA P50/P95；
- Token 与成本。

### 人工 Claim 级指标

对锁定 Test 的 40 条回答进行人工标注：

- Gold Claim Coverage；
- Correct Claim Precision；
- Unsupported Claim Rate；
- Contradictory Claim Rate；
- Citation Claim Support Rate；
- Citation Precision；
- Citation Recall；
- Answer Conciseness Pass Rate。

人工评分不使用模糊的“整体好不好”，而是将系统答案拆成原子 Claims，逐条标记：

- `correct_supported`
- `correct_but_uncited`
- `unsupported`
- `contradictory`
- `irrelevant`

### 拒答指标

- Answerability F1；
- Unanswerable Recall；
- False Answer Rate on Unanswerable；
- False Abstention Rate on Answerable。

## 12.4 指标定义与计算口径

以下指标必须在评测脚本和报告中使用相同口径。

### 12.4.1 标题检测 Precision / Recall / F1

```text
Precision = 正确匹配的预测标题数 / 预测标题总数
Recall    = 正确匹配的预测标题数 / Gold 标题总数
F1        = 2 × Precision × Recall / (Precision + Recall)
```

标题匹配要求文档、页码、规范化标题文本一致；层级正确性单独计算，不混入标题检测。

### 12.4.2 Section Boundary Accuracy

对每个 Gold Section，若预测 Section 的起止 Block 均落在允许容差内，则视为正确。MVP 默认容差为前后各 1 个 Block。

```text
Section Boundary Accuracy = 边界正确的 Gold Section 数 / Gold Section 总数
```

### 12.4.3 OCR 路由 Precision / Recall

```text
Precision = 正确进入 OCR 的页面数 / 系统送入 OCR 的页面数
Recall    = 正确进入 OCR 的页面数 / Gold 标记需要 OCR 的页面数
```

### 12.4.4 OCR CER

```text
CER = (替换字符数 + 删除字符数 + 插入字符数) / Gold 字符总数
```

先按固定规范统一空格、换行、全角半角和标点，再计算 Levenshtein 编辑距离。

### 12.4.5 Evidence Resolving Rate

```text
Evidence Resolving Rate = 能成功读取且版本匹配的 Evidence 数 / 待核验 Evidence 总数
```

### 12.4.6 Evidence Text Consistency

对系统 Evidence 文本与 Gold Evidence 文本计算规范化 CER：

```text
Evidence Text Consistency = 1 - Evidence CER
```

报告平均值，并额外报告完全一致率。

### 12.4.7 Chunk Evidence Coverage

对每条 Gold Evidence，判断是否存在至少一个 Chunk 完整覆盖其 Source Span：

```text
Chunk Evidence Coverage = 被至少一个 Chunk 完整覆盖的 Gold Evidence 数 / Gold Evidence 总数
```

### 12.4.8 Complete Semantic Unit Rate

对人工抽样的语义单元进行 Checklist：定义、步骤、列表、表格、示例是否在一个 Child Chunk 或可恢复的 Parent-Child 组合中完整存在。

```text
Complete Semantic Unit Rate = 完整保留的语义单元数 / 抽样语义单元总数
```

### 12.4.9 Cross-boundary Split Error Rate

```text
Cross-boundary Split Error Rate = 被不合理切断的语义单元数 / 抽样语义单元总数
```

“不合理切断”不包括可通过明确 Parent Expansion 恢复的正常分块。

### 12.4.10 Chunk Redundancy Rate

对同一文档相邻 Chunk 的规范化 Token 集合计算重复 Token 数。Overlap 配置允许的重复也计入实际冗余，但报告中需注明目标 Overlap。

```text
Chunk Redundancy Rate = 所有相邻 Chunk 重复 Token 总数 / 所有 Chunk Token 总数
```

### 12.4.11 Knowledge Point Precision / Recall / F1

在人工建立的预测—Gold 匹配表上计算：

```text
Precision = 匹配 Gold 的预测知识点数 / 预测知识点总数
Recall    = 被匹配的 Gold 知识点数 / Gold 知识点总数
```

一个预测知识点最多匹配一个 Gold；过度归并需要单独标记，不能重复计 TP。

### 12.4.12 Granularity Acceptance Rate

```text
Granularity Acceptance Rate = 粒度被人工判定为可接受的预测知识点数 / 预测知识点总数
```

### 12.4.13 Over-merge Rate 与 Under-merge Rate

```text
Over-merge Rate = 同时错误合并两个及以上 Gold 知识点的预测项数 / 预测知识点总数
Under-merge Rate = 同一个 Gold 被拆成两个及以上预测项的 Gold 数 / Gold 知识点总数
```

### 12.4.14 Evidence Binding Accuracy

```text
Evidence Binding Accuracy = 证据关系被人工判定正确的预测 KP-Evidence Link 数 / 被检查 Link 总数
```

### 12.4.15 Knowledge Point Linking F1

Query 中预测链接的知识点 ID 与 Gold ID 按集合计算 Precision、Recall 和 F1。

### 12.4.16 Filter Parsing Exact Match

章节、文档、页码、知识点和来源等级等结构化过滤字段全部与 Gold 一致时记 1，否则记 0。

```text
Filter Parsing EM = 完全匹配案例数 / 案例总数
```

另可报告字段级 Micro F1，帮助定位是哪一类过滤字段错误。

### 12.4.17 Rewrite Effective Rate 与 Negative Rewrite Rate

在相同 Retriever 配置下，对每条启用改写的 Query 比较目标指标，默认用 Recall@10，其次用 MRR@10：

```text
Rewrite Effective Rate = 指标得到严格提升的 Query 数 / 启用改写的 Query 数
Negative Rewrite Rate  = 指标严格下降的 Query 数 / 启用改写的 Query 数
```

### 12.4.18 Hit@K、Recall@K、Precision@K

设每条 Query 的 Gold Evidence 集合为 G，Top-K 返回结果覆盖的 Evidence 集合为 R_K：

```text
Hit@K       = 1，若 G ∩ R_K 非空；否则为 0
Recall@K    = |G ∩ R_K| / |G|
Precision@K = |G ∩ R_K| / K
```

最终指标为所有适用 Query 的宏平均。不可回答 Query 不进入普通 Recall 和 Precision，而进入拒检指标。

### 12.4.19 MRR@K

设第一个相关结果排名为 rank：

```text
RR@K = 1 / rank，若 rank ≤ K；否则为 0
MRR@K = 所有 Query 的 RR@K 平均值
```

### 12.4.20 nDCG@K

```text
DCG@K  = Σ(i=1..K) (2^rel_i - 1) / log2(i + 1)
nDCG@K = DCG@K / IDCG@K
```

`rel_i` 使用 0/1/2 相关等级。若某 Query 无相关 Gold，则不进入 nDCG，单独评价拒检。

### 12.4.21 Complete Evidence Group Recall@K

```text
Complete Group Hit = 1，若 Top-K 完整覆盖至少一个 complete Evidence Group；否则为 0
Complete Evidence Group Recall@K = Complete Group Hit 的宏平均
```

### 12.4.22 Context Gold Evidence Coverage

```text
Context Gold Evidence Coverage = 最终 Context 覆盖的 Gold Evidence 数 / Gold Evidence 总数
```

### 12.4.23 Context Precision

按 Evidence 与必要相邻 Block 近似计算：

```text
Context Precision = 相关 Evidence 和必要相邻上下文 Token 数 / Context 总 Token 数
```

必要相邻上下文必须在 Gold 或人工复核中明确标记，不能事后随意扩大。

### 12.4.24 Duplicate Context Rate

```text
Duplicate Context Rate = Context 中重复出现的规范化 Token 数 / Context 总 Token 数
```

### 12.4.25 Exact Match 与 Token F1

Exact Match 对规范化后的预测短答案与任一 `gold_short_answers` 完全一致时记 1。

Token F1 对中文采用字符或分词后 Token 多重集合：

```text
Precision = 重叠 Token 数 / 预测 Token 数
Recall    = 重叠 Token 数 / Gold Token 数
F1        = 2PR / (P + R)
```

同一问题有多个 Gold 短答案时取最高 F1。

### 12.4.26 Gold Claim Coverage

```text
Gold Claim Coverage = 被系统回答正确表达的 required Gold Claims 数 / required Gold Claims 总数
```

由人工 Claim 匹配表判定，不使用纯 Embedding 阈值自动评分。

### 12.4.27 Correct Claim Precision

```text
Correct Claim Precision = correct_supported Claims 数 / 系统事实性 Claims 总数
```

### 12.4.28 Unsupported Claim Rate

```text
Unsupported Claim Rate = unsupported + correct_but_uncited Claims 数 / 系统事实性 Claims 总数
```

若 Claim 虽正确但引用不支持，仍视为 unsupported。

### 12.4.29 Contradictory Claim Rate

```text
Contradictory Claim Rate = 与 Gold 或原文直接冲突的 Claims 数 / 系统事实性 Claims 总数
```

### 12.4.30 Answerability Precision / Recall / F1

把“系统选择回答”视为预测正类，把 Gold `answerable=true` 视为真实正类：

```text
Precision = 正确回答的可回答问题数 / 系统选择回答的问题数
Recall    = 正确回答的可回答问题数 / Gold 可回答问题数
```

这里“正确回答”至少要求没有 contradictory Claim，且 Required Gold Claim Coverage 达到预设阈值，MVP 默认 0.5，最终在 Dev 固定。

同时报告：

```text
False Answer Rate on Unanswerable = 不可回答问题中系统仍作答的比例
False Abstention Rate on Answerable = 可回答问题中系统拒答的比例
```

### 12.4.31 Citation Claim Support Rate

```text
Citation Claim Support Rate = 至少有一个引用能够直接支持的系统事实性 Claims 数 / 系统事实性 Claims 总数
```

### 12.4.32 Citation Precision / Recall

Claim 级计算：

```text
Citation Precision = 能支持其所绑定 Claim 的 Citation Link 数 / 系统输出 Citation Link 总数
Citation Recall    = 已被至少一个正确 Citation 支持的 Gold Claims 数 / 需要引用的 Gold Claims 总数
```

### 12.4.33 Citation Resolvability

```text
Citation Resolvability = 可成功解析到指定文档版本和 Source Span 的 Citation 数 / 系统输出 Citation 总数
```

### 12.4.34 Reused Artifact Ratio

```text
Reused Artifact Ratio = 增量构建中直接复用的阶段产物数 / 理论可复用阶段产物总数
```

阶段产物以 Section 级 Parsed、Evidence、Chunk、KP Candidate 和 Embedding 记录计数，报告中必须注明粒度。

### 12.4.35 Full-to-Incremental Speedup

```text
Speedup = 同一更新场景的全量重建耗时 / 增量构建耗时
```

### 12.4.36 P50 / P95

对同一配置的多次运行延迟排序：

- P50：第 50 百分位；
- P95：第 95 百分位。

冷启动和热缓存必须分开报告。

---


### 12.4.37 标题层级准确率

在已正确匹配的标题上计算：

```text
标题层级准确率 = 预测 level 与 Gold level 一致的匹配标题数 / 正确匹配标题总数
```

### 12.4.38 页码映射准确率

```text
页码映射准确率 = 页码范围与 Gold 完全一致的 Evidence 或 Block 数 / 被检查对象总数
```

若跨页对象只允许容差，应在 Run Manifest 中固定容差，不得临时调整。

### 12.4.39 Parent Expansion Sufficiency

仅在 Gold 标记需要父级扩展的案例上计算：

```text
Parent Expansion Sufficiency = 扩展后完整覆盖 Gold 语义单元的案例数 / 需要 Parent Expansion 的案例总数
```

### 12.4.40 Parent Expansion Utility

```text
Parent Expansion Utility = 扩展后 Gold Coverage 提升且未导致 Context Precision 低于阈值的案例数 / 启用 Parent Expansion 的案例数
```

Context Precision 阈值在 Dev 固定，MVP 初始可设为 0.5。

### 12.4.41 Token Budget Compliance

```text
Token Budget Compliance = 最终 Context Token 数不超过配置预算的案例数 / 全部 Context 案例数
```

### 12.4.42 Truncation Rate

```text
Truncation Rate = 至少一个 Context Item 被截断的案例数 / 全部 Context 案例数
```

同时报告“关键 Evidence 被截断率”。

### 12.4.43 Evidence Boundary Preservation

```text
Evidence Boundary Preservation = 最终 Context 中未被截断或重排破坏的 Gold Evidence 数 / 进入 Context 的 Gold Evidence 数
```

### 12.4.44 Answer Conciseness Pass Rate

人工依据固定 Checklist 判断回答是否存在大段重复、明显无关解释或超出配置长度：

```text
Answer Conciseness Pass Rate = 通过简洁性检查的回答数 / 被人工检查回答总数
```

### 12.4.45 OCR Source Disclosure Rate

```text
OCR Source Disclosure Rate = 正确标记为 OCR 来源的 OCR Citation 数 / 系统输出的 OCR Citation 总数
```

### 12.4.46 Stale Citation Rate

```text
Stale Citation Rate = 指向已失效文档版本或已变化 Source Span 的 Citation 数 / 被检查 Citation 总数
```

### 12.4.47 Citation Migration Success Rate

```text
Citation Migration Success Rate = 可迁移旧引用中被正确映射至新 Evidence 的数量 / Gold 标记为可迁移的旧引用总数
```

### 12.4.48 Reprocessed Section Ratio

```text
Reprocessed Section Ratio = 增量任务实际重新处理的 Section 数 / 文档 Section 总数
```

该指标越低不一定越好，还需同时满足变更覆盖正确。

### 12.4.49 Unaffected Knowledge Point Preservation

```text
Unaffected KP Preservation = 更新前未受影响且更新后 ID、内容和状态保持正确的 KP 数 / Gold 未受影响 KP 总数
```

### 12.4.50 Review Status Preservation

```text
Review Status Preservation = 未受影响对象中审核状态保持正确的对象数 / 未受影响且已有审核状态的对象总数
```

### 12.4.51 Citation Preservation

```text
Citation Preservation = Gold 预期仍有效的旧引用中更新后仍可解析且内容一致的数量 / Gold 预期仍有效的旧引用总数
```

### 12.4.52 Duplicate Writeback Rate

```text
Duplicate Writeback Rate = 因重复请求产生的额外业务记录或索引记录数 / 重复写回请求总数
```

幂等实现正确时应为 0。

### 12.4.53 Enrichment Trigger Correctness

```text
Enrichment Trigger Correctness = 触发状态与 Gold 预期一致的写回场景数 / 写回触发测试场景总数
```

### 12.4.54 Low-recall Retry Improvement Rate

在确实触发二次检索的 Query 上计算：

```text
Improvement Rate = 二次检索后 Recall@10 或 Complete Group Coverage 提升的 Query 数 / 触发二次检索 Query 数
```

同时报告负收益率和额外延迟。

## 13. 引用可信度评测

当前不评价最终 QA 文本，只评价检索结果和 Context 的来源链。

## 13.1 指标

- Citation Resolvability：返回的 `evidence_id` 能否成功解析；
- Citation Completeness：每个正式 Context Item 是否至少有一个 Evidence；
- Citation Text Consistency：Evidence 文本是否与原文一致；
- Citation Page Accuracy；
- Citation Section Accuracy；
- OCR Source Disclosure Rate；
- Stale Citation Rate；
- Citation Migration Success Rate。

## 13.2 文档更新测试

构造以下情况：

1. 只修改文档名称；
2. 修改某一 Section 的一个段落；
3. 插入新页导致后续页码变化；
4. 替换扫描页；
5. 调整 Chunker；
6. 更新 Parser；
7. 删除原证据。

验证旧引用能否被标记为：

- `valid`
- `migrated`
- `needs_review`
- `invalid`

---

## 14. 增量更新评测

## 14.1 测试场景

建议建立 8–12 个固定场景：

| 场景 | 预期影响范围 |
|---|---|
| 修改文档显示名称 | 仅元数据 |
| 修改一个段落 | 当前 Section + 邻接边界 |
| 新增一个 Section | 新 Section 及索引 |
| 删除一个 Section | 删除相关 Evidence、Chunk、知识点链接 |
| 替换单个扫描页 | 当前页与所属 Section |
| 修改 Chunker 配置 | 当前文档 Chunk 与索引 |
| 修改知识点 Prompt | 指定 Section 或文档知识点 |
| 修改 Embedding 模型 | 受影响 Chunk 向量 |
| 修改 Reranker | 无需重建索引 |
| 新增 1 条教师写回 | 立即保存，不触发完整知识点抽取 |
| 写回达到批次阈值 | 触发 EnrichmentBatch |

## 14.2 指标

- Reprocessed Section Ratio；
- Reused Artifact Ratio；
- Incremental Build Time；
- Full-to-Incremental Speedup；
- Unaffected Knowledge Point Preservation；
- Review Status Preservation；
- Citation Preservation；
- Duplicate Writeback Rate；
- Enrichment Trigger Correctness。

---

## 15. 人工标注流程

## 15.1 总体流程

```text
选择文档和 Section
    ↓
导出带页码、章节和稳定编号的原文
    ↓
网页版 GPT 生成候选
    ↓
候选 Schema 校验
    ↓
人工逐条回到原文核验
    ↓
修改、补充或拒绝
    ↓
批准为 Gold
    ↓
随机抽样复核
    ↓
锁定数据集版本
```

## 15.2 人工审核最低要求

每条 Retrieval Query 必须确认：

- Query 是否自然；
- Query 是否仅依赖给定课程资料；
- `answerable` 是否正确；
- Gold Evidence 是否充分；
- 页码和章节是否正确；
- 是否存在未记录的替代证据；
- Query 类型是否正确；
- 是否与已有 Query 重复；
- 是否泄漏原文专有措辞，导致问题过于简单。

每个 Knowledge Point 必须确认：

- 是否具有教学意义；
- 粒度是否合理；
- 名称是否规范；
- Alias 是否真的是同义表达；
- Evidence 是否直接支持；
- 是否与其他 Gold 重复；
- Parent 是否合理；
- Importance 是否合理。

## 15.3 抽样复核

正式 Test 集建议：

- 打乱顺序；
- 隐藏候选来源；
- 对至少 20% 的样本执行第二次复核；
- 记录前后修改；
- 若发现系统性问题，返回全量重查对应类别。

---

## 16. 用网页版 GPT 生成 Retrieval + QA 候选的提示词

下面的 Prompt 只用于生成候选，不生成正式 Gold。

```text
你是一名课程知识库评测数据标注助手。我要基于我提供的课程原文，生成用于 RAG 检索、基础 QA 和引用评测的候选问题、证据与答案 Claims。你的结果只作为候选，之后会由人工回到原文审核。

【目标】
根据给定原文生成自然、真实、具有区分度的检索问题。问题应模拟教师备课、学生理解课程或教学 Agent 调取资料时可能提出的查询。

【严格要求】
1. 只能使用我提供的原文，不得补充外部知识。
2. 每个可回答问题必须给出完整、逐字复制的候选证据，不得改写证据。
3. 证据必须标明我提供的页码、章节和段落编号。
4. 不得使用 Chunk ID。
5. 同一问题如果需要多个片段共同支撑，必须分别列出。
6. 不要只把标题改写成问题。
7. 不要生成只靠一个罕见关键词就能直接命中的机械问题。
8. 至少包含同义改写、比较、步骤、应用和跨段综合问题。
9. 可以生成少量不可回答问题，但必须确保给定原文确实没有答案。
10. 每个 Gold Claim 必须绑定能够直接支持它的候选 Evidence。
11. 对不可回答问题不得生成虚假答案或 Claims。
12. 可以列出原文明确不支持、容易被模型误答的 forbidden_claims。
13. 不得因为不确定而编造证据。
14. 输出必须是合法 JSON 数组，不要输出解释文字。

【问题类型】
exact_fact
definition
paraphrase
comparison
procedure
application
cross_section
unanswerable

【难度】
easy：问题措辞与原文接近，单一证据即可。
medium：存在同义改写，或需要理解段落语义。
hard：需要多个证据、跨段比较，或存在相似但错误的干扰内容。

【输出 Schema】
[
  {
    "candidate_id": "cand_001",
    "query": "",
    "query_type": "",
    "answerable": true,
    "difficulty": "",
    "gold_answer_type": "factoid|list|explanatory|comparison|procedure|unanswerable",
    "candidate_gold_answer": "",
    "candidate_gold_short_answers": [],
    "candidate_gold_claims": [
      {
        "claim_id": "claim_001",
        "claim_text": "",
        "importance": "required|optional",
        "required_evidence_refs": ["ev_001"]
      }
    ],
    "candidate_evidence": [
      {
        "evidence_ref": "ev_001",
        "page": 0,
        "section": "",
        "paragraph_id": "",
        "evidence_text": "",
        "relevance": 2
      }
    ],
    "forbidden_claims": [],
    "expected_knowledge_points": [],
    "requires_multiple_evidence": false,
    "requires_alias": false,
    "review_status": "candidate",
    "generation_notes": ""
  }
]

【本次生成要求】
- 生成 12 个候选问题。
- 其中至少 2 个 comparison。
- 至少 2 个 procedure 或 application。
- 至少 2 个 cross_section。
- 最多 2 个 unanswerable。
- 不要让多个问题只是表述稍有不同。

【课程原文】
在这里粘贴带页码、章节和段落编号的原文。
```

---

## 17. 用网页版 GPT 生成知识点候选的提示词

```text
你是一名课程知识点标注助手。我要根据给定课程原文生成知识点候选，用于评测知识点抽取系统。你的输出只作为候选，必须经过人工审核后才能成为 Gold。

【知识点定义】
知识点应是具有可讲授性、可解释性或可测量性的课程概念、原理、方法、步骤、公式或典型应用。不要把普通名词、文档标题、无意义短语或过于宽泛的章节名直接当作知识点。

【严格要求】
1. 只能依据给定原文。
2. 每个知识点必须绑定逐字复制的原文证据。
3. 不要创建原文没有明确支持的概念。
4. 合并同义表达，并将其他表达放入 aliases。
5. 不要求抽取先修、因果或一般相关关系。
6. 可以给出可选父知识点，但不确定时必须为 null。
7. 标记知识点在证据中的内容角色。
8. 避免知识点过宽或过窄。
9. 输出合法 JSON 数组，不输出额外解释。

【内容角色】
definition
principle
procedure
example
comparison
formula
application
limitation
exercise
summary

【输出 Schema】
[
  {
    "candidate_id": "kp_cand_001",
    "canonical_name": "",
    "aliases": [],
    "summary": "",
    "parent_candidate_name": null,
    "importance": "core",
    "granularity": "atomic",
    "candidate_evidence": [
      {
        "page": 0,
        "section": "",
        "paragraph_id": "",
        "evidence_text": "",
        "role": "definition",
        "is_primary": true
      }
    ],
    "review_status": "candidate",
    "generation_notes": ""
  }
]

【本次任务】
- 尽量覆盖原文中的核心和支撑知识点。
- 不追求数量，优先保证语义合理。
- 明确指出疑似重复或粒度不确定的候选。
- 原文中没有父子层级依据时，不要强行创建。

【课程原文】
在这里粘贴带页码、章节和段落编号的原文。
```

---

## 18. 候选审核 Checklist

## 18.1 Retrieval Query Checklist

```text
[ ] 问题符合真实检索语言
[ ] 仅依赖给定语料
[ ] answerable 标记正确
[ ] Gold Evidence 能充分支撑
[ ] 页码、章节、段落编号正确
[ ] 证据为原文逐字内容
[ ] 已记录所有必要证据
[ ] 不与已有 Query 重复
[ ] 不只是标题改写
[ ] 难度标记合理
[ ] 类型标记合理
[ ] 不可回答问题确实无答案
```

## 18.2 Knowledge Point Checklist

```text
[ ] 具有教学意义
[ ] 名称规范
[ ] 粒度合理
[ ] Alias 为真实同义表达
[ ] Summary 不引入外部知识
[ ] Evidence 直接支持
[ ] 内容角色正确
[ ] 与已有 Gold 不重复
[ ] Parent 有明确依据或为空
[ ] Importance 合理
```

---



## 18.3 QA Gold 与系统回答 Checklist

```text
[ ] Gold Answer Type 正确
[ ] Required Gold Claims 完整
[ ] Optional Claims 未被误标为必需
[ ] 每个 Gold Claim 有直接支持 Evidence
[ ] Forbidden Claims 确实与资料冲突或不受支持
[ ] 系统 Claims 已拆分为单一事实
[ ] correct_supported 的引用确实支持 Claim
[ ] unsupported 和 contradictory 标记正确
[ ] missed_gold_claim_ids 完整
[ ] Answer Status 判断正确
[ ] Conciseness 判断遵循统一规则
```

## 19. 基线系统定义

为保证结果可解释，基线分为“当前系统基线”和“逐步增强基线”。

## 19.1 B0：当前系统基线

尽量保持当前仓库行为：

- PDF 按页原生文本提取；
- DOCX 当前解析路径；
- 固定字符 Chunk；
- 当前 Overlap；
- 当前知识点抽取方式；
- 当前 API Embedding；
- Dense Top-K；
- 无 BM25；
- 无 RRF；
- 无 Reranker；
- 无 Query Processing；
- 无稳定 Evidence；
- 无 OCR。

B0 需要冻结代码 Commit、环境配置和模型信息。

当前旧评测数据若由 Top-K 结果反推 Gold，只能用于调试，不进入正式基线报告。

## 19.2 逐步增强基线

| 编号 | 新增能力 | 主要回答的问题 |
|---|---|---|
| B0 | 当前实现 | 当前真实起点 |
| B1 | 结构化解析 + OCR | 上游文本质量改善多少 |
| B2 | Evidence + 层级 Chunk | 语义完整性和可引用性改善多少 |
| B3 | 知识点持久化与元信息 | 知识点检索和过滤是否改善 |
| B4 | BM25 + Dense + RRF | 混合召回是否改善 |
| B5 | API Reranker | 排序质量是否改善 |
| B6 | 基础 Query Processing | 标准化、链接、过滤、扩展的收益 |
| B7 | Router + 可选多查询改写 + 低召回重试 | 复杂 Query 的收益和代价 |
| B8 | Context Packing | Agent 最终上下文质量 |

### 基础 Query Processing

B6 默认包含：

- 标准化；
- Knowledge Point Linking；
- Filter Parsing；
- Alias Expansion。

### 高级 Query Processing

B7 包含：

- Router；
- 可选 Multi-query Rewrite；
- Low-recall Retry。

---



## 19.3 QA 基线轨道

由于当前仓库没有独立 QA API，QA 采用单独但共享 Retrieval 数据的基线轨道：

| 编号 | 配置 | 作用 |
|---|---|---|
| Q0 | B0 Dense Top-K + 原样拼接 + 固定 QA Prompt，无拒答 | 最小 QA 起点 |
| Q1 | B5 Hybrid + Reranker + 固定 Context + 引用 Prompt | 检索增强后的 QA |
| Q2 | B8 Context Packing + Claim-Evidence 结构化输出 | 正式基础引用 QA |
| Q3 | Q2 + Evidence Sufficiency + 拒答阈值 | 最终 MVP 配置 |

Q0—Q3 使用同一生成模型、温度和最大输出 Token。检索和 Context 的变化必须通过 Run Manifest 记录。

## 20. 消融实验矩阵

## 20.1 Parser / OCR

固定 Retriever，比较：

- 当前 Parser；
- 结构化 Parser；
- 结构化 Parser + OCR；
- 结构化 Parser + OCR + 噪声处理；
- 结构化 Parser + OCR + 跨页合并。

报告解析指标和 Retrieval 指标，验证上游改善是否传递到检索。

## 20.2 Chunk

固定 Parser 和 Retriever，比较：

- 固定字符；
- 段落切分；
- Section-aware；
- Parent-Child；
- Parent-Child + Neighbor Expansion。

## 20.3 Knowledge Point Metadata

比较：

- 不使用知识点；
- 仅知识点名称；
- 名称 + Alias；
- 名称 + Alias + 内容角色；
- 只使用自动发布知识点；
- 只使用 `approved` 知识点；
- 自动发布 + `approved`。

## 20.4 Retrieval

比较：

- Dense；
- Sparse；
- Dense + Sparse RRF；
- Dense + Sparse 加权融合；
- Hybrid + Reranker。

## 20.5 Query Processing

比较：

- 全关闭；
- 仅 Normalize；
- + KP Linking；
- + Filter Parsing；
- + Alias Expansion；
- + Router；
- + Multi-query；
- + Low-recall Retry。

## 20.6 Context Packing

比较：

- Top-K 原样拼接；
- 去重；
- Parent Expansion；
- Neighbor Expansion；
- Token Budget Packing；
- Role-aware Packing。

---



## 20.7 基础引用 QA

固定 Test Query 与生成模型，比较：

- Raw Top-K + 普通 Prompt；
- Context Packing；
- 结构化 Claim 输出；
- Claim-Evidence 强制绑定；
- Evidence Sufficiency Check；
- 拒答阈值；
- 不同最大回答长度。

报告答案、Claim、引用、拒答、延迟和成本指标，不只报告整体成功率。

## 21. 实验控制

每次对比必须尽可能固定：

- 语料版本；
- Dev/Test Split；
- Gold Dataset 版本；
- Embedding Provider 与模型；
- Reranker Provider、Endpoint 类型、模型、截断配置与 Fallback Policy；
- Top-K；
- Candidate-K；
- Rerank Top-N；
- Query Processing 配置；
- 随机种子；
- API 温度；
- 缓存策略；
- 并发数；
- 超时和重试策略。

如果某一实验必须改变多个因素，应明确标记为“集成版本比较”，不能将全部提升归因于单一模块。

---

## 22. 基线运行流程

```text
1. 验证语料 Hash
2. 验证 Gold Dataset Schema
3. 冻结代码 Commit 和环境配置
4. 清理或隔离实验索引
5. 运行解析与 OCR
6. 运行知识点抽取
7. 构建索引
8. 运行 Query Processing 单元测试
9. 运行 Retrieval Dev
10. 运行 QA Dev 与拒答阈值校准
11. 调整 Dev 参数
12. 冻结最终配置
13. 运行 Retrieval + QA Test 一次
14. 完成 Test 40 条 Claim 级人工评分
15. 生成指标、错误案例和成本报告
16. 保存完整 Run Manifest
```

Test 结果产生后，如果继续调参，应创建新的数据集或实验版本，不应覆盖原 Test 报告。

---

## 23. Run Manifest

每次正式运行保存：

```yaml
run_id: rag_eval_2026_001
dataset_version: v1
split: test
git_commit: abc123
corpus_hash: ...
parser:
  name: structural_pdf_docx
  version: v2
ocr:
  provider: configured_engine
  version: v1
chunker:
  profile: parent_child_v1
knowledge_point:
  provider: env_api
  model: configured_model
  threshold: 0.75
query_processing:
  normalize: true
  link_knowledge_points: true
  extract_filters: true
  expand_aliases: true
  route_query: true
  multi_query_rewrite: false
  low_recall_retry: true
embedding:
  provider: env_api
  model: configured_embedding
reranker:
  provider: configured_rerank_provider
  endpoint_type: dedicated_rerank_api
  model: configured_reranker
  candidate_k: 30
  top_n: 8
  fallback_policy: fail_sample
retrieval:
  mode: hybrid
  candidate_k: 30
  rerank_top_n: 8
  return_top_n: 5
qa:
  provider: env_api
  model: configured_generation_model
  prompt_version: qa_prompt_v1
  max_answer_tokens: 600
  require_claim_citations: true
  allow_abstention: true
  sufficiency_threshold: dev_frozen_value
```

不得把 API Key 写入 Manifest。

---

## 24. 错误分析分类

所有失败案例至少归入以下一类：

### 解析

- 标题漏识别；
- 标题层级错误；
- 阅读顺序错误；
- 跨页合并错误；
- 表格损坏；
- 噪声残留；
- OCR 路由错误；
- OCR 识别错误。

### 知识点

- 漏抽；
- 误抽；
- 粒度过宽；
- 粒度过窄；
- 重复；
- 过度归并；
- Evidence 错绑；
- Parent 错误。

### Query Processing

- 标准化破坏术语；
- 链接错误知识点；
- Alias 扩展过宽；
- Filter 丢失；
- Router 错误；
- Rewrite 改变意图；
- 二次检索引入伪相关。

### Retrieval

- Dense 漏召回；
- Sparse 漏召回；
- 融合排序错误；
- Reranker 降级；
- Hard Negative 排名过高；
- 多证据覆盖不足；
- 过滤错误。

### QA

- Gold Claim 遗漏；
- 无证据 Claim；
- 与原文冲突；
- 引用不支持 Claim；
- 错误拒答；
- 应拒答但强行作答；
- 回答冗余；
- 结构化输出失败。

### Context / Citation

- 去重误删；
- Parent 扩展不足；
- Token 截断关键证据；
- Evidence 边界破坏；
- 引用失效；
- 页码错误。

---

## 25. 报告格式

每份正式评测报告至少包含：

1. 实验目的；
2. 语料和数据集；
3. Split；
4. Run Manifest；
5. 基线配置；
6. 总体指标；
7. 分 Query 类型指标；
8. OCR 子集指标；
9. 多证据子集指标；
10. Query Processing 消融；
11. QA 与拒答指标；
12. Claim 和引用错误分析；
13. 延迟、Token 和成本；
14. 错误案例；
15. 结论；
16. 下一步修改；
17. 可用于简历的指标候选。

---

## 26. 简历指标使用规则

可以写入简历的指标必须满足：

- 来自锁定 Test；
- 有明确基线；
- 有数据集规模；
- 有脚本和报告；
- 无 Gold 泄漏；
- 能说明配置；
- 不混淆结构通过率与内容质量；
- 不只挑选单个成功案例。

推荐写法：

```text
在 100 条人工审核课程检索集上，将 Recall@10 从 X 提升至 Y，
MRR@10 从 A 提升至 B；同时将知识库全量构建耗时从 M 降至 N。
```

或：

```text
构建 PDF/DOCX 解析、OCR、知识点和检索分层评测体系，
覆盖 40 页解析样本、15 页 OCR 转录及 100 条 Gold Query。
```

不得在实验完成前预填目标数字。

---

## 27. MVP 验收条件

### 数据集

- 语料 Hash 和版本固定；
- Pilot、Dev、Test 明确分离；
- Retrieval 正式 Query 不少于 100 条；
- Test 不少于 40 条；
- Gold Evidence 独立于 Retriever；
- 所有 Gold 绑定 Evidence Span；
- 候选与正式 Gold 状态分离；
- 所有正式 Test 样本人工审核。

### 解析与 OCR

- 至少 40 页解析 Gold，其中至少 10 页为固定 Renderer Profile 下的 DOCX 分页映射；
- 至少 15 页 OCR 人工转录；
- 能计算 OCR 路由和 CER；
- 能报告章节、页码、噪声和 Evidence 指标。

### 知识点

- 至少 20 个 Section 的 Gold；
- 能计算 Precision、Recall、F1；
- 能评估 Evidence 绑定、粒度、重复和父子关系；
- 能比较 0.75 与其他阈值；
- Gold 不直接复制系统抽取结果。

### Query Processing

- 至少 60 条单元案例；
- 每个模块可独立关闭；
- 能报告单元准确率、检索收益、延迟和成本；
- 保留原始 Query 和中间结果。

### Retrieval 与引用

- 能计算 Hit、Recall、MRR、nDCG 和 Precision；
- 能评估多 Evidence Query；
- 能报告 Context Coverage 和 Citation Resolvability；
- 能测试文档更新后的引用状态。



### 基础引用 QA

- 100 条 Retrieval Query 均具有 QA 所需字段或明确标记不适用；
- Test 40 条回答全部完成 Claim 级人工评分；
- 可计算短答案 EM/F1、Gold Claim Coverage、Correct Claim Precision、Unsupported Claim Rate；
- 可计算 Answerability F1、False Answer Rate 和 False Abstention Rate；
- 可计算 Citation Claim Support、Citation Precision / Recall；
- 可复现 Q0—Q3 至少 Q0、Q2、Q3 三组比较；
- QA 评测复用相同 Gold Evidence，不重新构造另一套检索 Gold。

### 工程

- 每次运行保存 Run Manifest；
- 可复现 B0；
- 至少完成 B0、B1、B4、B5、B6 的正式比较；
- 保存错误案例；
- Test 运行结果不被 Dev 调参覆盖。

---

## 28. 实施顺序

### Step 1：建立 Pilot

先完成小规模 Schema 和脚本，验证：

- GPT 候选输出是否可解析；
- 人工审核字段是否足够；
- Evidence Span 是否可稳定定位；
- 指标脚本是否正确。

### Step 2：冻结正式语料

确定 6 份文档及其 Hash。

### Step 3：完成解析、OCR 和知识点 Gold

优先完成上游 Gold，以支撑后续技术改造。

### Step 4：完成 Retrieval + QA Dev/Test

使用网页版 GPT 批量生成候选，人工审核为正式 100 条；同时标注 Gold Answer Type、Gold Claims、Claim-Evidence 关系和不可回答状态。

### Step 5：运行 B0

在任何重大改造前保存当前真实基线。

### Step 6：逐层改造与 Dev 消融

所有参数只在 Dev 调整。

### Step 7：冻结配置并运行 Test

生成最终报告和简历指标。

---

## 29. 当前默认结论

- 不使用 LLM-as-a-Judge；
- 使用 GPT 生成候选、人工审核为 Gold；
- Gold 绑定 Evidence，不绑定 Chunk；
- Retrieval 正式数据集为 100 条；
- Dev/Test 为 60/40；
- Pilot 不进入正式报告；
- Query Processing 单元案例为 60 条；
- 解析 Gold 为 40 页；
- OCR Gold 为 15 页；
- 知识点 Gold 覆盖 20–24 个 Section；
- 默认知识点发布阈值 0.75，但通过 Dev 校准；
- 基础引用 QA 纳入 MVP；
- QA 与 Retrieval 共用 100 条 Query、Gold Evidence 和 Dev/Test Split；
- Test 40 条回答执行 Claim 级人工评分；
- B0 必须保留当前系统行为；
- 每次实验记录数据、代码、模型和配置版本；
- QA 基线使用 Q0—Q3 独立轨道；
- 只有锁定 Test 的真实结果可以进入简历。
