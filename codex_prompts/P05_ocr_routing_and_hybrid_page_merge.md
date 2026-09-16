# Codex 阶段 Prompt：P05 OCR 页面路由与混合页合并

请在 **Plan 模式**执行本阶段。先完成审计和计划，不要在计划获批前修改代码。

## 阶段目标

实现按页 OCR 决策、Provider 抽象、坐标和置信度保留，以及混合页面去重合并。

## 前置依赖

- 阶段依赖：P04
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

- P05-T01: 实现 native/ocr/hybrid PageParseDecision 与可配置阈值。
- P05-T02: 实现 OCRProvider、至少一个轻量 Adapter，并为其他候选提供可插拔接口。
- P05-T03: 保存 Engine/Model/DPI/Image Hash、文本、BBox、Confidence 和 Warning。
- P05-T04: 实现原生 Block 与 OCR Block 坐标合并、重复文本去除和来源标记。
- P05-T05: 实现 OCR 失败、低置信度和资源上限的 `ready_with_warnings` 处理。
- P05-T06: 在 15 页 OCR Pilot 上比较候选引擎的 CER、路由、延迟、内存和部署复杂度。
- P05-T07: 冻结默认 OCR Profile，并在 Manifest 记录。

## 主要代码区域

- `src/courserag/parsers/page_classifier.py`
- `src/courserag/parsers/ocr/`
- `src/courserag/parsers/normalizer.py`

## 明确禁止

- 不在无 Gold 情况下永久锁定 OCR 引擎
- 不承诺公式、手写和极复杂版式完全正确
- 不执行 P05 之后阶段的业务实现；只允许建立当前阶段必需的接口或 TODO。
- 不自行改变冻结产品决策。发现不兼容时写入 Decision Log 候选并说明最小安全默认方案。

## 必须验证

- OCR Routing Precision/Recall
- CER Calculator
- Mixed Page Merge Test
- Resource Limit/Timeout Test
- 运行主测试、Ruff 和 Mypy；如存在既有失败，提供证据并运行阶段专项测试。
- 检查 Secret、临时文件、未说明 Fallback 和破坏性迁移。

## Exit Gate

- OCR Gold 可定位到页和区域
- 低置信度不静默通过
- 默认引擎选择有 Pilot 证据

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
