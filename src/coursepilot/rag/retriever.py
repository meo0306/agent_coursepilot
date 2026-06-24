from coursepilot.rag.vector_store import ChromaVectorStore
from coursepilot.schemas.kb_schema import KBSearchResult


class CoursePilotRetriever:
    def __init__(self, vector_store: ChromaVectorStore | None = None):
        self.vector_store = vector_store or ChromaVectorStore()

    def search(
        self,
        *,
        course_id: str,
        query: str,
        chapter: str | None = None,
        source_type: str | None = None,
        verified_only: bool | None = None,
        top_k: int = 5,
    ) -> list[KBSearchResult]:
        docs_with_scores = self.vector_store.search(
            course_id=course_id,
            query=query,
            chapter=chapter,
            source_type=source_type,
            verified_only=verified_only,
            top_k=top_k,
        )
        results: list[KBSearchResult] = []
        for doc, score in docs_with_scores:
            metadata = doc.metadata
            results.append(
                KBSearchResult(
                    chunk_id=str(metadata.get("chunk_id", "")),
                    course_id=str(metadata.get("course_id", course_id)),
                    document_id=metadata.get("document_id"),
                    source_type=metadata.get("source_type"),
                    chapter=metadata.get("chapter"),
                    section=metadata.get("section"),
                    page=metadata.get("page"),
                    title=metadata.get("title"),
                    content=doc.page_content,
                    score=float(score),
                    verified=bool(metadata.get("verified", False)),
                )
            )
        return results

