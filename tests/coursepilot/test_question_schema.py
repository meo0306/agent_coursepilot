import pytest
from pydantic import ValidationError

from coursepilot.schemas.lesson_schema import Reference
from coursepilot.schemas.question_schema import QuestionItem


def _multiple_choice(answer: str) -> QuestionItem:
    return QuestionItem(
        question_type="multiple_choice",
        knowledge_point="NeRF",
        difficulty="medium",
        score=6,
        question_text="Choose all supported statements.",
        options={"A": "first", "B": "second", "C": "third", "D": "fourth"},
        correct_answer=answer,
        explanation="A and B are supported.",
        references=[Reference(chunk_id="evidence-1")],
    )


@pytest.mark.parametrize("answer", ["AB", "A,B", "A，B", "A B", "A、B"])
def test_multiple_choice_normalizes_supported_provider_answer_forms(answer: str) -> None:
    assert _multiple_choice(answer).correct_answer == "A,B"


def test_multiple_choice_rejects_text_that_is_not_declared_option_keys() -> None:
    with pytest.raises(ValidationError, match="multiple_choice answer must match option keys"):
        _multiple_choice("A and B")


@pytest.mark.parametrize(
    ("answer", "expected"),
    [("A", "正确"), ("B", "错误"), ("true", "true"), ("错", "错误")],
)
def test_judgement_normalizes_supported_provider_answer_forms(answer: str, expected: str) -> None:
    item = QuestionItem(
        question_type="judgement",
        knowledge_point="NeRF",
        difficulty="medium",
        score=5,
        question_text="NeRF is a neural radiance field.",
        options={"A": "正确", "B": "错误"},
        correct_answer=answer,
        explanation="The statement matches the source.",
        references=[Reference(chunk_id="evidence-1")],
    )

    assert item.correct_answer == expected


def test_judgement_rejects_unmapped_option_key() -> None:
    with pytest.raises(
        ValidationError, match="judgement answer must be true/false or Chinese equivalents"
    ):
        QuestionItem(
            question_type="judgement",
            knowledge_point="NeRF",
            difficulty="medium",
            score=5,
            question_text="NeRF is a neural radiance field.",
            options={"A": "supported", "B": "unsupported"},
            correct_answer="A",
            explanation="The statement matches the source.",
            references=[Reference(chunk_id="evidence-1")],
        )
