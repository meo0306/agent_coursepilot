# Codex 使用说明与阶段 Prompt 指南

**文档版本：** v1.0  
**文档状态：** 冻结执行版  
**冻结日期：** 2026-07-22

---

## 1. 推荐交付给 Codex 的目录

将整个冻结包复制到仓库：

```text
docs/refactor/frozen_v1.0/
├── 00_Document_Index_and_Decision_Baseline_v1.0.md
├── 01_...v1.0.md
├── 02_...v1.0.md
├── 03_...v1.0.md
├── 03A_...v1.0.md
├── 04_...v1.0.md
├── 05_...v1.0.md
├── 06_...v1.0.md
├── 07_Implementation_Roadmap_and_Task_Backlog_v1.0.md
└── 08_Codex_Execution_Guide_and_Phase_Prompts_v1.0.md

codex_prompts/
├── 00_MASTER_EXECUTION_RULES.md
├── P00_baseline_freeze_and_execution_scaffold.md
├── ...
├── P19_....md
├── 90_CONTINUE_AFTER_PLAN_APPROVAL.md
├── 91_INDEPENDENT_PHASE_VERIFICATION.md
└── 92_STATUS_AND_REPORT_TEMPLATES.md
```

同时在仓库建立：

```text
docs/refactor/EXECUTION_STATUS.md
docs/refactor/DECISION_LOG.md
docs/refactor/RISK_REGISTER.md
docs/refactor/phase_reports/
```

建议将 `00_MASTER_EXECUTION_RULES.md` 的内容复制为根目录 `AGENTS.md`。Codex 会把它作为长期执行约束；阶段 Prompt 只负责当前阶段的具体范围。

## 2. 不要一次把全部路线交给 Codex 执行

正确方式是：

```text
一个阶段
→ Plan 模式审计和计划
→ 人工检查计划
→ 继续执行
→ 独立验收
→ 更新状态
→ 再进入下一阶段
```

不推荐使用“根据所有文档完成全部改造”这一类总 Prompt。它会导致：

- Context 过长；
- 跨阶段提前实现；
- 数据模型、API 和 Graph 同时大改；
- 测试失败后难以定位；
- Codex 忘记人工 Gold、Interrupt 和评测门禁；
- 无法形成清晰的 Git/PR 历史。

## 3. 第一次启动 Codex

### 3.1 准备仓库

1. 将冻结文档和 Prompt Pack 放入仓库；
2. 保证当前改动已提交或明确保留；
3. 建立新分支，例如 `refactor/p00-baseline`；
4. 创建状态文件；
5. 不要提前删除旧 RAG 或旧 Graph。

### 3.2 首次输入

在 Codex Plan 模式中粘贴当前阶段 Prompt，例如 `P00_baseline_freeze_and_execution_scaffold.md` 的完整内容。

Codex 输出计划后，重点检查：

- 是否引用了正确的冻结文档；
- 是否先审计而不是凭空重写；
- 是否只包含本阶段；
- 是否保留公开 API 和旧基线；
- 是否列出测试、迁移和回滚；
- 是否把人工任务错误地自动化为 approved Gold。

计划通过后，粘贴 `90_CONTINUE_AFTER_PLAN_APPROVAL.md`。

完成后新开一次只读验收，粘贴 `91_INDEPENDENT_PHASE_VERIFICATION.md`。

## 4. 每个阶段给 Codex 哪些文档

Codex 能直接读取仓库文件时，不要反复把全文粘贴进聊天。阶段 Prompt 已列出必须读取的文件。

始终读取：

- 00 决策基线；
- 07 开发任务清单；
- Master Rules；
- Execution Status、Decision Log、Risk Register。

再按阶段读取产品、技术和评测文档。Codex 不需要在每个阶段重新读取所有文档。

## 5. 分支、Commit 和 PR

推荐一阶段一个主分支；复杂阶段可以拆多个小 PR，但仍归属于同一阶段报告。

```text
refactor/p00-baseline
refactor/p01-courserag-port
refactor/p02-eval-foundation
...
```

Codex 默认只修改工作区，不自动 Commit/Push。你检查测试和 diff 后，再明确要求其提交；需要发布时再使用单独的 Git/PR Prompt。

Commit Message 建议带阶段和任务：

```text
refactor(P04): add canonical PDF document IR
feat(P08): add BM25 and RRF retrieval
fix(P13): preserve untouched fields during repair
```

## 6. 如何处理上下文与长任务

- 只向 Codex开放当前阶段的目标、相关文档和代码；
- 阶段中断后，下一会话先让 Codex读取 Execution Status 和阶段报告；
- 大阶段按独立子模块执行，但不要拆出新的产品决策；
- 每个子模块完成立即运行专项测试；
- 不依赖聊天历史保存设计，关键结论写入仓库文档；
- 真实模型、OCR、Renderer 和数据库集成测试使用 gated 标记，默认测试不能依赖网络 Secret。

## 7. 需要你人工提供或批准的内容

### 可以晚些提供

- 1 套真实教案 DOCX 模板；
- 1 套真实 PPTX 模板；
- Main/Light Model、Embedding、Reranker API 配置；
- OCR 候选运行环境；
- 正式课程 PDF/DOCX Corpus。

