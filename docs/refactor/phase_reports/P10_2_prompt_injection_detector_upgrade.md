# P10.2 Prompt Injection Detector 架构升级阶段报告

## 1. 修复目的

P10.1 已经把检测位置从 PDF/DOCX 原始二进制修正到解析后文本，但独立盲测结果为
TP=1、FN=7、FP=3、TN=1。这证明“看得到正文”只是必要条件，基于少量短语组合的正则仍然
无法在真实改写、跨块语义和困难负例上泛化。P10.2 的目标不是让旧盲测变绿，而是把
检测器升级为可版本化、可定位、可审计的本地语义分类 Stage，并用全新的 Dev/Blind
发布流程重新建立安全证据。

## 2. 问题现象

1. P10 正式安全控制曾漏掉策略绕过语义；P10.1 公开 Dev 虽为 20/20，但独立盲测只命中
   1/8 正例，并误报 3/4 困难负例。
2. P10.1 Scanner 按单个 Block 扫描，不能稳定捕获跨 Block 的指令组合和长上下文攻击。
3. 安全 Profile 被写入 Parser/OCR Stage 指纹；仅修改安全检测就会重跑昂贵解析/OCR。
4. 正则 Finding 只有规则命中，没有模型、阈值、窗口和决策路径身份。
5. 如果继续追加失败句或查看旧 Blind 内容调规则，得到的是 Test 记忆，不是安全泛化。

## 3. 根因分析

根因不是某一条表达缺失，而是三个架构层次同时不足：

- 表征层：正则只能匹配表面词形，无法表达“命令意图 + 受保护目标 + 指令层级”的语义。
- 上下文层：逐 Block 扫描丢失跨块关系，长文档也没有重叠窗口。
- 生命周期层：检测与 Parser/OCR 耦合，Profile 变更成本过高，容易诱发少测或复用旧结果。

因此，单纯补一条正则既会再次过拟合，也无法解决误报和 Stage 耦合。

## 4. 方案提出与选择

选择本地 `Llama-Prompt-Guard-2-86M`：模型规模小于通用生成模型，适合离线二分类，不把
教材片段发送到外部安全 API。权重受 Llama 4 Community License 单独约束，存放在 D 盘
外部目录；Git 只保存 Adapter、Manifest/Hash 和 Notice。

决策链为：

`Canonical IR → 448-token overlap Window → Prompt Guard score → auxiliary rule signal → policy → locatable Finding`

其中高分由模型直接标记；中分必须与已注册高精度规则达成一致；低分即使正则命中也不能
标记。这样保留了规则的可解释定位能力，同时取消其独立裁决权。

## 5. 实施结果

- 新增模型无关 Detector、Score、Window、Segment 合同。
- 窗口最大 512 Token，正文窗口 448，重叠 128；支持跨 Block，并可逆映射到 Page、Block
  和字符区间。
- 新增本地 Transformers Adapter，启用 `local_files_only`，验证不可变 Revision、逐文件
  Hash、Bundle Hash、许可证接受状态和运行时禁网。
- 新增双阈值决策策略；规则只能辅助中分判定或细化 Finding。
- 新增独立 `security_annotation` Build Stage；Parser/OCR 不再包含安全 Profile/执行逻辑。
- 安全 Stage 替换 Artifact 中的 IR/Preview/Quality JSON，完整保留 OCR 结果和二进制资产。
- 新增 160 条 Dev Candidate：80 正例、80 Hard Negative，中英文各半，覆盖五类攻击、
  跨块、长上下文、轻度混淆、引用讨论和正常技术命令。
- 新 Blind 仅建立 48 条分布承诺，尚无内容，实施侧无法读取。
- 新增三份 JSON Schema、精确 Hash 审批 Loader、固定六组阈值网格和 Freeze Candidate Runner。

## 6. 当前验证证据

- Detector/Stage/Data/Runner 专项：25 passed（核心集合）；P10.2 数据/Schema集合另 20 passed。
- 全量：574 passed、5 skipped。
- Ruff format：527 files already formatted；Ruff check passed。
- Mypy：354 source files，0 error。
- Alembic：唯一 Head `0015_incremental_writeback_security`，P10.2 无 Migration。
- `git diff --check`：无 whitespace error，仅仓库既有 CRLF 提示。
- Dev Candidate SHA-256：`d017a907ec3ce4611c6e282c8b060ede1fb0f2692cb8807fc39ba5238f57a482`。

