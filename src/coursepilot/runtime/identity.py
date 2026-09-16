from __future__ import annotations

from coursepilot.domain.task import WorkflowType


def stable_thread_id(workflow_type: WorkflowType | str, task_id: str) -> str:
    workflow = WorkflowType(workflow_type)
    if not task_id.strip():
        raise ValueError("task_id cannot be blank")
    return f"coursepilot:{workflow.value}:{task_id}"
