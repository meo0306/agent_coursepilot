from courserag.qa.citations import compose_claim_evidence_ids


def test_composer_selects_best_claim_overlap_with_stable_tie_break() -> None:
    evidence = {
        "ev-b": "模型训练需要高质量数据和计算资源。",
        "ev-a": "人工智能模型训练依赖标注数据。",
        "ev-c": "跨境支付需要实时汇率。",
    }

    assert compose_claim_evidence_ids("模型训练依赖高质量数据。", evidence) == ("ev-b",)
    assert compose_claim_evidence_ids("完全无共同词", {"ev-b": "甲乙", "ev-a": "丙丁"}) == ("ev-a",)


def test_composer_returns_empty_without_context_evidence() -> None:
    assert compose_claim_evidence_ids("任意 Claim", {}) == ()
