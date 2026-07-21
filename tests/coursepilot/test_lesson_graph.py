from agents.coursepilot.graphs.lesson_graph import coursepilot_lesson_agent


def test_lesson_graph_chat_entry():
    result = coursepilot_lesson_agent.invoke({"messages": []})

    assert "messages" in result
    assert "CoursePilot lesson agent is available" in result["messages"][-1].content


def test_lesson_graph_structured_workflow():
    result = coursepilot_lesson_agent.invoke(
        {
            "lesson_params": {
                "course_name": "AI",
                "chapter_range": "Search",
                "total_sessions": 1,
                "session_duration": 45,
            },
            "retrieved_contexts": [
                {
                    "chunk_id": "chunk-1",
                    "course_id": "course-1",
                    "document_id": "doc-1",
                    "source_type": "textbook",
                    "chapter": "Search",
                    "content": "state space search heuristic search",
                    "score": 0.9,
                    "verified": False,
                }
            ],
        }
    )

    assert result["lesson_design"]["total_sessions"] == 1
    assert result["validation_report"]["session_count_valid"] is True
    assert result["validation_report"]["citation_valid"] is True
