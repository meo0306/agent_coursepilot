from __future__ import annotations

from dataclasses import dataclass

from courserag.contracts.qa import AnswerType


@dataclass(frozen=True)
class AnswerShapeDecision:
    forced_type: AnswerType | None
    rule_id: str
    reason: str


def decide_answer_shape(
    question: str,
    intent_route: str | None = None,
    *,
    generation_reliability: bool = False,
) -> AnswerShapeDecision:
    normalized = " ".join(question.split())
    if any(marker in normalized for marker in ("哪些", "列出", "分别给出", "包括哪些")):
        return AnswerShapeDecision(
            forced_type=AnswerType.LIST,
            rule_id="answer_shape.explicit_list.v1",
            reason="explicit list wording",
        )
    if (
        generation_reliability
        and "哪一项" in normalized
        and any(marker in normalized for marker in ("任务", "工作"))
    ):
        return AnswerShapeDecision(
            forced_type=AnswerType.FACTOID,
            rule_id="answer_shape.explicit_task_factoid.v1",
            reason="explicit single task wording",
        )
    if intent_route == "comparison" or any(
        marker in normalized for marker in ("比较", "区别", "异同", "相比")
    ):
        return AnswerShapeDecision(
            forced_type=AnswerType.COMPARISON,
            rule_id="answer_shape.explicit_comparison.v1",
            reason="explicit comparison wording",
        )
    if intent_route == "procedure" or any(
        marker in normalized for marker in ("步骤", "流程", "如何操作")
    ):
        return AnswerShapeDecision(
            forced_type=AnswerType.PROCEDURE,
            rule_id="answer_shape.explicit_procedure.v1",
            reason="explicit procedure wording",
        )
    if any(marker in normalized for marker in ("是什么概念", "指什么", "哪一个概念")):
        return AnswerShapeDecision(
            forced_type=AnswerType.FACTOID,
            rule_id="answer_shape.explicit_factoid.v1",
            reason="explicit concept wording",
        )
    return AnswerShapeDecision(
        forced_type=None,
        rule_id="answer_shape.provider_bounded_auto.v1",
        reason="no high-confidence shape rule matched",
    )
