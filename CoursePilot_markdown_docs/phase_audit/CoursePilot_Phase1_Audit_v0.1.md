# CoursePilot Phase 1 审核说明 v0.1

本文档用于解释 Phase 1 做了什么、为什么这样做、相关代码在哪里、每段新增代码大致承担什么职责，以及你应该如何运行命令来验收。

对照文件：
- `PLAN.md`
- `CoursePilot_markdown_docs/CoursePilot_Development_Plan_v0.2.md`
- `CoursePilot_markdown_docs/CoursePilot_PRD_v0.1.md`
- `CoursePilot_markdown_docs/CoursePilot_Technical_Architecture_v0.2.md`

参考文档：
- `CoursePilot_markdown_docs/phase_audit/CoursePilot_Phase0_Audit_v0.1.md`

## 1. Phase 1 的目标

Phase 1 的目标是“课程管理与动态知识库”。

换成新手更容易理解的话，就是先把 CoursePilot 的资料入口跑通：

1. 老师可以创建一门课程。
2. 老师可以给这门课程上传资料。
3. 系统可以记录资料元数据，例如文件名、文件类型、来源类型、解析状态。
4. 系统可以解析资料文本。
5. 系统可以把长文本切成适合 RAG 检索的小块，也就是 chunk。
6. 系统可以把 chunk 写入 Chroma 向量库。
7. 系统也会把 chunk 的摘要 metadata 写入关系数据库，方便后续管理和追踪。
8. 用户可以按课程检索知识库，且不同课程的资料不会混在一起。
9. Streamlit 页面可以完成“创建课程 -> 上传资料 -> 构建知识库 -> 检索”的基础演示。

PRD 中对应的是：
- FR-001 创建课程
- FR-002 上传课程资料
- FR-003 文档解析与 chunk 切分
- FR-004 构建私有课程知识库

技术架构中对应的是：
- FastAPI 新增 `/api/coursepilot/*`
- PostgreSQL 保存业务 metadata
- Chroma 保存向量化文本
- Parser / Chunker / Retriever 独立放在 `src/coursepilot/rag/`
- Streamlit 新增 CoursePilot 业务页面

## 2. Phase 1 任务对照

| PLAN 任务 | 目标 | 当前实现位置 | 状态 |
|---|---|---|---|
| T1-001 Course 数据模型 | 定义课程 ORM 和 Pydantic schema | `src/coursepilot/models/course.py`, `src/coursepilot/schemas/course_schema.py` | 已实现 |
| T1-002 Course API | 创建、查询、更新、删除课程 | `src/coursepilot/api/routes_courses.py`, `src/coursepilot/services/course_service.py` | 已实现 |
| T1-003 Document 模型与上传 API | 上传资料并记录 parse_status | `src/coursepilot/models/document.py`, `src/coursepilot/api/routes_documents.py`, `src/coursepilot/services/document_service.py` | 已实现 |
| T1-004 Parser 抽象与具体 Parser | 解析 PDF/DOCX/MD/TXT，当前额外支持 XLSX | `src/coursepilot/rag/parsers/` | 已实现 |
| T1-005 Chunker | 按长度、段落和标题切分文本 | `src/coursepilot/rag/chunker.py` | 已实现 |
| T1-006 Chroma VectorStore | 写入 chunk、按 course_id 过滤检索 | `src/coursepilot/rag/vector_store.py`, `src/coursepilot/rag/embeddings.py` | 已实现 |
| T1-007 KnowledgeBaseService | 串联 parse、chunk、入库、错误记录 | `src/coursepilot/services/kb_service.py` | 已实现 |
| T1-008 KB Search API | 提供课程知识库检索接口 | `src/coursepilot/api/routes_kb.py`, `src/coursepilot/rag/retriever.py` | 已实现 |
| T1-009 Streamlit 知识库页面 | 页面跑通创建、上传、构建、检索 | `src/coursepilot/ui/knowledge_base_page.py`, `src/streamlit_app.py` | 已实现 |

注意：当前仓库已经继续实现了 Phase 2 的教学设计模块，所以有些文件现在包含 Phase 2 的扩展，例如 `routes_lessons.py` 和 lesson 生成 UI。本文只审核 Phase 1 范围。

## 3. 新增了哪些文件

### 3.1 数据库模型

新增：
- `src/coursepilot/models/course.py`
- `src/coursepilot/models/document.py`
- `src/coursepilot/models/chunk.py`

动机：

