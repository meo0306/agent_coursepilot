# 跨阶段质量门禁与性能收敛政策

- Policy ID: `coursepilot.cross-phase-quality-gate.v1`
- Status: owner-approved
- Approved date: 2026-08-10
- Last amended: 2026-08-12 under owner-approved P10-D013 dependency-scope adjustment
- Applies to: P10—P19，以及任何可能改变既有评测分布、共享 Profile 或公开指标的修复

## 1. 目的

本政策解决两个必须同时控制的问题：

1. 每个阶段完成时应达到可验证、可演示且无明显回归的质量状态；
2. 开发不得因为次要指标、极小样本或单个 Provider 行为陷入无限调参。

冻结文档中的阶段目标、依赖和 Exit Gate 仍是产品与阶段范围的最高执行依据。本政策不修改
冻结产品决策，只把阶段 Exit Gate、Profile Freeze、性能目标、回归保护和诊断指标分开，
并规定变更影响范围、调参窗口和 Test 使用边界。若本政策与冻结文档冲突，必须停止冲突
部分并在 Decision Log 提交候选，不得自行解释覆盖。

## 2. 两类状态必须分开

### 2.1 Phase Exit Gate

判断本阶段要求的架构、合同、安全和可验证能力是否完成。只有冻结阶段 Gate 或预先批准的
硬门禁失败时，才默认阻塞下一阶段。

允许的 Phase 状态：

- `completed`：核心 Gate 和已批准质量目标均通过；
- `completed_with_quality_debt`：核心 Gate 通过，但存在不影响合同/安全的显式质量债务；
- `completed_with_isolated_security_capability_debt`：核心合同通过，但一个从未发布、默认
  关闭且不参与授权/副作用的安全候选未通过自身 Profile Gate；只能按 2.3 节显式豁免；
- `gate_failed`：冻结核心 Gate、硬安全或不可回滚兼容要求失败；
- `blocked`：上游依赖、人工批准或外部条件未满足。

### 2.2 Profile Freeze

判断某组模型、Prompt、阈值、Token Budget、检索或生成参数是否足以成为默认 Profile。
Profile Freeze 失败不得被改写为成功，也不得通过事后放宽阈值；但它只有在冻结阶段明确
要求默认 Profile 时才自动等同于 Phase Gate 失败。

允许的 Profile 状态：

- `frozen_default`；
- `provisional_dev_only`；
- `candidate_rejected_default_off`；
- `not_applicable`。

### 2.3 可隔离安全能力与下游依赖豁免

安全候选失败不得被改写为通过，也不得降低其预注册阈值。但若失败的是一个尚未发布、
默认关闭且不参与授权或副作用裁决的新增安全能力，可以在 Course Owner 明确批准后，将
“该能力的发布 Gate”与“阶段其余核心合同”分开。该豁免必须同时满足：

- 候选状态固定为 `candidate_rejected_default_off`，Runtime Factory 不得隐式选择；
- 未产生 Secret 泄漏、未授权访问、工具执行、外部调用、持久化或索引副作用；
- 下游阶段不把该候选的输出当作可信边界、授权依据或已通过的安全能力；
- 现有 Prompt/Context 隔离、ACL、工具默认拒绝、Secret 隔离和审计控制保持启用；
- 风险、Owner、后续收敛阶段和再次放行所需的新 Dev/Blind release 均写入治理文档；
- 在系统集成或正式发布收敛点前，必须由新的独立证据解决，不能再次豁免。

满足上述条件时，阶段可标记为 `completed_with_isolated_security_capability_debt`，并通过
显式依赖豁免允许与失败能力无运行时依赖的下游基础设施阶段启动。这不表示安全 Profile
Freeze 或对应检测指标通过，也不改变 L0 对已启用运行时事件的零容忍要求。P17 系统安全
集成和 P18 正式收敛不得继承该豁免。

## 3. 四层指标分类

