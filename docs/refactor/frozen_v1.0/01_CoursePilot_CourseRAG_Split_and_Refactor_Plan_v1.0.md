# CoursePilot 与 CourseRAG 项目拆分及总体改造方案

**文档版本：** v1.0  
**文档状态：** 冻结执行版
**冻结日期：** 2026-07-22
**项目定位：** Agent 工程 60% + RAG 工程 40%  
**拆分策略：** 先逻辑拆分，后物理拆仓  
**适用目标：** Agent / 大模型应用开发岗位作品集、简历项目与技术面试

---

## 1. 文档目的

本文档用于确定 CoursePilot 与 CourseRAG 的整体边界、演进路线、接口关系和验收标准，作为后续以下文档的共同依据：

1. CourseRAG PRD；
2. CourseRAG 评测数据集与基线方案；
3. CourseRAG 具体技术改造方案；
4. CoursePilot Agent 工程化改造方案；
5. CoursePilot 与系统级评测方案；
6. 分阶段开发任务清单。

本文档只回答“两个项目为什么拆、拆成什么、如何协作、如何迁移”，不展开具体 Parser、Chunker、Retriever、Validator 或 LangGraph 节点的实现细节。

---

## 2. 已确认的核心决策

### 2.1 能力重心

项目作品集的能力展示比例确定为：

- **CoursePilot：Agent 工程能力约 60%**
- **CourseRAG：RAG 工程能力约 40%**

CoursePilot 是面向教师备课场景的上层业务 Agent 系统，重点展示工作流编排、结构化生成、校验修复、人工审核、持久化恢复、可观测性和文档导出。

CourseRAG 是独立的课程知识库与检索增强服务，重点展示中文课程长文档解析、结构化切分、混合检索、重排序、引用证据和可复现实验。

### 2.2 CourseRAG 优化优先级

CourseRAG 的优化优先级按以下顺序确定：

1. **提升文档解析能力**
2. **提升检索准确率**
3. **增强引用可信度**

该排序意味着第一阶段不会直接堆叠复杂检索算法，而是先建立可靠的文档中间表示和证据定位机制。检索与引用能力均依赖解析结果，解析错误不能通过 Reranker 根本修复。

### 2.3 模型使用原则

默认优先使用 API 模型，以降低本地部署、显存和环境维护成本。

允许在以下条件下使用本地模型：

- 模型体量较小；
- 部署和运行成本可控；
- 能明显降低 API 成本或延迟；
- 不影响项目复现；
- 已通过统一 Provider 接口与业务代码解耦。

初步默认方案：

| 能力 | 默认实现 |
|---|---|
| 主生成模型 | API |
| 查询改写 | API |
| 知识点抽取 | API，小模型或批处理 |
| Embedding | API 优先 |
| Reranker | API 优先，可切换本地 |
| BM25 | 本地 |
| 规则校验 | 本地代码 |
| 文件解析与结构识别 | 本地代码，必要时调用多模态 API |

所有模型能力通过统一配置和 Provider 接口调用，不允许在业务节点中硬编码厂商 SDK。

### 2.4 LangSmith Cloud 策略

项目允许将以下内容完整上传至 LangSmith Cloud：

- 课程原文；
- 检索片段；
- Prompt 模板；
- 运行时 Prompt；
- 模型输入；
- 模型输出；
- LangGraph 状态摘要；
- 校验错误和修复结果。

默认不进行课程内容脱敏或截断。

但以下凭据类信息无论如何不得进入 Trace：

- API Key；
- 数据库密码；
- JWT 和 Session Token；
- Cookie；
- 云存储临时签名；
- 用户登录凭据；
- 其他 Secret。

LangSmith 负责 Agent Trace、节点性能分析、Prompt 版本对比和运行诊断；PostgreSQL 继续负责业务数据、任务记录、审计结果和可恢复状态。

### 2.5 评测原则

当前阶段暂不使用 LLM-as-a-Judge。

评测以以下三类证据为主：

1. 程序可自动计算的确定性指标；
2. 人工审核后的 RAG Gold Dataset；
3. 小规模人工 Checklist 或评分表。

LLM 可以用于生成候选标注，但未经人工审核的内容不得作为正式 Gold 数据。

### 2.6 PPT 产品定位

PPT 功能定位为：

> 基于课程资料和教学设计生成带授课备注、引用信息和统一模板的可编辑课件初稿。

项目不以自动生成商业级精美课件为目标，不将复杂图片生成作为 MVP 依赖。

### 2.7 拆分顺序

采用以下顺序：

1. 在当前 CoursePilot 仓库中建立明确的 RAG 服务边界；
2. 上层业务代码只依赖抽象接口；
3. 保留本地适配器，确保现有功能可运行；
4. 建立独立 CourseRAG API 与客户端；
5. 完成两套测试和评测；
6. 最后物理拆分为两个仓库。

---

## 3. 拆分动机

### 3.1 当前问题

当前 CoursePilot 同时承担文件解析、文本切分、知识点抽取、向量索引、检索、教案生成、试题生成、PPT 生成、校验修复、导出和审核写回。

这种结构虽然适合快速完成 Demo，但不利于形成清晰的技术深度和可信的评测边界，主要问题包括：

