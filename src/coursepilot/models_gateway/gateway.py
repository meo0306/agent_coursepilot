from __future__ import annotations

import hashlib
import json
from pathlib import Path

from coursepilot.models_gateway.errors import (
    ModelCapabilityError,
    ModelConfigurationError,
    ToolCallingForbidden,
)
from coursepilot.models_gateway.models import (
    GatewayMode,
    ModelCapability,
    ModelProfile,
    ResolvedRoute,
)


class ModelGateway:
    """Resolve logical profiles without performing implicit model fallback."""

    def __init__(
        self,
        *,
        profiles: dict[str, ModelProfile],
        capability: ModelCapability,
        main_config: tuple[str, str, str],
        light_config: tuple[str, str, str] | None,
        mode: GatewayMode,
    ) -> None:
        self.profiles = profiles
        self.capability = capability
        self.main_config = main_config
        self.light_config = light_config or main_config
        self.mode = mode

    @classmethod
    def from_files(
        cls,
        *,
        profile_path: Path,
        capability_path: Path,
        main_config: tuple[str, str, str],
        light_config: tuple[str, str, str] | None,
        mode: GatewayMode,
    ) -> ModelGateway:
        payload = json.loads(profile_path.read_text(encoding="utf-8"))
        profiles = {
            item["profile_id"]: ModelProfile.model_validate(item)
            for item in payload.get("profiles", [])
        }
        if len(profiles) != 6:
            raise ModelConfigurationError("Exactly six CoursePilot model profiles are required")
        capability = ModelCapability.model_validate_json(
            capability_path.read_text(encoding="utf-8")
        )
        return cls(
            profiles=profiles,
            capability=capability,
            main_config=main_config,
            light_config=light_config,
            mode=mode,
        )

    @property
    def capability_sha256(self) -> str:
        return hashlib.sha256(
            json.dumps(
                self.capability.model_dump(mode="json"),
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        ).hexdigest()

    def resolve(
        self,
        requested_profile: str,
        *,
        allow_escalation: bool = False,
        escalation_reason: str | None = None,
        tools_requested: bool = False,
    ) -> ResolvedRoute:
        if tools_requested:
            raise ToolCallingForbidden("P11 ModelGateway does not expose tool calling")
        try:
            profile = self.profiles[requested_profile]
        except KeyError as exc:
            raise ModelConfigurationError(f"Unknown model profile: {requested_profile}") from exc
        decisions: list[str] = []
        resolved = profile
        if profile.requires_structured_output and not self.capability.structured_output:
            if not allow_escalation or self.mode is GatewayMode.EVALUATION:
                raise ModelCapabilityError("Structured output capability is required")
            if profile.escalation_target is None or escalation_reason is None:
                raise ModelCapabilityError("Escalation requires a declared target and reason")
            resolved = self.profiles[profile.escalation_target]
            decisions.append("explicit_capability_escalation")
            if resolved.requires_structured_output and not self.capability.structured_output:
                raise ModelCapabilityError("Escalated model still lacks structured output")
        provider, model, base_url = (
            self.main_config if resolved.tier == "main" else self.light_config
        )
        if not provider or not model or not base_url:
            raise ModelConfigurationError("Resolved model configuration is incomplete")
        parameters: dict[str, object] = {
            "temperature": resolved.temperature,
            "max_tokens": resolved.max_output_tokens,
            "timeout": resolved.timeout_seconds,
        }
        if resolved.reasoning_effort is not None:
            if self.capability.reasoning_parameter and self.capability.reasoning_field:
                parameters[self.capability.reasoning_field] = resolved.reasoning_effort
                decisions.append("reasoning_sent")
            else:
                decisions.append("reasoning_omitted_unsupported")
        if resolved.thinking is not None:
            if self.capability.thinking_toggle and self.capability.thinking_field:
                parameters[self.capability.thinking_field] = {"type": resolved.thinking}
                decisions.append("thinking_sent")
            else:
                decisions.append("thinking_omitted_unsupported")
        return ResolvedRoute(
            requested_profile=requested_profile,
            resolved_profile=resolved.profile_id,
            tier=resolved.tier,
            provider=provider,
            model=model,
            base_url=base_url,
            escalation_reason=escalation_reason if resolved is not profile else None,
            capability_decision=tuple(decisions),
            request_parameters=parameters,
        )