CoursePilot 需要把课程、上传资料、知识库 chunk 作为长期业务数据保存。它们不能混进原 Agent Service Toolkit 的 memory/checkpointer 表，所以统一使用 `coursepilot_` 前缀：

```text
coursepilot_courses
coursepilot_documents
coursepilot_chunks
```

这对应 Phase 0 里已经搭好的 SQLAlchemy + Alembic 基础。

### 3.2 Pydantic Schema

新增：
- `src/coursepilot/schemas/course_schema.py`
- `src/coursepilot/schemas/document_schema.py`
- `src/coursepilot/schemas/kb_schema.py`

动机：

FastAPI 不应该直接把数据库对象暴露给外部。Schema 用来定义：
- 请求体应该长什么样。
- 响应体应该返回哪些字段。
- 必填字段和基础校验规则是什么。

例如课程名 `course_name` 必须至少有 1 个字符，这样空课程名会在进入业务逻辑前被 FastAPI/Pydantic 拦住。

### 3.3 API 路由

新增：
- `src/coursepilot/api/routes_courses.py`
- `src/coursepilot/api/routes_documents.py`
- `src/coursepilot/api/routes_kb.py`
- `src/coursepilot/api/router.py`

动机：

技术架构要求所有 CoursePilot 产品流程 API 都统一挂在：

```text
/api/coursepilot/*
```

所以 `router.py` 统一注册子路由：

```python
api_router = APIRouter(prefix="/api/coursepilot")
api_router.include_router(courses_router)
api_router.include_router(documents_router)
api_router.include_router(kb_router)
```

这样业务接口和原 AST 的 `/invoke`、`/stream`、`/info` 不会互相污染。

### 3.4 Service 层

新增：
- `src/coursepilot/services/course_service.py`
- `src/coursepilot/services/document_service.py`
- `src/coursepilot/services/kb_service.py`

动机：

API 路由只负责 HTTP 层，例如接收参数、抛 404/400。真正的业务逻辑放到 service：
- CourseService 负责课程 CRUD。
- DocumentService 负责保存上传文件和创建文档记录。
- KnowledgeBaseService 负责解析、切块、写 Chroma、写数据库、失败状态记录。

这样后续 Streamlit、测试、Agent graph 或其他 API 都可以复用同一套业务逻辑。

### 3.5 RAG 模块

新增：
- `src/coursepilot/rag/types.py`
- `src/coursepilot/rag/embeddings.py`
- `src/coursepilot/rag/chunker.py`
- `src/coursepilot/rag/vector_store.py`
- `src/coursepilot/rag/retriever.py`
- `src/coursepilot/rag/parsers/base.py`
- `src/coursepilot/rag/parsers/__init__.py`
- `src/coursepilot/rag/parsers/pdf_parser.py`
- `src/coursepilot/rag/parsers/docx_parser.py`
- `src/coursepilot/rag/parsers/markdown_parser.py`
- `src/coursepilot/rag/parsers/txt_parser.py`
- `src/coursepilot/rag/parsers/xlsx_parser.py`

动机：

PRD 和技术架构都强调 CoursePilot 要有动态课程知识库，而不是复用原项目里静态的 `scripts/create_chroma_db.py` 示例。这个模块把动态 RAG 拆成几层：

```text
上传文件
  -> parser 解析文本
  -> chunker 切分文本
  -> embeddings 生成向量
  -> vector_store 写入 Chroma
  -> retriever 检索结果并返回引用信息
```

当前额外支持 `xlsx`，是为了能处理示例资料里的知识图谱表格。`doc` 文件允许上传但没有 parser，构建知识库时会被标记为 `failed`，这正好覆盖失败状态记录的验收路径。

### 3.6 数据库迁移

新增：
- `alembic/versions/2026_06_21_0002-create_phase1_tables.py`

动机：

Phase 0 的 `0001_initial_coursepilot_base` 是空基线迁移。Phase 1 的 `0002_create_phase1_tables` 才真正创建课程、文档、chunk 三张业务表。

### 3.7 Streamlit 页面

新增：
- `src/coursepilot/ui/knowledge_base_page.py`

修改：
- `src/streamlit_app.py`

动机：

Development Plan 的 T1-009 要求用户能从 UI 完成知识库流程。当前 Streamlit 入口默认进入 `CoursePilot Knowledge Base`，同时保留 `Agent Chat` 作为原 AST 聊天入口。

### 3.8 测试

新增：
- `tests/coursepilot/test_course_api.py`
- `tests/coursepilot/test_document_upload.py`
- `tests/coursepilot/test_parser.py`
- `tests/coursepilot/test_chunker.py`
- `tests/coursepilot/test_retriever.py`

