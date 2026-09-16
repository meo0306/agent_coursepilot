# P18 后系统整体优化需求与实施路线基线

- Document ID: `coursepilot.p18-post-optimization-baseline.v1.1`
- Status: `fixed_working_baseline`
- Fixed date: 2026-08-27
- Last amended: 2026-08-27，补充 CourseRAG 面向 CoursePilot 长内容生成的定向优化需求和任务
- Applies to: P18 之后、下一次独立正式 Test 之前的 CoursePilot / CourseRAG 系统优化
- Source of truth: 当前仓库实现、P18 正式报告、P18 人工评审结果及既有冻结文档
- Change boundary: 本文档不修改 P18 已失败的正式 Gate 结论，不解锁或复用已消费的 P18 Test，不自动扩大 P19 范围

## 1. 文档目的

本文档把 P18 正式评测暴露的问题转化为可实施、可验收、可停止的系统优化需求，固定以下内容：

1. 系统要达到的目标状态；
2. 当前问题的因果链和优化优先级；
3. 跨组件和分产物的功能需求；
4. 实施阶段、依赖关系和退出条件；
5. Dev 调优、新 Test 冻结和正式 Gate 的边界；
6. 明确不采用的表层优化和风险较高方案。

本文档是后续拆分阶段任务、设计实现方案和制定验收计划的工作基线。具体代码修改仍须一次只执行一个批准阶段，并在实施前完成该阶段的仓库审计和文件级计划。

## 2. P18 结果基线

### 2.1 正式执行结论

P18 已完成正式 Test 执行，但正式质量 Gate 为 `failed`。已消费 Test 必须保持不可调参、不可重跑、不可由系统输出反推 Gold。

主要结果如下：

| 维度 | CP-B0 | CP-B10 | 结论 |
|---|---:|---:|---|
| Provider 成功 | 10/12 | 10/12 | 两条链路均存在生成失败 |
| 合同通过率 | 58.33% | 75.00% | 均未达到完整性要求 |
| Citation/Trace 完整 | 10/12 | 10/12 | 失败样本无可交付结果 |
| P50 延迟 | 67.935 s | 137.819 s | B10 约为 B0 的 2.03 倍 |
| P95 延迟 | 515.179 s | 737.685 s | 尾延迟严重 |
| 成本 | CNY 0.486533 | CNY 1.202527 | B10 约为 B0 的 2.47 倍 |

稳定性复跑为 5/6 Provider 成功、3/6 合同通过。20 个成功生成的文件均可打开或渲染，但四个上游生成失败导致四个预期导出缺失。

### 2.2 人工质量基线

24 个盲审单元中：

- `accepted`: 0；
- `minor`: 7；
- `major`: 13；
- `reject`: 4；
- Acceptable Rate: 29.17%，目标不低于 80%；
- Mean Rubric: 2.8884，目标不低于 4.0；
- Mean Edit Burden: 2.625，目标不高于 1.5；
- Critical-free Rate: 83.33%，目标为 100%。

分产物表现：

| 产物 | Acceptable Rate | Mean Rubric | Mean Edit Burden | 主要问题 |
|---|---:|---:|---:|---|
| Exam | 0% | 2.5875 | 3.000 | 语义重复、难度虚高、证据越界、计数/分值失败 |
| Lesson | 50% | 3.21875 | 2.125 | 事实扩写越界、活动材料不足、主题拼接 |
| PPT | 37.5% | 2.925 | 2.750 | 文本堆叠、叙事重复、字号/留白失衡、视觉支持弱 |

即使排除四个生成失败的 reject，剩余 20 个产物的 Acceptable Rate 仍只有 35%，Mean Rubric 为 3.274，Mean Edit Burden 为 2.35。因此，整体质量不佳不能归因于少数 Provider 失败。

### 2.3 系统链路基线

- L0 危险事件为零：未发生跨课程泄漏、未授权访问、Secret 泄漏、重复副作用、静默 Fallback、不可解析正式引用或危险工具执行。
- Offline Validation、Repair、Recovery、Template、Fault/Security 检查通过。
- Track B 的健康检查、Capability 合同和一条真实 PostgreSQL 写回集成通过。
- 8 条状态/副作用合同均通过，但正式 CourseRAG Test Index 缺失，7/8 live journey 被阻塞。

### 2.4 CourseRAG 现有能力与缺口基线

CourseRAG 已经完成 Hybrid Retrieval、RRF、Reranker、Query Processing、Parent/Neighbor Expansion、Context Packing、Evidence Sufficiency、Claim-Evidence QA、Verified Overlay、增量构建、引用迁移、写回、ACL 和课程隔离等基础建设。现有证据不支持推倒重做 Parser、Chunker、Embedding 或 Hybrid Retrieval：

- P08 Dev 中 Cohere Rerank 的 Recall@10 为 0.8858、MRR@10 为 0.7384、nDCG@10 为 0.8259、Complete Group Recall@8 为 0.8426；
- P10 正式 Test 中 B4 Hybrid Recall@10 为 0.9167、Complete Group Recall@8 为 0.8611；B5 Cohere 的 MRR@10 为 0.7014、nDCG@10 为 0.8006；
- P09/P10 已验证 Citation Resolvability、Claim-Citation Completeness、Unanswerable Recall 和零 False Answer 等基础可信能力。

但这些能力主要面向检索 QA，尚未完整覆盖 CoursePilot 的长内容生成：

