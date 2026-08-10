from __future__ import annotations

import argparse
import json
from collections.abc import Mapping
from pathlib import Path
from typing import cast

from pydantic import JsonValue

from evaluation.io import atomic_write_json
from evaluation.manifest import sha256_file
from evaluation.p09_dev_loader import P09DevCase, load_p09_dev_bundle
from evaluation.p09_retrieval_qa_eval import (
    P09EvaluationSystem,
    P09SystemResult,
    _aggregate_cases,
    run_p09_dev,
)

SOURCE_REPORT_SHA256 = "b04fc9b620fccddecaf889c201fa5b8d0cec139b92686a2ac354dffed853f77b"
Q2_SOURCE_REPORT_SHA256 = "8cf07e7026a58a8750ff455101440b9338f7713b9a51ed28dc52ad59b2f7f197"
RETRIEVAL_SNAPSHOT_SHA256 = "d85d9603965ecad620d62e39d2fde15f4b2857d180b9aba2379a568a59656602"
APPROVED_BUNDLE_SHA256 = "5a84bac041375310d5bb80f17f7481464d07dbcf75f9f980c6b8a030e58af0c1"
FORMAL_REPORT_SHA256 = "652d2a08dcd1c7b175002fc5f4d32ec1beb71bbc2991a81b6a6175c746a9c392"
DELTA_DEEPSEEK_TOKEN_CAP = 180_000
PHASE_DEEPSEEK_TOKEN_CAP = 2_500_000
PHASE_DEEPSEEK_TOKENS_BEFORE = 824_734

FRESH_CASE_IDS = (
    "gold-qa-01fd462adc1638a1a81fcabdf58e0ac9",
    "gold-qa-0ce2025962b5691d0cb3f1522ed1aaa8",
    "gold-qa-10caf16efab833ad40e600359b5239c2",
    "gold-qa-2b8972b47de56a5b6b62e68091320557",
    "gold-qa-3513e4ae011f3940d8b22e9133f521e6",
    "gold-qa-574fc80decab989823e88f69bc850f15",
    "gold-qa-730f317833bc4b6f6d458f42814069be",
    "gold-qa-74304d145c41aaf7ea44b17108ef39ef",
    "gold-qa-7efcb21383c840fa94d106b878b972b1",
    "gold-qa-ae7a2fadc743507c01dc579c6a728f06",
    "gold-qa-f287be490a3c23fdd7bc3d027b70051a",
    "gold-qa-f6ec6bb28fa466f2958eb45ee887480e",
)


class GenerationReliabilityDeltaSystem:
    def __init__(
        self,
        *,
        fresh_system: P09EvaluationSystem,
        fixed_results: Mapping[str, P09SystemResult],
        profile_sha256: str,
    ) -> None:
        self.fresh_system = fresh_system
        self.fixed_results = fixed_results
        self.label = f"generation-reliability-delta-v1:{profile_sha256}"

    def run(self, case: P09DevCase) -> P09SystemResult:
        if case.qa.record_id in FRESH_CASE_IDS:
            return self.fresh_system.run(case)
        return self.fixed_results[case.qa.record_id].model_copy(deep=True)


