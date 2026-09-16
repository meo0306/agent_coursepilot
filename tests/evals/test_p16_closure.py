from __future__ import annotations

import json
from pathlib import Path

from evaluation.p16_closure import run


def test_p16_closure_reexports_cached_provider_artifacts_without_calls(tmp_path: Path) -> None:
    result = run(
        repository_root=Path("."),
        output_dir=tmp_path,
        r3_report=Path("storage_eval/p16_provider_pilot_r3/report.json"),
    )
    assert result["provider_requests"] == 0
    assert result["cp_ds7"]["all_passed"] is True
    assert [item["artifact"]["template_id"] for item in result["cases"]] == [
        "ppt_standard_lecture_v2",
        "ppt_concept_explanation_v2",
        "ppt_case_seminar_v2",
    ]
    review = json.loads((tmp_path / "review/review_package.json").read_text(encoding="utf-8"))
    assert len(review["records"]) == 46
    assert review["status"] == "pending_owner_review"
    assert "download" in (tmp_path / "review/index.html").read_text(encoding="utf-8")
