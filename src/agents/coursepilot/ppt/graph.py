from __future__ import annotations

from typing import Any, cast

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from agents.coursepilot.ppt.generator import PPTGenerator
from agents.coursepilot.ppt.state import PPTWorkflowState
from coursepilot.domain.interrupts import InterruptType


def _architecture(state: PPTWorkflowState) -> dict[str, Any]:
    raw_targets = state.get("request", {}).get("slide_targets")
    slide_targets = (
        cast(list[dict[str, object]], raw_targets) if isinstance(raw_targets, list) else None
    )
    architecture = PPTGenerator(
        use_model=bool(state.get("request", {}).get("use_model", False))
    ).build_architecture(
        course_id=state["course_id"],
        lesson_artifact_id=state["lesson_artifact_id"],
        template_id=state["template_id"],
        template_snapshot_id=state["template_snapshot_id"],
        context_evidence_ids=state.get("context_evidence_ids", []),
        slide_targets=slide_targets,
    )
    return {"architecture": architecture.model_dump(mode="json")}


def _architecture_review(state: PPTWorkflowState) -> dict[str, Any]:
    return {
        "decision": interrupt(
            {
                "interrupt_type": InterruptType.PPT_ARCHITECTURE.value,
                "task_id": state["task_id"],
                "architecture": state["architecture"],
                "allowed_actions": ["approve", "edit_resume", "replan", "reject", "cancel"],
            }
        )
    }


def _generate(state: PPTWorkflowState) -> dict[str, Any]:
    from coursepilot.domain.ppt import SlideArchitecture

    artifact = PPTGenerator(
        use_model=bool(state.get("request", {}).get("use_model", False))
    ).build_artifact(
        SlideArchitecture.model_validate(state["architecture"]),
        evidence_records=state.get("evidence_records", []),
    )
    return {
        "slides": [s.model_dump(mode="json") for s in artifact.slides],
        "artifact": artifact.model_dump(mode="json"),
    }


def _final_review(state: PPTWorkflowState) -> dict[str, Any]:
    return {
        "decision": interrupt(
            {
                "interrupt_type": InterruptType.PPT_FINAL.value,
                "task_id": state["task_id"],
                "artifact": state.get("artifact"),
                "allowed_actions": ["approve", "edit_resume", "regenerate", "reject", "cancel"],
            }
        )
    }


def build_ppt_graph(
    *, checkpointer: BaseCheckpointSaver, workflow_service: Any | None = None
) -> Any:
    graph = StateGraph(PPTWorkflowState)

    def load_inputs(state: PPTWorkflowState) -> dict[str, Any]:
        if workflow_service is None:
            return {}
        resolved = workflow_service.load_inputs(
            course_id=state["course_id"],
            lesson_artifact_id=state["lesson_artifact_id"],
            query=str(state.get("request", {}).get("query", "PPT generation")),
        )
        # Evidence text is consumed by the next node only; the durable state keeps refs/hashes.
        return {
            "context_evidence_ids": list(resolved.context_ref.evidence_ids),
            "context_ref": resolved.context_ref.model_dump(mode="json"),
            "input_hash": resolved.lesson_content_sha256,
            "knowledge_points": [
                item.model_dump(mode="json") for item in resolved.knowledge_points.items
            ],
            "evidence_records": list(resolved.evidence_records),
        }

    graph.add_node("load_inputs", load_inputs)
    graph.add_node("architecture", _architecture)
    graph.add_node("architecture_review", _architecture_review)
    graph.add_node("generate_slides", _generate)
    graph.add_node("final_review", _final_review)
    graph.add_edge(START, "load_inputs")
    graph.add_edge("load_inputs", "architecture")
    graph.add_edge("architecture", "architecture_review")
    graph.add_edge("architecture_review", "generate_slides")
    graph.add_edge("generate_slides", "final_review")
    graph.add_edge("final_review", END)
    return graph.compile(checkpointer=checkpointer)
