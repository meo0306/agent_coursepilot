from __future__ import annotations

from pathlib import Path

from courserag.evals.schemas import DS3KnowledgePointDataset
from evaluation.p07_split_revision import (
    APPROVED_DS3,
    PROTOCOL_CANDIDATE,
    REVISED_SPLIT,
    P07EvaluationProtocolCandidate,
    _mixed_scopes,
    build_section_isolated_split,
    generate_protocol_revision,
)

ROOT = Path(__file__).resolve().parents[2]


def test_revised_split_is_scope_and_family_isolated() -> None:
    gold = DS3KnowledgePointDataset.model_validate_json(
        (ROOT / APPROVED_DS3).read_text(encoding="utf-8")
    )

    revised = build_section_isolated_split(gold)

    assert revised.dataset_version == "p07-r2"
    assert not _mixed_scopes(gold, revised)
    assert set(revised.calibration_ids).isdisjoint(revised.holdout_ids)
    assert len(revised.calibration_ids) + len(revised.holdout_ids) == 107
    assert 0.6 <= revised.actual_calibration_ratio <= 0.8


def test_protocol_generation_preserves_approved_gold_and_old_split() -> None:
    old_gold_hash = (ROOT / APPROVED_DS3).read_bytes()
    old_split_hash = (
        ROOT / "datasets/courserag_eval/v1/provenance/ds3_p07_split.json"
    ).read_bytes()

    first = generate_protocol_revision(ROOT)
    second = generate_protocol_revision(ROOT)

    assert first == second
    assert (
        P07EvaluationProtocolCandidate.model_validate_json(
            (ROOT / PROTOCOL_CANDIDATE).read_text(encoding="utf-8")
        )
        == first
    )
    assert (ROOT / REVISED_SPLIT).is_file()
    assert (ROOT / APPROVED_DS3).read_bytes() == old_gold_hash
    assert (
        ROOT / "datasets/courserag_eval/v1/provenance/ds3_p07_split.json"
    ).read_bytes() == old_split_hash
