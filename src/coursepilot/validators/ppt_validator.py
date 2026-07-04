from coursepilot.schemas.ppt_schema import SlideOutlineContent, SlideValidationReport


class PPTValidator:
    allowed_slide_types = {"title", "objectives", "content", "activity", "summary", "references"}

    def validate(
        self,
        outline: SlideOutlineContent,
        *,
        expected_slide_count: int | None = None,
        total_sessions: int | None = None,
    ) -> SlideValidationReport:
        errors: list[str] = []

        slide_count_valid = True
        if expected_slide_count is not None:
            slide_count_valid = len(outline.slides) == expected_slide_count
        else:
            slide_count_valid = len(outline.slides) >= 3
        if not slide_count_valid:
            errors.append("slide_count_valid failed")

        slide_type_valid = all(slide.slide_type in self.allowed_slide_types for slide in outline.slides)
        if not slide_type_valid:
            errors.append("slide_type_valid failed")

        content_not_empty = all(slide.title and slide.bullet_points for slide in outline.slides)
        if not content_not_empty:
            errors.append("content_not_empty failed")

        source_session_valid = True
        if total_sessions is not None:
            source_session_valid = all(
                slide.source_session_index is None or 1 <= slide.source_session_index <= total_sessions
                for slide in outline.slides
            )
        if not source_session_valid:
            errors.append("source_session_valid failed")

        non_title_slides = [slide for slide in outline.slides if slide.slide_type != "title"]
        citation_valid = all(slide.references for slide in non_title_slides)
        if not citation_valid:
            errors.append("citation_valid failed")

        return SlideValidationReport(
            slide_count_valid=slide_count_valid,
            slide_type_valid=slide_type_valid,
            content_not_empty=content_not_empty,
            source_session_valid=source_session_valid,
            citation_valid=citation_valid,
            errors=errors,
        )
