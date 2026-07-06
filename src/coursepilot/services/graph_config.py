from uuid import uuid4

from langchain_core.runnables import RunnableConfig


def new_workflow_config(*, namespace: str, course_id: str | None = None) -> RunnableConfig:
    """Create an isolated LangGraph config for CoursePilot product workflows."""
    configurable = {
        "thread_id": f"coursepilot-{namespace}-{uuid4()}",
        "checkpoint_ns": namespace,
    }
    if course_id:
        configurable["user_id"] = course_id
    return RunnableConfig(configurable=configurable)
