"""Section-scoped incremental planning for immutable document versions."""

from courserag.incremental.planner import (
    ArtifactKind,
    ChangeKind,
    ImpactAction,
    IncrementalBuildPlan,
    IncrementalProfileChange,
    SectionImpact,
    SectionSnapshot,
    build_incremental_plan,
)

__all__ = [
    "ArtifactKind",
    "ChangeKind",
    "ImpactAction",
    "IncrementalBuildPlan",
    "IncrementalProfileChange",
    "SectionImpact",
    "SectionSnapshot",
    "build_incremental_plan",
]
