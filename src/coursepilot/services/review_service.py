from sqlalchemy.orm import Session

from coursepilot.models import LessonDesign, Question, ReviewRecord, SlideOutline
from coursepilot.rag.vector_store import ChromaVectorStore
from coursepilot.schemas.ppt_schema import SlideOutlineContent
from coursepilot.schemas.review_schema import ReviewCreate, ReviewRead, ReviewWriteBackResponse


class ReviewService:
    def __init__(self, session: Session, vector_store: ChromaVectorStore | None = None):
        self.session = session
        self.vector_store = vector_store or ChromaVectorStore()

    def create_review(self, payload: ReviewCreate) -> ReviewRead:
        course_id = self._resolve_course_id(payload.target_type, payload.target_id)
        if course_id is None:
            raise ValueError(f"Review target not found: {payload.target_type}/{payload.target_id}")

        review = ReviewRecord(
            course_id=course_id,
            target_type=payload.target_type,
            target_id=payload.target_id,
            review_status=payload.review_status,
            comment=payload.comment,
            write_back_status="pending" if payload.review_status == "approved" else "not_written",
        )
        self.session.add(review)
        self._apply_target_status(payload.target_type, payload.target_id, payload.review_status)
        self.session.commit()
        self.session.refresh(review)
        return ReviewRead.model_validate(review)

    def write_back(self, review_id: str) -> ReviewWriteBackResponse | None:
        review = self.session.get(ReviewRecord, review_id)
        if review is None:
            return None
        if review.review_status != "approved":
            review.write_back_status = "skipped"
            self.session.commit()
            return ReviewWriteBackResponse(
                review_id=review.id,
                target_type=review.target_type,
                target_id=review.target_id,
                write_back_status=review.write_back_status,
            )
        if review.target_type != "ppt_outline":
            raise ValueError("Only ppt_outline write-back is supported in Phase 4")

        outline = self.session.get(SlideOutline, review.target_id)
        if outline is None:
            raise ValueError("PPT outline not found")
        content = SlideOutlineContent.model_validate(outline.outline_json)
        texts = []
        ids = []
        metadatas = []
        for slide in content.slides:
            chunk_id = f"review-{review.id}-slide-{slide.slide_index}"
            texts.append(self._slide_text(content, slide.slide_index))
            ids.append(chunk_id)
            metadatas.append(
                {
                    "chunk_id": chunk_id,
                    "document_id": f"review:{review.id}",
                    "source_type": "reviewed_ppt",
                    "chapter": content.chapter,
                    "section": f"slide-{slide.slide_index}",
                    "title": content.slides[slide.slide_index - 1].title,
                    "verified": True,
                }
            )
        self.vector_store.add_verified_texts(
            course_id=review.course_id,
            texts=texts,
            ids=ids,
            metadatas=metadatas,
        )
        review.write_back_status = "written"
        outline.status = "approved"
        self.session.commit()
        return ReviewWriteBackResponse(
            review_id=review.id,
            target_type=review.target_type,
            target_id=review.target_id,
            write_back_status=review.write_back_status,
            written_chunk_ids=ids,
        )

    def _slide_text(self, outline: SlideOutlineContent, slide_index: int) -> str:
        slide = outline.slides[slide_index - 1]
        parts = [outline.course_name, outline.chapter, slide.title, *slide.bullet_points]
        if slide.speaker_notes:
            parts.append(slide.speaker_notes)
        return "\n".join(parts)

    def _resolve_course_id(self, target_type: str, target_id: str) -> str | None:
        if target_type == "ppt_outline":
            target = self.session.get(SlideOutline, target_id)
        elif target_type == "lesson_design":
            target = self.session.get(LessonDesign, target_id)
        elif target_type == "question":
            target = self.session.get(Question, target_id)
        else:
            return None
        return target.course_id if target is not None else None

    def _apply_target_status(self, target_type: str, target_id: str, review_status: str) -> None:
        if target_type == "ppt_outline":
            target = self.session.get(SlideOutline, target_id)
        elif target_type == "lesson_design":
            target = self.session.get(LessonDesign, target_id)
        elif target_type == "question":
            target = self.session.get(Question, target_id)
        else:
            target = None
        if target is not None and hasattr(target, "status"):
            target.status = review_status
