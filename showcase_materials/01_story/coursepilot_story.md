# CoursePilot 独立项目故事

## 一句话定位

CoursePilot 是证据驱动的教师备课工作流 Agent：将教案、试卷和 PPT 生成拆成可暂停、可编辑、
可恢复、可校验、可局部修复和可审计的业务流程。

## Motivation

教师备课不是一次文本生成。任务通常包含资料选择、结构规划、内容生成、人工修改、全局校验、
导出和审核写回。把它们放进一个 Prompt 会产生：

- 中途无法确认结构；
- 失败后只能整件重跑；
- 人工修改容易被覆盖；
- 无法判断内容使用了哪个 Prompt、模型、模板和 Evidence；
- 导出、写回和 Resume 可能产生重复副作用。

因此系统采用 workflow-first、agent-enhanced，而不是追求完全自治 Agent。

## Runtime

```text
BusinessTask / Stable Thread
  → ContextPackageRef
  → Blueprint ArtifactVersion
  → Human Interrupt
  → Controlled Generation
  → ValidationReport
  → Targeted Repair
  → Final Review
  → Versioned Export
  → Optional Verified Writeback
```

CommonGraphState 只保存 Typed DTO、引用、Hash 和摘要，不保存完整教材、Secret 或无界模型消息。
PostgreSQL Checkpoint 支持服务重启后恢复；ArtifactVersion 和历史 Checkpoint 不可变。

## 六类人工节点

- Lesson Plan Review
- Lesson Final Review
- Exam Blueprint Review
- Exam Global Review
- PPT Architecture Review
- PPT Final Review

每个节点支持批准、字段编辑并恢复、重新规划/生成、拒绝或取消。导出和知识写回使用独立
Approval Scope，不能把“允许下载”解释成“允许写回知识库”。

## Validation 与 Repair

Validator 不返回裸字符串，而是返回包含 Code、Severity、Scope、Item ID 和 JSON Path 的
ValidationIssue。RepairPlanner 决定目标路径、前置条件和模型 Profile；LLM 不能自行扩大允许
修改范围。修复后同时重跑目标校验和全局约束，计算 Unauthorized Modification 与 Regression。

## 三条业务工作流

### Lesson

读取 CourseRAG 已审核 KP 和 Evidence，生成 Lesson Blueprint 与 Session；不再从 Context 重复
抽取 KP。Session 可独立修订，最终导出 DOCX，只有单个审核片段可以写回。

### Exam

Blueprint 固定题型、分值、难度、KP 和 Batch。Question Batch 有界并行，Fan-in 后稳定编号并
重新检查题量、总分、覆盖、重复和答案泄漏。只允许单题或解析写回。

### PPT

先生成 Slide Architecture，再逐页生成内容、Notes、Citation 和素材占位。导出使用多个真实
Layout 和可编辑 Office 对象，并通过 LibreOffice/Poppler 做 Open、Render、Overflow 和 Boundary
检查。只允许单页审核片段写回。

## Model Gateway

业务节点只引用逻辑 Profile，不硬编码 Provider。Capability Manifest 决定是否发送 structured
output、reasoning 或 thinking 参数。Evaluation 禁止静默换模和 deterministic fallback。
Main/Light 当前映射到同一实际模型，所以只证明逻辑路由能力，不宣称双模型成本收益。

## 真实评测结论

工程合同、Checkpoint、审批、幂等和导出链路完成，但 P18 正式内容质量 Gate 失败：24 项人工
审核中 7 minor、13 major、4 reject，Acceptable Rate 29.17%。这说明系统能够可靠执行工作流，
但生成质量仍不适合作为生产内容质量声明。

## 已知限制

- Lesson、Exam 和 PPT 内容质量仍依赖模型和 Prompt；
- Exam 全卷语义多样性和 PPT 页面密度存在债务；
- Streamlit 属于兼容 UI，不是项目重点，也不是生产前端；
- 当前作品集 Demo 主要证明系统边界和可恢复工作流，不是实时模型质量演示。
