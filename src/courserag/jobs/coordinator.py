from __future__ import annotations

from dataclasses import dataclass

from courserag.jobs.stages import (
    BuildStageRunner,
    StageContext,
    StageOutput,
    canonical_json_bytes,
)
from courserag.persistence.base import utc_now
from courserag.persistence.models import BuildJobRecord, DocumentVersionRecord
from courserag.persistence.repositories import CourseRAGRepository


@dataclass(frozen=True)
class DocumentInventoryStage:
    documents: tuple[DocumentVersionRecord, ...]
    name: str = "legacy_document_inventory"
    version: str = "1.0"

    def execute(self, context: StageContext) -> StageOutput:
        payload = {
            "schema_version": "1.0",
            "documents": [
                {
                    "document_version_id": document.id,
                    "content_sha256": document.content_sha256,
                    "object_uri": document.object_uri,
                    "mime_type": document.mime_type,
                }
                for document in self.documents
            ],
        }
        return StageOutput(
            content=canonical_json_bytes(payload),
            counts={"document_versions": len(self.documents)},
        )


class BuildJobCoordinator:
    """Resumes idempotent stages; queue leasing remains owned by the existing worker."""

    def __init__(self, repository: CourseRAGRepository, stage_runner: BuildStageRunner) -> None:
        self.repository = repository
        self.stage_runner = stage_runner

    def resume(self, build_job_id: str) -> BuildJobRecord:
        job = self.repository.get_build_job(build_job_id)
        if job is None:
            raise ValueError("CourseRAG build job not found")
        if job.status == "succeeded":
            return job
        job.status = "running"
        job.started_at = job.started_at or utc_now()
        job.completed_at = None
        job.error_code = None
        job.error_message = None
        job.attempt_count += 1
        try:
            documents = tuple(self.repository.list_build_document_versions(job.id))
            if not documents:
                raise ValueError("CourseRAG build job has no document versions")
            stage = DocumentInventoryStage(documents)
            context = StageContext(
                build_job_id=job.id,
                knowledge_base_id=job.knowledge_base_id,
                input_hashes=tuple(document.content_sha256 for document in documents),
                input_identities=tuple(
                    "|".join((document.id, document.object_uri, document.mime_type))
                    for document in documents
                ),
                config={"pipeline": "p03_compatibility_bridge", "pipeline_version": "1.0"},
            )
            self.stage_runner.run(
                stage,
                context,
                force=job.force_rebuild or job.retry_from_stage == stage.name,
            )
        except Exception as exc:
            job.status = "failed"
            job.error_code = type(exc).__name__
            job.error_message = "Build stage failed; inspect protected service logs"
            job.completed_at = utc_now()
            self.repository.audit(
                "build.failed", "build_job", job.id, details={"error_code": job.error_code}
            )
            self.repository.flush()
            raise
        job.status = "succeeded"
        job.retry_from_stage = None
        job.completed_at = utc_now()
        self.repository.audit("build.succeeded", "build_job", job.id)
        self.repository.flush()
        return job
