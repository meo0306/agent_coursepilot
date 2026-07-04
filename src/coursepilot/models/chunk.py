"""
定义KnowledgeChunk数据模型
用于存储知识块相关信息，包括课程ID、文档ID、源类型等。
该模型与Course和Document模型建立了一对多的关系，允许一个知识块属于一个课程和一个文档。
"""

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from coursepilot.db.base import Base


def utc_now() -> datetime:
    return datetime.now(UTC)


class KnowledgeChunk(Base):
    __tablename__ = "coursepilot_chunks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    course_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("coursepilot_courses.id", ondelete="CASCADE"), nullable=False
    )
    document_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("coursepilot_documents.id", ondelete="CASCADE"), nullable=False
    )
    source_type: Mapped[str] = mapped_column(String(100), nullable=False)
    # RAG 引用需要展示的来源信息
    chapter: Mapped[str | None] = mapped_column(String(255), nullable=True)
    section: Mapped[str | None] = mapped_column(String(255), nullable=True)
    page: Mapped[int | None] = mapped_column(Integer, nullable=True)
    title: Mapped[str | None] = mapped_column(String(512), nullable=True)
    # 保存 chunk 前 1000 字左右的预览，完整正文主要在 Chroma 里
    content_preview: Mapped[str] = mapped_column(Text, nullable=False)
    # 保存简单提取出的关键词列表
    knowledge_points_json: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    # 审核标志
    verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # Chroma 向量数据库相关字段
    chroma_collection: Mapped[str] = mapped_column(String(255), nullable=False)
    chroma_doc_id: Mapped[str] = mapped_column(String(255), nullable=False)
    
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    course = relationship("Course", back_populates="chunks")
    document = relationship("Document", back_populates="chunks")

