"""
保存上传文件和创建文档记录
"""
from pathlib import Path
from uuid import uuid4

from fastapi import UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from core.settings import settings
from coursepilot.models import Course, Document

SUPPORTED_UPLOAD_SUFFIXES = {".pdf", ".docx", ".txt", ".md", ".markdown", ".xlsx"}


class DocumentService:
    def __init__(self, session: Session):
        self.session = session

    def list_documents(self, course_id: str) -> list[Document]:
        """ 列出所有文档，按创建时间倒序排列 """
        stmt = (
            select(Document)
            .where(Document.course_id == course_id)
            .order_by(Document.created_at.desc())
        )
        return list(self.session.scalars(stmt))

    def get_document(self, document_id: str) -> Document | None:
        """ 根据ID获取文档，返回文档对象或None """
        return self.session.get(Document, document_id)

    def save_upload(self, course_id: str, file: UploadFile, source_type: str) -> Document:
        """ 保存上传文件并创建文档记录，=create """
        # 取安全文件名
        # 上传资料前先确认课程存在,避免产生没有归属课程的文档
        if self.session.get(Course, course_id) is None:
            raise ValueError(f"Course not found: {course_id}")

        file_name = Path(file.filename or "").name
        #校验后缀
        suffix = Path(file_name).suffix.lower() # 文件类型（后缀）
        if suffix == ".doc":    # 不支持上传.doc
            raise ValueError("Unsupported legacy .doc file. Please convert it to .docx before upload.")
        if suffix not in SUPPORTED_UPLOAD_SUFFIXES:
            raise ValueError(f"Unsupported file type: {suffix or '<none>'}")    # 不支持文件返回error
        # 创建目录
        upload_dir = Path(settings.COURSEPILOT_STORAGE_DIR) / "uploads" / course_id #每门课程的上传文件单独放到 storage/uploads/{course_id}
        upload_dir.mkdir(parents=True, exist_ok=True)
        # 生成服务端文件名
        storage_name = f"{uuid4()}{suffix}" # 实际保存文件名使用 UUID，避免同名文件互相覆盖
        file_path = upload_dir / storage_name
        # 分块写入磁盘
        with file_path.open("wb") as output:
            while chunk := file.file.read(1024 * 1024): # 按 1MB 分块写文件
                output.write(chunk)
        # 元数据写入数据库
        document = Document(
            course_id=course_id,
            file_name=file_name,
            file_path=str(file_path),
            file_type=suffix.lstrip("."),
            source_type=source_type,
            parse_status="uploaded",
        )
        self.session.add(document)
        self.session.commit()
        self.session.refresh(document)
        return document
