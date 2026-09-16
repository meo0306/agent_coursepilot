from __future__ import annotations

from coursepilot.domain.ppt import (
    PPTArtifact,
    SlideArchitecture,
    SlideCitation,
    SlideContent,
    SlidePlan,
)
from coursepilot.llm import generate_structured


def _string_list(value: object) -> list[str]:
    return [str(item) for item in value] if isinstance(value, list) else []


class PPTGenerator:
    def __init__(self, *, use_model: bool = False) -> None:
        self.use_model = use_model

    def build_architecture(
        self,
        *,
        course_id: str,
        lesson_artifact_id: str,
        template_id: str,
        template_snapshot_id: str,
        context_evidence_ids: list[str],
        slide_targets: list[dict[str, object]] | None = None,
    ) -> SlideArchitecture:
        targets = slide_targets or []
        plans: list[SlidePlan] = []
        for i, target in enumerate(targets, 1):
            raw_type = str(target.get("slide_type", "concept"))
            slide_type = (
                raw_type
                if raw_type
                in {
                    "title",
                    "agenda",
                    "objectives",
                    "concept",
                    "process",
                    "comparison",
                    "example",
                    "activity",
                    "summary",
                    "references",
                }
                else "concept"
            )
            plans.append(
                SlidePlan(
                    slide_id=f"slide-{i}",
                    slide_index=i,
                    slide_type=slide_type,
                    layout_role=str(target.get("layout_role", slide_type)),
                    title_intent=str(target.get("title", f"课程内容 {i}")),
                    source_session_index=target.get("session_index")
                    if isinstance(target.get("session_index"), int)
                    else None,
                    knowledge_point_ids=_string_list(target.get("knowledge_point_ids", [])),
                    evidence_ids=_string_list(target.get("evidence_ids", [])),
                    asset_kind=str(target.get("asset_kind", "none")),
                )
            )
        if not plans:
            plans = [
                SlidePlan(
                    slide_id="slide-1",
                    slide_index=1,
                    slide_type="title",
                    layout_role="title",
                    title_intent="课程主题",
                ),
                SlidePlan(
                    slide_id="slide-2",
                    slide_index=2,
                    slide_type="concept",
                    layout_role="concept",
                    title_intent="核心概念",
                    evidence_ids=list(context_evidence_ids[:1]),
                ),
                SlidePlan(
                    slide_id="slide-3",
                    slide_index=3,
                    slide_type="references",
                    layout_role="references",
                    title_intent="参考资料",
                    evidence_ids=list(context_evidence_ids),
                ),
            ]
        if plans[0].slide_type != "title":
            plans[0] = plans[0].model_copy(update={"slide_type": "title", "layout_role": "title"})
        if plans[-1].slide_type != "references":
            plans[-1] = plans[-1].model_copy(
                update={
                    "slide_type": "references",
                    "layout_role": "references",
                    "title_intent": "参考资料",
                    "evidence_ids": list(context_evidence_ids),
                }
            )
        plans = [p.model_copy(update={"slide_index": i}) for i, p in enumerate(plans, 1)]
        deterministic = SlideArchitecture(
            course_id=course_id,
            lesson_artifact_id=lesson_artifact_id,
            template_id=template_id,
            template_snapshot_id=template_snapshot_id,
            slide_count=len(plans),
            plans=plans,
            context_evidence_ids=context_evidence_ids,
        )
        if not self.use_model:
            return deterministic
        return generate_structured(
            prompt_name="ppt/p16_plan_architecture",
            output_schema=SlideArchitecture,
            payload={
                "deterministic": deterministic.model_dump(mode="json"),
                "slide_targets": targets,
            },
            fallback=lambda: deterministic,
            profile_id="planner_main",
            allow_fallback=False,
        )

    def generate_slides(
        self,
        architecture: SlideArchitecture,
        *,
        evidence_records: list[dict[str, object]] | None = None,
    ) -> list[SlideContent]:
        evidence_by_id = {str(r.get("evidence_id")): r for r in (evidence_records or [])}
        slides: list[SlideContent] = []
        for plan in architecture.plans:
            cited = [
                SlideCitation(
                    evidence_id=eid,
                    course_id=architecture.course_id,
                    source_document_id=str(
                        evidence_by_id.get(eid, {}).get("source_document_id", "unknown")
                    ),
                    source_document_version=str(
                        evidence_by_id.get(eid, {}).get("source_document_version", "unknown")
                    ),
                    page_start=evidence_by_id.get(eid, {}).get("page_start"),
                    page_end=evidence_by_id.get(eid, {}).get("page_end"),
                    content_sha256=str(evidence_by_id.get(eid, {}).get("content_sha256", "0" * 64)),
                )
                for eid in plan.evidence_ids
            ]
            content = SlideContent(
                slide_id=plan.slide_id,
                title=plan.title_intent,
                bullets=[f"{plan.title_intent}：关键内容"],
                body_text="基于课程证据组织的可编辑内容。",
                speaker_notes=f"教学提示：围绕 {plan.title_intent} 展开。引用 Evidence: {', '.join(plan.evidence_ids)}",
                citations=cited,
                assets=plan.assets,
            )
            if self.use_model:

                def fallback_content() -> SlideContent:
                    return content

                content = generate_structured(
                    prompt_name="ppt/p16_generate_slide",
                    output_schema=SlideContent,
                    payload={
                        "architecture": architecture.model_dump(mode="json"),
                        "slide_plan": plan.model_dump(mode="json"),
                        "evidence": [
                            evidence_by_id[eid]
                            for eid in plan.evidence_ids
                            if eid in evidence_by_id
                        ],
                    },
                    fallback=fallback_content,
                    profile_id="generator_main",
                    allow_fallback=False,
                )
            if content.slide_id != plan.slide_id or any(
                c.evidence_id not in set(plan.evidence_ids) for c in content.citations
            ):
                raise ValueError("PPT slide output contains an invalid identity or Evidence ID")
            slides.append(content)
        return slides

    def build_artifact(
        self,
        architecture: SlideArchitecture,
        *,
        evidence_records: list[dict[str, object]] | None = None,
    ) -> PPTArtifact:
        return PPTArtifact(
            course_id=architecture.course_id,
            lesson_artifact_id=architecture.lesson_artifact_id,
            template_id=architecture.template_id,
            template_snapshot_id=architecture.template_snapshot_id,
            architecture=architecture,
            slides=self.generate_slides(architecture, evidence_records=evidence_records),
        )