1. P18 Track A 使用固定 `source_snapshots` 和 `p18-track-a-fixture-v1`，没有执行实时 CourseRAG 检索，因此 P18 人工质量失败不能直接归因为在线检索排序失败；
2. P18 数据构造每个知识点只选取第一个可解析 Evidence，每个任务固定组合两个知识点，证据容量与 10—30 道题、2—3 课时或 10—16 页 PPT 的要求不匹配；
3. 现有 `EvidenceSufficiencyGate` 主要检查 Evidence 存在性、可解析性、Rerank 阈值、来源数量和 OCR 置信度，不判断证据能否支持指定题量、课时、页数、认知操作或内容类型；
4. `ContextRequest` 尚未结构化表达 Artifact 类型、目标单元数、知识点覆盖、表格/公式/案例等材料要求；
5. `purpose` 尚未形成 Lesson/Exam/PPT 的差异化检索与打包策略，请求级 Packing 配置也需要核实并接通实际 Packer；
6. P09 曾观察到 Context 阶段相对上游检索的 Coverage/Complete Group Coverage 下降，说明长内容任务不能只依赖 Top-N 相关性；
7. P18 Track B 缺少可恢复的 Formal CourseRAG Index，属于系统交付和正式环境准备的直接缺口。

固定结论：CourseRAG 不进行无证据的全面重写，但必须增加“面向 CoursePilot 长内容生成”的任务型上下文能力，并与 CoursePilot 的任务可行性、补检索和停止决策形成闭环。

### 2.5 基线证据位置

- `docs/refactor/phase_reports/P18_coursepilot_system_formal_evaluation.md`
- `reports/p18/formal_test_report.json`
- `human_review/p18/formal_test/review_decisions.json`
- `storage_eval/p18/formal_test/track_a/report.json`
- `storage_eval/p18/formal_test/stability/report.json`
- `storage_eval/p18/formal_test/track_b/report.json`
- `docs/refactor/phase_reports/P08_hybrid_retrieval_rrf_reranker.md`
- `docs/refactor/phase_reports/P09_query_context_cited_qa.md`
- `docs/refactor/phase_reports/P10_incremental_writeback_security_formal_eval.md`

## 3. 目标状态

优化后的系统必须同时满足以下六类目标，不能以其中一类成功抵消另一类失败。

### 3.1 输入可行

- 系统能够判断现有证据是否足以支撑指定题量、课时数、页数、知识点覆盖和难度要求。
- 证据不足时优先补充检索，其次明确要求缩小范围或转人工，不通过重复、常识扩写或幻觉凑齐产物。
- CoursePilot 必须以结构化任务需求请求上下文；CourseRAG 必须返回任务覆盖、证据容量、完整证据组和缺口，而不是只返回相关性 Top-N。
- Lesson、Exam、PPT 使用差异化的检索与 Context Packing 策略，但共享稳定的 Evidence、Trace、课程隔离和版本合同。

### 3.2 生成可靠

- ID、题数、分值、课时、时长、页数、顺序和顶层 Schema 由应用层确定性控制。
- 单个批次失败不导致整个产物丢失；Resume 不产生重复副作用。
- 正常 Dev 样本不再出现随机顶层 JSON、计数和装配失败。

### 3.3 事实可信

- 正式事实性 Claim 不仅引用 ID 合法，而且其含义得到对应证据支持。
- 课程事实、合理推导、假设示例、讨论问题和教学组织行为具有明确类型边界。
- 无证据事实不得通过重新挂接一个合法 Evidence ID 被伪装修复。

### 3.4 教学可用

- Exam 具备全卷层面的语义多样性、真实难度层次和答案独立性。
- Lesson 的目标、活动、评价和证据相互对齐，教师无需大幅补写即可授课。
- PPT 具备教学叙事、可投影可读性、适当视觉表达和完整讲稿备注。

### 3.5 系统真实可运行

- CoursePilot 通过公开 Port/API 使用 CourseRAG，不导入其 Parser、Chunker、Index 等内部实现。
- 开发和正式评测均具备对应的真实索引、数据库和服务边界。
- 正式 Track B 必须执行真实 HTTP/Application 旅程，不能以状态查表或纯模拟替代。

### 3.6 性能经济

- 在质量和可靠性达标后，再降低请求数、Token、延迟和成本。
- 新增节点必须证明边际收益；高 reasoning、长上下文和内容 Repair 不能作为默认兜底。

## 4. 总体因果模型与优化原则

系统整体可用性按乘法链理解：

```text
整体可用性
≈ 输入可行性
× 结构可靠性
× 语义可信度
× 教学质量
× 导出/视觉质量
× 端到端可运行性
```

因此固定以下优化原则：

1. 先修复乘法链前部的可行性、结构和 Grounding，再优化文风、视觉、模型和性能。
2. 确定性程序拥有结构，LLM 只填充受约束的语义字段。
3. 引用合法不等于语义受支持；两者必须分别验证。
4. 薄证据可以产生丰富的教学组织，不能产生额外课程事实。
5. 严重全局冲突应回到 Blueprint/Batch 重规划，不能只做逐字段局部 Repair。
6. Dev 可使用候选辅助分析，但正式评测禁止 LLM-as-a-Judge、静默 Fallback 和 Test 调参。
7. 自动合同、人工质量和真实系统旅程是三个独立 Gate。
8. 只有质量达标后，Profile、延迟和成本优化才具有业务意义。

### 4.1 CoursePilot / CourseRAG 责任边界

| 问题 | CoursePilot 责任 | CourseRAG 责任 | 固定归属 |
|---|---|---|---|
| JSON、Schema、计数、分值、页数、装配 | 结构所有权、校验、失败隔离 | 无直接责任 | CoursePilot 主责 |
| Exam 重复和难度虚高 | 全卷语义规划、认知操作、冲突修复 | 提供足够且多样的证据 | CoursePilot 主责，CourseRAG 影响上限 |
| Lesson/PPT 事实越界 | Claim 类型、生成约束、Grounding Validator | 返回完整 Evidence/Span 和 Adequacy | CoursePilot 主责，双方共同防线 |
| 任务证据不足 | 定义任务需求、判断可行性、缩范围/停止 | 检索补充材料、报告覆盖和缺口 | 双方共同责任 |
| 检索相关性与完整证据组 | 不绕过 Port 或直接访问索引 | Query、Retrieval、Expansion、Packing | CourseRAG 主责 |
| Track B 缺少正式索引 | 绑定并消费正式身份 | 构建、恢复、发布和探测索引 | CourseRAG/系统集成主责 |
| 教学目标、活动、视觉表达 | 产物规划与人工质量 | 不替代教学设计 | CoursePilot 主责 |

