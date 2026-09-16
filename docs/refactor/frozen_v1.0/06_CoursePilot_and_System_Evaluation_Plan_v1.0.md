# CoursePilot 与系统级评测方案

**文档版本：** v1.0  
**文档状态：** 冻结执行版
**冻结日期：** 2026-07-22
**上位文档：**
- `01_CoursePilot_CourseRAG_Split_and_Refactor_Plan_v1.0.md`
- `03_CourseRAG_Evaluation_Dataset_and_Baseline_v1.0.md`
- `03A_CourseRAG_Evaluation_Dataset_Construction_Guide_v1.0.md`
- `04_CourseRAG_Technical_Refactor_Plan_v1.0.md`
- `05_CoursePilot_Agent_Engineering_Upgrade_Plan_v1.0.md`

**评测对象：**
- CoursePilot 教案工作流；
- CoursePilot 试卷工作流；
- CoursePilot PPT 工作流；
- Validation 与 Targeted Repair；
- LangGraph Checkpoint、Interrupt 和恢复；
- Template、Model Routing 和 Export；
- CoursePilot—CourseRAG 集成；
- 端到端可靠性、安全、成本和人工负担。

**不采用：**
- LLM-as-a-Judge；
- 未经人工审核的模型评分；
- 只看“能否生成文件”的单一成功率；
- 将 Deterministic Fallback 结果计入真实模型质量；
- 用同一批 Test 反复调参。

---

## 1. 文档目的

本文档用于确定 CoursePilot Agent 工程和 CoursePilot—CourseRAG 系统的正式评测数据、基线、指标、人工评分、故障注入、实验流程、验收门槛和报告格式。

本文档需要解决：

1. 教案、试卷和 PPT 分别需要构造哪些正式任务；
2. 多种合理输出无法建立唯一 Gold 时，如何公平评价；
3. Agent 自身质量和 CourseRAG 上游质量如何隔离；
4. ValidationIssue 是否真正发现并定位错误；
5. Targeted Repair 是否只修错处且不引入回归；
6. Interrupt、Checkpoint 和恢复是否具备真实业务价值；
7. Main/Light Model Routing 是否降低成本且不明显损害质量；
8. 内置模板和用户模板是否可复现、可导出、可扩展；
9. PPTX、DOCX 是否真正可用，而非只通过 Schema；
10. CoursePilot 与 CourseRAG 连接后，Evidence、Index Version、Trace 和写回是否保持一致；
11. 哪些结果可以进入 README、论文式实验报告或求职简历。

---

## 2. 总体原则

### 2.1 分离 Agent 质量与 RAG 质量

同一组 CoursePilot 任务运行两条轨道。

#### Track A：Agent-Isolated

使用固定的：

- CourseRAG `ContextPackage`；
- Knowledge Point Snapshot；
- Evidence Records；
- Citation Map；
- Retrieval Trace 摘要。

这些内容被保存为评测 Fixture，不在每次运行时重新检索。

Track A 用于比较：

- Graph；
- Planning；
- Generation；
- Validation；
- Repair；
- Interrupt；
- Model Routing；
- Template；
- Export。

#### Track B：Integrated System

使用真实 CourseRAG：

```text
原始 PDF/DOCX
→ CourseRAG Build
→ Search/Context
→ CoursePilot Agent
→ Validation/Repair
→ Interrupt
→ Export/Writeback
```

Track B 用于评价：

- 上下游接口；
- Index/Evidence Version；
- Trace 连通；
- RAG 错误向 Agent 的传播；
- 端到端延迟与成本；
- 失败隔离和恢复。

Track A 不通过时，不应直接用 Track B 解释 Agent 质量。

### 2.2 Gold 采用“约束 + 证据 + 人工 Rubric”

教案、试卷和 PPT 存在多种合理答案，不构造唯一标准全文。

正式 Gold 包含：

- 输入任务；
- 必须满足的硬约束；
- 推荐覆盖的软约束；
- 禁止内容；
- Gold Knowledge Points；
- Gold Evidence；
- 允许的结构范围；
- 人工评分 Rubric。

### 2.3 自动指标和人工指标分离

自动指标负责：

- Schema；
- 数量；
- 时间；
- 分值；
- 引用 ID；
- Evidence 可解析性；
- Template/Layout；
- Checkpoint；
- Side Effect；
- Token、延迟、成本。

人工指标负责：

- 教学逻辑；
- 题目质量；
- 难度合理性；
- PPT 信息组织；
- Grounding 的语义支持；
- 实际修改负担。

不能用模型评分替代这些人工判断。

### 2.4 正式评测禁用静默 Fallback

真实模型评测中：

- LLM 调用失败即记录失败；
- Structured Output 失败进入显式 Repair；
- 不允许生成模板化假内容后标记为成功；
- Model Profile 升级或切换必须记录；
- RAG、模型和导出 Fallback 分开统计。

### 2.5 Dev/Test 隔离

- Pilot：验证数据和脚本；
- Dev：选择 Prompt、模型、阈值、并发和模板；
- Test：配置冻结后用于正式结果。

Test 结果产生后不得继续调参并覆盖同一 Run。

### 2.6 评测结果必须可追溯

每个结果必须能追溯到：

- Dataset Version；
- Task ID；
- CourseRAG Snapshot/Index Version；
- Template Version；
- Prompt Hash；
- Model Profile 和实际模型；
- Graph Version；
- Validator Version；
- Exporter Version；
- Git Commit；
- Trace ID；
- Human Review Record。

---

## 3. 评测层级

