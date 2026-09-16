# P18 后 CoursePilot + CourseRAG 系统优化详细执行计划

- Document ID: `coursepilot.p18-post-optimization-execution-plan.v1`
- Status: `execution_plan_fixed`
- Fixed date: 2026-08-27
- Requirement baseline: `docs/system_optimization/P18_SYSTEM_OPTIMIZATION_REQUIREMENTS_AND_ROADMAP.md` v1.1
- Repository baseline: 当前 `D:\project\agent_coursepilot` 联合工作区，P19 Portfolio Release 已完成，P18 正式质量 Gate 保持失败且 Test 已消费
- Execution boundary: 本计划只定义后续执行，不授权立即修改代码、数据库、正式评测资产、Git 历史或外部仓库

## 1. 计划目标

本计划把需求基线中的 `OPT-FEAS`、`OPT-RAG`、`OPT-STRUCT`、`OPT-GROUND`、`OPT-EXAM`、`OPT-LESSON`、`OPT-PPT`、`OPT-TRACKB`、`OPT-PROFILE` 和 `OPT-EVAL` 映射为可逐阶段执行的工程任务。

最终目标不是让旧 P18 报告“变绿”，而是形成一个新的系统候选：

1. CoursePilot 能把教学任务转换为明确的证据需求；
2. CourseRAG 能返回面向 Lesson/Exam/PPT 的任务型 Context 和可解释 Adequacy；
3. 证据不足时系统补检索、缩范围或停止，不通过幻觉凑齐产物；
4. 结构、Grounding、教学质量、导出和真实系统链路分别通过 Gate；
5. 新候选在新的独立 Test 上一次性完成正式评测。

## 2. 当前仓库状态与实施起点

### 2.1 已具备的 CourseRAG 基础

- `src/courserag/contracts/` 已有 Search、Context、QA、Evidence、Knowledge Point、Verified Content 和 Capability 合同；
- `src/courserag/query/` 已有 Query Pipeline、Intent/Strategy、Multi-query 和 Trace；
- `src/courserag/retrieval/` 已有 Dense、Sparse、Hybrid/RRF、Rerank 和过滤边界；
- `src/courserag/context/` 已有 Context Packer、Evidence Boundary 和 Neighbor Expansion；
- `src/courserag/qa/sufficiency.py` 已有面向 QA 的 Evidence Sufficiency Gate；
- `src/courserag/persistence/` 已有 Query、Retrieval、Context、QA、Index 和写回事实；
- `src/courserag/api/` 已有稳定 v1 HTTP 边界；
- P08/P10 检索指标未显示必须重做 Embedding/Hybrid/Reranker。

### 2.2 已具备的 CoursePilot 基础

- `src/coursepilot/ports/courserag.py` 已定义完整 CourseRAG Consumer Port；
- Remote、Local 和 Mock Adapter 均已存在；
- `ContextPackageRef`、Context Binding 和 Stale Preflight 已存在；
- Lesson、Exam、PPT V2 Domain、Generator、Workflow、Validator、Repair 和 Versioned Exporter 已存在；
- Exam 已具备小批生成、Checkpoint 复用、全卷 Validation 和 Conflict Repair 骨架；
- PPT 已具备固定模板、可编辑导出和 LibreOffice Render 验证；
- Model Gateway 已支持 Profile、Capability 和禁止静默 Fallback。

### 2.3 当前明确缺口

1. CoursePilot 没有统一的任务可行性领域模型；
2. CourseRAG Context 合同不表达题量、课时、页数、知识点最低覆盖和材料类型；
3. QA Sufficiency 不能判断长内容生成的任务级充分性；
4. `purpose` 尚未真正驱动 Lesson/Exam/PPT 差异化 Query/Packing；
5. 请求级 Packing 配置尚未完整接通实际 Packer；
6. Lesson/Exam/PPT 没有统一消费 Adequacy 和补检索结果；
7. 应用层尚未完全拥有所有结构字段，LLM 结构错误仍可导致整件失败；
8. Citation ID 合法与 Claim 语义受支持仍未形成统一闭环；
9. Exam 缺少真实语义单元和认知操作级全卷规划；
10. Lesson 缺少事实层与教学组织层的强边界；
11. PPT 缺少叙事、视觉语义和投影可读性 Gate；
12. P18 Formal CourseRAG Index 不可恢复，现有 Track B Journey Runner 仍以状态合同为主；
13. CP-B10 复杂度、延迟和成本尚未证明边际收益。

### 2.4 工作树保护

当前工作树已有与本计划无关的未跟踪目录或文件，包括 `.tmp/`、`career_package/`、`human_review/`、`reports/` 以及一份数据集 Review Copy。所有阶段必须：

- 不删除、不移动、不覆盖这些资产；
- 不使用 `git reset --hard`、`git checkout --` 或清理工作树；
- 每阶段通过明确路径限制修改范围；
- 新评测产物使用新的目录和版本身份，不复用 P18 输出目录；
- 未经用户明确授权不 commit、push、创建 PR 或同步外部仓库。

## 3. 执行原则

1. 一次只执行一个 EP 阶段；上一阶段 Exit Gate 未通过时，不进入依赖它的下一阶段。
2. 先完成可运行功能闭环，再做阶段级扩展验证和轻量治理更新。
3. 公共 API/持久化合同只做加法或显式版本迁移；旧 v1 行为保持兼容。
4. 新能力先默认关闭或通过显式 Capability 启用，禁止静默切换。
5. 正式 Gold、人工 Rubric 和新 Test 必须由人工批准；Codex 只生成候选和工具。
6. P18 Test 保持不可读调参、不可重跑、不可修补。
7. PostgreSQL 是业务事实源；Index、Context、Cache 和 Trace 不能成为唯一事实源。
8. 不预先决定更换 Embedding、Reranker 或 LLM；先用 Dev 数据定位真正瓶颈。
9. 每阶段只新增与真实失败模式对应的测试，不机械补齐全部测试类型。
10. 所有阶段必须保留课程隔离、ACL、Secret、引用、幂等和无静默 Fallback 的 L0 边界。

## 4. 总体阶段与关键路径

| 阶段 | 名称 | 映射需求 | 优先级 | 复杂度 | 主要依赖 |
|---|---|---|---|---|---|
| EP-00 | 新 Dev 工作台与基线 | OPT-EVAL | P0 | M | 无 |
| EP-01 | CoursePilot 任务需求与可行性领域 | OPT-FEAS | P0 | M | EP-00 |
| EP-02 | CourseRAG 任务型合同与 Adequacy 基础 | OPT-RAG-001/002/009 | P0 | L | EP-01 |
| EP-03 | Purpose-aware Retrieval、Packing 与补检索 | OPT-RAG-003—008 | P0 | L | EP-02 |
| EP-04 | CoursePilot—CourseRAG 可行性闭环 | OPT-FEAS-005 | P0 | L | EP-03 |
| EP-05 | 确定性结构、失败隔离与 Resume | OPT-STRUCT | P0 | L | EP-04 |
| EP-06 | Claim-level Grounding | OPT-GROUND | P0 | L | EP-05 |
| EP-07 | Exam 全卷质量 | OPT-EXAM | P0 | L | EP-06 |
| EP-08 | Lesson 教学质量 | OPT-LESSON | P1 | M/L | EP-06 |
| EP-09 | PPT 叙事与视觉质量 | OPT-PPT | P1 | L | EP-08 |
| EP-10 | Dev/Formal Index 与真实 Track B | OPT-TRACKB | P0 | L | EP-04、EP-09 |
| EP-11 | Profile、延迟与成本消融 | OPT-PROFILE | P1 | M | EP-07—EP-10 |
| EP-12 | 新候选冻结与独立正式评测 | OPT-EVAL | P0 | L | EP-11 |

