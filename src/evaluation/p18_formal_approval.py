"""Approve the three exact P18 formal Gold bundles without locking Test."""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any, cast

from pydantic import BaseModel, JsonValue

from evaluation.contracts import ApprovalRecord, ReviewLogEntry, ReviewStatus, TestLock
from evaluation.datasets import record_digest
from evaluation.io import atomic_write_json, atomic_write_text
from evaluation.p18_formal_data import _file_sha
from evaluation.p18_schemas import (
    P18ExamDataset,
    P18FaultDataset,
    P18FormalApproval,
    P18JourneyDataset,
    P18LessonDataset,
    P18PPTDataset,
    P18RecoveryDataset,
    P18RepairDataset,
    P18ReviewTemplate,
    P18TemplateDataset,
    P18ValidationDataset,
)

ROOT = Path("datasets/coursepilot_eval/v1")
BUSINESS_SHA = "4ce0ac60ca70c1f1fd23e62aaab911718dc763882ceee0d371d726926bd9a869"
QUALITY_SHA = "d724a1c430ed1c02ae42b770b46714fe3ff0b73abb94d83906d9e6268470a082"
INTEGRATION_SHA = "5d42d4428aad1f31b07434febcd9ff9b487436095c5c99d3f3e2348627a46683"

MANIFESTS = {
    "business": ROOT / "provenance/p18_business_bundle_manifest.json",
    "quality_recovery": ROOT / "provenance/p18_quality_recovery_bundle_manifest_r2.json",
    "integration_export": ROOT / "provenance/p18_integration_export_bundle_manifest_r2.json",
}
REVIEWS = {
    "business_r1": Path(
        f"storage_eval/p18_business_review/{BUSINESS_SHA}/p18_business_review.json"
    ),
    "quality_r1": Path(
        "storage_eval/p18_quality_recovery_review/"
        "2c5b112458f3b602be1742a35644ae0b36a758bb61a8ad63bc6cba2bfe79483c/"
        "p18_quality_recovery_review.json"
    ),
    "quality_r2": Path(
        f"storage_eval/p18_quality_recovery_review/{QUALITY_SHA}/"
        "p18_quality_recovery_r2_review.json"
    ),
    "integration_r1": Path(
        "storage_eval/p18_integration_export_review/"
        "f9e818926e49d2077e1001fab60867c24604f3767a09495b7dd388d422b13d40/"
        "p18_integration_export_review.json"
    ),
    "integration_r2": Path(
        f"storage_eval/p18_integration_export_review/{INTEGRATION_SHA}/"
        "p18_integration_export_r2_review.json"
    ),
}

CANDIDATES: dict[str, tuple[Path, type[BaseModel], str]] = {
    "cp_ds1": (
        ROOT / "candidates/cp_ds1/p18_lesson_formal_r1.json",
        P18LessonDataset,
        "cases",
    ),
    "cp_ds2": (
        ROOT / "candidates/cp_ds2/p18_exam_formal_r1.json",
        P18ExamDataset,
        "cases",
    ),
    "cp_ds3": (
        ROOT / "candidates/cp_ds3/p18_ppt_formal_r1.json",
        P18PPTDataset,
        "cases",
    ),
    "cp_ds4": (
        ROOT / "candidates/cp_ds4/p18_validation_formal_r1.json",
        P18ValidationDataset,
        "new_cases",
    ),
    "cp_ds5": (
        ROOT / "candidates/cp_ds5/p18_repair_formal_r2.json",
        P18RepairDataset,
        "new_cases",
    ),
    "cp_ds6": (
        ROOT / "candidates/cp_ds6/p18_recovery_formal_r1.json",
        P18RecoveryDataset,
        "cases",
    ),
    "cp_ds7": (
        ROOT / "candidates/cp_ds7/p18_export_templates_formal_r2.json",
        P18TemplateDataset,
        "cases",
    ),
    "cp_ds8": (
        ROOT / "candidates/cp_ds8/p18_fault_security_formal_r2.json",
        P18FaultDataset,
        "cases",
    ),
    "sys_ds1": (
        ROOT / "candidates/sys_ds1/p18_system_journeys_formal_r2.json",
        P18JourneyDataset,
        "cases",
    ),
}
APPROVED = {component: ROOT / f"approved/{component}/p18_formal.json" for component in CANDIDATES}
APPROVAL_PATH = ROOT / "provenance/p18_formal_gold_approval.json"
DECISIONS_PATH = ROOT / "reviews/p18_formal_review_decisions.json"
SPLIT_PATH = ROOT / "provenance/p18_component_splits.json"


def _load(path: Path) -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))


