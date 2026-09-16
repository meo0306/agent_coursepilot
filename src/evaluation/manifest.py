from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping
from datetime import datetime
from pathlib import Path

from pydantic import Field, JsonValue, model_validator

from evaluation.contracts import (
    DatasetSplit,
    FallbackPolicy,
    HashedArtifact,
    RunIntent,
    Sha256,
    StrictModel,
)
from evaluation.datasets import canonical_json_bytes

_URL_CREDENTIAL = re.compile(r"://[^/\s:@]+:[^/\s@]+@")
_LEGACY_GOLD_KEY = re.compile(
    r"(expected|gold)[_-]?chunk[_-]?(id|ids)$|top[_-]?k[_-]?(as|is)[_-]?gold",
    re.IGNORECASE,
)
_SECRET_KEY_SUFFIXES = (
    "apikey",
    "authtoken",
    "bearertoken",
    "clientsecret",
    "credential",
    "credentials",
    "password",
    "passwd",
    "privatekey",
    "refreshtoken",
    "accesstoken",
)
_EXACT_SECRET_KEYS = frozenset(
    {
        "authorization",
        "cookie",
        "secret",
        "token",
    }
)


class RunDatasetRef(StrictModel):
    dataset_id: str = Field(min_length=1, max_length=160)
    dataset_version: str = Field(min_length=1, max_length=80)
    split: DatasetSplit
    manifest_sha256: Sha256
    split_sha256: Sha256
    test_lock_sha256: Sha256 | None = None


class RunManifest(StrictModel):
    schema_version: str = "course-eval.run-manifest.v1"
    run_id: str = Field(min_length=1, max_length=160)
    created_at: datetime
    dataset: RunDatasetRef
    intent: RunIntent
    tuning_enabled: bool
    git_commit: str = Field(pattern=r"^[0-9a-f]{7,40}$")
    git_dirty: bool
    input_artifacts: list[HashedArtifact] = Field(default_factory=list)
    component_versions: dict[str, str] = Field(default_factory=dict)
    configuration: dict[str, JsonValue] = Field(default_factory=dict)
    fallback_policy: FallbackPolicy
    random_seed: int
    llm_as_judge: bool = False

    @model_validator(mode="after")
    def validate_safe_manifest(self) -> RunManifest:
        if self.llm_as_judge:
            raise ValueError("LLM-as-a-Judge is prohibited")
        _reject_secrets(self.configuration)
        _reject_secrets(self.component_versions)
        _reject_legacy_gold_contract(self.configuration)
        if self.dataset.split is DatasetSplit.TEST:
            if self.tuning_enabled or self.intent is RunIntent.TUNING:
                raise ValueError("automatic tuning is prohibited on the Test split")
            if self.intent not in {RunIntent.EVALUATION, RunIntent.REPLAY}:
                raise ValueError("Test runs require evaluation or replay intent")
            if self.git_dirty:
                raise ValueError("Test runs require a clean Git worktree")
            if self.fallback_policy not in {
                FallbackPolicy.FAIL_SAMPLE,
                FallbackPolicy.FAIL_RUN,
            }:
                raise ValueError("Test runs require a fail-closed fallback policy")
            if self.dataset.test_lock_sha256 is None:
                raise ValueError("Test runs require a test lock hash")
        return self

    def identity_payload(self) -> dict[str, JsonValue]:
        payload = self.model_dump(mode="json")
        payload.pop("run_id")
        payload.pop("created_at")
        return payload

    @property
    def identity_sha256(self) -> str:
        return hashlib.sha256(canonical_json_bytes(self.identity_payload())).hexdigest()


def _reject_secrets(
    value: JsonValue | Mapping[str, str],
    *,
    path: tuple[str, ...] = (),
) -> None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            if _is_secret_key(key):
                location = ".".join((*path, key))
                raise ValueError(f"secret-like key is not allowed in Run Manifest: {location}")
            _reject_secrets(child, path=(*path, key))
        return
    if isinstance(value, list):
        for index, child in enumerate(value):
            _reject_secrets(child, path=(*path, str(index)))
        return
    if isinstance(value, str) and _URL_CREDENTIAL.search(value):
        location = ".".join(path)
        raise ValueError(f"URL credentials are not allowed in Run Manifest: {location}")


def _is_secret_key(key: str) -> bool:
    normalized = re.sub(r"[^a-z0-9]", "", key.casefold())
    return normalized in _EXACT_SECRET_KEYS or normalized.endswith(_SECRET_KEY_SUFFIXES)


def _reject_legacy_gold_contract(
    value: JsonValue,
    *,
    path: tuple[str, ...] = (),
) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if _LEGACY_GOLD_KEY.search(key):
                location = ".".join((*path, key))
                raise ValueError(f"legacy Chunk IDs or Top-K output cannot define Gold: {location}")
            _reject_legacy_gold_contract(child, path=(*path, key))
        return
    if isinstance(value, list):
        for index, child in enumerate(value):
            _reject_legacy_gold_contract(child, path=(*path, str(index)))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()
