# Agent / RAG 项目深挖问答

## 1. 为什么拆成 CourseRAG 和 CoursePilot？

原单体中 Agent 节点直接依赖 Chunk 和向量库，Retriever 改动会影响业务 Graph，端到端指标也
无法判断是检索失败还是生成失败。我先抽象 CourseRAGServicePort，再稳定 Evidence、Context、
错误和版本合同，最后通过 HTTP 物理拆仓。这样 CourseRAG 可以独立评价 Recall/Citation，
CoursePilot 可以在固定 Evidence 下评价 Agent 工作流。

## 2. 为什么不是一开始就做微服务？

当数据模型和接口尚未稳定时直接拆仓，会同时承受业务重写、网络边界和部署问题。我采用
Port → Adapter → 双进程 → 物理仓库的渐进方式，保留 Legacy 路径做兼容和 B0 对照。代价是
过渡期代码较多，但每一步都可回滚和验证。

## 3. 为什么 Evidence 不能用 Chunk ID？

Chunk 是检索优化产物，窗口、Overlap 或模型变化都会改变它。Evidence 是引用事实，必须能回到
文档版本、页码、BBox 和 Source Span。检索仍索引 Child Chunk，但输出 Citation 时通过
Chunk–Evidence Link 回源 PostgreSQL。

## 4. 为什么使用 Dense + BM25 + RRF？

Dense 擅长语义改写，BM25 对课程术语、数字和特殊符号更稳定。两路原始 Score 不可直接比较，
RRF 只基于 Rank 融合，鲁棒且可解释。Reranker 只对融合后的有界候选重排，并保留完整阶段 Trace。

## 5. 为什么选择本地 Qwen3 Embedding？

课程索引会批量发送大量教材 Chunk，本地部署可以降低持续费用和数据外发。Qwen3-Embedding-0.6B
在 RTX 4060 Laptop 8GB 上显存约 1.13–1.28 GiB，Batch 8 实测约 123 items/s，适合作品集和
中小课程离线构建。Reranker 仍保留 HTTP Adapter，因为其候选量更小、替换成本较低。

## 6. 为什么用 LangGraph，而不是普通函数链？

核心需求不是“调用多个函数”，而是稳定 Thread、人工 Interrupt、暂停数小时后 Resume、服务重启、
Edit/Replan、Node Reuse 和副作用幂等。LangGraph 提供状态图和 Command Resume，业务事实仍保存在
PostgreSQL 的 Task、Artifact、Approval 和 SideEffect 表中，避免框架状态成为唯一事实源。

## 7. Typed State 解决了什么问题？

旧 State 混合宽泛字典、完整 Context 和消息历史，难以序列化和复用。新 State 只保存 Pydantic DTO、
Artifact/Context 引用、Hash、Warning 和 Error。正文在节点执行时临时 Resolve，Secret 和无界消息
不进 Checkpoint。

## 8. ArtifactVersion 为什么不可变？

人工编辑、Repair 和 Regenerate 必须保留“谁基于哪个版本做了什么”。覆盖原 JSON 会让审批和
Checkpoint 失去含义。Artifact 是稳定业务对象，ArtifactVersion 是不可变内容；Approval、Export
和 Writeback 都绑定具体版本，旧版本不能被新编辑追认。

## 9. Targeted Repair 如何防止 LLM 乱改？

Validator 先输出可定位的 ValidationIssue。RepairPlanner 在调用模型前决定 `allowed_paths`、
Precondition 和 Profile。Patch Apply 会拒绝越界路径；修复后同时重跑目标和全局校验，并比较未授权
字段与新增 Regression。LLM 只生成候选 Patch，不能自行决定权限范围。

## 10. Exam 并行为什么还要 Global Validation？

每个 Batch 单独正确，不代表整卷总分、题量、覆盖和语义多样性正确。Fan-out 后 Fan-in 按 Blueprint
顺序稳定排序，再统一编号和做全局校验。重复题只修后出现题，缺题只生成缺失 Slot，不整卷重跑。

## 11. 如何保证 PPT 可编辑和可渲染？

使用 python-pptx 创建真实 Text、Table、Shape、Connector 和 Picture Placeholder，不把整页栅格化。
模板以 Layout Role 而不是数组下标映射。导出后用固定 LibreOffice 转 PDF、Poppler 生成 PNG，检查
页数、必需文本、Shape Boundary、Overflow、字体和空 Placeholder。

## 12. 如何避免重复导出和写回？

SideEffect identity 绑定 Approval Scope、Artifact Version、Target 和 Operation Key。同 Key 同请求返回
原结果，不同请求返回冲突。远程写回还携带 CourseRAG Idempotency Key；状态不明的请求不自动重发。

## 13. 为什么 Primary Index 和 Verified Overlay 分开？

教师审核内容有价值，但不能覆盖教材事实。Primary 保存课程资料，Overlay 保存批准片段并独立版本化。
查询可以融合两路结果，Trace 同时记录两个版本。撤销只发布新 Overlay，不重建 Primary。

## 14. 如何判断旧 Artifact 已经过期？

ContextBindingRef 保存 Primary/Overlay Version 和每条 Evidence 的 Document Version/Hash。导出或写回前
调用 CourseRAG Validate Binding；发生索引、Evidence 或课程变化时返回 Stale，任务进入 needs_review，
刷新 Context 并创建新 ArtifactVersion 后必须重新审批。

## 15. 评测数据如何构造？

LLM 可生成候选，但正式 Gold 和 Rubric 必须人工审核。数据按 Dev/Test 分割，Test 只有在 Frozen
Manifest 批准后解锁。Retrieval 在 Evidence 层评分，Agent 使用固定 Context 的 Track A，系统使用真实
服务的 Track B。不使用 LLM-as-a-Judge。

## 16. P18 为什么失败？

锁定 Test 中有 4 个 Provider/Schema 失败、8 个合同失败；24 项人工审核只有 7 minor、13 major、
4 reject。Track B 又缺少可恢复正式 CourseRAG Test Index，7 条 live Journey 被阻塞。因此工程能力
完成不等于内容质量通过。我没有用 Test 继续调 Prompt，而是冻结失败并把产品定位为工程 MVP。

## 17. 失败后为什么还值得放进简历？

项目证明了从数据、检索到 Agent、审批、导出和写回的工程闭环，也证明我会设计真实会失败的评测，
而不是只展示挑选后的成功案例。简历突出可验证工程实现，面试主动说明质量边界和下一版本计划。

## 18. 如果继续做，优先改什么？

1. 用新的 Dev 数据修复 Provider/Schema 失败和 Exam 全卷多样性；
2. 重建可独立发布的 CourseRAG Formal Index；
3. 为内容质量候选建立新的独立 Test，而不是重跑旧 Test；
4. 将双 Schema 进一步拆成独立数据库账号/实例；
5. 自动 Prompt Injection Detector 只作为辅助信号，继续保持授权边界独立。
