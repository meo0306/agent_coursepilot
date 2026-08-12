"""Local, hash-bound Llama Prompt Guard adapter.

The optional heavyweight runtime is imported lazily so the default service and unit-test
environment do not install or download a model implicitly.
"""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from courserag.security.detector import DetectorScore, SecurityTextWindow


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def model_directory_identity(path: str | Path) -> tuple[dict[str, str], str]:
    root = Path(path).resolve()
    if not root.is_dir():
        raise ValueError(f"prompt-guard model directory is missing: {root}")
    files = {
        item.relative_to(root).as_posix(): sha256_file(item)
        for item in sorted(root.rglob("*"))
        if item.is_file()
        and ".cache" not in item.relative_to(root).parts
        and not item.name.endswith((".lock", ".tmp"))
    }
    if not files:
        raise ValueError("prompt-guard model directory is empty")
    payload = json.dumps(files, sort_keys=True, separators=(",", ":")).encode()
    return files, hashlib.sha256(payload).hexdigest()


class PromptGuardModelManifest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str = "courserag.prompt-guard-model-manifest.v1"
    model_id: str = Field(min_length=1, max_length=240)
    revision: str = Field(min_length=1, max_length=240)
    model_bundle_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    files: dict[str, str] = Field(min_length=1)
    license: str = Field(min_length=1, max_length=240)
    license_url: str = Field(min_length=1, max_length=1000)
    license_accepted_by_owner: bool
    runtime_network_required: bool = False

    @model_validator(mode="after")
    def validate_files(self) -> PromptGuardModelManifest:
        if any(not name or name.startswith("/") or ".." in name.split("/") for name in self.files):
            raise ValueError("model manifest paths must be relative and contained")
        if any(len(digest) != 64 for digest in self.files.values()):
            raise ValueError("model manifest file hashes must be SHA-256")
        if not self.license_accepted_by_owner:
            raise ValueError("local Prompt Guard requires explicit owner license acceptance")
        if self.runtime_network_required:
            raise ValueError("Prompt Guard runtime must not require network access")
        return self

    @property
    def sha256(self) -> str:
        payload = json.dumps(
            self.model_dump(mode="json"), sort_keys=True, separators=(",", ":")
        ).encode()
        return hashlib.sha256(payload).hexdigest()

    def verify(self, model_path: str | Path) -> None:
        files, bundle = model_directory_identity(model_path)
        if files != self.files or bundle != self.model_bundle_sha256:
            raise ValueError("local Prompt Guard model files differ from frozen manifest")


def load_prompt_guard_manifest(path: str | Path) -> PromptGuardModelManifest:
    manifest_path = Path(path)
    if not manifest_path.is_file():
        raise ValueError(f"prompt-guard model manifest is missing: {manifest_path}")
    try:
        return PromptGuardModelManifest.model_validate_json(
            manifest_path.read_text(encoding="utf-8")
        )
    except (OSError, ValueError) as exc:
        raise ValueError(f"prompt-guard model manifest is invalid: {manifest_path}") from exc


class TransformersOffsetTokenizer:
    def __init__(self, tokenizer: Any, *, tokenizer_id: str) -> None:
        self._tokenizer = tokenizer
        self._tokenizer_id = tokenizer_id

    @property
    def tokenizer_id(self) -> str:
        return self._tokenizer_id

    def offsets(self, text: str) -> tuple[tuple[int, int], ...]:
        encoded = self._tokenizer(
            text,
            add_special_tokens=False,
            return_offsets_mapping=True,
            truncation=False,
        )
        values = encoded.get("offset_mapping")
        if not isinstance(values, list):
            raise RuntimeError("Prompt Guard tokenizer did not return offset mapping")
        return tuple((int(item[0]), int(item[1])) for item in values)


