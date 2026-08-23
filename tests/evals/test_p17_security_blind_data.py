from __future__ import annotations

import json
from pathlib import Path

import pytest

from evaluation.p10_schemas import P17SecurityBlindDataset
from evaluation.p17_security_blind_data import build


def test_blind_candidate_has_frozen_distribution_and_label_free_second_review(
    tmp_path: Path,
) -> None:
    result = build(tmp_path / "blind")
    root = Path(result["output_root"])
    dataset = P17SecurityBlindDataset.model_validate_json(
        (root / "blind_candidate_r1.json").read_text(encoding="utf-8")
    )
    assert len(dataset.cases) == 48
    assert sum(case.label == "malicious" for case in dataset.cases) == 24
    assert sum(case.language == "zh" for case in dataset.cases) == 24
    assert all(case.historical_similarity == [] for case in dataset.cases)
    assert all(span in case.text for case in dataset.cases for span in case.key_spans)

    second = json.loads((root / "blind_second_review_r1.json").read_text(encoding="utf-8"))
    assert len(second["records"]) == 48
    assert all("proposed_label" not in record for record in second["records"])
    assert all("proposed_family" not in record for record in second["records"])
    assert all(record["decision_label"] is None for record in second["records"])
    assert result["blind_runs"] == 0
    assert result["external_provider_calls"] == 0


def test_blind_builder_refuses_to_overwrite_existing_package(tmp_path: Path) -> None:
    output = tmp_path / "blind"
    build(output)
    with pytest.raises(FileExistsError):
        build(output)


def test_blind_builder_does_not_import_or_execute_security_detector() -> None:
    source = Path("src/evaluation/p17_security_blind_data.py").read_text(encoding="utf-8")
    assert "courserag.security" not in source
    assert "p17_security_eval" not in source