关键路径：

```text
EP-00
  ↓
EP-01 → EP-02 → EP-03 → EP-04 → EP-05 → EP-06
                                           ├→ EP-07 Exam ─────┐
                                           └→ EP-08 Lesson → EP-09 PPT
                                                              ↓
                                           EP-10 Real Track B/Index
                                                              ↓
                                           EP-11 Profile Ablation
                                                              ↓
                                           EP-12 Independent Test
```

EP-07 与 EP-08 在 EP-06 通过后可以由不同执行者并行，但单个执行者仍按 Exam → Lesson 顺序推进。EP-09 必须等待 EP-08，因为 PPT 应消费已合格 Lesson，而不是继续从薄 Evidence 直接凑页。

## 5. EP-00：新 Dev 工作台与可信基线

### 5.1 目标

建立不读取 P18 Test 的新开发测量环境，让后续每项功能修改都能在新的 Dev 证据上得到自动和人工反馈。

### 5.2 任务

| Task ID | 任务 | 输出 |
|---|---|---|
| EP00-T01 | 固定旧 P18 Test 隔离规则 | Dev Loader 明确拒绝 P18 Test/Blind 路径 |
| EP00-T02 | 定义联合 Dev Case Schema | Task Demand、Evidence Package、预期 Adequacy、Artifact Rubric |
| EP00-T03 | 构造薄/中/丰富三档候选 | Lesson/Exam/PPT 各覆盖三档证据容量 |
| EP00-T04 | 增加特殊材料切片 | 定义、比较、过程、公式、表格、数值、案例 |
| EP00-T05 | 增加失败重放类别 | Schema、Timeout、Missing Batch、Incomplete Group、Index Missing |
| EP00-T06 | 生成人工 Review Package | 不含系统自评 Gold，支持 Reviewer/时间/0—4 Burden |
| EP00-T07 | 记录当前 B0/B10 开发基线 | 自动合同、人工质量、请求、Token、延迟、成本 |

### 5.3 预计文件

新增：

- `src/evaluation/system_optimization/__init__.py`
- `src/evaluation/system_optimization/schemas.py`
- `src/evaluation/system_optimization/dev_loader.py`
- `src/evaluation/system_optimization/dev_data.py`
- `src/evaluation/system_optimization/review.py`
- `src/evaluation/system_optimization/baseline_runner.py`
- `tests/evals/system_optimization/`
- `datasets/system_optimization/v1/candidates/`
- `datasets/system_optimization/v1/approved/`，仅在人工批准后生成

复用但原则上不修改：

- `src/evaluation/p18_*`，只作为实现参考；
- `human_review/p18/` 和 `reports/p18/`，保持只读历史证据。

### 5.4 数据要求

- Dev Case 不复制 P18 Test 文本、ID、Gold 或盲审映射；
- 可以复现“薄证据生成长产物”等失败类别，但必须使用新的来源组合；
- 初始建议每类 Artifact 至少 9 个 Dev Case：薄/中/丰富各 3 个；
- Exam 至少包含 10、15、24、30 题需求；
- Lesson 至少包含 1、2、3 课时；
- PPT 至少包含 8、12、16 页；
- Adequacy Gold 和人工 Rubric 必须由人工批准后才进入正式 Dev 指标。

### 5.4.1 2026-08-30 已批准的 EP-00 返工覆盖项

首轮人工审核因 Evidence 与任务规模不匹配而得到 24 条 `request_changes`、3 条 `reject`
和 0 条 `approve`。Course Owner 选择“不新增 Evidence、缩小任务规模”的返工方案，因此
EP-00 的原始数量建议在 r2 Candidate 中调整为：Lesson 1/1/2 课时、Exam 2/4/6 题、PPT
3/5/7 页，分别对应 single/adjacent/non-adjacent 任务。27 条案例及每类 Artifact 的
thin/medium/rich 3/3/3 矩阵保持不变。该覆盖项仅适用于 EP-00 Dev 候选，不修改正式 Test
或产品 API 的数量合同；r2 仍须人工批准。

### 5.5 验证

```powershell
uv run pytest -q tests/evals/system_optimization
uv run python -m evaluation.system_optimization.dev_loader --check-only
uv run ruff check src/evaluation/system_optimization tests/evals/system_optimization
```

### 5.6 Exit Gate

- Loader 无法读取 P18 Test/Blind；
- 三类 Artifact 和三档证据容量均有新 Dev 候选；
- 人工批准边界明确；
- Baseline Runner 可以在无外部 Provider 模式下完成结构和数据检查；
- 没有修改旧 P18 数据、报告或锁。

### 5.7 回滚

删除本阶段新增的独立 Dev 包即可；不涉及 API、数据库和运行时行为。

## 6. EP-01：CoursePilot 任务需求与可行性领域

### 6.1 目标

在 CoursePilot 内部建立与具体检索实现无关的 Artifact Demand 和 Feasibility Decision，使系统能明确表达“需要什么证据”和“何时不应生成”。

### 6.2 任务

| Task ID | 任务 | Requirement |
|---|---|---|
| EP01-T01 | 定义 `ArtifactDemand` | OPT-FEAS-002 |
| EP01-T02 | 定义 `SemanticUnitRequirement` 和材料类型 | OPT-FEAS-001/002 |
| EP01-T03 | 定义 `FeasibilityStatus` 和 Decision | OPT-FEAS-003 |
| EP01-T04 | 实现 Lesson Demand Builder | 课时、KP、目标、案例/过程需求 |
| EP01-T05 | 实现 Exam Demand Builder | 题量、题型、难度、认知操作、刺激材料需求 |
| EP01-T06 | 实现 PPT Demand Builder | 页数、叙事角色、视觉材料需求 |
| EP01-T07 | 实现纯函数 Feasibility Evaluator | OPT-FEAS-004 |
| EP01-T08 | 定义补证据、缩范围、转人工用户状态 | `needs_more_evidence` 等 |

### 6.3 预计文件

新增：

- `src/coursepilot/domain/feasibility.py`
- `src/coursepilot/application/feasibility_service.py`
- `tests/coursepilot/feasibility/test_models.py`
- `tests/coursepilot/feasibility/test_service.py`

修改：

- `src/coursepilot/domain/task.py`：只在需要公开任务状态时增加兼容状态；
- `src/coursepilot/domain/__init__.py`：导出新领域模型；
- `src/coursepilot/runtime/state.py`：预留 Demand/Decision 状态，不接真实生成链路；
- Lesson/Exam/PPT 请求 Schema：仅增加可选字段或由现有字段推导 Demand。

