from __future__ import annotations

import json
import os
import subprocess
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

import fitz
import pytest

from evaluation.io import atomic_write_json
from evaluation.p10_3_security_approval import approve_dev_candidate
from evaluation.p10_3_security_data import (
    P103BlindCommitment,
    P103ReviewDecision,
    P103ReviewPass,
    P103SecurityDevCandidate,
    generate_dev_candidate,
    sha256_file,
)
from evaluation.p10_3_security_review import write_review_package


def test_p10_3_candidate_has_independent_balanced_distribution() -> None:
    candidate = generate_dev_candidate()
    assert len(candidate.cases) == 120
    assert not candidate.p10_2_case_ids_reused
    assert not candidate.test_content_included
    assert sum(case.expected_marked for case in candidate.cases) == 60
    assert sum(not case.expected_marked for case in candidate.cases) == 60
    positives = Counter(
        (case.family, case.language) for case in candidate.cases if case.expected_marked
    )
    assert set(positives.values()) == {6}
    assert all(case.record_id.startswith("p10-3-") for case in candidate.cases)


def test_p10_3_candidate_round_trip_is_deterministic() -> None:
    first = generate_dev_candidate()
    second = P103SecurityDevCandidate.model_validate_json(first.model_dump_json())
    assert first == second
    assert json.loads(first.model_dump_json())["test_content_included"] is False


def test_p10_3_blind_commitment_contains_no_content() -> None:
    commitment = P103BlindCommitment()
    payload = commitment.model_dump(mode="json")
    assert payload["status"] == "awaiting_independent_construction"
    assert payload["bundle_sha256"] is None
    assert payload["content_visible_to_implementation"] is False
    assert "cases" not in payload


def test_p10_3_review_package_has_working_download_script(tmp_path: Path) -> None:
    candidate_path = tmp_path / "candidate.json"
    candidate_path.write_text(generate_dev_candidate().model_dump_json(indent=2), encoding="utf-8")
    review_path = write_review_package(candidate_path, tmp_path / "review.html", pass_number=1)
    rendered = review_path.read_text(encoding="utf-8")
    assert "校验并下载决策 JSON" in rendered
    assert "addEventListener('click'" in rendered
    assert "new Blob" in rendered
    assert "link.click()" in rendered
    assert "p10_3_review_pass_${identity.pass_number}.json" in rendered
    assert "textContent=' 已下载';" in rendered
    assert "JSON.stringify(result,null,2)+'\\n'" in rendered


def test_p10_3_review_export_javascript_executes_in_browser(tmp_path: Path) -> None:
    if os.environ.get("COURSEPILOT_RUN_REVIEW_BROWSER_SMOKE") != "1":
        pytest.skip("set COURSEPILOT_RUN_REVIEW_BROWSER_SMOKE=1 for browser export smoke")
    browser_candidates = (
        Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
        Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
        Path(r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"),
    )
    browser = next((path for path in browser_candidates if path.is_file()), None)
    if browser is None:
        pytest.skip("Chromium browser is unavailable for review-export smoke")
    candidate_path = tmp_path / "candidate.json"
    candidate_path.write_text(generate_dev_candidate().model_dump_json(indent=2), encoding="utf-8")
    review_path = write_review_package(candidate_path, tmp_path / "review.html", pass_number=1)
    output_pdf = tmp_path / "review-export-self-test.pdf"
    subprocess.run(
        (
            str(browser),
            "--headless=new",
            "--disable-gpu",
            "--no-sandbox",
            "--no-first-run",
            "--disable-default-apps",
            f"--user-data-dir={tmp_path / 'browser-profile'}",
            "--print-to-pdf-no-header",
            f"--print-to-pdf={output_pdf}",
            review_path.as_uri() + "?export-self-test=1",
        ),
        check=True,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
    )
    with fitz.open(output_pdf) as document:
        rendered_text = "\n".join(page.get_text() for page in document)
    assert "EXPORT_SELF_TEST_PASSED" in rendered_text


def test_p10_3_approval_requires_two_complete_passing_reviews(tmp_path: Path) -> None:
    candidate = generate_dev_candidate()
    dataset_path = tmp_path / "candidate.json"
    atomic_write_json(dataset_path, candidate.model_dump(mode="json"))
    reviews = []
    for pass_number in (1, 2):
        review_path = tmp_path / f"review-{pass_number}.json"
        atomic_write_json(
            review_path,
            P103ReviewPass(
                dataset_sha256=sha256_file(dataset_path),
                pass_number=pass_number,
                reviewer="course_owner",
                reviewed_at=datetime.now(UTC),
                decisions=tuple(
                    P103ReviewDecision(record_id=case.record_id, decision="pass")
                    for case in candidate.cases
                ),
            ).model_dump(mode="json"),
        )
        reviews.append(review_path)
    approval = approve_dev_candidate(
        dataset_path=dataset_path,
        first_review_path=reviews[0],
        second_review_path=reviews[1],
        approval_path=tmp_path / "approval.json",
        expected_dataset_sha256=sha256_file(dataset_path),
        owner_approved=True,
    )
    assert approval.is_file()


def test_p10_3_approval_rejects_returned_case(tmp_path: Path) -> None:
    candidate = generate_dev_candidate()
    dataset_path = tmp_path / "candidate.json"
    atomic_write_json(dataset_path, candidate.model_dump(mode="json"))
    review_paths = []
    for pass_number in (1, 2):
        review_path = tmp_path / f"review-{pass_number}.json"
        decisions = [
            P103ReviewDecision(record_id=case.record_id, decision="pass")
            for case in candidate.cases
        ]
        if pass_number == 2:
            decisions[0] = P103ReviewDecision(
                record_id=candidate.cases[0].record_id, decision="return"
            )
        atomic_write_json(
            review_path,
            P103ReviewPass(
                dataset_sha256=sha256_file(dataset_path),
                pass_number=pass_number,
                reviewer="course_owner",
                reviewed_at=datetime.now(UTC),
                decisions=tuple(decisions),
            ).model_dump(mode="json"),
        )
        review_paths.append(review_path)
    with pytest.raises(ValueError, match="returned cases"):
        approve_dev_candidate(
            dataset_path=dataset_path,
            first_review_path=review_paths[0],
            second_review_path=review_paths[1],
            approval_path=tmp_path / "approval.json",
            expected_dataset_sha256=sha256_file(dataset_path),
            owner_approved=True,
        )