def prepare_protocol(repository_root: Path, output_dir: Path) -> tuple[Path, str]:
    root = repository_root.resolve()
    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    paths = _paths(root)
    _validate_fixed_inputs(paths)
    profile_sha256 = sha256_file(paths["profile"])
    payload: dict[str, JsonValue] = {
        "schema_version": "courserag.p09-generation-reliability-protocol.v1",
        "status": "preregistered_before_provider_calls",
        "approved_by_course_owner": True,
        "approved_on": "2026-08-10",
        "scope": "approved_dev_delta_only",
        "test_access": False,
        "external_data_authorized": True,
        "single_candidate_only": True,
        "post_run_prompt_tuning_allowed": False,
        "approved_bundle_sha256": APPROVED_BUNDLE_SHA256,
        "source_answer_grounding_report_sha256": SOURCE_REPORT_SHA256,
        "q2_source_report_sha256": Q2_SOURCE_REPORT_SHA256,
        "formal_claim_citation_report_sha256": FORMAL_REPORT_SHA256,
        "b7_retrieval_snapshot_sha256": RETRIEVAL_SNAPSHOT_SHA256,
        "generation_reliability_profile_sha256": profile_sha256,
        "fresh_case_ids": list(FRESH_CASE_IDS),
        "fresh_case_count": len(FRESH_CASE_IDS),
        "reuse_policy": "exact_source_report_result_for_non_delta_cases",
        "deepseek_additional_token_cap": DELTA_DEEPSEEK_TOKEN_CAP,
        "p09_phase_tokens_before": PHASE_DEEPSEEK_TOKENS_BEFORE,
        "p09_phase_total_token_cap": PHASE_DEEPSEEK_TOKEN_CAP,
        "cohere_additional_search_units": 0,
        "automatic_gates": {
            "qa_failure_rate": 0,
            "factoid_short_answer_f1_min": 0.40610823798540377,
            "claim_citation_completeness": 1,
            "citation_resolvability": 1,
            "unanswerable_recall": 1,
            "false_answer_rate": 0,
            "fallback_count": 0,
            "approved_list_cases_answered_with_cited_items": True,
        },
        "formal_protection_floors": {
            "gold_claim_coverage": 0.8461538461538461,
            "correct_claim_precision": 0.95,
            "unsupported_claim_rate_max": 0.05,
            "citation_precision": 0.95,
            "citation_recall": 0.80,
            "citation_f1": 0.87,
            "answerability_f1": 0.98,
            "conciseness_pass_rate": 0.95,
        },
    }
    path = output_dir / "protocol_manifest.json"
    atomic_write_json(path, payload)
    return path, sha256_file(path)


def run_delta(
    *,
    repository_root: Path,
    output_dir: Path,
    external_data_authorized: bool,
    resume: bool = False,
) -> tuple[Path, Path, Path, str]:
    if not external_data_authorized:
        raise RuntimeError(
            "P09 Generation Reliability requires explicit external-data authorization"
        )
    root = repository_root.resolve()
    output_dir = output_dir.resolve()
    paths = _paths(root)
    _validate_fixed_inputs(paths)
    protocol_path = output_dir / "protocol_manifest.json"
    _validate_protocol(protocol_path, paths["profile"])

    from core.settings import settings
    from evaluation.p09_systems import build_formal_p09_suite

    source = json.loads(paths["source_report"].read_text(encoding="utf-8"))
    fixed_results = _results(source, "q3")
    run_dir = output_dir / "run-1"
    checkpoint_path = run_dir / "checkpoint.json" if resume else None
    suite = build_formal_p09_suite(
        root,
        settings,
        checkpoint_path=checkpoint_path,
        retrieval_snapshot_path=paths["snapshot"],
        max_deepseek_tokens=DELTA_DEEPSEEK_TOKEN_CAP,
        max_cohere_search_units=0,
        label_suffix="generation-reliability-delta-v1",
        generation_reliability_enabled=True,
    )
    profile_sha256 = sha256_file(paths["profile"])
    system = GenerationReliabilityDeltaSystem(
        fresh_system=suite.system("q3"),
        fixed_results=fixed_results,
        profile_sha256=profile_sha256,
    )
    report = run_p09_dev(
        repository_root=root,
        output_dir=run_dir,
        run_id="p09-generation-reliability-delta-run-1",
        systems={"q3": system},
        resume=resume,
        max_deepseek_tokens=DELTA_DEEPSEEK_TOKEN_CAP,
        max_cohere_search_units=0,
        governance_amendments=[
            {
                "protocol_manifest_sha256": sha256_file(protocol_path),
                "generation_reliability_profile_sha256": profile_sha256,
                "fresh_case_count": len(FRESH_CASE_IDS),
                "deepseek_additional_token_cap": DELTA_DEEPSEEK_TOKEN_CAP,
                "p09_phase_total_token_cap": PHASE_DEEPSEEK_TOKEN_CAP,
                "cohere_additional_search_units": 0,
            }
        ],
    )
    evaluation = output_dir / "automatic_gate_report.json"
    _write_automatic_gate(root, report, evaluation)
    usage_audit = output_dir / "usage_audit.json"
    _write_usage_audit(report, usage_audit)
    return report, evaluation, usage_audit, sha256_file(evaluation)


