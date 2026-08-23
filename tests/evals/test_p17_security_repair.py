from __future__ import annotations

import hashlib
import json
from pathlib import Path

from courserag.security.ensemble import load_multi_axis_profile
from evaluation.p10_schemas import P17SecurityQualificationDataset

PROTOCOL = Path("resources/security_profiles/p17_scope_aware_qualification_protocol_r2.json")
PROFILE = Path("resources/security_profiles/p17_scope_aware_candidate_r2.json")
DATASET = Path("datasets/courserag_eval/releases/p17_security/approved/qualification_dev.json")
R2_REPORT = Path("storage_eval/p17_security/qualification_dev_report_r2.json")
R2_REPORT_SHA256 = "83463c48d7f051d1fcc042a35b90911a80cc12b45853b25599787157fb1ac387"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_r2_protocol_preserves_approved_dev_and_binds_implementation() -> None:
    protocol = json.loads(PROTOCOL.read_text(encoding="utf-8"))
    assert protocol["qualification_dev_sha256"] == _sha256(DATASET)
    assert protocol["approved_dataset_preserved_without_modification"] is True
    assert protocol["profile_sha256"] == _sha256(PROFILE)
    assert protocol["run_policy"]["qualification_dev_runs"] == 1
    assert protocol["run_policy"]["blind_runs"] == 0
    assert protocol["run_policy"]["runtime_network_required"] is False
    for path, expected in protocol["code_sha256"].items():
        assert _sha256(Path(path)) == expected


def test_r2_profile_uses_structured_v2_and_hikma_as_corroboration() -> None:
    protocol = json.loads(PROTOCOL.read_text(encoding="utf-8"))
    profile = load_multi_axis_profile(PROFILE)
    assert profile.sha256 == protocol["profile_canonical_sha256"]
    assert {
        axis.detector_id for axis in profile.axes if axis.axis_id != "general_untrusted_instruction"
    } == {"courserag/structured-capability-axes@v2"}
    assert protocol["decision_contract"]["semantic_model_role"] == "corroboration_only"
    assert protocol["decision_contract"]["authorization_role"] == "none"


def test_approved_dev_remains_valid_and_r2_qualification_is_consumed_once() -> None:
    dataset = P17SecurityQualificationDataset.model_validate_json(
        DATASET.read_text(encoding="utf-8")
    )
    assert len(dataset.cases) == 120
    assert sum(case.language == "zh" for case in dataset.cases) == 60
    assert all("ÔÚ" not in case.text for case in dataset.cases)

    report = json.loads(R2_REPORT.read_text(encoding="utf-8"))
    assert _sha256(R2_REPORT) == R2_REPORT_SHA256
    assert report["status"] == "passed"
    assert report["protocol_sha256"] == _sha256(PROTOCOL)
    assert report["dataset_sha256"] == _sha256(DATASET)
    assert report["record_count"] == 120
    assert report["blind_access"] is False
    assert report["test_access"] is False
    assert report["runtime_network"] is False
    assert report["external_provider_calls"] == 0
    assert report["fallbacks"] == 0


def test_v1_failure_is_preserved_and_not_overwritten() -> None:
    disposition = json.loads(
        Path("storage_eval/p17_security/v1_candidate_disposition.json").read_text(encoding="utf-8")
    )
    report_path = Path("storage_eval/p17_security/qualification_dev_report_v1.json")
    assert disposition["status"] == "rejected_low_recall"
    assert disposition["qualification_report_sha256"] == _sha256(report_path)
    assert disposition["blind_access"] is False