### 6.4 设计约束

- Feasibility Evaluator 是确定性逻辑，不调用 LLM；
- 字符数只作为预警，不作为最终充分性标准；
- Demand 不包含 CourseRAG 内部 Chunk、Index 或 Provider 字段；
- 本阶段先使用 Fake Adequacy 测试，不修改 CourseRAG 公共 API；
- 不可行状态必须是正常业务结果，不包装为 500 Internal Error。

### 6.5 验证

```powershell
uv run pytest -q tests/coursepilot/feasibility
uv run pytest -q tests/coursepilot/runtime/test_context_resolver.py
uv run ruff check src/coursepilot/domain src/coursepilot/application tests/coursepilot/feasibility
uv run mypy src/coursepilot/domain src/coursepilot/application
```

### 6.6 Exit Gate

- Lesson/Exam/PPT Demand 可从现有任务请求确定性生成；
- 薄证据 Fake 被判定为 `needs_more_evidence` 或 `scope_reduction_required`；
- 中/丰富 Evidence Fake 可进入 `feasible`；
- 不同运行得到相同 Decision 和理由；
- 现有 API 和生成工作流行为未改变。

### 6.7 回滚

新领域模块保持未接线即可完全隔离；若新增了可选 Schema 字段，回滚前确认没有新版本持久化记录依赖该字段。

## 7. EP-02：CourseRAG 任务型合同与 Adequacy 基础

### 7.1 目标

建立 CoursePilot 与 CourseRAG 的版本化公共合同，并实现不依赖 LLM 的 Context Adequacy 统计。

### 7.2 任务

| Task ID | 任务 | Requirement |
|---|---|---|
| EP02-T01 | 定义 `GenerationContextRequirements` | OPT-RAG-001 |
| EP02-T02 | 定义 `GenerationContextRequest/Response` | OPT-RAG-001/002 |
| EP02-T03 | 定义 `ContextAdequacyReport` 和 Requirement Result | OPT-RAG-002 |
| EP02-T04 | 增加 Capability/Operation | OPT-RAG-009 |
| EP02-T05 | 增加 CourseRAG Application Service | 任务型 Context 入口 |
| EP02-T06 | 实现确定性 Evidence/Semantic Unit 统计 | OPT-RAG-002 |
| EP02-T07 | 增加新 HTTP Endpoint | 版本化加法 API |
| EP02-T08 | 扩展 CoursePilot Port/Remote/Local/Mock | 跨边界一致性 |
| EP02-T09 | 固定错误分类 | Invalid Demand、Index Not Ready、Unresolvable |

### 7.3 预计文件

新增：

- `src/courserag/contracts/generation_context.py`
- `src/courserag/context/adequacy.py`
- `src/courserag/context/generation_service.py`
- `tests/courserag/context/test_adequacy.py`
- `tests/contracts/test_generation_context_contract.py`

修改：

- `src/courserag/contracts/__init__.py`
- `src/courserag/contracts/service_info.py`
- `src/courserag/api/retrieval_qa.py`，或新增独立 `generation_context.py` Router；
- `src/courserag/api/__init__.py`
- `src/courserag/api/dependencies.py`
- `src/coursepilot/ports/courserag.py`
- `src/coursepilot/clients/remote_courserag.py`
- `src/coursepilot/adapters/local_courserag.py`
- `src/coursepilot/adapters/mock_courserag.py`
- `src/coursepilot/services/courserag_runtime.py`
- `tests/contracts/test_courserag_http_schema.py`
- `tests/contracts/test_courserag_contract.py`
- `tests/coursepilot/test_local_courserag_adapter.py`
- `tests/coursepilot/test_mock_courserag_service.py`

### 7.4 API 方案

首选新增操作：

```text
POST /api/courserag/v1/knowledge-bases/{course_id}/generation-contexts
```

请求返回一个封装对象：

```text
GenerationContextResponse
├── context: ContextPackage
└── adequacy: ContextAdequacyReport
```

不修改现有 `/contexts` 的响应类型，避免破坏当前 CoursePilot/外部调用者。Capability 明确声明是否支持任务型 Context。

### 7.5 数据库与持久化

默认不新增迁移：

- 优先使用现有 Context Package、Query/Retrieval Trace 和 JSON 字段；
- Requirements/Adequacy 先进入稳定响应和 Trace JSON；
- 只有在 EP-02 审计证明现有 JSON 事实无法支持 Resume、审计或正式身份时，才提出单独 Migration；
- 若必须迁移，使用 `0018_generation_context` 加法迁移，并验证 `0017 -> 0018 -> 0017 -> 0018`；
- 不删除或改写既有 P09/P10 Context 记录。

### 7.6 验证

```powershell
uv run pytest -q tests/courserag/context/test_adequacy.py
uv run pytest -q tests/contracts/test_generation_context_contract.py
uv run pytest -q tests/contracts/test_courserag_http_schema.py tests/contracts/test_courserag_contract.py
uv run pytest -q tests/coursepilot/test_local_courserag_adapter.py tests/coursepilot/test_mock_courserag_service.py
uv run ruff check src/courserag/contracts src/courserag/context src/coursepilot/ports src/coursepilot/clients src/coursepilot/adapters
uv run mypy src/courserag src/coursepilot/ports src/coursepilot/clients src/coursepilot/adapters
```

若有 Migration，再运行：

```powershell
uv run pytest -q tests/courserag/test_p09_migrations.py tests/courserag/test_p10_migrations.py
uv run python -m alembic heads
```

### 7.7 Exit Gate

- 新合同可序列化、OpenAPI 可见、Remote/Local/Mock 一致；
- 旧 `/search`、`/contexts`、`/qa` 合同不变；
- Adequacy 对固定 Context 产生确定性逐 Requirement 结果；
- Course/Index/Overlay/Evidence Tier 不匹配时 fail closed；
- Capability 缺失时 CoursePilot 不静默改用旧 Context；
- 无不必要数据库迁移。

### 7.8 回滚

通过关闭新 Capability 和移除新路由恢复旧行为；旧 v1 合同、数据和 Active Index 不受影响。

## 8. EP-03：Purpose-aware Retrieval、Packing 与补检索

### 8.1 目标

在现有检索基础上增加面向长内容生成的覆盖策略，不预先更换 Embedding/Reranker。

### 8.2 任务

| Task ID | 任务 | Requirement |
|---|---|---|
| EP03-T01 | 实现 Lesson/Exam/PPT Query Plan | OPT-RAG-003 |
| EP03-T02 | 按 KP/Content Role 分桶检索 | OPT-RAG-004 |
| EP03-T03 | 实现 Coverage-first Selector | OPT-RAG-004 |
| EP03-T04 | 保留 Complete Evidence Group | OPT-RAG-005 |
| EP03-T05 | 完整处理 Formula/Table/Procedure | OPT-RAG-005 |
| EP03-T06 | 接通请求级 Packing Options | OPT-RAG-006 |
| EP03-T07 | 增加 Purpose-specific Profiles | OPT-RAG-003/006 |
| EP03-T08 | 实现有界补检索与 Trace | OPT-RAG-007 |
| EP03-T09 | 增加任务型 Dev Metrics/Runner | OPT-RAG-008 |
| EP03-T10 | 对现有 P08/P10 指标做回归保护 | OPT-RAG-008/009 |