CourseRAG 不负责决定“30 道题在教学上是否合理”，CoursePilot 不负责直接操作 Chunk、Embedding 或 Index。双方通过版本化公开合同交换任务需求、Context、Adequacy、Evidence 和 Trace。

## 5. 固定需求

### 5.1 OPT-FEAS：任务可行性与证据容量

#### OPT-FEAS-001 语义容量建模

生成前必须从批准上下文中识别可用语义单元，包括：

- 独立事实；
- 定义和边界；
- 条件、因果和比较关系；
- 过程步骤；
- 示例和反例；
- 表格、公式和数值；
- 可以支持应用或分析任务的情境材料。

不得仅使用字符数作为最终可行性判据；字符数只能作为低成本预警信号。

#### OPT-FEAS-002 任务需求容量计算

系统必须把下列要求映射为证据需求：

- 题量、题型、难度和知识点覆盖；
- 课时数、每课时核心目标和必要讲授内容；
- PPT 页数、叙事段落和视觉表达需要；
- 表格题、公式题、案例题等特殊材料要求。

#### OPT-FEAS-003 可行性状态

生成前必须返回以下显式状态之一：

- `feasible`；
- `needs_more_evidence`；
- `scope_reduction_required`；
- `needs_human_review`。

只有 `feasible` 可以无条件进入正常生成。

#### OPT-FEAS-004 证据不足处理

固定处理顺序：

1. 通过 CourseRAG Port 请求同课程、同知识点范围的补充上下文；
2. 优先补充过程、例子、表格、公式、比较维度和相邻证据；
3. 重新计算可行性；
4. 仍不足时提出补材料或缩小范围；
5. 不允许通过模型常识或重复改写强行满足数量合同。

#### OPT-FEAS-005 双向可行性闭环

CoursePilot 先生成不含课程事实的 `GenerationContextRequirements`，CourseRAG 返回 Context 和 `ContextAdequacyReport`，CoursePilot 再做最终业务可行性判断：

```text
CoursePilot TaskSpec
→ GenerationContextRequirements
→ CourseRAG Task-oriented Context Build
→ ContextPackage + ContextAdequacyReport
→ CoursePilot Feasibility Decision
→ 生成 / 补检索 / 缩范围 / 转人工
```

CourseRAG 的 `sufficient` 只表示检索和证据覆盖满足声明的 Requirements，不代表最终教学设计已合格；CoursePilot 不得忽略 `missing_requirements` 强行进入生成。

### 5.2 OPT-RAG：面向长内容生成的 CourseRAG 定向优化

#### OPT-RAG-001 版本化任务型上下文合同

在不破坏现有 `ContextRequest` 的前提下，通过加法字段或新版本合同增加 `GenerationContextRequirements`。至少表达：

- `artifact_type`：`lesson` / `exam` / `ppt`；
- `knowledge_point_ids` 和每个知识点的最低覆盖；
- `target_unit_count`：题目、课时或内容页数量；
- `required_content_roles`：定义、原理、过程、比较、应用、例子等；
- `required_modalities`：表格、公式、数值、案例、图示关系等；
- `minimum_distinct_sources` 和 `minimum_semantic_units`；
- Context Token/Item 预算及是否允许补充轮次；
- 课程、索引、Overlay 和 Evidence Tier 边界。

合同中不得包含由 Test 输出反推的 Gold 特征，也不得要求 CourseRAG 了解 CoursePilot 内部 Blueprint 类型。

#### OPT-RAG-002 Context Adequacy Report

CourseRAG 必须随任务型 Context 返回可审计的充分性报告，至少包含：

- 知识点覆盖和缺失知识点；
- 独立 Evidence、Source 和 Complete Evidence Group 数量；
- 事实、定义、关系、过程、比较、例子、公式、表格、数值等语义单元分布；
- `selected`、`discarded_for_budget`、`discarded_for_item_limit` 和缺失 Evidence；
- 必要 Parent/Neighbor 是否完整；
- 各 Requirement 是否满足；
- `adequate`、`needs_more_evidence` 或 `unresolvable` 状态；
- `missing_requirements` 和可执行的补检索建议。

Adequacy 必须基于 Evidence 和确定性统计；正式 Gate 不使用 LLM-as-a-Judge 判定证据是否充分。

#### OPT-RAG-003 Purpose-aware Query Plan

CourseRAG 必须根据公开的 `artifact_type`、内容角色和知识点生成可审计的查询计划：

- Exam：按知识点、事实单元、认知操作材料和题型刺激材料检索；
- Lesson：按核心概念、过程、例子/反例、教学案例和边界检索；
- PPT：优先检索可视觉化的比较、过程、层级、表格、数值和案例；
- 每个子查询保留 Query Trace、过滤条件、命中和预算使用；
- 子查询必须受课程、索引版本、知识点和 Source Tier 约束。

任务型 Query Plan 可以由确定性规则和已批准 Router 生成，不得静默切换外部搜索或未批准 Provider。

#### OPT-RAG-004 Coverage-first Retrieval

长内容生成不能只优化单一 Top-N 相关性。检索和选择必须同时考虑：

- Query relevance；
- 知识点覆盖；
- 语义单元多样性；
- Complete Evidence Group 完整性；
- Source/Section 多样性；
- 硬负例隔离；
- Evidence Tier 和教师审核状态；
- Token Budget。

应为每个必需知识点和内容角色保留最低预算，避免单一高分知识点占满 Context。是否采用 MMR、分桶、约束选择或其他算法由实现阶段比较决定，不在本文档预先指定。

#### OPT-RAG-005 完整 Evidence Group 与必要邻接

