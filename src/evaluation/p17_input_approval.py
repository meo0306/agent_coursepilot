"""Approve the exact P17 Integration and Security Qualification input bundles."""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any, cast

from pydantic import JsonValue

from coursepilot.evals.formal_schemas import CPDS8P17Dataset, SYSDS1P17Dataset
from evaluation.contracts import ApprovalRecord, ReviewLogEntry, ReviewStatus, TestLock
from evaluation.datasets import record_digest
from evaluation.io import atomic_write_json, atomic_write_text
from evaluation.p10_schemas import P17SecurityQualificationDataset
from evaluation.p17_input_data import ROOT, SECURITY_ROOT, _file_sha, _sha
from evaluation.p17_input_revision_r3 import R2_INTEGRATION_SHA, R2_SECURITY_SHA

INTEGRATION_R3_SHA = "c44c94779b83731a3a3029498703ff3929173e36637272faac548ed2662bc7d1"
CP_ROOT = Path("datasets/coursepilot_eval/v1")
CR_ROOT = Path("datasets/courserag_eval/v1")


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _raw_record_digest(record: dict[str, Any]) -> str:
    return _sha({key: value for key, value in record.items() if key != "approval"})


def _verify_manifest(path: Path, expected_sha: str) -> dict[str, Any]:
    manifest = _load(path)
    if manifest.get("bundle_sha256") != expected_sha:
        raise ValueError(f"Bundle identity differs: {path}")
    body = {
        key: value
        for key, value in manifest.items()
        if key not in {"schema_version", "bundle_sha256"}
    }
    if _sha(body) != expected_sha:
        raise ValueError(f"Bundle manifest content changed: {path}")
    return manifest


def _review_records(path: Path, bundle: str) -> list[dict[str, Any]]:
    review = _load(path)
    if review.get("bundle_sha256") != bundle:
        raise ValueError(f"Review is bound to a different Bundle: {path}")
    records = review.get("records", [])
    if not records or any(item.get("decision") not in {"approve", "reject"} for item in records):
        raise ValueError(f"Review is incomplete: {path}")
    return records


