from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from core.settings import settings
from coursepilot.db.base import Base
from coursepilot.domain.task import WorkflowType
from coursepilot.models import (
    ArtifactVersionRecord,
    Course,
    GenerationTask,
    ModelInvocationRecord,
    NodeRunRecord,
    WorkflowRunRecord,
)
from coursepilot.runtime.legacy_adapter import LegacyRuntimeAdapter
from coursepilot.runtime.repository import RuntimeRepository


def test_legacy_adapter_pins_snapshot_run_and_immutable_artifact() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        course = Course(course_name="Test")
        session.add(course)
        session.flush()
        task = GenerationTask(
            course_id=course.id,
            task_type="lesson_design",
            status="running",
            input_params_json={"teaching_template": "standard"},
        )
        session.add(task)
        session.flush()
        adapter = LegacyRuntimeAdapter(RuntimeRepository(session))

        run_id = adapter.begin(
            task=task,
            workflow_type=WorkflowType.LESSON,
            legacy_template="standard",
            input_payload=task.input_params_json,
            request_id="request-1",
            trace_id="trace-1",
        )
        adapter.complete(
            task=task,
            run_id=run_id,
            artifact_type="lesson",
            content={"title": "Lesson"},
            status="completed",
            invocations=[
                {
                    "prompt_name": "lesson/generate_lesson_design",
                    "prompt_sha256": "a" * 64,
                    "status": "fallback",
                    "attempt_count": 0,
                    "fallback_used": True,
                    "usage": {
                        "input_tokens": 7,
                        "output_tokens": 3,
                        "total_tokens": 10,
                        "usage_estimated": True,
                    },
                }
            ],
        )
        session.commit()

        run = session.get(WorkflowRunRecord, run_id)
        versions = list(session.scalars(select(ArtifactVersionRecord)))
        assert task.thread_id == f"coursepilot:lesson:{task.id}"
        assert task.template_snapshot_id is not None
        assert run is not None and run.status == "completed"
        assert len(versions) == 1 and versions[0].version == 1
        assert versions[0].content_json == {"title": "Lesson"}
        node = session.scalar(select(NodeRunRecord))
        invocation = session.scalar(select(ModelInvocationRecord))
        assert node is not None and node.status == "succeeded"
        assert invocation is not None and invocation.fallback_used is True
        assert invocation.usage_known is False
        assert invocation.total_tokens is None


def test_legacy_adapter_rejects_unknown_template_without_side_effects() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        course = Course(course_name="Test")
        session.add(course)
        session.flush()
        task = GenerationTask(
            course_id=course.id,
            task_type="lesson_design",
            status="running",
            input_params_json={},
        )
        session.add(task)
        session.flush()
        adapter = LegacyRuntimeAdapter(RuntimeRepository(session))

        try:
            adapter.begin(
                task=task,
                workflow_type=WorkflowType.LESSON,
                legacy_template="unknown",
                input_payload={},
                request_id="request-1",
                trace_id="trace-1",
            )
        except ValueError as exc:
            assert "Unsupported legacy template" in str(exc)
        else:
            raise AssertionError("unknown template must fail")
        assert task.thread_id is None


def test_legacy_adapter_can_disable_compatibility_recording(monkeypatch) -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        course = Course(course_name="Test")
        session.add(course)
        session.flush()
        task = GenerationTask(
            course_id=course.id,
            task_type="lesson_design",
            status="running",
            input_params_json={"teaching_template": "standard"},
        )
        session.add(task)
        session.flush()
        monkeypatch.setattr(settings, "COURSEPILOT_RUNTIME_COMPATIBILITY_RECORDING", False)
        adapter = LegacyRuntimeAdapter(RuntimeRepository(session))

        run_id = adapter.begin(
            task=task,
            workflow_type=WorkflowType.LESSON,
            legacy_template="standard",
            input_payload=task.input_params_json,
            request_id="request-1",
            trace_id="trace-1",
        )

        assert run_id is None
        assert task.thread_id is None
        assert session.scalar(select(WorkflowRunRecord)) is None
