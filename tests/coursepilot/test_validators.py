from coursepilot.schemas.lesson_schema import (
    LessonDesignContent,
    LessonSession,
    Reference,
    SessionPlan,
    TeachingProcessItem,
    TimeAllocation,
)
from coursepilot.schemas.exam_schema import ExamBlueprintContent, QuestionGroupPlan
from coursepilot.schemas.kb_schema import KBSearchResult
from coursepilot.schemas.question_schema import QuestionItem
from coursepilot.schemas.ppt_schema import SlideItem, SlideOutlineContent
from coursepilot.validators import LessonValidator, PPTValidator, QuestionValidator
from coursepilot.validators.duplicate_detector import DuplicateDetector


def test_lesson_validator_passes_valid_design():
    design = LessonDesignContent(
        course_name="AI",
        chapter="Search",
        total_sessions=1,
        session_duration=45,
        knowledge_points=["state space"],
        session_plan=[
            SessionPlan(
                session_index=1,
                session_title="Search",
                duration=45,
                knowledge_points=["state space"],
                teaching_focus="state space",
                difficulty_points=["abstraction"],
                time_allocation=[
                    TimeAllocation(activity="Intro", minutes=5),
                    TimeAllocation(activity="Lecture", minutes=30),
                    TimeAllocation(activity="Practice", minutes=5),
                    TimeAllocation(activity="Summary", minutes=5),
                ],
            )
        ],
        sessions=[
            LessonSession(
                session_index=1,
                session_title="Search",
                teaching_objectives=["Explain state space"],
                key_points=["state space"],
                difficult_points=["abstraction"],
                teaching_process=[
                    TeachingProcessItem(stage="Intro", minutes=5, content="case")
                ],
                references=[Reference(chunk_id="chunk-1")],
            )
        ],
    )

    report = LessonValidator().validate(design, expected_sessions=1, session_duration=45)

    assert report.passed is True


def test_question_validator_passes_valid_question_set():
    context = KBSearchResult(
        chunk_id="chunk-1",
        course_id="course-1",
        document_id="doc-1",
        source_type="textbook",
        content="state space search heuristic",
        score=0.9,
        verified=False,
    )
    blueprint = ExamBlueprintContent(
        course_name="AI",
        chapter_range="Search",
        generation_type="exam",
        total_score=5,
        question_groups=[
            QuestionGroupPlan(
                question_type="single_choice",
                count=1,
                score_each=2,
                total_score=2,
                knowledge_points=["state space"],
                difficulty="medium",
            ),
            QuestionGroupPlan(
                question_type="short_answer",
                count=1,
                score_each=3,
                total_score=3,
                knowledge_points=["heuristic"],
                difficulty="medium",
            ),
        ],
        retrieved_contexts=[context],
        knowledge_points=["state space", "heuristic"],
    )
    questions = [
        QuestionItem(
            question_type="single_choice",
            knowledge_point="state space",
            difficulty="medium",
            score=2,
            question_text="Which option describes state space?",
            options={"A": "State representation", "B": "Noise"},
            correct_answer="A",
            explanation="State space is a representation of search states.",
            references=[Reference(chunk_id="chunk-1")],
        ),
        QuestionItem(
            question_type="short_answer",
            knowledge_point="heuristic",
            difficulty="medium",
            score=3,
            question_text="Explain heuristic search.",
            correct_answer="A heuristic estimates distance to the goal.",
            explanation="The answer should mention estimation and search guidance.",
            references=[Reference(chunk_id="chunk-1")],
        ),
    ]

    report = QuestionValidator().validate(blueprint, questions)

    assert report.passed is True
    assert report.duplicate_rate == 0


def test_duplicate_detector_flags_similar_questions():
    questions = [
        QuestionItem(
            question_type="short_answer",
            knowledge_point="search",
            difficulty="medium",
            score=5,
            question_text="Explain heuristic search and give an example.",
            correct_answer="Use heuristic estimates.",
            explanation="Grounded explanation.",
            references=[Reference(chunk_id="chunk-1")],
        ),
        QuestionItem(
            question_type="short_answer",
            knowledge_point="search",
            difficulty="medium",
            score=5,
            question_text="Explain heuristic search and give an example.",
            correct_answer="Use heuristic estimates.",
            explanation="Grounded explanation.",
            references=[Reference(chunk_id="chunk-1")],
        ),
    ]

    duplicate_rate, pairs = DuplicateDetector(threshold=0.5).detect(questions)

    assert duplicate_rate == 1.0
    assert pairs == [(1, 2)]


def test_ppt_validator_passes_valid_outline():
    outline = SlideOutlineContent(
        course_name="AI",
        chapter="Search",
        lesson_id="lesson-1",
        slides=[
            SlideItem(
                slide_index=1,
                slide_type="title",
                title="AI Search",
                bullet_points=["2 sessions"],
            ),
            SlideItem(
                slide_index=2,
                slide_type="content",
                title="State Space",
                bullet_points=["Define state space"],
                references=[Reference(chunk_id="chunk-1")],
                source_session_index=1,
            ),
            SlideItem(
                slide_index=3,
                slide_type="references",
                title="References",
                bullet_points=["chunk-1"],
                references=[Reference(chunk_id="chunk-1")],
            ),
        ],
    )

    report = PPTValidator().validate(outline, expected_slide_count=3, total_sessions=1)

    assert report.passed is True
