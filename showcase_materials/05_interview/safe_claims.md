# 可安全使用的表述

## 无需附带复杂限制

- 个人独立项目；
- 两个公开仓库；
- CoursePilot 与 CourseRAG 使用 HTTP Port 解耦；
- PostgreSQL 双 Schema、独立 Migration；
- Typed State、Checkpoint、Interrupt、ArtifactVersion；
- ValidationIssue、Targeted Repair、Approval Scope、幂等副作用；
- Stable Evidence、Hybrid Retrieval、RRF、Reranker、Context Packing 和 Citation；
- Docker 本地 Demo 无付费 Provider 调用；
- CourseRAG 199 passed，CoursePilot 258 passed；
- P19 作品集发布 Gate 通过。

## 必须带限定词

- “在课程特定 Dev 集上，Hybrid Recall@10 达 91.67%”；
- “在课程特定 Dev QA 上，Citation Resolvability 达 100%”；
- “P16 Dev Pilot 的 3 份 PPTX 均可打开渲染”；
- “工程合同和安全副作用控制通过，但 P18 正式内容质量 Gate 未通过”；
- “Main/Light 具备逻辑 Profile 路由能力，当前使用同一物理模型”。

## 推荐项目定位

- Agent/RAG 工程 MVP；
- 可运行、可审计、可恢复的作品集系统；
- 不是生产质量认证；
- 不以商业级 PPT 视觉设计为目标。
