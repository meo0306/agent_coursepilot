from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from core.settings import settings
from coursepilot.domain.common import canonical_sha256
from coursepilot.domain.task import WorkflowType
from coursepilot.models import GenerationTask
from coursepilot.prompts.loader import load_prompt
from coursepilot.runtime.identity import stable_thread_id
from coursepilot.runtime.repository import RuntimeRepository
from coursepilot.templates import TemplateRegistry

_PROMPTS_BY_WORKFLOW = {
    WorkflowType.LESSON: ("lesson/plan_sessions", "lesson/generate_lesson_design"),
    WorkflowType.EXAM: ("exam/plan_exam_blueprint", "exam/generate_short_answer"),
    WorkflowType.PPT: ("ppt/generate_slide_outline", "ppt/repair_slide_outline"),
}

_TEMPLATE_ALIASES = {
    (WorkflowType.LESSON, "standard"): "lesson_standard_university_v1",
    (WorkflowType.LESSON, "seminar"): "lesson_seminar_v1",
    (WorkflowType.LESSON, "lab_practice"): "lesson_lab_practice_v1",
    (WorkflowType.EXAM, "homework"): "exam_chapter_assignment_v1",
    (WorkflowType.EXAM, "unit_quiz"): "exam_unit_quiz_v1",
    (WorkflowType.EXAM, "exam"): "exam_midterm_final_v1",
    (WorkflowType.PPT, "standard"): "ppt_standard_lecture_v1",
    (WorkflowType.PPT, "concept_explanation"): "ppt_concept_explanation_v1",
    (WorkflowType.PPT, "case_seminar"): "ppt_case_seminar_v1",
}


class LegacyRuntimeAdapter:
    """Mirror legacy successes into P11 facts without changing wire responses."""

    def __init__(self, repository: RuntimeRepository):
        self.repository = repository
        self.registry = TemplateRegistry(Path(settings.COURSEPILOT_TEMPLATE_REGISTRY_PATH))

    def begin(
        self,
        *,
        task: GenerationTask,
        workflow_type: WorkflowType,
        legacy_template: str,
        input_payload: Mapping[str, Any],
        request_id: str,
        trace_id: str,
    ) -> str | None:
        if not settings.COURSEPILOT_RUNTIME_COMPATIBILITY_RECORDING:
            return None
        template_id = self._template_id(workflow_type, legacy_template)
        prompt_hashes = {
            name: canonical_sha256({"text": load_prompt(name)})
            for name in _PROMPTS_BY_WORKFLOW[workflow_type]
        }
        model_profile_sha256 = canonical_sha256(
            Path(settings.COURSEPILOT_MODEL_PROFILE_PATH).read_text(encoding="utf-8")
        )
        snapshot = self.registry.snapshot(
            template_id,
            prompt_hashes=prompt_hashes,
            model_profile_sha256=model_profile_sha256,
            schema_versions={"input": "legacy-v1", "output": "legacy-v1"},
        )
        record = self.repository.pin_template_snapshot(snapshot.model_dump(mode="json"))
        task.workflow_type = workflow_type.value
        task.current_stage = "legacy_compatibility"
        task.thread_id = stable_thread_id(workflow_type, task.id)
        task.template_snapshot_id = record.id
        run = self.repository.start_run(
            task=task,
            template_snapshot=record,
            graph_version="legacy-compatibility-p11-v1",
            request_id=request_id,
            trace_id=trace_id,
            input_payload=input_payload,
        )
        return run.id

    @staticmethod
    def validate_template(workflow_type: WorkflowType, legacy_template: str) -> str:
        return LegacyRuntimeAdapter._template_id(workflow_type, legacy_template)

    def complete(
        self,
        *,
        task: GenerationTask,
        run_id: str | None,
        artifact_type: str,
        content: dict[str, Any] | list[Any],
        status: str,
        invocations: list[dict[str, Any]] | None = None,
    ) -> None:
        if run_id is None:
            return
        artifact = self.repository.find_artifact(
            task_id=task.id,
            artifact_type=artifact_type,
        )
        _, _, artifact_ref = self.repository.append_artifact_version(
            task=task,
            artifact_type=artifact_type,
            schema_version="legacy-v1",
            content=content,
            created_by="legacy_runtime_adapter",
            source_run_id=run_id,
            artifact=artifact,
        )
        capability_sha256 = canonical_sha256(
            Path(settings.COURSEPILOT_PROVIDER_CAPABILITY_PATH).read_text(encoding="utf-8")
        )
        self.repository.record_legacy_node(
            run_id=run_id,
            node_name="legacy_graph_compatibility",
            input_fingerprint=canonical_sha256(task.input_params_json),
            artifact_refs=[artifact_ref.model_dump(mode="json")],
            invocations=invocations or [],
            provider=settings.COURSEPILOT_MAIN_PROVIDER,
            model=settings.COURSEPILOT_MAIN_MODEL or settings.COMPATIBLE_MODEL or "unknown",
            capability_sha256=capability_sha256,
        )
        self.repository.finish_run(run_id, status=status)
        task.current_stage = "completed" if status == "completed" else "needs_review"

    def fail(self, run_id: str | None) -> None:
        if run_id is None:
            return
        self.repository.finish_run(run_id, status="failed")

    @staticmethod
    def _template_id(workflow_type: WorkflowType, legacy_template: str) -> str:
        try:
            return _TEMPLATE_ALIASES[(workflow_type, legacy_template)]
        except KeyError as exc:
            raise ValueError(
                f"Unsupported legacy template for {workflow_type.value}: {legacy_template}"
            ) from exc