- 表格不得只返回标题或局部行而丢失解题所需列和值；
- 公式必须保留符号定义、边界和必要上下文；
- 过程必须保留关键步骤及顺序；
- 指代、跨页句和截断段落必须带必要 Parent/Neighbor；
- `necessary_neighbors` 必须进入实际 Context 或明确报告未能装入，不能只存在于评测元数据；
- Evidence Boundary、Source Span 和 Content Hash 必须保持可追溯。

#### OPT-RAG-006 请求级 Packing 与预算接通

- 核实并接通 `ContextRequest.packing` 到实际 `ContextPacker`；
- Lesson/Exam/PPT 可使用不同但显式配置的 Packing Profile；
- 请求级预算不能越过服务端硬上限；
- 对被预算丢弃的必需 Evidence 发出结构化缺口，而不是普通 Warning 后继续宣称 adequate；
- 不通过无条件增大 4,000 Token 或 Top-K 解决覆盖问题。

#### OPT-RAG-007 补检索协议与停止规则

- CoursePilot 可以依据 `missing_requirements` 发起有界补检索；
- 每次补检索必须携带上一 Context 身份、已覆盖单元和尚缺单元；
- CourseRAG 必须去重并保留完整 Trace；
- 补检索轮次、Token、请求和成本必须预设上限；
- 达到上限仍不足时返回 `needs_more_evidence` 或 `unresolvable`，不得循环检索或静默降级。

#### OPT-RAG-008 CourseRAG 定向评测

在新的 Dev 数据上增加下游任务导向指标：

- Task Evidence Coverage；
- Complete Evidence Group Coverage；
- Knowledge Point Minimum Coverage；
- Required Modality Coverage；
- Distinct Semantic Unit Count；
- Context Budget Loss Rate；
- Adequacy Decision Precision/Recall；
- 补检索后的增量覆盖及重复率；
- Context Adequacy 与下游人工质量的关联。

Recall/MRR/nDCG 继续作为检索指标，但不能单独证明 Context 足以生成合格教学产物。只有新 Dev 证明检索相关性或排序仍是瓶颈时，才启动 Embedding、RRF、Reranker 或阈值调整。

#### OPT-RAG-009 兼容与架构边界

- CoursePilot 只依赖 CourseRAG Port/API 和公共 Contract；
- CoursePilot 不导入 Parser、Chunker、Embedding、RRF、Reranker 或数据库实现；
- PostgreSQL 继续作为业务事实源，Index/Cache/Trace 不能成为唯一数据源；
- 现有 Search/Context/QA v1 调用保持兼容；
- 新任务型能力默认通过版本化或显式 Capability 暴露；
- 不因本优化重做已有 Parser/OCR/Chunk/Evidence 身份，除非新的 Dev 证据证明其为阻塞根因。

### 5.3 OPT-STRUCT：确定性结构与有界生成

#### OPT-STRUCT-001 应用层结构所有权

应用层必须拥有并锁定：

- Artifact/Session/Slide/Slot/Question ID；
- 题数、题型数、单题分值和总分；
- 课时数、课时顺序和分钟数；
- PPT 页数、页序、Title/References 页位置；
- 知识点和 Evidence 白名单；
- 顶层对象封装、批次顺序和最终装配。

LLM 不得自由增加、删除或重排上述结构。

#### OPT-STRUCT-002 小批次生成

- Exam 默认按 2—5 个 Slot 的小批次生成；
- Lesson 按单课时生成；
- PPT 按单页或同一叙事段的小批次生成；
- 每批独立进行 Schema 验证和 Checkpoint；
- 最终 Artifact 由应用层确定性装配。

#### OPT-STRUCT-003 失败隔离与 Resume

- 单批失败不能抹除已完成批次；
- 重试只能针对失败批次或明确冲突目标；
- Resume 必须验证输入 Fingerprint 和已完成状态；
- 导出、写回和 Resume 保持幂等。

#### OPT-STRUCT-004 修复类型隔离

修复必须分为：

1. JSON/Schema 修复；
2. 确定性结构修复；
3. 内容再生成。

JSON 修复不得改写业务语义；确定性修复不得制造事实；内容再生成不得改变锁定身份和结构合同。

### 5.4 OPT-GROUND：Claim-level Grounding

#### OPT-GROUND-001 Claim 类型

内容中的关键陈述必须能够区分：

- `evidence_fact`：证据直接支持的事实；
- `derived_conclusion`：由证据在明确条件下推导的结论；
- `instructional_action`：教师或学生的教学活动；
- `hypothetical_example`：明确标记的假设示例；
- `discussion_prompt`：开放讨论问题；
- `caution_or_limitation`：边界、限制或不确定性说明。

#### OPT-GROUND-002 支持关系

对正式事实性 Claim，至少保留：

- Claim 内容或稳定身份；
- Claim 类型；
- Evidence ID；
- 支持关系类型；
- 可定位的 Source Span 或短 Support Summary。

#### OPT-GROUND-003 分层语义校验

- 数值、公式、专名、实体和枚举执行确定性一致性校验；
- 核心术语检查是否来自证据或批准词表；
- 关系和结论检查是否存在相应支持；
- 无支持事实标记为 `unsupported`；
- 假设和讨论必须有显式语言标记，不得写成课程定论。

#### OPT-GROUND-004 无支持 Claim 的修复规则

只允许：

- 删除；
- 收窄为证据可支持的结论；
- 降级为假设或讨论；
- 请求补充证据；
- 转人工审查。

禁止仅替换或追加合法 Evidence ID 后保留原无支持内容。

### 5.5 OPT-EXAM：全卷语义规划

#### OPT-EXAM-001 语义 Slot 分配

每个题目 Slot 必须绑定：

- 独立语义单元；
- 认知操作；
- 预期答案依据；
- 所需刺激材料；
- 已使用和禁止复用的事实/答案 Signature。

Slot ordinal、题号或字符串后缀不得作为语义唯一性的证明。

#### OPT-EXAM-002 认知操作与难度

难度必须由可观察设计组成，例如：

- 信息组合数量；
- 推理步数；
- 是否包含干扰信息；
- 是否迁移到新情境；
- 是否要求比较、应用、诊断或解释；
- 是否使用表格、公式或数值。

