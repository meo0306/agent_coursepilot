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
        document = self.session.get(Document, document_id)
        if document is None:
            return None

        try:
            parser = get_parser(document.file_path)
            parsed = parser.parse(document.file_path)
            chunks = self.chunker.split(
                parsed,
                course_id=document.course_id,
                document_id=document.id,
                source_type=document.source_type,
            )
            if not chunks:
                raise ValueError("No text chunks were extracted from this document")

            old_chunk_ids = list(
                self.session.scalars(
                    select(KnowledgeChunk.chroma_doc_id).where(
                        KnowledgeChunk.document_id == document.id
                    )
                )
            )
            self.vector_store.delete_chunks(document.course_id, old_chunk_ids)
            self.session.execute(delete(KnowledgeChunk).where(KnowledgeChunk.document_id == document.id))

            collection_name = self.vector_store.add_chunks(chunks)
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

            document.parse_status = "built"
            document.error_message = None
            self.session.commit()
            return DocumentBuildResponse(
                document_id=document.id,
                course_id=document.course_id,
                parse_status=document.parse_status,
                chunk_count=len(chunks),
            )
        except (UnsupportedParserError, Exception) as exc:
            self.session.rollback()
            document = self.session.get(Document, document_id)
            if document is not None:
                document.parse_status = "failed"
                document.error_message = self._format_error(exc)
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
        return CoursePilotRetriever(self.vector_store).search(
            course_id=course_id,
            query=payload.query,
            chapter=payload.chapter,
            source_type=payload.source_type,
            verified_only=payload.verified_only,
            top_k=payload.top_k,
        )

    def _format_error(self, exc: Exception) -> str:
        if isinstance(exc, UnsupportedParserError):
            suffix = Path(str(exc)).suffix
            return str(exc) if not suffix else f"Unsupported parser for file type: {suffix}"
        return str(exc)

