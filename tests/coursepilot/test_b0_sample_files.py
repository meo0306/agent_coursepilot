import os
from pathlib import Path

import pytest

from coursepilot.evals.run_b0_smoke import run_b0_smoke


@pytest.mark.b0_sample_files
def test_owner_supplied_docx_and_pdf_complete_b0_smoke(tmp_path):
    if os.getenv("COURSEPILOT_RUN_B0_SAMPLE_SMOKE") != "1":
        pytest.skip("set COURSEPILOT_RUN_B0_SAMPLE_SMOKE=1 for the gated local B0 smoke")

    report = run_b0_smoke(
        repository_root=Path.cwd(),
        sample_dir=Path("data/sample_files"),
        output_path=tmp_path / "b0-report.json",
        baseline_commit="test-baseline",
    )

    assert len(report["documents"]) == 2
    assert {item["input"]["media_type"] for item in report["documents"]} == {
        "application/pdf",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    }
    assert all(item["parse_status"] == "built" for item in report["documents"])
    assert all(item["chunk_count"] > 0 for item in report["documents"])
    assert all(item["probe"]["course_scope_passed"] for item in report["documents"])
    assert all(item["probe"]["document_scope_passed"] for item in report["documents"])
    assert report["quality_claims"]["gold_used"] is False
    assert report["workflows"]["lesson"]["exported"] is True
    assert report["workflows"]["ppt"]["exported"] is True
    assert all(
        item["write_back_status"]
        in {"written", "requires_fragment_selection", "requires_evidence_migration"}
        for item in report["workflows"]["review_write_backs"]
    )
