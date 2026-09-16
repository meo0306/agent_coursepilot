"""Build the two-record P17 Integration r3 delta after the r2 owner review."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, cast

from pydantic import JsonValue

from coursepilot.evals.formal_schemas import SYSDS1P17Dataset
from evaluation.io import atomic_write_json, atomic_write_text
from evaluation.p17_input_data import ROOT, _file_sha, _sha

R2_INTEGRATION_SHA = "7e613ea920077cf0c811ac36c4867df6901c915340f17a330c4d7018d29fae54"
R2_SECURITY_SHA = "be1f7a235b5c40e55b8b6814b78f8759d17b4987dfcbe0175af3ab099f869b8b"
INTEGRATION_REVIEW = (
    Path("storage_eval/p17_integration_review")
    / R2_INTEGRATION_SHA
    / "p17_integration_r2_review_template.json"
)
SECURITY_REVIEW = (
    Path("storage_eval/p17_security_review")
    / R2_SECURITY_SHA
    / "p17_security_r2_review_template.json"
)
REPAIRED_IDS = {"p17-sys-ds1-06", "p17-sys-ds1-08"}


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _validated_review(path: Path, expected_rejected: set[str]) -> dict[str, dict[str, Any]]:
    records = {item["record_id"]: item for item in _load(path)["records"]}
    unresolved = {record_id for record_id, item in records.items() if item.get("decision") is None}
    rejected = {
        record_id for record_id, item in records.items() if item.get("decision") == "reject"
    }
    if unresolved:
        raise RuntimeError(f"Review contains unresolved records: {sorted(unresolved)}")
    if rejected != expected_rejected:
        raise RuntimeError(
            f"Unexpected rejected records: expected {sorted(expected_rejected)}, got {sorted(rejected)}"
        )
    return records


def _repair_journeys(payload: dict[str, Any]) -> dict[str, Any]:
    repaired_cases: list[dict[str, Any]] = []
    for original in payload["cases"]:
        case = dict(original)
        if case["record_id"] == "p17-sys-ds1-06":
            artifact_ref = case["upstream_artifact_refs"][0]
            case["trace_version_assertions"] = [
                f"P14 Lesson Artifact identity is retained: {artifact_ref}",
                "CourseRAG index version is retained",
                "Evidence version is retained",
            ]
            case["fixture_details"] = {
                **case.get("fixture_details", {}),
                "artifact_owner": "P14",
                "lesson_artifact_ref": artifact_ref,
                "lesson_artifact_file_sha256": artifact_ref.rsplit(":", 1)[1],
            }
        elif case["record_id"] == "p17-sys-ds1-08":
            case["expected_final_status"] = "completed"
        repaired_cases.append(case)
    payload["cases"] = repaired_cases
    return payload


def _review_template(
    bundle_sha: str,
    records: list[dict[str, Any]],
    decisions: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    return {
        "version": "p17_review_v1",
        "bundle_sha256": bundle_sha,
        "reviewer_id": "course_owner",
        "review_pass": "single_r3_delta",
        "records": [
            {
                "record_id": record["record_id"],
                "candidate_record": record,
                "prior_rejection_notes": decisions[record["record_id"]]["notes"],
                "decision": None,
                "notes": "",
            }
            for record in records
        ],
    }


def generate() -> str:
    integration_decisions = _validated_review(INTEGRATION_REVIEW, REPAIRED_IDS)
    _validated_review(SECURITY_REVIEW, set())

    journey_payload = _repair_journeys(
        _load(ROOT / "candidates/sys_ds1/p17_system_journeys_r2.json")
    )
    SYSDS1P17Dataset.model_validate(journey_payload)
    journey_path = ROOT / "candidates/sys_ds1/p17_system_journeys_r3.json"
    atomic_write_json(journey_path, cast(JsonValue, journey_payload))

    fault_path = ROOT / "candidates/cp_ds8/p17_fault_security_r2.json"
    carried_forward = sorted(
        set(
            _load(ROOT / "provenance/p17_integration_bundle_manifest_r2.json")[
                "carried_forward_approved_ids"
            ]
        )
        | {
            record_id
            for record_id, item in integration_decisions.items()
            if item["decision"] == "approve"
        }
    )
    integration_payload = {
        "revision": "r3",
        "parent_bundle_sha256": R2_INTEGRATION_SHA,
        "fault_candidate_relative_path": str(fault_path).replace("\\", "/"),
        "fault_candidate_sha256": _file_sha(fault_path),
        "journey_candidate_relative_path": str(journey_path).replace("\\", "/"),
        "journey_candidate_sha256": _file_sha(journey_path),
        "repaired_record_ids": sorted(REPAIRED_IDS),
        "carried_forward_approved_ids": carried_forward,
        "review_passes": ["single_r3_delta"],
        "security_bundle_sha256": R2_SECURITY_SHA,
        "security_review_status": "all_120_records_reviewed_without_rejection",
    }
    integration_sha = _sha(integration_payload)
    atomic_write_json(
        ROOT / "provenance/p17_integration_bundle_manifest_r3.json",
        cast(
            JsonValue,
            {
                "schema_version": "coursepilot.p17-integration-bundle-manifest.v1",
                "bundle_sha256": integration_sha,
                **integration_payload,
            },
        ),
    )

    r3_records = [item for item in journey_payload["cases"] if item["record_id"] in REPAIRED_IDS]
    review_root = Path("storage_eval/p17_integration_review") / integration_sha
    review_root.mkdir(parents=True, exist_ok=True)
    atomic_write_json(
        review_root / "p17_integration_r3_review_template.json",
        cast(JsonValue, _review_template(integration_sha, r3_records, integration_decisions)),
    )

    history_path = ROOT / "provenance/p17_candidate_revision_history.json"
    history = _load(history_path)
    for item in history["revisions"]:
        if item["candidate_relative_path"].endswith("p17_system_journeys_r2.json"):
            item["status"] = "superseded"
            item["reason"] = "Owner r2 review returned two SYS-DS1 records; replaced by r3."
    history["dataset_version"] = "p17-pilot-r3"
    history["revisions"] = [
        item
        for item in history["revisions"]
        if not item["candidate_relative_path"].endswith("p17_system_journeys_r3.json")
    ]
    history["revisions"].append(
        {
            "revision": 5,
            "candidate_relative_path": "datasets/coursepilot_eval/v1/candidates/sys_ds1/p17_system_journeys_r3.json",
            "candidate_file_sha256": _file_sha(journey_path),
            "status": "pending_course_owner_review",
            "reason": "Two-record SYS-DS1 r3 Candidate pending delta review.",
        }
    )
    atomic_write_json(history_path, cast(JsonValue, history))

    report = f"""# Pre-P17 Integration r3 增量修订报告

- Integration r3 Bundle：`{integration_sha}`。
- 仅修复 `p17-sys-ds1-06` 与 `p17-sys-ds1-08`；其余 36 条 Integration 记录沿用此前人工通过结果。
- `p17-sys-ds1-06` 绑定 Approved P14 Lesson Artifact 文件身份及 SHA-256，不再声称 P16/P15 Artifact identity。
- `p17-sys-ds1-08` 在 Owner re-review 完成后以 `completed` 作为最终状态。
- Security r2 Bundle `{R2_SECURITY_SHA}` 的 120 条记录已完成一轮审核且零退回；未生成 Security r3。
- 本轮只生成 2 条记录的 JSON 复审模板，不生成 HTML。
"""
    atomic_write_text(
        Path("docs/refactor/phase_reports/ED_PRE_P17_input_candidate_review_r3.md"), report
    )
    return integration_sha


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--generate", action="store_true")
    args = parser.parse_args()
    if args.generate:
        first = generate()
        second = generate()
        if first != second:
            raise RuntimeError("P17 Integration r3 generation is not deterministic")
        print(json.dumps({"integration_bundle_sha256": first}, ensure_ascii=False))


if __name__ == "__main__":
    main()
