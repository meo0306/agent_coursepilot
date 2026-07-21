import logging

from pydantic import BaseModel
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import coursepilot.services.lesson_service as lesson_service_module
from coursepilot.db.base import Base
from coursepilot.llm import LLMWorkflowCollector, generate_structured
from coursepilot.models import Course, GenerationTask
from coursepilot.schemas.lesson_schema import LessonGenerationParams
from coursepilot.services.graph_config import new_workflow_config, workflow_thread_id
from coursepilot.services.lesson_service import LessonService
from coursepilot.services.workflow_tracking import (
    finish_graph_invocation,
    merge_llm_metadata,
    start_graph_invocation,
)


class _ProbeOutput(BaseModel):
    value: str


def _context(course_id: str) -> dict:
    return {
        "chunk_id": "chunk-1",
        "course_id": course_id,
        "document_id": "doc-1",
        "source_type": "textbook",
        "chapter": "Search",
        "content": "state space search heuristic search",
        "score": 0.9,
        "verified": False,
    }


def _lesson_result(course_id: str) -> dict:
    context = _context(course_id)
    session_plan = [
        {
            "session_index": 1,
            "session_title": "Search",
            "duration": 45,
            "knowledge_points": ["state space search"],
            "teaching_focus": "search",
            "difficulty_points": ["heuristic"],
            "time_allocation": [
                {"activity": "intro", "minutes": 10},
                {"activity": "lecture", "minutes": 25},
                {"activity": "summary", "minutes": 10},
            ],
        }
    ]
    reference = {
        "chunk_id": "chunk-1",
        "source_type": "textbook",
        "chapter": "Search",
        "page": None,
    }
    return {
        "retrieved_contexts": [context],
        "knowledge_points": ["state space search"],
        "session_plan": session_plan,
        "lesson_design": {
            "course_name": "AI",
            "chapter": "Search",
            "total_sessions": 1,
            "session_duration": 45,
            "retrieved_contexts": [context],
            "knowledge_points": ["state space search"],
            "session_plan": session_plan,
            "sessions": [
                {
                    "session_index": 1,
                    "session_title": "Search",
                    "teaching_objectives": ["Explain state space search"],
                    "key_points": ["state space search"],
                    "difficult_points": ["heuristic"],
                    "teaching_process": [
                        {"stage": "intro", "minutes": 10, "content": "Introduce search"},
                        {"stage": "lecture", "minutes": 25, "content": "Explain search"},
                        {"stage": "summary", "minutes": 10, "content": "Summarize search"},
                    ],
                    "interaction_design": ["Discuss one search example."],
                    "blackboard_or_slide_suggestions": ["Draw a search tree."],
                    "homework_suggestion": ["Summarize state space search."],
                    "references": [reference],
                }
            ],
        },
        "validation_report": {
            "schema_valid": True,
            "session_count_valid": True,
            "time_allocation_valid": True,
            "required_fields_valid": True,
            "knowledge_coverage_valid": True,
            "citation_valid": True,
            "errors": [],
            "repair_attempts": 0,
        },
    }


def test_new_workflow_config_uses_thread_id_as_trace_id():
    config = new_workflow_config(namespace="lesson", course_id="course-1")
    thread_id = workflow_thread_id(config)

    assert thread_id.startswith("coursepilot-lesson-")
    assert config["configurable"]["course_id"] == "course-1"
    assert "user_id" not in config["configurable"]
    assert config["metadata"]["coursepilot_thread_id"] == thread_id
    assert f"thread:{thread_id}" in config["tags"]


