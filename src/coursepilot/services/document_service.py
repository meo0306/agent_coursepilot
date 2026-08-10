"""Persist uploaded source files and their legacy CoursePilot document record."""

from pathlib import Path
from uuid import uuid4

from fastapi import UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from core.settings import settings
from coursepilot.models import Course, Document
from courserag.security import DocumentSecurityPolicy

SUPPORTED_UPLOAD_SUFFIXES = {".pdf", ".docx", ".txt", ".md", ".markdown", ".xlsx"}


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

        raw_file_name = file.filename or ""
        file_name = Path(raw_file_name).name
        suffix = Path(file_name).suffix.lower()
        if suffix == ".doc":
            raise ValueError(
                "Unsupported legacy .doc file. Please convert it to .docx before upload."
            )
        if suffix not in SUPPORTED_UPLOAD_SUFFIXES:
            raise ValueError(f"Unsupported file type: {suffix or '<none>'}")

        inspected_content: bytes | None = None
        if suffix in {".pdf", ".docx"}:
            inspected_content = file.file.read(settings.COURSERAG_MAX_DOCUMENT_BYTES + 1)
            DocumentSecurityPolicy(
                max_document_bytes=settings.COURSERAG_MAX_DOCUMENT_BYTES,
                max_docx_entries=settings.COURSERAG_MAX_DOCX_ENTRIES,
                max_docx_uncompressed_bytes=settings.COURSERAG_MAX_DOCX_UNCOMPRESSED_BYTES,
                max_docx_compression_ratio=settings.COURSERAG_MAX_DOCX_COMPRESSION_RATIO,
                max_pdf_pages=settings.COURSERAG_MAX_PDF_PAGES,
                max_ocr_dpi=settings.COURSERAG_MAX_OCR_DPI,
                parse_timeout_seconds=settings.COURSERAG_PARSE_TIMEOUT_SECONDS,
            ).inspect(
                filename=raw_file_name,
                declared_mime=file.content_type or "application/octet-stream",
                content=inspected_content,
            )

        upload_dir = Path(settings.COURSEPILOT_STORAGE_DIR) / "uploads" / course_id
        upload_dir.mkdir(parents=True, exist_ok=True)
        storage_name = f"{uuid4()}{suffix}"
        file_path = upload_dir / storage_name
        with file_path.open("wb") as output:
            if inspected_content is not None:
                output.write(inspected_content)
            else:
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