不得只依赖模型输出的 `easy/medium/hard` 标签。

#### OPT-EXAM-003 全卷冲突图

全局校验至少覆盖：

- 语义重复；
- Assessment Target 重叠；
- 答案 Signature 重复；
- 题干或解析泄露其他题答案；
- 伪多选题；
- 所需刺激材料缺失；
- 难度标签与认知操作不匹配。

#### OPT-EXAM-004 冲突修复层级

- 局部措辞问题可进行单题 Repair；
- 多题共享同一语义单元时必须回到 Batch 或 Blueprint 重规划；
- 证据容量不足时必须回到 OPT-FEAS，不得循环改写题干。

### 5.6 OPT-LESSON：教案事实与教学设计分层

#### OPT-LESSON-001 事实内容层

每课时明确：

- 必须讲清的核心概念；
- 对应证据；
- 允许使用的案例；
- 事实边界和不确定性。

#### OPT-LESSON-002 教学组织层

每课时可包含：

- 导入问题；
- 教师活动和学生活动；
- 具体材料、步骤和预期产出；
- 形成性评价；
- 作业和延伸讨论。

教学组织可以丰富，但不能引入未经支持的课程事实。

#### OPT-LESSON-003 可测量目标

教学目标至少包含学习者行为、对象、条件和可观察标准。不得以字符串长度代替可测量性判断。

#### OPT-LESSON-004 目标—活动—评价对齐

每个核心目标必须至少有一个教学活动和一个评价方式；活动所需材料必须真实存在或明确为教师待补充材料。

### 5.7 OPT-PPT：教学叙事和视觉语义

#### OPT-PPT-001 叙事架构

PPT Architecture 应从已审核教案和证据形成页面角色，不得按少数 Evidence 轮转凑页。允许的典型角色包括：

- 导入；
- 目标；
- 核心概念；
- 例子/反例；
- 比较/过程；
- 课堂活动；
- 理解检查；
- 小结；
- 参考资料。

#### OPT-PPT-002 视觉类型映射

- 比较内容优先使用表格、矩阵或并列卡片；
- 过程内容优先使用流程图；
- 层级内容优先使用树或分层结构；
- 数值内容优先使用图表；
- 因果内容优先使用明确关系图；
- 教学任务优先使用步骤卡和操作区。

视觉表达不得制造证据之外的新事实。

#### OPT-PPT-003 渲染质量校验

除溢出和越界外，至少检查：

- 最小字号；
- 文本密度；
- 过度留白；
- 标题语义重复；
- 连续页面版式重复；
- 图文比例；
- 投影可读性；
- 内容页 Speaker Notes 完整性；
- 表格、图形和文本的可编辑性。

#### OPT-PPT-004 内容压缩优先

证据不足以支持指定页数时，优先合并和减少页面，或请求补证据；禁止把同一事实拆成多页重复表达。

### 5.8 OPT-TRACKB：真实索引和真实系统旅程

#### OPT-TRACKB-001 Dev 实索引

开发优化早期必须具备可重复使用的 CourseRAG Dev Index，并支持指定课程的真实检索和上下文构建。

#### OPT-TRACKB-002 正式索引身份

下一次正式评测必须固定并验证：

- Formal Index Artifact/Version；
- 对应课程范围；
- 数据库迁移和初始数据；
- 可重复恢复或构建流程；
- Preflight 实际查询结果。

#### OPT-TRACKB-003 真实 Journey

正式 Track B Journey 必须调用真实 HTTP/Application 边界并核对：

- 服务响应；
- 任务/Artifact 状态；
- 数据库持久化；
- CourseRAG 检索或写回结果；
- 重试和 Resume；
- 副作用幂等性。

纯状态查表或预置 `_ACTION_STATES` 只允许作为 Unit/Contract Test，不能计为 live journey。

### 5.9 OPT-PROFILE：模型、延迟和成本优化

#### OPT-PROFILE-001 优化前置条件

只有 OPT-FEAS、OPT-STRUCT 和 OPT-GROUND 达到 Dev 退出条件后，才进入正式 Profile 对比。

#### OPT-PROFILE-002 增量消融

固定比较顺序：

```text
B0
→ B0 + 确定性结构
→ + 可行性/证据补充
→ + 任务级规划
→ + 语义校验
→ + 有界 Repair
```

每一层只有在人工质量或可靠性有可解释收益、且成本/延迟增幅可接受时保留。

#### OPT-PROFILE-003 节点级配置

- 不为简单分类、装配或格式校验默认启用高 reasoning；
- 不为所有节点使用同一超时和最大输出长度；
- 不假设 `main`/`light` 标签代表不同物理模型；
- Provider、模型和 Capability 必须通过配置与 Adapter 绑定；
- 不允许静默模型切换或正式评测 Fallback。

#### OPT-PROFILE-004 性能优化顺序

1. 删除无价值调用；
2. 缩小上下文和输出 Schema；
3. 减小批次；
4. 复用确定性规划和已完成 Checkpoint；
5. 仅重试失败批次；
6. 降低低复杂度节点 reasoning；
7. 最后再考虑更换模型。

### 5.10 OPT-EVAL：开发评测和新正式 Test

#### OPT-EVAL-001 旧 Test 隔离

- P18 Test 保持已消费和只读；
- 不按旧 Test 个案修补 Prompt、规则或输出；
- 可以使用失败类别和公开系统限制设计新的 Dev 切片；
- 不得复用旧 Test Gold 作为新 Dev Gold。

#### OPT-EVAL-002 新 Dev 切片

至少覆盖：

- 薄、中、丰富三档证据容量；
- 单知识点和多知识点；
- 相邻主题和不相邻主题；
- 定义、比较、过程、公式、表格、数值、案例；
- 不同题量、课时数和页数；
- Provider/schema/fault/resume 失败模式。

#### OPT-EVAL-003 人工 Dev 反馈

