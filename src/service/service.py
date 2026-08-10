import json
import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Annotated, Any
from uuid import uuid4

from fastapi import APIRouter, Depends, FastAPI, HTTPException, status
from fastapi.responses import StreamingResponse
from fastapi.routing import APIRoute
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from langchain_core.messages import AIMessage, AnyMessage, HumanMessage
from langchain_core.runnables import RunnableConfig

from agents import DEFAULT_AGENT, AgentGraph, get_agent, get_all_agent_info, load_agent
from core import settings
from coursepilot.api import api_router as coursepilot_router
from coursepilot.llm import check_coursepilot_llm_health
from coursepilot.services.task_worker import CoursePilotTaskWorker
from courserag.api import (
    CourseRAGAPIError,
    courserag_api_error_handler,
    knowledge_point_router,
    retrieval_qa_router,
    verified_content_router,
)
from memory import initialize_database, initialize_store
from schema import (
    ChatHistory,
    ChatHistoryInput,
    ChatMessage,
    ServiceMetadata,
    StreamInput,
    UserInput,
)
from service.utils import langchain_to_chat_message

logger = logging.getLogger(__name__)


def custom_generate_unique_id(route: APIRoute) -> str:
    """Generate idiomatic operation IDs for OpenAPI client generation."""
    return route.name