def _verify_manifest(path: Path, expected_sha: str) -> dict[str, Any]:
    manifest = _load(path)
    if manifest.get("bundle_sha256") != expected_sha:
        raise ValueError(f"P18 Bundle identity differs: {path}")
    return manifest


def _review(path: Path, bundle_sha: str) -> P18ReviewTemplate:
    review = P18ReviewTemplate.model_validate_json(path.read_text(encoding="utf-8"))
    if review.bundle_sha256 != bundle_sha:
        raise ValueError(f"P18 review is bound to another Bundle: {path}")
    if any(item.decision == "pending" for item in review.decisions):
        raise ValueError(f"P18 review is incomplete: {path}")
    return review


def _final_review_map(
    first: P18ReviewTemplate, revision: P18ReviewTemplate | None = None
) -> dict[str, str]:
    decisions: dict[str, str] = {item.record_id: item.decision for item in first.decisions}
    if revision is not None:
        for item in revision.decisions:
            if decisions.get(item.record_id) != "reject":
                raise ValueError(f"r2 reviews a record not rejected in r1: {item.record_id}")
            decisions[item.record_id] = item.decision
    rejected = sorted(
        record_id for record_id, decision in decisions.items() if decision != "approve"
    )
    if rejected:
        raise ValueError(f"P18 final review still contains rejected records: {rejected}")
    return decisions


def _approve_records(
    records: list[Any], *, component: str, reviewed_at: datetime
) -> tuple[list[Any], dict[str, ApprovalRecord], list[ReviewLogEntry]]:
    approved: list[Any] = []
    approvals: dict[str, ApprovalRecord] = {}
    logs: list[ReviewLogEntry] = []
    for record in records:
        candidate_sha = record_digest(record)
        provisional = record.model_copy(
            update={"review_status": ReviewStatus.APPROVED, "approval": None}
        )
        approved_sha = record_digest(provisional)
        approval = ApprovalRecord(
            review_id=f"p18-formal.{component}.{record.record_id}",
            reviewer_id="course_owner",
            reviewed_at=reviewed_at,
            candidate_sha256=candidate_sha,
            approved_record_sha256=approved_sha,
            notes="Exact P18 formal Bundle approval; CP-DS0 and Test lock remain out of scope.",
        )
        approvals[record.record_id] = approval
        approved.append(
            record.model_copy(update={"review_status": ReviewStatus.APPROVED, "approval": approval})
        )
        logs.append(
            ReviewLogEntry(
                review_id=approval.review_id,
                record_id=record.record_id,
                action="approve",
                reviewer_id="course_owner",
                reviewed_at=reviewed_at,
                candidate_sha256=candidate_sha,
                resulting_record_sha256=approved_sha,
                notes=approval.notes,
            )
        )
    return approved, approvals, logs


def _append_log(path: Path, additions: list[ReviewLogEntry]) -> None:
    old = path.read_text(encoding="utf-8") if path.exists() else ""
    if old and not old.endswith("\n"):
        raise ValueError("review_log.jsonl must end with a newline")
    existing = {
        item.review_id: item
        for line in old.splitlines()
        if line.strip()
        for item in [ReviewLogEntry.model_validate_json(line)]
    }
    appended = ""
    for item in additions:
        prior = existing.get(item.review_id)
        if prior is not None and prior != item:
            raise ValueError(f"existing P18 review log differs: {item.review_id}")
        if prior is None:
            appended += item.model_dump_json() + "\n"
    atomic_write_text(path, old + appended)


def _component_splits(models: dict[str, BaseModel]) -> dict[str, Any]:
    splits: dict[str, dict[str, list[str]]] = {}
    for component, model in models.items():
        payload = model.model_dump(mode="json")
        records = payload.get("new_cases", payload.get("cases", []))
        if component in {"cp_ds4", "cp_ds5"}:
            records = [*payload["carried_dev_records"], *records]
        component_splits: dict[str, list[str]] = {}
        for record in records:
            split = record.get("split", record.get("split_role", "unspecified"))
            component_splits.setdefault(split, []).append(record["record_id"])
        splits[component] = component_splits
    return {
        "schema_version": "coursepilot.p18-component-splits.v1",
        "business_distribution": {
            "dev": 18,
            "test": 12,
            "per_artifact_type": {"dev": 6, "test": 4},
        },
        "components": splits,
        "global_test_lock_required_for_test_and_blind": True,
        "test_locked": False,
    }


def _existing_approval(root: Path, bundles: dict[str, str]) -> dict[str, Any] | None:
    path = root / APPROVAL_PATH
    if not path.exists():
        return None
    approval = P18FormalApproval.model_validate_json(path.read_text(encoding="utf-8"))
    if approval.bundle_sha256s != bundles:
        raise ValueError("existing P18 approval binds different Bundles")
    for component, expected in approval.approved_dataset_sha256s.items():
        target = root / APPROVED[component]
        if not target.is_file() or _file_sha(target) != expected:
            raise ValueError(f"existing P18 Approved dataset changed: {component}")
    return approval.model_dump(mode="json")


