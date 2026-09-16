"""Deterministic serialization for parsed-document artifacts."""

from __future__ import annotations

import io
import zipfile
from dataclasses import dataclass

from courserag.domain.document import (
    ParsedDocumentIR,
    ParsePreview,
    ParseQualityReport,
    canonical_json_bytes,
    sha256_bytes,
)
from courserag.parsers.ocr.types import OCRPageResult

_ZIP_TIMESTAMP = (1980, 1, 1, 0, 0, 0)


@dataclass(frozen=True)
class ParsedArtifactBundle:
    content: bytes
    sha256: str


def build_parsed_artifact_bundle(
    document: ParsedDocumentIR,
    quality: ParseQualityReport,
    preview: ParsePreview,
    *,
    binary_assets: dict[str, bytes] | None = None,
    ocr_results: tuple[OCRPageResult, ...] | None = None,
) -> ParsedArtifactBundle:
    entries = {
        "document_ir.json": canonical_json_bytes(document),
        "preview.json": canonical_json_bytes(preview),
        "quality_report.json": canonical_json_bytes(quality),
    }
    if ocr_results is not None:
        entries["ocr_results.json"] = canonical_json_bytes(
            [result.model_dump(mode="json") for result in ocr_results]
        )
    for name, content in (binary_assets or {}).items():
        normalized = name.replace("\\", "/").lstrip("/")
        if not normalized or ".." in normalized.split("/"):
            raise ValueError("binary asset path must stay inside the parsed artifact")
        if normalized in entries:
            raise ValueError(f"duplicate parsed artifact entry: {normalized}")
        entries[normalized] = content

    content = _write_entries(entries)
    return ParsedArtifactBundle(content=content, sha256=sha256_bytes(content))


def replace_parsed_artifact_document(
    content: bytes,
    document: ParsedDocumentIR,
    quality: ParseQualityReport,
    preview: ParsePreview,
) -> ParsedArtifactBundle:
    """Replace only annotation-aware JSON entries and preserve all parser/OCR assets."""

    with zipfile.ZipFile(io.BytesIO(content), mode="r") as archive:
        entries = {name: archive.read(name) for name in archive.namelist()}
    required = {"document_ir.json", "preview.json", "quality_report.json"}
    if not required.issubset(entries):
        raise ValueError("parsed artifact is missing required JSON entries")
    entries.update(
        {
            "document_ir.json": canonical_json_bytes(document),
            "preview.json": canonical_json_bytes(preview),
            "quality_report.json": canonical_json_bytes(quality),
        }
    )
    replaced = _write_entries(entries)
    return ParsedArtifactBundle(content=replaced, sha256=sha256_bytes(replaced))


def _write_entries(entries: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(
        buffer, mode="w", compression=zipfile.ZIP_DEFLATED, compresslevel=9
    ) as archive:
        for name, content in sorted(entries.items()):
            info = zipfile.ZipInfo(name, _ZIP_TIMESTAMP)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            info.create_system = 3
            archive.writestr(info, content, compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
    return buffer.getvalue()


def read_bundle_json(content: bytes, name: str) -> bytes:
    with zipfile.ZipFile(io.BytesIO(content), mode="r") as archive:
        if name not in archive.namelist():
            raise ValueError(f"parsed artifact entry is missing: {name}")
        return archive.read(name)
