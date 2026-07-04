from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from coursepilot.db.session import get_session
from coursepilot.schemas.ppt_schema import (
    PPTExportResponse,
    PPTGenerationParams,
    PPTGenerationResponse,
    SlideOutlineRead,
)
from coursepilot.services.ppt_service import PPTService

router = APIRouter(tags=["coursepilot-ppt"])


@router.post(
    "/lessons/{lesson_id}/ppt/generate",
    response_model=PPTGenerationResponse,
)
def generate_ppt_outline(
    lesson_id: str,
    payload: PPTGenerationParams,
    session: Session = Depends(get_session),
):
    response = PPTService(session).generate_outline(lesson_id, payload)
    if response is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lesson not found")
    return response


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
