from __future__ import annotations

import hashlib
from pathlib import Path

from sqlalchemy.orm import Session

from core.settings import settings
from coursepilot.models import Course, Document, GenerationTask
from coursepilot.services.async_task_service import complete_execution_task
from courserag.jobs.artifacts import FileArtifactStore
from courserag.jobs.cleanup import CleanupPlan, CleanupService
from courserag.jobs.coordinator import BuildJobCoordinator
from courserag.jobs.stages import BuildStageRunner, sha256_json
from courserag.persistence.models import (
    BuildJobDocumentVersionRecord,
    BuildJobRecord,
    DocumentVersionRecord,
    KnowledgeBaseRecord,
    SourceDocumentRecord,
)
from courserag.persistence.repositories import CourseRAGRepository


class CourseRAGTaskOwnershipError(RuntimeError):
    pass


class CourseRAGBuildExecutionError(RuntimeError):
    pass


class CourseRAGBuildCompatibilityBridge:
    """Explicit P03 bridge; existing public build endpoints do not call it by default."""

    def __init__(self, session: Session, *, artifact_root: Path | None = None) -> None:
        self.session = session
        self.repository = CourseRAGRepository(session)
        root = artifact_root or Path(settings.COURSERAG_ARTIFACT_DIR)
        self.artifact_store = FileArtifactStore(root)

    def enqueue_legacy_document(self, document_id: str, *, force: bool = False) -> BuildJobRecord:
        document = self.session.get(Document, document_id)
        if document is None:
            raise ValueError("Legacy document not found")
        document_type = document.file_type.lower().removeprefix(".")
        if document_type not in {"pdf", "docx"}:
            raise ValueError("P03 compatibility bridge only supports PDF and DOCX")
        course = self.session.get(Course, document.course_id)
        if course is None:
            raise ValueError("Legacy course not found")
        source_path = Path(document.file_path)
        content = source_path.read_bytes()
        content_sha256 = hashlib.sha256(content).hexdigest()

        knowledge_base = self.repository.get_knowledge_base_by_course(course.id)
        if knowledge_base is None:
            knowledge_base = KnowledgeBaseRecord(
                course_id=course.id,
                name=course.course_name,
                description=course.description,
            )
            self.repository.add(knowledge_base)
            self.repository.flush()
        source_document = self.repository.get_source_document_by_legacy_id(
            knowledge_base.id, document.id
        )
        if source_document is None:
            source_document = SourceDocumentRecord(
                knowledge_base_id=knowledge_base.id,
                legacy_document_id=document.id,
                filename=document.file_name,
                document_type=document_type,
            )
            self.repository.add(source_document)
            self.repository.flush()

        version = self._get_or_create_version(
            source_document=source_document,
            content_sha256=content_sha256,
            size_bytes=len(content),
            mime_type=(
                "application/pdf"
                if document_type == "pdf"
                else "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            ),
        )
        request_hash = sha256_json(
            {
                "knowledge_base_id": knowledge_base.id,
                "document_version_ids": [version.id],
                "force": force,
                "bridge_version": "1.0",
            }
        )
        existing = self.repository.get_build_job_by_request(knowledge_base.id, request_hash)
        if existing is not None:
            return existing
        task = GenerationTask(
            course_id=course.id,
            task_type="courserag_build",
            status="pending",
            input_params_json={},
        )
        self.session.add(task)
        self.repository.flush()
        job = BuildJobRecord(
            knowledge_base_id=knowledge_base.id,
            queue_task_id=task.id,
            request_hash=request_hash,
            status="queued",
            force_rebuild=force,
        )
        self.repository.add(job)
        self.repository.flush()
        self.repository.add(
            BuildJobDocumentVersionRecord(build_job_id=job.id, document_version_id=version.id)
        )
        task.input_params_json = {"build_job_id": job.id}
        self.repository.audit(
            "build.queued",
            "build_job",
            job.id,
            details={"legacy_document_id": document.id},
        )
        self.session.commit()
        return job

    def resume_task(self, task: GenerationTask) -> BuildJobRecord:
        build_job_id = str(task.input_params_json["build_job_id"])
        expected_worker_id = task.worker_id
        if not expected_worker_id:
            raise CourseRAGTaskOwnershipError("CourseRAG task has no worker lease owner")
        runner = BuildStageRunner(self.repository, self.artifact_store)
        job = self.repository.get_build_job(build_job_id)
        if job is None:
            raise ValueError("CourseRAG build job not found")
        job.worker_id = expected_worker_id
        job.locked_until = task.locked_until
        try:
            job = BuildJobCoordinator(self.repository, runner).resume(build_job_id)
        except Exception as exc:
            self._assert_task_ownership(task, expected_worker_id)
            # Preserve sanitized Stage/Build failure evidence before the legacy worker
            # rolls back its task transaction and records GenerationTask failure.
            self.session.commit()
            raise CourseRAGBuildExecutionError(
                f"CourseRAG build failed ({type(exc).__name__})"
            ) from None
        self._assert_task_ownership(task, expected_worker_id)
        complete_execution_task(
            task,
            {"build_job_id": job.id, "status": job.status, "pipeline": "p03"},
        )
        self.session.commit()
        return job

    def _assert_task_ownership(self, task: GenerationTask, expected_worker_id: str) -> None:
        with self.session.no_autoflush:
            self.session.refresh(task)
        if task.status != "running" or task.worker_id != expected_worker_id:
            self.session.rollback()
            raise CourseRAGTaskOwnershipError("CourseRAG task lease ownership changed")

    def retry(self, build_job_id: str, *, from_stage: str) -> GenerationTask:
        job = self.repository.get_build_job(build_job_id)
        if job is None:
            raise ValueError("CourseRAG build job not found")
        if from_stage != "legacy_document_inventory":
            raise ValueError("Unknown P03 build stage")
        knowledge_base = self.repository.get_knowledge_base(job.knowledge_base_id)
        if knowledge_base is None:
            raise ValueError("CourseRAG knowledge base not found")
        task = GenerationTask(
            course_id=knowledge_base.course_id,
            task_type="courserag_build",
            status="pending",
            input_params_json={"build_job_id": job.id},
        )
        self.session.add(task)
        self.repository.flush()
        job.queue_task_id = task.id
        job.status = "queued"
        job.retry_from_stage = from_stage
        job.completed_at = None
        self.repository.audit(
            "build.retry_requested",
            "build_job",
            job.id,
            details={"from_stage": from_stage},
        )
        self.session.commit()
        return task

    def cleanup(self, *, dry_run: bool = True, actor_id: str = "system") -> CleanupPlan:
        plan = CleanupService(self.repository, self.artifact_store).run(
            artifact_retention_hours=settings.COURSERAG_ARTIFACT_RETENTION_HOURS,
            staging_retention_hours=settings.COURSERAG_STAGING_RETENTION_HOURS,
            dry_run=dry_run,
            actor_id=actor_id,
        )
        self.session.commit()
        return plan

    def _get_or_create_version(
        self,
        *,
        source_document: SourceDocumentRecord,
        content_sha256: str,
        size_bytes: int,
        mime_type: str,
    ) -> DocumentVersionRecord:
        if source_document.current_version_id is not None:
            current = self.session.get(DocumentVersionRecord, source_document.current_version_id)
            if current is not None and current.content_sha256 == content_sha256:
                return current
        version = DocumentVersionRecord(
            source_document_id=source_document.id,
            version_number=self.repository.next_document_version(source_document.id),
            content_sha256=content_sha256,
            object_uri=f"legacy-document://{source_document.legacy_document_id}/{content_sha256}",
            mime_type=mime_type,
            size_bytes=size_bytes,
            source_metadata_json={"mapping": "coursepilot_document_v1"},
        )
        self.repository.add(version)
        self.repository.flush()
        source_document.current_version_id = version.id
        return version
