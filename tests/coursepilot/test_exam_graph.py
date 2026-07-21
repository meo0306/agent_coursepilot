from agents.coursepilot.graphs.exam_graph import coursepilot_exam_agent
from agents.coursepilot.nodes import exam_nodes
from coursepilot.prompts.loader import load_prompt
from coursepilot.schemas.exam_schema import ExamBlueprintLLMOutput, QuestionGroupPlan
from coursepilot.schemas.kb_schema import KBSearchResult


def test_exam_graph_chat_entry():
    result = coursepilot_exam_agent.invoke({"messages": []})

    assert "messages" in result
    assert "CoursePilot exam agent is available" in result["messages"][-1].content


def test_exam_graph_structured_workflow():
    result = coursepilot_exam_agent.invoke(
        {
            "exam_params": {
                "course_name": "AI",
                "chapter_range": "Search",
                "generation_type": "exam",
                "question_counts": {
                    "single_choice": 1,
                    "multiple_choice": 1,
                    "judgement": 1,
                    "short_answer": 1,
                },
                "score_per_question": {
                    "single_choice": 2,
                    "multiple_choice": 3,
                    "judgement": 1,
                    "short_answer": 10,
                },
            },
            "retrieved_contexts": [
                {
                    "chunk_id": "chunk-1",
                    "course_id": "course-1",
                    "document_id": "doc-1",
                    "source_type": "textbook",
                    "chapter": "Search",
                    "content": "state space search heuristic search path cost",
                    "score": 0.9,
                    "verified": False,
                }
            ],
        }
    )

    assert result["exam_blueprint"]["total_score"] == 16
    assert len(result["questions"]) == 4
    assert result["validation_report"]["question_count_valid"] is True
    assert result["validation_report"]["citation_valid"] is True


def test_exam_blueprint_injects_trusted_context_after_llm(monkeypatch):
    context = {
        "chunk_id": "chunk-1",
        "course_id": "course-1",
        "document_id": "doc-1",
        "source_type": "textbook",
        "chapter": "Search",
        "content": "state space search",
        "score": 0.9,
        "verified": False,
    }
    captured = {}

    def fake_generate_structured(*, output_schema, **_kwargs):
        captured["schema"] = output_schema
        return ExamBlueprintLLMOutput(
            course_name="AI",
            chapter_range="Search",
            generation_type="exam",
            total_score=2,
            question_groups=[
                QuestionGroupPlan(
                    question_type="single_choice",
                    count=1,
                    score_each=2,
                    total_score=2,
                    knowledge_points=["state space search"],
                )
            ],
            knowledge_points=["state space search"],
        )

    monkeypatch.setattr(exam_nodes, "generate_structured", fake_generate_structured)

    result = exam_nodes.plan_exam_blueprint(
        {
            "exam_params": {"chapter_range": "Search"},
            "retrieved_contexts": [context],
        }
    )

    assert captured["schema"] is ExamBlueprintLLMOutput
    assert "retrieved_contexts" not in ExamBlueprintLLMOutput.model_json_schema()["properties"]
    assert result["exam_blueprint"]["retrieved_contexts"] == [
        KBSearchResult.model_validate(context).model_dump(mode="json")
    ]
    assert "Do not return retrieved_contexts" in load_prompt("exam/plan_exam_blueprint")
