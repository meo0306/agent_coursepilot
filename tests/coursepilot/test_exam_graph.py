from agents.coursepilot.graphs.exam_graph import coursepilot_exam_agent


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