修改或配合：
- `tests/coursepilot/conftest.py`

动机：

Phase 1 的验收标准不是只看文件是否存在，而是要证明：
- API 能创建和维护课程。
- 上传接口能保存资料记录。
- 不支持的文件类型能给出清晰错误。
- Parser 能解析基础文件。
- Chunker 能切分长文并保留 metadata。
- 检索时不同 course_id 不混淆。

## 4. 修改了哪些已有文件

### 4.1 `src/service/service.py`

修改点：

```python
from coursepilot.api import api_router as coursepilot_router
...
app.include_router(coursepilot_router, dependencies=[Depends(verify_bearer)])
```

注释式理解：
- 第一行是把 CoursePilot 的业务路由导入 FastAPI 主服务。
- 最后一行把 `/api/coursepilot/*` 挂到同一个 `app` 上。
- `dependencies=[Depends(verify_bearer)]` 表示 CoursePilot API 也沿用原项目的鉴权逻辑。
- 原来的 `/info`、`/invoke`、`/stream` 没有被改写，所以符合“保留 AST 主框架”的原则。

### 4.2 `src/streamlit_app.py`

修改点：

```python
from coursepilot.ui.knowledge_base_page import render_knowledge_base_page
...
app_mode = st.radio(
    "App mode",
    options=["CoursePilot Knowledge Base", "Agent Chat"],
    index=0,
)
if app_mode == "CoursePilot Knowledge Base":
    render_knowledge_base_page(agent_client.base_url, agent_client._headers)
    return
```

注释式理解：
- 新增 import，把 CoursePilot 页面从主 app 中拆出去。
- sidebar 里加了模式选择。
- 默认 `index=0`，所以打开 Streamlit 先看到 CoursePilot 页面。
- 如果用户选择 `Agent Chat`，才继续走原来的聊天界面。

### 4.3 `src/coursepilot/models/__init__.py`

修改点：

```python
from coursepilot.models.chunk import KnowledgeChunk
from coursepilot.models.course import Course
from coursepilot.models.document import Document
```

注释式理解：
- Alembic 和 SQLAlchemy 需要 import models 后，表模型才会注册进 `Base.metadata`。
- 这里统一导出模型，避免迁移或测试漏掉某张表。

### 4.4 `src/coursepilot/api/router.py`

当前文件现在还包含：

```python
from coursepilot.api.routes_lessons import router as lessons_router
api_router.include_router(lessons_router)
```

这属于 Phase 2 后续扩展，不是 Phase 1 的验收重点。Phase 1 只关注 courses、documents、kb 三类路由。

## 5. 关键新增代码解读

### 5.1 Course 模型：`src/coursepilot/models/course.py`

核心代码：

```python
class Course(Base):
    __tablename__ = "coursepilot_courses"

    id = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    course_name = mapped_column(String(255), nullable=False)
    course_type = mapped_column(String(100), nullable=True)
    student_level = mapped_column(String(100), nullable=True)
    student_background = mapped_column(Text, nullable=True)
    description = mapped_column(Text, nullable=True)

    documents = relationship("Document", back_populates="course", cascade="all, delete-orphan")
    chunks = relationship("KnowledgeChunk", back_populates="course", cascade="all, delete-orphan")
```

逐行理解：
- `__tablename__` 指定数据库表名，使用 `coursepilot_` 前缀隔离业务表。
- `id` 使用 UUID 字符串作为主键，便于 API 外部传递。
- `course_name` 不允许为空，因为创建课程至少要有名称。
- `course_type`、`student_level`、`student_background`、`description` 是 PRD 里课程基本信息字段。
- `documents` 表示一门课程可以有多个上传文档。
- `chunks` 表示一门课程可以有多个知识块。
- `cascade="all, delete-orphan"` 表示删除课程时，它下面的文档和 chunk 也会被数据库关系层清理，避免孤儿数据。

### 5.2 Document 模型：`src/coursepilot/models/document.py`

核心代码：

```python
class Document(Base):
    __tablename__ = "coursepilot_documents"

    course_id = mapped_column(
        String(36),
        ForeignKey("coursepilot_courses.id", ondelete="CASCADE"),
        nullable=False,
    )
    file_name = mapped_column(String(512), nullable=False)
    file_path = mapped_column(Text, nullable=False)
    file_type = mapped_column(String(32), nullable=False)
    source_type = mapped_column(String(100), nullable=False, default="unknown")
    parse_status = mapped_column(String(32), nullable=False, default="uploaded")
    error_message = mapped_column(Text, nullable=True)
```