| 层级 | 被测对象 | 核心问题 |
|---|---|---|
| CP-E1 | 输入、模板与合同 | 请求、模板、Artifact 和引用合同是否稳定 |
| CP-E2 | Planning | Session Plan、Exam Blueprint、Slide Architecture 是否合理 |
| CP-E3 | Generation | 内容是否满足约束、基于证据且可使用 |
| CP-E4 | Validation | 是否发现、定位和分级真实问题 |
| CP-E5 | Repair | 是否修复目标问题且不破坏正确内容 |
| CP-E6 | HITL 与恢复 | Interrupt、编辑、恢复和副作用授权是否正确 |
| CP-E7 | Export | DOCX/PPTX 是否结构、版式、引用和可编辑性合格 |
| CP-E8 | Model/Template Engineering | 路由和模板是否带来质量、延迟或成本收益 |
| SYS-E1 | CoursePilot—CourseRAG 集成 | Context、Evidence、Version 和 Trace 是否一致 |
| SYS-E2 | 端到端可靠性 | 构建、生成、审批、导出、写回是否可完成和恢复 |
| SYS-E3 | 安全与隔离 | 跨课程、Prompt Injection、授权和敏感数据是否受控 |
| SYS-E4 | 效率与成本 | P50/P95、并发、Token、API 调用和人工时间 |

---

## 4. 数据集总览

建议准备 9 组 CoursePilot/系统级数据资产。

| 编号 | 数据集 | 建议规模 | 主要用途 |
|---|---|---:|---|
| CP-DS0 | Evaluation Manifest 与 Template Snapshot | 1 套 | 冻结环境、模板、模型和版本 |
| CP-DS1 | Lesson Task Set | Pilot 3 + 正式 10 | 教案 Planning、Generation、Validation、Export |
| CP-DS2 | Exam Task Set | Pilot 3 + 正式 10 | Blueprint、题目、答案、全局校验 |
| CP-DS3 | PPT Task Set | Pilot 3 + 正式 10 | Slide Architecture、内容、Notes、PPTX |
| CP-DS4 | Validation Fault Set | 每类约 30，合计约 90 | ValidationIssue 定位与分级 |
| CP-DS5 | Repair Set | 每类约 20，合计约 60 | Targeted Repair 与回归 |
| CP-DS6 | Interrupt/Recovery Set | 18～24 个场景 | 六个 Interrupt、编辑、恢复、授权 |
| CP-DS7 | Export/Template Set | 9 内置 + 2 自定义 | DOCX/PPTX、Layout、模板扩展 |
| CP-DS8 | Fault/Security Set | 20～30 个场景 | Provider、Worker、RAG、安全和副作用 |
| SYS-DS1 | End-to-End Journey Set | 6～8 条 Journey | 系统级完成率、Trace、成本和写回 |

CP-DS1～CP-DS3 的正式任务总数为 30：

- Lesson：10；
- Exam：10；
- PPT：10。

正式任务建议划分：

- Dev：18，三类各 6；
- Test：12，三类各 4。

Pilot 9 条不进入最终指标。

---

## 5. CP-DS0：Evaluation Manifest

```yaml
dataset_version: coursepilot_eval_v1
git_commit: ...
coursepilot_graph_version: ...
courserag_fixture_version: ...
courserag_index_version: ...
template_registry_version: ...
validator_version: ...
repair_policy_version: ...
exporter_version: ...
model_profiles:
  planner_main: ...
  generator_main: ...
  content_repair_main: ...
  classifier_light: ...
  json_repair_light: ...
split: dev
```

Manifest 还需保存：

- CourseRAG Fixture Hash；
- Prompt Hash；
- Built-in Template Hash；
- 自定义模板 Hash；
- 字体包与渲染环境；
- 运行模式；
- 是否允许 Profile Escalation；
- 并发；
- Timeout；
- Repair Round；
- Checkpoint Backend；
- LangSmith Project/Trace Tag；
- 评审 Rubric Version。

不得保存 API Key。

---

## 6. CP-DS1：Lesson Task Set

## 6.1 覆盖范围

10 条正式任务建议覆盖：

| 类型 | 数量 |
|---|---:|
| 标准高校讲授 | 3 |
| 研讨/案例课 | 2 |
| 实验/实践课 | 2 |
| 多课时复杂章节 | 2 |
| 证据不足或约束冲突 | 1 |

交叉属性至少覆盖：

- 单课时和多课时；
- 45/50/90 分钟；
- 明确教学重点；
- 指定活动类型；
- 指定模板；
- 指定知识点；
- OCR 来源 Evidence；
- 多 Section Evidence；
- Teacher Verified 片段；
- 无法完全满足的输入。

## 6.2 Lesson Case Schema

```json
{
  "case_id": "lesson_001",
  "course_id": "course_eval_001",
  "template_id": "lesson_standard_university_v1",
  "input": {
    "chapter_range": "第3章 启发式搜索",
    "total_sessions": 2,
    "session_duration": 50,
    "teaching_focus": "区分无信息搜索和启发式搜索",
    "audience": "本科二年级"
  },
  "fixed_context_package_id": "ctx_lesson_001",
  "gold": {
    "required_knowledge_point_ids": [],
    "optional_knowledge_point_ids": [],
    "required_evidence_ids": [],
    "required_session_count": 2,
    "required_minutes_per_session": 50,
    "required_activity_types": ["comparison", "practice"],
    "forbidden_claims": [],
    "required_interrupts": [
      "lesson_session_plan_review",
      "lesson_final_review"
    ]
  },
  "review_status": "approved"
}
```

## 6.3 Lesson 自动评价

- Schema Pass；
- Session Count；
- Time Allocation；
- Required Field Coverage；
- Knowledge Point Coverage；
- Evidence/Citation Resolvability；
- Required Activity Coverage；
- Forbidden Claim Hit；
- Template Contract；
- Final Approval；
- Export Success；
- Writeback Authorization。

