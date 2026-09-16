# 从单体 CoursePilot 到 CourseRAG + CoursePilot

## 30 秒版本

项目最初是一个把 RAG、教案、试卷和 PPT 都放在一起的备课 Demo。随着功能增加，Agent 节点
开始直接依赖 Chroma 和 Chunk，检索改动会影响生成流程，也无法区分 RAG 问题和 Agent 问题。
我先引入 CourseRAGServicePort 做逻辑拆分，再分别建设 Stable Evidence、版本化混合检索和
CoursePilot 的 Checkpoint、Interrupt、ArtifactVersion、Validation/Repair，最后通过 HTTP、双
Schema 和独立 CI 物理拆成两个仓库。正式评测没有掩盖失败：工程闭环通过，但内容质量仍有
债务，因此当前定位为可演示的工程 MVP，而不是生产质量产品。

## 完整演进路径

```text
单体 Demo
  → CourseRAG Port / Legacy Adapter
  → 评测基础设施和人工 Gold
  → CourseRAG Evidence-first 数据层
  → Hybrid Retrieval / Context / Cited QA
  → 增量、迁移、Verified Overlay
  → CoursePilot Typed Runtime / Model Gateway
  → PostgreSQL Checkpoint / Interrupt / Approval
  → ValidationIssue / Targeted Repair
  → Lesson / Exam / PPT V2
  → 双进程 HTTP 集成、Trace、Stale、Writeback
  → Locked Test
  → 两个公开仓库和本地作品集 Demo
```

## 为什么不一开始就拆仓

直接拆仓会同时改变包边界、数据模型、API 和运行时，难以区分迁移错误与业务错误。我选择：

1. 先抽象 Port；
2. 保留 Local/Remote/Mock Adapter 和 Legacy 行为；
3. 稳定 API、版本、错误和幂等合同；
4. 用双进程验证跨服务边界；
5. 最后物理拆仓。

优点是每一步可回滚，缺点是过渡期需要维护兼容层和较大的工作树。

## 十个关键难点

### 1. 引用随 Chunk 漂移

**原因：** Chunk 由窗口、Overlap 和模型决定，不是稳定业务身份。

**方案：** 引入 Stable Evidence，保存文档版本、Source Span、页码、BBox 和内容 Hash；Chunk 只
建立 N:N Evidence Link。

**结果：** Citation、迁移和 Gold 不再依赖 Chunk ID。

### 2. 一次检索跨索引版本

**原因：** Active Index 在请求中途可能切换。

**方案：** 请求开始固定 Primary 和 Overlay Version，Dense/Sparse 必须来自同一版本；新版本
通过 Staging、Manifest 校验和 Active Pointer 原子发布。

### 3. 中文语义召回与术语召回难兼顾

**方案：** 本地 Qwen3 Embedding + BM25S + 搜索分词 + 字符二元组兜底，再用 RRF 融合和
Reranker 重排。

### 4. Agent 状态不可恢复

**方案：** 稳定 Thread、PostgreSQL Checkpoint、Typed State 和 ContextPackageRef。Checkpoint
不保存完整正文和 Secret。

### 5. 人工编辑覆盖历史

**方案：** Artifact 和 ArtifactVersion 分离，编辑、Repair 和 Regenerate 都创建新不可变版本，
Resume 校验当前版本和 Precondition。

### 6. LLM 修复范围失控

**方案：** ValidationIssue 精确定位，RepairPlanner 预先决定 `allowed_paths`；修复后计算未授权
修改和新增回归。

### 7. 并行生成破坏全局一致性

**方案：** Exam 按 Batch 有界 Fan-out，Fan-in 后按 Blueprint 顺序重排并重新执行全局校验；
局部 Batch 通过不能替代总分、覆盖、重复和泄漏检查。

### 8. PPTX 能生成但不可用

**方案：** 使用真实 Master/Layout 和可编辑 Office 对象，固定 LibreOffice/Poppler 渲染，检查
页面数量、必需文本、Shape Boundary、Overflow 和 Placeholder。

### 9. 写回和导出可能重复

**方案：** Approval Scope、Artifact Version、Operation Key 和 SideEffect identity 联合保证幂等；
写回只进入 Verified Overlay，不能覆盖 Primary Source。

### 10. 端到端指标无法归因

**方案：** Track A 固定 Context/KP/Evidence 评价 Agent；Track B 连接真实 CourseRAG 评价系统。
正式 Test 锁定后不回流调参。

## 真实失败与反思

### PostgreSQL 真实集成晚于 Fake

Fake 测试不能证明真实事务、锁和 Checkpoint 恢复。接入 Docker PostgreSQL 后才暴露 Stale
Interrupt Status 和 Decision Hash 冲突，说明数据库边界必须做真实 Integration Test。

### 自动 Prompt Injection 检测没有达到门槛

规则、ONNX 和多模型候选都无法同时保证 Recall 与 Specificity。最终保持 Detector 默认关闭，
用 ACL、课程隔离、工具禁用、Secret 隔离和审批控制危险副作用。这证明分类器只能作为信号，
不能替代授权边界。

### P18 正式质量 Gate 失败

正式 Test 中出现 4 个生成失败、8 个合同失败和较低人工接受率。没有使用 Test 继续调 Prompt，
而是冻结结果、公开限制并将项目定位为工程 MVP。下一版本应重新建立 Dev Candidate 和独立 Test，
不能重跑已消费 Test。

## 面试结论

项目的主要成果不是“模型生成得特别好”，而是把一个不可控 Demo 重构成了具备数据版本、
证据引用、可恢复工作流、人工审批、局部修复、幂等副作用和可信评测边界的双服务系统。
