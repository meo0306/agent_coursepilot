"""CourseRAG evaluation contracts, adapters, and metrics."""

from courserag.evals.schemas import (
    DS0CorpusDataset,
    DS1ParsingDataset,
    DS2EvidenceDataset,
    DS3KnowledgePointDataset,
    DS4QueryProcessingDataset,
    DS5RetrievalQADataset,
    DS6CitationMigrationDataset,
    DS7IncrementalWritebackDataset,
    DS8PerformanceDataset,
)

__all__ = [
    "DS0CorpusDataset",
    "DS1ParsingDataset",
    "DS2EvidenceDataset",
    "DS3KnowledgePointDataset",
    "DS4QueryProcessingDataset",
    "DS5RetrievalQADataset",
    "DS6CitationMigrationDataset",
    "DS7IncrementalWritebackDataset",
    "DS8PerformanceDataset",
]