每个阶段计划必须在任何正式运行前，把所有指标放入以下且仅以下一层。

### L0：安全与合同硬门禁

失败即停止受影响部分并阻塞阶段：

- Secret、未授权访问、跨课程泄漏、路径穿越和危险文件处理事件为 0；
- False Answer、无 Evidence 事实性 Claim 和不可解析正式引用为 0；
- 静默 Provider/模型/索引/Fallback 切换为 0；
- 重复写回、重复导出和重复副作用为 0；
- Test Gold 泄漏、由输出反推 Gold 和 Test 调参为 0；
- 公开合同、版本和持久化事实不可被无迁移路径破坏。

L0 不使用百分比容忍区间，不允许由其他质量指标补偿。

### L1：阶段主指标

每阶段最多选择 1—3 个真正代表阶段目标的指标。主指标必须有：

- 指标定义和实现；
- 数据范围与样本量；
- Baseline 和目标；
- 统计/人工评审口径；
- 允许的校准次数；
- 未达到时的阻塞或降级规则。

不得因为 Runner 已经输出大量指标，就把它们全部设为同等阻塞门槛。

### L2：回归保护指标

保护已稳定能力，目标是“不明显变差”，不是要求每个阶段持续提高所有旧指标。

默认升级区间仅用于触发审查，不是事后接受阈值：

- 绝对下降 `< 2` 个百分点：样本量足够时可视为小幅波动，但仍记录；
- 下降 `2—5` 个百分点：必须完成原因分析并记录质量债务；
- 下降 `> 5` 个百分点：默认阻塞受影响 Profile 或需要新的明确批准；
- P95 延迟或单位成本上升 `> 20%`：必须解释并得到批准；
- L0 指标不适用上述容忍区间。

阶段计划应在运行前根据样本量、置信区间和业务风险收紧或替换区间；不得看结果后调整。

### L3：诊断指标

用于定位问题，但默认不阻塞阶段：

- 极小样本的分类型指标；
- Intent/Route 等中间分类准确率；
- Provider 绝对分数；
- 人工偏好、风格和细粒度错误类型；
- 尚未具备正式 Gold 的候选指标。

L3 只有在样本、Gold、定义和业务影响稳定后，才能通过新决策升级为 L1/L2。

## 4. 性能与质量调优规则

### 4.1 先预注册，后运行

任何会产生正式比较、外部 Provider 调用或 Profile Freeze 候选的运行，都必须先固定：

- 精确数据与 Split Hash；
- 输入/代码/Profile/Prompt/模型/索引 Hash；
- L0—L3 指标分类；
- 主指标和回归保护阈值；
- Token、请求、时间和成本上限；
- Fallback、失败和 Resume 语义；
- 停止规则和是否需要人工批准。

### 4.2 一个阶段只允许一个有界校准窗口

默认每阶段最多一个主要候选和一次预先声明的修订。更严格的既有阶段决策优先，例如
P09-D011 对 P10 继承的 QA 校准当前限制为最多一个候选。增加候选或修订次数属于新的
关键决策，必须在看到新增结果前获得批准。

候选失败后不得：

- 继续微调同一 Prompt 直到过线；
- 只修最低指标而忽略耦合指标；
- 更换样本、Gold 或 Applicability；
- 放宽已经看过结果的阈值；
- 自动增加费用或转付费。

### 4.3 Test 只用于冻结后评测

- Dev 可用于已批准的校准；
- Test 在所有 Profile、阈值、模型、Prompt、索引和数据处理配置冻结后解锁；
- Test 正式运行原则上只执行一次；基础设施失败可按完全相同 Manifest Resume；
- Test 结果只能进入报告、限制和后续新版本 Backlog，不得回流本版本调参；
- P10 是 CourseRAG 正式收敛点，P18 是 CoursePilot/系统正式收敛点。

## 5. 变更影响与最小回归范围

