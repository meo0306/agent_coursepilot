from __future__ import annotations

import json
from pathlib import Path

from evaluation.p16_ppt_review import build_review_package


def test_p16_review_package_is_rebuilt_from_closure_report(tmp_path: Path) -> None:
    source = Path("storage_eval/p16_provider_pilot_r3/report.json")
    from evaluation.p16_closure import run

    run(output_dir=tmp_path, repository_root=Path("."), r3_report=source)
    result = build_review_package(closure_report=tmp_path / "report.json", output_dir=tmp_path)
    assert result["record_count"] == 46
    payload = json.loads(
        (tmp_path / "review/review_decisions_template.json").read_text(encoding="utf-8")
    )
    assert all(item["slide_status"] == "" for item in payload["records"])
    assert all(item["edit_burden"] is None for item in payload["records"])
    assert all(
        set(item["rubric_scores"]) == {f"P-H{i}" for i in range(1, 11)}
        for item in payload["records"]
    )
    assert all(item["title"] for item in payload["records"])
    previews = [item["preview_path"] for item in payload["records"] if item["preview_path"]]
    assert all(item.startswith("rendered_pages/") for item in previews)
    assert all((tmp_path / "review" / item).is_file() for item in previews)

    html = (tmp_path / "review/index.html").read_text(encoding="utf-8")
    assert "../rendered_pages/" not in html
    assert "img.src=record.preview_path" in html
    assert "P-H10':'视觉可用性" in html
    assert "Speaker Notes" in html
    assert "校验并下载决策 JSON" in html
    assert "reviewer_notes" in html
