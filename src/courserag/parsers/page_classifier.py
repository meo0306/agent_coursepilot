"""Deterministic, profile-driven page routing for native text and OCR."""

from __future__ import annotations

import unicodedata
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from courserag.domain.document import BBox, PageParseDecision, canonical_json_bytes, sha256_bytes


class PageClassifierProfile(BaseModel):
    """Frozen routing thresholds included in the OCR Stage fingerprint."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(default="p05_balanced_v1", min_length=1, max_length=160)
    min_native_chars: int = Field(default=30, ge=0)
    min_printable_ratio: float = Field(default=0.80, ge=0, le=1)
    max_garbled_ratio: float = Field(default=0.20, ge=0, le=1)
    hybrid_min_image_area_ratio: float = Field(default=0.50, ge=0, le=1)
    hybrid_max_native_text_area_ratio: float = Field(default=0.35, ge=0, le=1)

    @property
    def sha256(self) -> str:
        return sha256_bytes(canonical_json_bytes(self))


class PageClassificationFeatures(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    native_char_count: int = Field(ge=0)
    printable_ratio: float = Field(ge=0, le=1)
    garbled_ratio: float = Field(ge=0, le=1)
    image_area_ratio: float = Field(ge=0, le=1)
    native_text_area_ratio: float = Field(ge=0, le=1)


class PageClassifier:
    def __init__(self, profile: PageClassifierProfile | None = None) -> None:
        self.profile = profile or PageClassifierProfile()

    def classify(
        self,
        features: PageClassificationFeatures,
        *,
        force_ocr: bool = False,
    ) -> PageParseDecision:
        profile = self.profile
        reasons: list[str] = []
        rule: Literal[
            "forced_ocr",
            "empty_native_text",
            "unreliable_native_text",
            "insufficient_native_text",
            "mixed_native_text_and_image",
            "reliable_native_text",
        ]
        mode: Literal["native", "ocr", "hybrid"]
        if force_ocr:
            mode = "ocr"
            rule = "forced_ocr"
            reasons.append("forced_ocr")
        elif features.native_char_count == 0:
            mode = "ocr"
            rule = "empty_native_text"
            reasons.append("empty_native_text")
        elif (
            features.printable_ratio < profile.min_printable_ratio
            or features.garbled_ratio > profile.max_garbled_ratio
        ):
            mode = "ocr"
            rule = "unreliable_native_text"
            if features.printable_ratio < profile.min_printable_ratio:
                reasons.append("low_printable_ratio")
            if features.garbled_ratio > profile.max_garbled_ratio:
                reasons.append("high_garbled_ratio")
        elif (
            features.native_char_count < profile.min_native_chars
            and features.image_area_ratio >= profile.hybrid_min_image_area_ratio
        ):
            mode = "ocr"
            rule = "insufficient_native_text"
            reasons.append("insufficient_native_text")
        elif (
            features.native_char_count < profile.min_native_chars * 4
            and features.image_area_ratio >= profile.hybrid_min_image_area_ratio
            and features.native_text_area_ratio <= profile.hybrid_max_native_text_area_ratio
        ):
            mode = "hybrid"
            rule = "mixed_native_text_and_image"
            reasons.append("mixed_native_text_and_image")
        else:
            mode = "native"
            rule = "reliable_native_text"

        return PageParseDecision(
            mode=mode,
            rule=rule,
            reasons=tuple(reasons),
            profile_name=profile.name,
            profile_sha256=profile.sha256,
            metrics={
                "native_char_count": float(features.native_char_count),
                "printable_ratio": features.printable_ratio,
                "garbled_ratio": features.garbled_ratio,
                "image_area_ratio": features.image_area_ratio,
                "native_text_area_ratio": features.native_text_area_ratio,
                "forced_ocr": float(force_ocr),
            },
        )


def extract_page_features(
    text: str,
    *,
    page_width: float,
    page_height: float,
    image_area: float,
    native_text_bboxes: tuple[BBox, ...],
) -> PageClassificationFeatures:
    non_space = [character for character in text if not character.isspace()]
    native_chars = len(non_space)
    printable_ratio = (
        sum(character.isprintable() for character in non_space) / native_chars
        if native_chars
        else 0.0
    )
    garbled_ratio = (
        sum(_is_garbled_character(character) for character in non_space) / native_chars
        if native_chars
        else 0.0
    )
    page_area = max(1.0, page_width * page_height)
    text_area = sum(_bbox_area(bbox) for bbox in native_text_bboxes)
    return PageClassificationFeatures(
        native_char_count=native_chars,
        printable_ratio=printable_ratio,
        garbled_ratio=garbled_ratio,
        image_area_ratio=min(1.0, max(0.0, image_area / page_area)),
        native_text_area_ratio=min(1.0, max(0.0, text_area / page_area)),
    )


def _bbox_area(bbox: BBox) -> float:
    return max(0.0, bbox[2] - bbox[0]) * max(0.0, bbox[3] - bbox[1])


def _is_garbled_character(character: str) -> bool:
    if character == "\ufffd":
        return True
    category = unicodedata.category(character)
    return category in {"Cc", "Cs", "Co", "Cn"}


class PageClassifierConfig(BaseModel):
    """Validated request-level override without mutating the frozen Profile."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    profile: PageClassifierProfile = Field(default_factory=PageClassifierProfile)
    force_ocr: bool = False

    @model_validator(mode="after")
    def validate_force_ocr(self) -> PageClassifierConfig:
        return self
