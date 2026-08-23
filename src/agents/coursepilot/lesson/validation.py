from __future__ import annotations

from coursepilot.domain.lesson import LessonArtifact
from coursepilot.validation.models import (
    IssueLayer,
    IssueScope,
    Severity,
    ValidationIssue,
    ValidationReport,
)


class LessonP14Validator:
    """Deterministic Lesson checks for evidence, time and coverage."""

    def validate(
        self, artifact: LessonArtifact, *, artifact_id: str = "lesson"
    ) -> ValidationReport:
        issues: list[ValidationIssue] = []
        blueprint = artifact.blueprint
        expected = set(blueprint.context_evidence_ids)
        used: set[str] = set()
        for session_position, session in enumerate(artifact.sessions):
            total = sum(activity.minutes for activity in session.activities)
            if total != blueprint.session_duration:
                issues.append(
                    self._issue(
                        "LESSON_TIME_ALLOCATION_MISMATCH",
                        f"$.sessions[{session_position}].activities",
                        session.session_id,
                        auto_repairable=True,
                    )
                )
            facts = [
                ("key_points", index, fact) for index, fact in enumerate(session.key_points)
            ] + [
                ("difficult_points", index, fact)
                for index, fact in enumerate(session.difficult_points)
            ]
            for field_name, fact_index, fact in facts:
                used.update(fact.binding.evidence_ids)
                if not fact.binding.evidence_ids:
                    issues.append(
                        self._issue(
                            "LESSON_FACT_EVIDENCE_MISSING",
                            f"$.sessions[{session_position}].{field_name}[{fact_index}]",
                            session.session_id,
                            auto_repairable=True,
                        )
                    )
        missing = expected - used
        if missing:
            issues.append(
                self._issue(
                    "LESSON_EVIDENCE_COVERAGE_MISSING",
                    "$.sessions",
                    artifact.course_id,
                    actual=sorted(missing),
                )
            )
        required_kps = {
            allocation.knowledge_point_id for allocation in blueprint.selected_knowledge_points
        }
        covered_kps = {
            kp for session in blueprint.session_plans for kp in session.knowledge_point_ids
        }
        if required_kps - covered_kps:
            issues.append(
                self._issue(
                    "LESSON_KP_NOT_COVERED",
                    "$.blueprint.session_plans",
                    artifact.course_id,
                    actual=sorted(required_kps - covered_kps),
                )
            )
        report = ValidationReport(
            artifact_id=artifact_id,
            artifact_version=1,
            artifact_type="lesson",
            validator_profile="p14_lesson_v1",
            issues=issues,
            coverage_metrics={
                "evidence_coverage": len(used & expected) / len(expected) if expected else 1.0
            },
        )
        return report.finalize()

    @staticmethod
    def _issue(
        code: str,
        path: str,
        item_id: str,
        *,
        actual: object | None = None,
        auto_repairable: bool = False,
    ) -> ValidationIssue:
        return ValidationIssue(
            issue_id=f"{code}:{item_id}:{path}",
            code=code,
            severity=Severity.ERROR,
            layer=IssueLayer.L2,
            scope=IssueScope(artifact_type="lesson", item_id=item_id, json_path=path),
            allowed_parent_paths=[path],
            auto_repairable=auto_repairable,
            message=code,
            actual=actual,
            repair_strategy="model_patch" if auto_repairable else "human_review",
        )
