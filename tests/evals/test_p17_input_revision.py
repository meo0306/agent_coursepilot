from __future__ import annotations

import hashlib
import json
from pathlib import Path

from coursepilot.evals.formal_schemas import CPDS8P17Dataset, SYSDS1P17Dataset
from evaluation.p10_schemas import P17SecurityQualificationDataset

ROOT = Path("datasets/coursepilot_eval/v1")
SECURITY_ROOT = Path("datasets/courserag_eval/releases/p17_security")
R1_INTEGRATION = "01b7549801efad637b4da39c271fe932c2ae44104ab73f3c618add0dfdac7b78"
R1_SECURITY = "f230655e5ed60c9462401e0824b6a3ec4e302b275faf16460ce61a50fd54ad8b"
R2_INTEGRATION = "7e613ea920077cf0c811ac36c4867df6901c915340f17a330c4d7018d29fae54"
R2_SECURITY = "be1f7a235b5c40e55b8b6814b78f8759d17b4987dfcbe0175af3ab099f869b8b"


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def test_p17_r2_distributions_and_real_variants() -> None:
    faults = CPDS8P17Dataset.model_validate_json(
        (ROOT / "candidates/cp_ds8/p17_fault_security_r2.json").read_text(encoding="utf-8")
    )
    journeys = SYSDS1P17Dataset.model_validate_json(
        (ROOT / "candidates/sys_ds1/p17_system_journeys_r2.json").read_text(encoding="utf-8")
    )
    assert len(faults.cases) == 30
    assert sum(len(case.variants) for case in faults.cases) == 34
    assert len(journeys.cases) == 8
    for case in faults.cases:
        injections = {variant.injection for variant in case.variants}
        assert len(injections) == len(case.variants)


def test_p17_r2_post_commit_side_effects_and_journey_versions() -> None:
    faults = CPDS8P17Dataset.model_validate_json(
        (ROOT / "candidates/cp_ds8/p17_fault_security_r2.json").read_text(encoding="utf-8")
    )
    by_id = {case.record_id: case for case in faults.cases}
    for record_id in ["p17-ds8-15", "p17-ds8-18", "p17-ds8-19", "p17-ds8-20"]:
        assert by_id[record_id].variants[0].expected_side_effect_count == 1
        assert (
            "duplicate side-effect count remains zero"
            in by_id[record_id].variants[0].postconditions
        )
    journeys = SYSDS1P17Dataset.model_validate_json(
        (ROOT / "candidates/sys_ds1/p17_system_journeys_r2.json").read_text(encoding="utf-8")
    )
    journey_by_id = {case.record_id: case for case in journeys.cases}
    assert "idx-v1→idx-v2" in journey_by_id["p17-sys-ds1-04"].steps[3].version_transition
    assert journey_by_id["p17-sys-ds1-06"].steps[-1].expected_state == "needs_review"
    assert journey_by_id["p17-sys-ds1-08"].steps[1].expected_side_effect_count == 1


def test_p17_r2_security_is_literal_balanced_and_unique() -> None:
    dataset = P17SecurityQualificationDataset.model_validate_json(
        (SECURITY_ROOT / "qualification_dev_candidate_r2.json").read_text(encoding="utf-8")
    )
    malicious = [case for case in dataset.cases if case.label == "malicious"]
    benign = [case for case in dataset.cases if case.label == "benign"]
    assert len(malicious) == len(benign) == 60
    assert sum(case.obfuscation_modifier is not None for case in malicious) == 24
    assert all(all(span in case.text for span in case.key_spans) for case in malicious)
    assert len({(case.language, case.input_surface, case.text) for case in benign}) == 60


def test_p17_r2_carries_forward_approved_records_and_reviews_only_delta() -> None:
    integration_review = _load(
        Path("storage_eval/p17_integration_review") / R1_INTEGRATION / "p17_integration_review.json"
    )
    security_review = _load(
        Path("storage_eval/p17_security_review") / R1_SECURITY / "p17_security_review.json"
    )
    f1 = _load(ROOT / "candidates/cp_ds8/p17_fault_security_r1.json")
    f2 = _load(ROOT / "candidates/cp_ds8/p17_fault_security_r2.json")
    j1 = _load(ROOT / "candidates/sys_ds1/p17_system_journeys_r1.json")
    j2 = _load(ROOT / "candidates/sys_ds1/p17_system_journeys_r2.json")
    s1 = _load(SECURITY_ROOT / "qualification_dev_candidate_r1.json")
    s2 = _load(SECURITY_ROOT / "qualification_dev_candidate_r2.json")
    old_i = {item["record_id"]: item for item in f1["cases"] + j1["cases"]}
    new_i = {item["record_id"]: item for item in f2["cases"] + j2["cases"]}
    old_s = {item["record_id"]: item for item in s1["cases"]}
    new_s = {item["record_id"]: item for item in s2["cases"]}
    approved_i = {
        item["record_id"] for item in integration_review["records"] if item["decision"] == "approve"
    }
    approved_s = {
        item["record_id"] for item in security_review["records"] if item["decision"] == "approve"
    }
    assert all(_digest(old_i[key]) == _digest(new_i[key]) for key in approved_i)
    assert all(_digest(old_s[key]) == _digest(new_s[key]) for key in approved_s)
    integration_template = _load(
        Path("storage_eval/p17_integration_review")
        / R2_INTEGRATION
        / "p17_integration_r2_review_template.json"
    )
    security_template = _load(
        Path("storage_eval/p17_security_review")
        / R2_SECURITY
        / "p17_security_r2_review_template.json"
    )
    assert len(integration_template["records"]) == 20
    assert len(security_template["records"]) == 91
