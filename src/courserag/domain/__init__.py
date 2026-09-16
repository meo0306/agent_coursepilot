"""CourseRAG domain layer.

P01 establishes the package boundary. Persistent domain entities are added by
their owning later phases.
"""

from courserag.domain.chunk import ChunkArtifact, ChunkProfile, ChunkRecord
from courserag.domain.document import (
    BlockIR,
    DocxPageAnchor,
    ImageIR,
    LineIR,
    PageIR,
    PageParseDecision,
    ParsedDocumentIR,
    ParsePreview,
    ParseQualityReport,
    ParseWarning,
    RendererManifest,
    SectionIR,
    SourceSpan,
    TableCellRecord,
    TableRecord,
    TextSpanIR,
)
from courserag.domain.evidence import (
    EvidenceArtifact,
    EvidenceRecord,
    EvidenceSourceUnit,
    PageBBox,
    stable_evidence_id,
)

__all__ = [
    "BlockIR",
    "ChunkArtifact",
    "ChunkProfile",
    "ChunkRecord",
    "DocxPageAnchor",
    "EvidenceArtifact",
    "EvidenceRecord",
    "EvidenceSourceUnit",
    "ImageIR",
    "LineIR",
    "PageIR",
    "PageParseDecision",
    "PageBBox",
    "ParsePreview",
    "ParseQualityReport",
    "ParseWarning",
    "ParsedDocumentIR",
    "RendererManifest",
    "SectionIR",
    "SourceSpan",
    "TableCellRecord",
    "TableRecord",
    "TextSpanIR",
    "stable_evidence_id",
]
