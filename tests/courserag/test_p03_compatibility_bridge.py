from datetime import timedelta
from pathlib import Path

from sqlalchemy.orm import Session

from core.settings import settings
from coursepilot.adapters.courserag_build_bridge import CourseRAGBuildCompatibilityBridge
from coursepilot.models import Course, Document, GenerationTask
from coursepilot.services.async_task_service import utc_now
from coursepilot.services.task_worker import CoursePilotTaskWorker
from courserag.persistence.models import (
    BuildJobRecord,
    BuildStageRunRecord,
    DocumentVersionRecord,
    KnowledgeBaseRecord,
)


def test_legacy_bridge_maps_document_and_worker_recovers_expired_lease(
    p03_session: Session, tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(settings, "COURSERAG_ARTIFACT_DIR", str(tmp_path / "worker-artifacts"))
    course = Course(course_name="Course")
    p03_session.add(course)
    p03_session.flush()
    source = tmp_path / "source.pdf"
    source.write_bytes(b"%PDF-p03-fixture")
    document = Document(
        course_id=course.id,
        file_name=source.name,
        file_path=str(source),
        file_type="pdf",
        source_type="upload",
    )
    p03_session.add(document)
    p03_session.commit()

    bridge = CourseRAGBuildCompatibilityBridge(p03_session, artifact_root=tmp_path / "artifacts")
    job = bridge.enqueue_legacy_document(document.id)
    task = p03_session.get(GenerationTask, job.queue_task_id)
    assert task is not None
    task.status = "running"
    task.worker_id = "dead-worker"
    task.locked_until = utc_now() - timedelta(seconds=1)
    p03_session.commit()

    engine = p03_session.get_bind()
    worker = CoursePilotTaskWorker(
        session_factory=lambda: Session(engine, expire_on_commit=False),
        lease_seconds=30,
    )
    assert worker.run_once() is True
    p03_session.expire_all()
    assert p03_session.get(type(task), task.id).status == "completed"
    assert p03_session.get(type(job), job.id).status == "succeeded"
    assert p03_session.query(DocumentVersionRecord).count() == 1
    assert p03_session.query(BuildStageRunRecord).filter_by(status="succeeded").count() == 1

    retry_task = bridge.retry(job.id, from_stage="legacy_document_inventory")
    assert worker.run_once() is True
    p03_session.expire_all()
    assert p03_session.get(GenerationTask, retry_task.id).status == "completed"
    attempts = (
        p03_session.query(BuildStageRunRecord)
        .filter_by(build_job_id=job.id, stage_name="legacy_document_inventory")
        .order_by(BuildStageRunRecord.attempt_number)
        .all()
    )
    assert [attempt.attempt_number for attempt in attempts] == [1, 2]
    assert all(attempt.status == "succeeded" for attempt in attempts)


def test_bridge_is_idempotent_for_same_document_content(
    p03_session: Session, tmp_path: Path
) -> None:
    course = Course(course_name="Course")
    p03_session.add(course)
    p03_session.flush()
    source = tmp_path / "source.docx"
    source.write_bytes(b"PK-p03-fixture")
    document = Document(
        course_id=course.id,
        file_name=source.name,
        file_path=str(source),
        file_type="docx",
        source_type="upload",
    )
    p03_session.add(document)
    p03_session.commit()
    bridge = CourseRAGBuildCompatibilityBridge(p03_session, artifact_root=tmp_path / "artifacts")
    first = bridge.enqueue_legacy_document(document.id)
    second = bridge.enqueue_legacy_document(document.id)
    assert first.id == second.id
    assert p03_session.query(DocumentVersionRecord).count() == 1


def test_worker_persists_build_failure_before_task_rollback(
    p03_session: Session, tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(settings, "COURSERAG_ARTIFACT_DIR", str(tmp_path / "artifacts"))
    course = Course(course_name="Course")
    p03_session.add(course)
    p03_session.flush()
    knowledge_base = KnowledgeBaseRecord(course_id=course.id, name=course.course_name)
    p03_session.add(knowledge_base)
    p03_session.flush()
    task = GenerationTask(
        course_id=course.id,
        task_type="courserag_build",
        status="pending",
        input_params_json={},
    )
    p03_session.add(task)
    p03_session.flush()
    job = BuildJobRecord(
        knowledge_base_id=knowledge_base.id,
        queue_task_id=task.id,
        request_hash="f" * 64,
        status="queued",
    )
    p03_session.add(job)
    p03_session.flush()
    task.input_params_json = {"build_job_id": job.id}
    p03_session.commit()

    engine = p03_session.get_bind()
    worker = CoursePilotTaskWorker(
        session_factory=lambda: Session(engine, expire_on_commit=False),
        lease_seconds=30,
    )
    assert worker.run_once() is True
    p03_session.expire_all()
    failed_job = p03_session.get(BuildJobRecord, job.id)
    failed_task = p03_session.get(GenerationTask, task.id)
    assert failed_job.status == "failed"
    assert failed_job.error_message == "Build stage failed; inspect protected service logs"
    assert failed_task.status == "failed"
    assert failed_task.error_message == "CourseRAG build failed (ValueError)"
    assert "no document versions" not in failed_task.error_message
