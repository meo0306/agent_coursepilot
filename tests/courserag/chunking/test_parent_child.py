from __future__ import annotations

import hashlib

from courserag.chunking.splitter import ParentChildChunker
from courserag.domain.chunk import ChunkProfile
from courserag.domain.document import sha256_text
from courserag.domain.evidence import EvidenceRecord, stable_evidence_id
from courserag.evidence.builder import EvidenceBuilder
from tests.courserag.evidence.test_builder import _document


class CharacterTokenizer:
    tokenizer_id = "test-char-v1"
    tokenizer_sha256 = "c" * 64

    def token_spans(self, text: str) -> tuple[tuple[int, int], ...]:
        return tuple((index, index + 1) for index in range(len(text)))

    def count(self, text: str) -> int:
        return len(text)

    def token_ids(self, text: str) -> tuple[int | str, ...]:
        return tuple(text)


def _profile(*, child_target: int = 25) -> ChunkProfile:
    return ChunkProfile(
        name="test",
        version="v1",
        tokenizer_id="test-char-v1",
        tokenizer_sha256="c" * 64,
        parent_min_tokens=1,
        parent_target_tokens=80,
        parent_max_tokens=100,
        child_min_tokens=1,
        child_target_tokens=child_target,
        child_max_tokens=40,
        child_overlap_tokens=12,
    )


def test_parent_child_relationships_and_evidence_coverage_are_complete() -> None:
    evidence = EvidenceBuilder().build(_document())
    artifact = ParentChildChunker(_profile(), CharacterTokenizer()).build(evidence)
    parents = [chunk for chunk in artifact.chunks if chunk.kind == "parent"]
    children = [chunk for chunk in artifact.chunks if chunk.kind == "child"]

    assert parents
    assert children
    assert all(
        child.parent_chunk_id in {parent.chunk_id for parent in parents} for child in children
    )
    assert all(chunk.evidence_links for chunk in artifact.chunks)
    parent_coverage = {
        link.evidence_id
        for parent in parents
        for link in parent.evidence_links
        if link.evidence_char_start == 0
    }
    assert parent_coverage == {record.evidence_id for record in evidence.records}


def test_chunk_profile_change_changes_chunks_but_not_evidence() -> None:
    evidence = EvidenceBuilder().build(_document())
    first = ParentChildChunker(_profile(child_target=20), CharacterTokenizer()).build(evidence)
    second = ParentChildChunker(_profile(child_target=30), CharacterTokenizer()).build(evidence)

    assert first.chunk_set_id != second.chunk_set_id
    assert {link.evidence_id for chunk in first.chunks for link in chunk.evidence_links} == {
        record.evidence_id for record in evidence.records
    }
    assert [record.evidence_id for record in evidence.records] == [
        record.evidence_id for record in EvidenceBuilder().build(_document()).records
    ]


def test_long_atomic_sentence_is_split_with_visible_warning() -> None:
    artifact = EvidenceBuilder().build(_document())
    long_record = artifact.records[-1].model_copy(
        update={
            "text": "超" * 95,
            "content_sha256": "",
            "normalized_sha256": "",
        }
    )
    # Rebuild a valid immutable record with the same source identity but long source text.
    source = long_record.source_units[0].model_copy(
        update={
            "char_end": 95,
            "text": "超" * 95,
            "text_sha256": hashlib.sha256(("超" * 95).encode()).hexdigest(),
        }
    )

    content_hash = sha256_text("超" * 95)
    record = EvidenceRecord(
        evidence_id=stable_evidence_id("version-1", (source,), content_hash),
        document_id="doc-1",
        document_version_id="version-1",
        section_id="section-1",
        section_path=("搜索",),
        evidence_type="paragraph",
        source_mode="native",
        text="超" * 95,
        content_sha256=content_hash,
        normalized_sha256=content_hash,
        source_units=(source,),
    )
    long_artifact = artifact.model_copy(update={"records": (record,)})
    chunks = ParentChildChunker(_profile(), CharacterTokenizer()).build(long_artifact)
    children = [chunk for chunk in chunks.chunks if chunk.kind == "child"]

    assert len(children) == 3
    assert all(child.token_count <= 40 for child in children)
    assert all("ATOMIC_TOKEN_SPLIT" in child.warning_codes for child in children)
