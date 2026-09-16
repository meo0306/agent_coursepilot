from __future__ import annotations

from pathlib import Path

from coursepilot.domain.ppt import SlideContent, SlidePlan
from coursepilot.llm import CoursePilotLLMCallError
from evaluation.p16_provider_completion import (
    _call_provider,
    _CompletionCheckpoint,
    preflight,
)


def test_p16_provider_completion_scope_is_exactly_nine_pages() -> None:
    result = preflight()
    assert result["external_calls_made"] == 0
    assert result["scope_exact"] is True
    assert result["target_count"] == 9
    assert len(set(result["target_slide_ids"])) == 9
    assert result["provider_contract"] == {
        "initial_profile": "content_repair_main",
        "initial_profile_resource": "resources/model_profiles/p16_provider_completion_v1.yaml",
        "initial_timeout_seconds": 120,
        "timeout_retry_profile": "content_repair_main",
        "timeout_retry_profile_resource": (
            "resources/model_profiles/p16_provider_completion_retry_v1.yaml"
        ),
        "timeout_retry_seconds": 360,
        "max_timeout_retries_per_slide": 1,
        "fallback_allowed": False,
        "budget_hard_limit": None,
        "maximum_target_pages": 9,
        "maximum_physical_requests": 18,
    }


def test_p16_provider_completion_retries_only_timeout_with_long_profile(
    monkeypatch, tmp_path: Path
) -> None:
    profiles: list[str] = []
    resources: list[str] = []

    def fake_generate_structured(**kwargs):
        profile_id = kwargs["profile_id"]
        profiles.append(profile_id)
        if len(profiles) == 1:
            raise CoursePilotLLMCallError("timeout", "timed out")
        return SlideContent(slide_id="slide-1", title="Provider repaired")

    monkeypatch.setattr(
        "evaluation.p16_provider_completion.generate_structured",
        fake_generate_structured,
    )
    monkeypatch.setattr(
        "evaluation.p16_provider_completion._activate_profile_resource",
        resources.append,
    )
    candidate, source = _call_provider(
        checkpoint=_CompletionCheckpoint(tmp_path / "checkpoint.json"),
        original=SlideContent(slide_id="slide-1", title="Original"),
        plan=SlidePlan(
            slide_id="slide-1",
            slide_index=1,
            slide_type="concept",
            layout_role="concept",
            title_intent="Concept",
        ),
        decision={"reviewer_notes": "内容不完整"},
        target={"evidence_snapshots": [], "required_claims": []},
    )
    assert candidate.title == "Provider repaired"
    assert source == "provider_completion_timeout_retry"
    assert profiles == ["content_repair_main", "content_repair_main"]
    assert resources == [
        "resources/model_profiles/p16_provider_completion_v1.yaml",
        "resources/model_profiles/p16_provider_completion_retry_v1.yaml",
        "resources/model_profiles/p16_provider_completion_v1.yaml",
    ]


def test_p16_provider_completion_does_not_retry_non_timeout(monkeypatch, tmp_path: Path) -> None:
    calls = 0

    def fake_generate_structured(**kwargs):
        nonlocal calls
        calls += 1
        raise CoursePilotLLMCallError("llm_provider_error", "provider rejected request")

    monkeypatch.setattr(
        "evaluation.p16_provider_completion.generate_structured",
        fake_generate_structured,
    )
    monkeypatch.setattr(
        "evaluation.p16_provider_completion._activate_profile_resource",
        lambda _: None,
    )
    try:
        _call_provider(
            checkpoint=_CompletionCheckpoint(tmp_path / "checkpoint.json"),
            original=SlideContent(slide_id="slide-1", title="Original"),
            plan=SlidePlan(
                slide_id="slide-1",
                slide_index=1,
                slide_type="concept",
                layout_role="concept",
                title_intent="Concept",
            ),
            decision={"reviewer_notes": "内容不完整"},
            target={"evidence_snapshots": [], "required_claims": []},
        )
    except CoursePilotLLMCallError as exc:
        assert exc.category == "llm_provider_error"
    else:
        raise AssertionError("non-timeout provider error must fail closed")
    assert calls == 1
