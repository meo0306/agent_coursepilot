import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from coursepilot.evals import run_real_eval
from coursepilot.evals.checkpoint import EvalCheckpointRunner
from coursepilot.evals.run_real_eval import (
    enforce_strict_fallback,
    fallback_violations_from_tasks,
    run_generation_workflows,
    validate_task_coverage,
)


class FakeCoursePilotClient:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def generate_lesson(self, *_args: Any, **_kwargs: Any) -> dict[str, Any]:
        self.calls.append("generate_lesson")
        return {"task_id": "task-lesson", "lesson_id": "lesson-1"}

    def export_lesson(self, *_args: Any, **_kwargs: Any) -> dict[str, Any]:
        self.calls.append("export_lesson")
        return {"file_path": "lesson.docx"}

    def create_exam_blueprint(self, *_args: Any, **_kwargs: Any) -> dict[str, Any]:
        self.calls.append("create_exam_blueprint")
        return {"task_id": "task-blueprint", "blueprint_id": "blueprint-1"}

    def confirm_exam_blueprint(self, *_args: Any, **_kwargs: Any) -> dict[str, Any]:
        self.calls.append("confirm_exam_blueprint")
        return {"status": "confirmed"}

    def enqueue_questions(self, *_args: Any, **_kwargs: Any) -> dict[str, Any]:
        self.calls.append("enqueue_questions")
        return {"task_id": "task-questions", "status": "accepted"}

    def wait_for_task(self, *_args: Any, **_kwargs: Any) -> dict[str, Any]:
        self.calls.append("wait_for_task")
        return {"questions": [], "validation_report": {"schema_valid": True}}

    def export_exam(self, *_args: Any, **_kwargs: Any) -> dict[str, Any]:
        self.calls.append("export_exam")
        return {"file_path": "exam.docx"}

    def generate_ppt_outline(self, *_args: Any, **_kwargs: Any) -> dict[str, Any]:
        self.calls.append("generate_ppt_outline")
        return {"task_id": "task-ppt", "outline_id": "outline-1"}

    def export_ppt(self, *_args: Any, **_kwargs: Any) -> dict[str, Any]:
        self.calls.append("export_ppt")
        return {"file_path": "slides.pptx"}


class UnexpectedCallClient:
    def __getattr__(self, name: str) -> Any:
        raise AssertionError(f"Resume unexpectedly called client method: {name}")


def checkpoint_runner(tmp_path: Path, *, resume: bool = False) -> EvalCheckpointRunner:
    return EvalCheckpointRunner(
        checkpoint_path=tmp_path / "real-eval.checkpoint.json",
        output_path=tmp_path / "real-eval.json",
        fingerprint="test-fingerprint",
        metadata={"test": True},
        resume=resume,
    )


def test_generation_collects_four_tasks_and_resume_recovers_question_task_id(tmp_path):
    client = FakeCoursePilotClient()
    workflows, task_ids = run_generation_workflows(
        client,
        "course-1",
        checkpoint_runner(tmp_path),
        generation_timeout=1.0,
    )

    assert task_ids == [
        "task-lesson",
        "task-blueprint",
        "task-questions",
        "task-ppt",
    ]
    assert workflows["exam_questions"]["result"]["task_id"] == "task-questions"
    checkpoint = json.loads((tmp_path / "real-eval.checkpoint.json").read_text(encoding="utf-8"))
    assert (
        checkpoint["steps"]["generation.exam_questions.enqueue"]["result"]["result"]["task_id"]
        == "task-questions"
    )
    assert (
        checkpoint["steps"]["generation.exam_questions.wait"]["result"]["result"]["task_id"]
        == "task-questions"
    )

    resumed_workflows, resumed_task_ids = run_generation_workflows(
        UnexpectedCallClient(),
        "course-1",
        checkpoint_runner(tmp_path, resume=True),
        generation_timeout=1.0,
    )

    assert resumed_task_ids == task_ids
    assert resumed_workflows["exam_questions"]["result"]["task_id"] == "task-questions"


def test_task_coverage_accepts_exact_four_task_set():
    expected = ["lesson", "blueprint", "questions", "ppt"]
    tasks = [{"id": task_id} for task_id in reversed(expected)]

    validate_task_coverage(expected, tasks)


@pytest.mark.parametrize(
    ("expected", "tasks", "message"),
    [
        (["lesson", "questions"], [{"id": "lesson"}], "missing=['questions']"),
        (
            ["lesson", "questions"],
            [{"id": "lesson"}, {"id": "questions"}, {"id": "unexpected"}],
            "unexpected=['unexpected']",
        ),
        (
            ["lesson", "questions"],
            [{"id": "lesson"}, {"id": "questions"}, {"id": "questions"}],
            "duplicate_observed=['questions']",
        ),
        (
            ["lesson", "lesson"],
            [{"id": "lesson"}],
            "duplicate_expected=['lesson']",
        ),
    ],
)
def test_task_coverage_rejects_incomplete_or_ambiguous_sets(expected, tasks, message):
    with pytest.raises(ValueError, match="Generation task coverage audit failed") as exc_info:
        validate_task_coverage(expected, tasks)

    assert message in str(exc_info.value)


