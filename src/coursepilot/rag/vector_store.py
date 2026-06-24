import re
from pathlib import Path

from langchain_chroma import Chroma

from core.settings import settings
from coursepilot.rag.embeddings import HashingEmbeddings
from coursepilot.rag.types import Chunk


def collection_name_for_course(course_id: str) -> str:
    safe_id = re.sub(r"[^A-Za-z0-9_-]", "_", course_id)
    return f"coursepilot_{safe_id}"[:63]


class ChromaVectorStore:
    def __init__(self, persist_directory: str | None = None):
        self.persist_directory = persist_directory or settings.COURSEPILOT_CHROMA_DIR
        Path(self.persist_directory).mkdir(parents=True, exist_ok=True)
        self.embeddings = HashingEmbeddings()

    def collection_for_course(self, course_id: str) -> Chroma:
        return Chroma(
            collection_name=collection_name_for_course(course_id),
            persist_directory=self.persist_directory,
            embedding_function=self.embeddings,
        )

    def add_chunks(self, chunks: list[Chunk]) -> str:
        if not chunks:
            raise ValueError("No chunks to add to Chroma")

        course_id = chunks[0].course_id
        collection_name = collection_name_for_course(course_id)
        store = self.collection_for_course(course_id)
        store.add_texts(
            texts=[chunk.content for chunk in chunks],
            ids=[chunk.id for chunk in chunks],
            metadatas=[self._metadata(chunk, collection_name) for chunk in chunks],
        )
        return collection_name

    def delete_chunks(self, course_id: str, chunk_ids: list[str]) -> None:
        if not chunk_ids:
            return
        self.collection_for_course(course_id).delete(ids=chunk_ids)

    def search(
        self,
        *,
        course_id: str,
        query: str,
        chapter: str | None = None,
        source_type: str | None = None,
        verified_only: bool | None = None,
        top_k: int = 5,
    ):
        where = self._where_filter(
            course_id=course_id,
            chapter=chapter,
            source_type=source_type,
            verified_only=verified_only,
        )
        return self.collection_for_course(course_id).similarity_search_with_relevance_scores(
            query,
            k=top_k,
            filter=where,
        )

    def _metadata(self, chunk: Chunk, collection_name: str) -> dict[str, str | int | bool]:
        metadata: dict[str, str | int | bool] = {
            "chunk_id": chunk.id,
            "course_id": chunk.course_id,
            "document_id": chunk.document_id,
            "source_type": chunk.source_type,
            "verified": chunk.verified,
            "chroma_collection": collection_name,
        }
        if chunk.chapter:
            metadata["chapter"] = chunk.chapter
        if chunk.section:
            metadata["section"] = chunk.section
        if chunk.page is not None:
            metadata["page"] = chunk.page
        if chunk.title:
            metadata["title"] = chunk.title
        return metadata

    def _where_filter(
        self,
        *,
        course_id: str,
        chapter: str | None,
        source_type: str | None,
        verified_only: bool | None,
    ) -> dict:
        filters: list[dict[str, str | bool]] = [{"course_id": course_id}]
        if chapter:
            filters.append({"chapter": chapter})
        if source_type:
            filters.append({"source_type": source_type})
        if verified_only is not None:
            filters.append({"verified": verified_only})
        if len(filters) == 1:
            return filters[0]
        return {"$and": filters}

