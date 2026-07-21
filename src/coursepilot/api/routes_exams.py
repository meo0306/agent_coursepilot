from fastapi import APIRouter, Depends, Header, HTTPException, Response, status
from sqlalchemy.orm import Session

from coursepilot.api.idempotency import execute_idempotent
from coursepilot.db.session import get_session
from coursepilot.models import Course, ExamBlueprint
from coursepilot.schemas.exam_schema import (
    ExamBlueprintRead,
    ExamExportResponse,
    ExamGenerationParams,
)
from coursepilot.schemas.question_schema import QuestionRead
from coursepilot.schemas.task_schema import AsyncTaskAccepted
from coursepilot.services.async_task_service import AsyncTaskService
from coursepilot.services.exam_service import ExamService

router = APIRouter(tags=["coursepilot-exams"])


@router.post(
    "/courses/{course_id}/exams/blueprint",
    response_model=AsyncTaskAccepted,
    status_code=status.HTTP_202_ACCEPTED,
)
def create_exam_blueprint(
    course_id: str,
    payload: ExamGenerationParams,
    response: Response,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    session: Session = Depends(get_session),
):
    if session.get(Course, course_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Course not found")
    return execute_idempotent(
        session=session,
        response=response,
        operation="exam.blueprint",
        idempotency_key=idempotency_key,
        request_payload={"course_id": course_id, "payload": payload},
        fn=lambda: AsyncTaskService(session).enqueue(
            course_id=course_id,
            task_type="exam_blueprint",
            input_params={"params": payload.model_dump(mode="json")},
        ),
        response_status=status.HTTP_202_ACCEPTED,
        resource_type="async_task",
        resource_id_field="task_id",
        retry_if_resource_failed=True,
    )


@router.get("/exams/{blueprint_id}", response_model=ExamBlueprintRead)
def get_exam_blueprint(blueprint_id: str, session: Session = Depends(get_session)):
    blueprint = ExamService(session).get_blueprint(blueprint_id)
    if blueprint is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Exam blueprint not found"
        )
    return blueprint


@router.post("/exams/{blueprint_id}/confirm", response_model=ExamBlueprintRead)
def confirm_exam_blueprint(blueprint_id: str, session: Session = Depends(get_session)):
    blueprint = ExamService(session).confirm_blueprint(blueprint_id)
    if blueprint is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Exam blueprint not found"
        )
    return blueprint


@router.post(
    "/exams/{blueprint_id}/generate",
    response_model=AsyncTaskAccepted,
    status_code=status.HTTP_202_ACCEPTED,
)
def generate_exam_questions(
    blueprint_id: str,
    response: Response,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    session: Session = Depends(get_session),
):
    blueprint = session.get(ExamBlueprint, blueprint_id)
    if blueprint is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Exam blueprint not found",
        )
    if blueprint.status != "confirmed":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Exam blueprint must be confirmed before generating questions",
        )
    return execute_idempotent(
        session=session,
        response=response,
        operation="exam.questions",
        idempotency_key=idempotency_key,
        request_payload={"blueprint_id": blueprint_id},
        fn=lambda: AsyncTaskService(session).enqueue(
            course_id=blueprint.course_id,
            task_type="exam_questions",
            input_params={"blueprint_id": blueprint.id},
        ),
        response_status=status.HTTP_202_ACCEPTED,
        resource_type="async_task",
        resource_id_field="task_id",
        retry_if_resource_failed=True,
    )


@router.get("/exams/{blueprint_id}/questions", response_model=list[QuestionRead])
def list_exam_questions(blueprint_id: str, session: Session = Depends(get_session)):
    questions = ExamService(session).list_questions(blueprint_id)
    if questions is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Exam blueprint not found"
        )
    return questions


@router.post("/exams/{blueprint_id}/export", response_model=ExamExportResponse)
def export_exam_files(blueprint_id: str, session: Session = Depends(get_session)):
    try:
        response = ExamService(session).export_exam_files(blueprint_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    if response is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Exam blueprint not found"
        )
    return response