逐行理解：
- `course_id` 把文档绑定到课程，这是防止不同课程资料混用的第一道边界。
- `file_name` 保存用户上传时的原文件名。
- `file_path` 保存实际落盘路径。
- `file_type` 保存后缀类型，例如 `txt`、`pdf`、`docx`。
- `source_type` 表示资料来源，例如 `textbook`、`syllabus`。
- `parse_status` 表示当前处理状态，常见值是 `uploaded`、`built`、`failed`。
- `error_message` 保存构建失败原因，满足“构建失败记录错误信息”的验收标准。

### 5.3 KnowledgeChunk 模型：`src/coursepilot/models/chunk.py`

核心代码：

```python
class KnowledgeChunk(Base):
    __tablename__ = "coursepilot_chunks"

    course_id = mapped_column(ForeignKey("coursepilot_courses.id", ondelete="CASCADE"))
    document_id = mapped_column(ForeignKey("coursepilot_documents.id", ondelete="CASCADE"))
    source_type = mapped_column(String(100), nullable=False)
    chapter = mapped_column(String(255), nullable=True)
    section = mapped_column(String(255), nullable=True)
    page = mapped_column(Integer, nullable=True)
    title = mapped_column(String(512), nullable=True)
    content_preview = mapped_column(Text, nullable=False)
    knowledge_points_json = mapped_column(JSON, nullable=False, default=list)
    verified = mapped_column(Boolean, nullable=False, default=False)
    chroma_collection = mapped_column(String(255), nullable=False)
    chroma_doc_id = mapped_column(String(255), nullable=False)
```

逐行理解：
- `course_id` 和 `document_id` 同时保存，方便从 chunk 追溯到课程和原始文档。
- `chapter`、`section`、`page`、`title` 是 RAG 引用需要展示的来源信息。
- `content_preview` 保存 chunk 前 1000 字左右的预览，完整正文主要在 Chroma 里。
- `knowledge_points_json` 保存简单提取出的关键词列表。
- `verified` 给后续 Phase 4 的“教师审核后写回知识库”预留字段。
- `chroma_collection` 和 `chroma_doc_id` 用于关联 Chroma 中的实际向量记录。

### 5.4 CourseService：`src/coursepilot/services/course_service.py`

核心代码：

```python
def create_course(self, payload: CourseCreate) -> Course:
    course = Course(**payload.model_dump())
    self.session.add(course)
    self.session.commit()
    self.session.refresh(course)
    return course
```

逐行理解：
- `payload.model_dump()` 把 Pydantic 请求对象转成普通 dict。
- `Course(**...)` 创建 ORM 对象。
- `session.add()` 把对象加入数据库事务。
- `session.commit()` 提交事务，真正写入数据库。
- `session.refresh(course)` 重新读取数据库生成的字段，例如 `id`、`created_at`。
- 返回 ORM 对象给 FastAPI，FastAPI 再按 `CourseRead` schema 转成 JSON。

更新逻辑：

```python
for key, value in payload.model_dump(exclude_unset=True).items():
    setattr(course, key, value)
```

含义：
- `exclude_unset=True` 只更新用户真的传入的字段。
- 如果用户只传 `course_name`，不会把其他字段覆盖成 `None`。

### 5.5 DocumentService：`src/coursepilot/services/document_service.py`

核心代码：

```python
if self.session.get(Course, course_id) is None:
    raise ValueError(f"Course not found: {course_id}")
```

含义：
- 上传资料前先确认课程存在。
- 避免产生没有归属课程的文档。

```python
suffix = Path(file_name).suffix.lower()
if suffix not in SUPPORTED_UPLOAD_SUFFIXES:
    raise ValueError(f"Unsupported file type: {suffix or '<none>'}")
```

含义：
- 根据后缀做文件类型白名单。
- 不支持的文件会返回清晰错误，而不是后续解析时随机失败。

```python
upload_dir = Path(settings.COURSEPILOT_STORAGE_DIR) / "uploads" / course_id
upload_dir.mkdir(parents=True, exist_ok=True)
storage_name = f"{uuid4()}{suffix}"
file_path = upload_dir / storage_name
```

含义：
- 每门课程的上传文件单独放到 `storage/uploads/{course_id}`。
- 实际保存文件名使用 UUID，避免同名文件互相覆盖。

