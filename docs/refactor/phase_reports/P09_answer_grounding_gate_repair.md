# P09 Answer Grounding 联合修复报告

## 1. 问题现象

P09 原始实现已经满足“回答 Claim 必须绑定 Context 内 Evidence”和“不可回答样本拒答”两条
安全底线，但 Freeze Gate 仍不能通过。第一次 Gate Repair 通过改进 Router、恢复 B7 Context
和引用后处理，把 Citation Precision/Recall/Macro-F1 提升到 `0.7234/0.8298/0.7567`，18 项
Protocol r2 检查中通过 17 项；唯一失败是 Q3 Short-answer Token F1 相比 Q2 下降
`0.02221`，超过允许的 `0.02` 保护边界 `0.00221`。

该现象说明问题不是单独的“引用选错”。同一条模型输出同时决定回答长度、列表拆分、Claim
粒度和 Evidence 引用；只反复调整 Citation Composer，可能让 Citation 指标上升，却让短答案
或列表指标下降，形成耦合指标之间的来回修补和无效工作。

## 2. 原因分析

根因分为三层：

1. Context Item 在一个搜索结果中可包含多个 Evidence ID，但旧 Prompt 主要看到聚合文本，
   模型难以稳定判断某句话对应哪一个 Evidence。
2. QA 合同只有统一的 `answer + claims` 形态。事实型问题容易回答过长，有限列表问题容易被
   压缩成一个概括 Claim，导致 Short-answer F1、List Set F1 和 Citation 指标互相牵制。
3. 引用后处理只能纠正 Evidence 选择，不能修复答案本身的粒度和完整性。对“无词面信号”
   的内容若强行改引，还可能制造伪支持。

因此，本次修复把重点指标分层：安全硬门禁保持 Claim 完整引用、可解析、零静默 Fallback、
正确拒答；主质量指标围绕 Context Coverage、Citation P/R/F1、Short-answer F1 和 List Set F1；
Router 与误拒答率作为保护指标，只要求不出现明显退化。该排序避免平均用力，也避免牺牲安全
指标换取表面答案分数。

## 3. 解决方案

修复采用一条联合、可消融、可回滚的链路：

- `ContextEvidenceSegment` 在每个 Context Item 内显式保存 Evidence ID、原文、顺序、来源
  Search Rank 和内容 Hash；Context 的选取、8 项/4,000 Token 预算和 B7 Snapshot 不变。
- `AnswerShapeDecision` 用高置信规则区分
  `factoid/list/explanatory/comparison/procedure`；不确定时由 Provider 在受限枚举内选择。
- QA v3 输出固定为 `status/answer_type/answer/list_items/claims`。Factoid 最多 80 字；List
  使用最多 40 个带 Evidence ID 的结构化 Item；其他类型最多 200 字。
- Validator 同时校验 Answer Shape、结构和 Context Evidence ID；仍只允许一次定向 Repair。
- Citation Composer 对每个原子 Claim 或 List Item 独立计算字符二元组覆盖并选择 Context
  Evidence。没有正向词面信号时只保留模型已经给出的有效 Context 引用并发出 Warning，不
  伪造支持关系。
- API 仅增加默认可空字段；没有 ORM/Alembic 变化。候选 Profile 在 Owner Freeze 前不会成为
  `default_v1`。

## 4. 预注册、数据和预算边界

- Approved Gold Approval SHA-256：
  `a19ab29918c4b6b53da0c148c04849ab6e570b8b8ff2350dd58a3c858f4d8cef`。
- B7 Retrieval Snapshot SHA-256：
  `d85d9603965ecad620d62e39d2fde15f4b2857d180b9aba2379a568a59656602`。
- Protocol r2 SHA-256：
  `5bfbe1ceaf468d555a8f3d09206a5b5f8bfb1089443e37d5eeedc90fca810802`。
- Answer Grounding Profile SHA-256：
  `345500b79064a2c7e9d454b6f2fa96ca0e191e1c7974a3367eb040795631d6fe`。
- Pre-registration Manifest SHA-256：
  `211bf746f950eae3b8ba78729609b28ce2d8ebd50e95cdccb08358b068f5f9ec`。

Runner 只允许一个 Fresh Q3 Candidate，读取 Approved Dev 60 条，不读取 Test，不做运行后
Prompt 调参，不调用 Cohere，不重建 Retrieval/Embedding。DeepSeek 独立上限为 375,000，
P09 全阶段上限仍为 2,500,000。逐例预算预检得到一次完整生成保守估算 212,804 Token；
若 60 条全部 Repair，理论值 425,608。系统不会因此暗中扩额，而是在下一次调用可能越过
375,000 前停止并保留 Checkpoint。

## 5. 实施结果

本地 Dry Run 成功恢复 60/60 个 B7 Dev Search Snapshot，`raw_retriever=0`，初始
DeepSeek/Cohere 用量均为 0，证明该执行路径不会重新发送教材 Chunk、调用 Embedding 或
消耗 Cohere Search Unit。

本地验证结果：

- Answer Grounding/P09 专项：65 passed；
- 全量 Pytest：486 passed，5 gated skips；
- B0 owner PDF/DOCX Smoke：1 passed；
- Ruff format/check：456 files formatted，check passed；
- Mypy：0 errors in 311 source files；
- Alembic head：`0014_query_context_qa`；
- `git diff --check`：通过，仅有既有 Windows LF/CRLF 提示。

## 6. 真实 Dev Run 状态

Fresh Run 在第一个 DeepSeek 请求建立网络连接前被托管执行沙箱阻断，错误为 Windows
`ConnectError / WinError 10013`。Checkpoint 只记录脱敏错误类型和固定错误消息，没有
Provider 响应、答案、Secret 或教材输出；Cohere 调用为 0。随后申请网络权限升级又被平台
账户额度策略拒绝，因此不能通过代理、替代命令或其他方式绕过。

