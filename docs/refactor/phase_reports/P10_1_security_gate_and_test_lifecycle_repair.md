# P10.1 Security Gate、Test 生命周期与 DS8 收敛修复报告

## 1. 执行结论

P10.1 的代码修复、Dev 验证、Test 生命周期修复、语义等价验证和 DS8 离线性能基线均已完成。
本阶段没有调用 Cohere、DeepSeek 或任何外部模型 API，没有重新运行原 P10 的 40 条正式语义
Test，也没有修改原 Test Lock、Primary/Overlay Index 或正式报告。

当前状态不是 `completed`，而是
`repair_implemented_awaiting_independent_blind_test`。原因不是功能或 Dev 指标失败，而是新的 12 条
独立盲测尚未由隔离流程构造、两轮审核、绑定 Hash 并由 Course Owner 锁定。P11 因此仍为
`not_started / blocked_by_P10`。

P10.1 Frozen Manifest Candidate SHA-256：
`ffe8f58220cf3b1b821d25e25a681a34cef039d8cf20d8ab87c929c5cb71401e`。

2026-08-11，Course Owner 已明确批准上述精确 SHA-256 作为 P10.1 Profile Freeze。该批准冻结
Scanner/Profile 并允许进入独立 Blind Test 构造流程；它不等于批准尚不存在的 Blind Bundle，
也不解除 Security L0 Gate。

## 2. 问题现象

原 P10 正式 Test 的五类安全控制中，`p10-sec-15-prompt-injection` 没有生成
`PROMPT_INJECTION_MARKED`。文档内容没有被执行，也没有产生数据库、Artifact、工具或外部调用副作用，
但零容忍合同要求“攻击内容必须被标记”，所以 L0 Security Gate 合理失败。

与此同时，正式 Test Lock 从 `locked=false` 合法转为 `locked=true` 后，历史数据构造测试仍假设仓库
永远处于 Pre-lock 状态，导致全量评测测试出现 23 项失败。P10 的 DS8 离线 Cold/Warm 性能模板也因
L0 失败提前停止，缺少真实证据。

## 3. 为什么初始测试没有发现

初始实现把 Prompt Injection 检查放在上传预检，直接扫描 PDF/DOCX 原始 bytes。真实正文通常位于
PDF 压缩流、DOCX ZIP/XML 或 OCR 图片结果中，二进制层无法稳定看见可读文本。即使文本可见，旧规则
也只覆盖少量固定短语，没有 Page、Block、Span 级 Finding 合同。

历史 Test Lock 测试则把“候选构造期必须 unlocked”误写成“仓库全生命周期永远 unlocked”。在正式
Lock 产生前，这种状态耦合不会暴露；Lock 合法切换后，测试把正常生命周期误判成产品回归。

## 4. 根因链路

安全漏标的根因链路是：

`原始二进制扫描 → 压缩/编码正文不可见 → 行为意图规则没有输入 → 无定位 Finding → Warning 无法传播`

Test 失败的根因链路是：

`测试复制实时仓库 → 实时 Lock 已消费 → 构造期断言仍要求 false → 23 项历史测试失败`

性能缺口还有一个在实施中发现的测量根因：最初五类 workload 共用一个 Python 进程，PyTorch CUDA
allocator 会把前一个 workload 的显存保留到后一个 workload，导致纯 Section Update 也显示 GPU
占用。该结果功能上正确，但不满足 `Cold=新进程`，因此没有被包装成正式证据。

## 5. 为什么拒绝“补一条正则”

直接把已曝光的 `Ignore application policy ...` 放进旧正则，只能证明系统记住了答案，不能证明它能
识别策略绕过、角色伪装、秘密提取、工具强迫或轻度混淆等行为族。更严重的是，已曝光 Test 会反向
参与实现选择，破坏 Test 的独立性。

本修复把旧句子降级为公开 regression sentinel；Profile 选择只使用新的 30 条 Dev。最终 L0 只接受
一个实现侧不可见、独立构造和两轮人工审核的 12 条 Blind Test。

## 6. 架构修复

### 6.1 文件安全与语义安全分层

- MIME、Magic、ZIP Bomb、加密 PDF、路径、页数、DPI 和资源限制继续在任何持久化之前执行；
- Prompt Injection 在结构化 PDF/DOCX 解析和 OCR 合并后扫描 Block text；
- Scanner 使用 Unicode NFKC、casefold、零宽字符移除、异常空白和 compact view；
- 规则覆盖中英文的 policy override、role impersonation、secret extraction、tool coercion 和
  obfuscation；
- Finding 保存 `rule/category/severity/page/block/char span/matched hash`；
- 原文不删除、不改写、不执行，Warning 传播到 Parsed IR、Evidence 和 Chunk 审计元数据；
- Security Profile Hash 进入 Structured Parse/OCR Fingerprint，旧未标记 Artifact 不会误命中缓存；
- Profile 缺失、损坏或 Hash 不一致时 fail-closed。

