from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from coursepilot.db.session import get_session
from coursepilot.schemas.lesson_schema import (
    ExportFileRead,
    LessonDesignRead,
    LessonGenerationParams,
    LessonGenerationResponse,
    LessonRevisionRequest,
    LessonRevisionResponse,
)
from coursepilot.services.lesson_service import LessonService

router = APIRouter(tags=["coursepilot-lessons"])


@router.post(
    "/courses/{course_id}/lessons/generate",
    response_model=LessonGenerationResponse,
)
def generate_lesson(
    course_id: str,
    payload: LessonGenerationParams,
    session: Session = Depends(get_session),
):
    try:
        return LessonService(session).generate_lesson(course_id, payload)
    except ValueError as exc:
        detail = str(exc)
        status_code = status.HTTP_404_NOT_FOUND if "Course not found" in detail else status.HTTP_400_BAD_REQUEST
        raise HTTPException(status_code=status_code, detail=detail) from exc


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

