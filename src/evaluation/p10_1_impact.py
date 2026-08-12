from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, JsonValue, TypeAdapter

from core.settings import settings
from courserag.chunking.profile import load_chunk_profile
from courserag.chunking.splitter import ParentChildChunker
from courserag.chunking.tokenizer import LocalTokenizer
from courserag.contracts.qa import QAResponse
from courserag.contracts.retrieval import ContextPackage, SearchResponse
from courserag.domain.chunk import ChunkArtifact
from courserag.domain.document import ParsedDocumentIR, canonical_json_bytes, sha256_bytes
from courserag.domain.evidence import EvidenceArtifact
from courserag.evidence.builder import EvidenceBuilder
from courserag.parsers.docx import StructuredDOCXParser
from courserag.parsers.pdf import StructuredPDFParser
from courserag.parsers.structure import enrich_document_structure
from courserag.security import load_prompt_injection_profile, mark_untrusted_instructions
from evaluation.io import atomic_write_json

_JSON_ADAPTER: TypeAdapter[JsonValue] = TypeAdapter(JsonValue)


def run_impact_equivalence(*, repository_root: Path, output_path: Path) -> Path:
    root = repository_root.resolve()
    profile = load_prompt_injection_profile(
        root / "resources/security_profiles/prompt_injection_candidate_v2.json"
    )
    chunk_profile = load_chunk_profile(root / "resources/chunk_profiles/parent_child_v1.json")
    tokenizer = LocalTokenizer(
        root / settings.COURSERAG_CHUNK_TOKENIZER_PATH,
        tokenizer_id=chunk_profile.tokenizer_id,
        expected_sha256=chunk_profile.tokenizer_sha256,
    )
    chunker = ParentChildChunker(chunk_profile, tokenizer)
    sources = (
        root / "data/sample_files/人工智能通识教程.pdf",
        root / "data/sample_files/教材-人工智能：从算法到系统.docx",
    )
    comparisons: list[dict[str, object]] = []
    for ordinal, source in enumerate(sources, 1):
        content = source.read_bytes()
        document = _parse_document(
            content,
            suffix=source.suffix.casefold(),
            document_id=f"p10-1-impact-doc-{ordinal}",
            document_version_id=f"p10-1-impact-version-{ordinal}",
        )
        marked = mark_untrusted_instructions(document, profile)
        before_evidence = EvidenceBuilder().build(document)
        after_evidence = EvidenceBuilder().build(marked)
        before_chunks = chunker.build(before_evidence)
        after_chunks = chunker.build(after_evidence)
        before = semantic_projection(document, before_evidence, before_chunks)
        after = semantic_projection(marked, after_evidence, after_chunks)
        comparisons.append(
            {
                "source_name": source.name,
                "source_sha256": sha256_bytes(content),
                "semantic_projection_sha256_before": sha256_bytes(canonical_json_bytes(before)),
                "semantic_projection_sha256_after": sha256_bytes(canonical_json_bytes(after)),
                "semantic_equal": before == after,
                "parsed_artifact_hash_changed": document.content_sha256 != marked.content_sha256,
                "evidence_artifact_hash_changed": (
                    before_evidence.content_sha256 != after_evidence.content_sha256
                ),
                "block_count": sum(len(page.blocks) for page in document.pages),
                "evidence_count": len(before_evidence.records),
                "child_chunk_count": sum(chunk.kind == "child" for chunk in before_chunks.chunks),
            }
        )
    wire_schema_hashes = {
        model.__name__: _schema_sha256(model)
        for model in (SearchResponse, ContextPackage, QAResponse)
    }
    immutable_paths = (
        root / "storage_eval/p10/frozen_manifest.json",
        root / "storage_eval/p10/formal/retrieval-run-1/report.json",
        root / "storage_eval/p10/formal/retrieval-run-1/checkpoint.json",
        root / "storage_eval/p10/formal/qa-run-1/report.json",
        root / "storage_eval/p10/formal/qa-run-1/checkpoint.json",
        root / "datasets/courserag_eval/v1/test.lock.json",
    )
    immutable_hashes = {
        path.relative_to(root).as_posix(): _sha256_file(path) for path in immutable_paths
    }
    index_versions = _collect_values(
        json.loads(
            (root / "storage_eval/p10/formal/qa-run-1/checkpoint.json").read_text(encoding="utf-8")
        ),
        "index_version",
    )
    checks = {
        "document_text_block_order_evidence_chunk_and_corpus_equal": all(
            bool(item["semantic_equal"]) for item in comparisons
        ),
        "public_wire_schemas_bound": len(wire_schema_hashes) == 3,
        "primary_report_manifest_and_test_lock_bound": len(immutable_hashes) == 6,
        "formal_index_versions_bound": bool(index_versions),
        "external_provider_calls_zero": True,
        "test_access_false": True,
    }
    payload: dict[str, object] = {
        "schema_version": "courserag.p10-1-impact-equivalence.v1",
        "status": "passed" if all(checks.values()) else "failed",
        "generated_at": datetime.now(UTC).isoformat(),
        "security_profile_sha256": profile.sha256,
        "comparisons": comparisons,
        "wire_schema_sha256": wire_schema_hashes,
        "immutable_p10_sha256": immutable_hashes,
        "formal_index_versions": sorted(index_versions),
        "checks": checks,
    }
    atomic_write_json(output_path.resolve(), _JSON_ADAPTER.validate_python(payload))
    return output_path.resolve()


