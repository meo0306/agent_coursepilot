from __future__ import annotations

from pathlib import Path

from courserag.chunking.splitter import ParentChildChunker
from courserag.domain.chunk import ChunkProfile
from courserag.domain.document import sha256_text
from courserag.domain.evidence import (
    EvidenceArtifact,
    EvidenceRecord,
    EvidenceSourceUnit,
    stable_evidence_id,
)
from courserag.evals.p06_metrics import (
    chunk_evidence_coverage,
    chunk_redundancy_rate,
    complete_semantic_unit_rate,
    cross_boundary_split_error_rate,
    evidence_resolving_rate,
    evidence_text_consistency,
    map_gold_to_system_evidence,
    parent_expansion_sufficiency,
)
from courserag.evals.schemas import DS2EvidenceDataset


class CharacterTokenizer:
    tokenizer_id = "metric-char-v1"
    tokenizer_sha256 = "d" * 64

    def token_spans(self, text: str) -> tuple[tuple[int, int], ...]:
        return tuple((index, index + 1) for index in range(len(text)))

    def count(self, text: str) -> int:
        return len(text)

    def token_ids(self, text: str) -> tuple[int | str, ...]:
        return tuple(text)


def _profile() -> ChunkProfile:
    return ChunkProfile(
        name="metric",
        version="v1",
        tokenizer_id="metric-char-v1",
        tokenizer_sha256="d" * 64,
        parent_min_tokens=1,
        parent_target_tokens=2000,
        parent_max_tokens=3000,
        child_min_tokens=1,
        child_target_tokens=1000,
        child_max_tokens=1500,
        child_overlap_tokens=10,
    )


def test_p06_metrics_are_source_grounded_and_computable() -> None:
    dataset = DS2EvidenceDataset.model_validate_json(
        Path("datasets/courserag_eval/v1/approved/ds2/p06_evidence.json").read_text(
            encoding="utf-8"
        )
    )
    gold = next(record for record in dataset.evidence if record.requires_parent)
    text = "\n\n".join([*gold.necessary_neighbor_text, gold.gold_text])
    unit = EvidenceSourceUnit(
        block_id=gold.source_units[0].source_unit_id,
        block_type="paragraph",
        ordinal=0,
        char_start=0,
        char_end=len(text),
        text=text,
        text_sha256=sha256_text(text),
    )
    content_hash = sha256_text(text)
    evidence = EvidenceRecord(
        evidence_id=stable_evidence_id(gold.source_span.document_version, (unit,), content_hash),
        document_id=gold.source_span.document_id,
        document_version_id=gold.source_span.document_version,
        section_id="metric-section",
        section_path=tuple(gold.source_span.section_path),
        evidence_type="paragraph",
        source_mode="native",
        text=text,
        content_sha256=content_hash,
        normalized_sha256=sha256_text(" ".join(text.split())),
        source_units=(unit,),
    )
    artifact = EvidenceArtifact(
        document_id=evidence.document_id,
        document_version_id=evidence.document_version_id,
        parsed_document_sha256="e" * 64,
        builder_profile="metric",
        builder_profile_sha256="f" * 64,
        records=(evidence,),
    )
    chunks = ParentChildChunker(_profile(), CharacterTokenizer()).build(artifact)
    matches = map_gold_to_system_evidence([gold], [evidence])

    assert len(matches) == 1
    assert evidence_resolving_rate(artifact, chunks).value == 1.0
    assert evidence_text_consistency([gold], [evidence], matches).value == 1.0
    assert chunk_evidence_coverage([gold], chunks.chunks).value == 1.0
    assert complete_semantic_unit_rate([gold], chunks.chunks).value == 1.0
    assert cross_boundary_split_error_rate([gold], chunks.chunks).value == 0.0
    assert parent_expansion_sufficiency([gold], chunks.chunks).value == 1.0
    assert chunk_redundancy_rate(chunks.chunks, list).applicable
