from courserag.contracts.qa import AnswerType
from courserag.query.answer_shape import decide_answer_shape


def test_high_confidence_rules_force_list_and_factoid_shapes() -> None:
    listing = decide_answer_shape("文中列出了哪些主要步骤？", "procedure")
    assert listing.forced_type == AnswerType.LIST
    assert listing.rule_id == "answer_shape.explicit_list.v1"

    factoid = decide_answer_shape("这个概念指什么？", "definition")
    assert factoid.forced_type == AnswerType.FACTOID
    assert factoid.rule_id == "answer_shape.explicit_factoid.v1"


def test_route_rules_and_bounded_auto_are_distinct() -> None:
    assert decide_answer_shape("比较两种方法", "comparison").forced_type == AnswerType.COMPARISON
    assert decide_answer_shape("请说明实施过程", "procedure").forced_type == AnswerType.PROCEDURE
    decision = decide_answer_shape("说明这一内容", "fact")
    assert decision.forced_type is None
    assert decision.rule_id == "answer_shape.provider_bounded_auto.v1"


def test_explicit_single_task_wording_is_a_high_confidence_factoid() -> None:
    legacy = decide_answer_shape(
        "课程实践要求掌握使用 ERNIE 完成哪一项 fine-tune 任务的全过程？",
        "fact",
    )
    assert legacy.forced_type is None
    decision = decide_answer_shape(
        "课程实践要求掌握使用 ERNIE 完成哪一项 fine-tune 任务的全过程？",
        "fact",
        generation_reliability=True,
    )
    assert decision.forced_type == AnswerType.FACTOID
    assert decision.rule_id == "answer_shape.explicit_task_factoid.v1"
