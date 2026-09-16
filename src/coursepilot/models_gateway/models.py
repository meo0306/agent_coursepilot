from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class GatewayMode(StrEnum):
    LOCAL = "local"
    PRODUCTION = "production"
    EVALUATION = "evaluation"


class ModelCapability(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    capability_id: str
    json_mode: bool
    structured_output: bool
    reasoning_parameter: bool
    thinking_toggle: bool
    usage_returned: bool
    tool_calling: bool
    reasoning_field: str | None = None
    thinking_field: str | None = None


class ModelProfile(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    profile_id: str
    tier: Literal["main", "light"]
    temperature: float = Field(ge=0, le=2)
    max_output_tokens: int = Field(ge=1)
    timeout_seconds: float = Field(gt=0)
    requires_structured_output: bool = True
    reasoning_effort: Literal["low", "medium", "high"] | None = None
    thinking: Literal["enabled", "disabled"] | None = None
    escalation_target: str | None = None


class ResolvedRoute(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    requested_profile: str
    resolved_profile: str
    tier: Literal["main", "light"]
    provider: str
    model: str
    base_url: str
    escalation_reason: str | None = None
    capability_decision: tuple[str, ...]
    request_parameters: dict[str, object]


class GatewayInvocation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    requested_profile: str
    resolved_profile: str
    provider: str
    model: str
    prompt_name: str
    prompt_sha256: str
    request_sha256: str
    response_sha256: str | None = None
    status: Literal["success", "failed"]
    error_category: str | None = None
    usage_known: bool = False
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    cost: float | None = None
    fallback_used: Literal[False] = False
