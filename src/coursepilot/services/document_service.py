from pathlib import Path
from uuid import uuid4

from fastapi import UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from core.settings import settings
from coursepilot.models import Course, Document

SUPPORTED_UPLOAD_SUFFIXES = {".pdf", ".docx", ".txt", ".md", ".markdown", ".xlsx", ".doc"}


class DocumentService:
    def __init__(self, session: Session):
        self.session = session

    def list_documents(self, course_id: str) -> list[Document]:
        stmt = (
            select(Document)
            .where(Document.course_id == course_id)
            .order_by(Document.created_at.desc())
        )
        return list(self.session.scalars(stmt))

    def get_document(self, document_id: str) -> Document | None:
        return self.session.get(Document, document_id)

    def save_upload(self, course_id: str, file: UploadFile, source_type: str) -> Document:
        if self.session.get(Course, course_id) is None:
            raise ValueError(f"Course not found: {course_id}")

        file_name = Path(file.filename or "").name
        suffix = Path(file_name).suffix.lower()
        if suffix not in SUPPORTED_UPLOAD_SUFFIXES:
            raise ValueError(f"Unsupported file type: {suffix or '<none>'}")

        upload_dir = Path(settings.COURSEPILOT_STORAGE_DIR) / "uploads" / course_id
        upload_dir.mkdir(parents=True, exist_ok=True)
        storage_name = f"{uuid4()}{suffix}"
        file_path = upload_dir / storage_name

        with file_path.open("wb") as output:
            while chunk := file.file.read(1024 * 1024):
                output.write(chunk)

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

