from __future__ import annotations

import hashlib
from collections.abc import Callable
from typing import Protocol

from pydantic import ValidationError

from courserag.contracts.common import ResponseMeta
from courserag.contracts.qa import (
    AnswerClaim,
    AnswerStatus,
    AnswerType,
    Citation,
    ModelReference,
    QARequest,
    QAResponse,
)
from courserag.contracts.retrieval import ContextPackage
from courserag.qa.citations import CITATION_COMPOSER_VERSION, compose_claim_evidence
from courserag.qa.models import (
    GeneratedClaim,
    GeneratedListItem,
    ProviderOutputError,
    ProviderQAResult,
    StructuredQAOutput,
)
from courserag.qa.sufficiency import EvidenceSufficiencyGate
from courserag.query.answer_shape import AnswerShapeDecision, decide_answer_shape


class QAProvider(Protocol):
    def generate(
        self, question: str, context: ContextPackage, *, answer_shape: AnswerShapeDecision
    ) -> ProviderQAResult: ...

    def repair(
        self,
        question: str,
        context: ContextPackage,
        *,
        error: str,
        answer_shape: AnswerShapeDecision,
    ) -> ProviderQAResult: ...


class QAValidationError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class CitedQAService:
    def __init__(
        self,
        *,
        provider: QAProvider,
        gate: EvidenceSufficiencyGate,
        generation_reliability_enabled: bool = False,
    ) -> None:
        self.provider = provider
        self.gate = gate
        self.generation_reliability_enabled = generation_reliability_enabled

    def answer(
        self,
        request: QARequest,
        *,
        context: ContextPackage,
        top_rerank_score: float | None,
        intent_route: str,
        minimum_source_count: int | None = None,
        persist: Callable[[QAResponse], str] | None = None,
    ) -> QAResponse:
        decision = self.gate.evaluate(
            context,
            top_rerank_score=top_rerank_score,
            intent_route=intent_route,
            minimum_source_count=minimum_source_count,
        )
        if not decision.sufficient:
            return QAResponse(
                meta=ResponseMeta.from_context(request.context, warnings=list(decision.reasons)),
                question=request.question,
                answer_status=AnswerStatus.ABSTAINED_INSUFFICIENT_EVIDENCE,
                answer=None,
                context_package_id=context.context_package_id,
                retrieval_trace_id=context.retrieval_trace_id,
                warnings=list(decision.reasons),
                validation_summary={"sufficiency": False, "reasons": list(decision.reasons)},
            )
        answer_shape = decide_answer_shape(
            request.question,
            intent_route,
            generation_reliability=self.generation_reliability_enabled,
        )
        if request.answering.answer_shape is not None:
            answer_shape = AnswerShapeDecision(
                forced_type=request.answering.answer_shape,
                rule_id="answer_shape.request_override.v1",
                reason="explicit AnsweringOptions override",
            )
        repair_count = 0
        initial_error_metadata: dict[str, object] = {}
        try:
            result = self.provider.generate(request.question, context, answer_shape=answer_shape)
            self._validate(result.output, context, answer_shape)
        except (QAValidationError, ValidationError, ValueError) as exc:
            initial_error_code = _validation_error_code(exc)
            initial_error_metadata = _validation_error_metadata(exc)
            repair_count = 1
            try:
                result = self.provider.repair(
                    request.question,
                    context,
                    error=initial_error_code,
                    answer_shape=answer_shape,
                )
                self._validate(result.output, context, answer_shape)
            except (QAValidationError, ValidationError, ValueError) as repair_exc:
                repair_error_code = _validation_error_code(repair_exc)
                return QAResponse(
                    meta=ResponseMeta.from_context(
                        request.context, warnings=["QA_SCHEMA_REPAIR_FAILED"]
                    ),
                    question=request.question,
                    answer_status=AnswerStatus.FAILED,
                    context_package_id=context.context_package_id,
                    retrieval_trace_id=context.retrieval_trace_id,
                    warnings=["QA_SCHEMA_REPAIR_FAILED"],
                    validation_summary={
                        "repair_count": repair_count,
                        "valid": False,
                        "initial_error_code": initial_error_code,
                        "repair_error_code": repair_error_code,
                        "initial_error_metadata": initial_error_metadata,
                        "repair_error_metadata": _validation_error_metadata(repair_exc),
                    },
                )
        response = self._compose(
            request,
            context,
            result,
            repair_count=repair_count,
            answer_shape=answer_shape,
            initial_error_metadata=initial_error_metadata,
        )
        if persist is not None:
            response.qa_run_id = persist(response)
        return response

    @staticmethod
    def _validate(
        output: StructuredQAOutput,
        context: ContextPackage,
        answer_shape: AnswerShapeDecision,
    ) -> None:
        if output.status != "answered":
            return
        actual_type = output.answer_type or AnswerType.EXPLANATORY
        if answer_shape.forced_type is not None and actual_type != answer_shape.forced_type:
            raise QAValidationError(
                "ANSWER_SHAPE_MISMATCH",
                "Provider Answer Type differs from the forced Answer Shape",
            )
        available = set(context.evidence_map)
        units: tuple[GeneratedClaim | GeneratedListItem, ...] = (
            *output.claims,
            *output.list_items,
        )
        for claim in units:
            if not set(claim.evidence_ids).issubset(available):
                raise QAValidationError(
                    "EVIDENCE_OUTSIDE_CONTEXT",
                    "Claim references Evidence outside the Context Package",
                )

    @staticmethod
    def _compose(
        request: QARequest,
        context: ContextPackage,
        result: ProviderQAResult,
        *,
        repair_count: int,
        answer_shape: AnswerShapeDecision,
        initial_error_metadata: dict[str, object],
    ) -> QAResponse:
        output = result.output
        if output.status != "answered":
            return QAResponse(
                meta=ResponseMeta.from_context(request.context),
                question=request.question,
                answer_status=AnswerStatus.ABSTAINED_INSUFFICIENT_EVIDENCE,
                answer=output.answer,
                context_package_id=context.context_package_id,
                retrieval_trace_id=context.retrieval_trace_id,
                model=ModelReference(
                    provider=result.provider,
                    model=result.model,
                    prompt_version=result.prompt_version,
                ),
                usage=result.usage.model_dump(mode="json"),
                validation_summary={"repair_count": repair_count, "valid": True},
            )
        answer_type = output.answer_type or AnswerType.EXPLANATORY
        evidence_texts = _context_evidence_texts(context)
        source_units: tuple[GeneratedClaim | GeneratedListItem, ...] = (
            output.list_items if answer_type == AnswerType.LIST else output.claims
        )
        claims: list[AnswerClaim] = []
        used: list[str] = []
        composer_trace: list[dict[str, object]] = []
        warnings: list[str] = []
        for index, claim in enumerate(source_units, start=1):
            selection = compose_claim_evidence(
                claim.text,
                evidence_texts,
                original_evidence_ids=claim.evidence_ids,
            )
            if selection.status != "composed":
                warnings.append("CITATION_NO_LEXICAL_SUPPORT_SIGNAL")
            claims.append(
                AnswerClaim(
                    claim_id=f"claim_{hashlib.sha256(f'{index}:{claim.text}'.encode()).hexdigest()[:24]}",
                    text=claim.text,
                    evidence_ids=list(selection.evidence_ids),
                    validation_status=(
                        "valid" if selection.status == "composed" else "valid_with_warning"
                    ),
                )
            )
            used.extend(selection.evidence_ids)
            composer_trace.append(
                {
                    "claim_index": index,
                    "original_evidence_ids": list(claim.evidence_ids),
                    "selected_evidence_ids": list(selection.evidence_ids),
                    "score": selection.score,
                    "status": selection.status,
                }
            )
        used = list(dict.fromkeys(used))
        citations = [
            Citation(
                evidence_id=evidence_id,
                document_id=context.evidence_map[evidence_id].document_id or "unknown",
                page_start=context.evidence_map[evidence_id].page_start,
                page_end=context.evidence_map[evidence_id].page_end,
                section_path=context.evidence_map[evidence_id].section_path,
                content_sha256=context.evidence_map[evidence_id].content_sha256,
            )
            for evidence_id in used
        ]
        return QAResponse(
            meta=ResponseMeta.from_context(request.context),
            question=request.question,
            answer_status=AnswerStatus.ANSWERED,
            answer=(
                output.answer or "；".join(item.text for item in output.list_items)
                if answer_type == AnswerType.LIST
                else output.answer
            ),
            answer_type=answer_type,
            list_items=[item.text for item in output.list_items],
            claims=claims,
            citations=citations,
            context_package_id=context.context_package_id,
            retrieval_trace_id=context.retrieval_trace_id,
            model=ModelReference(
                provider=result.provider,
                model=result.model,
                prompt_version=result.prompt_version,
            ),
            used_evidence_ids=used,
            usage=result.usage.model_dump(mode="json"),
            warnings=list(dict.fromkeys(warnings)),
            validation_summary={
                "repair_count": repair_count,
                "valid": True,
                "answer_shape_rule_id": answer_shape.rule_id,
                "answer_shape_reason": answer_shape.reason,
                "provider_completion": result.completion_metadata,
                "initial_error_metadata": initial_error_metadata,
                "citation_composer_version": CITATION_COMPOSER_VERSION,
                "citation_composer_trace": composer_trace,
            },
        )


