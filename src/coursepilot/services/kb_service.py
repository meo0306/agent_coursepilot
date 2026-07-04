"""
知识库服务
解析、切块、写 Chroma、写数据库、失败状态记录
"""
from pathlib import Path

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from coursepilot.models import Document, KnowledgeChunk
from coursepilot.rag.chunker import Chunker
from coursepilot.rag.parsers import UnsupportedParserError, get_parser
from coursepilot.rag.retriever import CoursePilotRetriever
from coursepilot.rag.vector_store import ChromaVectorStore
from coursepilot.schemas.document_schema import DocumentBuildResponse
from coursepilot.schemas.kb_schema import KBSearchRequest, KBSearchResult


class KnowledgeBaseService:
    def __init__(
        self,
        session: Session,
        *,
        chunker: Chunker | None = None,
        vector_store: ChromaVectorStore | None = None,
    ):
        self.session = session
        self.chunker = chunker or Chunker()
        self.vector_store = vector_store or ChromaVectorStore()

    def build_document(self, document_id: str) -> DocumentBuildResponse | None:
        """ 解析文档、切块、写 Chroma、写数据库、失败状态记录 """
        # 读取文档
        document = self.session.get(Document, document_id)
        if document is None:
            return None

        try:
            # 获取解析器
            parser = get_parser(document.file_path)
            # 获取解析后的文档
            parsed = parser.parse(document.file_path)
            # 切块
            chunks = self.chunker.split(
                parsed,
                course_id=document.course_id,
                document_id=document.id,
                source_type=document.source_type,
            )
            # 异常处理：如果没有切出任何 chunk，说明文档内容为空或无法解析，抛出异常
            if not chunks:
                raise ValueError("No text chunks were extracted from this document")
            
            # 先检查是否重复构建知识库==>重建逻辑
            # 重建某个文档的知识库前，先找出旧 chunk 在 Chroma 向量库里的 ID
            # session.scalars()：执行查询，并只取每行的第一个值；select()构造查询；.where()增加过滤条件；
            old_chunk_ids = list(
                self.session.scalars(
                    select(KnowledgeChunk.chroma_doc_id).where(
                        KnowledgeChunk.document_id == document.id
                    )
                )
            )
            # 删除旧 chunk 在 Chroma 向量库里的数据和数据库里的记录
            self.vector_store.delete_chunks(document.course_id, old_chunk_ids)
            # 删除数据库里的chunk记录
            self.session.execute(delete(KnowledgeChunk).where(KnowledgeChunk.document_id == document.id))

            # 写入 Chroma 和数据库
            # 先写Chroma 向量库
            collection_name = self.vector_store.add_chunks(chunks)
            
            # 再写PostgreSQL/SQLite数据库
            for chunk in chunks:
                self.session.add(
                    KnowledgeChunk(
                        id=chunk.id,
                        course_id=chunk.course_id,
                        document_id=chunk.document_id,
                        source_type=chunk.source_type,
                        chapter=chunk.chapter,
                        section=chunk.section,
                        page=chunk.page,
                        title=chunk.title,
                        content_preview=chunk.content[:1000],
                        knowledge_points_json=chunk.knowledge_points,
                        verified=chunk.verified,
                        chroma_collection=collection_name,
                        chroma_doc_id=chunk.id,
                    )
                )
            # 提交事务，更新文档状态为已构建
            document.parse_status = "built"
            document.error_message = None
            self.session.commit()
            
            # 返回构建结果
            return DocumentBuildResponse(
                document_id=document.id,
                course_id=document.course_id,
                parse_status=document.parse_status,
                chunk_count=len(chunks),
            )
        # 异常处理：解析器不支持的文件类型，或其他异常
        except (UnsupportedParserError, Exception) as exc:
            # 回滚事务，避免数据库状态不一致
            self.session.rollback()

            document = self.session.get(Document, document_id)
            if document is not None:
                # 记录文档状态为失败，并保存错误信息
                document.parse_status = "failed"
                document.error_message = self._format_error(exc)
                # 提交事务，保存失败状态
                self.session.commit()
                return DocumentBuildResponse(
                    document_id=document.id,
                    course_id=document.course_id,
                    parse_status=document.parse_status,
                    chunk_count=0,
                    error_message=document.error_message,
                )
            raise

    def search(self, course_id: str, payload: KBSearchRequest) -> list[KBSearchResult]:
        """ 在指定课程的知识库中搜索，返回引用信息（包含） """
        return CoursePilotRetriever(self.vector_store).search(
            course_id=course_id,
            query=payload.query,
            chapter=payload.chapter,
            source_type=payload.source_type,
            verified_only=payload.verified_only,
            top_k=payload.top_k,
        )

    def _format_error(self, exc: Exception) -> str:
        """ 格式化异常信息，返回给前端 """
        if isinstance(exc, UnsupportedParserError):
            # 解析器不支持的文件类型，返回给前端提示
            suffix = Path(str(exc)).suffix
            return str(exc) if not suffix else f"Unsupported parser for file type: {suffix}"
        return str(exc)

