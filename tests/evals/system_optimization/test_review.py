import json
import shutil
from collections import Counter
from pathlib import Path

from evaluation.system_optimization.review import build_review_packages

ROOT = Path("datasets/system_optimization/v1")


def test_review_package_has_six_repeat_blind_reviews(tmp_path: Path) -> None:
    candidate_dir = tmp_path / "candidates"
    candidate_dir.mkdir()
    for filename in ("dev_cases.json", "failure_replays.json", "historical_baseline.json"):
        shutil.copy(ROOT / "candidates" / filename, candidate_dir / filename)

    paths = build_review_packages(tmp_path)
    package = json.loads(Path(paths["artifact_package"]).read_text(encoding="utf-8"))
    key = json.loads(Path(paths["artifact_key"]).read_text(encoding="utf-8"))
    groups = Counter(
        item["repeat_group_id"] for item in key["records"] if item["repeat_group_id"] is not None
    )

    assert package["review_units"] == 33
    assert package["repeat_reviews"] == 6
    assert len(groups) == 6
    assert set(groups.values()) == {2}
    assert all("case_id" not in item for item in package["records"])
    assert "case_html" not in paths
    assert "artifact_html" not in paths


def test_review_json_uses_integer_zero_to_four_scale() -> None:
    payload = json.loads(
        (ROOT / "candidates/review/artifact_review_decisions_r2_template.json").read_text(
            encoding="utf-8"
        )
    )
    assert set(payload["edit_burden_scale"]) == {"0", "1", "2", "3", "4"}
