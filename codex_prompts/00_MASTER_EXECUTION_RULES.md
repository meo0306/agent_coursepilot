# Codex 主执行规则（建议复制为仓库根目录 `AGENTS.md`）

你正在改造 `meo0306/agent_coursepilot`。目标是按冻结文档集将项目逻辑拆分为 CourseRAG 与 CoursePilot，并完成可信评测。你必须把仓库事实与目标设计同时作为依据。

## 权威文档

始终先读取：

- `docs/refactor/frozen_v1.0/00_Document_Index_and_Decision_Baseline_v1.0.md`
- `docs/refactor/frozen_v1.0/07_Implementation_Roadmap_and_Task_Backlog_v1.0.md`
- `docs/refactor/EXECUTION_STATUS.md`
- `docs/refactor/DECISION_LOG.md`
- 当前阶段 Prompt 指定的文档。

## 通用执行规则

1. 一次只执行一个阶段，不提前实现后续阶段。
2. 修改前先审计仓库：相关文件、调用链、测试、数据库、配置和已有兼容行为。
3. 在 Plan 模式先给出：现状、差距、文件级计划、迁移/兼容风险、测试和回滚；用户批准后再修改。
4. 优先做最小、可测试、可回滚的改动；不要把多个独立大重构混在同一阶段。
5. 保持现有公开 API 可用，除非当前阶段明确要求版本化迁移。
6. 新代码遵守 Domain/Application/Infrastructure/API 边界；不要跨层直接访问具体数据库或 Provider。
7. 不在 CoursePilot 新代码中直接导入 CourseRAG Parser、Chunker、Chroma、BM25 等内部模块。
8. PostgreSQL 是业务事实源；Index、缓存和 Trace 不能成为唯一数据源。
9. 所有副作用必须幂等：构建、索引发布、导出、审批、Resume、写回和撤销。
10. 正式评测不得使用静默 Deterministic Fallback、LLM-as-a-Judge 或由系统输出反推 Gold。
11. GPT/LLM 可生成候选，正式 Gold 和人工 Rubric 必须由人工批准；不要自行把候选状态改为 approved。
12. 不把 Secret 写入代码、日志、报告、Manifest、LangSmith Metadata 或 Fixture。
13. 不硬编码外部 Provider 模型名；使用配置、Capability 和 Adapter。
14. 不无条件发送 reasoning/thinking 参数；先检查 Provider Capability。
15. 保留 MIT License 和上游 Attribution。更新作者信息时不得移除原许可证要求。
16. 除非用户明确要求，不执行 git commit、push、PR、破坏性数据库操作或数据删除。

## 代码质量

- Python 3.11+；
- Pydantic v2、SQLAlchemy 2；
- 类型清晰，避免宽泛 `Any` 扩散；
- 错误分类稳定，不吞异常；
- 配置有校验和安全默认值；
- 新增模块必须有 Unit/Contract/Integration Test；
- 外部 API 使用 Fake/Mock，真实集成测试默认 gated；
- 数据库迁移必须可验证升级，能否降级按阶段风险明确说明。

## 默认验收命令

优先使用仓库已有命令；若环境允许，至少执行：

```bash
uv sync --frozen
uv run pytest -q
uv run ruff format --check
uv run ruff check
uv run mypy src/
```

若全量命令受既有问题影响，必须同时运行当前阶段专项测试，并在阶段报告中区分“既有问题”和“本阶段回归”。不得只说“应该通过”。

## 每阶段结束必须更新

- `docs/refactor/EXECUTION_STATUS.md`
- `docs/refactor/DECISION_LOG.md`（只有产生新决策时）
- `docs/refactor/RISK_REGISTER.md`
- `docs/refactor/phase_reports/Pxx_*.md`

最终回复必须包含：

1. 完成的任务 ID；
2. 变更文件清单；
3. 数据库/API/配置变化；
4. 运行的命令和结果；
5. 专项评测结果；
6. 未完成项和风险；
7. 当前 Exit Gate 是否通过；
8. 下一阶段是否具备开始条件。