```python
with file_path.open("wb") as output:
    while chunk := file.file.read(1024 * 1024):
        output.write(chunk)
```

含义：
- 按 1MB 分块写文件。
- 这样比一次性读完整文件更稳，后续上传大文件时更容易扩展。

### 5.6 Parser：`src/coursepilot/rag/parsers/`

抽象基类：

```python
class BaseParser(ABC):
    supported_suffixes: set[str] = set()

    def supports(self, path: str | Path) -> bool:
        return Path(path).suffix.lower() in self.supported_suffixes

    @abstractmethod
    def parse(self, path: str | Path) -> ParsedDocument:
        raise NotImplementedError
```

逐行理解：
- 每个 parser 声明自己支持哪些后缀。
- `supports()` 用统一逻辑判断文件是否能处理。
- `parse()` 是抽象方法，要求具体 parser 必须实现。

Parser 选择器：

```python
PARSERS = (
    PDFParser(),
    DOCXParser(),
    MarkdownParser(),
    TXTParser(),
    XLSXParser(),
)

def get_parser(path: str | Path) -> BaseParser:
    for parser in PARSERS:
        if parser.supports(path):
            return parser
    raise UnsupportedParserError(...)
```

含义：
- 外部不用关心具体文件类型。
- 只要调用 `get_parser(path)`，系统会自动选合适的 parser。
- 如果没有 parser，抛出 `UnsupportedParserError`，后续由 `KnowledgeBaseService` 记录到 `error_message`。

### 5.7 Chunker：`src/coursepilot/rag/chunker.py`

核心流程：

```python
def split(self, parsed: ParsedDocument, *, course_id: str, document_id: str, source_type: str) -> list[Chunk]:
    chunks = []
    for section in parsed.sections:
        chunks.extend(self._split_section(...))
    return chunks
```

含义：
- Parser 输出的是 `ParsedDocument`，里面可能有多个 section。
- Chunker 遍历所有 section，把它们切成多个 `Chunk`。
- 每个 chunk 都补上 `course_id`、`document_id`、`source_type`。

长度控制：

```python
if len(buffer) + len(paragraph) + 2 > self.chunk_size and buffer:
    chunks.append(self._make_chunk(...))
    buffer = buffer[-self.overlap:] if self.overlap > 0 else ""
```

含义：
- 当当前缓冲区超过 `chunk_size` 时，就生成一个 chunk。
- `overlap` 会保留上一段末尾的一小部分，减少切分处语义断裂。
- 默认 `chunk_size=1000`，`overlap=150`，符合计划里“800-1200 字符，overlap 100-200”的范围。

关键词提取：

```python
def _extract_keywords(self, content: str) -> list[str]:
    candidates = re.findall(...)
    ...
    if len(keywords) >= 10:
        break
```

含义：
- 当前不是复杂 NLP，只是从文本里抽取前 10 个候选词。
- 目的是先让 metadata 有可展示的 `knowledge_points`，后续可以替换为更强的关键词/知识点抽取。

### 5.8 HashingEmbeddings：`src/coursepilot/rag/embeddings.py`

核心代码：

```python
class HashingEmbeddings(Embeddings):
    """Deterministic local embeddings for CoursePilot Phase 1 smoke tests and demos."""
```

含义：
- 这是一个本地、确定性的 embedding 实现。
- 它不依赖 OpenAI、Qwen 或其他在线 embedding API。
- 主要用于 Phase 1 本地烟测和演示，确保没有真实 API key 也能跑通流程。

```python
digest = hashlib.sha256(token.encode("utf-8")).digest()
index = int.from_bytes(digest[:4], "big") % self.dimensions
sign = 1.0 if digest[4] % 2 == 0 else -1.0
vector[index] += sign
```

含义：
- 把 token 哈希到固定维度向量的某个位置。
- 同一个 token 每次都会落到同一个位置，所以结果可复现。
- 它适合测试，不等价于生产级语义 embedding。

### 5.9 ChromaVectorStore：`src/coursepilot/rag/vector_store.py`

课程 collection 命名：

```python
def collection_name_for_course(course_id: str) -> str:
    safe_id = re.sub(r"[^A-Za-z0-9_-]", "_", course_id)
    return f"coursepilot_{safe_id}"[:63]
```

含义：
- 每门课程使用独立 Chroma collection。
- 非法字符会替换成 `_`。
- 截断到 63 个字符，避免 collection 名过长。

写入 chunk：

```python
store.add_texts(
    texts=[chunk.content for chunk in chunks],
    ids=[chunk.id for chunk in chunks],
    metadatas=[self._metadata(chunk, collection_name) for chunk in chunks],
)
```

