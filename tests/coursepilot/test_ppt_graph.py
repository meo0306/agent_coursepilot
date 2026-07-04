from agents.coursepilot.graphs.ppt_graph import coursepilot_ppt_agent


def _lesson_design():
    return {
        "course_name": "AI",
        "chapter": "Search",
        "total_sessions": 1,
        "session_duration": 45,
        "knowledge_points": ["state space", "heuristic"],
        "session_plan": [
            {
                "session_index": 1,
                "session_title": "Search",
                "duration": 45,
                "knowledge_points": ["state space", "heuristic"],
                "teaching_focus": "search",
                "time_allocation": [
                    {"activity": "Intro", "minutes": 5},
                    {"activity": "Lecture", "minutes": 30},
                    {"activity": "Practice", "minutes": 5},
                    {"activity": "Summary", "minutes": 5},
                ],
            }
        ],
        "sessions": [
            {
                "session_index": 1,
                "session_title": "Search",
                "teaching_objectives": ["Explain state space", "Apply heuristic"],
                "key_points": ["state space", "heuristic"],
                "teaching_process": [{"stage": "Intro", "minutes": 5, "content": "case"}],
                "references": [{"chunk_id": "chunk-1", "source_type": "textbook"}],
            }
        ],
    }


def test_ppt_graph_chat_entry():
    result = coursepilot_ppt_agent.invoke({"messages": []})

    assert "messages" in result
    assert "CoursePilot PPT agent is available" in result["messages"][-1].content


def test_ppt_graph_structured_workflow():
    result = coursepilot_ppt_agent.invoke(
        {
            "ppt_params": {"lesson_id": "lesson-1", "slide_count": 4},
            "lesson_design": _lesson_design(),
        }
    )

    assert len(result["slide_outline"]["slides"]) == 4
    assert result["validation_report"]["slide_count_valid"] is True
    assert result["validation_report"]["citation_valid"] is True
