from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from courserag.evals.p08_metrics import RetrievalEvalHit, retrieval_case_metrics
from courserag.evals.schemas import DS5RetrievalQADataset, RetrievalQACase
from evaluation.p08_corpus import load_p08_child_corpus
from evaluation.p08_retrieval_eval import run_p08_dev, write_freeze_candidate
from evaluation.p08_systems import P08SystemResult
from evaluation.runner import RunConfigurationMismatch


class FakeSystem:
    def __init__(self, label: str = "fake-b4") -> None:
        self.label = label

    def search(self, case: RetrievalQACase) -> P08SystemResult:
        positive = next(
            (item for item, relevance in case.graded_relevance.items() if relevance > 0),
            case.hard_negative_evidence_ids[0],
        )
        return P08SystemResult(
            hits=[
                RetrievalEvalHit(
                    chunk_id=f"chunk-{case.record_id}", evidence_ids=[positive], score=0.8
                )
            ],
            stage_latency_ms={"dense": 1, "fusion": 1},
        )


def _first_answerable() -> RetrievalQACase:
    dataset = DS5RetrievalQADataset.model_validate_json(
        Path("datasets/courserag_eval/v1/approved/ds5/p08_retrieval.json").read_text(
            encoding="utf-8"
        )
    )
    return next(item for item in dataset.cases if item.answerable)


def test_non_generic_retrieval_metrics_use_unique_evidence() -> None:
    case = _first_answerable()
    required = next(item for item, score in case.graded_relevance.items() if score == 2)
    hits = [
        RetrievalEvalHit(chunk_id="c1", evidence_ids=[required], score=1),
        RetrievalEvalHit(chunk_id="c2", evidence_ids=[required], score=0.9),
    ]
    result = retrieval_case_metrics(case, hits)
    assert result["hit@5"] == 1
    assert result["mrr@10"] == 1
    assert 0 <= result["ndcg@10"] <= 1


def test_p08_corpus_maps_chunks_back_to_approved_evidence() -> None:
    corpus = load_p08_child_corpus(Path.cwd())
    assert set(corpus) == {"course_ai_algorithms_systems", "course_ai_general_education"}
    assert all(item.text for items in corpus.values() for item in items)
    assert any(item.evidence_ids for items in corpus.values() for item in items)


def test_runner_is_dev_only_resumable_and_writes_freeze_candidate(tmp_path: Path) -> None:
    first = run_p08_dev(
        repository_root=Path.cwd(),
        output_dir=tmp_path / "run-1",
        run_id="p08-test-1",
        systems={"b4": FakeSystem()},
    )
    second = run_p08_dev(
        repository_root=Path.cwd(),
        output_dir=tmp_path / "run-2",
        run_id="p08-test-2",
        systems={"b4": FakeSystem()},
    )
    payload = json.loads(first.read_text(encoding="utf-8"))
    assert payload["report"]["case_count"] == 54
    assert payload["report"]["test_access"] is False
    assert len(payload["cases"]) == 54
    candidate = tmp_path / "freeze_candidate.json"
    sha256 = write_freeze_candidate([first, second], candidate)
    assert len(sha256) == 64
    assert json.loads(candidate.read_text(encoding="utf-8"))["default_profile_written"] is False

    with pytest.raises(RunConfigurationMismatch):
        run_p08_dev(
            repository_root=Path.cwd(),
            output_dir=tmp_path / "run-1",
            run_id="p08-test-1",
            systems={"changed": FakeSystem("changed")},
            resume=True,
        )


def test_owner_approved_default_profile_is_bound_to_exact_freeze_candidate() -> None:
    profile_path = Path("resources/retrieval_profiles/default_v1.json")
    profile = json.loads(profile_path.read_text(encoding="utf-8"))
    candidate_path = Path(profile["approval"]["freeze_candidate_path"])
    candidate_sha256 = hashlib.sha256(candidate_path.read_bytes()).hexdigest()
    candidate = json.loads(candidate_path.read_text(encoding="utf-8"))

    assert profile["status"] == "owner_approved"
    assert candidate_sha256 == profile["approval"]["freeze_candidate_sha256"]
    assert candidate_sha256 == ("5b5d973ebf70d32cc10fa0ad4103261eee745dc4604f9e9f1a693817d3c3c95f")
    assert profile["reranker"]["provider"] == "cohere"
    assert profile["reranker"]["model"] == "rerank-v4.0-pro"
    assert profile["reranker"]["rejection_threshold"] == 0.7502601
    assert (
        profile["evaluation_evidence"]["selected_system_result_sha256"]
        == (candidate["system_result_sha256"]["b5_cohere"])
    )
    assert profile["evaluation_evidence"]["run_report_sha256"] == candidate["report_sha256"]
    assert profile["runtime_activation"]["safe_provider_default"] == "disabled"
    for section, path_field, hash_field in (
        ("embedding", "profile_path", "profile_sha256"),
        ("sparse", "profile_path", "profile_sha256"),
        ("fusion", "profile_path", "profile_sha256"),
        ("reranker", "candidate_profile_path", "candidate_profile_sha256"),
    ):
        referenced = Path(profile[section][path_field])
        assert hashlib.sha256(referenced.read_bytes()).hexdigest() == profile[section][hash_field]
