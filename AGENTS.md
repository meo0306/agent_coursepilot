# Codex 主执行规则（建议复制为仓库根目录 `AGENTS.md`）

你正在改造 `meo0306/agent_coursepilot`。目标是按冻结文档集将项目逻辑拆分为 CourseRAG 与 CoursePilot，并完成可信评测。你必须把仓库事实与目标设计同时作为依据。

## 权威文档

始终先读取：

- `docs/refactor/frozen_v1.0/00_Document_Index_and_Decision_Baseline_v1.0.md`
- `docs/refactor/frozen_v1.0/07_Implementation_Roadmap_and_Task_Backlog_v1.0.md`
- `docs/refactor/EXECUTION_STATUS.md`
- `docs/refactor/DECISION_LOG.md`
- `docs/refactor/QUALITY_GATE_POLICY.md`（P10—P19 及跨阶段质量/性能决策）
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

## 功能交付优先与适度验证

本项目默认以可运行的功能增量为第一优先级。审计、Hash、冻结、Baseline、Gate、报告和测试是支持实现的手段，不得成为独立产出，也不得反复挤占功能开发、真实执行、模拟或测量的时间与上下文。

### 1. 默认工作顺序

1. 快速确认当前阶段、目标功能、相关调用链和直接约束。
2. 完成最小必要设计后尽快进入代码实现。
3. 运行与本次改动直接相关的专项测试或 Smoke Test。
4. 仅在阶段收尾、正式评测或高风险边界执行扩展验证和治理更新。

同一阶段已经读取并确认过的文档、仓库结构、版本、依赖和环境，不得在后续回合中无变化地重复核对。只有范围、代码、配置、依赖、数据或环境发生相关变化时才重新检查。

除非发现真实阻塞，执行阶段不得连续只做审计、计划、清单、Hash 核对或报告而不推进代码。

### 2. 默认不新增防御性机制

默认不新增以下机制：

- 文件、配置、Fixture、Prompt、Profile 或资源 Hash；
- 新的冻结 Contract、Snapshot、Baseline、Manifest 或版本身份；
- 新的 Gate、批准点、预注册步骤或阶段阻塞条件；
- 仅用于证明“没有变化”的重复验证脚本；
- 已能由 Git、数据库约束、类型系统或普通测试覆盖的自定义完整性机制。

只有同时满足以下条件时才允许新增：

1. 明确描述一个在本项目中现实可发生的具体失败场景；
2. 说明该失败可能造成的数据错误、跨课程泄漏、重复副作用、兼容破坏、安全问题或正式评测失真；
3. 分别说明 Git、版本号、主键、事务、唯一约束、外键、类型检查和普通测试为什么不足；
4. 证明新增机制比局部修复或普通测试更简单，并且会被实际运行或消费。

无法完成上述论证时，使用现有机制，不新增防线。不得仅因为“更严谨”“更可追溯”“以后可能需要”而增加治理设施。

### 3. 不扩大已有门禁

不为了简化而删除或绕过已经批准的安全措施、人工审批、正式 Gold 边界或发布要求；但也不得把它们泛化到无关的日常开发。

已有 Hash、Contract、Baseline 和 Gate 只在其原定边界生效，不自动扩展到新模块、普通 Fixture、内部数据结构或每次代码修改。历史阶段已有证据可以引用，不重复生成等价证据。

只有以下边界默认允许设置硬门禁：

- 不可逆或难以回滚的数据库迁移、删除和数据覆盖；
- 跨服务、跨仓库或公开 API/持久化合同的兼容变化；
- 鉴权、Secret、跨课程隔离、危险文件处理和外部工具执行；
- 写回、发布、导出、审批等可能产生重复副作用的操作；
- P10/P18 正式评测、Test 解锁、Gold 使用和公开指标；
- P19 正式发布、物理拆仓和生产部署。

普通内部重构、可逆配置调整、候选功能、默认关闭的实验能力和非正式 Dev 测量不得自动升级为阶段硬门禁。适合记录为质量债务的问题，不得仅为追求完美而阻塞后续功能。

### 4. 风险驱动的测试范围

默认执行与改动直接相关的最小充分验证：

- 纯函数或领域逻辑：专项 Unit Test；
- 公共 Port、API、Schema 或 Provider Adapter 变化：增加对应 Contract Test；
- 数据库、事务、索引、Checkpoint 或外部系统边界变化：增加对应 Integration Test；
- 用户可见工作流：至少运行一条代表性端到端 Smoke Path。

不得机械要求每个新增模块同时具备 Unit、Contract 和 Integration Test。测试类型必须与真实失败模式对应。

全量 `pytest`、Ruff、Mypy、迁移往返和正式评测原则上在阶段 Exit Gate 或受影响边界需要时各执行一次。修复后优先重跑失败项和受影响测试；没有代码、输入或环境变化时，不重复运行相同命令来获得相同结论。

不得为了提高覆盖率而测试无业务意义的实现细节，也不得为既有未触及模块补写大批测试后才开始当前功能。

### 5. 文档与报告保持轻量

仍按阶段要求更新 `EXECUTION_STATUS.md`、`RISK_REGISTER.md` 和阶段报告，但内容只记录：

- 实际完成的功能和任务 ID；
- 真实发生的 API、数据库和配置变化；
- 已运行的关键命令及结果；
- 尚未解决且会影响后续工作的风险；
- Exit Gate 结论和下一阶段条件。

没有新决策时不更新 `DECISION_LOG.md`。不得重复粘贴已有长篇背景、完整测试日志、未变化的 Hash 清单或历史阶段证据；优先引用已有文件和记录。

### 6. CoursePilot / CourseRAG 必须保留的边界

实现优先不意味着降低以下要求：

- 保持 CoursePilot 与 CourseRAG 的 Domain/Application/Infrastructure/API 边界；
- PostgreSQL 仍是业务事实源，索引、缓存和 Trace 不能成为唯一数据源；
- 写回、发布、导出、审批和 Resume 等真实副作用必须幂等；
- 不静默切换 Provider、模型、索引或 Deterministic Fallback；
- 不泄漏 Secret，不产生未授权访问或跨课程数据泄漏；
- 正式 Gold 和人工 Rubric 仍由人工批准，Codex 不自行批准候选；
- 正式 Test 不用于调参，不由系统输出反推 Gold；
- 不未经授权执行提交、推送、PR、数据删除或破坏性迁移。

这些要求应通过最直接的实现和最小充分测试保证，不再额外叠加同义 Hash、Snapshot、Gate 或审批层。

### 7. 与冻结文档和质量政策的关系

冻结文档明确指定的产品边界、阶段依赖、正式评测和发布要求继续执行。若冻结文档只在特定阶段或正式边界要求 Hash、Baseline、Contract Freeze 或 Gate，则只在该边界执行，不解释为日常开发的全局默认要求。

`QUALITY_GATE_POLICY.md` 中的 L0 安全与合同要求保持硬约束；L1 只保留真正代表当前阶段目标的少量指标；L2/L3 默认用于回归观察和诊断，不因细小波动或极小样本自动阻塞功能推进。

当治理要求与功能推进发生竞争时，优先完成可运行、可测试的功能闭环；只有具体风险已被证明会触及上述硬边界时，才扩大验证或暂停实现。
