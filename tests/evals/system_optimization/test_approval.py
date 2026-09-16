import json
import shutil
from datetime import UTC, datetime
from pathlib import Path

from evaluation.contracts import ReviewStatus
from evaluation.system_optimization.approval import approve_dev_data
from evaluation.system_optimization.dev_loader import load_approved, load_candidate

ROOT = Path("datasets/system_optimization/v1")


def test_approval_is_complete_hash_bound_and_idempotent(tmp_path: Path) -> None:
    candidate_dir = tmp_path / "candidates"
    review_dir = candidate_dir / "review"
    review_dir.mkdir(parents=True)
    for filename in ("dev_cases.json", "failure_replays.json", "historical_baseline.json"):
        shutil.copy(ROOT / "candidates" / filename, candidate_dir / filename)
    decisions = ROOT / "candidates/review/case_review_decisions_r2_template.json"
    shutil.copy(decisions, review_dir / decisions.name)

    kwargs = {
        "root": tmp_path,
        "decisions_path": review_dir / decisions.name,
        "failure_reviewer_id": "course_owner",
        "failure_reviewed_at": datetime(2026, 8, 31, 2, 48, 14, tzinfo=UTC),
    }
    first = approve_dev_data(**kwargs)
    second = approve_dev_data(**kwargs)
    approved = load_approved(tmp_path)
    candidate = load_candidate(tmp_path)
    reviews = (tmp_path / "approved/review_log.jsonl").read_text(encoding="utf-8").splitlines()

    assert first == second
    assert first["review_entries"] == 34
    assert len(reviews) == 34
    assert all(item.review_status is ReviewStatus.APPROVED for item in approved.cases.records)
    assert all(item.approval is not None for item in approved.cases.records)
    assert all(item.review_status is ReviewStatus.CANDIDATE for item in candidate.cases.records)
    assert json.loads((tmp_path / "approved/dev_cases.json").read_text(encoding="utf-8"))
