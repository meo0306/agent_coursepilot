from __future__ import annotations

from dataclasses import dataclass

from coursepilot.domain.common import canonical_sha256
from coursepilot.domain.context import ContextPackageRef
from coursepilot.ports.courserag import CourseRAGServicePort
from courserag.contracts import ContextPackage, ContextRequest


class ContextResolutionError(RuntimeError):
    pass


@dataclass(frozen=True)
class ContextResolver:
    courserag: CourseRAGServicePort

    def resolve(self, request: ContextRequest) -> ContextPackageRef:
        package = self.courserag.build_context(request)
        return context_package_ref(request, package)


def context_package_ref(request: ContextRequest, package: ContextPackage) -> ContextPackageRef:
    if package.meta.request_id != request.context.request_id:
        raise ContextResolutionError("CourseRAG Context request identity mismatch")
    if package.meta.trace_id != request.context.trace_id:
        raise ContextResolutionError("CourseRAG Context trace identity mismatch")
    if package.context_package_id is None or package.result_sha256 is None:
        raise ContextResolutionError("CourseRAG Context has no stable identity")
    evidence_ids = sorted(package.evidence_map)
    for evidence_id, summary in package.evidence_map.items():
        if summary.evidence_id not in {None, evidence_id}:
            raise ContextResolutionError("CourseRAG Context Evidence identity mismatch")
        if summary.content_sha256 is None:
            raise ContextResolutionError("CourseRAG Context Evidence has no content hash")
    calculated = canonical_sha256(
        {
            "course_id": request.course_id,
            "context_package_id": package.context_package_id,
            "index_version": package.index_version,
            "evidence": {
                key: value.content_sha256 for key, value in sorted(package.evidence_map.items())
            },
            "token_count": package.token_count,
            "result_sha256": package.result_sha256,
        }
    )
    return ContextPackageRef(
        context_id=package.context_package_id,
        purpose=package.purpose,
        course_id=request.course_id,
        index_version=package.index_version,
        evidence_ids=evidence_ids,
        token_count=package.token_count,
        content_hash=calculated,
        trace_id=package.meta.trace_id,
        warning_codes=list(package.meta.warnings),
    )
