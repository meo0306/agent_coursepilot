# P10.3 多轴联合不可信指令检测阶段报告

## 1. 修复目的

P10.3 的目的不是继续替换第四个分类模型，也不是通过降低阈值让旧指标变绿，而是修复
P10.2 暴露的合同错位：仓库要求同时识别策略绕过、角色伪装、秘密提取、工具强迫和轻度
混淆，但三个单模型分别只覆盖了这组任务的一部分。继续使用一个二分类分数承担全部安全
语义，会让召回率与误报率在同一个阈值上反复拉扯。

本阶段把“是否存在不可信指令”拆成可独立审计的威胁轴，在不改变正文、Evidence、Chunk、
索引或公开 API 的前提下，建立高置信联合检测候选和新的 Dev/Blind 发布流程。

## 2. 问题现象

- ProtectAI 在 160 条已消费 Dev 上的最佳预注册结果为 Recall `0.2375`、Specificity
  `0.7375`，表现为明显领域错配。
- HikmaAI 的 Specificity 为 `1.0`，总体 Recall 为 `0.775`，但中文 Recall 只有 `0.65`，
  Tool Coercion Recall 只有 `0.50`。
- Llama Prompt Guard 2 的最佳 Recall 只有 `0.2125`，Tool Coercion Recall 为 `0`；它更接近
  显式 Prompt/Policy Override 检测器，而不是完整五类威胁分类器。
- 如果继续围绕同一组已消费 Dev 换模型、扩阈值或补短语，得到的是选择偏差和测试记忆，
  不是可泛化的安全能力。

## 3. 原因分析

根因是把多个不同的因果模式压缩成一个宽泛二分类任务：

1. 策略绕过依赖“覆盖上级规则”的语义；
2. 角色伪装依赖“角色声明 + 权限/层级 + 行为效果”；
3. 秘密提取依赖“提取动作 + 受保护对象 + 输出/泄露效果”；
4. 工具强迫依赖“执行动作 + 工具/外部系统 + 副作用”；
5. 混淆只是增强上述意图的表面变换，本身不应自动判为攻击。

这些轴的正负样本边界和模型擅长领域不同。多数投票也不合适，因为一个真实的秘密提取
信号不应被三个无关、安静的轴投票否决。另一方面，简单关键词并集会把教材中的攻击引用、
安全课程和政策说明误报为执行性指令。

## 4. 解决方案

最终候选架构为：

`Security Window → HikmaAI General Axis + Structured Capability Axes + Optional Override Challenger → High-confidence Union → Locatable Finding`

- HikmaAI FP16 ONNX 是必需的通用语义轴，沿用已固定的模型 Revision、Manifest 和本地
  CUDA fail-closed 运行时。
- Role、Secret、Tool 使用结构化 `action + protected target + intended effect` 联合条件；
  Context Guard 区分引用、讨论、教学与真正的执行性命令。
- Obfuscation 只产生诊断修饰信号，不能单独生成 Finding。
- Llama Prompt Guard 2 仅作为 Policy Override Challenger；同一次评分中必须满足
  `unique TP > 0` 且 `added FP = 0` 才保留，否则自动生成不含该轴的候选 Profile。
- 决策采用高置信并集，不采用多数投票。任何必需轴缺模型、Hash 不符、Profile 损坏或
  Runtime 失败，整个 Security Stage fail closed，不回退旧正则或其他模型。
- Finding 保存 Axis、Signal、Detector、Window、Page/Block/Span 和 Decision Path，原始
  正文不修改，稳定 Evidence/Chunk 身份不改变。

## 5. 数据与发布治理

P10.3 新建 120 条 Qualification Dev Candidate：60 条正例、60 条困难负例，中英文各半，
五个正例家族等量覆盖。Candidate SHA-256 为
`b3ef6753da547c877e214c706777f69405ecd39f87395d23c13b780c2f80b6c2`。

候选 Multi-axis Profile 文件/规范化内容 SHA-256 分别为
`b8bff91ae1bf0ab64d2d50254b5b159bbf3953b2466a14c61f9467a2cb2a354e` /
`4e1efd2f6723c756b935151a281a20759ef3345284e1ac116aa4f74a2d9af83f`。
Qualification Protocol 精确绑定数据、Profile、两份模型 Manifest、结构化轴配置及十个实现
文件，文件 SHA-256 为
`91f51be096ddfb0db5e37d68e4be5b11e308c45968287e00659233eb1acb3a4c`。