## 7. 尚未完成与阻塞

1. Hugging Face 模型为 gated repository。本机没有缓存 Token，匿名下载返回 401；当前外部
   模型目录只有上游 LICENSE/README，Manifest 不会把它误认为完整模型。
2. 锁定的 CUDA Torch wheel 约 2.4 GiB；下载连接中断。基础 `.venv` 未损坏，但真实模型
   Runtime 尚不能导入 Torch/Transformers。
3. 160 条 Dev Candidate 必须由 Course Owner 按精确 Hash 批准；系统不会自行批准标签。
4. 真实 Dev 网格、阈值冻结、GPU/CPU 实测和新 48 条 Blind 尚未执行。

2026-08-12 更新：Course Owner 已批准 Dev Candidate `d017a907...`，审批 Artifact 为
`d50315a0...`。HF 登录账号 `nancy0929` 已验证，但模型文件仍返回 403，原因是账号尚未进入
该 gated repository 的 authorized list。CUDA 依赖不再需要重新下载：本机 uv 历史缓存中的
Torch `2.12.1+cu126` 已通过 RTX 4060/CUDA 12.6 探针，锁定 Transformers `5.14.1` 已安装。

### 2026-08-12 依赖替换检查点

Meta 拒绝了 gated 模型申请，Course Owner 因此启用预注册的公开备选
`protectai/deberta-v3-base-prompt-injection`，固定不可变 Revision `373b6af0...`，许可证为
Apache-2.0。已批准的 160 条 Dev 数据及其审批保持有效，因为它们绑定安全标签而非模型权重。
备选继续复用模型无关 Detector、Window、双阈值与独立 Stage 合同。上游主要面向英文，因此
不宣称与 Meta 多语言能力等价；中文和英文都必须分别通过仓库 Dev 及后续 Blind Gate。

安装器只下载八个必要的 Safetensors、Tokenizer 和模型卡文件；公开模型下载不发送缓存的
HF Token，传输缓存不进入 Manifest 身份，并使用从官方固定 Revision 得到的逐文件 SHA-256
白名单。官方 Xet 在完成 7/8 个文件后发生响应解码错误；普通 HTTP 随后在约 6 MB/738 MB
权重处断开并在 TLS Resume 时超时。官方小文件与断点状态保留。只有镜像续传文件通过官方
Hash 白名单后，才允许生成 Manifest、运行 Dev 阈值网格和进入 Profile Freeze；Blind 未运行。

### ProtectAI Dev 结果

镜像续传完成后，八个文件与官方固定 Revision 的 SHA-256 白名单完全一致。模型 Manifest
文件字节/规范化内容 SHA-256 分别为 `4077c162...`/`9fb91fac...`，Bundle SHA-256 为
`2ffea548...`，权重 SHA-256 为 `4473925f...`。
RTX 4060 Laptop 上 CUDA FP16 冷加载约 11.15 秒，探针推理约 1.56 秒，PyTorch 峰值分配
显存约 371 MiB；160 条 Dev 的复用实例打分约 3.95 秒，峰值约 447 MiB。

Approved Dev 报告 `dda19635...` 未产生 Profile：六组预注册阈值全部失败，最佳网格为
TP=19、FN=61、FP=21、TN=59，即 Recall `0.2375`、Specificity `0.7375`。英文 Recall 仅
`0.125`，中文样本同样存在严重正负重叠。只读遍历全部观测分数后的理论最佳平衡准确率仅
`0.50625`，证明问题不是阈值网格范围，而是英文显式短语训练分布与中英文、间接改写、引用
讨论教材场景不匹配。根据一次校准和 L0 零容忍规则，本阶段未增加阈值、未恢复正则裁决权、
未生成 Candidate，也未读取 Blind。

## 8. 性能预期与验证边界

