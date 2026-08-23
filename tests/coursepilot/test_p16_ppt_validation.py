from coursepilot.domain.ppt import PPTArtifact, SlideArchitecture, SlideContent, SlidePlan
from coursepilot.validation.ppt_v2 import validate_ppt_artifact


def _artifact(*, concept_notes: str) -> PPTArtifact:
    plans = [
        SlidePlan(
            slide_id="slide-1",
            slide_index=1,
            slide_type="title",
            layout_role="title",
            title_intent="Title",
            notes_required=False,
            citation_required=False,
        ),
        SlidePlan(
            slide_id="slide-2",
            slide_index=2,
            slide_type="concept",
            layout_role="title_content",
            title_intent="Concept",
            notes_required=True,
            citation_required=False,
        ),
        SlidePlan(
            slide_id="slide-3",
            slide_index=3,
            slide_type="references",
            layout_role="title_content",
            title_intent="References",
            notes_required=False,
            citation_required=False,
        ),
    ]
    architecture = SlideArchitecture(
        course_id="course-1",
        lesson_artifact_id="lesson-1",
        template_id="template-1",
        template_snapshot_id="snapshot-1",
        slide_count=3,
        plans=plans,
    )
    return PPTArtifact(
        course_id="course-1",
        lesson_artifact_id="lesson-1",
        template_id="template-1",
        template_snapshot_id="snapshot-1",
        architecture=architecture,
        slides=[
            SlideContent(slide_id="slide-1", title="Title"),
            SlideContent(slide_id="slide-2", title="Concept", speaker_notes=concept_notes),
            SlideContent(slide_id="slide-3", title="References"),
        ],
    )


def test_p16_notes_validation_follows_architecture_requirement() -> None:
    assert validate_ppt_artifact(_artifact(concept_notes="Required notes")).passed

    report = validate_ppt_artifact(_artifact(concept_notes=""))
    assert not report.passed
    assert [issue.issue_id for issue in report.issues] == ["PPT_NOTES_MISSING:slide-2"]
