# P17.3 三态安全检测收敛

## 修复动机

P17.2 证明现有 HikmaAI、Qwen3、Structured 与 Scope 特征无法同时满足二元 Recall 1.0 和 Specificity 0.975。继续移动阈值只会在漏报与误报之间反复振荡，因此 Course Owner 批准 `attack / needs_review / safe` 三态合同：无法自动可靠分类的内容必须进入人工复核，不能被强制猜成安全或攻击。

## 已完成实现

- 新增冻结的三态 Profile、边界校验、稳定 Decision DTO 与 Finding；
- `attack` 与 `needs_review` 均产生可定位 Finding，`safe` 不产生阻断 Finding；
- 新增 v4 Security Annotation Stage，未发布 Profile 不能执行；
- Candidate 选择器只读取 P17.2 已冻结组件分数，不重复调用模型；
- Runtime 支持三态 Provider，但 Candidate 始终默认关闭；
- 未新增数据库迁移或公开 API 必填字段。

## Calibration Candidate

- Profile SHA-256：`a6b905b0f42ad12637f07b44764355d1a1ecc24004de9e87effb6032162ab20e`；
- Selection Report SHA-256：`67ec5b8239ca70c131cf0e64092ed49d0c46817a70dcec4b3dbbcdc86e1b900f`；
- 恶意：76 attack、44 needs_review、0 safe；
- Hard Negative：3 attack、95 needs_review、22 safe；
- 恶意捕获率：1.0；
- Hard-negative Attack Specificity：0.975；
- 人工复核率：139/240，即 57.9%。

Candidate 满足预注册的离线选择约束，但人工复核负担较高，因此其自动化质量并未得到证明。Course Owner 批准 Candidate 后，另行构造并审核了与 P17.1 Calibration 文本 Hash 零重叠的 120 条 Qualification。

## 唯一 Qualification 结果

- Qualification Candidate SHA-256：`66a70fe2458745115cf39394e184f59dc1fa544a122c680d51fff67bb747c9fa`；
- Qualification Review SHA-256：`f0583ef3af1198bafe2d9c8845b12e3f24eca7bcc81c50112eebe8a374016c6f`；
- Result Report：`storage_eval/p17_3_security/qualification_report_r1.json`；
- Result Report SHA-256：`143e386d23f7a1b256b7e922fe4daf2572412e89365495a854b30b25022c79d3`；
- 恶意：30 attack、30 needs_review、0 safe；
- Hard Negative：6 attack、52 needs_review、2 safe；
- 恶意捕获 Recall：1.0；
- Hard-negative Attack Specificity：0.90；
- 人工复核率：82/120，即 68.33%；
- 英文 Hard-negative Specificity：0.8333；中文：0.9667；
- 外部 Provider、网络、付费 API、Fallback 与 Blind Access：全部为 0。

Qualification 未达到冻结的 Hard-negative Attack Specificity `>=0.975`，因此结果为 `failed`。虽然三态合同成功避免了把恶意样本判为 `safe`，但 6 个 Hard Negative 被直接阻断，且 68.33% 的样本进入人工复核，说明当前自动检测能力和运维负担均未达到发布标准。

## 当前结论

P17 系统集成、Trace/Version、写回闭环和故障恢复结果保持有效；P17.3 安全 Release 则为 `gate_failed_security_qualification`。Profile 继续 `enabled=false`，不得运行或准备 Blind，不得根据 Qualification 结果继续调阈值或重跑。

Course Owner 随后明确批准将 P17 按 `completed_with_isolated_security_automation_debt` 收口，并允许 P18 启动。该决策不把本次失败改写为通过，也不发布 P17.3 Detector：Profile 继续默认关闭，Qualification 报告保持不可变，Blind 未构造、未读取、未运行。

P17 的通过范围仅包括已经验证的系统集成、Remote Contract、Trace/Version 连续性、Stale Preflight、写回闭环、ACL、Approval、跨课程隔离、工具禁用、Secret 隔离和幂等副作用。P18 必须继续独立验证这些 L0 控制，且不得将 Detector 输出作为信任、授权、工具或写回依据。未来若要启用 Detector，必须重新建立独立 Release，不能复用本次依赖豁免。