def _write_automatic_gate(root: Path, report_path: Path, output_path: Path) -> None:
    bundle = load_p09_dev_bundle(root / "datasets/courserag_eval/v1")
    main = [case for case in bundle.cases if case.qa.evaluation_stratum == "retrieval_main"]
    candidate = json.loads(report_path.read_text(encoding="utf-8"))
    q2_source = json.loads(_paths(root)["q2_report"].read_text(encoding="utf-8"))
    q3 = _results(candidate, "q3")
    q2 = _results(q2_source, "q2")
    q3_metrics = _aggregate_cases(main, q3)
    q2_metrics = _aggregate_cases(main, q2)
    list_cases = [case for case in main if case.qa.gold_answer_type == "list"]
    list_contract_ok = all(
        q3[case.qa.record_id].answer_status == "answered"
        and bool(q3[case.qa.record_id].answer)
        and bool(q3[case.qa.record_id].list_items)
        and bool(q3[case.qa.record_id].claims)
        and all(claim.evidence_ids for claim in q3[case.qa.record_id].claims)
        and all(q3[case.qa.record_id].resolvable_citations)
        for case in list_cases
    )
    fallback_count = int(candidate["report"]["systems"]["q3"]["fallback_count"])
    checks = {
        "qa_failure_rate_0": _number(q3_metrics, "qa_failure_rate") == 0,
        "factoid_short_answer_f1_q2_delta": _number(q3_metrics, "short_answer_token_f1")
        >= _number(q2_metrics, "short_answer_token_f1") - 0.02,
        "claim_citation_completeness_1": _number(q3_metrics, "claim_citation_completeness") == 1,
        "citation_resolvability_1": _number(q3_metrics, "citation_resolvability") == 1,
        "unanswerable_recall_1": _number(q3_metrics, "unanswerable_recall") == 1,
        "false_answer_rate_0": _number(q3_metrics, "false_answer_rate") == 0,
        "fallback_count_0": fallback_count == 0,
        "approved_list_cases_answered_with_cited_items": list_contract_ok,
        "dev_only": candidate["report"].get("test_access") is False,
    }
    payload: dict[str, JsonValue] = {
        "schema_version": "courserag.p09-generation-reliability-automatic-gate.v1",
        "status": (
            "automatic_pass_human_delta_review_required"
            if all(checks.values())
            else "failed_no_further_tuning"
        ),
        "scope": "approved_dev_delta_plus_hash_locked_reuse",
        "test_access": False,
        "source_report_sha256": SOURCE_REPORT_SHA256,
        "candidate_report_sha256": sha256_file(report_path),
        "fresh_case_ids": list(FRESH_CASE_IDS),
        "q2_metrics": q2_metrics,
        "q3_metrics": q3_metrics,
        "checks": cast(dict[str, JsonValue], checks),
        "formal_metrics_pending_owner_delta_review": True,
        "freeze_candidate_written": False,
    }
    atomic_write_json(output_path, payload)


def _write_usage_audit(report_path: Path, output_path: Path) -> None:
    report = json.loads(report_path.read_text(encoding="utf-8"))
    results = _results(report, "q3")
    fresh_tokens = sum(
        _json_int(results[case_id].usage.get("deepseek_total_tokens", 0))
        for case_id in FRESH_CASE_IDS
    )
    phase_after = PHASE_DEEPSEEK_TOKENS_BEFORE + fresh_tokens
    if fresh_tokens > DELTA_DEEPSEEK_TOKEN_CAP:
        raise RuntimeError("P09 Generation Reliability DeepSeek cap exceeded")
    if phase_after > PHASE_DEEPSEEK_TOKEN_CAP:
        raise RuntimeError("P09 phase DeepSeek cap exceeded")
    payload: dict[str, JsonValue] = {
        "schema_version": "courserag.p09-generation-reliability-usage-audit.v1",
        "status": "within_authorized_limits",
        "fresh_case_count": len(FRESH_CASE_IDS),
        "deepseek_tokens": fresh_tokens,
        "deepseek_token_cap": DELTA_DEEPSEEK_TOKEN_CAP,
        "phase_deepseek_tokens_before": PHASE_DEEPSEEK_TOKENS_BEFORE,
        "phase_deepseek_tokens_after": phase_after,
        "phase_deepseek_token_cap": PHASE_DEEPSEEK_TOKEN_CAP,
        "cohere_search_units": 0,
        "cohere_search_unit_cap": 0,
    }
    atomic_write_json(output_path, payload)


