from __future__ import annotations

from sqlalchemy.orm import Session

from coursepilot.domain.context import ContextPackageRef
from coursepilot.models import ArtifactVersionRecord, WorkflowRunRecord
from coursepilot.ports.courserag import CourseRAGServicePort
from courserag.contracts import ContextBindingValidationRequest, RequestContext


class StaleCourseRAGContextError(RuntimeError):
    code = "STALE_COURSERAG_CONTEXT"


def assert_context_binding_current(
    *,
    session: Session,
    source_version: ArtifactVersionRecord,
    course_id: str,
    service: CourseRAGServicePort,
) -> None:
    """Fail before a side effect when a versioned artifact's source Context is stale."""
    if source_version.source_run_id is None:
        return
    run = session.get(WorkflowRunRecord, source_version.source_run_id)
    if run is None:
        raise StaleCourseRAGContextError("Source workflow run is missing")
    for raw_reference in run.context_refs_json:
        reference = ContextPackageRef.model_validate(raw_reference)
        if reference.course_id != course_id:
            raise StaleCourseRAGContextError("Context belongs to another course")
        response = service.validate_context_binding(
            ContextBindingValidationRequest(
                context=RequestContext(
                    caller="coursepilot-side-effect-preflight",
                    trace_id=run.trace_id,
                ),
                course_id=course_id,
                index_version=reference.index_version,
                verified_overlay_version=reference.verified_overlay_version,
                evidence_versions=reference.evidence_versions,
            )
        )
        if response.stale:
            detail = response.reason or response.status
            raise StaleCourseRAGContextError(detail)
