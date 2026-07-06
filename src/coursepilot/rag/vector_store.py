"""
写入 ChromaVectorStore
"""
import re
from pathlib import Path

from langchain_chroma import Chroma
from langchain_core.embeddings import Embeddings

from core.settings import settings
from coursepilot.rag.embeddings import get_coursepilot_embeddings
from coursepilot.rag.types import Chunk


def collection_name_for_course(course_id: str) -> str:
    """课程 collection 命名"""
    safe_id = re.sub(r"[^A-Za-z0-9_-]", "_", course_id)
    return f"coursepilot_{safe_id}"[:63]


class ChromaVectorStore:
    def __init__(self, persist_directory: str | None = None, embeddings: Embeddings | None = None):
        """Chroma 持久化向量存储"""
        self.persist_directory = persist_directory or settings.COURSEPILOT_CHROMA_DIR   # 指定持久化目录
        Path(self.persist_directory).mkdir(parents=True, exist_ok=True)
        # 如果没有传入 embeddings，则使用 get_coursepilot_embeddings() 获取默认的 embedding 实例
        self.embeddings = embeddings or get_coursepilot_embeddings()

    def collection_for_course(self, course_id: str) -> Chroma:
        """获取课程对应的 Chroma collection"""
        return Chroma(
            collection_name=collection_name_for_course(course_id),
            persist_directory=self.persist_directory,
            embedding_function=self.embeddings,
        )

    def add_chunks(self, chunks: list[Chunk]) -> str:
        """将 chunk 列表写入 Chroma collection"""
        if not chunks:
            raise ValueError("No chunks to add to Chroma")

        course_id = chunks[0].course_id
        collection_name = collection_name_for_course(course_id)
        store = self.collection_for_course(course_id)
        # 写入 chunk
        store.add_texts(
            texts=[chunk.content for chunk in chunks],  # 检索正文
            ids=[chunk.id for chunk in chunks], # ID
            metadatas=[self._metadata(chunk, collection_name) for chunk in chunks], # 元数据
        )
        return collection_name

    def delete_chunks(self, course_id: str, chunk_ids: list[str]) -> None:
        """从 Chroma collection 删除指定 chunk"""
        if not chunk_ids:
            return
        self.collection_for_course(course_id).delete(ids=chunk_ids)

    def add_verified_texts(
        self,
        *,
        course_id: str,
        texts: list[str],
        ids: list[str],
        metadatas: list[dict[str, str | int | bool]],
    ) -> str:
        """将已审核的文本写入 Chroma collection"""
        if not texts:
            raise ValueError("No texts to add to Chroma")
        collection_name = collection_name_for_course(course_id)
        normalized_metadata = []
        for metadata in metadatas:
            normalized = {
                "course_id": course_id,
                "verified": True,
                "chroma_collection": collection_name,
                **metadata,
            }
            normalized_metadata.append({key: value for key, value in normalized.items() if value is not None})
        self.collection_for_course(course_id).add_texts(
            texts=texts,
            ids=ids,
            metadatas=normalized_metadata,
        )
        return collection_name

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
        """
        在指定课程的 Chroma collection 中执行向量相似度检索
        return: list of (Chunk, score) tuples, where score is a float between 0 and 1
        """
        # 构建过滤条件
        where = self._where_filter(
            course_id=course_id,
            chapter=chapter,
            source_type=source_type,
            verified_only=verified_only,
        )
        # 获取课程对应的 Chroma collection
        store = self.collection_for_course(course_id)
        # 如果 collection 为空，则直接返回空列表，说明没有任何 chunk 可供检索
        if store._collection.count() == 0:
            return []
        # 否则，返回检索结果
        docs_with_distances = store.similarity_search_with_score(
            query,
            k=top_k,
            filter=where,
        )
        # 计算结果相似度评分
        return [
            (doc, 1.0 / (1.0 + max(float(distance), 0.0)))
            for doc, distance in docs_with_distances
        ]

    def _metadata(self, chunk: Chunk, collection_name: str) -> dict[str, str | int | bool]:
        """填充 chunk 的元数据"""
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
        """构建检索过滤条件"""
        # 默认带course_id 过滤
        filters: list[dict[str, str | bool]] = [{"course_id": course_id}]
        # 如果有其他过滤条件，加入 filters
        if chapter:
            filters.append({"chapter": chapter})
        if source_type:
            filters.append({"source_type": source_type})
        if verified_only is not None:
            filters.append({"verified": verified_only})
        # 如果只有一个过滤条件，直接返回该条件，否则返回 $and 组合
        if len(filters) == 1:
            return filters[0]
        return {"$and": filters}