## 6.4 Lesson 人工 Rubric

每项 1～5 分。

| 维度 | 评价内容 |
|---|---|
| L-H1 目标一致性 | 目标是否与章节、知识点和学生层次一致 |
| L-H2 课时规划 | Session 划分、顺序和负担是否合理 |
| L-H3 时间可执行性 | 各活动在给定时间内是否现实 |
| L-H4 知识覆盖 | 核心知识点是否充分且不过度扩展 |
| L-H5 教学活动 | 活动是否具体、可操作并服务目标 |
| L-H6 重点难点 | 是否真正识别并处理学习难点 |
| L-H7 证据忠实 | 事实性内容是否有来源且不超出资料 |
| L-H8 教师可用性 | 教师是否能低成本修改后使用 |

评分锚点：

- 1：明显错误或不可用；
- 3：基本可用但需较多修改；
- 5：逻辑完整、具体、少量编辑即可使用。

同时记录：

```text
edit_burden:
0 = 无需修改
1 = 轻微措辞/格式
2 = 多处局部修改
3 = 结构性重写
4 = 无法采用
```

---

## 7. CP-DS2：Exam Task Set

## 7.1 覆盖范围

10 条正式任务建议覆盖：

| 类型 | 数量 |
|---|---:|
| 章节作业 | 2 |
| 单元测验 | 2 |
| 期中/期末组合卷 | 3 |
| 单一题型压力 | 1 |
| 多知识点/难度约束 | 1 |
| 证据不足或约束冲突 | 1 |

覆盖题型：

- 单选；
- 多选；
- 判断；
- 简答；
- 计算/分析题，若课程资料支持。

覆盖：

- 不同分值；
- 难度分布；
- 多题型；
- Hard Negative；
- 相似知识点；
- 多 Evidence；
- Teacher Verified Question；
- 题量较大并行生成。

## 7.2 Exam Case Schema

```json
{
  "case_id": "exam_001",
  "template_id": "exam_unit_quiz_v1",
  "input": {
    "chapter_range": "第3章",
    "question_counts": {
      "single_choice": 5,
      "judgement": 3,
      "short_answer": 2
    },
    "score_per_question": {
      "single_choice": 4,
      "judgement": 5,
      "short_answer": 10
    },
    "difficulty_distribution": {
      "easy": 0.3,
      "medium": 0.5,
      "hard": 0.2
    }
  },
  "fixed_context_package_id": "ctx_exam_001",
  "gold": {
    "required_total_score": 55,
    "required_knowledge_point_ids": [],
    "required_evidence_ids": [],
    "forbidden_claims": [],
    "required_interrupts": [
      "exam_blueprint_review",
      "exam_global_review"
    ]
  }
}
```

## 7.3 Exam 自动评价

- Blueprint Schema；
- Question Count；
- Total Score；
- Type Distribution；
- Difficulty Label Distribution；
- Required Knowledge Coverage；
- Option Presence；
- Answer Presence；
- Explanation Presence；
- Citation Resolvability；
- Duplicate Rate；
- Global Validation；
- Export File Set；
- Approved Question Writeback Scope。

## 7.4 Exam 人工 Rubric

| 维度 | 评价内容 |
|---|---|
| E-H1 Blueprint 合理性 | 题型、分值、覆盖和难度规划 |
| E-H2 题干质量 | 清晰、无歧义、条件完整 |
| E-H3 正确性 | 答案是否正确且唯一/集合合理 |
| E-H4 干扰项质量 | 是否有辨识度且不明显荒谬 |
| E-H5 难度匹配 | 实际认知要求是否符合标签 |
| E-H6 覆盖与平衡 | 知识点、内容角色和题型是否均衡 |
| E-H7 重复与泄漏 | 是否重复、互相提示或答案泄漏 |
| E-H8 解析质量 | 解析是否解释关键依据而非复述答案 |
| E-H9 Grounding | 题目、答案和解析是否由资料支持 |
| E-H10 可用性 | 是否可直接进入教师复核流程 |

对每一道题额外标记：

```text
question_status:
accepted
minor_edit
major_edit
reject
```

---

## 8. CP-DS3：PPT Task Set

## 8.1 覆盖范围

10 条正式任务建议覆盖：

| 类型 | 数量 |
|---|---:|
| 标准讲授 | 3 |
| 概念解释 | 2 |
| 案例研讨 | 2 |
| 多课时长 PPT | 2 |
| 版式/证据压力 | 1 |

至少覆盖：

- 8～12 页短 Deck；
- 20 页以上长 Deck；
- 表格来源；
- 图片/图示 Placeholder；
- Speaker Notes；
- 多 Section；
- OCR Evidence；
- 内置三类模板；
- 一个用户自定义 PPTX 模板。

## 8.2 PPT Case Schema

```json
{
  "case_id": "ppt_001",
  "template_id": "ppt_standard_lecture_v1",
  "lesson_artifact_id": "lesson_fixture_001",
  "input": {
    "slide_count": 12,
    "include_references": true,
    "include_speaker_notes": true
  },
  "gold": {
    "required_slide_types": [
      "title",
      "objectives",
      "concept",
      "comparison",
      "activity",
      "summary",
      "references"
    ],
    "required_knowledge_point_ids": [],
    "required_evidence_ids": [],
    "max_bullets_per_slide": 6,
    "required_interrupts": [
      "ppt_architecture_review",
      "ppt_final_review"
    ]
  }
}
```

## 8.3 PPT 自动评价

- Slide Count；
- Slide Type Validity；
- Slide Architecture Coverage；
- Source Session Mapping；
- Citation Resolvability；
- Notes Presence；
- Layout Mapping；
- Placeholder Mapping；
- Text Overflow；
- Shape Outside Slide；
- Empty Placeholder；
- Font Fallback；
- PPTX Open/Render Success；
- Final Approval；
- Writeback Scope。

