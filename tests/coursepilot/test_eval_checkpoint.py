import json

import pytest

from coursepilot.evals import checkpoint as checkpoint_module
from coursepilot.evals.checkpoint import EvalCheckpointRunner, atomic_write_json


def _runner(tmp_path, *, resume=False, fingerprint="fingerprint", overwrite=False):
    return EvalCheckpointRunner(
        checkpoint_path=tmp_path / "eval.checkpoint.json",
        output_path=tmp_path / "eval.report.json",
        fingerprint=fingerprint,
        metadata={"sample": "fixture"},
        resume=resume,
        overwrite=overwrite,
    )


def test_checkpoint_persists_partial_and_final_reports(tmp_path):
    runner = _runner(tmp_path)

    result = runner.call("course.create", "create_course", lambda: {"id": "course-1"})
    runner.update_context(course_id=result["result"]["id"])

    checkpoint = json.loads((tmp_path / "eval.checkpoint.json").read_text(encoding="utf-8"))
    partial = json.loads((tmp_path / "eval.report.json").read_text(encoding="utf-8"))
    assert checkpoint["steps"]["course.create"]["status"] == "succeeded"
    assert checkpoint["context"]["course_id"] == "course-1"
    assert partial["partial"] is True
    assert partial["run"]["status"] == "running"

    report = {"metric": 1.0}
    runner.complete(report)

    final_report = json.loads((tmp_path / "eval.report.json").read_text(encoding="utf-8"))
    assert final_report["metric"] == 1.0
    assert final_report["run"]["status"] == "completed"
    assert final_report["steps"]["course.create"]["status"] == "succeeded"


def test_resume_skips_success_and_retries_failed_step(tmp_path):
    runner = _runner(tmp_path)
    runner.call("course.create", "create_course", lambda: {"id": "course-1"})

    with pytest.raises(RuntimeError, match="temporary failure"):
        runner.call(
            "generation.lesson",
            "generate_lesson",
            lambda: (_ for _ in ()).throw(RuntimeError("temporary failure")),
        )

    resumed = _runner(tmp_path, resume=True)
    cached = resumed.call(
        "course.create",
        "create_course",
        lambda: (_ for _ in ()).throw(AssertionError("successful step was rerun")),
    )
    retried = resumed.call(
        "generation.lesson",
        "generate_lesson",
        lambda: {"lesson_id": "lesson-1"},
    )

    assert cached["result"]["id"] == "course-1"
    assert retried["result"]["lesson_id"] == "lesson-1"
    assert resumed.state["steps"]["generation.lesson"]["attempt"] == 2
    assert len(resumed.state["steps"]["generation.lesson"]["history"]) == 1


def test_resume_rejects_changed_fingerprint(tmp_path):
    _runner(tmp_path, fingerprint="first")

    with pytest.raises(ValueError, match="does not match"):
        _runner(tmp_path, resume=True, fingerprint="changed")


def test_existing_checkpoint_requires_explicit_resume_or_overwrite(tmp_path):
    _runner(tmp_path)

    with pytest.raises(FileExistsError, match="--resume"):
        _runner(tmp_path)

    replacement = _runner(tmp_path, overwrite=True)
    assert replacement.state["steps"] == {}


def test_idempotency_key_is_stable_across_resume(tmp_path):
    runner = _runner(tmp_path)
    first_key = runner.idempotency_key("generation.lesson")

    resumed = _runner(tmp_path, resume=True)

    assert resumed.idempotency_key("generation.lesson") == first_key
    assert resumed.idempotency_key("generation.ppt") != first_key
    assert first_key.startswith(f"coursepilot-eval:{runner.run_id}:")


def test_atomic_write_retries_transient_permission_error(tmp_path, monkeypatch):
    path = tmp_path / "report.json"
    path.write_text('{"old": true}\n', encoding="utf-8")
    real_replace = checkpoint_module.os.replace
    attempts = []
    delays = []

    def flaky_replace(source, destination):
        attempts.append((source, destination))
        if len(attempts) < 3:
            raise PermissionError(13, "transient file lock", destination)
        real_replace(source, destination)

    monkeypatch.setattr(checkpoint_module.os, "replace", flaky_replace)
    monkeypatch.setattr(checkpoint_module.time, "sleep", delays.append)

    atomic_write_json(path, {"new": True})

    assert len(attempts) == 3
    assert delays == [0.025, 0.05]
    assert json.loads(path.read_text(encoding="utf-8")) == {"new": True}
    assert list(tmp_path.glob("*.tmp")) == []
