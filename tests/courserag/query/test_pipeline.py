from courserag.query import (
    IntentRoute,
    KnowledgePointCandidate,
    QueryPipeline,
    QueryPipelineProfile,
    RetrievalStrategy,
    StepStatus,
    aggregate_query_candidates,
)


class Catalog:
    def list_candidates(self) -> tuple[KnowledgePointCandidate, ...]:
        return (
            KnowledgePointCandidate(
                knowledge_point_id="kp-a",
                name="注意力机制",
                aliases=("Attention",),
                approved=True,
            ),
        )


class Rewriter:
    def rewrite(self, query: str, *, max_rewrites: int) -> tuple[str, ...]:
        return (f"{query} Attention", "丢失关键术语")[:max_rewrites]


def test_pipeline_preserves_filters_terms_and_dual_axis_route() -> None:
    state = QueryPipeline(
        profile=QueryPipelineProfile(multi_query=True),
        knowledge_points=Catalog(),
        rewrite_provider=Rewriter(),
    ).process("  比较 第2章 Attention 与 C++ 的区别，第 10-12 页  ")
    assert state.normalized_query == "比较 第2章 Attention 与 C++ 的区别,第 10-12 页"
    assert state.intent_route == IntentRoute.COMPARISON
    assert state.retrieval_strategy == RetrievalStrategy.METADATA_FILTERED
    assert state.explicit_filters.page_start == 10
    assert state.explicit_filters.page_end == 12
    assert state.linked_knowledge_points[0].hard_filter
    assert state.rewrites == ("比较 第2章 Attention 与 C++ 的区别,第 10-12 页 Attention",)
    assert "C++" in state.required_terms
    assert len(state.traces) == 7


def test_each_step_can_be_disabled_and_retry_runs_once() -> None:
    profile = QueryPipelineProfile(
        normalize=False,
        filter_parser=False,
        kp_link=False,
        alias_expansion=False,
        intent_router=False,
        retrieval_strategy=False,
        multi_query=False,
    )
    pipeline = QueryPipeline(profile=profile)
    state = pipeline.process(" raw  query ")
    assert all(trace.status == StepStatus.SKIPPED_DISABLED for trace in state.traces)
    retried = pipeline.apply_low_recall_retry(state, reason="no_candidates")
    second = pipeline.apply_low_recall_retry(retried, reason="no_candidates")
    assert retried.retry_reason == "no_candidates"
    assert second.retry_reason == "no_candidates"


def test_cross_query_rrf_deduplicates_stably() -> None:
    result = aggregate_query_candidates((("b", "a"), ("a", "c")))
    assert [item[0] for item in result] == ["a", "b", "c"]


def test_specific_intent_rules_precede_generic_how_wording() -> None:
    pipeline = QueryPipeline()
    cases = (
        (
            "教材分别如何说明“特定领域人工智能突破条件”和“深度学习平台推广”？",
            IntentRoute.CROSS_SECTION,
            2,
        ),
        ("根据教材，如何定义或说明“图灵测试”？", IntentRoute.DEFINITION, 1),
        (
            "教材如何说明“服务机器人视觉交互”的应用场景、作用或限制？",
            IntentRoute.EXAMPLE_APPLICATION,
            1,
        ),
        ("高斯粒子在瓦片中按什么过程完成深度排序与渲染？", IntentRoute.PROCEDURE, 1),
        ("支付系统如何利用 AI 识别异常交易？", IntentRoute.FACT, 1),
        (
            "根据教材，“支付合规监控”与“交易异常检测”分别关注什么，二者有何区别？",
            IntentRoute.COMPARISON,
            2,
        ),
    )
    for query, expected, minimum_sources in cases:
        state = pipeline.process(query)
        assert state.intent_route == expected
        assert state.minimum_source_count == minimum_sources
        assert state.intent_rule_id.startswith(f"intent.{expected.value}.")
