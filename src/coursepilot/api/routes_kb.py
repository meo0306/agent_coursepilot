from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from coursepilot.db.session import get_session
from coursepilot.schemas.kb_schema import KBSearchRequest, KBSearchResponse
from coursepilot.services.kb_service import KnowledgeBaseService

router = APIRouter(prefix="/courses/{course_id}/kb", tags=["coursepilot-kb"])


@router.post("/search", response_model=KBSearchResponse)
def search_kb(
    course_id: str,
    payload: KBSearchRequest,
    session: Session = Depends(get_session),
):
    return KBSearchResponse(results=KnowledgeBaseService(session).search(course_id, payload))

