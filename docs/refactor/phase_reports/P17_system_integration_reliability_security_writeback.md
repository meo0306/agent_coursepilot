# P17 系统集成、可靠性、安全与写回闭环

## 结果

P17 的系统集成功能和非安全专项 Gate 已完成，但独立 Security Blind Release 失败。因此
阶段最终状态为 `gate_failed_security_blind`，r2 检测 Profile 保持 rejected/default-off，
P18 不具备开始条件。

## 完成的任务

- P17-T01：完成双进程 CoursePilot/CourseRAG App Factory、Remote Client Bearer、Deadline、
  分类重试、Request/Trace ID 和无 Local Fallback 合同。
- P17-T02/T03：保存 Primary、Verified Overlay、Composite Snapshot 与 Evidence Version；
  统一 Stale Preflight 在导出/写回前失败关闭并要求重新审核。
- P17-T04：完成 VerifiedContent、即时 Overlay、Enrichment Lease/Item 幂等、KP 链接、
  新 Overlay 发布及后续检索来源闭环。
- P17-T05/T07：完成 CourseRAG/Graph/Validator/Exporter/Writeback 错误隔离，以及 Worker、
  Checkpoint、Export、Writeback 故障和重复副作用验证。
- P17-T06：实现 r2 Scope-first Action–Target–Effect + 本地 HikmaAI 佐证架构；Dev 通过，
  但 Blind 泛化失败，未推广运行时 Profile。
- P17-T08：CP-DS8 34/34 Variant 与 SYS-DS1 8/8 Journey 达到预期终态。

## 系统验证

- 双进程 Compose 中 CoursePilot、CourseRAG 和 PostgreSQL 均能独立健康运行；CoursePilot
  新运行时通过 HTTP/Port 访问 CourseRAG。
- `storage_eval/p17_system/report.json`：34/34 Fault Variant、8/8 SYS-DS1 Journey 通过，
  外部 Provider 调用为 0，报告 SHA-256 为
  `e66bce559a6069a299e937db2466e2ee1bc0783208875dbeeda094249bb3e2f5`。
- 跨课程 Evidence、未授权写回、Secret Trace、路径穿越、整件 Artifact 写回、重复
  Export/Writeback/Enrichment/Index 发布和静默 Fallback 均为 0。
- Trace、Version、Stale、Writeback Provenance 和 Completed Node Reuse 专项通过。

## Security Release

Qualification Dev r2 使用原 Approved 120 条、本地 HikmaAI CPU/ONNX、无网络和无外部
Provider执行一次：60 TP、60 TN、0 FP、0 FN，报告 SHA-256 为
`83463c48d7f051d1fcc042a35b90911a80cc12b45853b25599787157fb1ac387`。

Dev 通过后才构造独立 48 条 Blind。两轮 Course Owner 审核均完整，Bundle
`469f556c05d5c54e3f18db1972b045d338e8fac20aabc7c518fcd0a682cddf4b` 和 Approval
Candidate `83d00578c3c79cc8648f2333c195b74e0a737db86b895b421205d1f08f934f75`
获得精确批准。唯一一次 Blind 结果为：

- 11 TP、13 FN、1 FP、23 TN；
- 恶意 Recall `0.458333`；Hard-negative Specificity `0.958333`；
- 中文 Recall `0.416667`、Specificity `0.916667`；
- 英文 Recall `0.5`、Specificity `1.0`；
- Policy Override/Role/Secret/Tool Recall 分别为 `0.166667/0.5/0.666667/0.5`；
- Finding Span Resolvability `1.0`；网络、外部调用、Fallback、Secret/工具/未授权副作用均为 0。

Blind 报告 SHA-256 为
`a9c1004a4d1b3410dfead90093f2a7208ed65d7e2f4cb3250a65f62be6b335df`。结果未达到
预注册的 Recall 1.0 和 Specificity 0.975。按冻结规则，不使用 Blind 调参、不重新运行、
不启用 r2 Profile。

## Exit Gate

| Gate | 结果 | 证据 |
|---|---|---|
| 跨课程/未授权/Secret/重复副作用为 0 | 通过 | CP-DS8、SYS-DS1 与专项测试 |
| Trace 可跨服务追踪 | 通过 | Primary/Overlay/Evidence/Request/Trace 连续性 |
| 写回来源完整 | 通过 | Task、Artifact、Approval、Evidence、Batch、Overlay 闭环 |
| 独立安全 Dev 与 Blind | **失败** | Dev 通过，Blind Recall/Specificity 未达门槛 |

P17 因安全 Release 硬门禁失败，不能降级为普通质量债务。P18 继续阻塞。若后续继续安全
能力建设，必须形成新的架构和独立 Release 决策，不能围绕本次 Blind 样本修补 r2。

## 数据库、API 与配置

- 未新增 Alembic 迁移，Head 仍为 `0017_coursepilot_checkpoint_interrupts`。
- 新增/补齐的 HTTP 与可选 Trace/Version 字段保持向后兼容。
- Remote 模式不回退 Local；r2 Security Profile 未成为默认配置。
- 未调用 DeepSeek、Cohere、Jina 或其他付费 Provider。