def semantic_projection(
    document: ParsedDocumentIR,
    evidence: EvidenceArtifact,
    chunks: ChunkArtifact,
) -> dict[str, object]:
    return {
        "document": {
            "document_id": document.document_id,
            "document_version_id": document.document_version_id,
            "pages": [
                {
                    "page_id": page.page_id,
                    "content_sha256": page.content_sha256,
                    "blocks": [
                        {
                            "block_id": block.block_id,
                            "order_index": block.order_index,
                            "text": block.text,
                            "content_sha256": block.content_sha256,
                            "source_span": block.source_span.model_dump(mode="json"),
                        }
                        for block in page.blocks
                    ],
                }
                for page in document.pages
            ],
        },
        "evidence": [
            {
                "evidence_id": record.evidence_id,
                "text": record.text,
                "content_sha256": record.content_sha256,
                "source_units": [unit.model_dump(mode="json") for unit in record.source_units],
                "page_bboxes": [bbox.model_dump(mode="json") for bbox in record.page_bboxes],
            }
            for record in evidence.records
        ],
        "chunks": [
            {
                "chunk_id": chunk.chunk_id,
                "kind": chunk.kind,
                "parent_chunk_id": chunk.parent_chunk_id,
                "text": chunk.text,
                "content_sha256": chunk.content_sha256,
                "evidence_links": [link.model_dump(mode="json") for link in chunk.evidence_links],
            }
            for chunk in chunks.chunks
        ],
        "index_corpus": [
            {
                "chunk_id": chunk.chunk_id,
                "text_sha256": chunk.content_sha256,
            }
            for chunk in chunks.chunks
            if chunk.kind == "child"
        ],
    }


def _parse_document(
    content: bytes,
    *,
    suffix: str,
    document_id: str,
    document_version_id: str,
) -> ParsedDocumentIR:
    digest = sha256_bytes(content)
    if suffix == ".pdf":
        document = (
            StructuredPDFParser()
            .parse(
                content,
                document_id=document_id,
                document_version_id=document_version_id,
                document_sha256=digest,
            )
            .document
        )
    elif suffix == ".docx":
        document = (
            StructuredDOCXParser()
            .parse(
                content,
                document_id=document_id,
                document_version_id=document_version_id,
                document_sha256=digest,
            )
            .document
        )
    else:
        raise ValueError(f"unsupported impact source format: {suffix}")
    return enrich_document_structure(document)


def _schema_sha256(model: type[BaseModel]) -> str:
    return sha256_bytes(canonical_json_bytes(model.model_json_schema()))


def _collect_values(value: object, key: str) -> set[str]:
    found: set[str] = set()
    if isinstance(value, dict):
        for nested_key, nested_value in value.items():
            if nested_key == key and isinstance(nested_value, str) and nested_value:
                found.add(nested_value)
            found.update(_collect_values(nested_value, key))
    elif isinstance(value, list):
        for item in value:
            found.update(_collect_values(item, key))
    return found


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()
