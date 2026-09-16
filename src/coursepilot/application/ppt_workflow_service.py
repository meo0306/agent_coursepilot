from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from coursepilot.domain.context import ContextPackageRef
from coursepilot.ports.courserag import CourseRAGServicePort
from coursepilot.runtime.context_resolver import context_package_ref
from coursepilot.runtime.repository import RuntimeRepository
from courserag.contracts import (
    BatchGetEvidenceRequest,
    ContextRequest,
    KnowledgePointSnapshot,
    KnowledgePointSnapshotRequest,
    RequestContext,
)


@dataclass(frozen=True)
class PPTResolvedInputs:
    """References kept in workflow state; evidence text is request-scoped only."""

    course_id: str
    lesson_artifact_id: str
    lesson_version: int
    lesson_content_sha256: str
    knowledge_points: KnowledgePointSnapshot
    context_ref: ContextPackageRef
    evidence_records: tuple[dict[str, Any], ...]


class PPTWorkflowService:
    """Application boundary for P16 inputs; it never imports parser/index internals."""

    def __init__(self, session: Session, courserag: CourseRAGServicePort) -> None:
        self.session = session
        self.courserag = courserag

    def load_inputs(
        self,
        *,
        course_id: str,
        lesson_artifact_id: str,
        query: str,
        context: RequestContext | None = None,
    ) -> PPTResolvedInputs:
        found = RuntimeRepository(self.session).find_active_artifact(
            artifact_id=lesson_artifact_id, course_id=course_id
        )
        if found is None:
            raise ValueError("PPT_LESSON_ARTIFACT_NOT_FOUND")
        artifact, version = found
        if artifact.artifact_type != "lesson":
            raise ValueError("PPT_LESSON_ARTIFACT_NOT_FOUND")
        request_context = context or RequestContext()
        snapshot = self.courserag.list_knowledge_points(
            KnowledgePointSnapshotRequest(context=request_context, course_id=course_id)
        )
        context_request = ContextRequest(
            context=request_context,
            course_id=course_id,
            query=query,
            purpose="ppt_generation",
        )
        package = self.courserag.build_context(context_request)
        # Bind the package already retrieved above. Calling build_context a
        # second time could observe a newer index/overlay and duplicate work.
        context_ref = context_package_ref(context_request, package)
        evidence_ids = sorted(package.evidence_map)
        batch = self.courserag.batch_get_evidence(
            BatchGetEvidenceRequest(
                context=request_context,
                course_id=course_id,
                evidence_ids=evidence_ids or ["__none__"],
            )
        )
        if batch.missing_ids:
            raise ValueError("PPT_CONTEXT_EVIDENCE_UNRESOLVABLE")
        records = tuple(record.model_dump(mode="json") for record in batch.records)
        return PPTResolvedInputs(
            course_id=course_id,
            lesson_artifact_id=artifact.id,
            lesson_version=version.version,
            lesson_content_sha256=version.content_sha256,
            knowledge_points=snapshot,
            context_ref=context_ref,
            evidence_records=records,
        )