### 8.3 预计文件

新增：

- `src/courserag/query/generation_plan.py`
- `src/courserag/context/coverage_selector.py`
- `src/courserag/context/evidence_groups.py`
- `src/courserag/context/supplement.py`
- `resources/context_profiles/lesson_generation_v1.json`
- `resources/context_profiles/exam_generation_v1.json`
- `resources/context_profiles/ppt_generation_v1.json`
- `src/evaluation/system_optimization/courserag_metrics.py`
- `src/evaluation/system_optimization/courserag_runner.py`
- `tests/courserag/context/test_coverage_selector.py`
- `tests/courserag/context/test_evidence_groups.py`
- `tests/courserag/context/test_generation_service.py`

修改：

- `src/courserag/context/service.py`
- `src/courserag/context/packer.py`
- `src/courserag/context/models.py`
- `src/courserag/query/service.py`
- `src/courserag/query/pipeline.py`
- `src/courserag/query/models.py`
- `src/courserag/retrieval/service.py`，只在需要分桶/批量检索入口时修改；
- `src/courserag/contracts/retrieval.py`，仅做兼容性 Packing/Trace 补充；
- `tests/courserag/context/test_packer.py`
- `tests/courserag/query/test_service.py`
- `tests/courserag/query/test_pipeline.py`
- `tests/evals/test_p08_retrieval_eval.py`
- `tests/evals/test_p09_eval.py`

### 8.4 算法执行顺序

1. 根据 Requirements 生成确定性 Query Buckets；
2. 对每个 KP/Role 执行受限检索；
3. 合并候选并保留原始 Rank/Score/Trace；
4. 解析 Evidence Group、Parent、Previous/Next Neighbor；
5. 先满足强制 KP、Role 和 Modality；
6. 在剩余预算内按相关性和多样性补充；
7. 生成 Context Package 和 Adequacy；
8. 若缺口可补，执行一次或预注册次数的补检索；
9. 达到上限仍不足则返回明确不足状态。

### 8.5 关键规则

- Table：必须保留解题所需行列、表头和单位；
- Formula：必须保留符号定义、上下界和必要说明；
- Procedure：必须保留关键步骤及顺序；
- Cross-page：必须保留必要邻接；
- 每个强制 KP/Role 有最低预算，不能被单一高分命中挤出；
- 被丢弃的强制 Evidence 会使 Adequacy 失败；
- 补检索只检索尚缺内容，不重复完整初始请求；
- 不允许开放网络搜索；
- 不允许无限增加 Top-K 或 Token Budget。

### 8.6 验证

```powershell
uv run pytest -q tests/courserag/context tests/courserag/query
uv run pytest -q tests/evals/system_optimization
uv run pytest -q tests/evals/test_p08_retrieval_eval.py tests/evals/test_p09_eval.py
uv run ruff check src/courserag/context src/courserag/query src/evaluation/system_optimization
uv run mypy src/courserag/context src/courserag/query src/evaluation/system_optimization
```

有可用 Dev Index 时运行：

```powershell
uv run python -m evaluation.system_optimization.courserag_runner --split dev
```

### 8.7 Exit Gate

- 三类 Purpose 均产生可审计 Query Plan；
- `ContextRequest.packing` 实际影响选择，但不越过服务端硬上限；
- 必需 Formula/Table/Procedure/Neighbor 不被静默截断；
- 补检索达到上限后停止；
- 被判定 `adequate` 的 Dev Context 满足 Requirement Gate；
- 既有 P08/P10 检索主指标没有超出允许回归范围；
- 没有因为本阶段自动更换 Embedding/Reranker。

### 8.8 回滚

保留新合同，关闭任务型 Capability 或选择旧 QA Context Profile；不得在请求处理中静默回退。

## 9. EP-04：CoursePilot—CourseRAG 可行性闭环

### 9.1 目标

让 Lesson、Exam、PPT 在生成前真实调用任务型 Context，消费 Adequacy，并执行补检索、缩范围、转人工或继续生成。

### 9.2 任务

| Task ID | 任务 |
|---|---|
| EP04-T01 | 扩展 `ContextPackageRef` 保存 Requirements/Adequacy 身份和状态 |
| EP04-T02 | 扩展 `ContextResolver` 调用任务型 Context |
| EP04-T03 | 实现 Context Planning Application Service |
| EP04-T04 | Lesson Graph 增加 pre-generation feasibility node |
| EP04-T05 | Exam Graph 增加 pre-blueprint feasibility node |
| EP04-T06 | PPT Graph 增加 lesson-bound feasibility node |
| EP04-T07 | 实现有界 supplement/resume 状态 |
| EP04-T08 | API/Worker 返回稳定用户状态和缺口 |
| EP04-T09 | 增加三类真实 Context Smoke |

### 9.3 预计文件

新增：

- `src/coursepilot/application/context_planning_service.py`
- `tests/coursepilot/integration/test_generation_context_flow.py`

修改：

- `src/coursepilot/domain/context.py`
- `src/coursepilot/domain/runtime.py`
- `src/coursepilot/runtime/context_resolver.py`
- `src/coursepilot/runtime/state.py`
- `src/coursepilot/runtime/recoverable_graph.py`
- `src/agents/coursepilot/lesson/state.py`
- `src/agents/coursepilot/lesson/graph.py`
- `src/agents/coursepilot/exam/state.py`
- `src/agents/coursepilot/exam/graph.py`
- `src/agents/coursepilot/ppt/state.py`
- `src/agents/coursepilot/ppt/graph.py`
- `src/coursepilot/services/task_worker.py`
- 对应 Lesson/Exam/PPT API Schema/Route，只增加兼容状态和缺口字段；
- `tests/coursepilot/runtime/test_context_resolver.py`
- `tests/coursepilot/lesson/test_p14_workflow.py`
- `tests/coursepilot/exam/test_p15_exam_workflow.py`
- `tests/coursepilot/test_p16_ppt_validation.py`

### 9.4 状态机

```text
queued
→ resolving_context
→ evaluating_feasibility
   ├→ generating
   ├→ supplementing_context → evaluating_feasibility
   ├→ needs_more_evidence
   ├→ scope_reduction_required
   └→ needs_review
```

补检索必须继承 Task、Course、Trace、Index、Overlay 和上一 Context 身份。任何身份不一致都 fail closed。

### 9.5 API/数据库/配置影响

- API：增加可选 `feasibility_status`、`missing_requirements`、`context_adequacy` 摘要；
- 数据库：优先使用现有任务状态、Checkpoint 和 Artifact JSON；若新增枚举受 DB Check Constraint 限制，单独提出兼容 Migration；
- 配置：增加补检索最大轮次、请求和 Token 上限，默认保守且显式；
- 不允许自动替用户减少题量/课时/页数；只能返回建议，需用户或批准流程确认。

### 9.6 验证

