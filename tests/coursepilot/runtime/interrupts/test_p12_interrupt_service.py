def test_recoverable_graph_skeleton_reaches_interrupt() -> None:
    from langgraph.checkpoint.memory import MemorySaver

    from coursepilot.runtime.recoverable_graph import build_recoverable_graph

    graph = build_recoverable_graph("lesson", checkpointer=MemorySaver())
    result = graph.invoke({}, config={"configurable": {"thread_id": "test-p12"}})
    assert result["__interrupt__"][0].value["interrupt_type"] == "lesson_session_plan_review"
