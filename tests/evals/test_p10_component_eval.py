import json
from pathlib import Path

from evaluation.p10_component_eval import run_component_dev
from evaluation.p10_schemas import P10ComponentSplitManifest

ROOT = Path(__file__).resolve().parents[2]


def test_component_dev_is_deterministic_and_test_closed(tmp_path: Path) -> None:
    first = run_component_dev(ROOT, tmp_path / "first.json")
    second = run_component_dev(ROOT, tmp_path / "second.json")

    assert first.read_bytes() == second.read_bytes()
    report = json.loads(first.read_text(encoding="utf-8"))
    assert report["status"] == "passed"
    assert report["test_access"] is False
    assert report["test_ids_resolved"] == 0
    assert report["provider_calls"] == 0
    assert report["fallback_count"] == 0
    assert report["ds6"]["case_count"] == 5
    assert report["ds6"]["judgment_count"] == 15
    assert report["ds6"]["success_rate"] == 1.0
    assert report["ds7"]["case_count"] == 7
    assert report["ds7"]["change_coverage"] == 1.0
    assert report["ds7"]["reused_artifact_ratio"] == 1.0
    assert report["security"]["case_count"] == 10
    assert report["security"]["failed_count"] == 0

    splits = P10ComponentSplitManifest.model_validate_json(
        (ROOT / "datasets/courserag_eval/v1/provenance/p10_component_splits.json").read_text(
            encoding="utf-8"
        )
    )
    serialized = first.read_text(encoding="utf-8")
    assert all(
        test_id not in serialized
        for component in splits.components
        for test_id in component.test_ids
    )
