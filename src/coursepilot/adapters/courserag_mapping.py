from __future__ import annotations

from coursepilot.schemas.kb_schema import KBSearchResult
from courserag.contracts import ScoreBreakdown, SearchHit, SourceTier

LEGACY_DOCUMENT_VERSION = "legacy-unversioned"
LEGACY_INDEX_VERSION = "legacy-active"
LEGACY_RETRIEVAL_CONFIG_VERSION = "legacy-dense-v1"
LEGACY_SEARCH_WARNINGS = [
    "LEGACY_UNVERSIONED_RESULTS",
    "LEGACY_CHUNKS_HAVE_NO_STABLE_EVIDENCE_IDS",
]


def legacy_result_to_search_hit(result: KBSearchResult, *, rank: int) -> SearchHit:
    section_path = [
        value for value in (result.chapter, result.section) if value is not None and value.strip()
    ]
    return SearchHit(
        rank=rank,
        chunk_id=result.chunk_id,
        document_id=result.document_id,
        document_version=LEGACY_DOCUMENT_VERSION,
        document_type=result.source_type,
        title=result.title,
        section_path=section_path,
        page_start=result.page,
        page_end=result.page,
        text=result.content,
        scores=ScoreBreakdown(dense=result.score),
        evidence_ids=[],
        source_tier=(SourceTier.TEACHER_VERIFIED if result.verified else SourceTier.PRIMARY_SOURCE),
    )


def search_hit_to_legacy_result(hit: SearchHit, *, course_id: str) -> KBSearchResult:
    chapter = hit.section_path[0] if hit.section_path else None
    section = hit.section_path[-1] if len(hit.section_path) > 1 else None
    return KBSearchResult(
        chunk_id=hit.chunk_id,
        course_id=course_id,
        document_id=hit.document_id,
        source_type=hit.document_type,
        chapter=chapter,
        section=section,
        page=hit.page_start,
        title=hit.title,
        content=hit.text,
        score=hit.scores.dense or 0.0,
        verified=hit.source_tier == SourceTier.TEACHER_VERIFIED,
    )