```powershell
uv run pytest -q tests/coursepilot/integration/test_generation_context_flow.py
uv run pytest -q tests/coursepilot/runtime
uv run pytest -q tests/coursepilot/lesson/test_p14_workflow.py
uv run pytest -q tests/coursepilot/exam/test_p15_exam_workflow.py
uv run pytest -q tests/coursepilot/test_p16_ppt_validation.py
uv run pytest -q tests/contracts
```

### 9.7 Exit Gate

- Lesson/Exam/PPT 各一条真实 CourseRAG Context 流程通过；
- 明确不足任务不会调用内容生成模型；
- 补检索有上限且可 Resume；
- Course/Trace/Index 绑定全程一致；
- 旧 Context Resolver 路径仍可用于旧 API，但新路径不静默降级；
- 没有重复任务、Provider 调用或副作用。

### 9.8 回滚

通过显式关闭 Generation Context Capability 恢复旧路径；已产生的新状态保留可读，不能把 `needs_more_evidence` 改写为成功。

## 10. EP-05：确定性结构、失败隔离与 Resume

### 10.1 目标

消除 P18 中顶层 JSON、单对象代替集合、计数/总分、空输出和整件重做等结构性失败。

### 10.2 任务

| Task ID | 任务 |
|---|---|
| EP05-T01 | 定义 Lesson/Exam/PPT 内容 Draft Schema |
| EP05-T02 | 应用层锁定 ID、顺序、计数、分值、时长和页数 |
| EP05-T03 | LLM 只生成受限内容字段 |
| EP05-T04 | 顶层 Artifact 由应用层装配 |
| EP05-T05 | JSON、确定性、内容 Repair 分层 |
| EP05-T06 | 批次 Checkpoint 和失败批次 Resume |
| EP05-T07 | 完整 Artifact 前禁止导出/写回 |
| EP05-T08 | 重放四类 P18 失败模式的新 Dev 等价 Case |

### 10.3 预计文件

新增或扩展：

- `src/coursepilot/domain/generation_drafts.py`
- `src/coursepilot/application/artifact_assembly_service.py`
- `src/coursepilot/repair/json_repair.py`
- `src/coursepilot/repair/content_repair.py`
- `tests/coursepilot/generation/test_artifact_assembly.py`
- `tests/coursepilot/generation/test_failure_isolation.py`

修改：

- `src/agents/coursepilot/lesson/generator.py`
- `src/coursepilot/application/exam_workflow_service.py`
- `src/agents/coursepilot/ppt/generator.py`
- `src/coursepilot/llm.py`
- `src/coursepilot/runtime/checkpoint.py`
- `src/coursepilot/runtime/checkpoint_sync.py`
- `src/coursepilot/repair/service.py`
- `src/coursepilot/repair/planner.py`
- Lesson/Exam/PPT Prompts，缩小输出范围；
- 对应 Workflow 和 Provider 测试。

### 10.4 实施顺序

1. 先将顶层结构由应用层装配；
2. 再为每类 Artifact 引入最小 Content Draft；
3. 再实现批次级 Checkpoint；
4. 最后拆分 Repair；
5. 不在同一任务中同时重写语义质量和视觉质量。

### 10.5 验证

```powershell
uv run pytest -q tests/coursepilot/generation
uv run pytest -q tests/coursepilot/lesson/test_p14_model_generator.py
uv run pytest -q tests/coursepilot/exam/test_p15_exam_workflow.py
uv run pytest -q tests/evals/test_p16_provider_completion.py
uv run pytest -q tests/coursepilot/runtime
```

### 10.6 Exit Gate

- 新 Dev 结构合同通过率 100%；
- 单批失败保留此前成功批次；
- Resume 不重复 Provider 调用或副作用；
- 题数、总分、课时、页数、ID、顺序由程序保证；
- 无 Deterministic Fallback 被计为正式模型成功；
- 只有完整 Artifact 可以导出。

### 10.7 回滚

按 Artifact 类型逐一关闭新 Draft/Assembler；Checkpoint 新记录保留但不继续消费。不得把未完成 Artifact 标记为完整。

## 11. EP-06：Claim-level Grounding

### 11.1 目标

把“Evidence ID 合法”提升为“事实 Claim 得到 Evidence 语义支持”，同时允许教学行为、假设和讨论保持丰富度。

### 11.2 任务

| Task ID | 任务 |
|---|---|
| EP06-T01 | 定义 Claim Type 和 Support Relation |
| EP06-T02 | Lesson/Exam/PPT Draft 输出 Claim Binding |
| EP06-T03 | 数值、公式、实体、术语确定性校验 |
| EP06-T04 | Source Span/Support Summary 校验 |
| EP06-T05 | 区分事实、推导、教学行为、假设和讨论 |
| EP06-T06 | Unsupported Claim 安全 Repair |
| EP06-T07 | 导出前 Grounding Gate |
| EP06-T08 | Dev 人工 Claim 抽检和指标 |

### 11.3 预计文件

新增：

- `src/coursepilot/domain/grounding.py`
- `src/coursepilot/validation/grounding.py`
- `src/coursepilot/repair/grounding.py`
- `tests/coursepilot/validation/test_grounding.py`

修改：

- `src/coursepilot/domain/lesson.py`
- `src/coursepilot/domain/exam.py`
- `src/coursepilot/domain/ppt.py`
- `src/coursepilot/validation/service.py`
- `src/coursepilot/validation/exam.py`
- `src/coursepilot/validation/ppt_v2.py`
- `src/agents/coursepilot/lesson/generator.py`
- `src/agents/coursepilot/ppt/generator.py`
- Exam Generator/Repair 调用；
- `src/evaluation/system_optimization/review.py`
- Lesson/Exam/PPT Prompt。

### 11.4 兼容策略

- 现有 Citation/Evidence 字段保留；
- 新 Claim Binding 先作为加法字段；
- 旧 Artifact 缺少 Claim Binding 时标记 `legacy_unverified`，不得伪造支持；
- 正式新候选只接受新版本 Claim Binding；
- 不使用 LLM-as-a-Judge 作为正式语义支持结论。

### 11.5 验证

```powershell
uv run pytest -q tests/coursepilot/validation/test_grounding.py
uv run pytest -q tests/coursepilot/validation tests/coursepilot/test_validators.py
uv run pytest -q tests/evals/system_optimization
```

### 11.6 Exit Gate

- 正式事实 Claim 均有可解析 Evidence 和 Support；
- 无支持事实不会因挂接合法 ID 而通过；
- 教学行为和假设不会被误判为事实；
- 数值、公式、专名和枚举错误被确定性拦截；
- Dev 人工抽检达到预注册 Grounding 目标；
- Cross-course、Secret、Tool 和 Citation L0 保持为零。

### 11.7 回滚

新 Claim Validator 可按 Artifact Version 关闭；已标记 unsupported 的内容不得在回滚后自动发布。

## 12. EP-07：Exam 全卷质量

### 12.1 目标

解决 Exam 可接受率 0%、语义重复、难度虚高、答案线索和证据越界。

### 12.2 任务

