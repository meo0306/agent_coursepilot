"""Parser boundaries and fail-closed input validation."""

from __future__ import annotations

import io
import zipfile
from dataclasses import dataclass, field
from pathlib import PurePosixPath
from typing import Protocol

import fitz

from courserag.domain.document import ParsedDocumentIR


class UnsafeDocumentError(ValueError):
    pass


class UnsupportedStructuredDocumentError(ValueError):
    pass


@dataclass(frozen=True)
class ParserLimits:
    max_file_bytes: int = 100 * 1024 * 1024
    max_pdf_pages: int = 2_000
    max_docx_entries: int = 20_000
    max_docx_uncompressed_bytes: int = 512 * 1024 * 1024
    max_docx_compression_ratio: float = 200.0


@dataclass(frozen=True)
class ParseResult:
    document: ParsedDocumentIR
    binary_assets: dict[str, bytes] = field(default_factory=dict)


class StructuredDocumentParser(Protocol):
    parser_profile: str
    parser_version: str

    def parse(
        self,
        content: bytes,
        *,
        document_id: str,
        document_version_id: str,
        document_sha256: str,
    ) -> ParseResult: ...


def validate_file_size(content: bytes, limits: ParserLimits) -> None:
    if not content:
        raise UnsafeDocumentError("document is empty")
    if len(content) > limits.max_file_bytes:
        raise UnsafeDocumentError("document exceeds the configured size limit")


def validate_pdf(content: bytes, limits: ParserLimits) -> None:
    validate_file_size(content, limits)
    try:
        document = fitz.open(stream=content, filetype="pdf")
    except Exception as exc:
        raise UnsafeDocumentError("PDF cannot be opened") from exc
    try:
        if document.needs_pass:
            raise UnsafeDocumentError("encrypted PDF is not supported")
        if document.page_count > limits.max_pdf_pages:
            raise UnsafeDocumentError("PDF exceeds the configured page limit")
    finally:
        document.close()


def validate_docx(content: bytes, limits: ParserLimits) -> None:
    validate_file_size(content, limits)
    try:
        archive = zipfile.ZipFile(io.BytesIO(content), mode="r")
    except zipfile.BadZipFile as exc:
        raise UnsafeDocumentError("DOCX is not a valid ZIP package") from exc
    with archive:
        infos = archive.infolist()
        if len(infos) > limits.max_docx_entries:
            raise UnsafeDocumentError("DOCX contains too many ZIP entries")
        total_uncompressed = 0
        for info in infos:
            path = PurePosixPath(info.filename.replace("\\", "/"))
            if path.is_absolute() or ".." in path.parts:
                raise UnsafeDocumentError("DOCX ZIP entry escapes the package root")
            total_uncompressed += info.file_size
            if total_uncompressed > limits.max_docx_uncompressed_bytes:
                raise UnsafeDocumentError("DOCX uncompressed size exceeds the configured limit")
            if info.file_size and info.compress_size == 0:
                raise UnsafeDocumentError("DOCX contains an invalid compressed ZIP entry")
            if info.compress_size:
                ratio = info.file_size / info.compress_size
                if ratio > limits.max_docx_compression_ratio:
                    raise UnsafeDocumentError("DOCX ZIP entry exceeds the compression-ratio limit")
        if "word/document.xml" not in {info.filename for info in infos}:
            raise UnsafeDocumentError("DOCX package has no word/document.xml")