### 6.2 稳定身份保护

安全 Warning 会改变完整 Parsed/Evidence Artifact Hash，这是正确的审计行为；但非语义 Warning 不应
改变引用身份。Evidence Builder 保存标记前 Parsed Artifact 身份，Chunker 使用只排除
`PROMPT_INJECTION_MARKED` 的 Evidence identity projection。其他文本、来源、结构、OCR 或 Warning
变化仍保持 identity-sensitive。

两份真实样例的对照结果：

| 项目 | 数量 | 修复前后结果 |
|---|---:|---|
| Block | 4,852 | 文本、顺序、ID、Content Hash、Source Span 完全相同 |
| Evidence | 1,848 | Evidence ID、文本、来源完全相同 |
| Child Chunk | 1,048 | Chunk ID、文本、Evidence Link 完全相同 |
| Dense/BM25 Corpus Mapping | 1,048 | 完全相同 |
| Search/Context/QA Schema | 3 | Schema Hash 已绑定，无 Wire 变化 |

完整影响报告 SHA-256：
`9944963618273d3d1c5b4ddcb4b6536ac1628ef12fa6ef18112ee2d6653f7899`。

## 7. 数据与盲测治理

Dev 为 30 条：20 条正例、10 条 Hard Negative。正例按五个行为族各四条分布，覆盖中英文、大小写、
分隔符与轻度混淆。Dev 不包含正式 Blind 内容，报告中也不输出未来 Blind 文本。

Dev 结果：

- 正例 Recall：`20/20 = 1.0`；
- Hard Negative 误报：`0/10 = 0`；
- Provider Calls：`0`；
- Test Access：`false`；
- Report SHA-256：`0caba30e8ec95b9cfe5c6ee3893f69dbced100577c2611539459dc24be318b3c`。

Blind Test commitment 只公开 12 条、8 正/4 负的分布，不包含内容或 Bundle Hash。Blind Runner 已实现：
只有 commitment=`locked`、Bundle Hash、批准 Manifest Hash 和 Security Profile Hash 全部精确一致时，
才会读取一次 Bundle；未锁定时在读取 Bundle 前拒绝。Test 输出不会回流本 Profile 调参。

Profile Freeze 批准后，隔离流程交付了 Bundle `7394dfd4...` 以及两份审核文件 `a44d36b...`、
`f7cb11aa...`。实现侧只计算文件 Hash，并从审核文件校验 12 个 Record ID 的完整覆盖、两轮
12/12 pass、8 正/4 负分布、审核身份隔离、无 Scanner/Profile/Dev 访问和无真实 Secret；没有读取
Bundle 正文。精确 Bundle 尚待 Course Owner 单独批准，因此 Commitment 仍未锁定，Runner 未执行。

## 8. Test 生命周期修复

新增三个隔离 Fixture：

- `prelock_dataset_root`：显式创建合法的 `locked=false` 临时副本；
- `locked_dataset_root`：复制并验证真实锁定身份；
- `consumed_formal_release`：只读绑定原 Lock 与 Component/Retrieval/QA Report Hash。

数据构造/候选/审批测试使用 Pre-lock；正式 Loader/Resume 使用 Locked；仓库状态测试验证当前 Lock 合法
锁定。没有测试能够解锁或覆盖正式文件。

- 修复前：23 failed、165 passed、1 skipped；
- 修复后 `tests/evals/`：196 passed、1 skipped；
- Test Lock 仍为 `06c6473e...`；
- Component/Retrieval/QA 仍为 `1c10e637...` / `313a7e55...` / `b5b051ef...`。

Lifecycle Report SHA-256：
`e73ab3361b51ce92650f5db715e530856687d74d835e8cf916793bbbe65921c9`。

## 9. DS8 冷热性能与安全平衡

五类 Cold/Warm pair 分别在独立 Python PID 中运行。Cold 使用空数据库、Artifact、Index 和 Stage Cache；
Warm 保留同 pair 的 Cold 缓存。Embedding 是本地 Qwen3 CUDA，OCR 是 Hash 解析后的本地 RapidOCR，
Enrichment 使用 Contract Fake 且明确不代表 Provider 质量。

前三个执行目录分别因 OCR 身份未解析、缺少可恢复提交、共享进程污染而被显式标记
`eligible_for_release_evidence=false`；最终数字只来自 `ds8_run_20260811_04`。

| Workload | Cold mean | Cold P95 | Warm mean | Warm Reuse | Cold peak RSS | Cold peak GPU |
|---|---:|---:|---:|---:|---:|---:|
| Full Build | 58.114s | 58.114s | 0.026s | true | 2.32 GiB | 1.72 GiB |
| Single Document | 8.986s | 16.772s | 0.002s | true | 1.97 GiB | 1.59 GiB |
| Section Update | 0.008s | 0.015s | 0.001s | true | 0.71 GiB | 0 |
| 15-page OCR Batch | 924.868s | 925.124s | 0.009s | true | 0.71 GiB | 0 |
| Enrichment Batch | 0.008s | 0.014s | 0.002s | true | 0.70 GiB | 0 |