两份离线审核页面分别用于独立的 Course Owner 审核，只有两个 Review Decisions 覆盖全部
有序 ID、无退回且绑定相同 Candidate Hash 后，才允许生成 Approval。系统不会自行把标签
设为 Approved。

Course Owner 后续明确确认两轮审核均已完成，两个 Pass 均为 120/120 PASS。由于页面导出器
再次失效，系统没有要求人工重复审核，而是根据该明确会话证明恢复两份决策文件；每条记录
均注明来源为 Course Owner 两轮全 PASS 会话证明。第一轮/第二轮文件 SHA-256 分别为
`b6e5d2ce229a345a41dd8f69038e0de551c620ec2b1d175f5f8786f0427a41c9` /
`4817e358c298c012f0e0a8189415b3e6180413784a7afa242bd6476203fa528c`。Approval
`dcef3ebedc26b67909c9bbdb07db47b7035c9c07c520546b8fef880d9e95b09f` 精确绑定
Candidate、两轮 Decisions 及全部有序 ID。该恢复不等于系统自行审批标签。

新的 48 条 Blind 目前只有分布承诺和 Hash，不含 ID、文本或标签。它只能在 Dev/Profile
冻结并再次获得精确授权后构建、审核、锁定和运行一次。P10.1/P10.2 已消费 Dev/Blind 不被
读取或复用为本次选择数据。

## 6. 实现结果

- 新增 `ThreatAxis`、`SecurityAxisSignal` 和 `SecurityAxisDetector` 合同。
- 新增 HikmaAI 语义轴包装器、结构化能力轴、Context Guard 和非裁决 Obfuscation 信号。
- 新增 Multi-axis Profile、环境校验、高置信并集和 required-axis fail-closed。
- Security Finding/Stage 增加 Axis、Signal 和 Decision Path 审计信息。
- 新增 120-case Candidate、双审 Approval、可下载 Review UI、空 Blind Commitment、一次性
  Qualification Runner 和 Challenger Ablation。
- 新增配置、示例环境变量、Profile 身份和四份 JSON Schema；不新增 Alembic Migration。
- 默认 Provider 保持 `legacy_rules`，因此当前生产/旧 CoursePilot 行为未切换。

## 7. 当前验证证据

- `uv sync --frozen`：通过；基础环境按锁文件移除可选 Transformers Runtime。真实模型运行仍
  必须使用此前隔离并验证过的本地 CUDA Runtime，不允许隐式联网恢复依赖。
- Security 专项：29 passed。
- Parser/Evidence 回归：42 passed。
- P10.1/P10.3/Lock 专项：14 passed。
- 全部 Eval：208 passed、1 个按正式门禁跳过。
- B0 Sample Smoke：1 passed。
- 全仓测试：599 passed、5 个按外部/正式门禁跳过。
- Ruff Format：544 files already formatted；Ruff Check：通过。
- Mypy：368 source files，0 error。
- JSON Schema：84 份全部与模型一致。
- Alembic：唯一 Head `0015_incremental_writeback_security`；P10.3 无 Migration。
- `git diff --check`：通过，仅存在仓库既有的 CRLF 提示。
- Secret 扫描未发现 P10.3 Secret；正式 Qualification Runner 明确绑定 external calls=0、
  runtime network=false、Blind/Test access=false、fallbacks=0。

在本节记录的实现验证检查点，真实 Qualification Dev 与 Blind Test 尚未执行，正式 40 条
Retrieval/QA Test 也未重跑，且没有任何外部 Provider 调用；Qualification Dev 的一次性运行
结果记录在下文，不应把这个历史检查点误读为最终状态。

## 8. 当前状态与后续检查点

人工双审和 Candidate Approval 完成后，本阶段曾停在 Qualification Protocol 精确批准之前；
当时真实 Qualification Dev 尚未运行，P10 的 Security L0 仍为失败，P11 仍被阻塞。随后
Course Owner 已批准 Protocol，最终一次性运行结果见下一小节。

只有以下顺序全部完成，才允许继续：

1. Course Owner 批准精确 Candidate、Approval 和 Qualification Protocol SHA-256；
2. 运行唯一一次 Qualification Dev；
3. 若所有门禁通过，单独冻结 Profile 并构建全新 Blind Bundle；
4. Course Owner 审批、锁定并授权唯一一次 Blind Gate。

审核页面导出按钮第二次失效是独立工具质量问题。本轮按 Course Owner 要求不再修复导出器，
也不阻塞已经完成的审核；问题保留在风险登记中。未来任何新的长表单审核页面在交付前必须
通过真实浏览器执行和实际文件下载验证，不能只检查 HTML/JavaScript 字符串存在。

