import re
from collections import Counter

from langchain_core.messages import AIMessage

from agents.coursepilot.states.exam_state import ExamGraphState
from coursepilot.llm import generate_structured
from coursepilot.schemas.exam_schema import ExamBlueprintContent, ExamGenerationParams, QuestionGroupPlan
from coursepilot.schemas.kb_schema import KBSearchResult
from coursepilot.schemas.lesson_schema import Reference
from coursepilot.schemas.question_schema import QuestionItem, QuestionSet
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
    """根据检索上下文和考试参数生成 ExamBlueprintContent"""
    blueprint = generate_structured(
        prompt_name="exam/plan_exam_blueprint",
        output_schema=ExamBlueprintContent,
        payload={
            "exam_params": state.get("exam_params", {}),
            "retrieved_contexts": state.get("retrieved_contexts", []),
        },
        fallback=lambda: _deterministic_blueprint(state),
    )
    return {"exam_blueprint": blueprint.model_dump(mode="json")}


def _deterministic_blueprint(state: ExamGraphState) -> ExamBlueprintContent:
    """fallback策略：根据传入的 exam_params 和检索上下文拼装成一个确定性的蓝图"""
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
    return blueprint


def generate_exam_questions(state: ExamGraphState) -> ExamGraphState:
    """
    按题型 group 逐组调用 prompt，输出 `QuestionSet`
    """
    blueprint = ExamBlueprintContent.model_validate(state.get("exam_blueprint", {}))
    questions: list[QuestionItem] = []
    for group in blueprint.question_groups:
        result = generate_structured(
            prompt_name=f"exam/generate_{group.question_type}",
            output_schema=QuestionSet,
            payload={
                "blueprint": blueprint.model_dump(mode="json"),
                "question_group": group.model_dump(mode="json"),
                "existing_questions": [question.model_dump(mode="json") for question in questions],
            },
            fallback=lambda group=group: QuestionSet(
                blueprint_id=str(state.get("blueprint_id", "manual-blueprint")),
                questions=_deterministic_questions_for_group(blueprint, group, len(questions)),
            ),
        )
        questions.extend(result.questions[: group.count])
    return {"questions": [question.model_dump(mode="json") for question in questions]}


def validate_exam_questions(state: ExamGraphState) -> ExamGraphState:
    """校验题量、分值、选项、答案、解析、知识覆盖、引用、重复度"""
    blueprint = ExamBlueprintContent.model_validate(state.get("exam_blueprint", {}))
    questions = [QuestionItem.model_validate(item) for item in state.get("questions", [])]
    report = QuestionValidator().validate(blueprint, questions)
    report.repair_attempts = int(state.get("validation_report", {}).get("repair_attempts", 0))
    return {"validation_report": report.model_dump(mode="json")}


def repair_exam_questions(state: ExamGraphState) -> ExamGraphState:
    """使用 repair prompt 补齐缺失题目或修复结构"""
    report = dict(state.get("validation_report", {}))
    blueprint = ExamBlueprintContent.model_validate(state.get("exam_blueprint", {}))
    questions = [QuestionItem.model_validate(item) for item in state.get("questions", [])]
    result = generate_structured(
        prompt_name="repair/regenerate_missing_questions",
        output_schema=QuestionSet,
        payload={
            "blueprint": blueprint.model_dump(mode="json"),
            "questions": [question.model_dump(mode="json") for question in questions],
            "validation_report": report,
        },
        fallback=lambda: QuestionSet(
            blueprint_id=str(state.get("blueprint_id", "manual-blueprint")),
            questions=_repair_missing_questions(blueprint, questions),
        ),
    )
    report["repair_attempts"] = int(report.get("repair_attempts", 0)) + 1
    return {
        "questions": [question.model_dump(mode="json") for question in result.questions],
        "validation_report": report,
    }


def _repair_missing_questions(
    blueprint: ExamBlueprintContent,
    questions: list[QuestionItem],
) -> list[QuestionItem]:
    """修复fallback: 根据蓝图和现有题目生成缺失的题目"""
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
    return questions


def _deterministic_questions_for_group(
    blueprint: ExamBlueprintContent,
    group: QuestionGroupPlan,
    start_index: int = 0,
) -> list[QuestionItem]:
    """问题生成fallback: 根据蓝图和题型组生成确定性的题目"""
    references = _references(blueprint.retrieved_contexts)
    questions: list[QuestionItem] = []
    for index in range(1, group.count + 1):
        point = (
            group.knowledge_points[(index - 1) % len(group.knowledge_points)]
            if group.knowledge_points
            else blueprint.chapter_range
        )
        questions.append(
            _make_question(
                question_type=group.question_type,
                index=index,
                point=point,
                difficulty=group.difficulty,
                score=group.score_each,
                reference=references[(start_index + len(questions)) % len(references)],
            )
        )
    return questions


def _make_question(
    *,
    question_type: str,
    index: int,
    point: str,
    difficulty: str,
    score: int,
    reference: Reference,
) -> QuestionItem:
    """用于fallback的确定性题目生成器，根据题型、知识点、难度和分值按照规则生成一个简单的题目"""
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
    """fallback策略：以正则匹配规则从检索上下文中抽取知识点，最多 20 个"""
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
    """fallback策略：将检索上下文转换为引用列表"""
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
    """fallback策略：根据难度分布确定主导难度"""
    return max(distribution.items(), key=lambda item: item[1])[0] if distribution else "medium"