含义：
- `texts` 是要检索的正文。
- `ids` 是 chunk id。
- `metadatas` 保存 course_id、document_id、source_type、chapter、page、verified 等字段。

检索过滤：

```python
filters = [{"course_id": course_id}]
if chapter:
    filters.append({"chapter": chapter})
if source_type:
    filters.append({"source_type": source_type})
if verified_only is not None:
    filters.append({"verified": verified_only})
```

含义：
- 至少永远带 `course_id` 过滤，防止课程之间互相污染。
- 可选增加 chapter、source_type、verified 条件。

### 5.10 KnowledgeBaseService：`src/coursepilot/services/kb_service.py`

这是 Phase 1 的核心编排服务。

核心流程：

```python
parser = get_parser(document.file_path)
parsed = parser.parse(document.file_path)
chunks = self.chunker.split(...)
```

含义：
- 根据文件路径自动选择 parser。
- Parser 输出统一的 ParsedDocument。
- Chunker 把 ParsedDocument 转成 chunk 列表。

重建逻辑：

```python
old_chunk_ids = list(...)
self.vector_store.delete_chunks(document.course_id, old_chunk_ids)
self.session.execute(delete(KnowledgeChunk).where(KnowledgeChunk.document_id == document.id))
```

含义：
- 如果同一个文档重复构建知识库，先删除旧 chunk。
- 同时删除 Chroma 里的旧向量和数据库里的旧 metadata。
- 避免同一文档重复入库导致检索结果重复。

写入逻辑：

```python
collection_name = self.vector_store.add_chunks(chunks)
for chunk in chunks:
    self.session.add(KnowledgeChunk(...))
document.parse_status = "built"
document.error_message = None
self.session.commit()
```

含义：
- 先写 Chroma。
- 再把每个 chunk 的 metadata 写入 PostgreSQL/SQLite。
- 成功后把文档状态改为 `built`。

失败逻辑：

```python
except (UnsupportedParserError, Exception) as exc:
    self.session.rollback()
    document.parse_status = "failed"
    document.error_message = self._format_error(exc)
    self.session.commit()
```

含义：
- 任何解析、切块、入库错误都会触发失败记录。
- `parse_status` 会变成 `failed`。
- `error_message` 会保存可读错误，满足 Phase 1 验收标准。

## 6. API 清单

### 6.1 课程 API

```text
POST   /api/coursepilot/courses
GET    /api/coursepilot/courses
GET    /api/coursepilot/courses/{course_id}
PUT    /api/coursepilot/courses/{course_id}
DELETE /api/coursepilot/courses/{course_id}
```

用途：
- 创建课程。
- 查询课程列表。
- 查询单门课程。
- 更新课程信息。
- 删除课程。

### 6.2 文档 API

```text
GET  /api/coursepilot/courses/{course_id}/documents
POST /api/coursepilot/courses/{course_id}/documents/upload
POST /api/coursepilot/documents/{document_id}/build-kb
```

用途：
- 查看某门课程的资料列表。
- 上传资料。
- 对某个文档执行解析、切块、入库。

### 6.3 知识库检索 API

```text
POST /api/coursepilot/courses/{course_id}/kb/search
```

请求示例：

```json
{
  "query": "heuristic search",
  "top_k": 5,
  "chapter": null,
  "source_type": null,
  "verified_only": null
}
```

返回字段：

```text
chunk_id
course_id
document_id
source_type
chapter
section
page
title
content
score
verified
```

这些字段对应 PRD 中“检索结果可展示引用来源”的要求。

## 7. 哪些内容不是 Phase 1

当前仓库已经继续做了 Phase 2，所以审核时要注意边界。

以下文件不是 Phase 1 的核心成果：
- `src/coursepilot/schemas/lesson_schema.py`
- `src/coursepilot/services/lesson_service.py`
- `src/coursepilot/api/routes_lessons.py`
- `src/coursepilot/validators/lesson_validator.py`
- `src/coursepilot/exporters/lesson_docx_exporter.py`
- `src/agents/coursepilot/graphs/lesson_graph.py`
- `src/agents/coursepilot/nodes/*`
- `src/agents/coursepilot/states/lesson_state.py`
- `alembic/versions/2026_06_22_0003-create_lesson_tables.py`
- `tests/coursepilot/test_lesson_api.py`
- `tests/coursepilot/test_lesson_graph.py`
- `tests/coursepilot/test_validators.py`
- `tests/coursepilot/test_exporters.py`