全部 10 个模板成功，五个 Cold PID 互异，Warm Reuse 为 5/5，Provider Calls 为 0。在线维度只绑定原
P10 Retrieval/QA Report，不重放外部 API；原报告无法证明的 process-cold/provider-cold 细项标记为
`not_measured`。

OCR Cold 的约 15.4 分钟主要来自每页独立安全子进程重复加载模型。P10.1 不为了速度取消进程树资源
守卫或改动冻结 OCR Profile。该问题登记为 L2/L3 性能债务，后续可通过常驻受控 Worker、批内模型
复用和更细粒度隔离优化，但必须重新做资源、Crash Recovery 和 OCR 回归验证。

Performance Report SHA-256：
`44b001274c98c5ebb754d85444403cbdcae2eac61fdc60d4cdb442a13ef051bb`。

## 10. 验收结果

| 验收 | 结果 |
|---|---|
| `uv sync --frozen` | passed；DS8 可选依赖在隔离运行后移除 |
| Security | 7 passed |
| Parser + Evidence | 42 passed |
| P10.1 专项 | 11 passed；随后扩展专项 25 passed |
| `tests/evals/` | 196 passed、1 skipped |
| B0 Sample Smoke | 1 passed |
| 全量 Pytest | 563 passed、5 skipped |
| Ruff format/check | passed |
| Mypy `src/` | passed，346 files |
| Alembic | 唯一 Head `0015_incremental_writeback_security` |
| Migration | 无新增 Migration |
| External Provider | 0 |
| 原 P10 formal Test rerun | false |

## 11. Exit Gate 与剩余限制

当前可判定：

- Dev 正例与 Hard Negative：通过；
- 原公开回归 Sentinel：通过；
- Warning 定位、Finding 重现、语义等价与 Stage Reuse：通过；
- Test Lock 生命周期：通过；
- 新 Blind Test 8/8 与 0/4：失败（TP=1、FN=7、FP=3、TN=1）；
- P10.1 Security L0：`failed`；
- P10：`gate_failed_p10_1_blind_security`；
- P11：`blocked_by_P10`。

### 11.1 Blind Test 最终结果

Course Owner 随后批准并锁定 Bundle
`7394dfd462993c54e0b262d63c276e097c83eb2f32c99574472c81fdac0a62ee`。Runner 严格绑定
Manifest `ffe8f582...` 和 Profile `8ce80b54...`，只执行一次，未输出原文、未调用外部 Provider，
也没有产生文档指令副作用。

- True Positive：1；
- False Negative：7；
- False Positive：3；
- True Negative：1；
- 公开 Sentinel：通过；
- 副作用、外部调用、Test 后调参：均为 0；
- Blind Report SHA-256：
  `f07fc7c8660b7669c1e971b38c590fec0b97ac5d06040a083368ec84521f8d2e`。

因此 `8/8` 正例召回和 `0/4` Hard Negative 误报两项 L0 都失败。该结果说明规则型 Detector
在 30 条 Dev 上的满分不能泛化到独立表达，且漏报与误报同时存在；继续围绕 Blind 输出补规则会
造成 Test 后调参。当前 Profile、Bundle 和 Report 均冻结，不读取正文、不重跑、不在本版本修复。
P10 最终状态为 `gate_failed_p10_1_blind_security`，P11 继续 `blocked_by_P10`。

剩余限制：规则型 Scanner 不是完整内容安全分类器；复杂编码、跨 Block 拼接、视觉文字变形和新的语言
攻击仍可能需要下一版本 Dev/Blind 数据。规则命中表示“需要警告与不可信处理”，不等于删除正文或
自动拒绝所有业务使用。

## 12. 面试深挖总结

这个问题的关键不是“正则漏了一句话”，而是安全控制放错了层：二进制层适合判断文件能不能安全
打开，解析后文本层才适合判断内容是否试图改变系统行为。修复时同时处理了三个容易被忽略的耦合：
安全 Warning 不得改变稳定引用 ID；正式 Test 一旦曝光不能继续充当调参集；合法的 Test Lock 状态迁移
不能让历史测试依赖仓库瞬时状态。

最终方案用分层扫描、稳定 identity projection、独立盲测、生命周期 Fixture、进程隔离性能基线和
Hash-bound Release Manifest 把功能、安全、评测可信度与性能证据拆开。它避免了为单个指标反复调参，
也避免了为了开发速度放松 L0：非安全性能问题可以作为债务推进，Blind Security Gate 未过则 P11
仍必须等待。