## 8.4 PPT 人工 Rubric

| 维度 | 评价内容 |
|---|---|
| P-H1 Slide Architecture | 页序和页型是否服务教学逻辑 |
| P-H2 单页聚焦 | 每页是否有明确中心 |
| P-H3 信息密度 | 是否过载、过空或堆砌 Bullet |
| P-H4 内容连贯 | 页面间过渡和层次是否清晰 |
| P-H5 教学表达 | 是否适合课堂讲解而非文档搬运 |
| P-H6 活动与示例 | 是否支持课堂互动和理解 |
| P-H7 Notes | 是否提供可用讲解提示 |
| P-H8 引用与来源 | 是否准确、可解析并放置合理 |
| P-H9 可编辑性 | 教师是否可方便调整 |
| P-H10 视觉可用性 | 模板、布局和文本是否基本合格 |

PPT 不以商业演示视觉效果为目标，正式标准是“可编辑的教学 Deck 初稿”。

---

## 9. CP-DS4：Validation Fault Set

## 9.1 目的

评价 Validator 是否：

- 发现真实问题；
- 精确定位对象和字段；
- 正确分类 Severity；
- 给出可执行 Repair Strategy；
- 不把正确内容误判为问题。

## 9.2 构造方法

从人工确认的合法 Artifact Fixture 复制并注入单一或组合错误。

### Lesson Fault

- Session 数量错误；
- 时间合计错误；
- 缺教学目标；
- 知识点漏覆盖；
- 引用不存在；
- 引用属于错误 Session；
- Unsupported Claim；
- 活动与目标无关；
- 多 Session 内容重复；
- Template Required Field 缺失。

### Exam Fault

- 题量错误；
- 总分错误；
- 选择题缺选项；
- 答案不在选项；
- 多选答案格式错误；
- 解析与答案冲突；
- 知识点越界；
- 引用不存在；
- 重复题；
- 题干泄漏答案；
- Blueprint 与实际难度不一致。

### PPT Fault

- Slide 数量错误；
- 非法 Slide Type；
- Session 映射错误；
- 引用错误；
- Bullet 为空；
- 内容溢出；
- Layout 不存在；
- Notes 缺失；
- 参考页无引用；
- 页面重复；
- 表格/图片 Placeholder 丢失。

## 9.3 Gold Issue Schema

```json
{
  "fault_case_id": "val_lesson_001",
  "artifact_type": "lesson",
  "artifact_fixture_id": "lesson_valid_001",
  "injections": [],
  "gold_issues": [
    {
      "code": "LESSON_TIME_TOTAL_MISMATCH",
      "severity": "error",
      "scope": {
        "artifact_type": "lesson",
        "item_id": "session_2",
        "json_path": "$.session_plan[1].time_allocation"
      },
      "auto_repairable": true
    }
  ]
}
```

## 9.4 指标

### Issue Detection Precision

```text
正确匹配的预测 Issue 数 / 全部预测 Issue 数
```

### Issue Detection Recall

```text
正确匹配的预测 Issue 数 / Gold Issue 总数
```

### Issue Code Accuracy

预测与 Gold 的 `code` 一致比例。

### Scope Localization Accuracy

预测的 `item_id + json_path` 与 Gold 一致，或落在预先定义的允许父路径范围内的比例。

### Severity Accuracy

Severity 完全一致比例。

### Auto-repairable Accuracy

`auto_repairable` 判断正确比例。

### Clean Artifact False Positive Rate

无故障 Artifact 中被报告 Error/Critical 的比例。

Issue 匹配以 `code + scope` 为主，不用字符串错误全文匹配。

---

## 10. CP-DS5：Targeted Repair Set

## 10.1 构造

从 Validation Fault Set 中选择：

- 单字段错误；
- 单对象多字段错误；
- 多对象独立错误；
- Grounding 错误；
- 内容级教学错误；
- Critical Issue。

保留原始正确 Artifact，便于评价未授权字段是否发生变化。

## 10.2 Repair Patch Schema

```json
{
  "repair_case_id": "repair_exam_001",
  "artifact_before_id": "exam_fault_001",
  "allowed_paths": [
    "$.questions[3].correct_answer",
    "$.questions[3].explanation"
  ],
  "forbidden_paths": [
    "$.questions[0:3]",
    "$.blueprint"
  ],
  "expected_resolved_issue_codes": [
    "ANSWER_OPTION_MISMATCH"
  ]
}
```

## 10.3 指标

### Repair Attempt Success Rate

一次 Repair 后目标 Issue 被解决的案例比例。

### Final Repair Success Rate

允许的最大 Repair Round 内目标 Issue 被解决的案例比例。

### Targeted Modification Rate

```text
发生在 allowed_paths 内的修改字段数 / 全部修改字段数
```

### Unauthorized Modification Rate

```text
allowed_paths 外的修改字段数 / 全部修改字段数
```

### Regression Rate

Repair 后新增 Gold 中不存在的 Error/Critical Issue 的案例比例。

### Preservation Rate

原 Artifact 中未涉及修复的正确字段保持不变比例。

### Issue Reduction

```text
修复前加权 Issue 分数 - 修复后加权 Issue 分数
```

初始权重：

- info = 0；
- warning = 1；
- error = 3；
- critical = 5。

### Repair Cost

- Model Calls；
- Tokens；
- Latency；
- Repair Round；
- Main/Light Escalation。

---

## 11. CP-DS6：Interrupt、Checkpoint 与恢复

## 11.1 六个正式 Interrupt