- 每个有界校准窗口进行小规模盲审；
- 三类产物分别报告，不使用总平均掩盖某一产物失败；
- 记录 Reviewer ID、时间和审查版本；
- 至少 20% 样本执行重复盲审或一致性检查；
- Edit Burden 统一使用冻结定义的 0—4 量表。

#### OPT-EVAL-004 三类独立 Gate

1. 自动技术 Gate；
2. 人工质量 Gate；
3. 真实系统 Gate。

任何一类失败都必须如实报告；不得把人工 Gate 失败降格为不阻塞的普通质量债务。

#### OPT-EVAL-005 新正式 Test

只有所有 Dev 退出条件通过后，才允许：

1. 冻结新代码、Prompt、Profile、配置、索引和数据身份；
2. 由人工批准新 Gold 和 Rubric；
3. 锁定独立 Test；
4. 进行一次正式运行；
5. 失败后停止该候选，不在 Test 上继续调参。

## 6. 实施阶段与依赖顺序

```text
OPT-0 新 Dev 边界
    ↓
OPT-1 CoursePilot 任务可行性与需求建模
    ↓
OPT-RAG CourseRAG 任务型上下文与 Adequacy ─┐
    ↓                                      │
OPT-2 确定性结构与失败隔离                 │
    ↓                                      │
OPT-3 Claim-level Grounding                │
    ↓                                      │
OPT-4 Exam 专项质量                        │
    ↓                                      │
OPT-5 Lesson 专项质量                      │
    ↓                                      │
OPT-6 PPT 叙事与视觉质量                   │
    ↓                                      │
OPT-7 真实 Track B ← Dev/Formal Index ─────┘
    ↓
OPT-8 Profile/性能消融
    ↓
OPT-9 新候选冻结与独立 Test
```

### OPT-0：建立下一轮 Dev 边界

交付：

- 新 Dev 数据计划；
- 旧 Test 禁用声明；
- 三类 Gate 定义；
- 人工 Dev 评审流程；
- 失败分类和当前 Baseline。

退出条件：开发不读取 P18 Test Gold 或具体盲审映射进行调参。

### OPT-1：CoursePilot 任务可行性和需求建模

交付：

- 可行性领域模型；
- 语义容量提取；
- 任务容量判断；
- `GenerationContextRequirements` 消费侧模型；
- `ContextAdequacyReport` 消费和决策逻辑；
- 缩范围/转人工状态。

退出条件：所有 Dev 任务生成前具有明确需求和可行性结论；CoursePilot 能正确处理 `adequate`、`needs_more_evidence` 和 `unresolvable`；不可行任务不进入普通生成。

### OPT-RAG：CourseRAG 任务型上下文供给

交付：

- 版本化 `GenerationContextRequirements` / `ContextAdequacyReport` 公共合同；
- Purpose-aware Query Plan 和逐知识点/内容角色检索；
- Coverage-first Context Selection；
- Complete Evidence Group、Parent/Neighbor 和 Source Span 保留；
- 请求级 Packing/Profile 接通；
- 有界补检索协议和停止规则；
- CourseRAG 任务型 Dev 指标、报告和专项测试；
- CoursePilot Remote/Local/Mock Adapter 合同一致性。

代表性任务：

| Task ID | 任务 | 最小验证 |
|---|---|---|
| OPT-RAG-T01 | 定义加法合同和 Capability | Schema/Port/Remote/Local/Mock Contract Test |
| OPT-RAG-T02 | 实现 Adequacy 统计和缺口分类 | Unit Test，覆盖薄/中/丰富 Evidence |
| OPT-RAG-T03 | 实现 Purpose-aware Query Plan | Unit/Contract Test，覆盖 Lesson/Exam/PPT |
| OPT-RAG-T04 | 实现 Coverage-first Selection | Unit Test，验证每 KP/Role 最低覆盖和去重 |
| OPT-RAG-T05 | 保留完整表格、公式、过程和必要邻接 | Evidence Group Integration Test |
| OPT-RAG-T06 | 接通请求级 Packing 和服务端硬上限 | API/Service Integration Test |
| OPT-RAG-T07 | 实现有界补检索、Trace 和停止规则 | Integration Test，验证无循环和无静默降级 |
| OPT-RAG-T08 | 构建 CourseRAG 长内容生成 Dev Eval | Approved-Dev-only Evaluation，旧 P18 Test 不可读 |
| OPT-RAG-T09 | 打通 CoursePilot 消费闭环 | Lesson/Exam/PPT 各一条真实 Context Smoke |

退出条件：

- 三类 Artifact 的 Dev 请求均能返回可解释 Adequacy；
- 必需知识点和材料类型覆盖满足冻结的 Dev 要求；
- 表格、公式、过程和必要邻接不被静默截断；
- 补检索达到上限后正确停止；
- CoursePilot 在不足时不会进入普通生成；
- 现有 Search/Context/QA v1 和安全边界无回归。

### OPT-2：结构可靠性

交付：

- 确定性 Blueprint 和装配；
- 小批生成；
- Checkpoint/Resume；
- 三类 Repair 隔离；
- 结构专项测试。

退出条件：Dev 题数、分值、课时、页数和顶层 Schema 合同达到 100%；连续稳定性运行无结构随机失败。

### OPT-3：语义可信度

交付：

- Claim 类型和支持关系；
- 分层 Grounding Validator；
- 无支持 Claim 的安全 Repair；
- 人工抽检工具或 Review Package 增强。

退出条件：人工评审不再普遍出现“引用合法但正文越界”；关键事实均可定位支持。

### OPT-4：Exam 专项质量

交付：

- 语义单元池；
- 认知操作和难度模型；
- 全卷冲突图；
- Blueprint/Batch 层再规划；
- 答案线索和伪多选检查。

退出条件：Exam Dev 达到人工质量目标，且全卷结构合同保持 100%。

### OPT-5：Lesson 专项质量

交付：

