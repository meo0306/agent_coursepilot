import json
from pathlib import Path

from coursepilot.domain.common import canonical_sha256
from evaluation.p14_lesson_review import RUBRIC, _review_html, finalize_decisions


def test_p14_review_html_has_autosave_validation_and_blob_download() -> None:
    records = [{"blind_artifact_id": "lesson-review-01", "artifact": {"title": "A"}}]
    template = {
        "schema_version": "coursepilot.p14-human-review-decisions.v1",
        "source_report_sha256": "0" * 64,
        "decisions": [
            {
                "blind_artifact_id": "lesson-review-01",
                "rubric_scores": {key: None for key in RUBRIC},
                "edit_burden": None,
                "critical_defect": None,
                "artifact_status": None,
                "notes": "",
            }
        ],
    }

    page = _review_html(records, template)

    assert "校验并下载决策 JSON" in page
    assert "localStorage.setItem" in page
    assert "new Blob" in page
    assert "URL.createObjectURL" in page
    assert "a.download='p14_lesson_review_decisions.json'" in page
    assert all(key in page for key in RUBRIC)
    embedded = page.split("const base=", 1)[1].split(";\nfunction collect", 1)[0]
    assert json.loads(embedded)["decisions"][0]["blind_artifact_id"] == "lesson-review-01"


def test_finalize_p14_owner_decisions_reports_nonblocking_quality_debt(
    tmp_path: Path,
) -> None:
    report = {"status": "completed", "budget": {"cost": 0.1}}
    automatic = {"hard_gates": {"grounding": True, "budget": True}}
    key = {
        "items": [
            {"blind_artifact_id": "a", "case_id": "case-1", "track": "cp_b0"},
            {"blind_artifact_id": "b", "case_id": "case-1", "track": "p14"},
        ]
    }

    def decision(artifact_id, score, burden):
        return {
            "blind_artifact_id": artifact_id,
            "rubric_scores": {rubric: score for rubric in RUBRIC},
            "edit_burden": burden,
            "critical_defect": False,
            "artifact_status": "minor_edit",
            "notes": "",
        }

    decisions = {
        "schema_version": "coursepilot.p14-human-review-decisions.v1",
        "source_report_sha256": canonical_sha256(report),
        "decisions": [decision("a", 4, 1), decision("b", 3, 2)],
    }
    paths = {
        "report": tmp_path / "report.json",
        "automatic": tmp_path / "automatic.json",
        "key": tmp_path / "key.json",
        "decisions": tmp_path / "decisions.json",
        "output": tmp_path / "summary.json",
    }
    for name, payload in (
        ("report", report),
        ("automatic", automatic),
        ("key", key),
        ("decisions", decisions),
    ):
        paths[name].write_text(json.dumps(payload), encoding="utf-8")

    result = finalize_decisions(
        report_path=paths["report"],
        automatic_path=paths["automatic"],
        blinding_key_path=paths["key"],
        decisions_path=paths["decisions"],
        output_path=paths["output"],
    )

    assert result["hard_gates_passed"] is True
    assert result["phase_status"] == "completed_with_quality_debt"
    assert result["paired_results"][0]["rubric_mean_delta_p14_minus_cp_b0"] == -1
