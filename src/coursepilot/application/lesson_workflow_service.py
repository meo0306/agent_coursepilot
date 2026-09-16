from __future__ import annotations

from pathlib import Path
from typing import Any

from coursepilot.domain.lesson import LessonArtifact
from coursepilot.exporters.lesson_versioned_exporter import VersionedLessonDocxExporter
from coursepilot.ports.courserag import CourseRAGServicePort
from courserag.contracts.common import RequestContext
from courserag.contracts.verified_content import VerifiedContentType, VerifiedContentWriteRequest


class LessonWorkflowError(ValueError):
    pass


class LessonWorkflowService:
    """Application boundary for reviewed Lesson export and fragment writeback."""

    def __init__(self, courserag: CourseRAGServicePort):
        self.courserag = courserag

    def export(self, artifact: LessonArtifact, output_path: str | Path) -> Path:
        return VersionedLessonDocxExporter().export(artifact, output_path)

    def write_verified_fragment(
        self,
        *,
        artifact: LessonArtifact,
        session_index: int,
        evidence_ids: list[str],
        approved_by: str,
        task_id: str,
        approval_record_id: str,
        request_context: RequestContext | None = None,
    ) -> Any:
        if session_index < 1 or session_index > len(artifact.sessions):
            raise LessonWorkflowError("SESSION_NOT_FOUND")
        session = artifact.sessions[session_index - 1]
        allowed = {
            evidence_id
            for fact in [*session.key_points, *session.difficult_points]
            for evidence_id in fact.binding.evidence_ids
        }
        allowed.update(
            evidence_id
            for activity in session.activities
            for evidence_id in activity.binding.evidence_ids
        )
        if not evidence_ids or not set(evidence_ids) <= allowed:
            raise LessonWorkflowError("EVIDENCE_SCOPE_REQUIRED")
        content = {
            "session_id": session.session_id,
            "session_index": session.session_index,
            "title": session.title,
            "objectives": session.objectives,
            "activities": [activity.model_dump(mode="json") for activity in session.activities],
            "key_points": [fact.model_dump(mode="json") for fact in session.key_points],
            "homework": session.homework,
        }
        request = VerifiedContentWriteRequest(
            context=request_context or RequestContext(),
            course_id=artifact.course_id,
            content_type=VerifiedContentType.VERIFIED_LESSON_FRAGMENT,
            content=content,
            evidence_ids=evidence_ids,
            approved_by=approved_by,
            task_id=task_id,
            approval_record_id=approval_record_id,
        )
        return self.courserag.write_verified_content(request)

    def write_verified_path(
        self,
        *,
        artifact: LessonArtifact,
        json_path: str,
        evidence_ids: list[str],
        approved_by: str,
        task_id: str,
        approval_record_id: str,
        request_context: RequestContext | None = None,
    ) -> Any:
        """Write exactly one session (or a child of it), never the whole lesson.

        P14 deliberately keeps the public operation path based.  Root and multi-session
        paths are rejected before any CourseRAG call, which makes accidental whole-document
        writeback impossible even when the caller supplies a valid artifact.
        """
        prefix = "$.sessions["
        if not json_path.startswith(prefix) or "]" not in json_path:
            raise LessonWorkflowError("WRITEBACK_SCOPE_REQUIRED")
        index_text = json_path[len(prefix) :].split("]", 1)[0]
        try:
            session_index = int(index_text) + 1
        except ValueError as exc:
            raise LessonWorkflowError("WRITEBACK_SCOPE_REQUIRED") from exc
        if json_path in {"$", "$.sessions"} or json_path.count("$.sessions[") > 1:
            raise LessonWorkflowError("WRITEBACK_SCOPE_REQUIRED")
        return self.write_verified_fragment(
            artifact=artifact,
            session_index=session_index,
            evidence_ids=evidence_ids,
            approved_by=approved_by,
            task_id=task_id,
            approval_record_id=approval_record_id,
            request_context=request_context,
        )
