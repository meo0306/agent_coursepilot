"""
定义Document 数据模型
用于存储文档相关信息，包括课程ID、文件名、文件路径、文件类型、源类型等。
该模型与Course和KnowledgeChunk模型建立了一对多的关系，允许一个文档属于一个课程，并且可以包含多个知识块。
"""
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from coursepilot.db.base import Base


def utc_now() -> datetime:
    return datetime.now(UTC)


class Document(Base):
    __tablename__ = "coursepilot_documents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    course_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("coursepilot_courses.id", ondelete="CASCADE"), nullable=False
    )   # 把文档绑定到课程
    file_name: Mapped[str] = mapped_column(String(512), nullable=False)
    file_path: Mapped[str] = mapped_column(Text, nullable=False)
    file_type: Mapped[str] = mapped_column(String(32), nullable=False)
    source_type: Mapped[str] = mapped_column(String(100), nullable=False, default="unknown")    # 资料来源
    parse_status: Mapped[str] = mapped_column(String(32), nullable=False, default="uploaded")   # 当前处理状态
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )
    
    course = relationship("Course", back_populates="documents")
    chunks = relationship("KnowledgeChunk", back_populates="document", cascade="all, delete-orphan")

