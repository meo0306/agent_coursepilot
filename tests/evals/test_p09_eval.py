import json
from pathlib import Path

import pytest

from courserag.contracts.retrieval import SearchResponse
from evaluation.p09_dev_loader import P09DevCase
from evaluation.p09_retrieval_qa_eval import (
    P09ClaimResult,
    P09SystemResult,
    P09UsageBudget,
    _validate_answer_grounding_inputs,
    run_p09_dev,
    write_p09_freeze_candidate,
)
from evaluation.p09_systems import (
    _load_retrieval_snapshot,
    _query_state_from_search,
    _restored_cohere_budget,
    _restored_deepseek_budget,
)

ROOT = Path(__file__).resolve().parents[2]


class GoldEchoSystem:
    label = "fake-gold-echo-for-runner-contract-only"

    def run(self, case: P09DevCase) -> P09SystemResult:
        evidence_ids = list(case.context.relevant_evidence_ids)
        return P09SystemResult(
            intent_route={
                "exact_fact": "fact",
                "paraphrase": "fact",
                "definition": "definition",
                "comparison": "comparison",
                "procedure": "procedure",
                "application": "example_application",
                "cross_section": "cross_section",
                "unanswerable": None,
            }[case.qa.query_type],
            retrieval_strategy="hybrid_retrieval",
            selected_evidence_ids=evidence_ids,
            context_token_count=len(evidence_ids),
            context_item_count=len(evidence_ids),
            answer_status="answered" if case.qa.answerable else "abstained_insufficient_evidence",
            answer="contract result" if case.qa.answerable else None,
            claims=[
                P09ClaimResult(text=claim.claim_text, evidence_ids=claim.required_evidence_ids)
                for claim in case.qa.gold_claims
            ],
            resolvable_citations=[True for _value in evidence_ids],
        )


def test_p09_runner_is_dev_only_checkpointed_and_freeze_candidate_is_pending(
    tmp_path: Path,
) -> None:
    report_path = run_p09_dev(
        repository_root=ROOT,
        output_dir=tmp_path / "run",
        run_id="p09-runner-contract",
        systems={"q3": GoldEchoSystem()},
    )
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["report"]["test_access"] is False
    assert report["report"]["retrieval_main_count"] == 54
    assert report["report"]["upstream_gap_diagnostic_count"] == 6
    assert len(report["cases"]) == 60
    main_metrics = report["report"]["systems"]["q3"]["retrieval_main_metrics"]
    assert main_metrics["claim_citation_completeness"] == 1.0
    assert main_metrics["citation_resolvability"] == 1.0
    assert main_metrics["qa_failure_rate"] == 0.0
    candidate = tmp_path / "freeze_candidate.json"
    digest = write_p09_freeze_candidate(report_path, candidate)
    assert len(digest) == 64
    assert (
        json.loads(candidate.read_text(encoding="utf-8"))["status"]
        == "pending_course_owner_approval"
    )


def test_p09_usage_budget_fails_before_crossing_limits() -> None:
    budget = P09UsageBudget(max_deepseek_tokens=10, max_cohere_search_units=2)
    budget.reserve(deepseek_tokens=8, cohere_search_units=1)
    with pytest.raises(RuntimeError, match="DeepSeek"):
        budget.reserve(deepseek_tokens=3)
    with pytest.raises(RuntimeError, match="Cohere"):
        budget.reserve(cohere_search_units=2)


def test_p09_resume_restores_cumulative_cohere_usage_watermark() -> None:
    first = P09SystemResult(usage={"cohere_search_units": 7})
    later = P09SystemResult(usage={"cohere_search_units": 11})

    assert _restored_cohere_budget({("b7", "first"): first, ("b7", "later"): later}) == 11


def test_p09_resume_restores_deepseek_cumulative_and_incremental_usage() -> None:
    first = P09SystemResult(usage={"deepseek_total_tokens": 7}, usage_is_cumulative=True)
    later = P09SystemResult(usage={"deepseek_total_tokens": 11}, usage_is_cumulative=True)
    repair = P09SystemResult(usage={"deepseek_total_tokens": 5}, usage_is_cumulative=False)

    assert (
        _restored_deepseek_budget(
            {("q3", "first"): first, ("q3", "later"): later, ("q3", "repair"): repair}
        )
        == 16
    )


def test_answer_grounding_inputs_are_exact_and_restore_all_dev_searches() -> None:
    protocol = ROOT / "storage_eval/p09_answer_grounding/protocol_manifest.json"
    profile = ROOT / "resources/qa_profiles/p09_answer_grounding_candidate_v1.json"
    snapshot = ROOT / "storage_eval/p09_gate_repair/b7_retrieval_snapshot.json"

    _validate_answer_grounding_inputs(protocol, profile, snapshot)
    restored = _load_retrieval_snapshot(snapshot)

    assert len(restored) == 60
    assert all(variant == "b7" for variant, _case_id in restored)
    assert all(result.search_snapshot is not None for result in restored.values())
    assert all(result.usage == {} for result in restored.values())


def test_p09_resume_rehydrates_query_state_from_full_search_snapshot() -> None:
    response = SearchResponse.model_validate(
        {
            "meta": {
                "request_id": "request-1",
                "trace_id": "trace-1",
                "api_version": "v1",
                "service_version": "test",
                "duration_ms": 0,
            },
            "query": {
                "original": "比较两个章节",
                "normalized": "比较两个章节",
                "rewrites": ["章节一与章节二的差异"],
                "intent_route": "comparison",
                "intent_rule_id": "intent.comparison.explicit_relation.v2",
                "intent_reason": "explicit comparison wording",
                "minimum_source_count": 2,
                "retrieval_strategy": "hybrid_retrieval",
            },
            "hits": [],
            "retrieval": {
                "retrieval_config_version": "test",
                "index_version": "index-1",
                "candidate_count": 0,
                "returned_count": 0,
            },
        }
    )

    restored = _query_state_from_search(response)

    assert restored.intent_route.value == "comparison"
    assert restored.minimum_source_count == 2
    assert restored.rewrites == ("章节一与章节二的差异",)
