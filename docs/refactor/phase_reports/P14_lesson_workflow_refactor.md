# P14 教案工作流重构阶段报告

## 结果

P14-T01—T09 的本地可运行闭环已建立。新路径以 CourseRAG Port 提供的 KnowledgePoint Snapshot 和
`purpose=lesson_generation` ContextPackage 为事实输入，生成带 Evidence 绑定的 Lesson Blueprint、
Session Artifact，并通过 P12 的 Session Plan / Final Review Interrupt 暂停和恢复。旧 Lesson API 和旧
Graph 保持兼容；未调用外部 Provider，也未读取或修改 Test。

## 现象、原因与方案

旧 Lesson Graph 在检索后仍有二次 KP 抽取、使用 Legacy Chunk 引用，且 P12 的 Lesson Interrupt 只是占位
边界，无法保证课时级证据绑定和编辑恢复。P14 将 KP 读取收窄为 CourseRAG Port，Context 作为不可信输入，
用稳定 Evidence ID 生成 Blueprint/Session；Session Plan 和 Final 分开 Interrupt，编辑使用允许路径并
创建新的 Artifact Version，完整教案不进入 Verified 写回。该方案避免重复事实源和整件副作用，同时保留
Legacy 默认行为以降低迁移风险。

## 完成项

- P14-T01/T02：新增 KP Snapshot 合同、Local/Remote/Mock 实现、Lesson Domain 模型和确定性 Evidence-bound Generator。
- P14-T03/T04：新增 Lesson Recoverable Graph；保留旧空状态兼容路径，完整输入走 Blueprint → Session Plan Review → 顺序 Session 生成 → Final Review。
- P14-T05/T06：新增 P14 Lesson Validator，检查时间、KP 覆盖和事实 Evidence；P12 编辑支持数组 JSON 路径和 Artifact-owned active version 校验。
- P14-T07/T08：新增独立 Scope Approval 的 target paths、版本化中性 DOCX Exporter 和 Verified Lesson Fragment Application Service；禁止整件写回。
- P14-T09：新增离线 `evaluation.p14_lesson_eval`，复用 Approved CP-DS1，不调用 Provider。

## 证据与测试

- CP-DS1 三个 Approved Pilot Case：3/3 通过；Evidence Coverage 为 1.0；Provider Calls 为 0。
- P12 Interrupt、P13 Validation/Repair、Legacy Lesson Graph/API：17 项专项测试通过。
- 全量测试：664 passed, 12 skipped。
- Ruff Format/Check、Mypy（430 source files）通过；Alembic head 保持 `0017_coursepilot_checkpoint_interrupts`。
- 版本化 DOCX 使用 `lesson_default_v1.docx` 模板生成并可重新打开。

## 质量债务与边界

P14 未进行真实模型质量/成本评测，P14-R03 保持“Provider run pending”；默认不启用外部调用。
数据库真实写回、导出审批端到端测试仍需在后续集成环境补充，但 Port、Evidence、Scope 和幂等边界已在
代码合同中收窄。P10.3 Detector 仍不是授权边界，Context 继续按不可信数据处理。

## Exit Gate

1. Session Plan 可人工编辑后恢复：通过（P12 Checkpoint/Decision + 数组路径版本化）。
2. 所有事实引用 Evidence：通过（Generator/Validator/CP-DS1 3/3，Coverage 1.0）。
3. 完整教案不会整件写回：通过（仅 `verified_lesson_fragment` 且必须提供 Session/Evidence scope）。

P14 状态为 `completed_with_quality_debt`：核心功能和离线合同通过，真实 Provider 运行和生产级数据库
端到端测量留作后续显式授权工作。P15 尚不自动开始，需先确认是否需要补做真实集成 Smoke。