def test_merge_llm_metadata_summarizes_all_task_invocations():
    collector = LLMWorkflowCollector(thread_id="thread-2")
    collector.record(
        {
            "prompt_name": "prompt/b",
            "prompt_sha256": "hash-b",
            "schema": "SchemaB",
            "attempt_count": 1,
            "attempts": [],
            "fallback_used": True,
            "fallback_reason": "timeout",
            "error_category": "timeout",
            "latency_ms": 20,
            "usage": {
                "input_tokens": 7,
                "output_tokens": 0,
                "total_tokens": 7,
                "usage_source": "deepseek_v3_tokenizer",
                "usage_estimated": True,
            },
        }
    )
    existing_outputs = {
        "prompt_hashes": {
            "prompt/a": {
                "prompt_name": "prompt/a",
                "prompt_sha256": "hash-a",
                "schema": "SchemaA",
            }
        },
        "llm_invocations": [
            {
                "prompt_name": "prompt/a",
                "prompt_sha256": "hash-a",
                "schema": "SchemaA",
                "attempt_count": 1,
                "attempts": [],
                "fallback_used": False,
                "fallback_reason": None,
                "error_category": None,
                "latency_ms": 10,
                "usage": {
                    "input_tokens": 3,
                    "output_tokens": 2,
                    "total_tokens": 5,
                    "usage_source": "provider",
                    "usage_estimated": False,
                },
            }
        ],
    }

    outputs = merge_llm_metadata(existing_outputs, collector)

    assert len(outputs["llm_invocations"]) == 2
    assert outputs["prompt_hashes"]["prompt/a"]["prompt_sha256"] == "hash-a"
    assert outputs["prompt_hashes"]["prompt/b"]["prompt_sha256"] == "hash-b"
    assert outputs["llm_usage_summary"]["call_count"] == 2
    assert outputs["llm_usage_summary"]["fallback_count"] == 1
    assert outputs["llm_usage_summary"]["total_tokens"] == 12
    assert outputs["llm_usage_summary"]["usage_source_counts"] == {
        "provider": 1,
        "deepseek_v3_tokenizer": 1,
    }


def test_finish_graph_invocation_logs_traceback(caplog):
    outputs = start_graph_invocation(
        task_outputs=None,
        namespace="lesson",
        thread_id="thread-failed",
    )
    caplog.set_level(logging.ERROR, logger="coursepilot.services.workflow_tracking")

    try:
        raise ValueError("graph exploded")
    except ValueError as exc:
        outputs = finish_graph_invocation(
            task_outputs=outputs,
            thread_id="thread-failed",
            status="failed",
            error_message=str(exc),
            exc_info=exc,
        )

    assert outputs["graph_invocations"][0]["status"] == "failed"
    assert outputs["graph_invocations"][0]["error_message"] == "graph exploded"
    assert "Traceback" in caplog.text
    assert "ValueError: graph exploded" in caplog.text


def test_lesson_service_persists_graph_and_llm_metadata(monkeypatch):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session_local = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    class FakeAgent:
        def invoke(self, payload, config):
            generate_structured(
                prompt_name="lesson/generate_lesson_design",
                output_schema=_ProbeOutput,
                payload={"probe": payload["course_id"]},
                fallback=lambda: _ProbeOutput(value="ok"),
            )
            return _lesson_result(payload["course_id"])

    monkeypatch.setattr(lesson_service_module, "coursepilot_lesson_agent", FakeAgent())

    try:
        with session_local() as session:
            course = Course(course_name="AI")
            session.add(course)
            session.commit()
            session.refresh(course)

            response = LessonService(session).generate_lesson(
                course.id,
                LessonGenerationParams(
                    chapter_range="Search",
                    total_sessions=1,
                    session_duration=45,
                ),
            )
            task = session.get(GenerationTask, response.task_id)

            assert task is not None
            outputs = task.intermediate_outputs_json
            assert outputs["graph_invocations"][0]["thread_id"].startswith("coursepilot-lesson-")
            assert outputs["graph_invocations"][0]["status"] == "success"
            assert outputs["prompt_hashes"]["lesson/generate_lesson_design"]["prompt_sha256"]
            assert outputs["llm_invocations"][0]["fallback_reason"] == "generation_mode_disabled"
            assert outputs["llm_usage_summary"]["fallback_count"] == 1
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()
