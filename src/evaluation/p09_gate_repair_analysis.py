from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from pathlib import Path
from typing import cast

from pydantic import JsonValue

from courserag.qa.citations import (
    CITATION_COMPOSER_VERSION,
    compose_claim_evidence_ids,
)
from evaluation.io import atomic_write_json
from evaluation.manifest import sha256_file
from evaluation.p09_corpus import load_p09_runtime_corpus
from evaluation.p09_dev_loader import P09DevCase, load_p09_dev_bundle
from evaluation.p09_retrieval_qa_eval import (
    P09ClaimResult,
    P09SystemResult,
    _aggregate_cases,
    _intent_gold,
)

PROTOCOL_VERSION = "p09-freeze-gate-evaluation-r2"


def write_shadow_report(repository_root: Path, output_path: Path) -> str:
    root = repository_root.resolve()
    dataset_root = root / "datasets/courserag_eval/v1"
    bundle = load_p09_dev_bundle(dataset_root)
    main = [case for case in bundle.cases if case.qa.evaluation_stratum == "retrieval_main"]
    final_path = root / "storage_eval/p09_gate_repair/repair-run-1/report.json"
    old_path = root / "storage_eval/p09_query_context_qa/run-1/report.json"
    final = json.loads(final_path.read_text(encoding="utf-8"))
    old = json.loads(old_path.read_text(encoding="utf-8"))
    baseline = _results(final, "q3")
    corpus = load_p09_runtime_corpus(root)
    evidence_texts = {
        gold_id: corpus.evidence_by_id[system_id].text
        for system_id, gold_id in corpus.gold_by_system_evidence.items()
        if system_id in corpus.evidence_by_id
    }
    shadow = {
        case_id: _compose_result(result, evidence_texts) for case_id, result in baseline.items()
    }
    baseline_metrics = _aggregate_cases(main, baseline)
    shadow_metrics = _aggregate_cases(main, shadow)
    q2_metrics = _aggregate_cases(main, _results(old, "q2"))
    b7_metrics = cast(
        dict[str, JsonValue], final["report"]["systems"]["b7"]["retrieval_main_metrics"]
    )
    b8_metrics = cast(
        dict[str, JsonValue], final["report"]["systems"]["b8"]["retrieval_main_metrics"]
    )
    class_recall = _intent_recall(main, shadow)
    before_projection = _projection_sha256(baseline)
    after_projection = _projection_sha256(shadow)
    checks = _checks(
        shadow_metrics=shadow_metrics,
        q2_metrics=q2_metrics,
        b7_metrics=b7_metrics,
        b8_metrics=b8_metrics,
        class_recall=class_recall,
        projection_unchanged=before_projection == after_projection,
    )
    payload: dict[str, JsonValue] = {
        "schema_version": "courserag.p09-gate-repair-shadow.v1",
        "protocol_version": PROTOCOL_VERSION,
        "status": "invalid_for_freeze_gold_side_candidate_filter",
        "scope": "approved_dev_shadow_only",
        "test_access": False,
        "freeze_eligible": False,
        "diagnostic_warning": (
            "Shadow Composer candidates were filtered through Gold-mapped Evidence; "
            "all overlap metrics are diagnostic only and cannot support a Freeze."
        ),
        "source_report_sha256": sha256_file(final_path),
        "q2_source_report_sha256": sha256_file(old_path),
        "composer_version": CITATION_COMPOSER_VERSION,
        "baseline_metrics": baseline_metrics,
        "shadow_metrics": shadow_metrics,
        "q2_metrics": q2_metrics,
        "b7_metrics": b7_metrics,
        "b8_metrics": b8_metrics,
        "intent_recall_by_class": cast(dict[str, JsonValue], class_recall),
        "non_citation_projection_before_sha256": before_projection,
        "non_citation_projection_after_sha256": after_projection,
        "checks": cast(dict[str, JsonValue], checks),
        "changed_claim_count": sum(
            before.claims != shadow[case_id].claims for case_id, before in baseline.items()
        ),
        "provider_calls": {"cohere": 0, "deepseek": 0},
    }
    atomic_write_json(output_path, payload)
    return sha256_file(output_path)