def verify_bearer(
    http_auth: Annotated[
        HTTPAuthorizationCredentials | None,
        Depends(HTTPBearer(description="Please provide AUTH_SECRET api key.", auto_error=False)),
    ],
) -> None:
    if not settings.AUTH_SECRET:
        return
    auth_secret = settings.AUTH_SECRET.get_secret_value()
    if not http_auth or http_auth.credentials != auth_secret:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Initialize CoursePilot prompt agents and optional LangGraph persistence."""
    try:
        if settings.COURSEPILOT_GENERATION_MODE.lower() == "llm":
            check_coursepilot_llm_health()

        async with initialize_database() as saver, initialize_store() as store:
            if hasattr(saver, "setup"):
                await saver.setup()
            if hasattr(store, "setup"):
                await store.setup()

            for agent_info in get_all_agent_info():
                try:
                    await load_agent(agent_info.key)
                    agent = get_agent(agent_info.key)
                    agent.checkpointer = saver
                    agent.store = store
                    logger.info("Agent loaded: %s", agent_info.key)
                except Exception as exc:
                    logger.error("Failed to load agent %s: %s", agent_info.key, exc)

            task_worker = None
            if settings.COURSEPILOT_ASYNC_WORKER_ENABLED:
                task_worker = CoursePilotTaskWorker()
                task_worker.start()
                app.state.coursepilot_task_worker = task_worker
            try:
                yield
            finally:
                if task_worker is not None:
                    task_worker.stop()
                app.state.coursepilot_task_worker = None
    except Exception as exc:
        logger.error("Error during service initialization: %s", exc)
        raise


app = FastAPI(lifespan=lifespan, generate_unique_id_function=custom_generate_unique_id)
app.add_exception_handler(CourseRAGAPIError, courserag_api_error_handler)
router = APIRouter(dependencies=[Depends(verify_bearer)])


@router.get("/info")
async def info() -> ServiceMetadata:
    models = list(settings.AVAILABLE_MODELS)
    models.sort()
    return ServiceMetadata(
        agents=get_all_agent_info(),
        models=models,
        default_agent=DEFAULT_AGENT,
        default_model=settings.DEFAULT_MODEL,
    )


def _get_agent_or_404(agent_id: str) -> AgentGraph:
    try:
        return get_agent(agent_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Unknown agent: {agent_id}") from exc


def _build_config(user_input: UserInput) -> tuple[RunnableConfig, str]:
    run_id = uuid4()
    thread_id = user_input.thread_id or str(uuid4())
    user_id = user_input.user_id or str(uuid4())
    configurable: dict[str, Any] = {"thread_id": thread_id, "user_id": user_id}

    if user_input.model is not None:
        configurable["model"] = user_input.model

    if user_input.agent_config:
        reserved_keys = {"thread_id", "user_id", "model"}
        if overlap := reserved_keys & user_input.agent_config.keys():
            raise HTTPException(
                status_code=422,
                detail=f"agent_config contains reserved keys: {overlap}",
            )
        configurable.update(user_input.agent_config)

    return RunnableConfig(configurable=configurable, run_id=run_id), str(run_id)


async def _invoke_prompt_agent(user_input: UserInput, agent_id: str) -> ChatMessage:
    agent = _get_agent_or_404(agent_id)
    config, run_id = _build_config(user_input)
    result = await agent.ainvoke(
        {"messages": [HumanMessage(content=user_input.message)]},
        config=config,
    )
    messages = result.get("messages", []) if isinstance(result, dict) else []
    message = messages[-1] if messages else AIMessage(content="CoursePilot agent completed.")
    output = langchain_to_chat_message(message)
    output.run_id = run_id
    return output


@router.post("/{agent_id}/invoke", operation_id="invoke_with_agent_id")
@router.post("/invoke")
async def invoke(user_input: UserInput, agent_id: str = DEFAULT_AGENT) -> ChatMessage:
    """
    Prompt-entry invocation for CoursePilot agents.

    Structured lesson, exam, and PPT generation remains under /api/coursepilot/*.
    """
    try:
        return await _invoke_prompt_agent(user_input, agent_id)
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Agent invocation failed: %s", exc)
        raise HTTPException(status_code=500, detail="Unexpected error") from exc


async def message_generator(
    user_input: StreamInput,
    agent_id: str = DEFAULT_AGENT,
) -> AsyncGenerator[str, None]:
    try:
        message = await _invoke_prompt_agent(user_input, agent_id)
        yield f"data: {json.dumps({'type': 'message', 'content': message.model_dump()})}\n\n"
    except HTTPException as exc:
        yield f"data: {json.dumps({'type': 'error', 'content': exc.detail})}\n\n"
    except Exception as exc:
        logger.error("Agent stream failed: %s", exc)
        yield f"data: {json.dumps({'type': 'error', 'content': 'Internal server error'})}\n\n"
    finally:
        yield "data: [DONE]\n\n"


def _sse_response_example() -> dict[int | str, Any]:
    return {
        status.HTTP_200_OK: {
            "description": "Server Sent Event Response",
            "content": {
                "text/event-stream": {
                    "example": "data: {'type': 'message', 'content': {...}}\n\ndata: [DONE]\n\n",
                    "schema": {"type": "string"},
                }
            },
        }
    }


@router.post(
    "/{agent_id}/stream",
    response_class=StreamingResponse,
    responses=_sse_response_example(),
    operation_id="stream_with_agent_id",
)
@router.post("/stream", response_class=StreamingResponse, responses=_sse_response_example())
async def stream(user_input: StreamInput, agent_id: str = DEFAULT_AGENT) -> StreamingResponse:
    """Stream the CoursePilot prompt-entry response as server-sent events."""
    return StreamingResponse(
        message_generator(user_input, agent_id), media_type="text/event-stream"
    )


@router.post("/history")
async def history(input: ChatHistoryInput) -> ChatHistory:
    """Get prompt-agent chat history for the default CoursePilot agent."""
    agent = _get_agent_or_404(DEFAULT_AGENT)
    try:
        state_snapshot = await agent.aget_state(
            config=RunnableConfig(configurable={"thread_id": input.thread_id})
        )
        messages: list[AnyMessage] = state_snapshot.values.get("messages", [])
        return ChatHistory(messages=[langchain_to_chat_message(message) for message in messages])
    except Exception as exc:
        logger.error("Chat history lookup failed: %s", exc)
        raise HTTPException(status_code=500, detail="Unexpected error") from exc


@app.get("/health")
async def health_check() -> dict[str, str]:
    """Health check endpoint."""
    return {"status": "ok"}


app.include_router(router)
app.include_router(coursepilot_router, dependencies=[Depends(verify_bearer)])
app.include_router(knowledge_point_router, dependencies=[Depends(verify_bearer)])
app.include_router(retrieval_qa_router, dependencies=[Depends(verify_bearer)])
app.include_router(verified_content_router, dependencies=[Depends(verify_bearer)])
