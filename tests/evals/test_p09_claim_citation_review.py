import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from courserag.evals.schemas import (
    P09ClaimCitationPhase1Approval,
    P09ClaimCitationPhase1Decisions,
    P09ClaimCitationPhase1Package,
    P09ClaimCitationPhase2Decisions,
    P09ClaimCitationPhase2Package,
)
from evaluation.manifest import sha256_file
from evaluation.p09_claim_citation_review import (
    _require_hash,
    validate_phase1_decisions,
    validate_phase2_decisions,
    write_phase1_review_package,
    write_phase2_review_package,
)
from evaluation.p09_dev_loader import load_p09_dev_bundle

ROOT = Path(__file__).resolve().parents[2]


def test_phase1_review_pack_is_fixed_dev_only_blinded_and_reproducible(
    tmp_path: Path,
) -> None:
    first = write_phase1_review_package(ROOT, tmp_path / "first")
    second = write_phase1_review_package(ROOT, tmp_path / "second")
    package = P09ClaimCitationPhase1Package.model_validate_json(
        Path(first["package"]).read_text(encoding="utf-8")
    )
    manifest = json.loads(Path(first["manifest"]).read_text(encoding="utf-8"))
    bundle = load_p09_dev_bundle(ROOT / "datasets/courserag_eval/v1")
    main_ids = {
        case.qa.record_id for case in bundle.cases if case.qa.evaluation_stratum == "retrieval_main"
    }

    assert package.case_count == 54
    assert package.answered_case_count == 47
    assert package.abstained_case_count == 6
    assert package.failed_case_count == 1
    assert package.system_claim_count == 150
    assert package.citation_link_count == 150
    assert {case.case_id for case in package.cases} == main_ids
    assert package.test_access is False
    assert all(case.blinded_sample_id.startswith("p09-blind-") for case in package.cases)
    assert "gold_claims" not in Path(first["package"]).read_text(encoding="utf-8")
    assert manifest["provider_calls"] == {"cohere": 0, "deepseek": 0, "other": 0}
    assert manifest["counts"]["required_gold_claims_hidden_from_phase1"] == 117
    review_html = Path(first["review_index"]).read_text(encoding="utf-8")
    export_script = Path(first["recovery_export"]).read_text(encoding="utf-8")
    assert '<script src="recovery_export.js"></script>' in review_html
    assert "join('\\n')" in export_script
    assert "JSON.stringify(payload,null,2)+'\\n'" in export_script
    for key in (
        "package_sha256",
        "decision_template_sha256",
        "review_index_sha256",
        "recovery_export_sha256",
    ):
        assert first[key] == second[key]


def test_phase1_decisions_fail_closed_until_every_label_is_complete(tmp_path: Path) -> None:
    artifacts = write_phase1_review_package(ROOT, tmp_path / "review")
    draft = json.loads(Path(artifacts["decision_template"]).read_text(encoding="utf-8"))
    draft["review_status"] = "submitted"
    draft["reviewer_id"] = "course_owner"

    with pytest.raises(ValidationError, match="every Case review"):
        P09ClaimCitationPhase1Decisions.model_validate(draft)


def test_submitted_phase1_decisions_must_match_every_package_identity(tmp_path: Path) -> None:
    artifacts = write_phase1_review_package(ROOT, tmp_path / "review")
    draft_path = Path(artifacts["decision_template"])
    payload = json.loads(draft_path.read_text(encoding="utf-8"))
    package = P09ClaimCitationPhase1Package.model_validate_json(
        Path(artifacts["package"]).read_text(encoding="utf-8")
    )
    statuses = {case.case_id: case.answer_status for case in package.cases}
    payload["review_status"] = "submitted"
    payload["reviewer_id"] = "course_owner"
    for case in payload["cases"]:
        case["reviewed"] = True
        if statuses[case["case_id"]] == "answered":
            case["conciseness_pass"] = True
        for claim in case["claims"]:
            claim["label"] = "correct_supported"
            for citation in claim["citations"]:
                citation["supports_claim"] = True
    decisions_path = tmp_path / "phase1_decisions.json"
    decisions_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    result = validate_phase1_decisions(Path(artifacts["package"]), decisions_path)
    assert result["case_count"] == 54
    assert result["claim_count"] == 150
    assert result["citation_link_count"] == 150

    payload["cases"][0]["case_id"] = "tampered-case"
    decisions_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(ValueError, match="Case IDs"):
        validate_phase1_decisions(Path(artifacts["package"]), decisions_path)


def test_phase1_source_hash_guard_rejects_changed_input(tmp_path: Path) -> None:
    value = tmp_path / "input.json"
    value.write_text("{}\n", encoding="utf-8")

    with pytest.raises(ValueError, match="Hash mismatch"):
        _require_hash(value, "0" * 64)
    _require_hash(value, sha256_file(value))


