# CourseRAG / CoursePilot 展示素材索引

本目录集中保存从现有仓库中筛选出的展示界面内容源。材料以“能够公开、事实可追溯、适合重新编排”为筛选标准；原文件仍保留在原位置，本目录中的文件是独立副本。

## 推荐页面结构

### 1. 项目定位与演进

- [`01_story/courserag_story.md`](01_story/courserag_story.md)：CourseRAG 的定位、架构、设计取舍、指标和限制。
- [`01_story/coursepilot_story.md`](01_story/coursepilot_story.md)：CoursePilot 的工作流、Runtime、人工节点、Validation/Repair 和三类产物。
- [`01_story/monolith_to_two_services.md`](01_story/monolith_to_two_services.md)：从单体到双服务的演进路径、关键难点和失败反思，适合时间线或架构演进模块。

### 2. 架构图

- [`02_architecture/courserag_architecture.md`](02_architecture/courserag_architecture.md)：包含可直接由 Mermaid 渲染的 CourseRAG 架构图和服务边界。
- [`02_architecture/coursepilot_architecture.md`](02_architecture/coursepilot_architecture.md)：包含可直接由 Mermaid 渲染的 CoursePilot 工作流、持久化和跨服务边界。

### 3. Demo

- [`03_demo/demo_script.md`](03_demo/demo_script.md)：3 分钟和 5–8 分钟中文讲解脚本。
- [`03_demo/local_demo.md`](03_demo/local_demo.md)：双服务本地 Demo 的启动和验证说明。
- [`03_demo/local_demo_result.md`](03_demo/local_demo_result.md)：2026-08-26 已验证的本地 Demo 结果。
- [`03_demo/demo_local.py`](03_demo/demo_local.py)：现有确定性 Journey 脚本；可作为未来展示页 Live 模式的接口参考。

### 4. 指标与证据

- [`04_evidence/metrics_fact_sheet.json`](04_evidence/metrics_fact_sheet.json)：适合转成指标卡片的机器可读事实。
- [`04_evidence/claim_source_matrix.csv`](04_evidence/claim_source_matrix.csv)：关键表述与来源的对应关系，主要用于内容校核，不建议原样展示。
- [`04_evidence/courserag_evaluation.md`](04_evidence/courserag_evaluation.md)：CourseRAG 公开评测口径和限制。
- [`04_evidence/coursepilot_evaluation.md`](04_evidence/coursepilot_evaluation.md)：CoursePilot/P18 公开评测结论和质量边界。

### 5. 面试内容与表述边界

- [`05_interview/deep_dive.md`](05_interview/deep_dive.md)：18 个 Agent/RAG 技术深挖问题，可用于 FAQ 或演讲备注。
- [`05_interview/safe_claims.md`](05_interview/safe_claims.md)：可公开使用的项目表述。
- [`05_interview/prohibited_claims.md`](05_interview/prohibited_claims.md)：不得使用的夸大或失实表述，仅作内部校核，不应展示给访客。

## 公开边界

- P19 作品集发布 Gate 已通过；P18 正式内容质量 Gate 失败，两者必须同时说明。
- CourseRAG 指标来自小规模、课程特定 Dev 集，不代表开放域或生产效果。
- 本地 Demo 使用 deterministic generation 和标记过的 Demo Evidence，证明工程链路，不证明实时模型质量。
- 不公开正式 Gold、Test Fixture、教材正文、原始模型响应、Secret、凭据或内部人工审核数据。

## 本次未纳入的现有材料

- P14/P16/P18 人工审核 HTML：页面内嵌 Gold、教材片段、Evidence 标识和内部审核数据。
- P16/P18 原始 PPT 截图和 Office 文件：部分页面存在截断、空白、布局质量债务或正式评测标识，不适合直接作为作品集视觉材料。
- 课程原始 PDF/DOCX、评测数据集和 Provider 调用记录：不属于公开展示素材。

后续制作 HTML 时，优先把本目录作为内容源，重新生成脱敏架构图、Demo 状态截图和产物预览，不直接引用 `storage_eval/`、`human_review/` 或 `datasets/` 下的文件。