- 事实层/教学层分离；
- 可测量目标；
- 目标—活动—评价映射；
- 活动材料和证据边界检查。

退出条件：Lesson Dev 达到人工质量目标，不再需要成段删除无支持事实。

### OPT-6：PPT 专项质量

交付：

- 基于已审核 Lesson 的叙事架构；
- 页面角色和视觉类型映射；
- 字号、密度、留白、重复和可读性 QA；
- 可编辑视觉元素和完整 Notes。

退出条件：PPT Dev 达到人工质量目标，渲染后无需整体重排。

### OPT-7：真实系统闭环

交付：

- 可恢复 Dev Index；
- Formal Index 构建/恢复候选；
- 索引内容、课程范围、Profile 和数据库身份绑定；
- 从干净环境完成恢复、发布和指定课程 Probe；
- 真实 HTTP Journey Runner；
- 数据库和副作用核验。

退出条件：Dev 环境 8/8 代表性 Journey 实际通过；不存在 `blocked_missing_formal_index`。

### OPT-8：Profile、延迟和成本

交付：

- 节点级消融报告；
- 候选 Profile；
- 请求、Token、P50/P95 和成本报告；
- 回归保护结论。

退出条件：候选 Profile 不降低自动、人工或系统 Gate，且满足批准的性能预算。

### OPT-9：新正式候选

交付：

- 新 Frozen Manifest；
- 新独立 Test Lock；
- 正式 Track A/Track B/人工评审；
- 单一最终 Gate 结论。

退出条件：自动技术、人工质量和真实系统三类 Gate 同时通过。

## 7. 固定验收矩阵

### 7.1 L0 安全与可信边界

以下事件容忍度保持为零：

- 跨课程数据泄漏；
- 未授权访问或写回；
- Secret 泄漏；
- 重复导出、写回、发布或 Resume 副作用；
- 静默 Provider、模型、索引或 Fallback 切换；
- 正式事实性 Claim 无 Evidence；
- 不可解析的正式引用；
- Test Gold 泄漏或 Test 调参；
- 未授权危险工具执行。

### 7.2 CourseRAG 任务型上下文 Gate

对所有被判定为 `adequate` 的正式候选 Context：

- Context/Evidence Schema 和可解析率：100%；
- Required Knowledge Point Coverage：100%；
- Required Modality Coverage：100%；
- 必需 Complete Evidence Group 完整率：100%；
- Course/Index/Overlay/Evidence Tier 绑定正确率：100%；
- 必需 Evidence 被预算丢弃但仍返回 `adequate`：0；
- 人工批准的明确不可行 Dev 样本被误判为 `adequate`：0；
- 补检索超过预注册轮次、Token、请求或成本上限：0；
- 静默外部搜索、Provider、Index、Profile 或 Fallback 切换：0。

Recall/MRR/nDCG、Task Evidence Coverage、Distinct Semantic Unit Count 和 Context Budget Loss Rate 分别作为检索质量与诊断指标；具体 L1 阈值必须在 OPT-RAG Dev 正式运行前根据新数据范围预注册，不得在结果产生后放宽。既有检索指标的回归按 `QUALITY_GATE_POLICY.md` 的 L2 规则处理。

### 7.3 自动技术 Gate

下一次正式候选至少满足：

- 预期 Artifact 生成完整率：100%；
- Schema/Contract 通过率：100%；
- 预期导出和打开/渲染完整率：100%；
- Citation/Trace 完整率：100%；
- 固定稳定性重复中 Provider 和合同失败为 0；
- 真实 Track B Journey：8/8 通过。

### 7.4 人工质量 Gate

总计和 Lesson/Exam/PPT 各自至少满足：

- Acceptable Rate：不低于 80%；
- Mean Rubric：不低于 4.0；
- Mean Edit Burden：不高于 1.5；
- Critical Defect：0；
- 人工评审完备率：100%。

任何单一产物类型失败，不得由其他类型的高分补偿。

### 7.5 性能和成本

- 性能和成本阈值必须在正式运行前预注册；
- P95 或单位成本相对已批准候选增加超过 20% 时必须解释并批准；
- 性能优化不得牺牲 L0、自动合同或人工质量；
- 质量未通过时，性能结果只作为诊断，不得作为候选成功依据。

## 8. 开发验证策略

### 8.1 最小充分测试

- 纯可行性、语义单元和规划逻辑：Unit Test；
- 公共 Port、Schema、Provider Adapter：Contract Test；
- 数据库、索引、Checkpoint、Resume：Integration Test；
- Lesson/Exam/PPT 用户工作流：代表性 E2E Smoke；
- PPT 视觉：真实渲染和人工/规则联合 QA；
- 正式收敛前：一次全量测试、Ruff、Mypy 和完整 Dev Eval。

### 8.2 Dev 人工反馈节奏

每个专项阶段完成后，对新的 Dev 样本进行一次有界人工评审：

- 不要求每次都评审全部样本；
- 必须覆盖该阶段修复的主要失败切片；
- 结果不达标时只允许在预先定义的 Dev 校准窗口内调整；
- 同一配置无变化时不重复评审或重复运行以获取不同结论。

### 8.3 诊断指标

下列指标用于定位问题，默认不单独阻塞阶段：

- CourseRAG Task Evidence Coverage 和 Complete Evidence Group Coverage；
- 每知识点/内容角色覆盖和 Required Modality Coverage；
- Distinct Source、Evidence 和 Semantic Unit 数量；
- Context Budget Loss、补检索增益和重复率；
- Adequacy 状态、缺口类型、误报和漏报；
- 每个 Artifact 的证据语义单元数量；
- 每题独立事实/认知操作覆盖；
- Claim 类型分布和 unsupported 数量；
- Repair 调用率、成功率和回退层级；
- PPT 页面文本密度、留白、标题重复和布局类型分布；
- 每节点 Token、延迟和成本；
- 不同证据容量切片的质量差异。

## 9. 明确禁止的优化方式

不得使用以下方式宣称解决 P18 问题：

