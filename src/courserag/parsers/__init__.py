"""Structured PDF/DOCX parsing introduced by P04."""

from courserag.parsers.artifact_bundle import (
    ParsedArtifactBundle,
    build_parsed_artifact_bundle,
    read_bundle_json,
)

__all__ = ["ParsedArtifactBundle", "build_parsed_artifact_bundle", "read_bundle_json"]