系统内置模板和 Fake Provider 应先让开发流程可运行，这些材料不是 P00 的前置条件。

### 必须人工批准

- DS/CP-DS 正式 Gold；
- Knowledge Point Gold 和归并边界；
- QA Gold Claims 与 Evidence；
- CoursePilot 人工 Rubric；
- OCR/Reranker/Main/Light 最终选型；
- Interrupt 业务决策；
- Test 结果和简历指标。

Codex 可以生成候选、校验 Schema、去重和制作审核工具，但不能自行把候选升级为正式 Gold。

## 8. 遇到文档与代码不一致时

Codex 应：

1. 说明当前仓库事实；
2. 指出违反的冻结条款；
3. 给出最小迁移方案和兼容层；
4. 将需要改变冻结设计的事项写成 Decision Log 候选；
5. 继续完成不受冲突影响的安全任务；
6. 不静默修改产品边界。

只有涉及破坏性迁移、安全、跨服务合同或 Gold 口径时才需要暂停冲突部分等待人工决定。普通实现细节采用最小可配置默认值并记录。

## 9. 阶段 Prompt 索引

| 阶段 | 名称 | Prompt 文件 |
|---|---|---|
| P00 | 冻结基线与执行脚手架 | `P00_baseline_freeze_and_execution_scaffold.md` |
| P01 | 逻辑拆分与 CourseRAG Port | `P01_logical_split_and_courserag_ports.md` |
| P02 | 评测数据骨架与 B0 Runner | `P02_evaluation_schemas_and_b0_runner.md` |
| P03 | CourseRAG 持久化、版本与构建流水线 | `P03_courserag_persistence_versioning_and_build_pipeline.md` |
| P04 | 结构化 PDF/DOCX 解析与 DOCX 分页 | `P04_structured_pdf_docx_and_pagination.md` |
| P05 | OCR 页面路由与混合页合并 | `P05_ocr_routing_and_hybrid_page_merge.md` |
| P06 | Stable Evidence 与 Parent-Child Chunk | `P06_stable_evidence_and_hierarchical_chunking.md` |
| P07 | 课程级知识点资产流水线 | `P07_knowledge_point_asset_pipeline.md` |
| P08 | Hybrid Retrieval、RRF 与专用 Reranker | `P08_hybrid_retrieval_rrf_and_reranker.md` |
| P09 | Query Processing、Context Packing 与基础引用 QA | `P09_query_processing_context_and_qa.md` |
| P10 | CourseRAG 增量、写回、安全与正式评测 | `P10_courserag_incremental_writeback_security_and_eval.md` |
| P11 | CoursePilot 核心合同、Artifact、模板与模型网关 | `P11_coursepilot_runtime_templates_and_model_gateway.md` |
| P12 | PostgreSQL Checkpoint、六个 Interrupt 与审批 | `P12_checkpoint_interrupts_and_approvals.md` |
| P13 | 分层 ValidationIssue 与 Targeted Repair | `P13_validation_issues_and_targeted_repair.md` |
| P14 | 教案工作流重构 | `P14_lesson_workflow_refactor.md` |
| P15 | 试卷 Blueprint、Fan-out/Fan-in 与全局修复 | `P15_exam_blueprint_fanout_fanin.md` |
| P16 | PPT Slide Architecture、模板导出与渲染检查 | `P16_ppt_architecture_templates_and_rendering.md` |
| P17 | 系统集成、可靠性、安全与写回闭环 | `P17_system_integration_reliability_and_security.md` |
| P18 | CoursePilot 与系统正式评测 | `P18_coursepilot_and_system_evaluation.md` |
| P19 | 物理拆仓、CI/CD 与作品集收尾 | `P19_repository_split_ci_and_portfolio.md` |

## 10. 阶段完成后的检查清单

- [ ] 任务 ID 均有状态；
- [ ] Diff 未越过阶段边界；
- [ ] 新增行为有测试；
- [ ] API/数据库/配置变化已记录；
- [ ] 全量或专项测试结果有命令证据；
- [ ] 无 Secret、临时文件和静默 Fallback；
- [ ] 人工候选未被擅自批准；
- [ ] Execution Status、Risk 和 Phase Report 已更新；
- [ ] Exit Gate 逐项有证据；
- [ ] 下一阶段依赖明确。

## 11. 推荐的实际执行顺序

1. P00 和 P02 优先，确保旧基线和评测工具不丢；
2. P01 建立边界；
3. P03—P10 完成并冻结 CourseRAG；
4. P11—P13 建立 CoursePilot Runtime；
5. P14、P15、P16 分别迁移三条业务流；
6. P17 系统集成；
7. P18 正式评测；
8. P19 最后物理拆仓。

P14—P16 在 P13 完成后可以分别开分支并行开发，但它们共同依赖的 Schema、Validation、Template 和 Model Gateway 必须先冻结；合并前必须进行交叉集成测试。

## 12. 结果验收原则

Codex 的“已完成”不等于阶段完成。阶段完成以 07 中的 Exit Gate、实际测试输出、专项评测和人工审核为准。无法完成的项必须保持未勾选并说明原因，不能用 TODO、Mock 或文档描述代替真实实现。