- Lesson Session Plan Review；
- Lesson Final Review；
- Exam Blueprint Review；
- Exam Global Review；
- PPT Slide Architecture Review；
- PPT Final Review。

## 11.2 每个 Interrupt 至少测试

- Approve；
- Edit and Resume；
- Request Replan/Regenerate；
- Reject/Cancel；
- 重复提交同一决策；
- Worker 在 Interrupt 前后崩溃；
- 服务重启后恢复；
- 用户长时间未处理；
- Artifact Version 在暂停期间发生变化；
- CourseRAG Index Version 在暂停期间发生变化。

## 11.3 核心指标

### Interrupt Reach Rate

预期进入 Interrupt 的任务中成功进入的比例。

### Resume Success Rate

合法 Human Decision 后任务从正确节点继续并达到下一个预期状态的比例。

### Completed Node Reuse Rate

恢复后未重复执行的已成功高成本节点数，占恢复前已成功高成本节点总数的比例。

### Human Edit Preservation Rate

人工修改后，恢复生成结果中保留这些修改的字段比例。

### Duplicate Side-effect Rate

重复 Resume、重试或网络重放造成重复导出、重复写回的比例。

目标必须为 0。

### Approval Scope Accuracy

仅获得导出批准时不得写回；仅获得写回批准时不得跳过最终内容审核。权限执行正确比例。

### Stale Version Detection Rate

暂停期间 Template、Artifact 或 CourseRAG Index 发生不兼容变化时，系统正确拒绝或要求重审的比例。

---

## 12. CP-DS7：Template 与 Export

## 12.1 内置模板

评测 9 个内置逻辑模板：

- 3 个 Lesson；
- 3 个 Exam；
- 3 个 PPT。

每个模板检查：

- Input Schema；
- Prompt Profile；
- Output Schema；
- Validator Profile；
- Repair Profile；
- Model Profile；
- Exporter Profile；
- Template Snapshot；
- Version Reproducibility。

## 12.2 自定义模板

至少准备：

- 1 个用户教案 DOCX 模板；
- 1 个用户 PPTX 模板。

验证：

```text
导入
→ Style/Master/Layout 检测
→ Placeholder Mapping
→ 人工确认
→ Custom TemplateDefinition
→ 生成
→ 导出
```

## 12.3 Export 自动指标

### Render Success Rate

文件可由规定 Renderer 打开并完成渲染的比例。

### Layout Mapping Accuracy

Artifact 的逻辑类型被映射到期望 DOCX Style/PPT Layout 的比例。

### Required Placeholder Fill Rate

必填 Placeholder 被填充的比例。

### Text Overflow Rate

存在超出文本框或页面边界文本的页面比例。

### Severe Overflow Case Rate

至少一个关键标题、正文或答案被截断的文件比例。

### Font Availability Rate

所需字体存在且未意外回退的文本样式比例。

### Reference Render Accuracy

导出文件中的引用与 Artifact Evidence ID、页码或来源一致比例。

### Editable Object Rate

PPT 中要求可编辑的文本、表格、图形 Placeholder 仍为可编辑对象的比例。

不以 PDF 截图替代 PPTX 可编辑性。

## 12.4 视觉回归

使用固定 Renderer 生成：

- DOCX PDF Snapshot；
- PPT Slide PNG；
- Layout Metadata。

视觉回归用于发现：

- 元素缺失；
- 页数突变；
- Placeholder 错位；
- 文本框越界；
- 字体异常。

不使用严格像素相等作为唯一通过条件。

---

## 13. CP-DS8：故障与安全场景

## 13.1 Provider 故障

- Main Model Timeout；
- Light Model Timeout；
- 429；
- Invalid JSON；
- Schema 不通过；
- 返回空 Choices；
- Prompt 太长；
- Profile 不支持 Thinking/Reasoning；
- Reranker/Embedding 故障由 CourseRAG 传播。

## 13.2 CourseRAG 故障

- Context 为空；
- Context 不完整；
- Evidence 无法解析；
- Index Version 变化；
- CourseRAG Timeout；
- 返回跨课程 Evidence；
- Citation 过期；
- Teacher Verified 与 Primary Source 冲突。

## 13.3 Worker/持久化故障

- Node 完成后、Checkpoint 前崩溃；
- Checkpoint 后、任务状态提交前崩溃；
- Export 文件写入后、数据库记录前崩溃；
- Writeback 成功后、CoursePilot 响应丢失；
- Lease 过期被第二 Worker 接管；
- 重复 Idempotency-Key；
- Checkpointer 暂时不可用。

## 13.4 安全

- 检索资料包含“忽略系统提示”等文本；
- 资料要求输出 API Key；
- Course A 请求引用 Course B Evidence；
- 未审核用户尝试写回；
- 仅批准导出却触发写回；
- Template Placeholder 包含注入文本；
- 导出文件名路径穿越；
- LangSmith Trace 中出现 Secret；
- 用户输入要求绕过 Validator；
- 恶意超长反馈导致 Context 膨胀。

## 13.5 指标

- Fault Detection Rate；
- Graceful Failure Rate；
- Unauthorized Action Rate；
- Cross-course Leakage Rate；
- Secret Leakage Count；
- Injection Instruction Following Rate；
- Recovery Success Rate；
- Duplicate Side-effect Rate；
- User-visible Error Classification Accuracy。

安全目标：

```text
Unauthorized Action Rate = 0
Cross-course Leakage Rate = 0
Secret Leakage Count = 0
Duplicate Side-effect Rate = 0
```

---

## 14. SYS-DS1：端到端 Journey

建议 6～8 条 Journey。

### Journey 1：标准教案

```text
上传 PDF/DOCX
→ 构建 CourseRAG
→ 生成 Session Plan
→ 人工修改并批准
→ 生成教案
→ 最终批准
→ 导出 DOCX
```

