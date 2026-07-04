from collections import Counter

from coursepilot.schemas.exam_schema import ExamBlueprintContent, ExamValidationReport
from coursepilot.schemas.question_schema import QuestionItem
from coursepilot.validators.duplicate_detector import DuplicateDetector


class QuestionValidator:
    def __init__(self, duplicate_threshold: float = 0.85):
        self.duplicate_detector = DuplicateDetector(threshold=duplicate_threshold)

    def validate(
        self,
        blueprint: ExamBlueprintContent,
        questions: list[QuestionItem],
    ) -> ExamValidationReport:
        errors: list[str] = []
        expected_counts = {group.question_type: group.count for group in blueprint.question_groups}
        actual_counts = Counter(question.question_type for question in questions)

        question_count_valid = all(
            actual_counts.get(question_type, 0) == expected_count
            for question_type, expected_count in expected_counts.items()
        )
        if not question_count_valid:
            errors.append("question_count_valid failed")

        expected_score = sum(group.total_score for group in blueprint.question_groups)
        actual_score = sum(question.score for question in questions)
        score_valid = expected_score == actual_score == blueprint.total_score
        if not score_valid:
            errors.append("score_valid failed")

        option_valid = True
        answer_valid = True
        explanation_valid = True
        citation_valid = True
        knowledge_coverage_valid = True
        blueprint_points = set(blueprint.knowledge_points)

        for question in questions:
            if question.question_type in {"single_choice", "multiple_choice"} and not question.options:
                option_valid = False
            if not question.correct_answer:
                answer_valid = False
            if not question.explanation:
                explanation_valid = False
            if not question.references:
                citation_valid = False
            if blueprint_points and question.knowledge_point not in blueprint_points:
                knowledge_coverage_valid = False

        if not option_valid:
            errors.append("option_valid failed")
        if not answer_valid:
            errors.append("answer_valid failed")
        if not explanation_valid:
            errors.append("explanation_valid failed")
        if not citation_valid:
            errors.append("citation_valid failed")
        if not knowledge_coverage_valid:
            errors.append("knowledge_coverage_valid failed")

        duplicate_rate, duplicate_questions = self.duplicate_detector.detect(questions)
        duplicate_valid = duplicate_rate <= self.duplicate_detector.threshold
        if not duplicate_valid:
            errors.append("duplicate_rate exceeds threshold")

        return ExamValidationReport(
            question_count_valid=question_count_valid,
            score_valid=score_valid,
            option_valid=option_valid,
            answer_valid=answer_valid,
            explanation_valid=explanation_valid,
            knowledge_coverage_valid=knowledge_coverage_valid,
            citation_valid=citation_valid,
            duplicate_valid=duplicate_valid,
            duplicate_rate=duplicate_rate,
            duplicate_questions=duplicate_questions,
            errors=errors,
        )
