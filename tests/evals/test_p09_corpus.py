from pathlib import Path

from evaluation.p09_corpus import load_p09_runtime_corpus


def test_p09_runtime_corpus_keeps_system_evidence_separate_from_gold() -> None:
    root = Path(__file__).resolve().parents[2]
    corpus = load_p09_runtime_corpus(root)
    candidates = [value for course in corpus.candidates_by_course.values() for value in course]
    assert len(candidates) == 1327
    assert corpus.evidence_by_id
    assert corpus.gold_by_system_evidence
    assert all(
        evidence_id in corpus.evidence_by_id
        for candidate in candidates
        for evidence_id in candidate.evidence_ids
    )
    assert not any(
        evidence_id.startswith("gold-")
        for candidate in candidates
        for evidence_id in candidate.evidence_ids
    )