### Qualification Dev 最终结果

Course Owner 批准精确 Protocol
`91f51be096ddfb0db5e37d68e4be5b11e308c45968287e00659233eb1acb3a4c` 后，两个模型和
CUDA Runtime 先通过不读取 Dev 的 Manifest/环境预检，随后唯一一次 Dev 评分完成。报告
SHA-256 为 `26e5eb98bfe08536987cd8a6b36d769ce3e3370319f8479d57c15b1ba596f0bb`。

| 指标 | 完整候选 | 不含 Llama Override 的基线 | 预注册要求 |
|---|---:|---:|---:|
| Recall | 0.9500 | 0.9500 | 1.0000 |
| Specificity | 0.7333 | 0.8000 | >=0.9750 |
| Finding Locatability | 1.0000 | 1.0000 | 1.0000 |
| Llama unique TP | 0 | - | >0 才保留 |
| Llama added FP | 4 | - | 0 才保留 |

完整候选 TP/FN/FP/TN 为 `57/3/16/44`。三个 FN 均为中文：两个间接/改写 Policy Override，
一个改写 Tool Coercion。完整候选的 16 个 FP 中，Llama 额外贡献四个英文 Policy
Description 误报；因此按预注册消融合同剔除 Llama。剩余基线 12 个 FP 主要是十条中英文
Explicit Negation，以及两条英文合法凭据轮换说明。这说明结构化轴的 Context Guard 只做了
窗口级表面匹配，没有正确表达否定词对后续动作/效果的作用域；同时 Hikma/结构化组合仍未
覆盖中文间接策略覆盖和文件系统改写表达。

这不是可以用同一 Dev 临时补三个短语或调整阈值解决的问题：重复负例显示的是 scoped
negation 架构缺口，而三个 FN 显示的是中文语义召回缺口。根据 Protocol，系统没有生成
Profile Candidate，没有运行 Blind，没有外部调用、Test 访问或 Fallback，也不会重跑该 Dev。
P10 继续为 Security L0 Gate Failed，P11 继续阻塞。

## 9. 回滚与兼容

P10.3 没有数据库迁移，也未删除旧模型、Artifact、Test Lock 或报告。候选失败时不发布新
Profile，默认继续保持 `legacy_rules`。Security Stage 的失败不会修改 Primary/Overlay Active
Index。所有新数据和报告独立保存，便于审计失败原因而不覆盖 P10.1/P10.2 证据。

## 10. 项目深挖总结

这一轮修复的关键经验是：模型指标失败不一定意味着“换一个更强模型”，也可能意味着安全
合同把多个不同问题错误地压成一个分数。我们先用三次受控实验确认错误互补，再把威胁拆成
独立轴，以高置信并集保证单一严重风险不被多数投票稀释，同时用 Context Guard 和困难负例
控制误报。模型负责泛化语义，结构化轴负责可解释能力关系，消融规则负责证明额外模型是否
真的贡献独有价值，Dev/Blind 生命周期则防止失败样本回流调参。这使性能、解释性、回滚和
评测可信度成为同一套工程合同，而不是互相补丁式修复。

## 11. Gate 作用域调整与后续开发边界

Course Owner 在审阅失败形态后批准采用 P10-D013：严格的检测 Profile Freeze 保持失败，
但不再用这个从未发布、默认关闭且未产生副作用的候选能力无限阻塞无运行时依赖的 P11
基础设施工作。这一调整修复的是门禁作用域，而不是模型指标：

- `26e5eb98...` 仍是失败报告，Recall/Specificity 不变；
- 不生成 Profile、不运行 Blind、不重跑或补写同一 Dev；
- `multi_axis_local` 不得成为默认项，也不得用于授权、工具执行或可信判定；
- P10 的增量、Citation、写回、ACL、Port/Contract 和正式评测证据保持有效；
- P11 必须维持 Context-as-untrusted、系统/开发者指令优先、工具默认拒绝、ACL/Secret
  隔离和完整 Trace；
- P17 必须用新版本和新独立 Dev/Blind 解决该债务，P18 在此之前不能通过正式安全收敛。

因此本报告的组件结论仍是 `candidate_rejected_default_off`，阶段结论调整为
`completed_with_isolated_security_capability_debt`，P11 为 `ready_to_start`。这不是安全
通过声明，而是一个有明确隔离条件、Owner 和最终硬收敛点的依赖豁免。
