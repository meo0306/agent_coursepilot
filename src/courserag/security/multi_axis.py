"""Adapters that expose local semantic classifiers as explicit threat axes."""

from __future__ import annotations

import hashlib

from courserag.security.detector import (
    PromptInjectionDetector,
    SecurityAxisSignal,
    SecurityTextWindow,
    ThreatAxis,
)


class SemanticModelAxis:
    def __init__(
        self,
        detector: PromptInjectionDetector,
        *,
        axis_id: ThreatAxis,
        decision_threshold: float,
    ) -> None:
        if not 0 <= decision_threshold <= 1:
            raise ValueError("axis decision threshold must be in [0, 1]")
        self.detector = detector
        self.axis_id = axis_id
        self.decision_threshold = decision_threshold

    @property
    def detector_id(self) -> str:
        return self.detector.detector_id

    def validate_environment(self) -> None:
        self.detector.validate_environment()

    def detect(self, windows: tuple[SecurityTextWindow, ...]) -> tuple[SecurityAxisSignal, ...]:
        scores = self.detector.score(windows)
        if {score.window_id for score in scores} != {window.window_id for window in windows}:
            raise ValueError("semantic axis scores do not match security windows")
        return tuple(
            SecurityAxisSignal(
                signal_id=_signal_id(
                    score.window_id, self.axis_id, score.detector_id, score.attack_score
                ),
                window_id=score.window_id,
                axis_id=self.axis_id,
                score=score.attack_score,
                detector_id=score.detector_id,
                decision_ready=score.attack_score >= self.decision_threshold,
            )
            for score in scores
        )


def _signal_id(*parts: object) -> str:
    payload = "\x1f".join(str(part) for part in parts).encode("utf-8")
    return f"secsig_{hashlib.sha256(payload).hexdigest()[:24]}"
