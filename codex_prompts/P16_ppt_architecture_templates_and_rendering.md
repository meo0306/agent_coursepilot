# Codex 阶段 Prompt：P16 PPT Slide Architecture、模板导出与渲染检查

请在 **Plan 模式**执行本阶段。先完成审计和计划，不要在计划获批前修改代码。

## 阶段目标

生成可编辑教学 PPT 初稿，支持 Slide Architecture、Master/Layout、Notes、引用和渲染后校验。

## 前置依赖

- 阶段依赖：P10-P14,P11-P13
- 读取 `docs/refactor/EXECUTION_STATUS.md`，确认上游 Exit Gate 已通过。
- 检查当前 Git 状态并记录起始 Commit；不要覆盖用户未提交修改。

## 必须读取的文档

- `docs/refactor/frozen_v1.0/00_Document_Index_and_Decision_Baseline_v1.0.md`
- `docs/refactor/frozen_v1.0/07_Implementation_Roadmap_and_Task_Backlog_v1.0.md`
- `docs/refactor/frozen_v1.0/05_CoursePilot_Agent_Engineering_Upgrade_Plan_v1.0.md`
- `docs/refactor/frozen_v1.0/06_CoursePilot_and_System_Evaluation_Plan_v1.0.md`
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

- P16-T01: 实现 Slide Architecture：页型、课时来源、KP/Evidence、Layout、素材占位和页数预算。
- P16-T02: 接入 Architecture Review，支持增删、调整页序、页型和 Layout。
- P16-T03: 实现逐页内容、Speaker Notes、引用和素材 Placeholder 生成。
- P16-T04: 实现至少三套 PPTX Master/Layout 资源及 SlideType→Layout 映射。
- P16-T05: 实现表格、图形/图片占位、引用 Notes 和 Reference Slide。
- P16-T06: 实现 Overflow、Shape Boundary、Empty Placeholder、Font、可编辑对象和 Render Snapshot 检查。
- P16-T07: 按页面/字段定向 Repair，接入 Final PPT Review。
- P16-T08: 仅允许 verified_lesson_fragment 等白名单片段写回。
- P16-T09: 完成 CP-DS3、CP-DS7 Pilot 和一个用户模板导入验证。

## 主要代码区域

- `src/agents/coursepilot/ppt/`
- `src/coursepilot/exporters/pptx/`
- `resources/templates/ppt/`
- `src/coursepilot/rendering/`

## 明确禁止

- 不以商业级视觉设计为验收目标
- 不得继续只用默认 Title/Content Layout
- 不得把整份 PPT 大纲写回
- 不执行 P16 之后阶段的业务实现；只允许建立当前阶段必需的接口或 TODO。
- 不自行改变冻结产品决策。发现不兼容时写入 Decision Log 候选并说明最小安全默认方案。

## 必须验证

- Slide Architecture/Interrupt
- Layout/Placeholder Mapping
- PPTX Open/Render/Overflow
- Editable Object/Reference
- 运行主测试、Ruff 和 Mypy；如存在既有失败，提供证据并运行阶段专项测试。
- 检查 Secret、临时文件、未说明 Fallback 和破坏性迁移。

## Exit Gate

- PPTX 可打开、渲染和编辑
- 严重溢出为 0
- 页面引用可解析

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
