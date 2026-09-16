from pathlib import Path

import pytest

from coursepilot.models_gateway import GatewayMode, ModelGateway
from coursepilot.models_gateway.errors import ModelCapabilityError, ToolCallingForbidden

ROOT = Path(__file__).resolve().parents[3]
PROFILES = ROOT / "resources/model_profiles/default_v1.yaml"
DEEPSEEK = ROOT / "resources/model_profiles/capabilities/deepseek_v4.json"
MINIMAL = ROOT / "resources/model_profiles/capabilities/minimal_openai_compatible.json"


def gateway(capability: Path = DEEPSEEK, *, mode: GatewayMode = GatewayMode.LOCAL):
    return ModelGateway.from_files(
        profile_path=PROFILES,
        capability_path=capability,
        main_config=("openai-compatible", "same-model", "https://example.test/v1"),
        light_config=None,
        mode=mode,
    )


def test_six_profiles_route_to_same_model_without_losing_logical_identity() -> None:
    routes = [gateway().resolve(profile) for profile in gateway().profiles]

    assert len(routes) == 6
    assert {route.model for route in routes} == {"same-model"}
    assert {route.requested_profile for route in routes} == set(gateway().profiles)
    assert {route.tier for route in routes} == {"main", "light"}


def test_unsupported_reasoning_and_thinking_are_omitted() -> None:
    route = gateway(MINIMAL).resolve("generator_main")

    assert "reasoning_effort" not in route.request_parameters
    assert "thinking" not in route.request_parameters
    assert route.capability_decision == (
        "reasoning_omitted_unsupported",
        "thinking_omitted_unsupported",
    )


def test_evaluation_capability_failure_does_not_escalate(tmp_path: Path) -> None:
    capability = tmp_path / "no-structured.json"
    capability.write_text(
        MINIMAL.read_text(encoding="utf-8").replace(
            '"structured_output": true', '"structured_output": false'
        ),
        encoding="utf-8",
    )
    candidate = gateway(capability, mode=GatewayMode.EVALUATION)

    with pytest.raises(ModelCapabilityError):
        candidate.resolve("classifier_light", allow_escalation=True, escalation_reason="required")


def test_tool_calling_is_always_rejected() -> None:
    with pytest.raises(ToolCallingForbidden):
        gateway().resolve("planner_main", tools_requested=True)
