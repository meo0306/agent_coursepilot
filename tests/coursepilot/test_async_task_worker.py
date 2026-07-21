from datetime import timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from coursepilot.db.base import Base
from coursepilot.models import Course, GenerationTask
from coursepilot.services.async_task_service import complete_execution_task, utc_now
from coursepilot.services.task_worker import CoursePilotTaskWorker


def _runtime():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(
        bind=engine,
        autoflush=False,
        expire_on_commit=False,
    )
    with session_factory() as session:
        course = Course(course_name="Async")
        session.add(course)
        session.commit()
        course_id = course.id
    return engine, session_factory, course_id


def _complete_without_domain_work(session: Session, task: GenerationTask) -> None:
    complete_execution_task(task, {"task_id": task.id, "ok": True})
    session.commit()


def test_worker_claims_pending_task_and_persists_result(monkeypatch):
    engine, session_factory, course_id = _runtime()
    try:
        with session_factory() as session:
            task = GenerationTask(
                course_id=course_id,
                task_type="test",
                status="pending",
                input_params_json={},
            )
            session.add(task)
            session.commit()
            task_id = task.id

        monkeypatch.setattr(
            CoursePilotTaskWorker,
            "_dispatch",
            staticmethod(_complete_without_domain_work),
        )
        worker = CoursePilotTaskWorker(
            session_factory=session_factory,
            poll_seconds=0,
            lease_seconds=30,
        )

        assert worker.run_once() is True
        assert worker.run_once() is False
        with session_factory() as session:
            task = session.get(GenerationTask, task_id)
            assert task is not None
            assert task.status == "completed"
            assert task.result_json == {"task_id": task_id, "ok": True}
            assert task.attempt_count == 1
            assert task.worker_id is None
            assert task.locked_until is None
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()


def test_worker_reclaims_only_expired_running_task(monkeypatch):
    engine, session_factory, course_id = _runtime()
    try:
        with session_factory() as session:
            expired = GenerationTask(
                course_id=course_id,
                task_type="test",
                status="running",
                input_params_json={},
                attempt_count=1,
                worker_id="dead-worker",
                locked_until=utc_now() - timedelta(seconds=1),
            )
            active = GenerationTask(
                course_id=course_id,
                task_type="test",
                status="running",
                input_params_json={},
                attempt_count=1,
                worker_id="active-worker",
                locked_until=utc_now() + timedelta(minutes=5),
            )
            session.add_all([expired, active])
            session.commit()
            expired_id = expired.id
            active_id = active.id

        monkeypatch.setattr(
            CoursePilotTaskWorker,
            "_dispatch",
            staticmethod(_complete_without_domain_work),
        )
        worker = CoursePilotTaskWorker(
            session_factory=session_factory,
            poll_seconds=0,
            lease_seconds=30,
        )

        assert worker.run_once() is True
        assert worker.run_once() is False
        with session_factory() as session:
            expired = session.get(GenerationTask, expired_id)
            active = session.get(GenerationTask, active_id)
            assert expired is not None
            assert active is not None
            assert expired.status == "completed"
            assert expired.attempt_count == 2
            assert active.status == "running"
            assert active.attempt_count == 1
            assert active.worker_id == "active-worker"
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()
