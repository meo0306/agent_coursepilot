"""Deterministic prompt-injection marking over extracted document text.

Binary upload inspection and semantic instruction marking intentionally stay separate:
the former rejects unsafe files before persistence, while this module annotates text only
after PDF/DOCX parsing or OCR has made it observable and source-locatable.
"""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue, model_validator

from courserag.domain.document import ParsedDocumentIR, ParseWarning


class PromptInjectionRule(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    rule_id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]+$", max_length=120)
    category: Literal[
        "policy_override",
        "role_impersonation",
        "secret_extraction",
        "tool_coercion",
        "obfuscation",
    ]
    pattern: str = Field(min_length=1, max_length=2000)
    view: Literal["normalized", "compact"] = "normalized"
    severity: Literal["warning", "error"] = "warning"


class PromptInjectionProfile(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["courserag.prompt-injection-profile.v2"] = (
        "courserag.prompt-injection-profile.v2"
    )
    name: str = Field(min_length=1, max_length=120)
    version: str = Field(min_length=1, max_length=40)
    enabled: bool = True
    normalize_nfkc: Literal[True] = True
    remove_zero_width: Literal[True] = True
    rules: tuple[PromptInjectionRule, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_unique_rules(self) -> PromptInjectionProfile:
        rule_ids = [rule.rule_id for rule in self.rules]
        if len(set(rule_ids)) != len(rule_ids):
            raise ValueError("prompt-injection rule IDs must be unique")
        for rule in self.rules:
            try:
                re.compile(rule.pattern, re.IGNORECASE)
            except re.error as exc:
                raise ValueError(f"invalid prompt-injection rule {rule.rule_id}") from exc
        return self

    @property
    def sha256(self) -> str:
        payload = json.dumps(
            self.model_dump(mode="json"),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()


class PromptInjectionFinding(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    rule_id: str
    category: str
    severity: Literal["warning", "error"]
    char_start: int = Field(ge=0)
    char_end: int = Field(ge=0)
    matched_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    page_index: int | None = Field(default=None, ge=1)
    block_id: str | None = None
    detector_id: str = "legacy_rules"
    score: float | None = Field(default=None, ge=0, le=1)
    window_id: str | None = None
    decision_basis: Literal[
        "legacy_rule",
        "model_high_score",
        "model_rule_consensus",
        "axis_high_confidence_union",
        "scope_aware_consensus",
    ] = "legacy_rule"
    axis_id: str | None = None
    signal_ids: tuple[str, ...] = ()
    decision_path: tuple[str, ...] = ()


@dataclass(frozen=True)
class _TextView:
    text: str
    original_offsets: tuple[int, ...]


class PromptInjectionScanner:
    def __init__(self, profile: PromptInjectionProfile) -> None:
        self.profile = profile
        self._rules = tuple(
            (rule, re.compile(rule.pattern, re.IGNORECASE)) for rule in profile.rules
        )

    def scan(
        self,
        text: str,
        *,
        page_index: int | None = None,
        block_id: str | None = None,
    ) -> tuple[PromptInjectionFinding, ...]:
        if not self.profile.enabled or not text:
            return ()
        normalized = _normalized_view(text)
        compact = _compact_view(normalized)
        findings: list[PromptInjectionFinding] = []
        seen: set[tuple[str, int, int]] = set()
        for rule, pattern in self._rules:
            view = compact if rule.view == "compact" else normalized
            for match in pattern.finditer(view.text):
                start, end = _original_span(view, match.start(), match.end(), len(text))
                identity = (rule.rule_id, start, end)
                if identity in seen:
                    continue
                seen.add(identity)
                findings.append(
                    PromptInjectionFinding(
                        rule_id=rule.rule_id,
                        category=rule.category,
                        severity=rule.severity,
                        char_start=start,
                        char_end=end,
                        matched_sha256=hashlib.sha256(text[start:end].encode("utf-8")).hexdigest(),
                        page_index=page_index,
                        block_id=block_id,
                    )
                )
        return tuple(
            sorted(findings, key=lambda item: (item.char_start, item.char_end, item.rule_id))
        )


def load_prompt_injection_profile(path: str | Path) -> PromptInjectionProfile:
    profile_path = Path(path)
    if not profile_path.is_file():
        raise ValueError(f"prompt-injection profile is missing: {profile_path}")
    try:
        return PromptInjectionProfile.model_validate_json(profile_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ValueError(f"prompt-injection profile is invalid: {profile_path}") from exc


def mark_untrusted_instructions(
    document: ParsedDocumentIR,
    profile: PromptInjectionProfile,
) -> ParsedDocumentIR:
    """Return an immutable IR copy carrying block-locatable security findings."""

    scanner = PromptInjectionScanner(profile)
    pages = []
    new_warnings = [
        warning for warning in document.warnings if warning.code != "PROMPT_INJECTION_MARKED"
    ]
    finding_count = 0
    for page in document.pages:
        blocks = []
        for block in page.blocks:
            findings = scanner.scan(
                block.text,
                page_index=page.physical_page_index,
                block_id=block.block_id,
            )
            style = dict(block.style)
            style.pop("security_findings", None)
            existing_warnings = style.get("warning_codes", [])
            warning_codes = (
                [str(value) for value in existing_warnings]
                if isinstance(existing_warnings, list)
                else []
            )
            warning_codes = [code for code in warning_codes if code != "PROMPT_INJECTION_MARKED"]
            if findings:
                finding_count += len(findings)
                warning_codes.append("PROMPT_INJECTION_MARKED")
                style["security_findings"] = [
                    finding.model_dump(mode="json") for finding in findings
                ]
                rule_ids: list[JsonValue] = []
                rule_ids.extend(finding.rule_id for finding in findings)
                categories: list[JsonValue] = []
                categories.extend(sorted({finding.category for finding in findings}))
                new_warnings.append(
                    ParseWarning(
                        code="PROMPT_INJECTION_MARKED",
                        severity="warning",
                        message="Untrusted source text contains an instruction-like security marker",
                        page_index=page.physical_page_index,
                        block_id=block.block_id,
                        details={
                            "profile_name": profile.name,
                            "profile_sha256": profile.sha256,
                            "finding_count": len(findings),
                            "rule_ids": rule_ids,
                            "categories": categories,
                        },
                    )
                )
            if warning_codes:
                style_warning_codes: list[JsonValue] = []
                style_warning_codes.extend(sorted(set(warning_codes)))
                style["warning_codes"] = style_warning_codes
            else:
                style.pop("warning_codes", None)
            blocks.append(block.model_copy(update={"style": style}))
        pages.append(page.model_copy(update={"blocks": tuple(blocks)}))
    metadata = dict(document.metadata)
    previous_identity = metadata.get("prompt_injection_profile")
    input_content_sha256 = document.content_sha256
    if isinstance(previous_identity, dict):
        previous_input = previous_identity.get("input_content_sha256")
        if isinstance(previous_input, str) and re.fullmatch(r"[0-9a-f]{64}", previous_input):
            input_content_sha256 = previous_input
    metadata["prompt_injection_profile"] = {
        "name": profile.name,
        "sha256": profile.sha256,
        "finding_count": finding_count,
        "input_content_sha256": input_content_sha256,
    }
    return document.model_copy(
        update={
            "pages": tuple(pages),
            "warnings": tuple(new_warnings),
            "metadata": metadata,
        }
    )


def apply_prompt_injection_findings(
    document: ParsedDocumentIR,
    findings: tuple[PromptInjectionFinding, ...],
    *,
    profile_name: str,
    profile_sha256: str,
    detector_id: str,
) -> ParsedDocumentIR:
    """Project already-located detector findings onto an immutable document IR."""

    by_block: dict[str, list[PromptInjectionFinding]] = {}
    for finding in findings:
        if finding.block_id is None:
            raise ValueError("document security findings must be block-locatable")
        by_block.setdefault(finding.block_id, []).append(finding)

    pages = []
    warnings = [
        warning for warning in document.warnings if warning.code != "PROMPT_INJECTION_MARKED"
    ]
    finding_count = 0
    for page in document.pages:
        blocks = []
        for block in page.blocks:
            block_findings = tuple(
                sorted(
                    by_block.get(block.block_id, ()),
                    key=lambda item: (
                        item.char_start,
                        item.char_end,
                        item.rule_id,
                        item.window_id or "",
                    ),
                )
            )
            style = dict(block.style)
            style.pop("security_findings", None)
            existing = style.get("warning_codes", [])
            warning_codes = [str(value) for value in existing] if isinstance(existing, list) else []
            warning_codes = [code for code in warning_codes if code != "PROMPT_INJECTION_MARKED"]
            if block_findings:
                finding_count += len(block_findings)
                warning_codes.append("PROMPT_INJECTION_MARKED")
                style["security_findings"] = [
                    finding.model_dump(mode="json") for finding in block_findings
                ]
                warnings.append(
                    ParseWarning(
                        code="PROMPT_INJECTION_MARKED",
                        severity="warning",
                        message="Untrusted source text contains a semantic instruction marker",
                        page_index=page.physical_page_index,
                        block_id=block.block_id,
                        details={
                            "profile_name": profile_name,
                            "profile_sha256": profile_sha256,
                            "detector_id": detector_id,
                            "finding_count": len(block_findings),
                            "rule_ids": sorted({item.rule_id for item in block_findings}),
                            "categories": sorted({item.category for item in block_findings}),
                        },
                    )
                )
            if warning_codes:
                style_warning_codes: list[JsonValue] = []
                style_warning_codes.extend(sorted(set(warning_codes)))
                style["warning_codes"] = style_warning_codes
            else:
                style.pop("warning_codes", None)
            blocks.append(block.model_copy(update={"style": style}))
        pages.append(page.model_copy(update={"blocks": tuple(blocks)}))

    metadata = dict(document.metadata)
    metadata["prompt_injection_profile"] = {
        "name": profile_name,
        "sha256": profile_sha256,
        "detector_id": detector_id,
        "finding_count": finding_count,
        "input_content_sha256": _unannotated_content_sha256(document),
    }
    return document.model_copy(
        update={"pages": tuple(pages), "warnings": tuple(warnings), "metadata": metadata}
    )


def _unannotated_content_sha256(document: ParsedDocumentIR) -> str:
    identity = document.metadata.get("prompt_injection_profile")
    if isinstance(identity, dict):
        previous = identity.get("input_content_sha256")
        if isinstance(previous, str) and re.fullmatch(r"[0-9a-f]{64}", previous):
            return previous
    return document.content_sha256


def contains_prompt_injection_text(text: str, profile: PromptInjectionProfile) -> bool:
    return bool(PromptInjectionScanner(profile).scan(text))


def _normalized_view(text: str) -> _TextView:
    characters: list[str] = []
    offsets: list[int] = []
    whitespace_pending = False
    whitespace_offset = 0
    for index, character in enumerate(text):
        if character in {"\u200b", "\u200c", "\u200d", "\ufeff", "\u2060"}:
            continue
        normalized = unicodedata.normalize("NFKC", character).casefold()
        for value in normalized:
            if value.isspace():
                if characters:
                    whitespace_pending = True
                    whitespace_offset = index
                continue
            if whitespace_pending:
                characters.append(" ")
                offsets.append(whitespace_offset)
                whitespace_pending = False
            characters.append(value)
            offsets.append(index)
    return _TextView("".join(characters), tuple(offsets))


def _compact_view(normalized: _TextView) -> _TextView:
    characters: list[str] = []
    offsets: list[int] = []
    for character, offset in zip(normalized.text, normalized.original_offsets, strict=True):
        if character.isalnum() or "\u4e00" <= character <= "\u9fff":
            characters.append(character)
            offsets.append(offset)
    return _TextView("".join(characters), tuple(offsets))


def _original_span(view: _TextView, start: int, end: int, text_length: int) -> tuple[int, int]:
    if not view.original_offsets or start >= len(view.original_offsets):
        return 0, 0
    original_start = view.original_offsets[start]
    original_end = (
        view.original_offsets[min(max(end - 1, start), len(view.original_offsets) - 1)] + 1
    )
    return original_start, min(original_end, text_length)
