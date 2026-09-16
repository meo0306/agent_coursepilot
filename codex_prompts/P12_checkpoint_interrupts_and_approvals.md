# Codex 阶段 Prompt：P12 PostgreSQL Checkpoint、六个 Interrupt 与审批

请在 **Plan 模式**执行本阶段。先完成审计和计划，不要在计划获批前修改代码。

## 阶段目标

把随机 Thread 和裸 Graph 编译改为可恢复、可编辑、可审计的业务工作流。

## 前置依赖

- 阶段依赖：P11
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

- P12-T01: 使用 PostgreSQL Checkpointer 编译 Graph，Thread ID 稳定关联 Task/Artifact。
- P12-T02: 实现六个 Interrupt Payload：Lesson Plan/Final、Exam Blueprint/Global、PPT Architecture/Final。
- P12-T03: 实现 Approve、Edit+Resume、Replan/Regenerate、Reject/Cancel 和过期处理。
- P12-T04: 人工修改创建新 Artifact Version，再通过 Command resume 恢复。
- P12-T05: 实现导出、写回和白名单内容的独立 Approval Scope。
- P12-T06: 实现 Task/Interrupt/Resume API、状态查询和幂等 Decision。
- P12-T07: 注入 Worker/服务重启、重复 Resume、版本变化和长时间暂停场景。
- P12-T08: 完成 CP-DS6 Pilot。

## 主要代码区域

- `src/coursepilot/runtime/checkpoint/`
- `src/coursepilot/runtime/interrupts/`
- `src/coursepilot/api/tasks.py`
- `src/coursepilot/api/approvals.py`

## 明确禁止

- 不得把导出批准和写回批准合并
- 不得在 Resume 时直接篡改历史 Checkpoint
- 不得重复高成本节点和副作用
- 不执行 P12 之后阶段的业务实现；只允许建立当前阶段必需的接口或 TODO。
- 不自行改变冻结产品决策。发现不兼容时写入 Decision Log 候选并说明最小安全默认方案。

## 必须验证

- Checkpoint/Resume
- Edit Preservation
- Duplicate Decision/Side Effect
- Stale Version Detection
- 运行主测试、Ruff 和 Mypy；如存在既有失败，提供证据并运行阶段专项测试。
- 检查 Secret、临时文件、未说明 Fallback 和破坏性迁移。

## Exit Gate

- 六个 Interrupt 均可暂停编辑恢复
- Completed Node Reuse 可测
- 重复副作用为 0

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
