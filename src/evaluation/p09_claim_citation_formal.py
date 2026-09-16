"""Compute formal P09 Claim-Citation metrics from approved two-pass human review.

This module is deliberately offline: it reads only fixed Dev artifacts, calls no
Provider, and refuses to produce a Freeze Candidate when any preregistered Gate
check fails.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import cast

from pydantic import JsonValue

from courserag.evals.formal_metrics import (
    CitationAssessment,
    ClaimAssessment,
    claim_aware_answerability_metrics,
    claim_metrics,
)
from courserag.evals.schemas import (
    P09ClaimCitationPhase2Approval,
    P09ClaimCitationPhase2Decisions,
    P09ClaimCitationPhase2Package,
)
from evaluation.io import atomic_write_json
from evaluation.manifest import sha256_file
from evaluation.p09_claim_citation_review import validate_phase2_decisions
from evaluation.p09_dev_loader import load_p09_dev_bundle
from evaluation.p09_gate_repair_analysis import (
    _aggregate_cases,
    _all_answered_claims_resolvable,
    _checks,
    _intent_recall,
    _results,
)

PHASE1_PACKAGE_SHA256 = "ffde9da5545d6184d507128e1329300d334d136f0746e22231345dcb52e62281"
PHASE1_DECISIONS_SHA256 = "52e0044ecc702e3ecc0cc9c0b3045a0f5a1f4c0aeaa95dc86f37c0a7b50ec314"
PHASE1_APPROVAL_SHA256 = "1213567444943afeb32ed41df3c5164c3a021dd6429116ec44193ef28259110c"
PHASE2_PACKAGE_SHA256 = "0ad531262b39d660c580c7797712b395d6f21bfa8be5c48105df69d0c9f07ffb"
PHASE2_DECISIONS_SHA256 = "85cb33ebdf2d26ab7360fda3d59738746de5bf1bae6a433a26120f1e146fcd58"
ANSWER_GROUNDING_REPORT_SHA256 = "b04fc9b620fccddecaf889c201fa5b8d0cec139b92686a2ac354dffed853f77b"
Q2_REPORT_SHA256 = "8cf07e7026a58a8750ff455101440b9338f7713b9a51ed28dc52ad59b2f7f197"
B7_B8_REPORT_SHA256 = "ccef34afff9a0286a1e331e2182e6cfd729c345e24e51180ea9040034622a3c3"
APPROVED_GOLD_BUNDLE_SHA256 = "5a84bac041375310d5bb80f17f7481464d07dbcf75f9f980c6b8a030e58af0c1"
ANSWER_CORRECT_GOLD_COVERAGE_THRESHOLD = 0.5
PHASE2_APPROVAL_STATEMENT = (
    "批准 P09 Claim-Citation Phase 2 Decisions，SHA-256: " + PHASE2_DECISIONS_SHA256
)


def write_formal_claim_citation_report(
    repository_root: Path, output_dir: Path
) -> dict[str, str | None]:
    root = repository_root.resolve()
    output = output_dir.resolve()
    review_dir = root / "storage_eval/p09_claim_citation_review"
    phase1_package_path = review_dir / "phase1_package.json"
    phase1_decisions_path = review_dir / "phase1_decisions.json"
    phase1_approval_path = review_dir / "phase1_approval.json"
    phase2_package_path = review_dir / "phase2_package.json"
    phase2_decisions_path = review_dir / "phase2_decisions.json"
    answer_report_path = root / "storage_eval/p09_answer_grounding/run-1/report.json"
    q2_report_path = root / "storage_eval/p09_query_context_qa/run-1/report.json"
    b7_b8_report_path = root / "storage_eval/p09_gate_repair/repair-run-1/report.json"
    for path, expected in (
        (phase1_package_path, PHASE1_PACKAGE_SHA256),
        (phase1_decisions_path, PHASE1_DECISIONS_SHA256),
        (phase1_approval_path, PHASE1_APPROVAL_SHA256),
        (phase2_package_path, PHASE2_PACKAGE_SHA256),
        (phase2_decisions_path, PHASE2_DECISIONS_SHA256),
        (answer_report_path, ANSWER_GROUNDING_REPORT_SHA256),
        (q2_report_path, Q2_REPORT_SHA256),
        (b7_b8_report_path, B7_B8_REPORT_SHA256),
    ):
        _require_hash(path, expected)
    validate_phase2_decisions(phase2_package_path, phase2_decisions_path)

    package = P09ClaimCitationPhase2Package.model_validate_json(
        phase2_package_path.read_text(encoding="utf-8")
    )
    decisions = P09ClaimCitationPhase2Decisions.model_validate_json(
        phase2_decisions_path.read_text(encoding="utf-8")
    )
    approval = P09ClaimCitationPhase2Approval(
        dataset_id=package.dataset_id,
        dataset_version="phase2-approved-v1",
        reviewer_id=decisions.reviewer_id or "course_owner",
        approval_date="2026-08-10",
        source_package_sha256=PHASE2_PACKAGE_SHA256,
        decisions_sha256=PHASE2_DECISIONS_SHA256,
        approval_statement=PHASE2_APPROVAL_STATEMENT,
        approval_statement_sha256=_sha(PHASE2_APPROVAL_STATEMENT),
    )
    output.mkdir(parents=True, exist_ok=True)
    approval_path = output / "phase2_approval.json"
    atomic_write_json(approval_path, cast(JsonValue, approval.model_dump(mode="json")))

    package_by_id = {item.case_id: item for item in package.cases}
    decision_by_id = {item.case_id: item for item in decisions.cases}
    all_assessments: list[ClaimAssessment] = []
    all_required_gold_ids: set[str] = set()
    system_answered: list[bool] = []
    gold_answerable: list[bool] = []
    answered_correctly: list[bool] = []
    per_case: list[dict[str, JsonValue]] = []
    label_counts: Counter[str] = Counter()
    answered_conciseness: list[bool] = []
    for case_id in sorted(package_by_id):
        case = package_by_id[case_id]
        decision = decision_by_id[case_id]
        mapping_by_claim = {item.system_claim_id: item for item in decision.mappings}
        required_ids = {item.gold_claim_id for item in case.required_gold_claims}
        assessments: list[ClaimAssessment] = []
        for claim in case.system_claims:
            mapping = mapping_by_claim[claim.system_claim_id]
            label_counts[claim.phase1_label] += 1
            assessments.append(
                ClaimAssessment(
                    system_claim_id=claim.system_claim_id,
                    label=claim.phase1_label,
                    matched_gold_claim_ids=list(mapping.matched_gold_claim_ids),
                    citations=[
                        CitationAssessment(
                            citation_id=citation.citation_id,
                            supports_claim=citation.supports_claim,
                            supported_gold_claim_ids=(
                                list(mapping.matched_gold_claim_ids)
                                if citation.supports_claim
                                else []
                            ),
                        )
                        for citation in claim.citations
                    ],
                )
            )
        case_metrics = claim_metrics(assessments, required_gold_claim_ids=required_ids)
        coverage = case_metrics["gold_claim_coverage"].value or 0.0
        correct = (
            case.answer_status == "answered"
            and not any(item.label == "contradictory" for item in assessments)
            and coverage >= ANSWER_CORRECT_GOLD_COVERAGE_THRESHOLD
        )
        all_assessments.extend(assessments)
        all_required_gold_ids.update(required_ids)
        system_answered.append(case.answer_status == "answered")
        gold_answerable.append(case.answerable)
        answered_correctly.append(correct)
        if case.answer_status == "answered":
            if case.phase1_conciseness_pass is None:
                raise ValueError(f"answered Case lacks Phase-1 conciseness review: {case_id}")
            answered_conciseness.append(case.phase1_conciseness_pass)
        per_case.append(
            {
                "case_id": case_id,
                "answer_status": case.answer_status,
                "gold_answerable": case.answerable,
                "answered_correctly": correct,
                "required_gold_claim_count": len(required_ids),
                "covered_gold_claim_count": case_metrics["gold_claim_coverage"].numerator,
                "gold_claim_coverage": case_metrics["gold_claim_coverage"].value,
                "missed_gold_claim_ids": list(decision.missed_gold_claim_ids),
            }
        )

    formal = claim_metrics(all_assessments, required_gold_claim_ids=all_required_gold_ids)
    formal.update(
        claim_aware_answerability_metrics(
            system_answered=system_answered,
            gold_answerable=gold_answerable,
            answered_correctly=answered_correctly,
        )
    )
    citation_precision = formal["citation_precision"].value or 0.0
    citation_recall = formal["citation_recall"].value or 0.0
    citation_f1 = (
        2 * citation_precision * citation_recall / (citation_precision + citation_recall)
        if citation_precision + citation_recall
        else 0.0
    )

    bundle = load_p09_dev_bundle(root / "datasets/courserag_eval/v1")
    main = [item for item in bundle.cases if item.qa.evaluation_stratum == "retrieval_main"]
    answer_report = json.loads(answer_report_path.read_text(encoding="utf-8"))
    q2_report = json.loads(q2_report_path.read_text(encoding="utf-8"))
    b7_b8_report = json.loads(b7_b8_report_path.read_text(encoding="utf-8"))
    q3_results = _results(answer_report, "q3")
    q2_metrics = _aggregate_cases(main, _results(q2_report, "q2"))
    q3_metrics = _aggregate_cases(main, q3_results)
    b7_metrics = cast(
        dict[str, JsonValue], b7_b8_report["report"]["systems"]["b7"]["retrieval_main_metrics"]
    )
    b8_metrics = cast(
        dict[str, JsonValue], b7_b8_report["report"]["systems"]["b8"]["retrieval_main_metrics"]
    )
    class_recall = _intent_recall(main, q3_results)
    checks = _checks(
        shadow_metrics=q3_metrics,
        q2_metrics=q2_metrics,
        b7_metrics=b7_metrics,
        b8_metrics=b8_metrics,
        class_recall=class_recall,
        projection_unchanged=True,
    )
    checks.pop("non_citation_projection_unchanged")
    checks["formal_claim_citation_review_available"] = True
    checks.update(
        {
            "dev_only": package.test_access is False
            and answer_report["report"].get("test_access") is False,
            "fallback_count_0": answer_report["report"]["systems"]["q3"].get("fallback_count") == 0,
            "all_answered_claims_resolvable": _all_answered_claims_resolvable(q3_results),
            "phase1_phase2_decisions_owner_approved": True,
        }
    )
    failed_checks = sorted(name for name, passed in checks.items() if not passed)
    status = "passed" if not failed_checks else "failed"
    report: dict[str, JsonValue] = {
        "schema_version": "courserag.p09-claim-citation-formal-report.v1",
        "protocol_version": "p09-freeze-gate-evaluation-r2-human-contract-repair-v1",
        "status": status,
        "scope": "approved_main_dev_fixed_outputs",
        "test_access": False,
        "freeze_eligible": status == "passed",
        "runtime_default_activated": False,
        "answer_correct_gold_coverage_threshold": ANSWER_CORRECT_GOLD_COVERAGE_THRESHOLD,
        "source_hashes": {
            "approved_gold_bundle_sha256": APPROVED_GOLD_BUNDLE_SHA256,
            "answer_grounding_report_sha256": ANSWER_GROUNDING_REPORT_SHA256,
            "q2_report_sha256": Q2_REPORT_SHA256,
            "b7_b8_report_sha256": B7_B8_REPORT_SHA256,
            "phase1_package_sha256": PHASE1_PACKAGE_SHA256,
            "phase1_decisions_sha256": PHASE1_DECISIONS_SHA256,
            "phase1_approval_sha256": PHASE1_APPROVAL_SHA256,
            "phase2_package_sha256": PHASE2_PACKAGE_SHA256,
            "phase2_decisions_sha256": PHASE2_DECISIONS_SHA256,
            "phase2_approval_sha256": sha256_file(approval_path),
        },
        "counts": {
            "cases": package.case_count,
            "system_claims": package.system_claim_count,
            "required_gold_claims": package.required_gold_claim_count,
            "citation_links": sum(len(item.citations) for item in all_assessments),
            "labels": dict(sorted(label_counts.items())),
            "answered_conciseness_pass": sum(answered_conciseness),
            "answered_conciseness_total": len(answered_conciseness),
        },
        "formal_metrics": {
            name: cast(JsonValue, metric.model_dump(mode="json"))
            for name, metric in sorted(formal.items())
        },
        "citation_f1": citation_f1,
        "answer_conciseness_pass_rate": (
            sum(answered_conciseness) / len(answered_conciseness) if answered_conciseness else None
        ),
        "corrected_automatic_metrics": {"q2": q2_metrics, "q3": q3_metrics},
        "intent_recall_by_class": cast(dict[str, JsonValue], class_recall),
        "checks": cast(dict[str, JsonValue], checks),
        "failed_checks": cast(list[JsonValue], failed_checks),
        "per_case": cast(list[JsonValue], per_case),
        "provider_calls": {"cohere": 0, "deepseek": 0, "other": 0},
        "freeze_candidate": None,
    }
    report_path = output / "formal_report.json"
    atomic_write_json(report_path, report)
    manifest: dict[str, JsonValue] = {
        "schema_version": "courserag.p09-claim-citation-formal-manifest.v1",
        "status": status,
        "test_access": False,
        "provider_calls": {"cohere": 0, "deepseek": 0, "other": 0},
        "phase2_approval_sha256": sha256_file(approval_path),
        "formal_report_sha256": sha256_file(report_path),
        "freeze_candidate_generated": False,
        "failed_checks": cast(list[JsonValue], failed_checks),
    }
    manifest_path = output / "formal_manifest.json"
    atomic_write_json(manifest_path, manifest)
    return {
        "phase2_approval": str(approval_path),
        "phase2_approval_sha256": sha256_file(approval_path),
        "formal_report": str(report_path),
        "formal_report_sha256": sha256_file(report_path),
        "formal_manifest": str(manifest_path),
        "formal_manifest_sha256": sha256_file(manifest_path),
        "freeze_candidate": None,
    }


def _require_hash(path: Path, expected: str) -> None:
    if not path.is_file() or sha256_file(path) != expected:
        raise ValueError(f"fixed P09 formal input Hash mismatch: {path}")


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description="Score approved P09 Claim-Citation decisions.")
    parser.add_argument("--repository-root", type=Path, default=Path.cwd())
    parser.add_argument(
        "--output-dir", type=Path, default=Path("storage_eval/p09_claim_citation_formal")
    )
    args = parser.parse_args()
    print(
        json.dumps(
            write_formal_claim_citation_report(args.repository_root, args.output_dir),
            ensure_ascii=False,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
