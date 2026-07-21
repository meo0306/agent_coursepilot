from fastapi import APIRouter, Depends, Header, HTTPException, Response, status
from sqlalchemy.orm import Session

from coursepilot.api.idempotency import execute_idempotent
from coursepilot.db.session import get_session
from coursepilot.models import Course
from coursepilot.schemas.lesson_schema import (
    ExportFileRead,
    LessonDesignRead,
    LessonGenerationParams,
    LessonRevisionRequest,
    LessonRevisionResponse,
)
from coursepilot.schemas.task_schema import AsyncTaskAccepted
from coursepilot.services.async_task_service import AsyncTaskService
from coursepilot.services.lesson_service import LessonService

router = APIRouter(tags=["coursepilot-lessons"])


@router.post(
    "/courses/{course_id}/lessons/generate",
    response_model=AsyncTaskAccepted,
    status_code=status.HTTP_202_ACCEPTED,
)
def generate_lesson(
    course_id: str,
    payload: LessonGenerationParams,
    response: Response,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    session: Session = Depends(get_session),
):
    if session.get(Course, course_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Course not found")
    return execute_idempotent(
        session=session,
        response=response,
        operation="lesson.generate",
        idempotency_key=idempotency_key,
        request_payload={"course_id": course_id, "payload": payload},
        fn=lambda: AsyncTaskService(session).enqueue(
            course_id=course_id,
            task_type="lesson_design",
            input_params={"params": payload.model_dump(mode="json")},
        ),
        response_status=status.HTTP_202_ACCEPTED,
        resource_type="async_task",
        resource_id_field="task_id",
        retry_if_resource_failed=True,
    )


@router.get("/lessons/{lesson_id}", response_model=LessonDesignRead)
def get_lesson(lesson_id: str, session: Session = Depends(get_session)):
    lesson = LessonService(session).get_lesson(lesson_id)
    if lesson is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lesson not found")
    return lesson


@router.post("/lessons/{lesson_id}/revise", response_model=LessonRevisionResponse)
def revise_lesson(
    lesson_id: str,
    payload: LessonRevisionRequest,
    session: Session = Depends(get_session),
):
    response = LessonService(session).revise_lesson(lesson_id, payload)
    if response is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lesson not found")
    return response


@router.post("/lessons/{lesson_id}/export", response_model=ExportFileRead)
def export_lesson(lesson_id: str, session: Session = Depends(get_session)):
    response = LessonService(session).export_lesson_docx(lesson_id)
    if response is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lesson not found")
    return response
