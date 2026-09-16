"""Shared, product-neutral evaluation contracts and runner utilities."""

from evaluation.contracts import (
    ApprovalRecord,
    DatasetSplit,
    FallbackPolicy,
    HashedArtifact,
    HumanReviewMetadata,
    MetricResult,
    ReviewableRecord,
    ReviewStatus,
    RunIntent,
    SourceSpan,
    TestLock,
)

__all__ = [
    "ApprovalRecord",
    "DatasetSplit",
    "FallbackPolicy",
    "HashedArtifact",
    "HumanReviewMetadata",
    "MetricResult",
    "ReviewStatus",
    "ReviewableRecord",
    "RunIntent",
    "SourceSpan",
    "TestLock",
]
