"""Offline ONNX Runtime adapter for multilingual prompt-injection classifiers."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from courserag.security.detector import DetectorScore, SecurityTextWindow
from courserag.security.prompt_guard import (
    PromptGuardModelManifest,
    TransformersOffsetTokenizer,
)


class OnnxPromptGuardDetector:
    """Hash-bound ONNX classifier with an explicit, non-fallback execution provider."""

    def __init__(
        self,
        *,
        model_path: str | Path,
        manifest: PromptGuardModelManifest,
        device: str = "cuda",
        model_relative_path: str = "onnx/fp16/model.onnx",
        tokenizer_subfolder: str = "tokenizer",
        max_tokens: int = 512,
        batch_size: int = 16,
        timeout_seconds: float = 300,
    ) -> None:
        self.model_path = Path(model_path).resolve()
        self.manifest = manifest
        self.device = device
        self.model_relative_path = model_relative_path
        self.tokenizer_subfolder = tokenizer_subfolder
        self.max_tokens = max_tokens
        self.batch_size = batch_size
        self.timeout_seconds = timeout_seconds
        self._tokenizer: Any | None = None
        self._session: Any | None = None
        self._numpy: Any | None = None
        self._input_names: frozenset[str] = frozenset()
        self._attack_index: int | None = None
        self._environment_validated = False

    @property
    def detector_id(self) -> str:
        return f"{self.manifest.model_id}@{self.manifest.revision}:onnx-fp16"

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
            raise ValueError("ONNX Prompt Guard device must be cuda or cpu")
        if not 8 <= self.max_tokens <= 512:
            raise ValueError("ONNX Prompt Guard maximum tokens must be within 8..512")
        if self.batch_size < 1:
            raise ValueError("ONNX Prompt Guard batch size must be positive")
        if self.timeout_seconds <= 0:
            raise ValueError("ONNX Prompt Guard timeout must be positive")
        model_file = (self.model_path / self.model_relative_path).resolve()
        if not model_file.is_relative_to(self.model_path) or not model_file.is_file():
            raise ValueError("ONNX Prompt Guard model file is missing or outside the snapshot")
        self.manifest.verify(self.model_path)
        self._load()
        self._environment_validated = True

    def score(self, windows: tuple[SecurityTextWindow, ...]) -> tuple[DetectorScore, ...]:
        self.validate_environment()
        if not windows:
            return ()
        assert self._tokenizer is not None
        assert self._session is not None
        assert self._numpy is not None
        assert self._attack_index is not None
        started = time.monotonic()
        results: list[DetectorScore] = []
        for offset in range(0, len(windows), self.batch_size):
            self._check_timeout(started)
            batch = windows[offset : offset + self.batch_size]
            encoded = self._tokenizer(
                [window.text for window in batch],
                padding=True,
                truncation=True,
                max_length=self.max_tokens,
                return_tensors="np",
            )
            inputs = {
                name: self._numpy.asarray(value, dtype=self._numpy.int64)
                for name, value in encoded.items()
                if name in self._input_names
            }
            missing = self._input_names.difference(inputs)
            if missing:
                raise RuntimeError(
                    f"ONNX Prompt Guard tokenizer omitted model inputs: {sorted(missing)}"
                )
            outputs = self._session.run(None, inputs)
            if not outputs:
                raise RuntimeError("ONNX Prompt Guard returned no outputs")
            logits = self._numpy.asarray(outputs[0], dtype=self._numpy.float32)
            if logits.ndim != 2 or logits.shape[0] != len(batch):
                raise RuntimeError("ONNX Prompt Guard returned an invalid logits shape")
            shifted = logits - logits.max(axis=1, keepdims=True)
            exponentials = self._numpy.exp(shifted)
            probabilities = exponentials / exponentials.sum(axis=1, keepdims=True)
            if self._attack_index >= probabilities.shape[1]:
                raise RuntimeError("ONNX Prompt Guard attack label is outside the logits shape")
            scores = probabilities[:, self._attack_index].tolist()
            results.extend(
                DetectorScore(
                    window_id=window.window_id,
                    attack_score=float(score),
                    detector_id=self.detector_id,
                    model_revision=self.manifest.revision,
                )
                for window, score in zip(batch, scores, strict=True)
            )
        self._check_timeout(started)
        return tuple(results)

    def _check_timeout(self, started: float) -> None:
        if time.monotonic() - started > self.timeout_seconds:
            raise TimeoutError("ONNX Prompt Guard inference exceeded the configured timeout")

    def _load(self) -> None:
        if self._session is not None:
            return
        try:
            import numpy as np
            import onnxruntime as ort
            from transformers import AutoTokenizer
        except ImportError as exc:
            raise RuntimeError(
                "ONNX Prompt Guard dependencies are unavailable; install the locked ONNX extra"
            ) from exc

        if self.device == "cuda":
            try:
                import torch
            except ImportError as exc:
                raise RuntimeError(
                    "CUDA ONNX Prompt Guard requires the locked local PyTorch CUDA runtime"
                ) from exc
            if not torch.cuda.is_available():
                raise RuntimeError(
                    "ONNX Prompt Guard is configured for CUDA but CUDA is unavailable"
                )
            if hasattr(ort, "preload_dlls"):
                ort.preload_dlls()

        providers = tuple(ort.get_available_providers())
        requested_provider = (
            "CUDAExecutionProvider" if self.device == "cuda" else "CPUExecutionProvider"
        )
        if requested_provider not in providers:
            raise RuntimeError(
                f"required ONNX execution provider is unavailable: {requested_provider}; "
                f"available={providers}"
            )
        options = ort.SessionOptions()
        options.log_severity_level = 3
        if self.device == "cuda":
            session_providers = ["CUDAExecutionProvider", "CPUExecutionProvider"]
        else:
            session_providers = ["CPUExecutionProvider"]
        session = ort.InferenceSession(
            str(self.model_path / self.model_relative_path),
            sess_options=options,
            providers=session_providers,
        )
        actual_providers = tuple(session.get_providers())
        if not actual_providers or actual_providers[0] != requested_provider:
            raise RuntimeError(
                f"ONNX Prompt Guard did not activate {requested_provider}: {actual_providers}"
            )
        if self.device == "cuda":
            # ONNX Runtime requires CPU for a few shape/constant graph nodes in this export.
            # Keep CUDA first for model compute, then prohibit whole-session runtime fallback.
            session.disable_fallback()
        tokenizer = AutoTokenizer.from_pretrained(
            self.model_path,
            subfolder=self.tokenizer_subfolder,
            local_files_only=True,
            use_fast=True,
        )
        self._tokenizer = tokenizer
        self._session = session
        self._numpy = np
        self._input_names = frozenset(item.name for item in session.get_inputs())
        if not self._input_names:
            raise RuntimeError("ONNX Prompt Guard model declares no inputs")
        self._attack_index = _load_attack_label_index(self.model_path / "config.json")


def _load_attack_label_index(config_path: Path) -> int:
    try:
        config = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise RuntimeError("ONNX Prompt Guard config.json is missing or invalid") from exc
    labels = config.get("id2label", {})
    if isinstance(labels, dict):
        for index, label in labels.items():
            normalized = str(label).casefold()
            if any(term in normalized for term in ("attack", "injection", "malicious", "unsafe")):
                return int(index)
    if config.get("num_labels", 2) != 2:
        raise RuntimeError("ONNX Prompt Guard has no identifiable binary attack label")
    return 1