任何阶段计划和阶段报告都必须声明本阶段改变了哪一层，并按下表运行最小充分回归。

| 变更层 | 可能失效的下游能力 | 必须重新验证 |
|---|---|---|
| Parser/OCR/Canonical IR | Evidence、Chunk、Index、Retrieval、Context、QA | 解析 Gold + Evidence/Chunk + Retrieval/QA Sentinel |
| Evidence/Chunk Profile | Index、Retrieval、Context、QA、Citation | Stable ID/Resolver + Index + Retrieval/QA Sentinel |
| Embedding/BM25/RRF/Reranker/Index | Retrieval、Context、QA | 检索主指标 + Filter/Version + Context/QA Sentinel |
| Query Processing/Context Packing | QA | Query Toggle/Filter + Context + QA Sentinel |
| Prompt/Model/Token/Structured Output | 对应生成任务 | Provider Contract + 任务主指标 + Grounding/Failure |
| Shared Model Gateway Route | 所有使用该 Route 的生成任务 | 受影响任务的冻结 Sentinel，不重测无关 Retrieval |
| Validator/Repair | 对应 Artifact 和全局约束 | Detection/Repair + Preservation/Unauthorized Change |
| Checkpoint/Interrupt/Approval | 状态、版本和副作用 | Resume/Edit Preservation/Idempotency，不自动重跑语义评测 |
| Exporter/Layout/Renderer | 导出和视觉质量 | Open/Render/Edit/Overflow/Reference，不重跑 CourseRAG |
| Writeback/New Active Index | 新旧版本检索、引用和权限 | Version Isolation + Migration + Retrieval/QA + Security |
| 物理拆仓/部署依赖 | 启动、合同和可复现性 | Clean Checkout + Contract + Release Smoke |

如果变更没有触及某层，不得为了“完整”而无依据重跑昂贵 Provider 评测；如果触及上游分布，
也不得只跑本阶段 Unit Test 而省略受影响的下游 Sentinel。

## 6. P10—P19 耦合与调优边界

| 阶段 | 性质 | 主要耦合 | 允许的质量工作 | 禁止事项 |
|---|---|---|---|---|
| P10 | CourseRAG 收敛点 | P03—P09、写回、新 Index | 一次预注册 Dev 校准；随后冻结并运行 Test | Test 调参、自动重开 P09 循环 |
| P11 | 合同/模型网关基础 | 生成任务 Provider Route | Capability、Trace、成本和兼容验证 | 调 Lesson/Exam/PPT 内容质量 |
| P12 | 状态与审批可靠性 | Task/Artifact/Resume | Checkpoint、编辑保留、幂等和故障注入 | 用语义指标掩盖状态错误 |
| P13 | Validator/Repair | P14—P16 Artifact | Detection、Scope、Repair、Preservation | 以整件重写冒充局部修复 |
| P14 | Lesson 专用质量 | CourseRAG + P11—P13 | 独立 Lesson Profile 和一次有界 Pilot | 修改共享 CourseRAG 默认值补救教案 |
| P15 | Exam 专用质量 | CourseRAG + P11—P13 | Exam Profile、全局约束和并行消融 | 用并行收益补偿一致性失败 |
| P16 | PPT 专用质量 | P14 + P11—P13 | 内容/结构/渲染分轴 Pilot | 通过删内容掩盖 Layout/Overflow 缺陷 |
| P17 | 系统集成/安全 | P10、P14—P16 | Remote、Trace、故障、安全和写回闭环 | 在集成阶段重调业务 Prompt |
| P18 | CoursePilot/系统收敛点 | P14—P17 | 冻结配置后的 Track A/B 正式评测 | 根据 Test 或人工盲评结果返调本版本 |
| P19 | 拆仓/发布 | P10、P18 | Clean Environment、Contract、Release Smoke | 为适配部署静默更换正式 Profile |

## 7. 后续阶段推荐主指标

