"""Fail-closed high-confidence union for independent security axes."""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from courserag.domain.document import ParsedDocumentIR
from courserag.security.detector import (
    SecurityAxisDetector,
    SecurityAxisSignal,
    SecurityTextWindow,
    ThreatAxis,
)
from courserag.security.prompt_injection import PromptInjectionFinding
from courserag.security.structured_axes import classify_instruction_scope


class SecurityAxisProfile(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    axis_id: ThreatAxis
    detector_id: str = Field(min_length=1, max_length=240)
    required: bool = True
    decision_threshold: float | None = Field(default=None, ge=0, le=1)


class MultiAxisSecurityProfile(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["courserag.multi-axis-security-profile.v1"] = (
        "courserag.multi-axis-security-profile.v1"
    )
    name: str = Field(min_length=1, max_length=160)
    version: str = Field(min_length=1, max_length=80)
    decision: Literal["high_confidence_union", "scope_aware_consensus"] = "high_confidence_union"
    axes: tuple[SecurityAxisProfile, ...] = Field(min_length=1)
    hikma_manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    override_manifest_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    structured_profile_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_axes(self) -> MultiAxisSecurityProfile:
        identities = [(axis.axis_id, axis.detector_id) for axis in self.axes]
        if len(set(identities)) != len(identities):
            raise ValueError("multi-axis Profile contains duplicate detector axes")
        required_axes: set[ThreatAxis] = {
            "general_untrusted_instruction",
            "role_impersonation",
            "secret_extraction",
            "tool_coercion",
            "obfuscation_modifier",
        }
        configured_required_axes = {axis.axis_id for axis in self.axes if axis.required}
        if missing_axes := required_axes - configured_required_axes:
            raise ValueError(
                "multi-axis Profile is missing required architecture axes: "
                + ", ".join(sorted(missing_axes))
            )
        semantic_axes = {
            "general_untrusted_instruction",
            "policy_override",
        }
        if any(
            axis.axis_id in semantic_axes and axis.decision_threshold is None for axis in self.axes
        ):
            raise ValueError("semantic axes require a frozen decision threshold")
        return self

    @property
    def sha256(self) -> str:
        payload = json.dumps(
            self.model_dump(mode="json"), sort_keys=True, separators=(",", ":")
        ).encode()
        return hashlib.sha256(payload).hexdigest()


def load_multi_axis_profile(path: str | Path) -> MultiAxisSecurityProfile:
    profile_path = Path(path)
    if not profile_path.is_file():
        raise ValueError(f"multi-axis security Profile is missing: {profile_path}")
    try:
        return MultiAxisSecurityProfile.model_validate_json(
            profile_path.read_text(encoding="utf-8")
        )
    except (OSError, ValueError) as exc:
        raise ValueError(f"multi-axis security Profile is invalid: {profile_path}") from exc


class MultiAxisSecurityEnsemble:
    def __init__(
        self,
        profile: MultiAxisSecurityProfile,
        detectors: tuple[SecurityAxisDetector, ...],
    ) -> None:
        by_id = {detector.detector_id: detector for detector in detectors}
        if len(by_id) != len(detectors):
            raise ValueError("multi-axis detector IDs must be unique")
        required_ids = {axis.detector_id for axis in profile.axes if axis.required}
        missing = required_ids - set(by_id)
        if missing:
            raise ValueError("required multi-axis detectors are missing")
        self.profile = profile
        ordered_ids = tuple(dict.fromkeys(axis.detector_id for axis in profile.axes))
        self.detectors = tuple(by_id[detector_id] for detector_id in ordered_ids)

    def validate_environment(self) -> None:
        for detector in self.detectors:
            detector.validate_environment()

    def detect(self, windows: tuple[SecurityTextWindow, ...]) -> tuple[SecurityAxisSignal, ...]:
        signals: list[SecurityAxisSignal] = []
        for detector in self.detectors:
            signals.extend(detector.detect(windows))
        known_windows = {window.window_id for window in windows}
        if any(signal.window_id not in known_windows for signal in signals):
            raise ValueError("multi-axis detector returned an unknown window")
        return tuple(
            sorted(
                signals,
                key=lambda item: (item.window_id, item.axis_id, item.detector_id, item.signal_id),
            )
        )

    def decide(
        self,
        document: ParsedDocumentIR,
        windows: tuple[SecurityTextWindow, ...],
        signals: tuple[SecurityAxisSignal, ...],
    ) -> tuple[PromptInjectionFinding, ...]:
        window_by_id = {window.window_id: window for window in windows}
        block_text = {
            block.block_id: block.text for page in document.pages for block in page.blocks
        }
        by_window: dict[str, list[SecurityAxisSignal]] = defaultdict(list)
        for signal in signals:
            by_window[signal.window_id].append(signal)
        findings: list[PromptInjectionFinding] = []
        seen: set[tuple[str, int, int, ThreatAxis]] = set()
        for window_id, window_signals in by_window.items():
            window = window_by_id[window_id]
            scope = classify_instruction_scope(window.text)
            if self.profile.decision == "scope_aware_consensus" and scope in {
                "quoted",
                "negated",
                "educational",
                "defensive_description",
                "approved_procedure",
            }:
                continue
            structured = [
                signal
                for signal in window_signals
                if signal.detector_id == "courserag/structured-capability-axes@v2"
                and set(signal.evidence_ids) >= {"action", "target", "effect"}
                and signal.decision_ready
            ]
            # A semantic score corroborates a structured action-target-effect
            # conjunction; it cannot override scope or act as a standalone
            # authorization decision.
            if self.profile.decision == "scope_aware_consensus" and not structured:
                continue
            ready = (
                structured
                if self.profile.decision == "scope_aware_consensus"
                else [signal for signal in window_signals if signal.decision_ready]
            )
            if not ready:
                continue
            semantic_ready = any(
                signal.axis_id == "general_untrusted_instruction" and signal.decision_ready
                for signal in window_signals
            )
            modifiers = [
                signal.signal_id
                for signal in window_signals
                if signal.axis_id == "obfuscation_modifier"
            ]
            for signal in ready:
                for segment in window.segments:
                    identity = (
                        segment.block_id,
                        segment.block_char_start,
                        segment.block_char_end,
                        signal.axis_id,
                    )
                    if identity in seen:
                        continue
                    seen.add(identity)
                    text = block_text[segment.block_id][
                        segment.block_char_start : segment.block_char_end
                    ]
                    findings.append(
                        PromptInjectionFinding(
                            rule_id=f"axis_{signal.axis_id}",
                            category=(
                                "semantic_prompt_attack"
                                if signal.axis_id == "general_untrusted_instruction"
                                else signal.axis_id
                            ),
                            severity="warning",
                            char_start=segment.block_char_start,
                            char_end=segment.block_char_end,
                            matched_sha256=hashlib.sha256(text.encode()).hexdigest(),
                            page_index=segment.page_index,
                            block_id=segment.block_id,
                            detector_id=signal.detector_id,
                            score=signal.score,
                            window_id=window_id,
                            decision_basis=(
                                "scope_aware_consensus"
                                if self.profile.decision == "scope_aware_consensus"
                                else "axis_high_confidence_union"
                            ),
                            axis_id=signal.axis_id,
                            signal_ids=tuple(sorted({signal.signal_id, *modifiers})),
                            decision_path=(
                                (
                                    "scope_aware_consensus"
                                    if self.profile.decision == "scope_aware_consensus"
                                    else "high_confidence_union"
                                ),
                                scope,
                                "action_target_effect",
                                ("semantic_corroborated" if semantic_ready else "structured_only"),
                            ),
                        )
                    )
        return tuple(
            sorted(
                findings,
                key=lambda item: (
                    item.page_index or 0,
                    item.block_id or "",
                    item.char_start,
                    item.axis_id or "",
                ),
            )
        )


def _classify_scope(text: str) -> str:
    """Conservative scope gate used before any semantic detector decision."""
    import re

    value = " ".join(text.casefold().split())
    if re.search(
        r"\b(quoted|quote|example|excerpt|says|chapter|describes|explains)\b|示例|引用|本章|描述|说明",
        value,
    ):
        return (
            "quoted" if re.search(r"\b(quoted|quote|excerpt|says)\b|引用", value) else "educational"
        )
    if re.search(r"\b(do not|must not|never|not|禁止|不得|不要|不能)\b", value):
        return "negated"
    if re.search(r"\b(defensive|mitigation|protect|防御|防护|缓解)\b", value):
        return "defensive_description"
    if re.search(r"\b(approved procedure|runbook|approved workflow|已批准流程)\b", value):
        return "approved_procedure"
    return "operative"