1. RAG 改造容易影响上层 Agent；
2. Agent 节点直接依赖底层向量库实现；
3. 无法独立比较不同 Parser、Chunker 和 Retriever；
4. 端到端指标无法区分 RAG 问题和生成问题；
5. 两类能力在简历中容易被描述为功能堆叠；
6. 后续拆仓时可能出现数据模型、接口和任务状态的大规模重写。

### 3.2 拆分后的价值

拆分后形成两个相互关联、又可独立演示的项目。

#### CourseRAG

可独立回答：

- 如何解析中文课程长文档；
- 如何保留章节、页码、表格和知识图谱结构；
- 如何进行混合检索和重排序；
- 如何提供可核验引用；
- 如何设计人工标注数据集；
- 每项改造对 Recall、MRR 和延迟有什么影响。

#### CoursePilot

可独立回答：

- 为什么采用 LangGraph；
- 如何设计多阶段生成工作流；
- 如何做结构化输出和分层校验；
- 如何进行定向修复；
- 如何并行生成试题；
- 如何实现人工确认、中断恢复和幂等；
- 如何通过 LangSmith 定位节点性能和错误；
- 如何将结果导出为可编辑文档。

---

## 4. 项目定位与边界

### 4.1 CourseRAG 定位

CourseRAG 是面向中文课程资料的知识库构建、检索与引用问答服务。

#### 负责范围

- 文件上传和解析；
- 文档结构识别；
- 文档中间表示；
- 噪声识别；
- 层级切分；
- PDF / DOCX 表格及结构化内容解析；
- 文档版本和增量构建；
- Embedding；
- 稀疏检索；
- 稠密检索；
- 混合召回；
- Reranker；
- 查询改写与路由；
- Context Packing；
- 引用证据定位；
- 无答案判断；
- RAG 数据集管理；
- 检索、QA 与引用评测；
- 检索服务 API；
- 基础引用问答 API；
- QA 拒答与 Claim-Evidence 映射。

#### 不负责范围

- 教案业务规则；
- 试卷题型和分值规划；
- PPT 业务结构；
- 教学模板管理；
- 教师审核流程；
- Word、PPT、试卷文件导出；
- Agent 节点级恢复；
- CoursePilot 任务状态管理。

### 4.2 CoursePilot 定位

CoursePilot 是调用 CourseRAG 的教师备课 Agent 系统。

#### 负责范围

- 课程与用户业务管理；
- 教案生成工作流；
- 试卷生成工作流；
- PPT 初稿生成工作流；
- 教学模板系统；
- 任务计划与 Blueprint；
- Prompt 组织；
- 模型路由；
- LangGraph 状态；
- 结构化生成；
- 分层校验；
- 定向修复；
- 人工确认；
- Checkpoint 和恢复；
- 幂等控制；
- 文档导出；
- 审核与批准写回；
- LangSmith Trace；
- Agent 与系统级评测。

#### 不负责范围

- 直接操作 Chroma、BM25 或其他索引；
- 直接实例化底层 Embedding；
- 自行切分文件；
- 自行维护检索算法；
- 直接读取 CourseRAG 内部数据库表；
- 在工作流节点中依赖具体向量库 SDK。

---

## 5. 总体系统架构

```text
CoursePilot UI
    ↓
CoursePilot API
    ↓
CoursePilot Agent Runtime
    ↓ RetrievalServicePort
CourseRAG Client Layer
    ↓
CourseRAG API
    ↓
CourseRAG Core
```

### 5.1 可观测性架构

CoursePilot LangGraph 将节点输入输出、Prompt 与模型响应、检索请求与返回结果、校验问题及修复结果上传至 LangSmith Cloud。

CoursePilot 与 CourseRAG 的业务实体、任务状态、文档版本、索引版本、审核记录和评测运行记录保存在 PostgreSQL。

CourseRAG 内部检索阶段也应生成可观测事件，但 CourseRAG 不必强依赖 LangSmith。第一版优先保证 CoursePilot 的完整 Trace。

---

## 6. 核心接口设计

### 6.1 接口划分原则

原 `RetrievalServicePort` 同时包含检索、证据读取和审核写回，职责过宽，并且缺少文档上传、知识库构建和任务状态查询能力。

逻辑拆分后，CoursePilot 应依赖一个统一的 `CourseRAGServicePort` 门面；门面内部按职责拆为六类子接口：

1. `KnowledgeBasePort`：文档、构建任务和索引版本；
2. `RetrievalPort`：检索与上下文组装；
3. `QuestionAnsweringPort`：基础引用问答与拒答；
4. `EvidencePort`：证据读取与批量核验；
5. `VerifiedContentPort`：教师审核内容写回与撤销；
6. `ServiceInfoPort`：健康检查、能力发现与版本信息。

CoursePilot 的 LangGraph 业务节点主要使用 `RetrievalPort`、`QuestionAnsweringPort` 和 `EvidencePort`；资料管理页面通过应用服务使用 `KnowledgeBasePort`；审核节点使用 `VerifiedContentPort`。

### 6.2 CoursePilot 侧抽象接口