| Task ID | 任务 |
|---|---|
| EP07-T01 | 从 Context Adequacy 构建 `SemanticUnitPool` |
| EP07-T02 | 定义 Cognitive Operation 和 Difficulty Evidence |
| EP07-T03 | Slot 分配真实语义单元，不使用 ordinal 唯一性 |
| EP07-T04 | 全卷记录 Used/Excluded Fact/Answer Signature |
| EP07-T05 | 增强语义重复和 Target Overlap 检测 |
| EP07-T06 | 增强 Cross-answer Leakage Graph |
| EP07-T07 | Blueprint/Batch 层冲突再规划 |
| EP07-T08 | 固定 Question Count/Score/Type 装配 |
| EP07-T09 | Exam Dev 自动评测和盲审 |

### 12.3 预计文件

新增：

- `src/coursepilot/domain/exam_planning.py`
- `src/coursepilot/application/exam_planning_service.py`
- `tests/coursepilot/exam/test_semantic_unit_plan.py`
- `tests/coursepilot/exam/test_exam_conflict_graph.py`

修改：

- `src/coursepilot/domain/exam.py`
- `src/coursepilot/application/exam_workflow_service.py`
- `src/coursepilot/validation/exam.py`
- `src/coursepilot/repair/exam.py`
- `src/agents/coursepilot/exam/graph.py`
- `src/coursepilot/prompts/exam/p15_generate_batch.md`
- `src/coursepilot/prompts/exam/p15_repair_question.md`
- `tests/coursepilot/exam/test_p15_exam_workflow.py`
- `tests/coursepilot/exam/test_p15_exam_graph.py`
- `tests/evals/test_p15_exam_eval.py`
- `src/evaluation/system_optimization/` Exam 指标和 Review。

### 12.4 关键算法边界

- 语义唯一性至少由 `semantic_unit_id + cognitive_operation + answer_basis` 表达；
- Difficulty 由信息组合、推理步数、迁移、干扰和材料复杂度决定；
- 语义容量不足直接回到 Feasibility，不循环改写；
- 单题 Repair 只处理局部问题；共享事实冲突回到 Batch/Blueprint；
- Embedding 相似度可作为诊断信号，但正式冲突结论需有可解释的 Unit/Target/Answer 依据。

### 12.5 验证

```powershell
uv run pytest -q tests/coursepilot/exam
uv run pytest -q tests/evals/test_p15_exam_eval.py tests/evals/test_p15_targeted_repair.py
uv run python -m evaluation.system_optimization.baseline_runner --artifact exam --split dev
```

### 12.6 Exit Gate

- Exam 结构合同 100%；
- 无伪多选、答案集合冲突、计数或总分失败；
- 语义重复、Target Overlap、Answer Leakage 达到预注册目标；
- 难度标签有可解释依据；
- Exam Dev Acceptable Rate ≥80%、Mean Rubric ≥4、Edit Burden ≤1.5、Critical Defect=0；
- 未使用 P18 Test 调参。

### 12.7 回滚

新 Exam Planning Profile 保持版本化；旧 Blueprint 仍可读取，不能混用新旧 Signature 进行 Resume。

## 13. EP-08：Lesson 教学质量

### 13.1 目标

解决 Lesson 事实扩写越界、主题拼接和活动材料不足，使输出能直接用于组织课堂。

### 13.2 任务

| Task ID | 任务 |
|---|---|
| EP08-T01 | Lesson Blueprint 分离事实层和教学组织层 |
| EP08-T02 | 定义可测量 Objective 结构 |
| EP08-T03 | 建立 Objective—Activity—Assessment 映射 |
| EP08-T04 | 活动增加材料、步骤、产出和评价 |
| EP08-T05 | 限制跨不相邻主题拼接 |
| EP08-T06 | 区分 Evidence Fact 与教学假设/讨论 |
| EP08-T07 | Lesson 专项 Validator/Repair |
| EP08-T08 | Lesson Dev 自动评测和盲审 |

### 13.3 预计文件

新增：

- `src/coursepilot/domain/lesson_planning.py`
- `src/coursepilot/validation/lesson_v2.py`
- `tests/coursepilot/lesson/test_lesson_alignment.py`

修改：

- `src/coursepilot/domain/lesson.py`
- `src/agents/coursepilot/lesson/models.py`
- `src/agents/coursepilot/lesson/generator.py`
- `src/agents/coursepilot/lesson/validation.py`
- `src/agents/coursepilot/lesson/graph.py`
- `src/coursepilot/prompts/lesson/p14_plan_blueprint.md`
- `src/coursepilot/prompts/lesson/p14_generate_session.md`
- `src/coursepilot/prompts/lesson/p14_repair_session.md`
- `src/coursepilot/exporters/lesson_versioned_exporter.py`
- `tests/coursepilot/lesson/test_p14_model_generator.py`
- `tests/coursepilot/lesson/test_p14_workflow.py`
- `tests/evals/test_p14_lesson_eval.py`

### 13.4 验证

```powershell
uv run pytest -q tests/coursepilot/lesson
uv run pytest -q tests/evals/test_p14_lesson_eval.py
uv run python -m evaluation.system_optimization.baseline_runner --artifact lesson --split dev
```

### 13.5 Exit Gate

- 每个核心目标都有活动和评价；
- 每个活动有材料、步骤和预期产出；
- 不相邻主题不会被强行放入同一课时；
- 事实 Claim Grounding 通过；
- Lesson Dev Acceptable Rate ≥80%、Mean Rubric ≥4、Edit Burden ≤1.5、Critical Defect=0。

### 13.6 回滚

保留旧 Lesson Artifact 读取和导出；新规划仅对新 Artifact Version 生效。

## 14. EP-09：PPT 叙事与视觉质量

### 14.1 目标

让 PPT 从“可打开的文字列表”提升为可投影、可编辑、叙事清楚的教学演示文稿。

### 14.2 任务

| Task ID | 任务 |
|---|---|
| EP09-T01 | 从已合格 Lesson 生成 Slide Narrative |
| EP09-T02 | 定义 Slide Role 和跨页叙事约束 |
| EP09-T03 | 建立 Content Role → Visual Type 映射 |
| EP09-T04 | 生成可编辑表格、流程、层级、比较和活动元素 |
| EP09-T05 | 增加最小字号、密度、留白和重复检测 |
| EP09-T06 | 增加连续布局多样性和标题语义校验 |
| EP09-T07 | 完整 Speaker Notes 和 Citation |
| EP09-T08 | 真实 LibreOffice Render QA |
| EP09-T09 | PPT Dev 视觉盲审 |

### 14.3 预计文件

新增：

- `src/coursepilot/domain/ppt_narrative.py`
- `src/coursepilot/validation/ppt_visual.py`
- `tests/coursepilot/ppt/test_ppt_narrative.py`
- `tests/coursepilot/ppt/test_ppt_visual_validation.py`

修改：

