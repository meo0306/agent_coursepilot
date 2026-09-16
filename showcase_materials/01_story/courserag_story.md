# CourseRAG 独立项目故事

## 一句话定位

CourseRAG 是面向中文课程资料的 Evidence-first 知识服务：把 PDF/DOCX/扫描资料转换成带
稳定来源定位的 Evidence，通过版本化混合检索和 Context Packing，为上层 Agent 提供可核验
引用，而不是只返回相似 Chunk。

## Motivation

原系统直接把课程资料切块后写入向量库。它能快速完成 Demo，但有三个根本问题：

1. Parser、Chunk 和索引变化会让引用 ID 漂移；
2. 向量召回无法稳定覆盖中文术语、数字和特殊符号；
3. Agent 得到的是相似文本，不是可回到原文页码和 Source Span 的证据。

因此重构优先级被确定为“解析结构 → 检索准确率 → 引用可信度”，而不是先堆复杂 Reranker。

## Architecture

```text
DocumentVersion
  → Parser Router / OCR
  → Structured Document IR
  → Stable Evidence
  → Parent/Child Chunk + KP Links
  → Dense Index + BM25S Index
  → RRF Fusion + Reranker
  → Query Pipeline
  → Evidence-aware Context Package
  → Claim-Evidence QA / CoursePilot HTTP Port
```

PostgreSQL 保存文档、Evidence、版本、运行记录和审批事实。向量索引、BM25、缓存和 Trace 都不
作为唯一事实源。

## 关键设计取舍

### Evidence 与 Chunk 分离

Chunk 为召回优化服务，会随窗口、Overlap 和模型变化而改变。Evidence 用文档版本、原文范围和
内容 Hash 定位，作为 Citation 和 Gold 的稳定身份。检索命中 Chunk 后必须通过 Repository 回源
Evidence 与正文。

### Hybrid Retrieval

Dense 负责语义召回，BM25S 负责术语、数字、版本号和 `C++`、`A*` 等符号。两路先各取候选，
使用 RRF 按 Rank 融合，避免直接比较不可兼容的原始分数，再由可配置 Reranker 重排。

### 版本一致性

查询开始固定 Primary Index 和 Verified Overlay 版本，整个请求不跨版本读取。发布新索引采用
Staging、Manifest 校验和 Active Pointer 原子切换；构建失败保留旧 Active。

### 写回隔离

教师审核内容进入独立 Verified Overlay，而不是覆盖教材 Primary Index。撤销通过发布新 Overlay
实现，原内容和审计历史保留。

## 评测

评测按 Parser、OCR、Evidence、Retrieval、Context、QA 和 Incremental 分层。正式 Gold 经过人工
审核，不用 LLM-as-a-Judge。主要可公开 Dev 数字：

- Hybrid Recall@10：0.9167；
- Complete Evidence Group Recall@8：0.8611；
- Rerank MRR@10：0.7014；
- Rerank nDCG@10：0.8006；
- QA Answer Status Accuracy：0.9167；
- Unanswerable Recall：1.0；
- Citation Resolvability / Claim-Citation Completeness：1.0 / 1.0。

这些结果仅适用于课程特定小规模 Dev 集。

## 已知限制

- KP 名称抽取质量不高，Evidence 绑定好于命名质量；
- 自动 Prompt Injection Detector 未冻结，运行时依赖 ACL、工具禁用和不可信 Context 边界；
- P18 未恢复正式 Test Index，不能宣称完整正式 Track B 通过；
- 共享 PostgreSQL 实例暂未拆成独立数据库或独立账号。