```python
from typing import Protocol


class KnowledgeBasePort(Protocol):
    def register_document(
        self,
        request: "RegisterDocumentRequest",
    ) -> "RegisterDocumentResponse":
        ...

    def start_build(
        self,
        request: "StartBuildRequest",
    ) -> "BuildJob":
        ...

    def get_build_job(
        self,
        job_id: str,
        request_context: "RequestContext",
    ) -> "BuildJob":
        ...

    def list_documents(
        self,
        request: "ListDocumentsRequest",
    ) -> "DocumentPage":
        ...

    def delete_document(
        self,
        request: "DeleteDocumentRequest",
    ) -> "DeleteDocumentResult":
        ...


class RetrievalPort(Protocol):
    def search(
        self,
        request: "SearchRequest",
    ) -> "SearchResponse":
        ...

    def build_context(
        self,
        request: "ContextRequest",
    ) -> "ContextPackage":
        ...


class QuestionAnsweringPort(Protocol):
    def answer(
        self,
        request: "QARequest",
    ) -> "QAResponse":
        ...


class EvidencePort(Protocol):
    def get_evidence(
        self,
        request: "GetEvidenceRequest",
    ) -> "EvidenceRecord":
        ...

    def batch_get_evidence(
        self,
        request: "BatchGetEvidenceRequest",
    ) -> "EvidenceBatch":
        ...


class VerifiedContentPort(Protocol):
    def write_verified_content(
        self,
        request: "VerifiedContentWriteRequest",
    ) -> "VerifiedContentWriteResult":
        ...

    def revoke_verified_content(
        self,
        request: "RevokeVerifiedContentRequest",
    ) -> "RevokeVerifiedContentResult":
        ...


class ServiceInfoPort(Protocol):
    def health(self) -> "HealthResponse":
        ...

    def capabilities(self) -> "CapabilitiesResponse":
        ...


class CourseRAGServicePort(
    KnowledgeBasePort,
    RetrievalPort,
    QuestionAnsweringPort,
    EvidencePort,
    VerifiedContentPort,
    ServiceInfoPort,
    Protocol,
):
    pass
```

该门面提供三种实现：

1. `LocalCourseRAGAdapter`
2. `RemoteCourseRAGClient`
3. `MockCourseRAGService`

`LocalCourseRAGAdapter` 用于逻辑拆分阶段；`RemoteCourseRAGClient` 用于物理拆仓后；`MockCourseRAGService` 用于 Agent 单元测试、工作流测试、固定检索结果测试和故障注入。

### 6.3 通用合同

所有请求和响应应复用统一元数据，避免每个接口自行定义追踪、版本和幂等字段。

#### RequestContext

```json
{
  "request_id": "req_01",
  "trace_id": "trace_01",
  "caller": "coursepilot",
  "api_version": "v1",
  "idempotency_key": "task_001:writeback:question_003",
  "deadline_ms": 5000
}
```

规则：

- `request_id`：每次调用唯一；
- `trace_id`：贯穿 CoursePilot、CourseRAG 和 LangSmith；
- `idempotency_key`：仅在具有副作用的接口中强制要求；
- `deadline_ms`：由调用方给出最大等待时间；
- 重试不得生成新的幂等键。

#### ResponseMeta

```json
{
  "request_id": "req_01",
  "trace_id": "trace_01",
  "api_version": "v1",
  "service_version": "0.2.0",
  "duration_ms": 142,
  "warnings": []
}
```

#### ErrorResponse

```json
{
  "meta": {
    "request_id": "req_01",
    "trace_id": "trace_01",
    "api_version": "v1"
  },
  "error": {
    "code": "INDEX_NOT_READY",
    "message": "The requested course index is not ready.",
    "retryable": true,
    "retry_after_ms": 3000,
    "details": {
      "course_id": "course_001",
      "index_status": "building"
    }
  }
}
```

错误码至少分为：

- 参数与合同错误；
- 文档或资源不存在；
- 权限错误；
- 索引未就绪；
- 上游模型限流；
- 超时；
- 数据版本冲突；
- 幂等冲突；
- 内部不可重试错误。

### 6.4 文档与知识库构建合同

#### RegisterDocumentRequest

大文件不直接嵌入 JSON。逻辑拆分阶段可以传本地路径；物理拆仓后优先传对象存储 URI 或预签名上传结果。

```json
{
  "context": {},
  "course_id": "course_001",
  "file": {
    "object_uri": "s3://coursepilot/course_001/doc_001.pdf",
    "filename": "人工智能导论.pdf",
    "mime_type": "application/pdf",
    "size_bytes": 12582912,
    "sha256": "..."
  },
  "document_type": "textbook",
  "metadata": {
    "title": "人工智能导论",
    "language": "zh-CN"
  }
}
```

#### RegisterDocumentResponse

```json
{
  "meta": {},
  "document": {
    "document_id": "doc_001",
    "document_version": "v1",
    "status": "registered",
    "content_hash": "..."
  }
}
```

#### StartBuildRequest

```json
{
  "context": {},
  "course_id": "course_001",
  "document_ids": ["doc_001"],
  "build_mode": "incremental",
  "parser_profile": "course_pdf_v2",
  "chunking_profile": "hierarchical_v1",
  "retrieval_profile": "hybrid_rrf_v1",
  "force_rebuild": false
}
```

#### BuildJob

```json
{
  "meta": {},
  "job_id": "build_001",
  "course_id": "course_001",
  "status": "running",
  "stage": "embedding",
  "progress": {
    "completed_units": 212,
    "total_units": 391,
    "percent": 54.2
  },
  "document_versions": {
    "doc_001": "v1"
  },
  "target_index_version": "idx_20260721_001",
  "error": null,
  "created_at": "2026-07-21T10:00:00Z",
  "updated_at": "2026-07-21T10:04:31Z"
}
```

