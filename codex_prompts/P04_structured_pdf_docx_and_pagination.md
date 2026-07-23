# Codex 阶段 Prompt：P04 结构化 PDF/DOCX 解析与 DOCX 分页

请在 **Plan 模式**执行本阶段。先完成审计和计划，不要在计划获批前修改代码。

## 阶段目标

实现 Canonical Document IR、Section Tree、结构化 PDF/DOCX 和可复现 DOCX 原始页码快照。

## 前置依赖

- 阶段依赖：P03
- 读取 `docs/refactor/EXECUTION_STATUS.md`，确认上游 Exit Gate 已通过。
- 检查当前 Git 状态并记录起始 Commit；不要覆盖用户未提交修改。

## 必须读取的文档

- `docs/refactor/frozen_v1.0/00_Document_Index_and_Decision_Baseline_v1.0.md`
- `docs/refactor/frozen_v1.0/07_Implementation_Roadmap_and_Task_Backlog_v1.0.md`
- `docs/refactor/frozen_v1.0/02_CourseRAG_PRD_v1.0.md`
- `docs/refactor/frozen_v1.0/03_CourseRAG_Evaluation_Dataset_and_Baseline_v1.0.md`
- `docs/refactor/frozen_v1.0/04_CourseRAG_Technical_Refactor_Plan_v1.0.md`
- `docs/refactor/DECISION_LOG.md`
- `docs/refactor/RISK_REGISTER.md`
- `codex_prompts/00_MASTER_EXECUTION_RULES.md` 或仓库根目录 `AGENTS.md`

## 先做只读审计

1. 找出本阶段相关代码、测试、配置、迁移、API 和调用链。
2. 对照冻结文档，列出“已满足、部分满足、未满足、文档与代码冲突”。
3. 识别兼容、数据迁移、Provider、性能、安全和回滚风险。
4. 检查本阶段 Pilot Fixture、Fake/Mock 和验收命令是否具备。
5. 给出文件级实施计划和提交/PR 拆分建议；不要提前实现后续阶段。

## 本阶段任务

- P04-T01: 实现 ParsedDocumentIR、PageIR、BlockIR、SectionIR、TableRecord、SourceSpan 和 ParseWarning。
- P04-T02: PDF 使用 PyMuPDF dict/rawdict 保留 Block/Line/Span、字体、BBox、图片和阅读顺序。
- P04-T03: DOCX 使用 python-docx 解析 Paragraph、Run、Heading、Numbering、Table、Break 和 Inline Shape。
- P04-T04: 实现固定 LibreOffice Headless Renderer Profile、字体包清单、PDF Snapshot Hash 和版本记录。
- P04-T05: 将 DOCX Block 对齐到渲染 PDF，保存 physical_page_index、display_page_label、section_page_index 和 alignment_confidence。
- P04-T06: 实现标题层级、目录辅助、页眉页脚/页码噪声标记、跨页段落合并和表格结构。
- P04-T07: 实现 Parse Preview/Quality Report 和低置信度 Warning。
- P04-T08: 使用 DS1 Pilot 的 Native PDF、DOCX 和布局压力页进行评测。

## 主要代码区域

- `src/courserag/parsers/`
- `src/courserag/domain/document.py`
- `resources/renderers/`
- `tests/courserag/parsers/`

## 明确禁止

- 不接 OCR 识别正文，OCR 页面仅输出待处理决策
- 不做最终 Chunk/KP
- 不伪造 DOCX 页码
- 不执行 P04 之后阶段的业务实现；只允许建立当前阶段必需的接口或 TODO。
- 不自行改变冻结产品决策。发现不兼容时写入 Decision Log 候选并说明最小安全默认方案。

## 必须验证

- Parser Unit/Golden Fixture
- DOCX Pagination Reproducibility
- Section Boundary/Heading Pilot
- 缺字体和低对齐置信度 Test
- 运行主测试、Ruff 和 Mypy；如存在既有失败，提供证据并运行阶段专项测试。
- 检查 Secret、临时文件、未说明 Fallback 和破坏性迁移。

## Exit Gate

- 相同 Renderer Profile 页码可重复
- DOCX 引用同时保留分页和结构 Anchor
- 结构化解析优于 B0 且无严重回归

## 计划输出格式

请按以下结构输出计划：

1. 仓库现状与差距；
2. 关键设计选择；
3. 文件级变更计划；
4. 数据库/API/配置和兼容策略；
5. 测试与专项评测计划；
6. 风险与回滚；
7. 任务 ID 到变更的映射；
8. 预计在本阶段明确不做的内容。

计划获批后，再按计划执行。执行结束时更新状态、风险和阶段报告，并逐项判断 Exit Gate。
