"""
定义Course 数据模型
用于存储课程相关信息，包括课程名称、类型、学生水平、背景、描述以及创建和更新时间。
该模型与Document和KnowledgeChunk模型建立了一对多的关系，允许一个课程包含多个文档和知识块。
"""

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from coursepilot.db.base import Base


def utc_now() -> datetime:
    return datetime.now(UTC)


class Course(Base):
    # 指定数据库表名
    __tablename__ = "coursepilot_courses"
    # 添加数据库字段
    # 课程唯一标识符，使用UUID生成，作为主键
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    # 课程名称，不能为空
    course_name: Mapped[str] = mapped_column(String(255), nullable=False)
    # 课程基本信息字段
    course_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    student_level: Mapped[str | None] = mapped_column(String(100), nullable=True)
    student_background: Mapped[str | None] = mapped_column(Text, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 创建和更新时间字段，使用UTC时间
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )
    # 与Document和KnowledgeChunk模型建立一对多关系，设置级联删除
    documents = relationship("Document", back_populates="course", cascade="all, delete-orphan") # ORM 对象关系：可以通过 course.documents 拿到这个课程下的所有文档，cascade="all, delete-orphan"表示父对象操作会级联到子对象
    chunks = relationship("KnowledgeChunk", back_populates="course", cascade="all, delete-orphan")

