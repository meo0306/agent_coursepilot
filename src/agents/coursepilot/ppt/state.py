from __future__ import annotations

from typing import NotRequired, TypedDict


class PPTWorkflowState(TypedDict):
    task_id: str
    course_id: str
    lesson_artifact_id: str
    template_id: str
    template_snapshot_id: str
    request: dict[str, object]
    context_evidence_ids: list[str]
    context_ref: NotRequired[dict[str, object]]
    input_hash: NotRequired[str]
    knowledge_points: NotRequired[list[dict[str, object]]]
    evidence_records: NotRequired[list[dict[str, object]]]
    architecture: NotRequired[dict[str, object]]
    slides: NotRequired[list[dict[str, object]]]
    artifact: NotRequired[dict[str, object]]
    render_report: NotRequired[dict[str, object]]
    decision: NotRequired[dict[str, object]]
    legacy: NotRequired[bool]