def write_answer_grounding_report(
    repository_root: Path,
    answer_grounding_report_path: Path,
    output_path: Path,
) -> str:
    root = repository_root.resolve()
    dataset_root = root / "datasets/courserag_eval/v1"
    bundle = load_p09_dev_bundle(dataset_root)
    main = [case for case in bundle.cases if case.qa.evaluation_stratum == "retrieval_main"]
    gate_path = root / "storage_eval/p09_gate_repair/repair-run-1/report.json"
    original_path = root / "storage_eval/p09_query_context_qa/run-1/report.json"
    candidate = json.loads(answer_grounding_report_path.read_text(encoding="utf-8"))
    gate = json.loads(gate_path.read_text(encoding="utf-8"))
    original = json.loads(original_path.read_text(encoding="utf-8"))
    q3_results = _results(candidate, "q3")
    q3_metrics = _aggregate_cases(main, q3_results)
    q2_metrics = _aggregate_cases(main, _results(original, "q2"))
    b7_metrics = cast(
        dict[str, JsonValue], gate["report"]["systems"]["b7"]["retrieval_main_metrics"]
    )
    b8_metrics = cast(
        dict[str, JsonValue], gate["report"]["systems"]["b8"]["retrieval_main_metrics"]
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
    q3_system = candidate["report"]["systems"]["q3"]
    checks.update(
        {
            "dev_only": candidate["report"].get("test_access") is False,
            "fallback_count_0": q3_system.get("fallback_count") == 0,
            "all_answered_claims_resolvable": _all_answered_claims_resolvable(q3_results),
        }
    )
    payload: dict[str, JsonValue] = {
        "schema_version": "courserag.p09-answer-grounding-evaluation.v1",
        "protocol_version": PROTOCOL_VERSION,
        "status": "passed" if all(checks.values()) else "failed",
        "scope": "approved_dev_answer_grounding_only",
        "test_access": False,
        "source_report_sha256": sha256_file(answer_grounding_report_path),
        "q2_source_report_sha256": sha256_file(original_path),
        "b7_b8_source_report_sha256": sha256_file(gate_path),
        "q3_metrics": q3_metrics,
        "q2_metrics": q2_metrics,
        "b7_metrics": b7_metrics,
        "b8_metrics": b8_metrics,
        "intent_recall_by_class": cast(dict[str, JsonValue], class_recall),
        "checks": cast(dict[str, JsonValue], checks),
        "provider_calls": {"cohere": 0, "deepseek": "fresh_q3_only"},
        "runtime_default_activated": False,
    }
    atomic_write_json(output_path, payload)
    return sha256_file(output_path)


def _results(report: dict[str, object], variant: str) -> dict[str, P09SystemResult]:
    cases = cast(dict[str, dict[str, object]], report["cases"])
    return {
        key.split(":", 1)[1]: P09SystemResult.model_validate(state["result"])
        for key, state in cases.items()
        if key.startswith(f"{variant}:")
    }


def _compose_result(result: P09SystemResult, evidence_texts: dict[str, str]) -> P09SystemResult:
    if result.answer_status != "answered":
        return result.model_copy(deep=True)
    candidates = {
        evidence_id: evidence_texts[evidence_id]
        for evidence_id in result.selected_evidence_ids
        if evidence_id in evidence_texts
    }
    claims = [
        P09ClaimResult(
            text=claim.text,
            evidence_ids=list(compose_claim_evidence_ids(claim.text, candidates)),
        )
        for claim in result.claims
    ]
    return result.model_copy(update={"claims": claims}, deep=True)


def _projection_sha256(results: dict[str, P09SystemResult]) -> str:
    payload: dict[str, object] = {}
    for case_id, result in sorted(results.items()):
        value = result.model_dump(mode="json")
        value["claims"] = [{"text": claim["text"]} for claim in value["claims"]]
        value.pop("resolvable_citations", None)
        payload[case_id] = value
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _intent_recall(
    cases: list[P09DevCase], results: dict[str, P09SystemResult]
) -> dict[str, float]:
    totals: dict[str, int] = defaultdict(int)
    matches: dict[str, int] = defaultdict(int)
    for case in cases:
        if case.qa.query_type == "unanswerable":
            continue
        expected = _intent_gold(case.qa.query_type)
        totals[expected] += 1
        matches[expected] += results[case.qa.record_id].intent_route == expected
    return {key: matches[key] / value for key, value in sorted(totals.items())}


def _all_answered_claims_resolvable(results: dict[str, P09SystemResult]) -> bool:
    return all(
        result.answer_status != "answered"
        or (
            bool(result.claims)
            and all(claim.evidence_ids for claim in result.claims)
            and bool(result.resolvable_citations)
            and all(result.resolvable_citations)
        )
        for result in results.values()
    )


def _checks(
    *,
    shadow_metrics: dict[str, JsonValue],
    q2_metrics: dict[str, JsonValue],
    b7_metrics: dict[str, JsonValue],
    b8_metrics: dict[str, JsonValue],
    class_recall: dict[str, float],
    projection_unchanged: bool,
) -> dict[str, bool]:
    def number(payload: dict[str, JsonValue], key: str) -> float:
        value = payload.get(key, 0.0)
        if isinstance(value, bool) or not isinstance(value, int | float | str):
            return 0.0
        return float(value)

    return {
        "non_citation_projection_unchanged": projection_unchanged,
        "claim_citation_completeness_1": number(shadow_metrics, "claim_citation_completeness") == 1,
        "citation_resolvability_1": number(shadow_metrics, "citation_resolvability") == 1,
        "qa_failure_rate_0": number(shadow_metrics, "qa_failure_rate") == 0,
        "unanswerable_recall_1": number(shadow_metrics, "unanswerable_recall") == 1,
        "false_answer_rate_0": number(shadow_metrics, "false_answer_rate") == 0,
        "b8_context_coverage_delta": number(b8_metrics, "context_gold_evidence_coverage")
        >= number(b7_metrics, "context_gold_evidence_coverage") - 0.02,
        "b8_complete_group_delta": number(b8_metrics, "complete_group_coverage")
        >= number(b7_metrics, "complete_group_coverage") - 0.02,
        "context_coverage_floor": number(b8_metrics, "context_gold_evidence_coverage") >= 0.75,
        "complete_group_floor": number(b8_metrics, "complete_group_coverage") >= 0.70,
        "formal_claim_citation_review_available": False,
        "short_answer_token_f1_q2_delta": number(shadow_metrics, "short_answer_token_f1")
        >= number(q2_metrics, "short_answer_token_f1") - 0.02,
        "list_set_f1_q2_delta": number(shadow_metrics, "list_set_f1")
        >= number(q2_metrics, "list_set_f1") - 0.02,
        "intent_accuracy_floor": number(shadow_metrics, "intent_accuracy") >= 0.80,
        "intent_class_recall_floor": all(value >= 0.60 for value in class_recall.values()),
        "definition_cross_section_floor": all(
            class_recall.get(key, 0.0) >= 0.75 for key in ("definition", "cross_section")
        ),
        "false_abstention_ceiling": number(shadow_metrics, "false_abstention_rate") <= 0.0625,
    }