这不是模型质量失败，也不是代码或配置合同失败，但它阻止了 Protocol r2 的真实指标计算。
因此当前没有新的 Evaluation Report、Freeze Candidate 或 `default_v1`，旧 Candidate 也
不会被误标为通过。

## 7. 回滚与后续恢复

代码变更是加法合同，可通过不启用 Candidate Profile 保持原运行时行为；数据库无需回滚。
当允许外部网络执行时，只需对同一目录执行 Runner `--resume`：Manifest 会校验系统版本、
Gold、Split、Snapshot、Profile 和 Protocol Hash，并从失败 Case 继续。若任一 Hash 不同，
Resume 会拒绝；若预算即将越界，会在调用前停止。

在真实 Dev Report 通过 Protocol r2 且生成精确 Freeze Candidate 前：

- P09 Exit Gate：**未通过，environment-blocked**；
- P10：**不具备开始条件**；
- 不需要提出新的算法方案，也不应继续调 Prompt；当前唯一外部阻塞是获得允许访问已授权
  DeepSeek Endpoint 的执行环境。

## 8. Owner Resume 与正式结果

2026-08-09，Owner 在本机使用同一 Run Manifest 和 `--resume` 完成执行。Checkpoint 状态为
`completed`，60/60 Case 均为 succeeded；其中 59 个为 attempt 1，最初被网络阻断的 Case 在
attempt 2 成功。系统结果为 53 answered、6 abstained、1 failed；唯一失败是“职业自动化淘汰
概率”长列表在首次生成和一次 Repair 后都产生 `INVALID_JSON`，并按合同返回
`QA_SCHEMA_REPAIR_FAILED`，没有半有效答案。

正式产物：

- Run Manifest SHA-256：`d630da76e8cda10b049bf8a3127bcd2dfee668ddf392eb2b83871d5a0816a90f`；
- Report SHA-256：`b04fc9b620fccddecaf889c201fa5b8d0cec139b92686a2ac354dffed853f77b`；
- Checkpoint SHA-256：`2a53b2693592c6810781c05036a9110a39d72599b2c6c36b170bf12e48da4ccc`；
- Usage Audit SHA-256：`93ca9af16435082c99c402d013e078accf954b85e570d2a200351d0f410144d6`；
- Protocol r2 Evaluation SHA-256：`4fea276823686e0a70b615079a9230359b3cd744966d91ef0fe8fc1fde602f3b`。

Answer Grounding 保守计费口径为 199,264 Token，阶段累计 824,734 / 2,500,000；Cohere
新增用量为 0。Test 未读取，无 Fallback。

主 Dev 结果中，Context Coverage `0.7870`、Complete Group Coverage `0.7500`、Intent
Accuracy `0.8542`、Unanswerable Recall `1.0`、False Answer `0` 和 False Abstention
`0.0208` 均通过保护线。失败项为：QA Failure `0.0185`；Short-answer F1 `0.3523`，低于
Q2 `0.4341`；自动 Evidence-ID overlap proxy 的 Citation P/R/F1 为
`0.5168/0.6596/0.5508`；List Set F1 仍为 0。因而未生成 Freeze Candidate。

## 9. 根因复盘：不能继续围绕当前分数调参

逐 Case 诊断显示，Citation Composer 改写了 25 个 Case 的引用：按当前 Evidence-ID overlap
代理指标，0 个改善、9 个下降。若保留模型原始 Context 引用，代理 Recall 可从 `0.6596`
恢复到 `0.7979`，但 Precision/F1 仍只有 `0.5411/0.6110`，说明删除 Composer 也不足以
通过门禁。

Answer Shape 同样出现口径耦合：54 个主 Dev 中产生 9 个 list，但 Approved Gold 仅两个 Case
使用 `gold_list_items`；多个包含“哪些具体数据或事实”的短答案 Case 被扩展成长列表，使完整性
提高却降低 Short-answer F1。两个 Gold List Case 的自动 List Set F1 都为 0：其中 ERNIE
环境答案事实正确但拆成 5 项，而 Gold 是 4 项；职业概率 Case则因超长 JSON 失败。这说明简单
提高/降低列表长度会在完整性、结构可靠性和短答案指标之间反复摆动。

更关键的是评测合同偏差。冻结文档 03 将 Citation Precision/Recall 定义为 Claim 级指标：
每条 Citation Link 是否直接支持对应 Claim，以及多少 Gold Claim 获得正确引用，需要人工
Claim 匹配/支持判定。当前 `citation_metrics()` 实际计算的是预测 Evidence-ID 集合与 Gold
Evidence-ID 集合的全局相等交集，只能称为 Evidence-ID overlap proxy。此前 Shadow
Composer 还只在能映射到 Gold 的 Evidence 子集中选择，因此其 `0.7234/0.8298/0.7567`
包含 Gold 侧信息，不能作为运行时改进证据。

结论：本次 Fresh Run 是有效的失败证据，但当前不应再次调 Prompt、Answer Shape 或 Citation
阈值。应先单独批准并完成“P09 Claim-Citation 评测合同修复”：纠正指标名称和正式口径、生成
人工 Claim-Citation 评分包、对列表/短答案适用范围作不依赖系统输出的审计，并在固定现有输出
上重算。只有确认真正的失败项后，才决定是否需要第二次模型候选。

当前状态：P09 Exit Gate **failed**；P10 **blocked_by_P09**；不产生 Freeze Candidate，
不启动新的 Provider 调用。