def _context_evidence_texts(context: ContextPackage) -> dict[str, str]:
    output: dict[str, str] = {}
    for item in context.items:
        if item.evidence_segments:
            output.update({segment.evidence_id: segment.text for segment in item.evidence_segments})
        elif len(item.evidence_ids) == 1:
            output[item.evidence_ids[0]] = item.text
    return output


def _validation_error_code(exc: Exception) -> str:
    if isinstance(exc, ProviderOutputError):
        return exc.code
    if isinstance(exc, QAValidationError):
        return exc.code
    if isinstance(exc, ValidationError):
        errors = exc.errors()
        types = {str(item.get("type", "")) for item in errors}
        locations = {str(value) for item in errors for value in item.get("loc", ())}
        if "json_invalid" in types:
            return "INVALID_JSON"
        if "status" in locations and ("literal_error" in types or "missing" in types):
            return "INVALID_STATUS"
        if "answer" in locations and "missing" in types:
            return "MISSING_ANSWER"
        if "claims" in locations and "missing" in types:
            return "MISSING_CLAIMS"
        if "string_too_long" in types:
            return "OUTPUT_TOO_LONG"
        return "SCHEMA_VALIDATION_FAILED"
    return "QA_OUTPUT_INVALID"


def _validation_error_metadata(exc: Exception) -> dict[str, object]:
    if isinstance(exc, ProviderOutputError):
        return dict(exc.metadata)
    return {}
