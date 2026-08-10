import json
from pathlib import Path

from evaluation.p09_gate_repair_analysis import write_shadow_report

ROOT = Path(__file__).resolve().parents[2]


def test_p09_shadow_report_is_dev_only_and_preserves_non_citation_projection(
    tmp_path: Path,
) -> None:
    output = tmp_path / "shadow.json"
    digest = write_shadow_report(ROOT, output)
    payload = json.loads(output.read_text(encoding="utf-8"))

    assert len(digest) == 64
    assert payload["test_access"] is False
    assert payload["provider_calls"] == {"cohere": 0, "deepseek": 0}
    assert payload["freeze_eligible"] is False
    assert payload["status"] == "invalid_for_freeze_gold_side_candidate_filter"
    assert payload["checks"]["formal_claim_citation_review_available"] is False
    assert payload["checks"]["non_citation_projection_unchanged"] is True
    assert payload["changed_claim_count"] > 0
