from datetime import UTC, datetime

import pytest

from coursepilot.domain import (
    ArtifactRef,
    ArtifactVersion,
    BusinessTask,
    NodeResult,
    NodeStatus,
    RunContext,
    StorageKind,
    TaskStatus,
    WorkflowType,
)
from coursepilot.domain.common import canonical_sha256
from coursepilot.domain.task import require_task_transition
from coursepilot.runtime import compact_state, node_fingerprint, stable_thread_id
from coursepilot.runtime.state import can_reuse_node


def _now() -> datetime:
    return datetime.now(UTC)


def test_business_task_requires_stable_thread_and_legal_transition() -> None:
    thread_id = stable_thread_id(WorkflowType.LESSON, "task-1")
    task = BusinessTask(
        task_id="task-1",
        course_id="course-1",
        workflow_type=WorkflowType.LESSON,
        status=TaskStatus.QUEUED,
        current_stage="queued",
        thread_id=thread_id,
        created_at=_now(),
        updated_at=_now(),
    )
    assert task.thread_id == "coursepilot:lesson:task-1"
    require_task_transition(TaskStatus.QUEUED, TaskStatus.RUNNING)
    with pytest.raises(ValueError, match="illegal task transition"):
        require_task_transition(TaskStatus.COMPLETED, TaskStatus.RUNNING)


def test_artifact_version_is_content_addressed_and_rejects_host_path() -> None:
    content = {"title": "lesson", "items": [1, 2]}
    version = ArtifactVersion(
        artifact_id="artifact-1",
        version=1,
        content=content,
        content_hash=canonical_sha256(content),
        schema_version="v1",
        created_at=_now(),
        created_by="runtime",
    )
    assert version.version == 1
    with pytest.raises(ValueError, match="absolute host path"):
        ArtifactRef(
            artifact_id="artifact-1",
            artifact_type="lesson",
            artifact_version=1,
            storage_kind=StorageKind.OBJECT,
            storage_uri=r"D:\private\lesson.json",
            content_hash=version.content_hash,
            schema_version="v1",
        )


def test_node_fingerprint_controls_reuse() -> None:
    fingerprint = node_fingerprint(
        node_name="plan",
        inputs={"chapter": "A*"},
        template_hash="1" * 64,
        model_profile_hash="2" * 64,
        context_hashes=["3" * 64],
    )
    result = NodeResult(
        node_name="plan",
        status=NodeStatus.SUCCEEDED,
        input_fingerprint=fingerprint,
        started_at=_now(),
        ended_at=_now(),
    )
    assert can_reuse_node(result, fingerprint)
    assert not can_reuse_node(result.model_copy(update={"status": NodeStatus.FAILED}), fingerprint)


def test_compaction_removes_secrets_messages_and_large_text() -> None:
    state = {
        "run_context": RunContext(
            run_id="run-1",
            task_id="task-1",
            course_id="course-1",
            thread_id="coursepilot:lesson:task-1",
            git_commit="abc",
            graph_version="legacy-v1",
            template_snapshot_id="snapshot-1",
            template_snapshot_hash="1" * 64,
            prompt_manifest_hash="2" * 64,
            model_profile_manifest_hash="3" * 64,
            request_id="req-1",
            trace_id="trace-1",
        ),
        "request": {
            "api_key": "secret",
            "messages": ["unbounded"],
            "payload": "x" * 5000,
        },
        "artifacts": {},
        "context_packages": {},
        "node_results": [],
        "warnings": [],
        "summaries": {"plan": "ok"},
    }
    compacted = compact_state(state)
    assert "api_key" not in compacted["request"]
    assert "messages" not in compacted["request"]
    assert str(compacted["request"]["payload"]).startswith("<content-ref:")
