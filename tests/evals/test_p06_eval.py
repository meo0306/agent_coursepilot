from __future__ import annotations

from pathlib import Path

from courserag.chunking.profile import load_chunk_profile
from courserag.chunking.tokenizer import LocalTokenizer
from courserag.domain.chunk import ChunkArtifact
from courserag.domain.evidence import EvidenceArtifact
from evaluation.p06_evidence_eval import _decode_case, _system_case
from tests.courserag.evidence.test_builder import _document


def test_p06_system_output_is_runtime_identified_and_reproducible() -> None:
    profile = load_chunk_profile(Path("resources/chunk_profiles/parent_child_v1.json"))
    tokenizer = LocalTokenizer(
        Path("deepseek_v3_tokenizer/deepseek_v3_tokenizer/tokenizer.json"),
        tokenizer_id=profile.tokenizer_id,
        expected_sha256=profile.tokenizer_sha256,
    )

    first = _system_case(_document(), profile, tokenizer)
    second = _system_case(_document(), profile, tokenizer)
    first_evidence, first_chunks, _ = _decode_case(first)
    second_evidence, second_chunks, _ = _decode_case(second)

    assert isinstance(first_evidence, EvidenceArtifact)
    assert isinstance(first_chunks, ChunkArtifact)
    assert first_evidence.content_sha256 == second_evidence.content_sha256
    assert first_chunks.content_sha256 == second_chunks.content_sha256
    assert all(record.evidence_id.startswith("ev1_") for record in first_evidence.records)
    assert all(not record.evidence_id.startswith("gold-") for record in first_evidence.records)


def test_product_p06_modules_do_not_import_gold_or_dataset_paths() -> None:
    roots = [
        Path("src/courserag/evidence"),
        Path("src/courserag/chunking"),
        Path("src/courserag/jobs/evidence.py"),
        Path("src/courserag/jobs/chunking.py"),
    ]
    files = [
        child for root in roots for child in ([root] if root.is_file() else root.rglob("*.py"))
    ]
    for path in files:
        text = path.read_text(encoding="utf-8")
        assert "courserag.evals" not in text
        assert "datasets/" not in text
        assert "gold-ev-" not in text
