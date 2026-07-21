from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    Header,
    HTTPException,
    Response,
    UploadFile,
    status,
)
from sqlalchemy.orm import Session

from coursepilot.api.idempotency import execute_idempotent
from coursepilot.db.session import get_session
from coursepilot.models import Document
from coursepilot.schemas.document_schema import DocumentRead
from coursepilot.schemas.task_schema import AsyncTaskAccepted
from coursepilot.services.async_task_service import AsyncTaskService
from coursepilot.services.document_service import DocumentService

router = APIRouter(tags=["coursepilot-documents"])


@router.get("/courses/{course_id}/documents", response_model=list[DocumentRead])
def list_documents(course_id: str, session: Session = Depends(get_session)):
    return DocumentService(session).list_documents(course_id)


@router.post(
    "/courses/{course_id}/documents/upload",
    response_model=DocumentRead,
    status_code=status.HTTP_201_CREATED,
)
def upload_document(
    course_id: str,
    file: UploadFile = File(...),
    source_type: str = Form("unknown"),
    session: Session = Depends(get_session),
):
    try:
        return DocumentService(session).save_upload(course_id, file, source_type)
    except ValueError as exc:
        message = str(exc)
        status_code = (
            status.HTTP_404_NOT_FOUND
            if "Course not found" in message
            else status.HTTP_400_BAD_REQUEST
        )
        raise HTTPException(status_code=status_code, detail=message) from exc


@router.post(
    "/documents/{document_id}/build-kb",
    response_model=AsyncTaskAccepted,
    status_code=status.HTTP_202_ACCEPTED,
)
def build_document_kb(
    document_id: str,
    response: Response,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    session: Session = Depends(get_session),
):
    document = session.get(Document, document_id)
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")

    return execute_idempotent(
        session=session,
        response=response,
        operation="document.build_kb",
        idempotency_key=idempotency_key,
        request_payload={"document_id": document_id},
        fn=lambda: AsyncTaskService(session).enqueue(
            course_id=document.course_id,
            task_type="build_kb",
            input_params={"document_id": document.id},
        ),
        response_status=status.HTTP_202_ACCEPTED,
        resource_type="async_task",
        resource_id_field="task_id",
        retry_if_resource_failed=True,
    )