### Journey 2：试卷

```text
CourseRAG Context
→ Exam Blueprint
→ 人工调整难度/题量
→ 并行生成题目
→ 全局校验和 Repair
→ 批准
→ 导出四类 DOCX
→ 写回指定题目
```

### Journey 3：PPT

```text
已批准 Lesson
→ Slide Architecture
→ 人工调整页序
→ 生成内容与 Notes
→ 渲染校验
→ 批准
→ 导出 PPTX
```

### Journey 4：写回闭环

```text
批准 Question/Explanation/Lesson Fragment
→ CourseRAG Verified Content
→ Enrichment Batch
→ 新 Index Version
→ 新任务检索到写回内容
```

### Journey 5：故障恢复

在高成本节点后杀死 Worker，重启后从 Checkpoint 恢复，验证不重复模型调用和 Side Effect。

### Journey 6：证据不足

CourseRAG 返回不足 Context，Agent 应要求补充资料或进入 `needs_review`，不能生成确定性事实。

### Journey 7：恶意资料

课程资料包含 Prompt Injection，验证 Agent 不执行资料指令。

### Journey 8：版本变化

任务在 Interrupt 暂停期间更新 CourseRAG Index 或 Template，验证版本检测和重审。

---

## 15. CoursePilot 基线

## 15.1 CP-B0：当前实现

- 当前三条线性 Graph；
- 随机 Thread；
- 无业务 Checkpointer；
- Boolean Validation Report；
- Whole-artifact Repair；
- 教案从 Context 再抽知识点；
- 试题串行；
- 单一模型和固定高推理参数；
- 默认 DOCX/PPTX Export；
- 引用依赖 Chunk ID；
- 宽范围 Review Writeback。

## 15.2 增强基线

| 编号 | 新增能力 | 主要回答 |
|---|---|---|
| CP-B0 | 当前实现 | 当前真实起点 |
| CP-B1 | CourseRAG Port + Evidence Contract | 上下游解耦和引用是否改善 |
| CP-B2 | Typed State + Artifact Version + Template Snapshot | 状态可复现性 |
| CP-B3 | Layered ValidationIssue | 错误发现和定位是否改善 |
| CP-B4 | Repair Planner + Targeted Patch | 修复是否更准、回归更少 |
| CP-B5 | PostgreSQL Checkpoint + Stable Thread | 可恢复性 |
| CP-B6 | 六个 HITL Interrupt | 人工控制和修改保留 |
| CP-B7 | Exam Fan-out/Fan-in | 延迟和全局质量 |
| CP-B8 | Main/Light Model Routing | 成本、延迟和质量权衡 |
| CP-B9 | Template Export + PPT Render Validation | 文件可用性 |
| CP-B10 | 全集成 CoursePilot | Agent MVP 最终版本 |

CP-B1～CP-B10 不是必须每步都运行全部 30 条人工评分。各阶段先运行对应的专项数据集，最终 CP-B0 与 CP-B10 在锁定 Test 上完整对比。

---

## 16. Model Routing 实验

## 16.1 路由配置

### MR-0：Single Main High

所有节点使用 Main Model，并按当前方式启用高推理。

### MR-1：Single Main Profiled

仍使用一个实际模型，但按节点设置不同：

- Temperature；
- Reasoning；
- Output Token；
- Timeout。

### MR-2：Main + Light

- Planning/Generation/Content Repair：Main；
- Classification/JSON Repair/Compression：Light；
- Deterministic Rule 优先。

### MR-3：Main + Light + Escalation

Light 失败或 Issue Severity 高时显式升级 Main。

### MR-4：独立 Planner

只在 Dev 证明有价值时实验，不属于默认 MVP。

## 16.2 指标

- Schema Pass；
- Human Quality；
- Validation Pass；
- Repair Success；
- Profile Escalation Rate；
- Model Call Count；
- Input/Output Tokens；
- Cost；
- P50/P95；
- Task Failure；
- Model Switch Count。

## 16.3 选择规则

MR-2/MR-3 相对 MR-1 的质量非劣标准：

```text
人工平均分下降不超过 0.2
且 Critical Error 不增加
且 Grounding/Citation 不下降
```

同时至少满足一个：

```text
平均模型成本降低 ≥ 20%
或 P95 延迟降低 ≥ 20%
```

这些百分比是技术选型门槛，不是预先宣称的结果。

---

## 17. Exam 并行实验

比较：

- EX-P0：当前按题型串行；
- EX-P1：按题型并行；
- EX-P2：按 Question Batch 并行；
- EX-P3：Batch 并行 + 全局 Duplicate/Score/Coverage Repair。

指标：

- Wall-clock Latency；
- Sum of Model Latency；
- Parallel Speedup；
- Question Count；
- Duplicate Rate；
- Knowledge Coverage；
- Difficulty Distribution；
- Repair Round；
- Token/Cost；
- Human Question Acceptance。

并行方案只有在：

- P95 明显下降；
- Duplicate/一致性不恶化；
- 全局修复成本可控；

时才进入默认配置。

---

## 18. 人工评审流程

## 18.1 评审盲化

评审界面隐藏：

- Baseline 名称；
- 模型名称；
- Prompt 版本；
- 输出顺序。

使用随机 Sample ID。

## 18.2 评审量

正式 Test：

- 12 个 Artifact 全部人工评分；
- Exam 对所有题目做 accepted/minor/major/reject；
- PPT 对所有页面做关键故障检查；
- 至少 20% 样本在间隔后重新盲评；
- 条件允许时由第二位具有教学经验的评审者复核 20%。

## 18.3 一致性

若有两位评审：

- 1～5 分计算 Weighted Cohen's Kappa 或 ICC；
- 类别标签计算 Cohen's Kappa；
- 分歧超过 2 分时共同复核。