class LocalPromptGuardDetector:
    def __init__(
        self,
        *,
        model_path: str | Path,
        manifest: PromptGuardModelManifest,
        device: str = "cuda",
        dtype: str = "float32",
        max_tokens: int = 512,
        batch_size: int = 16,
        timeout_seconds: float = 300,
    ) -> None:
        self.model_path = Path(model_path).resolve()
        self.manifest = manifest
        self.device = device
        self.dtype = dtype
        self.max_tokens = max_tokens
        self.batch_size = batch_size
        self.timeout_seconds = timeout_seconds
        self._tokenizer: Any | None = None
        self._model: Any | None = None
        self._torch: Any | None = None
        self._environment_validated = False

    @property
    def detector_id(self) -> str:
        return f"{self.manifest.model_id}@{self.manifest.revision}"

    @property
    def tokenizer(self) -> TransformersOffsetTokenizer:
        self._load()
        assert self._tokenizer is not None
        return TransformersOffsetTokenizer(
            self._tokenizer,
            tokenizer_id=f"{self.detector_id}:{self.manifest.model_bundle_sha256}",
        )

    def validate_environment(self) -> None:
        if self._environment_validated:
            return
        if self.device not in {"cuda", "cpu"}:
            raise ValueError("Prompt Guard device must be cuda or cpu")
        if self.dtype not in {"float32", "float16"}:
            raise ValueError("Prompt Guard dtype must be float32 or float16")
        if not 8 <= self.max_tokens <= 512:
            raise ValueError("Prompt Guard maximum tokens must be within 8..512")
        if self.batch_size < 1:
            raise ValueError("Prompt Guard batch size must be positive")
        self.manifest.verify(self.model_path)
        self._load()
        self._environment_validated = True

    def score(self, windows: tuple[SecurityTextWindow, ...]) -> tuple[DetectorScore, ...]:
        self.validate_environment()
        if not windows:
            return ()
        assert self._tokenizer is not None and self._model is not None and self._torch is not None
        results: list[DetectorScore] = []
        started = time.monotonic()
        for offset in range(0, len(windows), self.batch_size):
            if time.monotonic() - started > self.timeout_seconds:
                raise TimeoutError("Prompt Guard inference exceeded the configured timeout")
            batch = windows[offset : offset + self.batch_size]
            encoded = self._tokenizer(
                [window.text for window in batch],
                padding=True,
                truncation=True,
                max_length=self.max_tokens,
                return_tensors="pt",
            )
            encoded = {name: value.to(self.device) for name, value in encoded.items()}
            with self._torch.inference_mode():
                logits = self._model(**encoded).logits
                probabilities = self._torch.softmax(logits.float(), dim=-1)
            attack_index = _attack_label_index(self._model.config)
            scores = probabilities[:, attack_index].detach().cpu().tolist()
            results.extend(
                DetectorScore(
                    window_id=window.window_id,
                    attack_score=float(score),
                    detector_id=self.detector_id,
                    model_revision=self.manifest.revision,
                )
                for window, score in zip(batch, scores, strict=True)
            )
        if time.monotonic() - started > self.timeout_seconds:
            raise TimeoutError("Prompt Guard inference exceeded the configured timeout")
        return tuple(results)

    def _load(self) -> None:
        if self._model is not None:
            return
        try:
            import torch
            from transformers import AutoModelForSequenceClassification, AutoTokenizer
        except ImportError as exc:
            raise RuntimeError(
                "local Prompt Guard dependencies are unavailable; install the locked optional extra"
            ) from exc
        if self.device == "cuda" and not torch.cuda.is_available():
            raise RuntimeError("Prompt Guard is configured for CUDA but CUDA is unavailable")
        torch_dtype = torch.float16 if self.dtype == "float16" else torch.float32
        tokenizer = AutoTokenizer.from_pretrained(
            self.model_path, local_files_only=True, use_fast=True
        )
        model = AutoModelForSequenceClassification.from_pretrained(
            self.model_path,
            local_files_only=True,
            dtype=torch_dtype,
        )
        model.to(self.device)
        model.eval()
        self._tokenizer = tokenizer
        self._model = model
        self._torch = torch


def _attack_label_index(config: Any) -> int:
    labels = getattr(config, "id2label", {})
    for index, label in labels.items():
        normalized = str(label).casefold()
        if any(term in normalized for term in ("attack", "injection", "malicious", "unsafe")):
            return int(index)
    if int(getattr(config, "num_labels", 2)) != 2:
        raise RuntimeError("Prompt Guard model has no identifiable binary attack label")
    return 1