它们属于 Phase 2 的教学设计 Agent 和 docx 导出能力。Phase 1 的验收重点是课程、资料、知识库和检索。

## 8. 如何运行验收

### 8.1 运行 Phase 1 专项测试

在项目根目录执行：

```powershell
$env:PYTHONPATH='src'
$env:OPENAI_API_KEY='sk-test'
.\.venv\Scripts\python.exe -m pytest tests\coursepilot\test_course_api.py tests\coursepilot\test_document_upload.py tests\coursepilot\test_parser.py tests\coursepilot\test_chunker.py tests\coursepilot\test_retriever.py -q
```

我本次实际运行结果：

```text
9 passed, 8 warnings in 1.50s
```

这些 warning 来自 LangGraph/SWIG 依赖的弃用提示，不是 Phase 1 测试失败。

### 8.2 检查 Phase 1 表迁移

先启动 Postgres：

```powershell
docker compose up -d postgres
```

设置本地环境变量：

```powershell
$env:PYTHONPATH='src'
$env:OPENAI_API_KEY='sk-test'
$env:POSTGRES_USER='postgres'
$env:POSTGRES_PASSWORD='postgres'
$env:POSTGRES_HOST='localhost'
$env:POSTGRES_PORT='5432'
$env:POSTGRES_DB='agent_service'
```

执行到 Phase 1 迁移：

```powershell
.\.venv\Scripts\python.exe -m alembic upgrade 0002_create_phase1_tables
```

预期：
- 命令成功执行。
- 数据库中出现 `coursepilot_courses`、`coursepilot_documents`、`coursepilot_chunks`。
- `coursepilot_chunks` 上有索引 `ix_coursepilot_chunks_course_filters`。

如果你已经执行过 Phase 2 或更后面的迁移，也没关系；那说明数据库版本已经超过 Phase 1。

### 8.3 启动 FastAPI 服务

```powershell
$env:PYTHONPATH='src'
$env:OPENAI_API_KEY='sk-test'
.\.venv\Scripts\python.exe src\run_service.py
```

服务默认地址：

```text
http://localhost:8080
```

健康检查：

```powershell
Invoke-RestMethod http://localhost:8080/health
```

预期返回：

```text
status: ok
```
--前面直接启动容器，从此之后在终端直接运行
### 8.4 用 API 手动跑通课程和知识库流程

创建课程：

```powershell
$course = Invoke-RestMethod -Method Post -Uri http://localhost:8080/api/coursepilot/courses -ContentType 'application/json' -Body '{"course_name":"AI Demo","course_type":"theory","student_level":"undergraduate"}'

$course
```

预期：
- 返回课程 JSON。
- 里面有 `id`。
- `course_name` 是 `AI Demo`。

准备一个测试资料：

```powershell
New-Item -ItemType Directory -Force .\storage\manual_test | Out-Null
Set-Content -Path .\storage\manual_test\lesson.txt -Value 'state space search and heuristic search are core AI topics' -Encoding UTF8
```

上传资料：

```powershell
$doc = Invoke-RestMethod -Method Post -Uri "http://localhost:8080/api/coursepilot/courses/$($course.id)/documents/upload" -Form @{    source_type='textbook'    file=Get-Item .\storage\manual_test\lesson.txt  }

$doc
```

如果你的 PowerShell 不支持 `-Form` 参数，可以改用 Windows 自带的 `curl.exe`：

```powershell
curl.exe -X POST "http://localhost:8080/api/coursepilot/courses/$($course.id)/documents/upload" -F "source_type=textbook" -F "file=@storage/manual_test/lesson.txt"
```

这个命令会直接打印上传结果 JSON。把其中的 `id` 复制出来，赋值给 `$documentId`，后续构建知识库时用：

```powershell
$documentId = '5886d780-6d77-44e6-aa3a-4e2268855eab'
```

预期：
- `parse_status` 是 `uploaded`。
- `file_type` 是 `txt`。
- `course_id` 等于刚创建课程的 id。

构建知识库：

```powershell
$build = Invoke-RestMethod `
  -Method Post `
  -Uri "http://localhost:8080/api/coursepilot/documents/$($doc.id)/build-kb"

$build
```

如果你使用的是上面的 `curl.exe` 上传方式，则把构建命令改成：

```powershell
$build = Invoke-RestMethod -Method Post -Uri "http://localhost:8080/api/coursepilot/documents/$documentId/build-kb"

$build
```

