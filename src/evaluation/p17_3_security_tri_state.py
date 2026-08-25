"""Offline P17.3 tri-state candidate selection from frozen P17.2 scores."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Any

from pydantic import JsonValue, TypeAdapter

from courserag.security.dual_hypothesis import TriStateDualHypothesisProfile
from evaluation.io import atomic_write_json

DEFAULT_DIAGNOSTIC = Path("storage_eval/p17_2_security/diagnostic_repair_report_r1.json")
DEFAULT_SELECTION = Path("storage_eval/p17_3_security/tri_state_selection_r1.json")
DEFAULT_PROFILE = Path("resources/security_profiles/p17_3_tri_state_candidate_v1.json")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--build-approved-candidate", action="store_true")
    parser.add_argument("--diagnostic", type=Path, default=DEFAULT_DIAGNOSTIC)
    parser.add_argument("--expected-diagnostic-sha256", required=True)
    parser.add_argument("--selection-output", type=Path, default=DEFAULT_SELECTION)
    parser.add_argument("--profile-output", type=Path, default=DEFAULT_PROFILE)
    args = parser.parse_args()
    if not args.build_approved_candidate:
        raise SystemExit("refusing P17.3 candidate build without explicit approval flag")
    if args.selection_output.exists() or args.profile_output.exists():
        raise SystemExit("P17.3 candidate output exists; refusing overwrite")
    if _sha256(args.diagnostic) != args.expected_diagnostic_sha256:
        raise SystemExit("P17.2 diagnostic report differs from approved SHA-256")
    report = json.loads(args.diagnostic.read_text(encoding="utf-8"))
    if report.get("consumed_blind_access") is not False:
        raise SystemExit("P17.3 requires a diagnostic report with no Blind access")
    rows = report.get("component_scores")
    if not isinstance(rows, list) or len(rows) != 240:
        raise SystemExit("P17.3 requires all 240 frozen component-score rows")
    candidate = select_tri_state_candidate(rows)
    if candidate is None:
        selection = _selection_report(args.diagnostic, None, "tri_state_candidate_failed")
        atomic_write_json(
            args.selection_output,
            TypeAdapter(JsonValue).validate_python(selection),
        )
        raise SystemExit("P17.3 could not satisfy the tri-state L0/L1 constraints")
    profile = TriStateDualHypothesisProfile(
        name="p17_3_tri_state_candidate_v1",
        version="1.0.0-candidate",
        enabled=False,
        base_profile_sha256=str(report["base_profile_canonical_sha256"]),
        hikma_weight=candidate["hikma_weight"],
        attack_semantic_weight=candidate["attack_semantic_weight"],
        structured_weight=candidate["structured_weight"],
        safe_semantic_weight=candidate["safe_semantic_weight"],
        scope_weight=candidate["scope_weight"],
        attack_boundary=candidate["attack_boundary"],
        safe_boundary=candidate["safe_boundary"],
    )
    atomic_write_json(
        args.profile_output,
        TypeAdapter(JsonValue).validate_python(profile.model_dump(mode="json")),
    )
    selection = _selection_report(args.diagnostic, candidate, "candidate_ready")
    selection["profile_canonical_sha256"] = profile.sha256
    atomic_write_json(
        args.selection_output,
        TypeAdapter(JsonValue).validate_python(selection),
    )
    print(
        json.dumps(
            {
                "selection": str(args.selection_output.resolve()),
                "selection_sha256": _sha256(args.selection_output),
                "profile": str(args.profile_output.resolve()),
                "profile_sha256": _sha256(args.profile_output),
                "status": "candidate_ready",
                "model_calls": 0,
                "consumed_blind_access": False,
            },
            sort_keys=True,
        )
    )


def select_tri_state_candidate(rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    candidates: list[dict[str, Any]] = []
    for hikma_step in range(2, 7):
        hikma_weight = hikma_step / 10
        for semantic_step in range(2, 8):
            attack_semantic_weight = semantic_step / 10
            structured_weight = 1 - hikma_weight - attack_semantic_weight
            if structured_weight < 0 or structured_weight > 0.4:
                continue
            for safe_step in range(4, 10):
                safe_semantic_weight = safe_step / 10
                scope_weight = 1 - safe_semantic_weight
                scored = [
                    (
                        row,
                        _risk(
                            row,
                            hikma_weight,
                            attack_semantic_weight,
                            structured_weight,
                            safe_semantic_weight,
                            scope_weight,
                        ),
                    )
                    for row in rows
                ]
                malicious_risks = [risk for row, risk in scored if row["label"] == "malicious"]
                negative_risks = [risk for row, risk in scored if row["label"] == "hard_negative"]
                attack_boundaries = {math.nextafter(value, math.inf) for value in negative_risks}
                attack_boundaries.add(math.nextafter(max(negative_risks), math.inf))
                for attack_boundary in attack_boundaries:
                    safe_boundary = min(
                        math.nextafter(min(malicious_risks), -math.inf),
                        math.nextafter(attack_boundary, -math.inf),
                    )
                    metrics = _tri_state_metrics(
                        scored,
                        attack_boundary=attack_boundary,
                        safe_boundary=safe_boundary,
                    )
                    if metrics["malicious_safe"] != 0 or metrics["hard_negative_attack"] > 3:
                        continue
                    candidates.append(
                        {
                            "hikma_weight": hikma_weight,
                            "attack_semantic_weight": attack_semantic_weight,
                            "structured_weight": round(structured_weight, 10),
                            "safe_semantic_weight": safe_semantic_weight,
                            "scope_weight": round(scope_weight, 10),
                            "attack_boundary": attack_boundary,
                            "safe_boundary": safe_boundary,
                            **metrics,
                        }
                    )
    if not candidates:
        return None
    candidates.sort(
        key=lambda item: (
            int(item["hard_negative_review"]),
            int(item["malicious_review"]),
            int(item["hard_negative_attack"]),
            -int(item["malicious_attack"]),
            -float(item["attack_boundary"]) + float(item["safe_boundary"]),
        )
    )
    return candidates[0]


def _risk(
    row: dict[str, Any],
    hikma_weight: float,
    attack_semantic_weight: float,
    structured_weight: float,
    safe_semantic_weight: float,
    scope_weight: float,
) -> float:
    attack = (
        hikma_weight * float(row["hikma_score"])
        + attack_semantic_weight * float(row["attack_semantic_score"])
        + structured_weight * float(row["structured_score"])
    )
    safe = safe_semantic_weight * float(row["safe_semantic_score"]) + scope_weight * float(
        row["scope_score"]
    )
    return attack - safe


def _tri_state_metrics(
    scored: list[tuple[dict[str, Any], float]],
    *,
    attack_boundary: float,
    safe_boundary: float,
) -> dict[str, Any]:
    counts = {
        "malicious_attack": 0,
        "malicious_review": 0,
        "malicious_safe": 0,
        "hard_negative_attack": 0,
        "hard_negative_review": 0,
        "hard_negative_safe": 0,
    }
    decisions: dict[str, str] = {}
    for row, risk in scored:
        if risk >= attack_boundary:
            decision = "attack"
        elif risk <= safe_boundary:
            decision = "safe"
        else:
            decision = "review"
        prefix = "malicious" if row["label"] == "malicious" else "hard_negative"
        counts[f"{prefix}_{decision}"] += 1
        decisions[str(row["record_id"])] = "needs_review" if decision == "review" else decision
    return {
        **counts,
        "malicious_capture_recall": (counts["malicious_attack"] + counts["malicious_review"]) / 120,
        "hard_negative_attack_specificity": 1 - counts["hard_negative_attack"] / 120,
        "review_count": counts["malicious_review"] + counts["hard_negative_review"],
        "review_rate": (counts["malicious_review"] + counts["hard_negative_review"]) / 240,
        "decisions": decisions,
    }


def _selection_report(
    diagnostic_path: Path,
    candidate: dict[str, Any] | None,
    status: str,
) -> dict[str, Any]:
    return {
        "schema_version": "courserag.p17-3-tri-state-selection.v1",
        "status": status,
        "diagnostic_sha256": _sha256(diagnostic_path),
        "candidate": candidate,
        "selection_objective": (
            "malicious_safe_eq_0_and_hard_negative_attack_lte_3_then_minimize_review"
        ),
        "model_calls": 0,
        "network": False,
        "external_provider_calls": 0,
        "consumed_blind_access": False,
        "qualification_access": False,
    }


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


if __name__ == "__main__":
    main()