这些是计划审计的默认候选，不自动成为阈值；每阶段仍需在 Plan 中确认。

| 阶段 | L1 主指标候选 | 必须保留的 L0/L2 |
|---|---|---|
| P10 | Incremental Reuse、Citation Migration、正式 Test 可复现 | 安全零容忍、无泄漏/静默 Fallback、P09 Grounding |
| P11 | Trace 完整率、Profile Route 正确率、API 兼容 | Secret、Capability、旧 API 回归 |
| P12 | Resume 成功率、编辑保留、重复副作用 | 版本陈旧检测、幂等 |
| P13 | Issue 定位、Repair 成功、未授权修改 | 全局约束不回归 |
| P14 | KP/Evidence 覆盖、教学时间/逻辑、编辑恢复 | 所有事实引用、非整件写回 |
| P15 | Blueprint/总分/难度/覆盖满足率、重复率 | 答案泄漏、正式导出/写回授权 |
| P16 | 严重溢出、可编辑对象、引用可解析 | 文件可打开、字体/Shape 边界 |
| P17 | 故障恢复、Trace 连续、闭环写回 | 跨课程/未授权/Secret/重复副作用为 0 |
| P18 | 任务人工质量、Edit Burden、端到端成功、P95/成本 | 锁 Test、公开指标可追溯 |
| P19 | Clean Start、跨仓 Contract、Release Smoke | Profile/Attribution/License 不漂移 |

## 8. Profile 所有权与隔离

- P08 Retrieval、P09 Query/Context/QA、P14 Lesson、P15 Exam、P16 PPT 必须使用独立的
  版本化 Profile；
- 下游任务不得直接修改共享上游默认 Profile；
- 任务特定改进先进入任务 Profile；若需升级共享默认值，必须单独进行影响分析和下游回归；
- 正式 Profile 必须绑定模型、Prompt、Tokenizer、Token Budget、Fallback、Index、数据与代码 Hash；
- `candidate_rejected_default_off` 不得被 Runtime Factory 隐式选择；
- P09 当前 Generation Reliability Candidate `8b2c7b37...` 保持拒绝/default-off。

## 9. 阶段计划和报告强制字段

后续每个阶段计划必须新增：

1. 变更影响层和受影响回归矩阵；
2. L0—L3 指标分类表；
3. 最多三个 L1 主指标；
4. Baseline、阈值、样本量和统计/人工口径；
5. 调参/候选/修订次数与成本上限；
6. Dev/Test/人工审批边界；
7. Profile 状态与回滚方式；
8. `completed_with_quality_debt` 的允许条件。

阶段报告必须逐项给出实际值、是否通过、是否影响 Phase Gate、是否仅影响 Profile Freeze、
回归范围、未达项、质量债务 Owner 和进入下一收敛点的处理方式。

## 10. P10 启动约束（已执行历史基线）

P10 启动时为 `ready_to_start`，其 Plan 必须并已按以下边界执行：

- 把本政策列入必读治理文档；
- 保留 P09 已验证的 Citation、Grounding、Abstention 和无静默 Fallback 能力；
- 把 P09-R08/R09/R20/R21 列为显式输入，而不是隐式重新调参；
- 将一次 Dev 校准和正式 Test 运行拆成两个不可混淆的检查点；
- 在任何 Test 访问或外部调用前取得相应明确批准；
- 不在 P10 Plan 获批前执行 P10 实现。

## 11. 当前解释性结论

“阶段完成时达到较好性能”定义为：核心合同和安全通过、L1 主指标达到预注册目标、受影响
的既有能力无明显回归、弱项被量化并有明确收敛点；它不等于每个细分指标都达到局部最优。

这样可以同时避免两类失败：一类是为了进度隐藏真实质量问题，另一类是为了少量波动无限
调参。P10 和 P18 负责全局收敛，其余阶段负责局部能力、任务专用 Profile 和最小充分回归。