`status` 至少包含：

- `queued`
- `running`
- `succeeded`
- `failed`
- `cancelled`

`stage` 至少包含：

- `parsing`
- `normalizing`
- `chunking`
- `extracting_metadata`
- `embedding`
- `building_sparse_index`
- `validating`
- `publishing`

### 6.5 检索合同

#### SearchRequest

```json
{
  "context": {},
  "course_id": "course_001",
  "query": "启发式搜索的定义与特点",
  "filters": {
    "document_ids": [],
    "document_types": ["textbook"],
    "section_paths": [],
    "page_range": null,
    "source_tiers": ["primary_source", "teacher_verified"]
  },
  "retrieval": {
    "mode": "hybrid",
    "candidate_k": 30,
    "rerank_top_n": 8,
    "return_top_n": 5,
    "enable_query_rewrite": false,
    "enable_parent_expansion": true
  }
}
```

#### SearchHit

```json
{
  "rank": 1,
  "chunk_id": "chunk_001",
  "parent_chunk_id": "parent_003",
  "document_id": "doc_001",
  "document_version": "v3",
  "section_path": ["第3章", "3.4 启发式搜索"],
  "page_start": 67,
  "page_end": 68,
  "text": "……",
  "scores": {
    "dense": 0.78,
    "sparse": 11.42,
    "fusion": 0.032,
    "rerank": 0.91
  },
  "evidence_ids": ["evidence_001"],
  "source_tier": "primary_source"
}
```

#### SearchResponse

```json
{
  "meta": {},
  "query": {
    "original": "启发式搜索的定义与特点",
    "normalized": "启发式搜索 定义 特点",
    "rewrites": []
  },
  "hits": [],
  "retrieval": {
    "retrieval_config_version": "hybrid_rrf_v1",
    "index_version": "idx_20260721_001",
    "candidate_count": 30,
    "returned_count": 5
  }
}
```

### 6.6 上下文组装合同

`search` 返回候选证据；`build_context` 负责去重、父块扩展和 Token Budget Packing。二者不得合并为一个不可观察的黑盒接口。

#### ContextRequest

```json
{
  "context": {},
  "course_id": "course_001",
  "query": "启发式搜索的定义与特点",
  "purpose": "lesson_generation",
  "search_request": {},
  "packing": {
    "max_tokens": 4000,
    "max_items": 8,
    "deduplicate": true,
    "include_neighbor_sections": true,
    "preserve_evidence_boundaries": true
  }
}
```

#### ContextItem

```json
{
  "context_item_id": "ctx_001",
  "text": "……",
  "document_id": "doc_001",
  "section_path": ["第3章", "3.4 启发式搜索"],
  "page_start": 67,
  "page_end": 68,
  "evidence_ids": ["evidence_001"],
  "token_count": 486,
  "truncated": false
}
```

#### ContextPackage

```json
{
  "meta": {},
  "query": "启发式搜索的定义与特点",
  "purpose": "lesson_generation",
  "items": [],
  "token_count": 3150,
  "evidence_map": {
    "evidence_001": {
      "document_id": "doc_001",
      "page_start": 67,
      "page_end": 68
    }
  },
  "retrieval_trace_id": "retrieval_trace_001",
  "index_version": "idx_20260721_001",
  "packing_report": {
    "candidate_count": 30,
    "selected_count": 6,
    "deduplicated_count": 4,
    "discarded_for_budget": 2
  }
}
```


### 6.7 基础引用问答合同

QA 接口复用 Query Processing、Retrieval 和 Context Packing，不建立另一套独立检索链路。

#### QARequest

```json
{
  "context": {},
  "course_id": "course_001",
  "question": "启发式搜索与无信息搜索有什么区别？",
  "filters": {},
  "retrieval": {
    "mode": "hybrid",
    "candidate_k": 30,
    "rerank_top_n": 8,
    "return_top_n": 5
  },
  "answering": {
    "max_answer_tokens": 600,
    "require_citations": true,
    "allow_abstention": true,
    "citation_style": "evidence_id"
  }
}
```

#### QAResponse

```json
{
  "meta": {},
  "question": "启发式搜索与无信息搜索有什么区别？",
  "answer_status": "answered",
  "answer": "启发式搜索利用问题相关信息指导搜索，而无信息搜索仅利用问题定义本身提供的信息。",
  "claims": [
    {
      "claim_id": "claim_001",
      "text": "启发式搜索利用问题相关信息指导搜索。",
      "evidence_ids": ["evidence_001"]
    }
  ],
  "citations": [
    {
      "evidence_id": "evidence_001",
      "document_id": "doc_001",
      "page_start": 67,
      "page_end": 67
    }
  ],
  "context_package_id": "ctx_pkg_001",
  "retrieval_trace_id": "retrieval_trace_001",
  "model": {
    "provider": "env_api",
    "model": "configured_generation_model",
    "prompt_version": "qa_prompt_v1"
  }
}
```

`answer_status` 至少包含：

- `answered`
- `abstained_insufficient_evidence`
- `abstained_out_of_scope`
- `failed`

QA 必须满足：

- 回答仅使用返回 Context；
- 每个事实性 Claim 至少关联一个 Evidence；
- 证据不足时允许拒答；
- QA 失败不能影响基础 Search API 可用性；
- QA 响应必须返回检索、Context、Prompt 和模型版本。

### 6.8 证据合同

