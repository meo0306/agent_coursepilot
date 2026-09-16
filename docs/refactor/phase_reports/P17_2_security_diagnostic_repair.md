# P17.2 Security Diagnostic Repair

## 修复目的

P17.1 唯一 Calibration 没有保存逐样本组件分数，无法区分“搜索范围过窄”和“特征本身不可分”。P17.2 在不读取已消费 Blind、不运行 Qualification、不访问网络和外部 API 的前提下，对相同的 240 条人工批准 Calibration 执行一次新的诊断运行，并保存完整组件证据。

## 实现与验证

- Runner 增加独立的 `diagnostic_repair` 模式；
- 保存每条记录的 Hikma、攻击语义、安全语义、结构、Scope、Prototype 和错误 ID；
- 本地模型只运行一次，后续权重搜索完全复用内存分数；
- 在 Recall、语言 Recall 和四个 Family Recall 均为 1.0 的约束下，确定性搜索软特征权重、阈值和边际；
- 最多允许一个 default-off Finalist；
- 新增合成约束测试，专项测试 7 passed，Ruff 和 Mypy 通过。

## 结果与原因分析

诊断报告 SHA-256 为 `f3f124d69678b872f2cb18f489df4d08990d432e3b53791e339f33cbb0703f66`。网络、外部 Provider、Fallback、Qualification 和 Blind Access 均为 0。

结果仍为 `calibration_failed`。最佳 Recall=1 的凸权重组合只有 Specificity 0.30，即 120 个 Hard Negative 中误报 84 个。组件分布解释了失败原因：

- 120 个恶意样本中有 4 个被 Scope 判为 `educational`；
- 120 个 Hard Negative 中有 57 个被 Scope 判为 `operative`；
- Hikma 恶意/Hard-negative 均出现接近 0 和接近 1 的重叠；
- Structured Score 在两类上的均值接近，无法提供有效区分；
- Qwen3 攻击与安全原型相似度虽有均值差异，但分布仍大范围重叠。

使用 construction group 隔离的五折 Logistic Regression 做只读可行性检查：无类别加权时 Recall 0.90、Specificity 0.908；逐步提高恶意权重可将 Recall 提高到 0.967，但 Specificity 降至 0.767。现有特征无法通过继续调权重同时满足 Recall 1.0 和 Specificity 0.975。

## 当前结论

P17.2 排除了阈值范围和简单线性组合问题，确认根因是现有 HikmaAI + 通用 Qwen3 Embedding 在当前安全合同下的特征可分性不足。继续补规则、扩大网格或降低门槛都会形成无界调参或牺牲另一侧指标，因此停止产生候选。

P17 保持 `gate_failed_security_release`，Candidate 保持 default-off，P18 继续阻塞。后续必须由 Course Owner 选择更强的专用本地语义模型，或批准将安全检测合同升级为 attack / needs_review / safe 三态并单独冻结人工复核边界。
