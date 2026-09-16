import hashlib
import json
from pathlib import Path

from coursepilot.models_gateway import GatewayMode, ModelGateway
from coursepilot.templates import TemplateRegistry
from evaluation.p11_schemas import P11FoundationApproval, P11FoundationCandidateDataset

ROOT = Path(__file__).resolve().parents[2]


def test_approved_foundation_contract_is_40_records_and_not_gold() -> None:
    approved = P11FoundationCandidateDataset.model_validate_json(
        (
            ROOT / "datasets/coursepilot_eval/v1/approved/work_packages/p11_foundation_input.json"
        ).read_text(encoding="utf-8")
    )
    approval = P11FoundationApproval.model_validate_json(
        (
            ROOT / "datasets/coursepilot_eval/v1/provenance/p11_foundation_input_approval.json"
        ).read_text(encoding="utf-8")
    )

    assert len(approved.records) == 40
    assert approval.gold_status_after == "skeleton_no_formal_gold"
    assert approval.formal_gold_promoted is False


def test_approved_template_contract_matches_runtime_registry() -> None:
    approved = json.loads(
        (
            ROOT / "datasets/coursepilot_eval/v1/approved/work_packages/p11_foundation_input.json"
        ).read_text(encoding="utf-8")
    )
    expected = {
        item["template_contract"]["template_id"]
        for item in approved["records"]
        if item["component"] == "template_contract"
    }
    registry = TemplateRegistry(ROOT / "resources/templates/registry_v1.yaml")

    assert set(registry.template_ids) == expected


def test_approved_model_profiles_have_deterministic_routes() -> None:
    gateway = ModelGateway.from_files(
        profile_path=ROOT / "resources/model_profiles/default_v1.yaml",
        capability_path=ROOT / "resources/model_profiles/capabilities/deepseek_v4.json",
        main_config=("fake", "same-model", "https://example.test/v1"),
        light_config=None,
        mode=GatewayMode.LOCAL,
    )

    assert len(gateway.profiles) == 6
    assert {gateway.resolve(profile).model for profile in gateway.profiles} == {"same-model"}


def test_runtime_foundation_does_not_reference_holdout_or_test_data() -> None:
    roots = (
        ROOT / "src/coursepilot/domain",
        ROOT / "src/coursepilot/runtime",
        ROOT / "src/coursepilot/templates",
        ROOT / "src/coursepilot/models_gateway",
    )
    text = "\n".join(
        path.read_text(encoding="utf-8") for root in roots for path in root.glob("*.py")
    )
    assert "DS3" not in text
    assert "holdout" not in text.lower()


def test_runtime_foundation_owner_approval_binds_exact_candidate() -> None:
    candidate = (
        ROOT
        / "datasets/coursepilot_eval/v1/candidates/work_packages/p11_runtime_foundation_snapshot_r1.json"
    )
    approval = json.loads(
        (
            ROOT
            / "datasets/coursepilot_eval/v1/provenance/p11_runtime_foundation_snapshot_approval.json"
        ).read_text(encoding="utf-8")
    )

    assert approval["reviewer_id"] == "course_owner"
    assert approval["p11_exit_gate"] == "passed"
    assert (
        approval["approved_snapshot"]["sha256"]
        == hashlib.sha256(candidate.read_bytes()).hexdigest()
    )
