"""
This module provides utilities for creating isolated LangGraph configurations for CoursePilot product workflows.
"""
from uuid import uuid4

from langchain_core.runnables import RunnableConfig


def new_workflow_config(*, namespace: str, course_id: str | None = None) -> RunnableConfig:
    """Create an isolated LangGraph config for CoursePilot product workflows."""
    thread_id = f"coursepilot-{namespace}-{uuid4()}"
    configurable = {
        "thread_id": thread_id,
        "checkpoint_ns": namespace,
    }
    if course_id:
        configurable["course_id"] = course_id
    return RunnableConfig(
        configurable=configurable,
        metadata={
            "coursepilot_thread_id": thread_id,
            "coursepilot_namespace": namespace,
            "course_id": course_id,
        },
        tags=["coursepilot", f"coursepilot:{namespace}", f"thread:{thread_id}"],
    )


def workflow_thread_id(config: RunnableConfig) -> str:
    """Return the CoursePilot workflow thread id carried by a RunnableConfig."""
    configurable = config.get("configurable", {})
    return str(configurable["thread_id"])