def test_read_db_stats_propagates_database_errors(monkeypatch):
    def raise_database_error() -> None:
        raise RuntimeError("database unavailable")

    monkeypatch.setattr(run_real_eval, "get_coursepilot_engine", raise_database_error)

    with pytest.raises(RuntimeError, match="database unavailable"):
        run_real_eval.read_db_stats("course-1", ["task-1"])


class FakeResult:
    def __init__(
        self,
        *,
        scalar_value: int | None = None,
        rows: list[dict[str, Any]] | None = None,
    ) -> None:
        self.scalar_value = scalar_value
        self.rows = rows or []

    def scalar(self) -> int | None:
        return self.scalar_value

    def mappings(self) -> list[dict[str, Any]]:
        return self.rows


class FakeConnection:
    def __init__(self, task_rows: list[dict[str, Any]]) -> None:
        self.task_rows = task_rows
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def __enter__(self) -> "FakeConnection":
        return self

    def __exit__(self, *_args: Any) -> None:
        return None

    def execute(self, statement: Any, params: dict[str, Any]) -> FakeResult:
        sql = str(statement)
        self.calls.append((sql, params))
        if "select count(*)" in sql:
            return FakeResult(scalar_value=0)
        if "group by source_type" in sql:
            return FakeResult(rows=[])
        return FakeResult(rows=self.task_rows)


class FakeEngine:
    def __init__(self, connection: FakeConnection) -> None:
        self.connection = connection

    def connect(self) -> FakeConnection:
        return self.connection


def test_read_db_stats_queries_complete_course_task_set_and_exposes_unexpected_task(
    monkeypatch,
):
    timestamp = datetime(2026, 7, 23, tzinfo=UTC)
    expected_task_ids = [
        "task-lesson",
        "task-blueprint",
        "task-questions",
        "task-ppt",
    ]
    task_rows = [
        {
            "id": task_id,
            "task_type": task_type,
            "status": "completed",
            "created_at": timestamp,
            "updated_at": timestamp,
            "input_params_json": {},
            "intermediate_outputs_json": {"llm_usage_summary": {"fallback_count": 0}},
            "validation_report_json": {},
            "error_message": None,
        }
        for task_id, task_type in (
            ("task-lesson", "lesson_design"),
            ("task-blueprint", "exam_blueprint"),
            ("task-questions", "exam_questions"),
            ("task-ppt", "ppt_outline"),
            ("task-unexpected", "lesson_design"),
        )
    ]
    connection = FakeConnection(task_rows)
    monkeypatch.setattr(
        run_real_eval,
        "get_coursepilot_engine",
        lambda: FakeEngine(connection),
    )

    stats = run_real_eval.read_db_stats("course-1", expected_task_ids)

    task_sql, task_params = connection.calls[-1]
    assert "course_id = :course_id" in task_sql
    assert "task_type = any(:task_types)" in task_sql
    assert task_params == {
        "course_id": "course-1",
        "task_types": list(run_real_eval.EVAL_GENERATION_TASK_TYPES),
    }
    with pytest.raises(ValueError, match=r"unexpected=\['task-unexpected'\]"):
        validate_task_coverage(expected_task_ids, stats["tasks"])


def task_with_usage(fallback_count: Any) -> dict[str, Any]:
    return {
        "id": "task-1",
        "task_type": "lesson",
        "llm_usage_summary": {"fallback_count": fallback_count},
    }


def test_zero_fallback_usage_passes_audit():
    tasks = [
        {
            "id": task_id,
            "task_type": task_type,
            "llm_usage_summary": {"fallback_count": 0},
        }
        for task_id, task_type in (
            ("task-lesson", "lesson"),
            ("task-blueprint", "exam_blueprint"),
            ("task-questions", "exam_questions"),
            ("task-ppt", "ppt"),
        )
    ]

    assert fallback_violations_from_tasks(tasks) == []
    enforce_strict_fallback([], allow_fallback=False)


def test_nonzero_fallback_fails_strict_audit():
    violations = fallback_violations_from_tasks([task_with_usage(1)])

    assert violations[0]["reason"] == "fallback_used"
    with pytest.raises(SystemExit, match="Fallback audit failed"):
        enforce_strict_fallback(violations, allow_fallback=False)


@pytest.mark.parametrize(
    ("task", "reason"),
    [
        (
            {"id": "task-1", "task_type": "lesson"},
            "missing_or_invalid_llm_usage_summary",
        ),
        (
            {"id": "task-1", "task_type": "lesson", "llm_usage_summary": {}},
            "missing_fallback_count",
        ),
        (task_with_usage("0"), "invalid_fallback_count"),
        (task_with_usage(True), "invalid_fallback_count"),
        (task_with_usage(-1), "invalid_fallback_count"),
    ],
)
def test_missing_or_invalid_usage_fails_strict_audit(task, reason):
    violations = fallback_violations_from_tasks([task])

    assert violations[0]["reason"] == reason
    with pytest.raises(SystemExit, match="Fallback audit failed"):
        enforce_strict_fallback(violations, allow_fallback=False)
