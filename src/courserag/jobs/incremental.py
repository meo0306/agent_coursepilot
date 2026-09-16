from __future__ import annotations

from dataclasses import dataclass

from courserag.jobs.artifacts import FileArtifactStore


class ArtifactReuseError(RuntimeError):
    pass


@dataclass(frozen=True)
class ReusableArtifact:
    artifact_id: str
    uri: str
    sha256: str
    artifact_kind: str


@dataclass(frozen=True)
class ArtifactReuseResult:
    reused: tuple[ReusableArtifact, ...]
    actual_reuse_ratio: float


def verify_artifact_reuse(
    artifacts: tuple[ReusableArtifact, ...],
    *,
    store: FileArtifactStore,
    eligible_count: int,
) -> ArtifactReuseResult:
    if eligible_count < len(artifacts):
        raise ValueError("Eligible Artifact count cannot be below planned reuse")
    for artifact in artifacts:
        if not store.verify(artifact.uri, artifact.sha256):
            raise ArtifactReuseError(
                f"Reusable Artifact failed integrity verification: {artifact.artifact_id}"
            )
    ratio = len(artifacts) / eligible_count if eligible_count else 1.0
    return ArtifactReuseResult(reused=artifacts, actual_reuse_ratio=ratio)
