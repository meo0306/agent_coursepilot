from __future__ import annotations

import io
import re
import zipfile
from dataclasses import dataclass
from pathlib import PurePosixPath


@dataclass(frozen=True)
class SecurityInspection:
    detected_mime: str
    safe: bool
    warning_codes: tuple[str, ...] = ()


class DocumentSecurityPolicy:
    def __init__(
        self,
        *,
        max_document_bytes: int = 100 * 1024 * 1024,
        max_docx_entries: int = 20_000,
        max_docx_uncompressed_bytes: int = 512 * 1024 * 1024,
        max_docx_compression_ratio: float = 200,
        max_pdf_pages: int = 2_000,
        max_ocr_dpi: int = 600,
        parse_timeout_seconds: float = 300,
    ) -> None:
        self.max_document_bytes = max_document_bytes
        self.max_docx_entries = max_docx_entries
        self.max_docx_uncompressed_bytes = max_docx_uncompressed_bytes
        self.max_docx_compression_ratio = max_docx_compression_ratio
        self.max_pdf_pages = max_pdf_pages
        self.max_ocr_dpi = max_ocr_dpi
        self.parse_timeout_seconds = parse_timeout_seconds

    def inspect(self, *, filename: str, declared_mime: str, content: bytes) -> SecurityInspection:
        self._validate_filename(filename)
        if len(content) > self.max_document_bytes:
            raise ValueError("DOCUMENT_SIZE_LIMIT")
        detected = self._detect_mime(content)
        normalized_declared = declared_mime.split(";", maxsplit=1)[0].strip().lower()
        allowed_declared = {
            "application/pdf": "application/pdf",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document": (
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            ),
        }
        if allowed_declared.get(normalized_declared) != detected:
            raise ValueError("MIME_MISMATCH")
        if detected.endswith("wordprocessingml.document"):
            self._inspect_docx(content)
        else:
            self._inspect_pdf(content)
        warnings = ("PROMPT_INJECTION_MARKED",) if contains_prompt_injection(content) else ()
        return SecurityInspection(detected_mime=detected, safe=True, warning_codes=warnings)

    @staticmethod
    def _validate_filename(filename: str) -> None:
        normalized = filename.replace("\\", "/")
        if (
            not filename
            or PurePosixPath(normalized).name != normalized
            or ".." in PurePosixPath(normalized).parts
        ):
            raise ValueError("UNSAFE_PATH")

    @staticmethod
    def _detect_mime(content: bytes) -> str:
        if content.startswith(b"%PDF-"):
            return "application/pdf"
        if content.startswith(b"PK\x03\x04"):
            return "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        raise ValueError("UNSUPPORTED_MIME")

    def _inspect_docx(self, content: bytes) -> None:
        try:
            archive = zipfile.ZipFile(io.BytesIO(content))
        except zipfile.BadZipFile as exc:
            raise ValueError("INVALID_DOCX_ZIP") from exc
        infos = archive.infolist()
        if len(infos) > self.max_docx_entries:
            raise ValueError("DOCX_ENTRY_LIMIT")
        total_uncompressed = 0
        total_compressed = 0
        for info in infos:
            path = PurePosixPath(info.filename.replace("\\", "/"))
            if path.is_absolute() or ".." in path.parts:
                raise ValueError("UNSAFE_ARCHIVE_PATH")
            total_uncompressed += info.file_size
            total_compressed += max(info.compress_size, 1)
        if total_uncompressed > self.max_docx_uncompressed_bytes:
            raise ValueError("DOCX_UNCOMPRESSED_SIZE_LIMIT")
        if total_uncompressed / max(total_compressed, 1) > self.max_docx_compression_ratio:
            raise ValueError("ARCHIVE_COMPRESSION_LIMIT")

    def _inspect_pdf(self, content: bytes) -> None:
        import fitz

        try:
            document = fitz.open(stream=content, filetype="pdf")
        except Exception as exc:
            raise ValueError("INVALID_PDF") from exc
        try:
            if document.needs_pass:
                raise ValueError("PDF_ENCRYPTED")
            self.validate_page_count(document.page_count)
        finally:
            document.close()

    def validate_runtime_limits(self, *, dpi: int, elapsed_seconds: float) -> None:
        if dpi > self.max_ocr_dpi:
            raise ValueError("DPI_LIMIT")
        if elapsed_seconds > self.parse_timeout_seconds:
            raise TimeoutError("PARSE_TIMEOUT")

    def validate_page_count(self, page_count: int) -> None:
        if page_count > self.max_pdf_pages:
            raise ValueError("PAGE_LIMIT")


_INJECTION = re.compile(
    rb"(?i)(ignore\s+(all\s+)?previous|system\s+prompt|developer\s+message|\xe5\xbf\xbd\xe7\x95\xa5.{0,20}\xe6\x8c\x87\xe4\xbb\xa4)"
)


def contains_prompt_injection(content: bytes) -> bool:
    return bool(_INJECTION.search(content))
