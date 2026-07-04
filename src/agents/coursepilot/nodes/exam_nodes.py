import re
from collections import Counter

from langchain_core.messages import AIMessage

from agents.coursepilot.states.exam_state import ExamGraphState
from coursepilot.schemas.exam_schema import ExamBlueprintContent, ExamGenerationParams, QuestionGroupPlan
from coursepilot.schemas.kb_schema import KBSearchResult
from coursepilot.schemas.lesson_schema import Reference
from coursepilot.schemas.question_schema import QuestionItem
from coursepilot.validators import QuestionValidator


def chat_response(state: ExamGraphState) -> ExamGraphState:
    return {
        "messages": [
            AIMessage(
                content=(
                    "CoursePilot exam agent is available. "
                    "Use /api/coursepilot/courses/{course_id}/exams/blueprint "
                    "for the product workflow."
                )
            )
        ]
    }


def plan_exam_blueprint(state: ExamGraphState) -> ExamGraphState:
    params = ExamGenerationParams.model_validate(state.get("exam_params", {}))
    contexts = [KBSearchResult.model_validate(item) for item in state.get("retrieved_contexts", [])]
    knowledge_points = _knowledge_points(contexts) or [params.chapter_range]
    difficulty = _dominant_difficulty(params.difficulty_distribution)
    groups: list[QuestionGroupPlan] = []
    for question_type, count in params.question_counts.items():
        if count <= 0:
            continue
        score_each = params.score_per_question[question_type]
        groups.append(
            QuestionGroupPlan(
                question_type=question_type,
                count=count,
                score_each=score_each,
                total_score=count * score_each,
                knowledge_points=knowledge_points[: max(1, min(len(knowledge_points), count))],
                difficulty=difficulty,
            )
        )
    blueprint = ExamBlueprintContent(
        course_name=str(state.get("exam_params", {}).get("course_name", "CoursePilot Course")),
        chapter_range=params.chapter_range,
        generation_type=params.generation_type,
        total_score=sum(group.total_score for group in groups),
        question_groups=groups,
        retrieved_contexts=contexts,
        knowledge_points=knowledge_points,
    )
    return {"exam_blueprint": blueprint.model_dump(mode="json")}


def generate_exam_questions(state: ExamGraphState) -> ExamGraphState:
    blueprint = ExamBlueprintContent.model_validate(state.get("exam_blueprint", {}))
    references = _references(blueprint.retrieved_contexts)
    questions: list[QuestionItem] = []
    for group in blueprint.question_groups:
        for index in range(1, group.count + 1):
            point = group.knowledge_points[(index - 1) % len(group.knowledge_points)] if group.knowledge_points else blueprint.chapter_range
            questions.append(
                _make_question(
                    question_type=group.question_type,
                    index=index,
                    point=point,
                    difficulty=group.difficulty,
                    score=group.score_each,
                    reference=references[len(questions) % len(references)],
                )
            )
    return {"questions": [question.model_dump(mode="json") for question in questions]}


def validate_exam_questions(state: ExamGraphState) -> ExamGraphState:
    blueprint = ExamBlueprintContent.model_validate(state.get("exam_blueprint", {}))
    questions = [QuestionItem.model_validate(item) for item in state.get("questions", [])]
    report = QuestionValidator().validate(blueprint, questions)
    return {"validation_report": report.model_dump(mode="json")}


def repair_exam_questions(state: ExamGraphState) -> ExamGraphState:
    report = dict(state.get("validation_report", {}))
    questions = [QuestionItem.model_validate(item) for item in state.get("questions", [])]
    blueprint = ExamBlueprintContent.model_validate(state.get("exam_blueprint", {}))
    expected = {group.question_type: group.count for group in blueprint.question_groups}
    actual = Counter(question.question_type for question in questions)
    references = _references(blueprint.retrieved_contexts)
    for group in blueprint.question_groups:
        missing = expected[group.question_type] - actual.get(group.question_type, 0)
        for offset in range(max(0, missing)):
            point = group.knowledge_points[offset % len(group.knowledge_points)] if group.knowledge_points else blueprint.chapter_range
            questions.append(
                _make_question(
                    question_type=group.question_type,
                    index=actual.get(group.question_type, 0) + offset + 1,
                    point=point,
                    difficulty=group.difficulty,
                    score=group.score_each,
                    reference=references[len(questions) % len(references)],
                )
            )
    report["repair_attempts"] = int(report.get("repair_attempts", 0)) + 1
    return {
        "questions": [question.model_dump(mode="json") for question in questions],
        "validation_report": report,
    }


def _make_question(
    *,
    question_type: str,
    index: int,
    point: str,
    difficulty: str,
    score: int,
    reference: Reference,
) -> QuestionItem:
    stem = f"Question {index} about {point}"
    if question_type == "single_choice":
        return QuestionItem(
            question_type=question_type,
            knowledge_point=point,
            difficulty=difficulty,
            score=score,
            question_text=f"{stem}: which option best matches this knowledge point?",
            options={"A": f"Core meaning of {point}", "B": "Unrelated concept", "C": "Random guess", "D": "Incorrect statement"},
            correct_answer="A",
            explanation=f"The course context identifies {point} as the assessed knowledge point.",
            references=[reference],
        )
    if question_type == "multiple_choice":
        return QuestionItem(
            question_type=question_type,
            knowledge_point=point,
            difficulty=difficulty,
            score=score,
            question_text=f"{stem}: which statements are related to this knowledge point?",
            options={"A": f"Understand {point}", "B": f"Apply {point}", "C": "Unrelated", "D": "Clearly wrong"},
            correct_answer="A,B",
            explanation=f"A and B cover understanding and application of {point}.",
            references=[reference],
        )
    if question_type == "judgement":
        return QuestionItem(
            question_type=question_type,
            knowledge_point=point,
            difficulty=difficulty,
            score=score,
            question_text=f"{stem}: {point} can be analyzed with examples from the course materials.",
            correct_answer="true",
            explanation=f"The retrieved course context provides material related to {point}.",
            references=[reference],
        )
    return QuestionItem(
        question_type=question_type,
        knowledge_point=point,
        difficulty=difficulty,
        score=score,
        question_text=f"{stem}: briefly explain the concept and give one course-based example.",
        correct_answer=f"A complete answer should define {point}, describe its use, and include one course example.",
        explanation="The answer should cover definition, application scenario, and source-grounded example.",
        references=[reference],
    )


def _knowledge_points(contexts: list[KBSearchResult]) -> list[str]:
    points: list[str] = []
    seen: set[str] = set()
    for context in contexts:
        for token in re.findall(r"[\u4e00-\u9fffA-Za-z][\u4e00-\u9fffA-Za-z0-9_-]{2,20}", context.content):
            if token in seen:
                continue
            seen.add(token)
            points.append(token)
            if len(points) >= 20:
                return points
    return points


def _references(contexts: list[KBSearchResult]) -> list[Reference]:
    return [
        Reference(
            chunk_id=context.chunk_id,
            source_type=context.source_type,
            chapter=context.chapter,
            page=context.page,
        )
        for context in contexts
    ] or [Reference(chunk_id="manual-context")]


def _dominant_difficulty(distribution: dict[str, float]) -> str:
    return max(distribution.items(), key=lambda item: item[1])[0] if distribution else "medium"