def test_phase2_review_pack_binds_approved_phase1_and_gold_without_test_access(
    tmp_path: Path,
) -> None:
    first_dir = tmp_path / "first"
    second_dir = tmp_path / "second"
    for output in (first_dir, second_dir):
        phase1 = write_phase1_review_package(ROOT, output)
        source = ROOT / "storage_eval/p09_claim_citation_review/phase1_decisions.json"
        (output / "phase1_decisions.json").write_bytes(source.read_bytes())
        assert phase1["package_sha256"] == sha256_file(output / "phase1_package.json")
    first = write_phase2_review_package(ROOT, first_dir)
    second = write_phase2_review_package(ROOT, second_dir)
    approval = P09ClaimCitationPhase1Approval.model_validate_json(
        Path(first["phase1_approval"]).read_text(encoding="utf-8")
    )
    package = P09ClaimCitationPhase2Package.model_validate_json(
        Path(first["phase2_package"]).read_text(encoding="utf-8")
    )

    assert approval.decisions_sha256 == (
        "52e0044ecc702e3ecc0cc9c0b3045a0f5a1f4c0aeaa95dc86f37c0a7b50ec314"
    )
    assert approval.reviewer_id == "course_owner"
    assert package.case_count == 54
    assert package.system_claim_count == 150
    assert package.required_gold_claim_count == 117
    assert package.test_access is False
    bundle = load_p09_dev_bundle(ROOT / "datasets/courserag_eval/v1")
    main_ids = {
        case.qa.record_id for case in bundle.cases if case.qa.evaluation_stratum == "retrieval_main"
    }
    assert {case.case_id for case in package.cases} == main_ids
    assert all(
        support.exact_support_excerpt
        for case in package.cases
        for claim in case.required_gold_claims
        for support in claim.supports
    )
    review_html = Path(first["phase2_review_index"]).read_text(encoding="utf-8")
    export_script = Path(first["phase2_export"]).read_text(encoding="utf-8")
    assert '<script src="phase2_export.js"></script>' in review_html
    assert "join('\\n')" in export_script
    assert "JSON.stringify(payload,null,2)+'\\n'" in export_script
    for key in (
        "phase1_approval_sha256",
        "phase2_package_sha256",
        "phase2_decision_template_sha256",
        "phase2_review_index_sha256",
        "phase2_export_sha256",
        "phase2_manifest_sha256",
    ):
        assert first[key] == second[key]


def test_phase2_decisions_require_exact_identity_and_gold_complement(tmp_path: Path) -> None:
    output = tmp_path / "review"
    write_phase1_review_package(ROOT, output)
    source = ROOT / "storage_eval/p09_claim_citation_review/phase1_decisions.json"
    (output / "phase1_decisions.json").write_bytes(source.read_bytes())
    artifacts = write_phase2_review_package(ROOT, output)
    template_path = Path(artifacts["phase2_decision_template"])
    payload = json.loads(template_path.read_text(encoding="utf-8"))
    payload["review_status"] = "submitted"
    payload["reviewer_id"] = "course_owner"
    for case in payload["cases"]:
        case["reviewed"] = True
    decisions_path = output / "phase2_decisions.json"
    decisions_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    result = validate_phase2_decisions(Path(artifacts["phase2_package"]), decisions_path)
    assert result["case_count"] == 54
    assert result["mapping_count"] == 0
    assert result["missed_gold_claim_count"] == 117

    package = P09ClaimCitationPhase2Package.model_validate_json(
        Path(artifacts["phase2_package"]).read_text(encoding="utf-8")
    )
    eligible_case = next(
        case
        for case in package.cases
        if case.required_gold_claims
        and any(
            claim.phase1_label in {"correct_supported", "correct_but_uncited"}
            for claim in case.system_claims
        )
    )
    case_payload = next(
        item for item in payload["cases"] if item["case_id"] == eligible_case.case_id
    )
    case_payload["mappings"][0]["matched_gold_claim_ids"] = ["unknown-gold-claim"]
    decisions_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(ValueError, match="invalid Gold Claim IDs"):
        validate_phase2_decisions(Path(artifacts["phase2_package"]), decisions_path)


def test_phase2_submitted_decisions_require_every_case_review(tmp_path: Path) -> None:
    output = tmp_path / "review"
    write_phase1_review_package(ROOT, output)
    source = ROOT / "storage_eval/p09_claim_citation_review/phase1_decisions.json"
    (output / "phase1_decisions.json").write_bytes(source.read_bytes())
    artifacts = write_phase2_review_package(ROOT, output)
    payload = json.loads(Path(artifacts["phase2_decision_template"]).read_text(encoding="utf-8"))
    payload["review_status"] = "submitted"
    payload["reviewer_id"] = "course_owner"

    with pytest.raises(ValidationError, match="every Case review"):
        P09ClaimCitationPhase2Decisions.model_validate(payload)
