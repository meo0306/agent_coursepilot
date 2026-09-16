"""Review persistence and safe CourseRAG verified-content write-back."""

from sqlalchemy.orm import Session

from coursepilot.models import LessonDesign, Question, ReviewRecord, SlideOutline
from coursepilot.ports.courserag import CourseRAGServicePort
from coursepilot.schemas.review_schema import ReviewCreate, ReviewRead, ReviewWriteBackResponse
from courserag.contracts import RequestContext, VerifiedContentType, VerifiedContentWriteRequest


class ReviewService:
    def __init__(
        self,
        session: Session,
        *,
        courserag: CourseRAGServicePort | None = None,
    ) -> None:
        self.session = session
        self.courserag = courserag

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
            return self._finish(review, "skipped")
        if review.target_type in {"lesson_design", "ppt_outline"}:
            return self._finish(review, "requires_fragment_selection")
        if review.target_type == "question":
            return self._write_question_via_courserag(review)
        raise ValueError(f"Unsupported review target type: {review.target_type}")

    def _write_question_via_courserag(
        self,
        review: ReviewRecord,
    ) -> ReviewWriteBackResponse:
        question = self.session.get(Question, review.target_id)
        if question is None:
            raise ValueError("Question not found")
        evidence_ids = sorted(
            {
                str(reference["evidence_id"])
                for reference in question.references_json
                if isinstance(reference, dict) and reference.get("evidence_id")
            }
        )
        if not evidence_ids or self.courserag is None:
            return self._finish(review, "requires_evidence_migration")
        result = self.courserag.write_verified_content(
            VerifiedContentWriteRequest(
                context=RequestContext(
                    caller="coursepilot-review",
                    idempotency_key=f"review:{review.id}",
                ),
                course_id=review.course_id,
                content_type=VerifiedContentType.VERIFIED_QUESTION,
                content={
                    "question": question.question_text,
                    "options": question.options_json,
                    "answer": question.correct_answer,
                    "explanation": question.explanation,
                    "knowledge_point": question.knowledge_point,
                },
                evidence_ids=evidence_ids,
                approved_by="coursepilot-review",
                task_id=question.exam_blueprint_id,
                approval_record_id=review.id,
            )
        )
        return self._finish(review, "written", item_ids=[result.verified_content_id])

    def _finish(
        self,
        review: ReviewRecord,
        status: str,
        *,
        item_ids: list[str] | None = None,
    ) -> ReviewWriteBackResponse:
        review.write_back_status = status
        self.session.commit()
        return ReviewWriteBackResponse(
            review_id=review.id,
            target_type=review.target_type,
            target_id=review.target_id,
            write_back_status=status,
            written_chunk_ids=item_ids or [],
        )

    def _resolve_course_id(self, target_type: str, target_id: str) -> str | None:
        target: SlideOutline | LessonDesign | Question | None
        if target_type == "ppt_outline":
            target = self.session.get(SlideOutline, target_id)
        elif target_type == "lesson_design":
            target = self.session.get(LessonDesign, target_id)
        elif target_type == "question":
            target = self.session.get(Question, target_id)
        else:
            target = None
        return target.course_id if target is not None else None

    def _apply_target_status(self, target_type: str, target_id: str, status: str) -> None:
        target: SlideOutline | LessonDesign | Question | None
        if target_type == "ppt_outline":
            target = self.session.get(SlideOutline, target_id)
        elif target_type == "lesson_design":
            target = self.session.get(LessonDesign, target_id)
        elif target_type == "question":
            target = self.session.get(Question, target_id)
        else:
            target = None
        if target is not None:
            target.status = status
