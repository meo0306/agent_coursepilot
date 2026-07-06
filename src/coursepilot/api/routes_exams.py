from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from coursepilot.db.session import get_session
from coursepilot.schemas.exam_schema import (
    ExamBlueprintRead,
    ExamBlueprintResponse,
    ExamExportResponse,
    ExamGenerationParams,
    QuestionGenerationResponse,
)
from coursepilot.schemas.question_schema import QuestionRead
from coursepilot.services.exam_service import BlueprintNotConfirmedError, ExamService

router = APIRouter(tags=["coursepilot-exams"])


@router.post(
    "/courses/{course_id}/exams/blueprint",
    response_model=ExamBlueprintResponse,
)
def create_exam_blueprint(
    course_id: str,
    payload: ExamGenerationParams,
    session: Session = Depends(get_session),
):
    try:
        return ExamService(session).create_blueprint(course_id, payload)
    except ValueError as exc:
        detail = str(exc)
        status_code = status.HTTP_404_NOT_FOUND if "Course not found" in detail else status.HTTP_400_BAD_REQUEST
        raise HTTPException(status_code=status_code, detail=detail) from exc


@router.get("/exams/{blueprint_id}", response_model=ExamBlueprintRead)
def get_exam_blueprint(blueprint_id: str, session: Session = Depends(get_session)):
    blueprint = ExamService(session).get_blueprint(blueprint_id)
    if blueprint is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Exam blueprint not found")
    return blueprint


@router.post("/exams/{blueprint_id}/confirm", response_model=ExamBlueprintRead)
def confirm_exam_blueprint(blueprint_id: str, session: Session = Depends(get_session)):
    blueprint = ExamService(session).confirm_blueprint(blueprint_id)
    if blueprint is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Exam blueprint not found")
    return blueprint


@router.post("/exams/{blueprint_id}/generate", response_model=QuestionGenerationResponse)
def generate_exam_questions(blueprint_id: str, session: Session = Depends(get_session)):
    try:
        response = ExamService(session).generate_questions(blueprint_id)
    except BlueprintNotConfirmedError as exc:
        # 如果蓝图未确认，则返回 409 冲突错误
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    if response is None:
        # 如果蓝图不存在，则返回 404 错误
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Exam blueprint not found")
    return response


@router.get("/exams/{blueprint_id}/questions", response_model=list[QuestionRead])
def list_exam_questions(blueprint_id: str, session: Session = Depends(get_session)):
    questions = ExamService(session).list_questions(blueprint_id)
    if questions is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Exam blueprint not found")
    return questions


@router.post("/exams/{blueprint_id}/export", response_model=ExamExportResponse)
def export_exam_files(blueprint_id: str, session: Session = Depends(get_session)):
    try:
        response = ExamService(session).export_exam_files(blueprint_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    if response is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Exam blueprint not found")
    return response