#### GetEvidenceRequest

```json
{
  "context": {},
  "course_id": "course_001",
  "evidence_id": "evidence_001"
}
```

#### EvidenceRecord

```json
{
  "meta": {},
  "evidence_id": "evidence_001",
  "document_id": "doc_001",
  "document_version": "v3",
  "section_path": ["第3章", "3.4 启发式搜索"],
  "page_start": 67,
  "page_end": 68,
  "block_ids": ["block_451", "block_452"],
  "char_start": 128,
  "char_end": 436,
  "evidence_text": "……",
  "source_tier": "primary_source",
  "content_hash": "..."
}
```

证据标识必须绑定文档版本和稳定原文范围。Chunker 改版可以改变 `chunk_id`，但不应让已批准内容的证据引用失效。

### 6.9 审核写回合同

#### VerifiedContentWriteRequest

```json
{
  "context": {
    "idempotency_key": "task_001:writeback:question_003"
  },
  "course_id": "course_001",
  "content_type": "verified_question",
  "content": {},
  "evidence_ids": ["evidence_001"],
  "source_tier": "teacher_verified",
  "approved_by": "user_001",
  "task_id": "task_001",
  "approval_record_id": "approval_001"
}
```

#### VerifiedContentWriteResult

```json
{
  "meta": {},
  "verified_content_id": "verified_001",
  "version": "v1",
  "status": "indexed",
  "index_version": "idx_20260721_002",
  "created": true
}
```

同一个幂等键重复调用时，返回已有结果，不能重复创建内容或重复写入索引。

#### RevokeVerifiedContentRequest

```json
{
  "context": {
    "idempotency_key": "verified_001:revoke"
  },
  "course_id": "course_001",
  "verified_content_id": "verified_001",
  "revoked_by": "user_001",
  "reason": "答案经教师复核后存在错误"
}
```

### 6.10 服务信息合同

#### HealthResponse

只反映服务进程和关键依赖是否可用，不返回完整业务能力。

```json
{
  "status": "healthy",
  "dependencies": {
    "postgres": "healthy",
    "vector_store": "healthy",
    "object_store": "healthy",
    "message_broker": "healthy"
  }
}
```

#### CapabilitiesResponse

用于让 CoursePilot 在运行时确认 CourseRAG 是否支持某项功能。

```json
{
  "api_version": "v1",
  "service_version": "0.2.0",
  "supported_document_types": ["pdf", "docx"],
  "supported_retrieval_modes": ["dense", "sparse", "hybrid"],
  "supports_rerank": true,
  "supports_query_rewrite": true,
  "supports_streaming_progress": true,
  "supports_verified_writeback": true
}
```

### 6.11 合同设计约束

- CoursePilot 不依赖 CourseRAG 内部 ORM、数据库主键或向量库对象；
- 所有时间统一为 UTC ISO 8601；
- 所有枚举字段必须显式定义；
- 所有有副作用的写操作必须支持幂等；
- 所有响应必须返回 `request_id` 和 `trace_id`；
- 所有检索结果必须返回索引版本和检索配置版本；
- 大文件通过对象 URI 传递，不通过进程间 JSON 复制；
- `search`、`build_context` 和 `get_evidence` 必须能独立观测和测试；
- API Schema 与本地 Adapter 使用同一组领域 DTO；
- Remote Client 与 Local Adapter 必须通过相同 Contract Test。

---

## 7. 数据所有权

### 7.1 CourseRAG 所有数据

- 原始文件；
- 解析结果；
- 文档中间表示；
- Section、Block、Table、Figure 元数据；
- Chunk；
- Evidence Span；
- 稀疏索引；
- 向量索引；
- 文档版本；
- 索引版本；
- 构建任务；
- RAG Gold Dataset；
- QA Run、Answer Claims 与 Claim-Evidence 映射；
- 检索、QA 与引用评测结果。

### 7.2 CoursePilot 所有数据

- 用户；
- 课程业务实体；
- 教学任务；
- 模板；
- Blueprint；
- 工作流状态；
- 教案；
- 试卷；
- PPT 初稿；
- Validator Issue；
- Repair Record；
- 审核结果；
- 导出文件；
- Agent 评测结果。

### 7.3 共享标识

- `course_id`
- `document_id`
- `document_version`
- `evidence_id`
- `task_id`
- `trace_id`

禁止 CoursePilot 将 CourseRAG 内部数据库主键作为业务依赖。

---

## 8. 审核写回与知识可信度

为防止生成内容未经审核进入知识库并在后续检索中自我强化，CourseRAG 使用来源分层：

| Source Tier | 含义 | 默认检索权重 |
|---|---|---|
| `primary_source` | 教材、课程大纲、教师上传的原始资料 | 最高 |
| `teacher_verified` | 教师确认并按白名单写回的题目、答案解析、教案片段 | 次高 |
| `external_reference` | 明确标注来源的外部材料 | 按配置 |
| `generated_draft` | 未审核的模型生成内容 | 默认不入库 |

CoursePilot 只有在用户点击批准后，才能调用 `write_verified_content`。

写回动作必须带审批人、原任务 ID、来源类型，并满足可追溯、可撤销和幂等要求。

---

## 9. 逻辑拆分阶段

### 9.1 建议目录