def _paths(root: Path) -> dict[str, Path]:
    return {
        "source_report": root / "storage_eval/p09_answer_grounding/run-1/report.json",
        "q2_report": root / "storage_eval/p09_query_context_qa/run-1/report.json",
        "formal_report": root / "storage_eval/p09_claim_citation_formal/formal_report.json",
        "snapshot": root / "storage_eval/p09_gate_repair/b7_retrieval_snapshot.json",
        "profile": root / "resources/qa_profiles/p09_generation_reliability_candidate_v1.json",
    }


def _validate_fixed_inputs(paths: Mapping[str, Path]) -> None:
    expected = {
        "source_report": SOURCE_REPORT_SHA256,
        "q2_report": Q2_SOURCE_REPORT_SHA256,
        "formal_report": FORMAL_REPORT_SHA256,
        "snapshot": RETRIEVAL_SNAPSHOT_SHA256,
    }
    for key, digest in expected.items():
        path = paths[key]
        if not path.is_file() or sha256_file(path) != digest:
            raise ValueError(f"P09 Generation Reliability input identity differs: {key}")


def _validate_protocol(path: Path, profile_path: Path) -> None:
    if not path.is_file():
        raise FileNotFoundError("Generation Reliability requires the preregistered Protocol")
    payload = json.loads(path.read_text(encoding="utf-8"))
    expected = {
        "status": "preregistered_before_provider_calls",
        "external_data_authorized": True,
        "single_candidate_only": True,
        "post_run_prompt_tuning_allowed": False,
        "test_access": False,
        "deepseek_additional_token_cap": DELTA_DEEPSEEK_TOKEN_CAP,
        "cohere_additional_search_units": 0,
        "generation_reliability_profile_sha256": sha256_file(profile_path),
    }
    for key, value in expected.items():
        if payload.get(key) != value:
            raise ValueError(f"P09 Generation Reliability Protocol has invalid {key}")
    if tuple(payload.get("fresh_case_ids", ())) != FRESH_CASE_IDS:
        raise ValueError("P09 Generation Reliability Protocol changed the Fresh Case set")


def _results(report: Mapping[str, object], variant: str) -> dict[str, P09SystemResult]:
    cases = cast(dict[str, dict[str, object]], report["cases"])
    return {
        key.split(":", 1)[1]: P09SystemResult.model_validate(state["result"])
        for key, state in cases.items()
        if key.startswith(f"{variant}:") and state.get("status") == "succeeded"
    }


def _number(payload: Mapping[str, JsonValue], key: str) -> float:
    value = payload.get(key, 0.0)
    if isinstance(value, bool) or not isinstance(value, int | float | str):
        return 0.0
    return float(value)


def _json_int(value: JsonValue | None) -> int:
    if isinstance(value, bool) or not isinstance(value, int | float | str):
        return 0
    return int(value)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the P09 Generation Reliability delta")
    parser.add_argument("--repository-root", type=Path, default=Path.cwd())
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--prepare", action="store_true")
    parser.add_argument("--external-data-authorized", action="store_true")
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    if args.prepare:
        path, digest = prepare_protocol(args.repository_root, args.output_dir)
        print(json.dumps({"protocol": str(path), "sha256": digest}, ensure_ascii=False))
        return
    report, evaluation, usage, digest = run_delta(
        repository_root=args.repository_root,
        output_dir=args.output_dir,
        external_data_authorized=args.external_data_authorized,
        resume=args.resume,
    )
    print(
        json.dumps(
            {
                "report": str(report),
                "automatic_gate": str(evaluation),
                "automatic_gate_sha256": digest,
                "usage_audit": str(usage),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