公开备选的 Safetensors 权重为 737,719,272 bytes，约为原 86M 候选的两倍规模。FP16 CUDA
路径预估总显存约 0.8–1.6 GiB，仍保留 2.5 GiB 预注册峰值上限；CPU FP32 路径预估约
1.5–2.5 GiB 内存并使用多个 CPU 核，但不作为 CUDA 配置的静默回退。最终只能以本机
RTX 4060 Laptop 的实测峰值、Wall Time 和吞吐作为冻结证据。

## 9. 回滚与兼容

默认 Provider 仍为 `legacy_rules`，因此现有公开 API 和旧构建路径不发生运行时切换。
在新 Profile 通过 Blind Gate 前，P10 仍失败、P11 仍阻塞；这不是把旧正则重新认定为安全。
如果本地模型身份、CUDA 或 Stage 失败，新构建停止并保留旧 Active Index，不删除任何旧
Artifact、报告、Blind 结果或 P10 Test Lock。

## 10. 面试深挖总结

这个问题展示了典型的“测试通过但泛化失败”：第一版修复纠正了检测位置，却仍把词形规则
当成语义模型。独立盲测暴露后，没有围绕失败文本循环加规则，而是冻结失败证据、重建
Detector/Window/Stage 生命周期，并把模型身份、许可证、Hash、人工审批和一次性 Blind
纳入同一个可审计合同。工程重点不是模型替换本身，而是防止模型缺失时静默退化、防止
Profile 变更引发无关 Parser/OCR 重算，以及防止 Test 结果回流调参。

## 11. HikmaAI multilingual ONNX second-backup result

After the ProtectAI backup demonstrated a strong domain mismatch on Dev, the Course Owner approved
`HikmaAI/hikmaai-mdeberta-v3-base-prompt-injection-multilingual` at immutable revision
`aef60fed9674e497a7ba08e43b41e8666483934e`. The FP16 ONNX path preserves the existing
Detector/Window/Policy contract while adding explicit Chinese and English upstream coverage.

The snapshot was transported through a public mirror into the external D-drive model directory;
weights were not added to Git. The 558,531,786-byte ONNX file and 16,350,764-byte tokenizer match
the upstream LFS SHA-256 values `52b3cd13...afb0` and `9ddbe35b...2365`. Manifest file,
canonical-content and Bundle SHA-256 values are `f5332023...d1f`, `bebebecf...6026` and
`b1aa09e9...ef82`. ONNX Runtime GPU 1.21.1 is isolated under
`D:\AI\runtimes\p10_2_hikma_onnx`, so the RapidOCR CPU runtime is not replaced.

The exported graph requires CPU for a small number of static Shape/Constant nodes. The adapter
therefore requires CUDA as the first provider, allows CPU only for those graph-support nodes,
disables whole-session runtime fallback after initialization, and fails closed when CUDA is absent.
A non-evaluation smoke probe scored an explicit injection at `0.999995` and ordinary course text at
`0.000021`.

The single owner-authorized Dev run reused exact dataset `d017a907...`, approval `d50315a0...` and
the six preregistered threshold pairs. It did not read Blind or call any external provider. Report
SHA-256 is `29abe241...c90`. The best result was TP=62, FN=18, FP=0 and TN=80: Recall `0.775`,
Specificity `1.0`, English Recall `0.90`, Chinese Recall `0.65`, and tool-coercion Recall `0.50`.
This is a meaningful false-positive improvement over ProtectAI, but it remains below the L0
positive-recall requirement.

No threshold pair passed, so the runner emitted no Profile Candidate. The stage did not enlarge the
grid, restore independent regex authority, rerun Dev, or unlock Blind. P10/P11 remain blocked. Any
continuation requires a separately approved architecture/data decision rather than repeated tuning
on the consumed Dev set.

## 12. ModelScope Llama Prompt Guard source-risk checkpoint

The owner identified a public ModelScope copy at `LLM-Research/Llama-Prompt-Guard-2-86M`. Read-only
metadata showed that it is an uncertified `USER_UPLOAD`, not an authenticated Meta mirror, and that
ModelScope records its license field as `other`. The owner had previously been rejected by Meta's
official gated repository. After these facts were explained, the owner explicitly accepted the
source and license-provenance risk and authorized local use.