```text
agent_coursepilot/
├── apps/
│   ├── coursepilot_api/
│   └── coursepilot_ui/
├── coursepilot/
│   ├── agents/
│   ├── workflows/
│   ├── validators/
│   ├── repair/
│   ├── templates/
│   ├── exports/
│   └── ports/
│       └── retrieval.py
├── courserag/
│   ├── api/
│   ├── application/
│   ├── domain/
│   ├── parsers/
│   ├── chunking/
│   ├── indexing/
│   ├── retrieval/
│   ├── citations/
│   └── evaluation/
├── adapters/
│   ├── local_courserag.py
│   └── remote_courserag.py
├── tests/
│   ├── coursepilot/
│   ├── courserag/
│   └── contract/
└── docs/
```

### 9.2 逻辑拆分任务

1. 建立 `RetrievalServicePort`；
2. 将现有知识库功能迁移至 `courserag` 包；
3. 实现 `LocalCourseRAGAdapter`；
4. 替换 LangGraph 节点中的直接 Retriever 调用；
5. 建立请求和响应 Pydantic Schema；
6. 建立 CoursePilot 与 CourseRAG Contract Test；
7. 为 Agent 测试实现 Mock Client；
8. 保持原有产品接口兼容；
9. 建立独立的 RAG 评测入口；
10. 建立独立的 Agent 评测入口。

### 9.3 逻辑拆分验收

- CoursePilot 代码中不存在 Chroma、BM25、Embedding Provider 的直接导入；
- CoursePilot 的工作流可使用 MockRetrievalService 运行；
- CourseRAG 可单独执行上传、构建和搜索；
- 现有教案、试卷、PPT 流程可以通过 Local Adapter 正常运行；
- Contract Test 覆盖关键接口字段；
- 两套测试可分别运行。

---

## 10. 物理拆仓阶段

### 10.1 目标仓库

#### `course-rag`

包含 CourseRAG Core、API、构建 Worker、检索与 QA、数据集、评测脚本、Docker 配置和独立 README。

#### `course-pilot`

包含 CoursePilot API、LangGraph Agent、UI、模板、Validator、Repair、Export、LangSmith、Agent 评测和 CourseRAG Client。

### 10.2 可选通信方式

物理拆仓只表示代码仓库和部署边界分离，并不限定只能使用 HTTP。可选方案包括：

| 方式 | 适合场景 | 主要优势 | 主要代价 | 本项目结论 |
|---|---|---|---|---|
| REST/HTTP + JSON | 检索、证据读取、写回、文档和任务管理 | 简单、可调试、OpenAPI 友好 | JSON 开销、强类型约束相对较弱 | 主接口 |
| gRPC + Protobuf | 高频内部调用、严格类型、多语言、流式返回 | 契约强、序列化紧凑、支持流式 RPC | 工具链和调试复杂度更高 | 暂不作为主接口 |
| 消息队列 / Task Queue | 文档解析、Embedding、索引构建等长任务 | 解耦、削峰、重试、失败隔离 | 最终一致性和任务状态更复杂 | 构建任务推荐 |
| Event Streaming | 多消费者事件、审计、回放和数据管道 | 事件可持久化与重放 | 对当前规模明显过重 | 不采用 Kafka |
| SSE | 构建进度、生成进度和日志单向推送 | 浏览器支持好、实现简单 | 仅服务端到客户端 | 推荐作为进度通道 |
| WebSocket | 高频双向交互和实时控制 | 全双工 | 连接管理和恢复更复杂 | 当前不需要 |
| MCP | 向通用 Agent 暴露检索工具和课程资源 | Agent 生态互操作性好 | 不适合作为全部领域管理接口 | 后续扩展接口 |
| 本地 SDK / Python Package | 单进程 Demo、测试、离线评测 | 无网络开销、开发简单 | 运行时耦合、不能独立扩缩容 | 保留 Local Adapter |
| 共享数据库 | 临时快速集成 | 表面实现简单 | 强耦合、绕过领域规则、难以演进 | 禁止 |
| 对象存储 / 共享文件存储 | 原始文件、解析产物和大对象传递 | 避免大文件穿过 RPC | 需要权限和生命周期管理 | 作为数据通道 |

### 10.3 推荐的混合通信架构

本项目不应在 REST、消息队列、SSE 和对象存储之间四选一，而应按交互性质组合使用：

```text
同步控制与查询：
CoursePilot ── REST/JSON ──► CourseRAG API
  - 搜索
  - Context 组装
  - 证据读取
  - 文档元数据
  - 审核写回
  - 任务状态查询

异步任务：
CourseRAG API ── Task Queue ──► CourseRAG Worker
  - PDF 解析
  - 结构识别
  - Chunk 构建
  - Embedding
  - 稀疏索引
  - 索引校验与发布

大文件数据：
CoursePilot / Browser ── Object Storage ──► CourseRAG
  - 原始教材
  - 大型解析产物
  - 可选评测数据文件

进度通知：
CourseRAG / CoursePilot ── SSE ──► UI
  - 构建阶段
  - 完成比例
  - 错误信息
```

### 10.4 分阶段实现建议

#### 逻辑拆分阶段

- `LocalCourseRAGAdapter`
- 同一组 Pydantic DTO
- 无网络调用
- Contract Test

#### 物理拆仓 MVP

- REST/HTTP + JSON；
- FastAPI + OpenAPI；
- 文档构建返回 `job_id`；
- 客户端轮询构建状态；
- 文件使用共享卷或对象 URI；
- 统一超时、重试、错误码和 Trace ID。