1. 直接降低人工质量或合同阈值；
2. 对已消费 P18 Test 逐例调 Prompt 或规则；
3. 仅更换更强模型而不修复输入和工作流；
4. 无界延长 Timeout 或增加重试次数；
5. 仅在 Prompt 中增加“不要幻觉、不要重复”的文字要求；
6. 把 Evidence ID 合法等同于语义 Grounding；
7. 用 LLM-as-a-Judge 替代正式人工质量评审；
8. 使用 Deterministic Fallback 伪造正式成功；
9. 在证据不足时强制满足题数、课时数或页数；
10. 用状态模拟代替 Track B 真实 HTTP Journey；
11. 在质量未达标前优先追求 P95、Token 或成本漂亮；
12. 同时重构全部三类产物和基础设施，导致原因与回归不可定位。
13. 仅因 CoursePilot 质量失败就重做 Parser、Chunker、Embedding、RRF 或 Reranker；
14. 只增加 Top-K、Token Budget 或邻接数量，却不做覆盖、完整组和缺口判断；
15. 使用 Recall/MRR/nDCG 单独证明 Context 足以生成合格教学产物；
16. 让 CourseRAG 承担教学目标、题目难度或 PPT 叙事决策，或让 CoursePilot 绕过 Port 访问索引内部。

## 10. 风险与控制

| 风险 | 表现 | 控制 |
|---|---|---|
| 可行性规则过严 | 大量任务被拒绝 | 使用补充检索和缩范围建议；按证据类型校准，不只看字符数 |
| Adequacy 规则误判 | 足够材料被拒绝或不足材料进入生成 | 新 Dev 分层标注；报告逐 Requirement 结果；对 `adequate` 假阳性采用严格 Gate |
| Coverage-first 降低首位相关性 | Context 更全但核心证据排名下降 | 设置核心相关性底线；比较 Top-N 与约束选择；保留检索与选择双 Trace |
| Purpose-aware 查询膨胀 | 请求、Token、延迟和成本上升 | 固定子查询和补检索上限；缓存；无覆盖增益立即停止 |
| 完整 Evidence Group 占用过多预算 | 其他知识点被挤出 | 按 KP/Role 预留预算；不足时返回缺口，不截断必需组 |
| 跨服务合同扩大 | Remote/Local/Mock 不一致或兼容破坏 | 加法版本化 Contract；Capability 协商；三类 Adapter Contract Test |
| 误把 CourseRAG 当作教学规划器 | 边界反转、耦合 CoursePilot 内部 Schema | CourseRAG 只判断声明需求的证据覆盖；最终业务可行性由 CoursePilot 决定 |
| Grounding 规则过严 | 教案内容过于贫乏 | 区分事实、教学行为、假设和讨论，允许非事实教学丰富度 |
| 语义校验误报 | 合法推导被删除 | 保存支持关系和推导条件；Dev 人工抽检；正式规则冻结 |
| 小批生成增加调用数 | 成本或延迟上升 | 并发受控、Checkpoint、失败批次重试；完成质量闭环后再消融 |
| 全卷规划过复杂 | Exam 开发周期扩大 | 先实现语义单元和使用记录，再逐步增加线索图和难度模型 |
| PPT 视觉规则模板化 | 页面风格僵化 | 冻结可读性底线，不冻结单一布局；使用内容到视觉类型映射 |
| Dev 指标过拟合 | 新 Test 仍失败 | 使用分层 Dev 切片、限制调参窗口、新独立 Test 一次性验证 |
| Track B 环境不可恢复 | 正式旅程再次阻塞 | 开发早期验证索引恢复；正式前从干净环境执行 Preflight |
| B10 继续复杂化 | 更慢、更贵但质量不升 | 每层做消融；无边际收益的节点删除或默认关闭 |

## 11. 回滚原则

- 每个 OPT 阶段单独实施、测试和记录，不跨阶段一次提交大规模重构；
- 新能力优先通过显式配置或版本化路径启用；
- 旧公开 API 保持可用，除非阶段明确批准版本迁移；
- 数据库变化必须有升级验证，降级能力按实际风险说明；
- 新 Planner、Validator 或 Repair 失败时可以回退到上一已批准开发版本，但不得在正式运行中静默回退；
- 正式候选冻结后出现失败，停止该候选并回到新的 Dev 版本，不修改已冻结结果。

## 12. 完成定义

本优化计划只有在以下条件全部满足时才视为完成：

1. 不可行任务能够正确补证据、缩范围或停止，而不是幻觉补足；
2. CourseRAG 能根据 Lesson/Exam/PPT Requirements 返回任务型 Context 和可解释 Adequacy；
3. 被判定为 `adequate` 的 Context 满足知识点、材料类型和完整 Evidence Group Gate；
4. CoursePilot 能消费 Adequacy 并完成补检索、缩范围、停止或正常生成闭环；
5. Lesson、Exam、PPT 的结构合同和导出完整率达到 100%；
6. 关键事实达到 Claim-level 可追溯和语义支持；
7. 三类产物各自达到人工质量阈值；
8. Track B 8/8 Journey 在真实索引和真实服务边界下通过；
9. L0 危险事件保持为零；
10. 候选 Profile 的成本和延迟满足预注册预算；
11. 新独立 Test 完成一次性正式评测并通过全部 Gate；
12. 结果、限制和剩余风险如实记录，不通过降低阈值或改写状态获得成功结论。

## 13. 后续执行约束

- 本文档固定需求和顺序，不授权立即修改代码、数据库、冻结文档或正式评测资产。
- 后续应从 `OPT-0` 开始，一次只启动一个阶段。
- 每个阶段开始前必须给出：现状、差距、文件级计划、兼容/迁移风险、测试和回滚。
- 每个阶段结束时记录实际完成的 Requirement ID、测试结果、未完成项、风险和 Gate 结论。
- 若实施发现本文档与冻结文档或质量政策冲突，停止冲突部分并提交明确决策，不自行覆盖既有权威文档。
