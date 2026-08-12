from __future__ import annotations

import io
import zipfile
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path, PurePosixPath

from courserag.security.prompt_injection import (
    PromptInjectionProfile,
    contains_prompt_injection_text,
    load_prompt_injection_profile,
)


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
        # Semantic instruction marking happens after structured parsing/OCR. Raw PDF and
        # DOCX bytes are not a reliable text surface and must not be treated as one.
        return SecurityInspection(detected_mime=detected, safe=True)

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


def contains_prompt_injection(content: bytes) -> bool:
    """Compatibility wrapper for already-extracted UTF-8 evaluation controls.

    Product ingestion must use ``mark_untrusted_instructions`` over ParsedDocumentIR.
    """

    return contains_prompt_injection_text(content.decode("utf-8", errors="ignore"), _profile())


@lru_cache(maxsize=1)
def _profile() -> PromptInjectionProfile:
    return load_prompt_injection_profile(
        Path(__file__).resolve().parents[3]
        / "resources/security_profiles/prompt_injection_candidate_v2.json"
    )