#### 工程化增强

- Redis/Celery、RabbitMQ 或同类任务队列承载构建任务；
- SSE 推送任务进度；
- 对象存储预签名上传；
- Outbox 或等效机制保证业务状态与任务事件的一致性。

#### 可选作品集增强

- 额外提供 CourseRAG MCP Server；
- 暴露 `search_course`、`build_context` 和 `get_evidence` 工具；
- MCP 只作为第三方 Agent 接入层，不替代 REST 领域 API。

### 10.5 为什么当前不选择 gRPC 作为主接口

gRPC 适合大量高频内部 RPC、严格 IDL、多语言客户端或双向流式通信。本项目的核心调用规模较小，CoursePilot 与 CourseRAG 都以 Python/FastAPI 为主，而且需要方便展示、调试和通过浏览器查看 OpenAPI。

因此当前使用 gRPC 会增加 Proto、代码生成、网关和调试成本，但难以形成足够可量化的收益。后续只有在压测证明 REST 序列化或连接开销成为显著瓶颈时，才考虑将高频检索接口迁移到 gRPC。

### 10.6 为什么不使用消息队列处理同步检索

检索和 Context 组装位于 LangGraph 的在线关键路径中，需要立即获得响应并受到明确 Deadline 约束。将其改为“发消息—等待结果”的 RPC-over-Queue 会增加关联 ID、临时回复队列、超时清理和重复消费处理。

因此：

- 在线检索：同步 REST；
- 离线构建：异步队列；
- 进度通知：SSE；
- 大文件：对象存储。

### 10.7 版本兼容

CourseRAG API 使用显式版本 `/api/v1/...`，响应中包含：

- `api_version`
- `service_version`
- `document_version`
- `index_version`
- `retrieval_config_version`

CoursePilot 不依赖未声明字段。新增可选字段应保持向后兼容；删除或改变字段语义必须升级主版本。

### 10.8 客户端可靠性要求

`RemoteCourseRAGClient` 必须统一实现：

- 连接超时和读取超时；
- Deadline 传递；
- 仅对可重试错误进行有限重试；
- 指数退避与随机抖动；
- 熔断或快速失败；
- 请求 ID、Trace ID 和 LangSmith Trace 关联；
- 写操作幂等键；
- 响应 Schema 校验；
- API 版本检查；
- 结构化错误映射。

---

## 11. 部署拓扑

### 11.1 本地开发

```text
docker compose
├── coursepilot-api
├── coursepilot-ui
├── courserag-api
├── courserag-worker
├── postgres
├── redis-or-rabbitmq
├── object-storage-or-shared-volume
└── vector-store
```

第一版可以复用 Redis 同时承担缓存、任务队列和状态协调用途，但业务数据、Checkpoint 和索引版本仍应保存在各自的持久化存储中。

### 11.2 简化演示

提供两种 Profile：

- **Full Profile：** CoursePilot 与 CourseRAG 独立服务运行，使用 REST、异步 Worker 和独立存储；
- **Demo Profile：** CoursePilot 通过 `LocalCourseRAGAdapter` 调用 CourseRAG Core。

两个 Profile 必须使用相同领域 DTO、接口语义和 Contract Test，不维护两套业务逻辑。

### 11.3 数据流与控制流分离

- 控制流：REST 请求、任务状态、错误和版本信息；
- 数据流：原始文件、解析产物和其他大对象；
- 任务流：构建任务及重试；
- 观测流：日志、指标、Trace 和进度事件。

不得通过共享数据库代替正式服务接口，也不得把大文件内容长期放入消息队列。

---

## 12. 评测边界

### 12.1 CourseRAG 独立评测

输入为固定版本课程资料、人工审核 Query、Gold Answer 和 Gold Evidence Span。

输出包括：

- Recall@K；
- Hit@K；
- MRR；
- nDCG；
- Precision@K；
- 引用命中；
- QA 答案与 Claim 指标；
- 拒答指标；
- Claim-Evidence 引用指标；
- 构建耗时；
- 检索延迟；
- 模型调用次数；
- 成本；
- 消融实验结果。

### 12.2 CoursePilot 独立评测

CoursePilot 可使用固定 CourseRAG 响应、Mock Retrieval、真实 CourseRAG 或故障注入响应。

输出包括：

- Schema 通过率；
- 初次校验通过率；
- 最终通过率；
- 分类修复成功率；
- 无回归率；
- 导出成功率；
- 并行执行收益；
- Checkpoint 恢复成功率；
- 副作用重复率；
- 人工 Checklist 通过率。

### 12.3 端到端评测

端到端评测只用于展示完整系统表现，不替代两个子系统的独立评测。

必须能够区分解析错误、检索错误、Context Packing 错误、生成错误、校验漏检、修复失败和导出错误。

---

## 13. LangSmith 设计边界

每个 CoursePilot 任务至少记录：

- `task_id`
- `course_id`
- `thread_id`
- `workflow_type`
- `template_id`
- `template_version`
- `prompt_version`
- `model_provider`
- `model_name`
- 节点输入输出；
- 检索结果；
- Token 与延迟；
- Validator Issues；
- Repair Rounds；
- 导出结果。

LangSmith 不作为业务数据库、唯一任务状态源、文件存储、审批记录源或 Checkpoint 数据库。Trace 丢失不应导致任务无法恢复。