- `src/coursepilot/domain/ppt.py`
- `src/agents/coursepilot/ppt/generator.py`
- `src/agents/coursepilot/ppt/graph.py`
- `src/coursepilot/application/ppt_workflow_service.py`
- `src/coursepilot/validation/ppt_v2.py`
- `src/coursepilot/templates/ppt.py`
- `src/coursepilot/exporters/pptx/exporter.py`
- `src/coursepilot/rendering/pptx.py`
- `src/coursepilot/prompts/ppt/p16_plan_architecture.md`
- `src/coursepilot/prompts/ppt/p16_generate_slide.md`
- `src/coursepilot/prompts/ppt/p16_repair_slide.md`
- `resources/templates/ppt/*.yaml`
- `tests/coursepilot/test_p16_ppt_validation.py`
- `tests/evals/test_p16_ppt_eval.py`

### 14.4 视觉规则初始范围

- 标题页和参考页固定身份；
- 内容页最小字号、文本行数和占用面积设为 Profile 配置；
- 表格、流程、层级和比较必须使用可编辑对象；
- 连续页面不能全部使用同一文字列表布局；
- 同义标题和 Evidence 轮转重复进入诊断；
- 薄证据优先合并页或请求缩页，不制造新事实；
- 规则阈值必须在新的 PPT Dev Render 上校准后冻结。

### 14.5 验证

```powershell
uv run pytest -q tests/coursepilot/ppt tests/coursepilot/test_p16_ppt_validation.py
uv run pytest -q tests/evals/test_p16_ppt_eval.py
docker compose -f compose.eval-pptx.yaml run --rm pptx-qa
uv run python -m evaluation.system_optimization.baseline_runner --artifact ppt --split dev
```

### 14.6 Exit Gate

- 所有 PPTX 可打开并完成固定 Renderer 渲染；
- 页数、Citation、Notes 和可编辑对象完整；
- 最小字号、过度留白、文本密度和连续重复达到冻结阈值；
- PPT Dev Acceptable Rate ≥80%、Mean Rubric ≥4、Edit Burden ≤1.5、Critical Defect=0；
- 人工不再要求整体重排。

### 14.7 回滚

视觉 Profile 和 Template 版本化；旧 PPT Artifact 可继续使用旧 Exporter Profile，不覆盖已导出文件。

## 15. EP-10：Dev/Formal Index 与真实 Track B

### 15.1 目标

修复 P18 7/8 live journey 因 Formal Index 缺失被阻塞的问题，并把 Journey Runner 从状态模拟升级为真实服务流程。

### 15.2 任务

| Task ID | 任务 |
|---|---|
| EP10-T01 | 固定可重复构建的 Dev Index |
| EP10-T02 | 从干净环境恢复/构建并 Probe Dev Index |
| EP10-T03 | 定义 Formal Index Candidate 身份和 Manifest |
| EP10-T04 | 实现真实 HTTP Journey Runner |
| EP10-T05 | 查询、Context、生成、审批、导出、写回 Journey |
| EP10-T06 | Resume、Lease、重复请求和副作用核验 |
| EP10-T07 | PostgreSQL 状态和 CourseRAG 检索结果核验 |
| EP10-T08 | 新正式候选前 Clean-room Preflight |

### 15.3 预计文件

新增：

- `scripts/system_optimization/build_dev_index.py`
- `scripts/system_optimization/probe_index.py`
- `src/evaluation/system_optimization/track_b_runner.py`
- `tests/system/test_optimization_journeys.py`
- 新的 Dev Compose Override；是否新增文件在阶段审计时决定。

修改：

- `compose.p18.yaml` 不直接覆盖历史用途；优先新增新版本 Compose；
- `src/evaluation/p18_track_b.py` 保留为历史实现，不修改其正式结果；
- `src/evaluation/system_optimization/` 新 Runner；
- `tests/system/test_p17_postgres_writeback_loop.py` 仅在公共边界变化时更新；
- `src/courserag/api/service_info.py` / Capability Probe；
- CoursePilot/CourseRAG Dockerfile 或配置仅在 Clean-room 缺依赖时修改。

### 15.4 Formal Index 身份至少绑定

- Course IDs；
- Source Documents 和 Versions；
- Parsed/Chunk/Evidence Version；
- Embedding/Retrieval/Profile Version；
- Primary/Verified Overlay Active Version；
- PostgreSQL Migration Head；
- 构建输入和输出校验身份；
- 恢复命令及 Probe 结果。

不新增仅用于证明“没有变化”的重复 Hash；只复用索引发布和正式评测已需要的现有身份。

### 15.5 验证

```powershell
docker compose -f <new-dev-compose> up -d --build
uv run python scripts/system_optimization/probe_index.py --course-id <dev-course>
uv run pytest -q tests/system/test_optimization_journeys.py
uv run pytest -q tests/system/test_p17_postgres_writeback_loop.py
```

正式候选前从空数据库/空卷执行一次构建或恢复，不允许依赖历史 Docker Volume。

### 15.6 Exit Gate

- Dev Index 可从干净环境重复构建或恢复；
- 指定课程 Search、Context 和 Evidence Probe 通过；
- 8/8 代表性 Journey 走真实 HTTP/Application 边界；
- 数据库状态和实际副作用与响应一致；
- 重复请求不重复导出或写回；
- 不使用 Track A Gold Fixture 伪装正式索引；
- Formal Index Candidate 在新 Test 冻结前可验证。

### 15.7 回滚

停止新 Compose/服务并保留构建日志；不删除数据库或索引。Active Index 回退必须使用已有发布指针操作和明确授权。

## 16. EP-11：Profile、延迟与成本消融

### 16.1 目标

在质量闭环通过后，验证每个 Planner、Generator、Validator 和 Repair 节点的边际收益，降低 CP-B10 的请求、Token、延迟和成本。

### 16.2 固定消融顺序

```text
B0
→ + Task Feasibility / Adequacy
→ + Deterministic Structure
→ + Task Planner
→ + Claim Grounding
→ + Bounded Repair
```

### 16.3 任务

| Task ID | 任务 |
|---|---|
| EP11-T01 | 输出逐节点请求、Token、Latency、Cost |
| EP11-T02 | 删除无价值调用和重复 Context 构建 |
| EP11-T03 | 缩小 Prompt Context 和 Output Schema |
| EP11-T04 | 调整批次、并发和 Checkpoint 复用 |
| EP11-T05 | 关闭低复杂度节点高 Reasoning |
| EP11-T06 | 核实 main/light 实际 Provider/Model 差异 |
| EP11-T07 | 执行有界 Profile Ablation |
| EP11-T08 | 人工质量与性能联合决策 |

### 16.4 预计文件

- `resources/model_profiles/` 新候选，不覆盖旧 Profile；
- `resources/context_profiles/` 新候选；
- `src/coursepilot/models_gateway/`，仅在 Capability/Trace 缺口时修改；
- `src/coursepilot/llm.py`，仅做测量和明确配置；
- `src/evaluation/system_optimization/profile_runner.py`；
- `tests/coursepilot/test_llm_infra.py`；
- `tests/evals/system_optimization/`。

### 16.5 保留规则

新增层只有同时满足以下条件才保留：

- 人工质量或结构可靠性有可解释提升；
- L0 和正式合同不下降；
- P95/单位成本增幅不超过预注册容忍度，或获得明确批准；
- 不引入静默 Fallback、模型切换或不可审计 Repair。

