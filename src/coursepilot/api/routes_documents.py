from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from coursepilot.db.session import get_session
from coursepilot.schemas.document_schema import DocumentBuildResponse, DocumentRead
from coursepilot.services.document_service import DocumentService
from coursepilot.services.kb_service import KnowledgeBaseService

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
        status_code = status.HTTP_404_NOT_FOUND if "Course not found" in message else status.HTTP_400_BAD_REQUEST
        raise HTTPException(status_code=status_code, detail=message) from exc


@router.post("/documents/{document_id}/build-kb", response_model=DocumentBuildResponse)
def build_document_kb(document_id: str, session: Session = Depends(get_session)):
    response = KnowledgeBaseService(session).build_document(document_id)
    if response is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    return response

