from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue, model_validator

from courserag.contracts.qa import AnswerType


class GeneratedClaim(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1, max_length=160)
    evidence_ids: tuple[str, ...] = Field(min_length=1)


class GeneratedListItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1, max_length=120)
    evidence_ids: tuple[str, ...] = Field(min_length=1)


class StructuredQAOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["answered", "abstained_insufficient_evidence"]
    answer_type: AnswerType | None = None
    answer: str | None = Field(default=None, max_length=400)
    claims: tuple[GeneratedClaim, ...] = ()
    list_items: tuple[GeneratedListItem, ...] = Field(default=(), max_length=40)

    @model_validator(mode="after")
    def validate_status(self) -> StructuredQAOutput:
        if self.status == "answered":
            answer_type = self.answer_type or AnswerType.EXPLANATORY
            if answer_type == AnswerType.LIST:
                if not self.list_items:
                    raise ValueError("list output requires list_items")
            elif not self.answer or not self.claims:
                raise ValueError("answered output requires answer and claims")
            if answer_type == AnswerType.FACTOID and self.answer and len(self.answer) > 80:
                raise ValueError("factoid answer exceeds 80 characters")
            if answer_type != AnswerType.LIST and self.list_items:
                raise ValueError("only list output may contain list_items")
        if self.status != "answered" and (
            self.claims or self.list_items or (self.answer and len(self.answer) > 80)
        ):
            raise ValueError("abstention cannot contain claims or a long factual answer")
        return self


class ProviderUsage(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    total_tokens: int = Field(default=0, ge=0)


class ProviderQAResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    output: StructuredQAOutput
    provider: str
    model: str
    prompt_version: str
    usage: ProviderUsage = Field(default_factory=ProviderUsage)
    raw_response_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    completion_metadata: dict[str, JsonValue] = Field(default_factory=dict)


class ProviderOutputError(ValueError):
    """Fail-closed structured-output error without retaining raw Provider content."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        metadata: dict[str, JsonValue] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.metadata = metadata or {}


class PlainQAOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    answer: str = Field(min_length=1, max_length=400)


class ProviderPlainQAResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    output: PlainQAOutput
    provider: str
    model: str
    prompt_version: str
    usage: ProviderUsage = Field(default_factory=ProviderUsage)
    raw_response_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class SufficiencyDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    sufficient: bool
    reasons: tuple[str, ...] = ()


class SufficiencyProfile(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    version: str = "candidate_v1"
    rerank_threshold: float = Field(default=0.7502601)
    max_low_confidence_ocr_ratio: float = Field(default=0.25, ge=0, le=1)
    multi_source_intents: tuple[str, ...] = ("comparison", "cross_section")
