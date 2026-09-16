from pathlib import Path

import pytest

from evaluation.p17_security_blind_eval import (
    DEFAULT_PROFILE,
    DEFAULT_PROTOCOL,
    _validate_release,
)

PACKAGE = Path("storage_eval/p17_security_blind_candidate_r1")
BUNDLE_SHA256 = "469f556c05d5c54e3f18db1972b045d338e8fac20aabc7c518fcd0a682cddf4b"
APPROVAL_SHA256 = "83d00578c3c79cc8648f2333c195b74e0a737db86b895b421205d1f08f934f75"
BLIND_REPORT = Path("storage_eval/p17_security/blind_report_r1.json")
BLIND_REPORT_SHA256 = "a9c1004a4d1b3410dfead90093f2a7208ed65d7e2f4cb3250a65f62be6b335df"


def test_approved_blind_release_binds_exact_reviewed_candidate() -> None:
    dataset, authorization = _validate_release(
        PACKAGE,
        expected_bundle_sha256=BUNDLE_SHA256,
        expected_approval_candidate_sha256=APPROVAL_SHA256,
        profile_path=DEFAULT_PROFILE,
        protocol_path=DEFAULT_PROTOCOL,
    )
    assert dataset.name == "blind_candidate_r1.json"
    assert authorization.name == "blind_run_authorization_r1.json"


def test_single_blind_result_is_immutable_failed_release_evidence() -> None:
    import hashlib
    import json

    report = json.loads(BLIND_REPORT.read_text(encoding="utf-8"))
    assert hashlib.sha256(BLIND_REPORT.read_bytes()).hexdigest() == BLIND_REPORT_SHA256
    assert report["status"] == "failed"
    assert report["blind_run_number"] == 1
    assert report["post_blind_tuning_allowed"] is False
    assert report["runtime_network"] is False
    assert report["external_provider_calls"] == 0
    assert report["fallbacks"] == 0


def test_blind_release_rejects_unapproved_identity() -> None:
    with pytest.raises(ValueError, match="Bundle differs"):
        _validate_release(
            PACKAGE,
            expected_bundle_sha256="0" * 64,
            expected_approval_candidate_sha256=APPROVAL_SHA256,
            profile_path=DEFAULT_PROFILE,
            protocol_path=DEFAULT_PROTOCOL,
        )
