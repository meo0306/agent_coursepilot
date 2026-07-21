from fastapi import APIRouter, Depends, Header, HTTPException, Response, status
from sqlalchemy.orm import Session

from coursepilot.api.idempotency import execute_idempotent
from coursepilot.db.session import get_session
from coursepilot.models import LessonDesign
from coursepilot.schemas.ppt_schema import (
    PPTExportResponse,
    PPTGenerationParams,
    SlideOutlineRead,
)
from coursepilot.schemas.task_schema import AsyncTaskAccepted
from coursepilot.services.async_task_service import AsyncTaskService
from coursepilot.services.ppt_service import PPTService

router = APIRouter(tags=["coursepilot-ppt"])


@router.post(
    "/lessons/{lesson_id}/ppt/generate",
    response_model=AsyncTaskAccepted,
    status_code=status.HTTP_202_ACCEPTED,
)
def generate_ppt_outline(
    lesson_id: str,
    payload: PPTGenerationParams,
    response: Response,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    session: Session = Depends(get_session),
):
    lesson = session.get(LessonDesign, lesson_id)
    if lesson is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lesson not found")
    return execute_idempotent(
        session=session,
        response=response,
        operation="ppt.generate",
        idempotency_key=idempotency_key,
        request_payload={"lesson_id": lesson_id, "payload": payload},
        fn=lambda: AsyncTaskService(session).enqueue(
            course_id=lesson.course_id,
            task_type="ppt_outline",
            input_params={
                "lesson_id": lesson.id,
                "params": payload.model_dump(mode="json"),
            },
        ),
        response_status=status.HTTP_202_ACCEPTED,
        resource_type="async_task",
        resource_id_field="task_id",
        retry_if_resource_failed=True,
    )


@router.get("/ppt/{outline_id}", response_model=SlideOutlineRead)
def get_ppt_outline(outline_id: str, session: Session = Depends(get_session)):
    outline = PPTService(session).get_outline(outline_id)
    if outline is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="PPT outline not found")
    return outline


@router.post("/ppt/{outline_id}/export", response_model=PPTExportResponse)
def export_ppt(outline_id: str, session: Session = Depends(get_session)):
    try:
        response = PPTService(session).export_pptx(outline_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    if response is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="PPT outline not found")
    return response