PostgreSQL 的任务记录保存 LangSmith Trace URL 或 Run ID。

---

## 14. 非目标

当前总体改造不追求：

- 通用企业知识库平台；
- 多租户 SaaS 完整商业化；
- 自动生成高质量教学插图；
- 自研 Embedding 或 Reranker 模型；
- 大规模分布式检索；
- 百万级文档吞吐；
- 完整 LMS；
- 全自动替代教师审核；
- 未经人工确认的生成内容自动写回知识库。

---

## 15. 风险与控制

### 15.1 过早拆仓

**风险：** 接口尚未稳定，两个仓库频繁同步修改。  
**控制：** 先完成 Port、Adapter 和 Contract Test，再拆仓。

### 15.2 RAG 功能无限扩张

**风险：** 变成通用知识库项目，削弱 Agent 主线。  
**控制：** 限定在中文课程资料、课程知识图谱和引用问答场景。

### 15.3 评测数据集质量不足

**风险：** LLM 生成的问题和答案存在错误，指标失真。  
**控制：** 候选生成与正式 Gold 分离，所有正式样本必须人工审核。

### 15.4 LangSmith 数据泄漏

**风险：** Trace 意外包含凭据。  
**控制：** 即使允许完整上传课程原文，也必须实施 Secret 过滤和配置隔离。

### 15.5 双重数据源不一致

**风险：** PostgreSQL 与向量索引状态不一致。  
**控制：** 后续采用索引版本、Staging Index、原子切换和可重试任务。

### 15.6 未审核内容污染知识库

**风险：** 模型生成错误被后续检索反复使用。  
**控制：** 来源分层、人工批准、写回幂等和撤销机制。

---

## 16. 分阶段路线

### P0：可信基线

- 整理归属和 Attribution；
- 建立当前版本评测基线；
- 区分结构通过与内容质量；
- 建立 RetrievalServicePort；
- 建立 Local Adapter；
- 修复现有评测 Gold 泄漏；
- 增加阶段耗时记录；
- 将 PPT 统一称为可编辑初稿。

### P1：CourseRAG 核心改造

1. 文档解析；
2. 文档中间表示；
3. 层级切分；
4. 证据范围；
5. 混合检索；
6. Reranker；
7. 查询处理；
8. 增量构建；
9. 引用与拒答；
10. 消融评测。

### P2：CoursePilot Agent 工程化

- 模板系统；
- 统一 Validator Issue；
- 分层校验；
- 定向修复；
- 试题并行；
- 模型路由；
- 上下文压缩；
- LangSmith；
- PPT 模板化。

### P3：可靠性和安全

- PostgreSQL Checkpointer；
- LangGraph Interrupt；
- 稳定 Thread；
- 节点级恢复；
- 幂等；
- 故障注入；
- Prompt Injection 测试；
- 文件安全和权限控制。

### P4：物理拆仓与作品集收尾

- 拆分仓库；
- 独立 CI；
- Docker Compose 联调；
- 独立 README；
- 演示视频；
- 架构图；
- 评测报告；
- 简历指标；
- 面试问题库。

---

## 17. 总体验收标准

只有满足以下条件，项目才进入物理拆仓。

### 架构

- CoursePilot 仅依赖 RetrievalServicePort；
- Local 和 Remote Adapter 行为一致；
- Contract Test 通过；
- 数据所有权清晰。

### CourseRAG

- 可独立上传、构建、搜索和引用；
- 存在人工审核的 Gold Dataset；
- 基线和改造后的指标可重复；
- 解析、检索和引用指标分开报告；
- 支持版本化索引。

### CoursePilot

- 三条工作流可使用 Mock Retrieval 测试；
- Validator 和 Repair 可独立测试；
- LangSmith Trace 能覆盖完整任务；
- 业务状态不依赖 LangSmith；
- 导出和写回具备幂等保护。

### 工程

- 两套测试可分别执行；
- 本地部署方式清晰；
- 配置不含硬编码 Secret；
- README 能说明上游来源和个人贡献；
- 所有简历指标均有脚本、数据和报告支撑。

---

## 18. 后续文档顺序

1. `01_CoursePilot_CourseRAG_Split_and_Refactor_Plan_v1.0.md`
2. `02_CourseRAG_PRD_v1.0.md`
3. `03_CourseRAG_Evaluation_Dataset_and_Baseline_v1.0.md`
4. `04_CourseRAG_Technical_Refactor_Plan_v1.0.md`
5. `05_CoursePilot_Agent_Engineering_Upgrade_Plan_v1.0.md`
6. `06_CoursePilot_and_System_Evaluation_Plan_v1.0.md`
7. `07_Implementation_Roadmap_and_Task_Backlog_v1.0.md`

---

## 19. 当前默认结论

- API 模型优先；
- Reranker 保留本地部署能力；
- CourseRAG 优先改解析；
- LLM 只生成候选标注；
- 正式评测必须人工审核；
- 不使用 LLM-as-a-Judge；
- LangSmith 允许上传完整课程原文和 Prompt；
- LangSmith 不保存 Secret；
- PPT 为可编辑初稿；
- CoursePilot 与 CourseRAG 先逻辑解耦；
- 物理拆仓后默认通过 HTTP API 通信；
- 本地开发保留 Local Adapter；
- CoursePilot 是作品集主项目；
- CourseRAG 是可独立评测的支撑项目。