The ModelScope snapshot contains the Llama 4 Community License and Acceptable Use Policy. Eight
runtime and license files were downloaded from fixed commit `be11c20d...`; each matches the SHA-256
published by the ModelScope repository API. Manifest file/canonical/Bundle SHA-256 values are
`292cede1...b50`, `fc27f708...2ee`, and `ca7df59c...1c9f`. The repository Notice explicitly states
that this establishes snapshot identity only and does not prove that the uploader possessed
redistribution authority or that Meta approved the owner's access.

A local FP16 CUDA smoke passed: explicit attack score `0.999386`, ordinary course-text score
`0.000415`, and peak PyTorch allocated VRAM about `552.7 MiB` on the RTX 4060 Laptop GPU. This was
not a Dev or Blind run. The default provider remains unchanged, and any new qualification run must
be separately approved because the original Approved Dev has already been consumed by earlier
model candidates.

## 13. ModelScope Meta Dev qualification result

### Problem and qualification purpose

The public ModelScope snapshot supplied the architecture originally selected for P10.2, but its
two-case smoke could only prove that the runtime and label mapping worked. It could not establish
coverage over the repository's five security families or distinguish quoted security discussion
from an executable untrusted instruction. The owner therefore approved the exact qualification
Protocol SHA-256
`c1be800a5807d679d6b13ef41fe296f52cfac430cb59b851197e11da12eeaf8f` and authorized one Dev-only
run. The authorization explicitly excluded Blind and any second run.

### Execution identity and controls

- Model snapshot: ModelScope commit `be11c20d...`; Bundle `ca7df59c...`.
- Approved Dev dataset: `d017a907...`; owner approval: `d50315a0...`.
- Fixed six-pair threshold grid: unchanged from the approved Protocol.
- Access: Dev only; `test_access=false`, `blind_access=false`.
- Network/provider calls and fallback: both zero.
- Report SHA-256: `6946176f48249f699f2d177ee651083bd47b9ab13b598ecdc857e2efd27d38b4`.
- CUDA scoring time for all 160 cases: about `5.074` seconds.

### Result

No threshold pair passed and no Profile Candidate was generated. The best-recall pair produced
TP=17, FN=63, FP=14, TN=66: Recall `0.2125` and Specificity `0.825`. The most specific pair
produced Recall `0.20` and Specificity `0.8875`. At the representative best-recall setting,
category recall was:

- policy override: `4/16 = 0.25`;
- role impersonation: `2/16 = 0.125`;
- secret extraction: `2/16 = 0.125`;
- tool coercion: `0/16 = 0`;
- obfuscation: `9/16 = 0.5625`.

English and Chinese recall were `0.25` and `0.175`. The result is materially below both the L0
release obligation and the already rejected HikmaAI candidate (`0.775` recall, `1.0`
specificity).

### Root cause and decision

The failure is not an omitted threshold. All six preregistered pairs remain in the narrow
`0.20-0.2125` recall band, so enlarging the threshold grid cannot recover the missing semantic
families without changing the approved experiment after seeing Dev. Prompt Guard 2 is primarily a
prompt-override detector, while the repository's positive contract also treats role impersonation,
secret extraction and tool coercion as independently sufficient untrusted-instruction classes.
One binary model is therefore being asked to satisfy a broader security contract than its learned
task boundary.

The candidate is rejected for `default_v1`. Dev will not be rerun, Blind remains unread, and the
default provider stays `legacy_rules` without being reclassified as a passed boundary. After three
candidate failures, further model swapping or threshold tuning would be an unbounded calibration
loop. The next safe action is a separately approved architecture decision that separates threat
families and defines a reviewed union/ensemble Gate while preserving zero silent fallback and the
independent Blind lifecycle.

### Final regression evidence

- P10.2 detector/data/evaluation专项：`24 passed`；
- repository full test suite：`580 passed, 5 skipped`；
- Ruff format：`533 files already formatted`；Ruff check：passed；
- Mypy：`360 source files`, zero errors；
- Alembic：single head `0015_incremental_writeback_security`；
- `git diff --check`：zero whitespace errors，only existing LF/CRLF conversion warnings。

The first full-test attempt reached approximately 75% with no failures before the five-minute
command wrapper timed out. A clean rerun with a longer wrapper completed successfully; this was a
test rerun, not a Dev/model evaluation rerun.
