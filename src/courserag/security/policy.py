"""Hybrid semantic decision policy with deterministic rule auxiliary signals."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, model_validator

from courserag.domain.document import ParsedDocumentIR
from courserag.security.detector import DetectorScore, SecurityTextWindow
from courserag.security.prompt_injection import (
    PromptInjectionFinding,
    PromptInjectionProfile,
    PromptInjectionScanner,
    apply_prompt_injection_findings,
)


class PromptInjectionDecisionProfile(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str = "courserag.prompt-injection-decision-profile.v3"
    name: str = Field(min_length=1, max_length=160)
    version: str = Field(min_length=1, max_length=80)
    provider: str = "local_prompt_guard"
    model_manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    auxiliary_rules_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    threshold_low: float = Field(ge=0, le=1)
    threshold_high: float = Field(ge=0, le=1)
    high_precision_rule_ids: tuple[str, ...]
    max_tokens: int = Field(default=512, ge=8, le=512)
    content_tokens: int = Field(default=448, ge=1, le=512)
    stride_tokens: int = Field(default=128, ge=1, le=511)

    @model_validator(mode="after")
    def validate_thresholds(self) -> PromptInjectionDecisionProfile:
        if self.threshold_low >= self.threshold_high:
            raise ValueError("Prompt Guard low threshold must be lower than high threshold")
        if self.content_tokens > self.max_tokens:
            raise ValueError("Prompt Guard content tokens exceed model maximum")
        if self.stride_tokens >= self.content_tokens:
            raise ValueError("Prompt Guard stride must be smaller than content window")
        if len(set(self.high_precision_rule_ids)) != len(self.high_precision_rule_ids):
            raise ValueError("high-precision rule IDs must be unique")
        return self

    @property
    def sha256(self) -> str:
        payload = json.dumps(
            self.model_dump(mode="json"), sort_keys=True, separators=(",", ":")
        ).encode()
        return hashlib.sha256(payload).hexdigest()


def load_decision_profile(path: str | Path) -> PromptInjectionDecisionProfile:
    profile_path = Path(path)
    if not profile_path.is_file():
        raise ValueError(f"prompt-injection decision profile is missing: {profile_path}")
    try:
        return PromptInjectionDecisionProfile.model_validate_json(
            profile_path.read_text(encoding="utf-8")
        )
    except (OSError, ValueError) as exc:
        raise ValueError(f"prompt-injection decision profile is invalid: {profile_path}") from exc


class PromptInjectionDecisionPolicy:
    def __init__(
        self,
        profile: PromptInjectionDecisionProfile,
        auxiliary_rules: PromptInjectionProfile,
    ) -> None:
        if auxiliary_rules.sha256 != profile.auxiliary_rules_sha256:
            raise ValueError("auxiliary prompt-injection rules differ from decision profile")
        missing = set(profile.high_precision_rule_ids) - {
            rule.rule_id for rule in auxiliary_rules.rules
        }
        if missing:
            raise ValueError("decision profile references unknown high-precision rules")
        self.profile = profile
        self.rule_scanner = PromptInjectionScanner(auxiliary_rules)

    def decide(
        self,
        document: ParsedDocumentIR,
        windows: tuple[SecurityTextWindow, ...],
        scores: tuple[DetectorScore, ...],
    ) -> tuple[PromptInjectionFinding, ...]:
        score_by_id = {score.window_id: score for score in scores}
        if set(score_by_id) != {window.window_id for window in windows}:
            raise ValueError("Prompt Guard detector scores do not match security windows")
        block_text = {
            block.block_id: block.text for page in document.pages for block in page.blocks
        }
        findings: list[PromptInjectionFinding] = []
        seen: set[tuple[str, int, int, str]] = set()
        high_precision = set(self.profile.high_precision_rule_ids)
        for window in windows:
            score = score_by_id[window.window_id]
            rule_findings = self.rule_scanner.scan(window.text)
            matched_rules = tuple(
                finding for finding in rule_findings if finding.rule_id in high_precision
            )
            basis: str | None = None
            if score.attack_score >= self.profile.threshold_high:
                basis = "model_high_score"
            elif score.attack_score >= self.profile.threshold_low and matched_rules:
                basis = "model_rule_consensus"
            if basis is None:
                continue
            category = matched_rules[0].category if matched_rules else "semantic_prompt_attack"
            for segment in window.segments:
                text = block_text[segment.block_id]
                start = segment.block_char_start
                end = segment.block_char_end
                identity = (segment.block_id, start, end, window.window_id)
                if identity in seen:
                    continue
                seen.add(identity)
                findings.append(
                    PromptInjectionFinding(
                        rule_id=(
                            matched_rules[0].rule_id
                            if basis == "model_rule_consensus"
                            else "prompt_guard_semantic"
                        ),
                        category=category,
                        severity="warning",
                        char_start=start,
                        char_end=end,
                        matched_sha256=hashlib.sha256(text[start:end].encode()).hexdigest(),
                        page_index=segment.page_index,
                        block_id=segment.block_id,
                        detector_id=score.detector_id,
                        score=score.attack_score,
                        window_id=window.window_id,
                        decision_basis=basis,
                    )
                )
        return tuple(
            sorted(
                findings,
                key=lambda item: (
                    item.page_index or 0,
                    item.block_id or "",
                    item.char_start,
                    item.window_id or "",
                ),
            )
        )

    def annotate(
        self,
        document: ParsedDocumentIR,
        windows: tuple[SecurityTextWindow, ...],
        scores: tuple[DetectorScore, ...],
    ) -> ParsedDocumentIR:
        detector_id = scores[0].detector_id if scores else "local_prompt_guard"
        return apply_prompt_injection_findings(
            document,
            self.decide(document, windows, scores),
            profile_name=self.profile.name,
            profile_sha256=self.profile.sha256,
            detector_id=detector_id,
        )
