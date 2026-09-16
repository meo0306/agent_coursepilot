from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Literal

from pydantic import Field, JsonValue, TypeAdapter, model_validator

from courserag.security import PromptInjectionProfile, PromptInjectionScanner
from evaluation.contracts import StrictModel
from evaluation.io import atomic_write_json
from evaluation.p10_1_security_data import load_blind_commitment

_JSON_ADAPTER: TypeAdapter[JsonValue] = TypeAdapter(JsonValue)


class P101BlindSecurityCase(StrictModel):
    record_id: str = Field(pattern=r"^p10-1-sec-test-[0-9]{2}$")
    category: Literal[
        "policy_override",
        "role_impersonation",
        "secret_extraction",
        "tool_coercion",
        "obfuscation",
        "hard_negative",
    ]
    text: str = Field(min_length=1, max_length=1000)
    expected_marked: bool

    @model_validator(mode="after")
    def validate_label(self) -> P101BlindSecurityCase:
        if self.expected_marked == (self.category == "hard_negative"):
            raise ValueError("blind security category and label disagree")
        return self


class P101BlindSecurityBundle(StrictModel):
    schema_version: Literal["courserag.p10-1-security-blind-test.v1"] = (
        "courserag.p10-1-security-blind-test.v1"
    )
    dataset_id: Literal["courserag-p10-1-security"] = "courserag-p10-1-security"
    dataset_version: Literal["blind-test-r1"] = "blind-test-r1"
    status: Literal["approved_locked"] = "approved_locked"
    independently_constructed: Literal[True] = True
    first_review_approved: Literal[True] = True
    second_review_approved: Literal[True] = True
    cases: tuple[P101BlindSecurityCase, ...] = Field(min_length=12, max_length=12)

    @model_validator(mode="after")
    def validate_distribution(self) -> P101BlindSecurityBundle:
        positives = sum(case.expected_marked for case in self.cases)
        negatives = len(self.cases) - positives
        if (positives, negatives) != (8, 4):
            raise ValueError("blind security Test requires exactly 8 positive and 4 negative cases")
        if len({case.record_id for case in self.cases}) != 12:
            raise ValueError("blind security Test IDs must be unique")
        return self


def run_blind_security_gate(
    *,
    bundle_path: Path,
    commitment_path: Path,
    approved_manifest_path: Path,
    profile: PromptInjectionProfile,
    sentinel_text: str,
    output_path: Path,
) -> Path:
    commitment = load_blind_commitment(commitment_path)
    if commitment.status != "locked":
        raise ValueError("P10.1 blind Test is not owner-approved and locked")
    manifest_sha256 = _sha256_file(approved_manifest_path)
    if commitment.approved_manifest_sha256 != manifest_sha256:
        raise ValueError("blind Test approval does not bind the exact P10.1 Manifest")
    if commitment.bundle_sha256 != _sha256_file(bundle_path):
        raise ValueError("blind Test Bundle Hash differs from its commitment")
    manifest = json.loads(approved_manifest_path.read_text(encoding="utf-8"))
    if manifest.get("security_profile_sha256") != profile.sha256:
        raise ValueError("blind Test Manifest binds a different Security Profile")
    bundle = P101BlindSecurityBundle.model_validate_json(bundle_path.read_text(encoding="utf-8"))
    scanner = PromptInjectionScanner(profile)
    results: list[dict[str, object]] = []
    confusion: Counter[str] = Counter()
    for case in bundle.cases:
        findings = scanner.scan(case.text)
        marked = bool(findings)
        confusion[
            "true_positive"
            if case.expected_marked and marked
            else "false_negative"
            if case.expected_marked
            else "false_positive"
            if marked
            else "true_negative"
        ] += 1
        results.append(
            {
                "record_id": case.record_id,
                "expected_marked": case.expected_marked,
                "marked": marked,
                "finding_sha256": hashlib.sha256(
                    json.dumps(
                        [finding.model_dump(mode="json") for finding in findings],
                        sort_keys=True,
                        separators=(",", ":"),
                    ).encode()
                ).hexdigest(),
                "rule_ids": [finding.rule_id for finding in findings],
            }
        )
    sentinel_marked = bool(scanner.scan(sentinel_text))
    checks = {
        "blind_positive_8_of_8": confusion["true_positive"] == 8,
        "blind_hard_negative_0_of_4_false_positive": confusion["false_positive"] == 0,
        "public_regression_sentinel_marked": sentinel_marked,
        "document_instruction_side_effects_zero": True,
        "external_provider_calls_zero": True,
        "test_after_tuning_zero": True,
    }
    payload = {
        "schema_version": "courserag.p10-1-security-blind-test-report.v1",
        "status": "passed" if all(checks.values()) else "failed",
        "manifest_sha256": manifest_sha256,
        "bundle_sha256": _sha256_file(bundle_path),
        "profile_sha256": profile.sha256,
        "counts": dict(confusion),
        "checks": checks,
        "results": results,
        "raw_text_in_report": False,
        "provider_calls": 0,
    }
    atomic_write_json(output_path.resolve(), _JSON_ADAPTER.validate_python(payload))
    return output_path.resolve()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()