def _latest_approved(
    passes: list[tuple[Path, str]], final_records: dict[str, Any]
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    latest: dict[str, tuple[str, Path, str]] = {}
    sources: list[dict[str, str]] = []
    for path, bundle in passes:
        sources.append(
            {"path": path.as_posix(), "sha256": _file_sha(path), "bundle_sha256": bundle}
        )
        for item in _review_records(path, bundle):
            record_id = item["record_id"]
            candidate = item.get("candidate_record")
            if candidate is not None and record_id in final_records:
                if _raw_record_digest(candidate) != record_digest(final_records[record_id]):
                    # A later repaired revision is allowed to supersede a rejected record only.
                    if item["decision"] == "approve":
                        raise ValueError(f"Approved review record changed later: {record_id}")
            latest[record_id] = (item["decision"], path, item.get("notes", ""))
    if set(latest) != set(final_records):
        raise ValueError("Review passes do not cover the final Candidate exactly")
    rejected = sorted(record_id for record_id, value in latest.items() if value[0] != "approve")
    if rejected:
        raise ValueError(f"Final review still contains rejected records: {rejected}")
    normalized = [
        {
            "record_id": record_id,
            "decision": "approve",
            "reviewer_id": "course_owner",
            "final_candidate_record_sha256": record_digest(final_records[record_id]),
            "latest_source_review": latest[record_id][1].as_posix(),
            "notes": latest[record_id][2],
        }
        for record_id in final_records
    ]
    return normalized, sources


def _approve_records(
    records: list[Any], *, review_id: str, reviewed_at: datetime, note: str
) -> tuple[list[Any], dict[str, ApprovalRecord]]:
    approved: list[Any] = []
    approvals: dict[str, ApprovalRecord] = {}
    for index, record in enumerate(records, start=1):
        candidate_hash = record_digest(record)
        provisional = record.model_copy(
            update={"review_status": ReviewStatus.APPROVED, "approval": None}
        )
        approval = ApprovalRecord(
            review_id=f"{review_id}.record.{index:03d}",
            reviewer_id="course_owner",
            reviewed_at=reviewed_at,
            candidate_sha256=candidate_hash,
            approved_record_sha256=record_digest(provisional),
            notes=note,
        )
        approvals[record.record_id] = approval
        approved.append(
            record.model_copy(update={"review_status": ReviewStatus.APPROVED, "approval": approval})
        )
    return approved, approvals


def _append_log(path: Path, additions: list[ReviewLogEntry]) -> None:
    old = path.read_text(encoding="utf-8") if path.exists() else ""
    if old and not old.endswith("\n"):
        raise ValueError(f"Review log must end with newline: {path}")
    existing = {
        item.review_id: item
        for line in old.splitlines()
        if line.strip()
        for item in [ReviewLogEntry.model_validate_json(line)]
    }
    appended = ""
    for item in additions:
        previous = existing.get(item.review_id)
        if previous is not None and previous != item:
            raise ValueError(f"Existing review log entry differs: {item.review_id}")
        if previous is None:
            appended += item.model_dump_json() + "\n"
    atomic_write_text(path, old + appended)


def _validate_boundaries(repository_root: Path) -> None:
    lock = TestLock.model_validate_json(
        (repository_root / CP_ROOT / "test.lock.json").read_text(encoding="utf-8")
    )
    if lock.locked:
        raise ValueError("P17 Pilot approval cannot modify a locked CoursePilot Test")
    for split in ("dev_ids.txt", "test_ids.txt"):
        if (repository_root / CP_ROOT / "splits" / split).read_text(encoding="utf-8").strip():
            raise ValueError("CoursePilot Dev/Test must remain empty during P17 Pilot approval")
    blind = _load(repository_root / SECURITY_ROOT / "blind_commitment.json")
    if blind.get("content_status") != "empty_unread" or blind.get("case_count") != 48:
        raise ValueError("P17 Security Blind Commitment boundary changed")


def _existing_approval(
    root: Path, *, integration_bundle: str, security_bundle: str
) -> dict[str, Any] | None:
    integration_path = root / CP_ROOT / "provenance/p17_integration_bundle_approval.json"
    security_path = root / SECURITY_ROOT / "approved/qualification_dev_approval.json"
    if not integration_path.exists() and not security_path.exists():
        return None
    if not integration_path.is_file() or not security_path.is_file():
        raise ValueError("P17 approval is only partially materialized")
    integration = _load(integration_path)
    security = _load(security_path)
    if integration.get("bundle_sha256") != integration_bundle:
        raise ValueError("Existing P17 Integration approval differs from requested Bundle")
    if security.get("bundle_sha256") != security_bundle:
        raise ValueError("Existing P17 Security approval differs from requested Bundle")
    bound_files = {
        root / CP_ROOT / "approved/cp_ds8/p17_fault_security.json": integration[
            "approved_dataset_hashes"
        ]["cp_ds8"],
        root / CP_ROOT / "approved/sys_ds1/p17_system_journeys.json": integration[
            "approved_dataset_hashes"
        ]["sys_ds1"],
        root / CP_ROOT / "reviews/p17_integration_review_decisions.json": integration[
            "review_decisions_sha256"
        ],
        root / SECURITY_ROOT / "approved/qualification_dev.json": security[
            "approved_dataset_sha256"
        ],
        root / SECURITY_ROOT / "approved/review_decisions.json": security[
            "review_decisions_sha256"
        ],
    }
    for path, expected_hash in bound_files.items():
        if not path.is_file() or _file_sha(path) != expected_hash:
            raise ValueError(f"Existing P17 approved artifact changed: {path}")
    return {
        "integration_bundle_sha256": integration_bundle,
        "integration_approval_sha256": _file_sha(integration_path),
        "security_bundle_sha256": security_bundle,
        "security_approval_sha256": _file_sha(security_path),
        "approved_record_counts": {"integration": 38, "security": 120},
        "blind_content_status": security["blind_content_status"],
    }


def approve_p17_inputs(
    *,
    repository_root: Path,
    integration_bundle_sha256: str,
    security_bundle_sha256: str,
    reviewed_at: datetime,
) -> dict[str, Any]:
    root = repository_root.resolve()
    if integration_bundle_sha256 != INTEGRATION_R3_SHA:
        raise ValueError("Unexpected P17 Integration approval identity")
    if security_bundle_sha256 != R2_SECURITY_SHA:
        raise ValueError("Unexpected P17 Security approval identity")
    _validate_boundaries(root)

    integration_manifest = _verify_manifest(
        root / ROOT / "provenance/p17_integration_bundle_manifest_r3.json",
        integration_bundle_sha256,
    )
    security_manifest = _verify_manifest(
        root / SECURITY_ROOT / "qualification_dev_manifest_r2.json", security_bundle_sha256
    )
    fault_path = root / integration_manifest["fault_candidate_relative_path"]
    journey_path = root / integration_manifest["journey_candidate_relative_path"]
    security_path = root / SECURITY_ROOT / "qualification_dev_candidate_r2.json"
    if _file_sha(fault_path) != integration_manifest["fault_candidate_sha256"]:
        raise ValueError("P17 CP-DS8 Candidate changed")
    if _file_sha(journey_path) != integration_manifest["journey_candidate_sha256"]:
        raise ValueError("P17 SYS-DS1 Candidate changed")
    if _file_sha(security_path) != security_manifest["candidate_sha256"]:
        raise ValueError("P17 Security Candidate changed")
    if (
        _file_sha(root / SECURITY_ROOT / "blind_commitment.json")
        != security_manifest["blind_commitment_sha256"]
    ):
        raise ValueError("P17 Security Blind Commitment changed")

    existing = _existing_approval(
        root,
        integration_bundle=integration_bundle_sha256,
        security_bundle=security_bundle_sha256,
    )
    if existing is not None:
        return existing

    faults = CPDS8P17Dataset.model_validate_json(fault_path.read_text(encoding="utf-8"))
    journeys = SYSDS1P17Dataset.model_validate_json(journey_path.read_text(encoding="utf-8"))
    security = P17SecurityQualificationDataset.model_validate_json(
        security_path.read_text(encoding="utf-8")
    )
    integration_final = {item.record_id: item for item in [*faults.cases, *journeys.cases]}
    security_final = {item.record_id: item for item in security.cases}

    integration_reviews, integration_review_sources = _latest_approved(
        [
            (
                root
                / "storage_eval/p17_integration_review/01b7549801efad637b4da39c271fe932c2ae44104ab73f3c618add0dfdac7b78/p17_integration_review.json",
                "01b7549801efad637b4da39c271fe932c2ae44104ab73f3c618add0dfdac7b78",
            ),
            (
                root
                / f"storage_eval/p17_integration_review/{R2_INTEGRATION_SHA}/p17_integration_r2_review_template.json",
                R2_INTEGRATION_SHA,
            ),
            (
                root
                / f"storage_eval/p17_integration_review/{INTEGRATION_R3_SHA}/p17_integration_r3_review_template.json",
                INTEGRATION_R3_SHA,
            ),
        ],
        integration_final,
    )
    security_reviews, security_review_sources = _latest_approved(
        [
            (
                root
                / "storage_eval/p17_security_review/f230655e5ed60c9462401e0824b6a3ec4e302b275faf16460ce61a50fd54ad8b/p17_security_review.json",
                "f230655e5ed60c9462401e0824b6a3ec4e302b275faf16460ce61a50fd54ad8b",
            ),
            (
                root
                / f"storage_eval/p17_security_review/{R2_SECURITY_SHA}/p17_security_r2_review_template.json",
                R2_SECURITY_SHA,
            ),
        ],
        security_final,
    )

    approved_faults, fault_approvals = _approve_records(
        faults.cases,
        review_id="p17-integration-gold-bundle-approval",
        reviewed_at=reviewed_at,
        note="P17 CP-DS8 Integration Pilot input approved; P18 formal Gold remains out of scope.",
    )
    approved_journeys, journey_approvals = _approve_records(
        journeys.cases,
        review_id="p17-integration-gold-bundle-approval.journey",
        reviewed_at=reviewed_at,
        note="P17 SYS-DS1 Integration Pilot input approved; P18 formal Gold remains out of scope.",
    )
    approved_security, security_approvals = _approve_records(
        security.cases,
        review_id="p17-security-qualification-dev-approval",
        reviewed_at=reviewed_at,
        note="P17 Security Qualification Dev approved; this does not approve or construct Blind content.",
    )

    approved_fault_dataset = faults.model_copy(update={"cases": approved_faults})
    approved_journey_dataset = journeys.model_copy(update={"cases": approved_journeys})
    approved_security_dataset = security.model_copy(update={"cases": approved_security})
    cp_fault_output = root / CP_ROOT / "approved/cp_ds8/p17_fault_security.json"
    cp_journey_output = root / CP_ROOT / "approved/sys_ds1/p17_system_journeys.json"
    security_output = root / SECURITY_ROOT / "approved/qualification_dev.json"
    cp_review_output = root / CP_ROOT / "reviews/p17_integration_review_decisions.json"
    security_review_output = root / SECURITY_ROOT / "approved/review_decisions.json"
    atomic_write_json(
        cp_review_output,
        cast(
            JsonValue,
            {
                "bundle_sha256": integration_bundle_sha256,
                "reviewer_id": "course_owner",
                "review_pass": "single_complete_review_across_revisions",
                "source_reviews": integration_review_sources,
                "records": integration_reviews,
            },
        ),
    )
    atomic_write_json(
        security_review_output,
        cast(
            JsonValue,
            {
                "bundle_sha256": security_bundle_sha256,
                "reviewer_id": "course_owner",
                "review_pass": "single_complete_review_across_revisions",
                "source_reviews": security_review_sources,
                "records": security_reviews,
            },
        ),
    )
    atomic_write_json(
        cp_fault_output, cast(JsonValue, approved_fault_dataset.model_dump(mode="json"))
    )
    atomic_write_json(
        cp_journey_output, cast(JsonValue, approved_journey_dataset.model_dump(mode="json"))
    )
    atomic_write_json(
        security_output, cast(JsonValue, approved_security_dataset.model_dump(mode="json"))
    )

    integration_approval = {
        "schema_version": "coursepilot.p17-integration-bundle-approval.v1",
        "bundle_sha256": integration_bundle_sha256,
        "reviewer_id": "course_owner",
        "reviewed_at": reviewed_at.isoformat(),
        "approval_scope": "cp_ds8_and_sys_ds1_p17_pilot_input_only",
        "candidate_hashes": {
            "cp_ds8": integration_manifest["fault_candidate_sha256"],
            "sys_ds1": integration_manifest["journey_candidate_sha256"],
        },
        "approved_dataset_hashes": {
            "cp_ds8": _file_sha(cp_fault_output),
            "sys_ds1": _file_sha(cp_journey_output),
        },
        "review_decisions_sha256": _file_sha(cp_review_output),
        "record_count": 38,
    }
    security_approval = {
        "schema_version": "courserag.p17-security-qualification-dev-approval.v1",
        "bundle_sha256": security_bundle_sha256,
        "reviewer_id": "course_owner",
        "reviewed_at": reviewed_at.isoformat(),
        "approval_scope": "p17_security_qualification_dev_only",
        "candidate_sha256": security_manifest["candidate_sha256"],
        "approved_dataset_sha256": _file_sha(security_output),
        "review_decisions_sha256": _file_sha(security_review_output),
        "blind_commitment_sha256": security_manifest["blind_commitment_sha256"],
        "blind_content_status": "empty_unread",
        "record_count": 120,
    }
    integration_approval_path = root / CP_ROOT / "provenance/p17_integration_bundle_approval.json"
    security_approval_path = root / SECURITY_ROOT / "approved/qualification_dev_approval.json"
    atomic_write_json(integration_approval_path, cast(JsonValue, integration_approval))
    atomic_write_json(security_approval_path, cast(JsonValue, security_approval))

    cp_logs = [
        ReviewLogEntry(
            review_id=approval.review_id,
            record_id=record_id,
            action="approve",
            reviewer_id="course_owner",
            reviewed_at=reviewed_at,
            candidate_sha256=approval.candidate_sha256,
            resulting_record_sha256=approval.approved_record_sha256,
            notes="P17 Integration Pilot input approved; P18 formal Gold remains out of scope.",
        )
        for record_id, approval in {**fault_approvals, **journey_approvals}.items()
    ]
    security_logs = [
        ReviewLogEntry(
            review_id=approval.review_id,
            record_id=record_id,
            action="approve",
            reviewer_id="course_owner",
            reviewed_at=reviewed_at,
            candidate_sha256=approval.candidate_sha256,
            resulting_record_sha256=approval.approved_record_sha256,
            notes="P17 Security Qualification Dev approved; Blind remains empty and unread.",
        )
        for record_id, approval in security_approvals.items()
    ]
    _append_log(root / CP_ROOT / "reviews/review_log.jsonl", cp_logs)
    _append_log(root / CR_ROOT / "reviews/review_log.jsonl", security_logs)

    cp_manifest_path = root / CP_ROOT / "manifest.json"
    cp_manifest = _load(cp_manifest_path)
    cp_manifest.setdefault("gold_components", {})["cp_ds8_p17_pilot"] = "approved"
    cp_manifest["gold_components"]["sys_ds1_p17_pilot"] = "approved"
    cp_manifest["gold_status"] = "p17_integration_pilot_approved"
    cp_manifest.setdefault("phase_input_status", {})["p17"] = "formal_dev_eval_ready"
    atomic_write_json(cp_manifest_path, cast(JsonValue, cp_manifest))

    cr_manifest_path = root / CR_ROOT / "manifest.json"
    cr_manifest = _load(cr_manifest_path)
    cr_manifest.setdefault("gold_components", {})["p17_security_qualification_dev"] = "approved"
    cr_manifest.setdefault("phase_input_status", {})["p17_security"] = "qualification_dev_ready"
    atomic_write_json(cr_manifest_path, cast(JsonValue, cr_manifest))

    revision_path = root / ROOT / "provenance/p17_candidate_revision_history.json"
    revision = _load(revision_path)
    for item in revision["revisions"]:
        if item["candidate_relative_path"].endswith("p17_fault_security_r2.json") or item[
            "candidate_relative_path"
        ].endswith("p17_system_journeys_r3.json"):
            item["status"] = "approved"
            item["reason"] = "Exact P17 Integration Candidate approved after complete owner review."
    atomic_write_json(revision_path, cast(JsonValue, revision))
    return {
        "integration_bundle_sha256": integration_bundle_sha256,
        "integration_approval_sha256": _file_sha(integration_approval_path),
        "security_bundle_sha256": security_bundle_sha256,
        "security_approval_sha256": _file_sha(security_approval_path),
        "approved_record_counts": {"integration": 38, "security": 120},
        "blind_content_status": "empty_unread",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository-root", type=Path, default=Path("."))
    parser.add_argument("--integration-bundle-sha256", required=True)
    parser.add_argument("--security-bundle-sha256", required=True)
    parser.add_argument("--reviewed-at", required=True)
    args = parser.parse_args()
    result = approve_p17_inputs(
        repository_root=args.repository_root,
        integration_bundle_sha256=args.integration_bundle_sha256,
        security_bundle_sha256=args.security_bundle_sha256,
        reviewed_at=datetime.fromisoformat(args.reviewed_at),
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
