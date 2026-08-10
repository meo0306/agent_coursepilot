from __future__ import annotations

from courserag.contracts.retrieval import ContextPackage
from courserag.qa.models import SufficiencyDecision, SufficiencyProfile


class EvidenceSufficiencyGate:
    def __init__(self, profile: SufficiencyProfile | None = None) -> None:
        self.profile = profile or SufficiencyProfile()

    def evaluate(
        self,
        context: ContextPackage,
        *,
        top_rerank_score: float | None,
        intent_route: str,
        minimum_source_count: int | None = None,
    ) -> SufficiencyDecision:
        reasons: list[str] = []
        selected_ids = {evidence_id for item in context.items for evidence_id in item.evidence_ids}
        if not selected_ids:
            reasons.append("NO_EVIDENCE")
        if selected_ids - set(context.evidence_map):
            reasons.append("UNRESOLVABLE_EVIDENCE")
        if top_rerank_score is None or top_rerank_score < self.profile.rerank_threshold:
            reasons.append("RERANK_BELOW_THRESHOLD")
        required_sources = minimum_source_count or (
            2 if intent_route in self.profile.multi_source_intents else 1
        )
        if required_sources > 1:
            sources = {
                (
                    summary.document_id or "unknown-document",
                    summary.section_id or "/".join(summary.section_path) or "unknown-section",
                )
                for evidence_id, summary in context.evidence_map.items()
                if evidence_id in selected_ids
            }
            if len(sources) < required_sources:
                reasons.append("MULTI_SOURCE_COVERAGE_INSUFFICIENT")
        selected = [
            context.evidence_map[value] for value in selected_ids if value in context.evidence_map
        ]
        if selected:
            low_ocr = sum(
                item.source_mode in {"ocr", "hybrid"}
                and any("LOW_CONFIDENCE" in code for code in item.warning_codes)
                for item in selected
            )
            if low_ocr / len(selected) > self.profile.max_low_confidence_ocr_ratio:
                reasons.append("LOW_CONFIDENCE_OCR_RATIO_EXCEEDED")
        return SufficiencyDecision(sufficient=not reasons, reasons=tuple(reasons))
