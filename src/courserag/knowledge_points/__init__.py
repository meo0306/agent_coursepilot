"""Offline CourseRAG Knowledge Point asset pipeline."""

from courserag.knowledge_points.normalize import consolidate_candidates
from courserag.knowledge_points.scoring import KnowledgePointScorer, ScoringProfile
from courserag.knowledge_points.windows import SectionSource, SectionWindowBuilder

__all__ = [
    "KnowledgePointScorer",
    "ScoringProfile",
    "SectionSource",
    "SectionWindowBuilder",
    "consolidate_candidates",
]