### 16.6 Exit Gate

- 选择唯一候选 Profile；
- Lesson/Exam/PPT 人工质量仍达标；
- Track B 和结构 Gate 无回归；
- 请求、Token、P50/P95 和成本在预算内；
- main/light 实际映射和 Capability 可验证；
- 未使用新 Test 数据做选择。

### 16.7 回滚

候选 Profile 默认不覆盖当前配置；回滚为选择上一通过的 Dev Profile，不在运行时静默切换。

## 17. EP-12：新候选冻结与独立正式评测

### 17.1 启动条件

只有以下条件全部满足才允许启动：

- EP-00—EP-11 均通过；
- 三类 Artifact Dev 人工 Gate 通过；
- CourseRAG Task Context Gate 通过；
- 8/8 Dev Journey 通过；
- 唯一代码、Prompt、Profile、配置和 Index Candidate 已选择；
- 新 Gold、Rubric、Review 和 Test Release 已完成人工批准；
- P18 Test 未参与调参或新 Gold 构造。

### 17.2 任务

| Task ID | 任务 |
|---|---|
| EP12-T01 | 冻结代码/Prompt/Profile/Config/Index 身份 |
| EP12-T02 | 锁定新独立 Test 和人工 Review Protocol |
| EP12-T03 | 执行 Preflight 和预算核验 |
| EP12-T04 | 一次执行 Track A |
| EP12-T05 | 一次执行真实 Track B |
| EP12-T06 | 执行预注册 Stability |
| EP12-T07 | 完成 100% 人工 Review 和 20% Repeat Blind Review |
| EP12-T08 | 生成单一正式报告和 Gate 结论 |

### 17.3 正式 Gate

CourseRAG Task Context：

- Context/Evidence 可解析率 100%；
- Required KP/Modality/Complete Group Coverage 100%；
- 不足 Context 被误判为 `adequate` 为 0；
- 补检索预算越界和静默切换为 0。

CoursePilot 自动技术：

- 预期 Artifact 生成完整率 100%；
- Schema/Contract 通过率 100%；
- 导出、打开/渲染完整率 100%；
- Citation/Trace 完整率 100%；
- Stability 中 Provider/合同失败为 0。

人工质量，总计和每类 Artifact 分别满足：

- Acceptable Rate ≥80%；
- Mean Rubric ≥4.0；
- Mean Edit Burden ≤1.5；
- Critical Defect=0；
- Review 完备率 100%。

系统：

- 真实 Track B Journey 8/8；
- Cross-course、Unauthorized、Secret、Duplicate Side Effect、Silent Fallback、Dangerous Tool、Unresolved Citation 均为 0。

### 17.4 失败处理

- 任何正式 Gate 失败都保留原结果；
- 不在同一 Test Release 上调参、修补或重跑；
- 不降低阈值；
- 不把失败改写为 `completed_with_quality_debt`；
- 后续修复进入新的 Dev 版本和新的独立 Test。

## 18. Requirement—Execution 映射

| Requirement | 执行阶段 |
|---|---|
| OPT-FEAS-001—004 | EP-01 |
| OPT-FEAS-005 | EP-02—EP-04 |
| OPT-RAG-001/002/009 | EP-02 |
| OPT-RAG-003—008 | EP-03 |
| OPT-STRUCT-001—004 | EP-05 |
| OPT-GROUND-001—004 | EP-06 |
| OPT-EXAM-001—004 | EP-07 |
| OPT-LESSON-001—004 | EP-08 |
| OPT-PPT-001—004 | EP-09 |
| OPT-TRACKB-001—003 | EP-10 |
| OPT-PROFILE-001—004 | EP-11 |
| OPT-EVAL-001—005 | EP-00、EP-03、EP-07—EP-12 |

## 19. 跨阶段 API、数据库和配置总览

| 边界 | 预计变化 | 首个阶段 | 兼容策略 |
|---|---|---|---|
| CourseRAG Contract | Generation Context/Adequacy | EP-02 | 新合同/新操作，加法兼容 |
| CourseRAG HTTP | generation-contexts Endpoint | EP-02 | 旧 search/context/qa 不变 |
| CourseRAG Capability | 支持任务型 Context | EP-02 | 显式声明，缺失不静默降级 |
| Context Packing | 请求级和 Purpose Profile | EP-03 | 服务端硬上限继续生效 |
| CoursePilot Port | build_generation_context | EP-02 | Remote/Local/Mock 同步 |
| CoursePilot Task Status | needs_more_evidence 等 | EP-04 | 加法状态；旧状态可读 |
| Artifact Schema | Draft/Claim Binding/Planning 字段 | EP-05—EP-09 | 新版本写、旧版本读 |
| PostgreSQL | 默认复用 JSON；必要时 0018 | EP-02/EP-04 审计后 | 加法迁移和往返验证 |
| Profiles | generation context/model/visual | EP-03/EP-09/EP-11 | 新候选文件，不覆盖旧默认 |
| Compose/Index | 新 Dev/Formal Candidate | EP-10 | 不覆盖 P18 历史 Compose/结果 |

## 20. 每阶段统一交付格式

每个 EP 阶段结束必须提供：

1. 完成的 EP Task ID 和 Requirement ID；
2. 实际变更文件；
3. API、数据库、配置变化；
4. 执行命令和实际结果；
5. 专项 Dev/人工评测结果；
6. 未完成项和风险；
7. 本阶段 Exit Gate；
8. 下一阶段是否具备开始条件；
9. 若产生新架构决策，再更新 `DECISION_LOG.md`；否则不更新；
10. 轻量更新 `EXECUTION_STATUS.md`、`RISK_REGISTER.md` 和对应阶段报告。

## 21. 全量收敛验证

阶段专项测试全部通过、准备新正式候选时执行一次：

```powershell
uv sync --frozen
uv run pytest -q
uv run ruff format --check
uv run ruff check
uv run mypy src/
uv run python -m alembic heads
git diff --check
```

此外执行：

- CourseRAG Dev Index clean-room build/restore；
- CoursePilot + CourseRAG Compose Smoke；
- Lesson/Exam/PPT 各一条真实端到端路径；
- PostgreSQL Resume/Idempotency/Writeback 集成；
- PPT 固定 Renderer；
- 新 Dev 自动评测和人工 Gate；
- Secret、跨课程、工具、Fallback 和 Test 泄漏检查。

全量命令若因既有未触及问题失败，必须区分既有问题与本轮回归，并同时提供受影响阶段专项测试的真实结果。

## 22. 启动建议

下一步只启动 `EP-00`，不要同时修改 CourseRAG Contract 或生成链路。EP-00 完成并获得新的 Dev 数据批准后，再进入 `EP-01`。

首次实现前需要确认当前联合仓库是否继续作为集成开发事实源。默认建议：

- 在当前联合工作区完成合同设计、集成实现和系统验证；
- 每阶段保持 CourseRAG/CoursePilot 边界和可拆分目录；
- EP-12 通过后，再按明确授权同步两个物理拆分仓库；
- 不在优化过程中同时维护三套分叉实现。

本建议不授权任何 Git push、外部仓库写入或生产部署。
