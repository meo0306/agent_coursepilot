from courserag.contracts.common import RequestContext, ResponseMeta
from courserag.contracts.qa import AnswerStatus, QARequest
from courserag.contracts.retrieval import (
    ContextItem,
    ContextPackage,
    EvidenceSummary,
    PackingReport,
)
from courserag.qa import (
    CitedQAService,
    EvidenceSufficiencyGate,
    GeneratedClaim,
    ProviderQAResult,
    StructuredQAOutput,
)
from courserag.qa.models import GeneratedListItem
from courserag.query.answer_shape import AnswerShapeDecision


def _context(*, evidence_ids: tuple[str, ...] = ("ev-a",)) -> ContextPackage:
    context = RequestContext(request_id="req", trace_id="trace")
    summaries = {
        value: EvidenceSummary(
            evidence_id=value,
            document_id=f"document-{index}",
            document_version_id="version-1",
            section_id=f"section-{index}",
            content_sha256=str(index) * 64,
        )
        for index, value in enumerate(evidence_ids, start=1)
    }
    return ContextPackage(
        meta=ResponseMeta.from_context(context),
        query="question",
        purpose="question_answering",
        items=[
            ContextItem(
                context_item_id=f"ctx-{value}",
                text=f"text {value}",
                evidence_ids=[value],
                token_count=2,
                content_sha256=str(index) * 64,
            )
            for index, value in enumerate(evidence_ids, start=1)
        ],
        token_count=2 * len(evidence_ids),
        evidence_map=summaries,
        retrieval_trace_id="retrieval-run",
        index_version="index-1",
        packing_report=PackingReport(
            candidate_count=len(evidence_ids),
            selected_count=len(evidence_ids),
            deduplicated_count=0,
            discarded_for_budget=0,
        ),
        context_package_id="context-1",
    )


class Provider:
    def __init__(self, *, invalid_first: bool | str = False, invalid_repair: bool = False) -> None:
        self.invalid_first = invalid_first
        self.invalid_repair = invalid_repair

    def generate(
        self,
        question: str,
        context: ContextPackage,
        *,
        answer_shape: AnswerShapeDecision,
    ) -> ProviderQAResult:
        if self.invalid_first == "raise":
            raise ValueError("invalid provider JSON")
        evidence_id = "outside" if self.invalid_first else next(iter(context.evidence_map))
        return self._result(evidence_id)

    def repair(
        self,
        question: str,
        context: ContextPackage,
        *,
        error: str,
        answer_shape: AnswerShapeDecision,
    ) -> ProviderQAResult:
        evidence_id = "outside" if self.invalid_repair else next(iter(context.evidence_map))
        return self._result(evidence_id)

    @staticmethod
    def _result(evidence_id: str) -> ProviderQAResult:
        return ProviderQAResult(
            output=StructuredQAOutput(
                status="answered",
                answer="answer",
                claims=(GeneratedClaim(text="claim", evidence_ids=(evidence_id,)),),
            ),
            provider="fake",
            model="fake",
            prompt_version="v1",
            raw_response_sha256="a" * 64,
        )


def test_sufficiency_rejects_empty_or_low_score_context() -> None:
    context = _context(evidence_ids=())
    decision = EvidenceSufficiencyGate().evaluate(
        context, top_rerank_score=0.9, intent_route="fact"
    )
    assert not decision.sufficient
    assert "NO_EVIDENCE" in decision.reasons
    decision = EvidenceSufficiencyGate().evaluate(
        _context(), top_rerank_score=0.1, intent_route="fact"
    )
    assert "RERANK_BELOW_THRESHOLD" in decision.reasons
    decision = EvidenceSufficiencyGate().evaluate(
        _context(),
        top_rerank_score=0.9,
        intent_route="fact",
        minimum_source_count=2,
    )
    assert "MULTI_SOURCE_COVERAGE_INSUFFICIENT" in decision.reasons


def test_answer_claims_and_citations_only_use_context_evidence() -> None:
    request = QARequest(course_id="course", question="question")
    response = CitedQAService(provider=Provider(), gate=EvidenceSufficiencyGate()).answer(
        request,
        context=_context(),
        top_rerank_score=0.9,
        intent_route="fact",
    )
    assert response.answer_status == AnswerStatus.ANSWERED
    assert response.used_evidence_ids == ["ev-a"]
    assert response.claims[0].evidence_ids == ["ev-a"]
    assert response.citations[0].document_id == "document-1"


def test_one_targeted_repair_then_fail_closed() -> None:
    request = QARequest(course_id="course", question="question")
    repaired = CitedQAService(
        provider=Provider(invalid_first=True), gate=EvidenceSufficiencyGate()
    ).answer(request, context=_context(), top_rerank_score=0.9, intent_route="fact")
    assert repaired.answer_status == AnswerStatus.ANSWERED
    assert repaired.validation_summary["repair_count"] == 1
    failed = CitedQAService(
        provider=Provider(invalid_first=True, invalid_repair=True),
        gate=EvidenceSufficiencyGate(),
    ).answer(request, context=_context(), top_rerank_score=0.9, intent_route="fact")
    assert failed.answer_status == AnswerStatus.FAILED
    assert failed.answer is None
    assert failed.validation_summary["initial_error_code"] == "EVIDENCE_OUTSIDE_CONTEXT"
    assert failed.validation_summary["repair_error_code"] == "EVIDENCE_OUTSIDE_CONTEXT"


def test_raw_provider_json_failure_also_gets_exactly_one_repair() -> None:
    request = QARequest(course_id="course", question="question")
    provider = Provider(invalid_first=True)
    provider.invalid_first = "raise"
    repaired = CitedQAService(provider=provider, gate=EvidenceSufficiencyGate()).answer(
        request, context=_context(), top_rerank_score=0.9, intent_route="fact"
    )
    assert repaired.answer_status == AnswerStatus.ANSWERED
    assert repaired.validation_summary["repair_count"] == 1


class ListProvider(Provider):
    @staticmethod
    def _result(evidence_id: str) -> ProviderQAResult:
        return ProviderQAResult(
            output=StructuredQAOutput(
                status="answered",
                answer_type="list",
                answer="简洁摘要。",
                claims=(),
                list_items=(
                    GeneratedListItem(text="明细一", evidence_ids=(evidence_id,)),
                    GeneratedListItem(text="明细二", evidence_ids=(evidence_id,)),
                ),
            ),
            provider="fake",
            model="fake",
            prompt_version="p09_generation_reliability_list_v1",
            raw_response_sha256="b" * 64,
        )


def test_list_summary_is_not_replaced_by_concatenated_detail_items() -> None:
    response = CitedQAService(provider=ListProvider(), gate=EvidenceSufficiencyGate()).answer(
        QARequest(course_id="course", question="列出了哪些事实？"),
        context=_context(),
        top_rerank_score=0.9,
        intent_route="fact",
    )
    assert response.answer == "简洁摘要。"
    assert response.list_items == ["明细一", "明细二"]
    assert [claim.text for claim in response.claims] == ["明细一", "明细二"]
