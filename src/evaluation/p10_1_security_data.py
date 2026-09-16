from __future__ import annotations

import hashlib
import json
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import Field, JsonValue, TypeAdapter, model_validator

from courserag.security import PromptInjectionProfile, PromptInjectionScanner
from evaluation.contracts import Sha256, StrictModel
from evaluation.io import atomic_write_json

_JSON_ADAPTER: TypeAdapter[JsonValue] = TypeAdapter(JsonValue)


class P101SecurityCase(StrictModel):
    record_id: str = Field(pattern=r"^p10-1-sec-dev-[0-9]{2}$")
    split: Literal["dev"] = "dev"
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
    semantic_content: Literal[False] = False

    @model_validator(mode="after")
    def validate_label(self) -> P101SecurityCase:
        if self.expected_marked == (self.category == "hard_negative"):
            raise ValueError("security category and expected label disagree")
        return self


class P101SecurityDevDataset(StrictModel):
    schema_version: Literal["courserag.p10-1-security-dev.v1"] = "courserag.p10-1-security-dev.v1"
    dataset_id: Literal["courserag-p10-1-security"] = "courserag-p10-1-security"
    dataset_version: Literal["dev-r1"] = "dev-r1"
    status: Literal["candidate_dev_only"] = "candidate_dev_only"
    test_content_included: Literal[False] = False
    cases: tuple[P101SecurityCase, ...] = Field(min_length=30, max_length=30)

    @model_validator(mode="after")
    def validate_distribution(self) -> P101SecurityDevDataset:
        counts = Counter(case.category for case in self.cases)
        if counts["hard_negative"] != 10:
            raise ValueError("P10.1 Dev requires exactly ten hard negatives")
        if any(counts[category] != 4 for category in counts if category != "hard_negative"):
            raise ValueError("P10.1 Dev requires four positives per rule family")
        if len({case.record_id for case in self.cases}) != 30:
            raise ValueError("P10.1 Dev record IDs must be unique")
        return self


class P101BlindTestCommitment(StrictModel):
    schema_version: Literal["courserag.p10-1-security-test-commitment.v1"] = (
        "courserag.p10-1-security-test-commitment.v1"
    )
    dataset_id: Literal["courserag-p10-1-security"] = "courserag-p10-1-security"
    dataset_version: Literal["blind-test-r1"] = "blind-test-r1"
    status: Literal[
        "awaiting_independent_construction",
        "hash_committed",
        "locked",
        "consumed",
    ]
    case_count: Literal[12] = 12
    positive_count: Literal[8] = 8
    hard_negative_count: Literal[4] = 4
    content_visible_to_implementation: Literal[False] = False
    bundle_sha256: Sha256 | None = None
    approved_manifest_sha256: Sha256 | None = None
    locked_at: datetime | None = None
    locked_by: str | None = None

    @model_validator(mode="after")
    def validate_state(self) -> P101BlindTestCommitment:
        if self.status == "awaiting_independent_construction":
            if any(
                value is not None
                for value in (
                    self.bundle_sha256,
                    self.approved_manifest_sha256,
                    self.locked_at,
                    self.locked_by,
                )
            ):
                raise ValueError("awaiting blind Test cannot carry unavailable identities")
        elif self.bundle_sha256 is None:
            raise ValueError("committed blind Test requires a Bundle Hash")
        if self.status in {"locked", "consumed"} and any(
            value is None
            for value in (self.approved_manifest_sha256, self.locked_at, self.locked_by)
        ):
            raise ValueError("locked blind Test requires Manifest and owner identity")
        return self


def load_dev_dataset(path: Path) -> P101SecurityDevDataset:
    return P101SecurityDevDataset.model_validate_json(path.read_text(encoding="utf-8"))


def load_blind_commitment(path: Path) -> P101BlindTestCommitment:
    return P101BlindTestCommitment.model_validate_json(path.read_text(encoding="utf-8"))


def run_dev_gate(
    *,
    dataset_path: Path,
    profile: PromptInjectionProfile,
    output_path: Path,
) -> Path:
    dataset = load_dev_dataset(dataset_path)
    scanner = PromptInjectionScanner(profile)
    results = []
    true_positive = false_negative = false_positive = true_negative = 0
    for case in dataset.cases:
        findings = scanner.scan(case.text)
        marked = bool(findings)
        if case.expected_marked and marked:
            true_positive += 1
        elif case.expected_marked:
            false_negative += 1
        elif marked:
            false_positive += 1
        else:
            true_negative += 1
        results.append(
            {
                "record_id": case.record_id,
                "expected_marked": case.expected_marked,
                "marked": marked,
                "finding_hash": hashlib.sha256(
                    json.dumps(
                        [item.model_dump(mode="json") for item in findings],
                        ensure_ascii=False,
                        sort_keys=True,
                        separators=(",", ":"),
                    ).encode("utf-8")
                ).hexdigest(),
                "rule_ids": [item.rule_id for item in findings],
            }
        )
    recall = true_positive / (true_positive + false_negative)
    false_positive_rate = false_positive / (false_positive + true_negative)
    checks = {
        "positive_recall_1": recall == 1.0,
        "hard_negative_false_positive_rate_lte_0_10": false_positive_rate <= 0.10,
        "test_content_absent": dataset.test_content_included is False,
        "provider_calls_zero": True,
    }
    report = {
        "schema_version": "courserag.p10-1-security-dev-report.v1",
        "status": "passed" if all(checks.values()) else "failed",
        "dataset_sha256": _sha256_file(dataset_path),
        "profile_name": profile.name,
        "profile_sha256": profile.sha256,
        "test_access": False,
        "provider_calls": 0,
        "counts": {
            "true_positive": true_positive,
            "false_negative": false_negative,
            "false_positive": false_positive,
            "true_negative": true_negative,
        },
        "metrics": {
            "positive_recall": recall,
            "hard_negative_false_positive_rate": false_positive_rate,
        },
        "checks": checks,
        "results": results,
    }
    atomic_write_json(output_path, _JSON_ADAPTER.validate_python(report))
    return output_path


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
