from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from coursepilot.db.session import get_session
from coursepilot.schemas.review_schema import ReviewCreate, ReviewRead, ReviewWriteBackResponse
from coursepilot.services.courserag_runtime import get_courserag_service
from coursepilot.services.review_service import ReviewService

router = APIRouter(tags=["coursepilot-reviews"])


@router.post("/reviews", response_model=ReviewRead)
def create_review(payload: ReviewCreate, session: Session = Depends(get_session)):
    try:
        return ReviewService(session).create_review(payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post("/reviews/{review_id}/write-back", response_model=ReviewWriteBackResponse)
def write_back_review(review_id: str, session: Session = Depends(get_session)):
    try:
        response = ReviewService(
            session,
            courserag=get_courserag_service(session),
        ).write_back(review_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    if response is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Review not found")
    return response
