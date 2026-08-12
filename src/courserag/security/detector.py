"""Model-independent prompt-injection detector contracts."""

from __future__ import annotations

from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field


class WindowSegment(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    page_index: int | None = Field(default=None, ge=1)
    block_id: str = Field(min_length=1, max_length=160)
    block_char_start: int = Field(ge=0)
    block_char_end: int = Field(ge=0)
    window_char_start: int = Field(ge=0)
    window_char_end: int = Field(ge=0)


class SecurityTextWindow(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    window_id: str = Field(pattern=r"^secwin_[0-9a-f]{24}$")
    text: str = Field(min_length=1)
    token_start: int = Field(ge=0)
    token_end: int = Field(ge=1)
    segments: tuple[WindowSegment, ...] = Field(min_length=1)


class DetectorScore(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    window_id: str
    attack_score: float = Field(ge=0, le=1)
    detector_id: str = Field(min_length=1, max_length=160)
    model_revision: str = Field(min_length=1, max_length=240)


ThreatAxis = Literal[
    "general_untrusted_instruction",
    "policy_override",
    "role_impersonation",
    "secret_extraction",
    "tool_coercion",
    "obfuscation_modifier",
]


class SecurityAxisSignal(BaseModel):
    """One independently attributable security-axis observation."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    signal_id: str = Field(pattern=r"^secsig_[0-9a-f]{24}$")
    window_id: str
    axis_id: ThreatAxis
    score: float = Field(ge=0, le=1)
    detector_id: str = Field(min_length=1, max_length=240)
    evidence_ids: tuple[str, ...] = ()
    decision_ready: bool = False


class PromptInjectionDetector(Protocol):
    @property
    def detector_id(self) -> str: ...

    def validate_environment(self) -> None: ...

    def score(self, windows: tuple[SecurityTextWindow, ...]) -> tuple[DetectorScore, ...]: ...


class SecurityAxisDetector(Protocol):
    @property
    def detector_id(self) -> str: ...

    def validate_environment(self) -> None: ...

    def detect(self, windows: tuple[SecurityTextWindow, ...]) -> tuple[SecurityAxisSignal, ...]: ...


class OffsetTokenizer(Protocol):
    @property
    def tokenizer_id(self) -> str: ...

    def offsets(self, text: str) -> tuple[tuple[int, int], ...]: ...
