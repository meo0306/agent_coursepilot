from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from coursepilot.db.base import Base


def utc_now() -> datetime:
    return datetime.now(UTC)


class Course(Base):
    __tablename__ = "coursepilot_courses"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    course_name: Mapped[str] = mapped_column(String(255), nullable=False)
    course_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    student_level: Mapped[str | None] = mapped_column(String(100), nullable=True)
    student_background: Mapped[str | None] = mapped_column(Text, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )

    documents = relationship("Document", back_populates="course", cascade="all, delete-orphan")
    chunks = relationship("KnowledgeChunk", back_populates="course", cascade="all, delete-orphan")