def approve_p18_formal(
    *,
    repository_root: Path,
    business_bundle_sha256: str,
    quality_bundle_sha256: str,
    integration_bundle_sha256: str,
    reviewed_at: datetime,
) -> dict[str, Any]:
    root = repository_root.resolve()
    bundles = {
        "business": business_bundle_sha256,
        "quality_recovery": quality_bundle_sha256,
        "integration_export": integration_bundle_sha256,
    }
    expected = {
        "business": BUSINESS_SHA,
        "quality_recovery": QUALITY_SHA,
        "integration_export": INTEGRATION_SHA,
    }
    if bundles != expected:
        raise ValueError("unexpected P18 formal Bundle identity")

    lock = TestLock.model_validate_json(
        (root / ROOT / "test.lock.json").read_text(encoding="utf-8")
    )
    if lock.locked:
        raise ValueError("P18 formal Gold approval cannot modify an already locked Test")

    manifests = {
        kind: _verify_manifest(root / MANIFESTS[kind], bundle) for kind, bundle in bundles.items()
    }
    existing = _existing_approval(root, bundles)
    if existing is not None:
        return existing

    business_review = _review(root / REVIEWS["business_r1"], BUSINESS_SHA)
    quality_r1 = _review(
        root / REVIEWS["quality_r1"],
        "2c5b112458f3b602be1742a35644ae0b36a758bb61a8ad63bc6cba2bfe79483c",
    )
    quality_r2 = _review(root / REVIEWS["quality_r2"], QUALITY_SHA)
    integration_r1 = _review(
        root / REVIEWS["integration_r1"],
        "f9e818926e49d2077e1001fab60867c24604f3767a09495b7dd388d422b13d40",
    )
    integration_r2 = _review(root / REVIEWS["integration_r2"], INTEGRATION_SHA)
    business_decisions = _final_review_map(business_review)
    quality_decisions = _final_review_map(quality_r1, quality_r2)
    integration_decisions = _final_review_map(integration_r1, integration_r2)
    if (
        len(business_decisions) != 30
        or len(quality_decisions) != 129
        or len(integration_decisions) != 39
    ):
        raise ValueError("P18 final review coverage differs from the frozen review scope")

    models: dict[str, BaseModel] = {}
    candidate_hashes: dict[str, str] = {}
    for component, (relative_path, model_type, _) in CANDIDATES.items():
        path = root / relative_path
        models[component] = model_type.model_validate_json(path.read_text(encoding="utf-8"))
        candidate_hashes[component] = _file_sha(path)

    business_records = {
        record.record_id: record
        for component in ("cp_ds1", "cp_ds2", "cp_ds3")
        for record in getattr(models[component], "cases")
    }
    quality_records = {
        record.record_id: record
        for component, field in (
            ("cp_ds4", "new_cases"),
            ("cp_ds5", "new_cases"),
            ("cp_ds6", "cases"),
        )
        for record in getattr(models[component], field)
    }
    templates = cast(P18TemplateDataset, models["cp_ds7"])
    integration_records = {
        record.record_id: record
        for record in [
            *[case for case in templates.cases if case.source_kind == "github_public"],
            *getattr(models["cp_ds8"], "cases"),
            *getattr(models["sys_ds1"], "cases"),
        ]
    }
    for kind, decisions, reviewed_records in (
        ("business", business_decisions, business_records),
        ("quality_recovery", quality_decisions, quality_records),
        ("integration_export", integration_decisions, integration_records),
    ):
        expected_record_hashes = manifests[kind]["candidate_record_hashes"]
        if set(decisions) != set(reviewed_records) or set(reviewed_records) != set(
            expected_record_hashes
        ):
            raise ValueError(f"P18 {kind} review/record coverage differs")
        for record_id, record in reviewed_records.items():
            if record_digest(record) != expected_record_hashes[record_id]:
                raise ValueError(f"P18 reviewed Candidate record changed: {record_id}")

    for component, expected_hash in manifests["business"]["candidate_hashes"].items():
        if candidate_hashes[component] != expected_hash:
            raise ValueError(f"P18 Business Candidate changed: {component}")
    for component, expected_hash in manifests["quality_recovery"]["candidate_hashes"].items():
        if candidate_hashes[component] != expected_hash:
            raise ValueError(f"P18 Quality Candidate changed: {component}")
    for component, expected_hash in manifests["integration_export"]["candidate_hashes"].items():
        if component == "cp_ds8_blind_commitment":
            continue
        if candidate_hashes[component] != expected_hash:
            raise ValueError(f"P18 Integration Candidate changed: {component}")

    approved_models: dict[str, BaseModel] = {}
    all_approvals: dict[str, ApprovalRecord] = {}
    all_logs: list[ReviewLogEntry] = []
    for component, model in models.items():
        _, _, record_field = CANDIDATES[component]
        component_records = list(getattr(model, record_field))
        approved_records, approvals, logs = _approve_records(
            component_records, component=component, reviewed_at=reviewed_at
        )
        approved_models[component] = model.model_copy(update={record_field: approved_records})
        all_approvals.update(approvals)
        all_logs.extend(logs)
    if len(all_approvals) != 208:
        raise ValueError(f"expected 208 P18 ApprovalRecords, got {len(all_approvals)}")

    split_payload = _component_splits(models)
    atomic_write_json(root / SPLIT_PATH, cast(JsonValue, split_payload))
    review_sources = {name: _file_sha(root / path) for name, path in REVIEWS.items()}
    consolidated = {
        "schema_version": "coursepilot.p18-final-review-decisions.v1",
        "bundle_sha256s": bundles,
        "reviewer_id": "course_owner",
        "review_sources": {
            name: {"path": path.as_posix(), "sha256": review_sources[name]}
            for name, path in REVIEWS.items()
        },
        "final_approved_review_scope": {
            "business": sorted(business_decisions),
            "quality_recovery": sorted(quality_decisions),
            "integration_export": sorted(integration_decisions),
            "reused_template_bindings_approved_by_exact_batch_authorization": sorted(
                case.record_id
                for case in cast(P18TemplateDataset, models["cp_ds7"]).cases
                if case.source_kind != "github_public"
            ),
        },
    }
    atomic_write_json(root / DECISIONS_PATH, cast(JsonValue, consolidated))

    for component, model in approved_models.items():
        atomic_write_json(
            root / APPROVED[component], cast(JsonValue, model.model_dump(mode="json"))
        )
    approved_hashes = {component: _file_sha(root / path) for component, path in APPROVED.items()}
    approved_record_hashes = {
        record_id: approval.approved_record_sha256 for record_id, approval in all_approvals.items()
    }
    approval = P18FormalApproval(
        reviewed_at=reviewed_at,
        bundle_sha256s=bundles,
        review_source_sha256s=review_sources,
        candidate_dataset_sha256s=candidate_hashes,
        approved_dataset_sha256s=approved_hashes,
        approved_record_sha256s=approved_record_hashes,
        approved_record_count=len(all_approvals),
        component_split_manifest_sha256=_file_sha(root / SPLIT_PATH),
    )
    atomic_write_json(root / APPROVAL_PATH, cast(JsonValue, approval.model_dump(mode="json")))
    _append_log(root / ROOT / "reviews/review_log.jsonl", all_logs)

    for history_path in sorted(
        (root / ROOT / "provenance").glob("p18_*_candidate_revision_history.json")
    ):
        history = _load(history_path)
        for revision in history["revisions"]:
            if revision["status"] == "pending_course_owner_review":
                revision["status"] = "approved"
                revision["reason"] = "Exact P18 formal Bundle approved by the Course Owner."
        atomic_write_json(history_path, cast(JsonValue, history))

    manifest_path = root / ROOT / "manifest.json"
    dataset_manifest = _load(manifest_path)
    components = dataset_manifest.setdefault("gold_components", {})
    for component in CANDIDATES:
        components[f"{component}_p18_formal"] = "approved"
    dataset_manifest["gold_status"] = "p18_formal_gold_approved"
    dataset_manifest.setdefault("phase_input_status", {})["p18"] = "formal_dev_eval_ready"
    dataset_manifest["p18_test_lock_status"] = "pending_dev_freeze"
    atomic_write_json(manifest_path, cast(JsonValue, dataset_manifest))
    return approval.model_dump(mode="json")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository-root", type=Path, default=Path("."))
    parser.add_argument("--business-bundle-sha256", required=True)
    parser.add_argument("--quality-bundle-sha256", required=True)
    parser.add_argument("--integration-bundle-sha256", required=True)
    parser.add_argument("--reviewed-at", required=True)
    args = parser.parse_args()
    result = approve_p18_formal(
        repository_root=args.repository_root,
        business_bundle_sha256=args.business_bundle_sha256,
        quality_bundle_sha256=args.quality_bundle_sha256,
        integration_bundle_sha256=args.integration_bundle_sha256,
        reviewed_at=datetime.fromisoformat(args.reviewed_at),
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
