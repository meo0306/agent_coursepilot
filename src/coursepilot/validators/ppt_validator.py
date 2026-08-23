"""
PPT 验证器
"""

from coursepilot.schemas.lesson_schema import LessonDesignContent, Reference
from coursepilot.schemas.ppt_schema import (
    SlideItem,
    SlideOutlineContent,
    SlideValidationReport,
)
from coursepilot.validation.service import ValidationContext, ValidatorService

SESSION_BOUND_SLIDE_TYPES = {"objectives", "content", "activity"}


def session_references(lesson: LessonDesignContent) -> dict[int, list[Reference]]:
    return {
        session.session_index: [reference.model_copy(deep=True) for reference in session.references]
        for session in lesson.sessions
    }


def inherit_session_references(
    outline: SlideOutlineContent,
    lesson: LessonDesignContent,
) -> SlideOutlineContent:
    """Fill omitted slide citations from the referenced lesson session."""
    normalized = outline.model_copy(deep=True)
    references_by_session = session_references(lesson)
    for slide in normalized.slides:
        if slide.slide_type == "title" or slide.references:
            continue
        if slide.source_session_index in references_by_session:
            slide.references = [
                reference.model_copy(deep=True)
                for reference in references_by_session[slide.source_session_index]
            ]
    return normalized


class PPTValidator:
    allowed_slide_types = {"title", "objectives", "content", "activity", "summary", "references"}

    def validate_structured(
        self,
        outline: SlideOutlineContent,
        *,
        expected_slide_count: int | None = None,
        artifact_id: str = "ppt",
        artifact_version: int | str = 1,
    ):
        return ValidatorService().validate_typed(
            "ppt",
            outline.model_dump(mode="python"),
            ValidationContext(
                artifact_id=artifact_id,
                artifact_version=artifact_version,
                expected_slide_count=expected_slide_count,
            ),
        )

    def validate(
        self,
        outline: SlideOutlineContent,
        *,
        expected_slide_count: int | None = None,
        total_sessions: int | None = None,
        valid_session_indices: set[int] | None = None,
        valid_chunk_ids: set[str] | None = None,
        session_reference_ids: dict[int, set[str]] | None = None,
    ) -> SlideValidationReport:
        """Validate slide structure, session ownership, and citation provenance."""
        errors: list[str] = []

        slide_count_valid = True
        if expected_slide_count is not None:
            slide_count_valid = len(outline.slides) == expected_slide_count
        else:
            slide_count_valid = len(outline.slides) >= 3
        if not slide_count_valid:
            errors.append("slide_count_valid failed")

        slide_type_valid = all(
            slide.slide_type in self.allowed_slide_types for slide in outline.slides
        )
        if not slide_type_valid:
            errors.append("slide_type_valid failed")

        content_not_empty = all(slide.title and slide.bullet_points for slide in outline.slides)
        if not content_not_empty:
            errors.append("content_not_empty failed")

        source_session_valid = all(
            self._source_session_is_valid(
                slide,
                total_sessions=total_sessions,
                valid_session_indices=valid_session_indices,
            )
            for slide in outline.slides
        )
        if not source_session_valid:
            errors.append("source_session_valid failed")

        non_title_slides = [slide for slide in outline.slides if slide.slide_type != "title"]
        citation_present = all(slide.references for slide in non_title_slides)
        if not citation_present:
            errors.append("citation_present failed")

        citation_grounded = citation_present and self._citations_are_grounded(
            outline,
            valid_chunk_ids=valid_chunk_ids,
            session_reference_ids=session_reference_ids,
        )
        if not citation_grounded:
            errors.append("citation_grounded failed")

        return SlideValidationReport(
            slide_count_valid=slide_count_valid,
            slide_type_valid=slide_type_valid,
            content_not_empty=content_not_empty,
            source_session_valid=source_session_valid,
            citation_present=citation_present,
            citation_grounded=citation_grounded,
            citation_valid=citation_present and citation_grounded,
            errors=errors,
        )

    @staticmethod
    def _source_session_is_valid(
        slide: SlideItem,
        *,
        total_sessions: int | None,
        valid_session_indices: set[int] | None,
    ) -> bool:
        session_index = slide.source_session_index
        if slide.slide_type in SESSION_BOUND_SLIDE_TYPES and session_index is None:
            return False
        if session_index is None:
            return True
        if valid_session_indices is not None and session_index not in valid_session_indices:
            return False
        return total_sessions is None or 1 <= session_index <= total_sessions

    @staticmethod
    def _citations_are_grounded(
        outline: SlideOutlineContent,
        *,
        valid_chunk_ids: set[str] | None,
        session_reference_ids: dict[int, set[str]] | None,
    ) -> bool:
        for slide in outline.slides:
            reference_ids = {reference.chunk_id for reference in slide.references}
            if valid_chunk_ids is not None and not reference_ids.issubset(valid_chunk_ids):
                return False
            if slide.source_session_index is None:
                continue
            if session_reference_ids is None:
                continue
            expected_ids = session_reference_ids.get(slide.source_session_index, set())
            if not reference_ids.intersection(expected_ids):
                return False
        return True