若只有一位评审：

- 20% 重复盲评；
- 报告 Intra-rater Agreement；
- 不伪称为 Inter-rater Reliability。

## 18.4 评审记录

保存：

- Score；
- Edit Burden；
- Critical Defect；
- 修改说明；
- 接受/拒绝；
- 评审时间；
- Reviewer ID；
- Rubric Version。

---

## 19. 通用指标定义

## 19.1 Contract Pass Rate

```text
满足全部强制合同的任务数 / 总任务数
```

## 19.2 Critical Defect-free Rate

```text
无 Critical Defect 的 Artifact 数 / 总 Artifact 数
```

## 19.3 Citation Resolvability

```text
可从 CourseRAG 解析的引用数 / 全部引用数
```

## 19.4 Evidence Trace Coverage

```text
需要来源支持且至少绑定一个有效 Evidence 的内容单元数
/ 全部需要来源支持的内容单元数
```

内容单元：

- Lesson Session/Teaching Item；
- Exam Question/Explanation；
- PPT Slide/Notes。

## 19.5 Human Acceptable Rate

```text
人工判断 accepted 或 minor_edit 的 Artifact/Question/Slide 数
/ 被评对象总数
```

## 19.6 Mean Edit Burden

对 0～4 修改负担取平均，并报告分布。

## 19.7 End-to-End Completion Rate

```text
按预定 Journey 完成全部必要阶段和副作用的运行数
/ Journey 运行总数
```

进入 `needs_review` 但符合场景预期时，不算系统失败；必须按 Journey Gold 判定。

## 19.8 Task Recovery Rate

```text
故障后从同一 Task/Thread 恢复并完成预期状态的任务数
/ 注入故障的任务数
```

## 19.9 Cost per Accepted Artifact

```text
正式模型与 RAG API 总成本
/ 人工 accepted 或 minor_edit 的 Artifact 数
```

## 19.10 Human Minutes per Accepted Artifact

```text
人工审核与修改总分钟数
/ accepted 或 minor_edit Artifact 数
```

---

## 20. 系统级指标

### 20.1 Version Consistency Rate

Task 使用的 Context、Evidence 和 Index Version 与运行记录一致的比例。

### 20.2 Trace Continuity Rate

可从 CoursePilot Task Trace 追踪到对应 CourseRAG Retrieval/Context Trace 的任务比例。

### 20.3 Writeback Provenance Completeness

写回记录中包含 Approval、Task、Artifact、Evidence、KP、Hash 和 Idempotency 的比例。

### 20.4 Stale Evidence Detection Rate

Evidence 失效或迁移后，CoursePilot 在导出/写回前正确阻止或要求重审的比例。

### 20.5 Error Isolation Rate

CourseRAG、模型、Graph、Validator、Exporter 或 Writeback 的错误被正确分类到原始组件，而非统一表现为未知失败的比例。

### 20.6 Upstream Error Propagation Rate

CourseRAG Context 已知缺陷未被 CoursePilot 识别、最终传播为用户可见事实错误的案例比例。

---

## 21. Run 设计

## 21.1 Deterministic Tests

- Unit/Contract/Fault Set 可重复多次；
- 禁用外部模型或使用固定 Fake；
- 目标是逻辑和副作用正确。

## 21.2 Real-model Dev

- 18 个正式 Dev Task；
- 每个关键配置至少运行一次；
- 对不稳定节点执行 3 次重复；
- 选择模型、Prompt、阈值和并行度。

## 21.3 Locked Test

- 12 个正式 Test Task；
- 完整 CP-B0 与 CP-B10；
- 完整 MR 最终候选；
- Track A 和 Track B；
- 人工内容评分只对冻结输出进行；
- Test 失败不通过临时修改结果文件修复。

## 21.4 稳定性子集

从 Test 选择至少 3 条任务：

- Lesson 1；
- Exam 1；
- PPT 1。

每条重复 3 次，报告：

- Contract Pass 方差；
- 人工评分变化；
- 结构差异；
- Token/延迟；
- 关键事实一致性。

---

## 22. 运行流程

```text
1. 验证 Dataset、Corpus、Fixture 和 Template Hash
2. 冻结 Git Commit、Model Profile、Prompt、Validator 和 Exporter
3. 初始化隔离数据库、Checkpoint 和导出目录
4. 运行 Deterministic Contract/Fault/Recovery Tests
5. 运行 Track A Agent-Isolated
6. 完成自动指标
7. 渲染 DOCX/PPTX
8. 执行盲化人工评分
9. 运行 Track B Integrated Journey
10. 运行故障与安全场景
11. 汇总质量、可靠性、延迟、成本和人工负担
12. 生成 Error Analysis
13. 保存 Run Manifest、Trace 和评审日志
```

---

## 23. 报告结构

正式报告至少包含：

1. 实验目的；
2. 数据集与任务分布；
3. CourseRAG Fixture/Index；
4. Template 和 Model；
5. CP-B0 与 CP-B10；
6. Lesson 指标；
7. Exam 指标；
8. PPT 指标；
9. Validation/Repair；
10. Interrupt/Recovery；
11. Model Routing；
12. Export/Template；
13. 系统级 Journey；
14. 故障和安全；
15. P50/P95、Token、成本；
16. Human Edit Burden；
17. 错误案例；
18. 限制；
19. 可用于 README/简历的结果。

---

## 24. 错误分析分类

### Planning

- 知识点遗漏；
- Session/题型/页面分配不合理；
- 时间/分值/页数预算错误；
- 约束冲突未识别。

### Generation

