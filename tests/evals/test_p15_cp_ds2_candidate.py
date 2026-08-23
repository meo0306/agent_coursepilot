import hashlib
import json
from pathlib import Path

from coursepilot.evals.formal_schemas import CPDS2P15PilotDataset, P15FixtureBundle
from evaluation.p15_cp_ds2_data import generate

ROOT = Path(__file__).parents[2]


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_p15_candidate_has_fixed_cases_targets_and_negative_contracts():
    candidate = json.loads(
        (ROOT / "datasets/coursepilot_eval/v1/candidates/cp_ds2/p15_exam_pilot_r1.json").read_text(
            encoding="utf-8"
        )
    )
    fixtures = json.loads(
        (ROOT / "datasets/coursepilot_eval/v1/provenance/p15_exam_fixtures_r1.json").read_text(
            encoding="utf-8"
        )
    )
    dataset = CPDS2P15PilotDataset.model_validate(candidate)
    fixture_bundle = P15FixtureBundle.model_validate(fixtures)
    assert len(dataset.cases) == 3
    assert len(dataset.targets) == 26
    assert [sum(case.blueprint.question_counts.values()) for case in dataset.cases] == [8, 12, 25]
    assert [case.blueprint.required_total_score for case in dataset.cases] == [50, 50, 100]
    assert len(fixture_bundle.context_fixtures) == 3
    assert fixture_bundle.insufficient_evidence_case.provider_calls_allowed == 0
    assert fixture_bundle.constraint_conflict_case.provider_calls_allowed == 0
    assert all(target.primary_evidence.course_id == target.course_id for target in dataset.targets)
    assert all(target.knowledge_point.course_id == target.course_id for target in dataset.targets)


def test_p15_generation_is_byte_stable():
    first = generate(ROOT)
    pilot = ROOT / "datasets/coursepilot_eval/v1/candidates/cp_ds2/p15_exam_pilot_r1.json"
    fixtures = ROOT / "datasets/coursepilot_eval/v1/provenance/p15_exam_fixtures_r1.json"
    hashes = (_sha(pilot), _sha(fixtures))
    second = generate(ROOT)
    assert first == second
    assert hashes == (_sha(pilot), _sha(fixtures))


def test_p15_review_bundle_has_export_and_manual_fallback():
    manifest = json.loads(
        (
            ROOT / "datasets/coursepilot_eval/v1/provenance/p15_cp_ds2_bundle_manifest.json"
        ).read_text(encoding="utf-8")
    )
    review_root = ROOT / "storage_eval/cpds2_p15_review" / manifest["bundle_sha256"]
    for name in (
        "index.html",
        "second_review.html",
        "manual_review_template_first.json",
        "manual_review_template_second.json",
    ):
        assert (review_root / name).is_file()
    html = (review_root / "index.html").read_text(encoding="utf-8")
    assert "导出本轮审核 JSON" in html
    assert "Required Claims" in html
    assert "Hard Negative" in html
