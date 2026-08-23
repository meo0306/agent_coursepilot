from __future__ import annotations

from collections.abc import Callable

from coursepilot.domain.context import ContextPackageRef
from coursepilot.domain.lesson import (
    AllocationImportance,
    KnowledgePointAllocation,
    LessonActivity,
    LessonArtifact,
    LessonBlueprint,
    LessonEvidenceBinding,
    LessonFact,
    LessonSessionArtifact,
    LessonSessionBlueprint,
)
from coursepilot.llm import generate_structured
from courserag.contracts.knowledge_points import (
    KnowledgePointSnapshot,
)


class LessonGenerator:
    """Evidence-bound lesson generator with deterministic and provider modes.

    Deterministic mode remains the Contract Fake used by unit tests.  Provider mode is
    explicitly enabled by the P14 runner and routes planner/session/repair calls through
    the Model Gateway with fallback disabled.
    """

    def __init__(self, *, use_model: bool = False) -> None:
        self.use_model = use_model

    def build_blueprint(
        self,
        *,
        course_id: str,
        chapter_scope: str,
        total_sessions: int,
        session_duration: int,
        template_snapshot_id: str,
        kp_snapshot: KnowledgePointSnapshot,
        context_ref: ContextPackageRef,
        context_records: list[dict[str, object]] | None = None,
        replan_instruction: str | None = None,
        previous_blueprint: LessonBlueprint | None = None,
    ) -> LessonBlueprint:
        if kp_snapshot.course_id != course_id or context_ref.course_id != course_id:
            raise ValueError("course identity mismatch")
        items = list(kp_snapshot.items)
        if not items:
            raise ValueError("at least one approved knowledge point is required")
        deterministic = self._build_blueprint_deterministic(
            course_id=course_id,
            chapter_scope=chapter_scope,
            total_sessions=total_sessions,
            session_duration=session_duration,
            template_snapshot_id=template_snapshot_id,
            kp_snapshot=kp_snapshot,
            context_ref=context_ref,
        )
        if not self.use_model:
            return deterministic
        payload = {
            "course_id": course_id,
            "chapter_scope": chapter_scope,
            "total_sessions": total_sessions,
            "session_duration": session_duration,
            "template_snapshot_id": template_snapshot_id,
            "context_package_id": context_ref.context_id,
            "approved_knowledge_points": [
                item.model_dump(mode="json") for item in kp_snapshot.items
            ],
            "context_evidence": context_records or [],
            "replan_instruction": replan_instruction,
        }
        if previous_blueprint is not None:
            payload["previous_blueprint"] = previous_blueprint.model_dump(mode="json")
        proposed = generate_structured(
            prompt_name="lesson/p14_plan_blueprint",
            output_schema=LessonBlueprint,
            payload=payload,
            fallback=lambda: deterministic,
            profile_id="planner_main",
            allow_fallback=False,
        )
        return self._validate_blueprint(proposed, deterministic, kp_snapshot, context_ref)

    def repair_session(
        self,
        session: LessonSessionArtifact,
        *,
        issue_payloads: list[dict[str, object]],
        allowed_fields: set[str],
        allowed_evidence_ids: set[str],
        context_records: list[dict[str, object]] | None = None,
    ) -> LessonSessionArtifact:
        """Run one scoped repair and reject modifications outside caller-owned fields."""
        if not self.use_model:
            return session
        permitted = {
            "objectives",
            "activities",
            "key_points",
            "difficult_points",
            "homework",
            "terminology",
        }
        if not allowed_fields or not allowed_fields.issubset(permitted):
            raise ValueError("lesson repair contains an unsupported allowed field")
        proposed = generate_structured(
            prompt_name="lesson/p14_repair_session",
            output_schema=LessonSessionArtifact,
            payload={
                "session": session.model_dump(mode="json"),
                "validation_issues": issue_payloads,
                "allowed_paths": sorted(f"$.{field}" for field in allowed_fields),
                "context_evidence": [
                    record
                    for record in (context_records or [])
                    if str(record.get("evidence_id")) in allowed_evidence_ids
                ],
            },
            fallback=self._session_fallback(session),
            profile_id="content_repair_main",
            allow_fallback=False,
        )
        before = session.model_dump(mode="json")
        after = proposed.model_dump(mode="json")
        changed_fields = {key for key in before if before.get(key) != after.get(key)}
        if not changed_fields.issubset(allowed_fields):
            raise ValueError("lesson repair modified a field outside the approved scope")
        if (
            proposed.session_id != session.session_id
            or proposed.session_index != session.session_index
        ):
            raise ValueError("lesson repair changed immutable session identity")
        if not self._ids_are_allowed(proposed, allowed_evidence_ids):
            raise ValueError("lesson repair contains an evidence ID outside the approved session")
        return proposed

    def _build_blueprint_deterministic(
        self,
        *,
        course_id: str,
        chapter_scope: str,
        total_sessions: int,
        session_duration: int,
        template_snapshot_id: str,
        kp_snapshot: KnowledgePointSnapshot,
        context_ref: ContextPackageRef,
    ) -> LessonBlueprint:
        items = list(kp_snapshot.items)
        allocations = [
            KnowledgePointAllocation(
                knowledge_point_id=item.knowledge_point_id,
                canonical_name=item.canonical_name,
                importance=AllocationImportance.CORE
                if index < total_sessions
                else AllocationImportance.SUPPORTING,
                evidence_ids=[link.evidence_id for link in item.evidence_links],
                session_indices=[(index % total_sessions) + 1],
            )
            for index, item in enumerate(items)
        ]
        sessions: list[LessonSessionBlueprint] = []
        for session_index in range(1, total_sessions + 1):
            selected = [
                item
                for item, allocation in zip(items, allocations)
                if session_index in allocation.session_indices
            ]
            if not selected:
                selected = [items[(session_index - 1) % len(items)]]
            kp_ids = [item.knowledge_point_id for item in selected]
            evidence_ids = sorted(
                {link.evidence_id for item in selected for link in item.evidence_links}
            )
            activities = self._activities(session_index, session_duration, evidence_ids)
            sessions.append(
                LessonSessionBlueprint(
                    session_id=f"session-{session_index}",
                    session_index=session_index,
                    title=f"{chapter_scope} · Session {session_index}",
                    duration_minutes=session_duration,
                    knowledge_point_ids=kp_ids,
                    objective_types=["understand", "apply"],
                    key_points=[item.canonical_name for item in selected],
                    difficult_points=[],
                    required_evidence_ids=evidence_ids,
                    required_activity_types=[activity.activity_type for activity in activities],
                    activities=activities,
                    predecessor_session_ids=(
                        [f"session-{session_index - 1}"] if session_index > 1 else []
                    ),
                )
            )
        return LessonBlueprint(
            course_id=course_id,
            chapter_scope=chapter_scope,
            total_sessions=total_sessions,
            session_duration=session_duration,
            selected_knowledge_points=allocations,
            session_plans=sessions,
            template_snapshot_id=template_snapshot_id,
            context_package_id=context_ref.context_id,
            context_evidence_ids=list(context_ref.evidence_ids),
        )

    def generate_sessions(
        self,
        blueprint: LessonBlueprint,
        kp_snapshot: KnowledgePointSnapshot,
        context_records: list[dict[str, object]] | None = None,
    ) -> list[LessonSessionArtifact]:
        by_id = {item.knowledge_point_id: item for item in kp_snapshot.items}
        result: list[LessonSessionArtifact] = []
        for plan in blueprint.session_plans:
            facts: list[LessonFact] = []
            for kp_id in plan.knowledge_point_ids:
                item = by_id[kp_id]
                evidence_ids = [link.evidence_id for link in item.evidence_links]
                facts.append(
                    LessonFact(
                        fact_id=f"{plan.session_id}:{kp_id}",
                        text=item.summary or item.canonical_name,
                        binding=LessonEvidenceBinding(
                            evidence_ids=evidence_ids,
                            knowledge_point_ids=[kp_id],
                        ),
                    )
                )
            deterministic = LessonSessionArtifact(
                session_id=plan.session_id,
                session_index=plan.session_index,
                title=plan.title,
                objectives=[f"Explain and apply {name}" for name in plan.key_points],
                activities=list(plan.activities),
                key_points=facts,
                difficult_points=[],
                homework=[f"Summarize {name} with one cited example" for name in plan.key_points],
                terminology=list(plan.key_points),
            )
            if self.use_model:
                allowed_evidence = set(plan.required_evidence_ids)
                proposed = generate_structured(
                    prompt_name="lesson/p14_generate_session",
                    output_schema=LessonSessionArtifact,
                    payload={
                        "blueprint": blueprint.model_dump(mode="json"),
                        "session_plan": plan.model_dump(mode="json"),
                        "approved_knowledge_points": [
                            by_id[kp_id].model_dump(mode="json")
                            for kp_id in plan.knowledge_point_ids
                        ],
                        "context_evidence": [
                            record
                            for record in (context_records or [])
                            if str(record.get("evidence_id")) in allowed_evidence
                        ],
                    },
                    fallback=self._session_fallback(deterministic),
                    profile_id="generator_main",
                    allow_fallback=False,
                )
                if (
                    proposed.session_id != plan.session_id
                    or proposed.session_index != plan.session_index
                ):
                    raise ValueError("model session identity does not match the approved plan")
                if not self._ids_are_allowed(proposed, allowed_evidence):
                    raise ValueError(
                        "model session contains an evidence ID outside the approved session"
                    )
                deterministic = proposed
            result.append(deterministic)
        return result

    @staticmethod
    def _activities(
        session_index: int, duration: int, evidence_ids: list[str]
    ) -> list[LessonActivity]:
        lecture = max(1, duration // 2)
        practice = max(1, duration - lecture)
        binding = LessonEvidenceBinding(evidence_ids=evidence_ids)
        return [
            LessonActivity(
                activity_id=f"session-{session_index}-explain",
                activity_type="explanation",
                title="Evidence-based explanation",
                minutes=lecture,
                objective_ids=["understand"],
                binding=binding,
            ),
            LessonActivity(
                activity_id=f"session-{session_index}-practice",
                activity_type="practice",
                title="Guided practice",
                minutes=practice,
                objective_ids=["apply"],
                binding=binding,
            ),
        ]

    def generate_artifact(
        self,
        blueprint: LessonBlueprint,
        kp_snapshot: KnowledgePointSnapshot,
        *,
        context_records: list[dict[str, object]] | None = None,
    ) -> LessonArtifact:
        return LessonArtifact(
            course_id=blueprint.course_id,
            chapter_scope=blueprint.chapter_scope,
            template_id=blueprint.template_snapshot_id,
            blueprint=blueprint,
            sessions=self.generate_sessions(blueprint, kp_snapshot, context_records),
        )

    @staticmethod
    def _session_fallback(
        result: LessonSessionArtifact,
    ) -> Callable[[], LessonSessionArtifact]:
        def fallback() -> LessonSessionArtifact:
            return result

        return fallback

    @staticmethod
    def _validate_blueprint(
        proposed: LessonBlueprint,
        deterministic: LessonBlueprint,
        kp_snapshot: KnowledgePointSnapshot,
        context_ref: ContextPackageRef,
    ) -> LessonBlueprint:
        allowed_kp = {item.knowledge_point_id for item in kp_snapshot.items}
        allowed_evidence = set(context_ref.evidence_ids)
        if (
            proposed.course_id != deterministic.course_id
            or proposed.total_sessions != deterministic.total_sessions
        ):
            raise ValueError("model blueprint changed immutable lesson constraints")
        if any(
            item.knowledge_point_id not in allowed_kp for item in proposed.selected_knowledge_points
        ):
            raise ValueError("model blueprint contains an unknown knowledge point")
        if any(
            evidence_id not in allowed_evidence for evidence_id in proposed.context_evidence_ids
        ):
            raise ValueError("model blueprint contains an unknown evidence ID")
        if len(proposed.session_plans) != deterministic.total_sessions:
            raise ValueError("model blueprint session count mismatch")
        return proposed

    @staticmethod
    def _ids_are_allowed(session: LessonSessionArtifact, allowed_evidence: set[str]) -> bool:
        for fact in [*session.key_points, *session.difficult_points]:
            if not set(fact.binding.evidence_ids).issubset(allowed_evidence):
                return False
        return all(
            set(activity.binding.evidence_ids).issubset(allowed_evidence)
            for activity in session.activities
        )
