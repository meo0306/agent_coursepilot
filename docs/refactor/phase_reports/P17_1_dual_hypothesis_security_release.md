# P17.1 双假设安全检测独立 Release

## 修复动机

P17 的 Remote、Trace/Version、Stale、写回闭环、故障恢复和 SYS-DS1 已经通过；唯一失败项是安全检测 r2 的独立 Blind。r2 在 120 条可见 Dev 上全对，但在 48 条 Blind 上只有 0.4583 Recall 和 0.9583 Specificity，说明硬编码 Action–Target–Effect 与作用域规则存在明显的模板拟合。该 Blind 已消费，不能再用于修规则、调阈值或重跑。

## 原因与架构修复

r2 要求完整结构三元组，HikmaAI 只能佐证，导致语义模型即使识别风险也无法挽救缺少词表槽位的表达；Scope 又通过硬分类排除文本，使 Recall 和 Specificity 相互牵制。P17.1 改为两个竞争假设：HikmaAI、Qwen3 攻击原型和软结构证据共同形成 Attack Score；Qwen3 安全语境原型和 Scope 证据形成 Safe-scope Score。最终由冻结阈值与安全边际共同决定，任何检测结果仍不得参与权限或副作用授权。

## 已完成实现

- `SecuritySemanticEncoder` 与现有 Embedding Port Adapter，不导入索引内部实现；
- 双假设 Profile、语义原型、窗口评分、稳定 Finding 和 v3 Annotation Stage；
- Candidate 默认关闭，模型身份不匹配或缺失时失败关闭；
- 240 条全新 Calibration Candidate：恶意/Hard-negative 各 120，中英文均衡；
- JSON 审核模板、双 SHA 审核门禁和本地 Calibration Runner；
- 确定性阈值/边际选择目标，最多输出两个 Finalist；
- Runner 无旧 Blind 参数和访问路径，不调用网络或外部 Provider。

## 当前证据

- Checkpoint：`3f5c415 refactor: checkpoint CoursePilot P13-P17 integration baseline`；
- Calibration Candidate：`474425a80638ee0ba7ebd716229d1edaede3fd0b6683305698fb79198f140031`；
- Review Template：`ebea4ec7605aa83f67a33b8554017d1c3e007b80f73484028355c370c77cd50e`；
- Architecture Profile：`f7574295d3fbff5ddd249720450e997a663ef9eba3725debb1383c67fda14828`；
- 专项验证：82 passed；Ruff 通过；新增三个核心模块 Mypy 通过；`git diff --check` 通过（仅既有行尾提示）；外部调用和 Blind Access 均为 0。

## Calibration 结果

Course Owner 批准 Dataset `474425a...031` 和 Review `215cefd...83` 后，唯一一次本地 Calibration 已执行。运行耗时 138.16 秒，处理 240 条记录，网络、外部 Provider、Fallback、Qualification Access 和旧 Blind Access 均为 0。报告 SHA-256 为 `6390f90a1bb983a55ad773ce82672dc567a56383d4e110f5191dd3ef5baf0c85`。

结果为 `calibration_failed`：在预注册的阈值 `0.45—0.85`、边际 `-0.10—0.30` 搜索范围内，没有候选同时满足 Hard-negative Specificity `>=0.975`，因此 Finalist 数为 0。Runner 没有自动扩大搜索范围、降低门槛、修改 Profile 或进入 Qualification。

## 当前状态与下一步

P17 当前为 `gate_failed_security_release`，P18 继续阻塞。P17.1 Candidate 保持 default-off，Qualification 与新 Blind 不得运行。后续需要新的人工决策来选择：停止安全模型路线并保留隔离边界，或制定一个能够保存逐样本 Calibration 诊断、但不访问已消费 Blind 的窄范围修复。未经批准不得重跑本次 Calibration。