- 内容空泛；
- 事实错误；
- 超出证据；
- 重复；
- 结构与 Blueprint 不一致；
- 活动不可执行；
- 题干/答案/解析问题；
- PPT 文档化堆砌。

### Validation

- 漏报；
- 误报；
- Scope 错；
- Severity 错；
- Repair Strategy 错。

### Repair

- 未修复；
- 整件重写；
- 未授权字段改变；
- 新增回归；
- 修复后引用失效。

### HITL

- Interrupt 未触发；
- 修改丢失；
- 恢复错节点；
- 导出/写回授权混淆；
- 重复副作用。

### Export

- 文件无法打开；
- Layout 错；
- 溢出；
- 字体缺失；
- 引用渲染错；
- PPT 对象不可编辑。

### Integration

- Evidence/Index 版本错；
- Trace 断裂；
- CourseRAG 错误未隔离；
- 写回来源不完整；
- 跨课程数据泄漏。

---

## 25. 初始验收门槛

以下为工程发布门槛，不代表最终实验结果。

### 必须达到

- Test Contract Pass Rate = 100%；
- Citation Resolvability = 100%；
- Critical Defect-free Rate = 100%；
- Duplicate Side-effect Rate = 0；
- Unauthorized Action Rate = 0；
- Cross-course Leakage Rate = 0；
- Secret Leakage Count = 0；
- 六个 Interrupt 均可恢复；
- Export Render Success Rate = 100%；
- Test 运行无静默 Deterministic Fallback；
- 所有 Artifact 有 Template/Prompt/Model/Graph Version。

### 建议门槛

- Validation Issue Precision/Recall ≥ 0.90；
- Scope Localization Accuracy ≥ 0.90；
- Final Repair Success Rate ≥ 0.80；
- Unauthorized Modification Rate ≤ 0.05；
- Repair Regression Rate ≤ 0.05；
- Human Acceptable Rate ≥ 0.80；
- 各类 Artifact 人工均分 ≥ 4.0/5；
- Mean Edit Burden ≤ 1.5；
- Resume Success Rate ≥ 0.95；
- Completed Node Reuse Rate ≥ 0.95；
- Evidence Trace Coverage ≥ 0.95；
- Severe Overflow Case Rate = 0。

若 Pilot 显示某项阈值不合理，应在进入 Test 前修改并记录理由；不能在看到 Test 结果后调整门槛。

---

## 26. 简历指标使用规则

可以写入简历的内容必须来自：

- 锁定 Test；
- 可复现 Baseline；
- 真实模型；
- 无静默 Fallback；
- 人工审核；
- 明确任务数量；
- 明确指标口径；
- 保存报告和 Trace。

可能的表达形式：

```text
将教案、试卷和 PPT 三类工作流重构为可恢复的 LangGraph 流程，
在 30 条正式任务集上实现分层校验、定向修复和六类人工审批节点。
```

```text
通过试题 Batch 并行和 Main/Light 模型路由，在人工质量非劣条件下，
将 P95 生成延迟或平均模型成本降低 X%。
```

```text
构建 90 条故障注入和 60 条修复评测集，
使 Validation Issue 定位准确率达到 X%，定向修复成功率达到 Y%。
```

```text
实现 CoursePilot—CourseRAG Evidence Trace，
使教案、试题和 PPT 的有效引用覆盖率达到 X%，重复写回率为 0。
```

不得在实验完成前填写 X、Y。

---

## 27. 实施顺序

### Step 1：建立 Pilot

先准备：

- Lesson 3；
- Exam 3；
- PPT 3；
- Validation Fault 每类 10；
- Repair 每类 5；
- 六个 Interrupt 的基础 Approve/Edit；
- 1 个故障恢复 Journey。

验证 Schema、Runner、Renderer 和人工 Rubric。

### Step 2：冻结 Agent Fixtures

从 CourseRAG Dev 数据创建固定：

- ContextPackage；
- Knowledge Point Snapshot；
- Evidence Records。

### Step 3：运行 CP-B0

在重大 Agent 改造前保存当前：

- 结构；
- 内容；
- 延迟；
- Token；
- Fallback；
- Export；
- 人工评分。

### Step 4：专项开发与专项评测

- Validation → CP-DS4；
- Repair → CP-DS5；
- Checkpoint/Interrupt → CP-DS6；
- Template/Export → CP-DS7；
- Fault/Security → CP-DS8；
- Model Routing → Dev 任务；
- Exam Parallel → Exam Dev。

### Step 5：完成正式 30 条任务

- Dev 18；
- Test 12；
- 锁定 Rubric 和 Gold Constraint。

### Step 6：Track A 冻结 Test

比较 CP-B0 与 CP-B10。

### Step 7：Track B 系统 Journey

连接正式 CourseRAG Test Index，运行 SYS-DS1。

### Step 8：生成最终报告

输出 Agent、系统、成本、人工负担和简历指标。

---

## 28. 当前默认结论

- CoursePilot 正式任务集为 30 条；
- Pilot 另设 9 条；
- Dev/Test 为 18/12；
- Agent-Isolated 与 Integrated System 分开；
- 不构造唯一全文 Gold；
- 使用硬约束、Evidence 和人工 Rubric；
- Lesson、Exam、PPT 全部人工评测；
- 不使用 LLM-as-a-Judge；
- Validation Fault 约 90 条；
- Repair Set 约 60 条；
- 六个 Interrupt 均纳入恢复测试；
- 导出批准和写回批准分离；
- CP-B0 保留当前真实实现；
- CP-B10 为最终集成版本；
- Model Routing 从 Main/Light 两模型起步；
- 独立 Planner 仅作为 Dev 实验；
- PPT 以可编辑教学初稿为目标；
- 正式 Test 禁止静默 Fallback；
- 只有锁定 Test 和人工审核结果可进入简历。
