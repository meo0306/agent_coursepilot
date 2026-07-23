# Codex 阶段 Prompt：P14 教案工作流重构

请在 **Plan 模式**执行本阶段。先完成审计和计划，不要在计划获批前修改代码。

## 阶段目标

实现证据驱动的 Lesson Blueprint、Session 生成、两次人工审核和局部修订。

## 前置依赖

- 阶段依赖：P10-P13
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

- P14-T01: 从 CourseRAG 获取 KP Snapshot 和 purpose=`lesson_generation` ContextPackage。
- P14-T02: 实现 Lesson Blueprint/SessionPlan，知识点、Evidence、目标、时间和活动显式绑定。
- P14-T03: 接入 Session Plan Review，支持字段级修改和重新规划。
- P14-T04: 实现按 Session 受控生成；可试验并行，但先确保跨课时顺序和共享约束。
- P14-T05: 实现全局知识覆盖、时间、重复、Evidence 和教学逻辑校验。
- P14-T06: 按 ValidationIssue 对单 Session/字段定向 Repair。
- P14-T07: 接入 Final Review，分别批准导出和 verified_lesson_fragment 写回。
- P14-T08: 实现版本化 Lesson DOCX Export 和 Revision Diff。
- P14-T09: 完成 CP-DS1 Pilot 和 CP-B0 对比。

## 主要代码区域

- `src/agents/coursepilot/lesson/`
- `src/coursepilot/application/lesson_service.py`
- `resources/templates/lesson/`

## 明确禁止

- 不得从检索 Context 再调用 Lesson KP Extractor
- 不得把未审核完整教案写回
- 不得绕过 Session Plan Interrupt
- 不执行 P14 之后阶段的业务实现；只允许建立当前阶段必需的接口或 TODO。
- 不自行改变冻结产品决策。发现不兼容时写入 Decision Log 候选并说明最小安全默认方案。

## 必须验证

- Lesson Graph/Interrupt
- Coverage/Time/Grounding
- Targeted Revision
- DOCX Export
- 运行主测试、Ruff 和 Mypy；如存在既有失败，提供证据并运行阶段专项测试。
- 检查 Secret、临时文件、未说明 Fallback 和破坏性迁移。

## Exit Gate

- Session Plan 可人工编辑后恢复
- 所有事实引用 Evidence
- 完整教案不会整件写回

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