预期：
- `parse_status` 是 `built`。
- `chunk_count` 大于等于 1。

检索知识库：

```powershell
$search = Invoke-RestMethod -Method Post -Uri "http://localhost:8080/api/coursepilot/courses/$($course.id)/kb/search" -ContentType 'application/json' -Body '{"query":"heuristic search","top_k":5}'

$search.results
```

预期：
- 返回至少 1 条结果。
- 每条结果的 `course_id` 都等于当前课程 id。
- 结果里包含 `chunk_id`、`score`、`content`。

### 8.5 验证不同 course_id 不混淆

再创建一门不同课程：

```powershell
$course2 = Invoke-RestMethod -Method Post -Uri http://localhost:8080/api/coursepilot/courses -ContentType 'application/json' -Body '{"course_name":"Math Demo"}'
```

如果你只给第一门课上传了 `heuristic search` 文档，那么对第二门课检索：

```powershell
$search2 = Invoke-RestMethod -Method Post -Uri "http://localhost:8080/api/coursepilot/courses/$($course2.id)/kb/search" -ContentType 'application/json' -Body '{"query":"heuristic search","top_k":5}'

$search2.results
```

预期：
- 不应该返回第一门课的 chunk。
- 这验证了 `course_id` 隔离。

### 8.6 启动 Streamlit 页面验收

保持 FastAPI 服务运行，再开一个 PowerShell：

```powershell
$env:PYTHONPATH='src'
$env:OPENAI_API_KEY='sk-test'
$env:AGENT_URL='http://localhost:8080'
.\.venv\Scripts\python.exe -m streamlit run src\streamlit_app.py
```

打开浏览器中的 Streamlit 地址，通常是：

```text
http://localhost:8501
```

验收步骤：

1. 左侧 `App mode` 选择 `CoursePilot Knowledge Base`。
2. 创建一门课程。
3. 上传一个 `txt`、`md`、`docx`、`pdf` 或 `xlsx` 文件。
4. 在文档下拉框选择刚上传的文件。
5. 点击 `Build knowledge base`。
6. 在 Search 输入关键词。
7. 点击 `Search knowledge base`。
8. 检查页面是否展示 score、chunk id、page 和 content 预览。

## 9. Phase 1 验收清单

你可以按下面清单逐项确认：

- `coursepilot_courses` 表存在。
- `coursepilot_documents` 表存在。
- `coursepilot_chunks` 表存在。
- `POST /api/coursepilot/courses` 可以创建课程。
- `GET /api/coursepilot/courses` 可以列出课程。
- `PUT /api/coursepilot/courses/{course_id}` 可以更新课程。
- `DELETE /api/coursepilot/courses/{course_id}` 可以删除课程。
- `POST /api/coursepilot/courses/{course_id}/documents/upload` 可以上传资料。
- 上传不支持的后缀会返回清晰错误。
- `POST /api/coursepilot/documents/{document_id}/build-kb` 可以构建知识库。
- 构建成功时 `parse_status` 变成 `built`。
- 构建失败时 `parse_status` 变成 `failed`，且 `error_message` 有内容。
- `POST /api/coursepilot/courses/{course_id}/kb/search` 能返回 chunk 检索结果。
- 检索结果包含 `chunk_id`、`source_type`、`chapter`、`page`、`score`、`content`。
- 不同课程的检索结果不会互相混淆。
- Streamlit 默认可以进入 CoursePilot 知识库页面。

如果这些都满足，Phase 1 就达到了“课程管理与动态知识库”的验收标准。

## 10. 当前实现的边界和后续注意点

1. 当前 embedding 是 `HashingEmbeddings`，适合本地 smoke test 和 demo，不是生产级语义 embedding。后续如果要更准确的语义检索，应替换为真实 embedding provider。
2. 当前 `.doc` 允许上传，但没有 `.doc` parser；构建时会进入 `failed` 状态。这可以用于验证失败路径，但正式使用建议上传 `.docx`。
3. 当前 parser 主要提取文本，复杂扫描版 PDF、OCR、复杂版式表格不是 Phase 1 重点。
4. 当前 chunker 的知识点提取是轻量关键词提取，不是完整知识图谱抽取。
5. 当前 Streamlit 页面已经混入 Phase 2 的教学设计入口；Phase 1 验收时只看课程、上传、构建、检索四步。
6. Chroma 数据保存在 `COURSEPILOT_CHROMA_DIR`，默认是 `./chroma_db`；上传文件保存在 `COURSEPILOT_STORAGE_DIR`，默认是 `./storage`。
