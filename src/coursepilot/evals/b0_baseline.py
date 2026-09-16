"""P00 B0 manifest helpers.

This module deliberately stores only fingerprints and structural metadata. It never serializes
source text, environment values, or provider credentials.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from coursepilot.rag.parsers import get_parser

EXPECTED_SAMPLE_COUNTS = {".docx": 1, ".pdf": 1}
SAMPLE_MANIFEST_SCHEMA = "coursepilot.p00.sample-input-manifest.v1"
B0_REPORT_SCHEMA = "coursepilot.p00.b0-smoke-report.v1"


class B0InputError(ValueError):
    """Raised when local B0 input preconditions are not satisfied."""


@dataclass(frozen=True)
class SampleInput:
    path: Path
    repository_relative_path: str
    media_type: str
    size_bytes: int
    sha256: str

    def as_manifest_item(self) -> dict[str, str | int]:
        return {
            "path": self.repository_relative_path,
            "media_type": self.media_type,
            "size_bytes": self.size_bytes,
            "sha256": self.sha256,
            "redistribution_status": "local_only_unverified",
            "approval_status": "candidate_not_approved",
        }


@dataclass(frozen=True)
class NonGoldProbe:
    query: str
    query_sha256: str
    query_char_count: int

    def safe_metadata(self) -> dict[str, str | int]:
        return {
            "derivation": "first_normalized_source_fragment",
            "classification": "non_gold_smoke_only",
            "query_sha256": self.query_sha256,
            "query_char_count": self.query_char_count,
        }


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def discover_sample_inputs(sample_dir: Path, repository_root: Path) -> list[SampleInput]:
    """Validate the owner-supplied one-DOCX/one-PDF input boundary."""

    sample_dir = sample_dir.resolve()
    repository_root = repository_root.resolve()
    if not sample_dir.is_dir():
        raise B0InputError(f"B0 sample directory does not exist: {sample_dir}")

    try:
        sample_dir.relative_to(repository_root)
    except ValueError as exc:
        raise B0InputError("B0 sample directory must be inside the repository") from exc

    supported = sorted(
        (
            path
            for path in sample_dir.iterdir()
            if path.is_file() and path.suffix.lower() in EXPECTED_SAMPLE_COUNTS
        ),
        key=lambda path: (path.suffix.lower(), path.name.casefold()),
    )
    actual_counts = {
        suffix: sum(path.suffix.lower() == suffix for path in supported)
        for suffix in EXPECTED_SAMPLE_COUNTS
    }
    if actual_counts != EXPECTED_SAMPLE_COUNTS:
        raise B0InputError(
            "B0 requires exactly one DOCX and one PDF; "
            f"found docx={actual_counts['.docx']} pdf={actual_counts['.pdf']}"
        )

    inputs: list[SampleInput] = []
    for path in supported:
        size_bytes = path.stat().st_size
        if size_bytes <= 0:
            raise B0InputError(f"B0 sample file is empty: {path.name}")
        relative_path = path.resolve().relative_to(repository_root).as_posix()
        inputs.append(
            SampleInput(
                path=path,
                repository_relative_path=relative_path,
                media_type=media_type_for_suffix(path.suffix),
                size_bytes=size_bytes,
                sha256=sha256_file(path),
            )
        )
    return inputs


def build_sample_manifest(
    inputs: list[SampleInput],
    *,
    baseline_commit: str,
    captured_at: str,
) -> dict[str, Any]:
    return {
        "schema_version": SAMPLE_MANIFEST_SCHEMA,
        "captured_at": captured_at,
        "baseline_commit": baseline_commit,
        "declared_relationship": "independent_documents_with_different_content",
        "gold_status": "not_gold",
        "source_text_included": False,
        "inputs": [item.as_manifest_item() for item in inputs],
    }


def select_non_gold_probe(path: Path, *, max_characters: int = 64) -> NonGoldProbe:
    """Derive an in-memory smoke query from source text without serializing that text."""

    parsed = get_parser(path).parse(path)
    for section in parsed.sections:
        normalized = re.sub(r"\s+", " ", section.content).strip()
        if len(normalized) < 4:
            continue
        query = normalized[:max_characters]
        return NonGoldProbe(
            query=query,
            query_sha256=hashlib.sha256(query.encode("utf-8")).hexdigest(),
            query_char_count=len(query),
        )
    raise B0InputError(f"No usable source text was extracted from {path.name}")


def write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    text = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    temporary.write_text(text, encoding="utf-8")
    os.replace(temporary, path)


def media_type_for_suffix(suffix: str) -> str:
    normalized = suffix.lower()
    if normalized == ".docx":
        return "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    if normalized == ".pdf":
        return "application/pdf"
    raise B0InputError(f"Unsupported B0 file type: {suffix}")
