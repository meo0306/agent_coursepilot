from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel

from coursepilot.evals.formal_schemas import (
    CPDS0ManifestDataset,
    CPDS1LessonDataset,
    CPDS2ExamDataset,
    CPDS3PPTDataset,
    CPDS4ValidationDataset,
    CPDS5RepairDataset,
    CPDS6RecoveryDataset,
    CPDS7ExportDataset,
    CPDS8FaultSecurityDataset,
    HumanScoreJsonlRecord,
    SYSDS1JourneyDataset,
)
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
    QAHumanReviewRecord,
)
from evaluation.contracts import (
    DatasetSplit,
    ReviewableRecord,
    ReviewLogEntry,
    ReviewStatus,
)


class DatasetValidationError(ValueError):
    """Raised when a dataset layout crosses an evaluation trust boundary."""


@dataclass(frozen=True)
class DatasetSpec:
    directory_name: str
    model: type[BaseModel]


COURSERAG_SPECS = (
    DatasetSpec("ds0", DS0CorpusDataset),
    DatasetSpec("ds1", DS1ParsingDataset),
    DatasetSpec("ds2", DS2EvidenceDataset),
    DatasetSpec("ds3", DS3KnowledgePointDataset),
    DatasetSpec("ds4", DS4QueryProcessingDataset),
    DatasetSpec("ds5", DS5RetrievalQADataset),
    DatasetSpec("ds6", DS6CitationMigrationDataset),
    DatasetSpec("ds7", DS7IncrementalWritebackDataset),
    DatasetSpec("ds8", DS8PerformanceDataset),
)

COURSEPILOT_SPECS = (
    DatasetSpec("cp_ds0", CPDS0ManifestDataset),
    DatasetSpec("cp_ds1", CPDS1LessonDataset),
    DatasetSpec("cp_ds2", CPDS2ExamDataset),
    DatasetSpec("cp_ds3", CPDS3PPTDataset),
    DatasetSpec("cp_ds4", CPDS4ValidationDataset),
    DatasetSpec("cp_ds5", CPDS5RepairDataset),
    DatasetSpec("cp_ds6", CPDS6RecoveryDataset),
    DatasetSpec("cp_ds7", CPDS7ExportDataset),
    DatasetSpec("cp_ds8", CPDS8FaultSecurityDataset),
    DatasetSpec("sys_ds1", SYSDS1JourneyDataset),
)


@dataclass(frozen=True)
class DatasetInventory:
    candidate_records: dict[str, ReviewableRecord]
    approved_records: dict[str, ReviewableRecord]
    split_ids: dict[DatasetSplit, set[str]]


def canonical_json_bytes(payload: object) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def record_digest(record: ReviewableRecord) -> str:
    payload = record.model_dump(mode="json", exclude={"approval"})
    return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()


def load_review_log(path: Path) -> dict[str, ReviewLogEntry]:
    if not path.exists():
        return {}
    entries: dict[str, ReviewLogEntry] = {}
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        stripped = line.strip()
        if not stripped:
            continue
        entry = ReviewLogEntry.model_validate_json(stripped)
        if entry.review_id in entries:
            raise DatasetValidationError(
                f"duplicate review_id {entry.review_id!r} in {path}:{line_number}"
            )
        entries[entry.review_id] = entry
    return entries


def load_qa_human_score_jsonl(path: Path) -> list[QAHumanReviewRecord]:
    records = _load_jsonl_models(path, QAHumanReviewRecord)
    return [record for record in records if isinstance(record, QAHumanReviewRecord)]


def load_coursepilot_human_score_jsonl(path: Path) -> list[HumanScoreJsonlRecord]:
    records = _load_jsonl_models(path, HumanScoreJsonlRecord)
    return [record for record in records if isinstance(record, HumanScoreJsonlRecord)]


def _load_jsonl_models(
    path: Path,
    model: type[BaseModel],
) -> list[BaseModel]:
    if not path.is_file():
        raise DatasetValidationError(f"missing human-score JSONL: {path}")
    records: list[BaseModel] = []
    review_ids: set[str] = set()
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        stripped = line.strip()
        if not stripped:
            continue
        try:
            record = model.model_validate_json(stripped)
        except ValueError as exc:
            raise DatasetValidationError(
                f"invalid human-score JSONL record in {path}:{line_number}"
            ) from exc
        if isinstance(record, QAHumanReviewRecord):
            review_id = record.metadata.review_id
        elif isinstance(record, HumanScoreJsonlRecord):
            review_id = record.root.metadata.review_id
        else:
            raise TypeError(f"unsupported human-score model: {type(record).__name__}")
        if review_id in review_ids:
            raise DatasetValidationError(
                f"duplicate human-score review_id {review_id!r} in {path}:{line_number}"
            )
        review_ids.add(review_id)
        records.append(record)
    if not records:
        raise DatasetValidationError(f"human-score Pilot JSONL is empty: {path}")
    return records


def load_dataset_inventory(root: Path, specs: Iterable[DatasetSpec]) -> DatasetInventory:
    root = root.resolve()
    candidate_records = _load_status_tree(root / "candidates", specs, approved=False)
    approved_records = _load_status_tree(root / "approved", specs, approved=True)
    review_entries = load_review_log(root / "reviews" / "review_log.jsonl")
    _validate_approvals(candidate_records, approved_records, review_entries)
    split_ids = _load_splits(root / "splits")
    _validate_splits(split_ids, candidate_records, approved_records)
    return DatasetInventory(
        candidate_records=candidate_records,
        approved_records=approved_records,
        split_ids=split_ids,
    )


def _load_status_tree(
    root: Path,
    specs: Iterable[DatasetSpec],
    *,
    approved: bool,
) -> dict[str, ReviewableRecord]:
    records: dict[str, ReviewableRecord] = {}
    for spec in specs:
        directory = root / spec.directory_name
        if not directory.is_dir():
            raise DatasetValidationError(f"missing dataset directory: {directory}")
        for path in sorted(directory.glob("*.json")):
            envelope = spec.model.model_validate_json(path.read_text(encoding="utf-8"))
            for record in records_from_envelope(envelope):
                expected_status = ReviewStatus.APPROVED if approved else None
                if approved and record.review_status is not expected_status:
                    raise DatasetValidationError(
                        f"non-approved record {record.record_id!r} found under approved/"
                    )
                if not approved and record.review_status is ReviewStatus.APPROVED:
                    raise DatasetValidationError(
                        f"approved record {record.record_id!r} found under candidates/"
                    )
                if record.record_id in records:
                    raise DatasetValidationError(
                        f"duplicate record_id {record.record_id!r} under {root}"
                    )
                records[record.record_id] = record
    return records


def records_from_envelope(envelope: BaseModel) -> list[ReviewableRecord]:
    if isinstance(envelope, DS0CorpusDataset):
        return list(envelope.documents)
    if isinstance(envelope, DS1ParsingDataset):
        return list(envelope.records)
    if isinstance(envelope, DS2EvidenceDataset):
        return list(envelope.evidence)
    if isinstance(envelope, DS3KnowledgePointDataset):
        return list(envelope.knowledge_points)
    if isinstance(envelope, DS4QueryProcessingDataset):
        return list(envelope.cases)
    if isinstance(envelope, DS5RetrievalQADataset):
        return list(envelope.cases)
    if isinstance(envelope, DS6CitationMigrationDataset):
        return list(envelope.cases)
    if isinstance(envelope, DS7IncrementalWritebackDataset):
        return list(envelope.cases)
    if isinstance(envelope, DS8PerformanceDataset):
        return list(envelope.cases)
    if isinstance(envelope, CPDS0ManifestDataset):
        return list(envelope.records)
    if isinstance(envelope, CPDS1LessonDataset):
        return list(envelope.cases)
    if isinstance(envelope, CPDS2ExamDataset):
        return list(envelope.cases)
    if isinstance(envelope, CPDS3PPTDataset):
        return list(envelope.cases)
    if isinstance(envelope, CPDS4ValidationDataset):
        return list(envelope.cases)
    if isinstance(envelope, CPDS5RepairDataset):
        return list(envelope.cases)
    if isinstance(envelope, CPDS6RecoveryDataset):
        return list(envelope.cases)
    if isinstance(envelope, CPDS7ExportDataset):
        return list(envelope.cases)
    if isinstance(envelope, CPDS8FaultSecurityDataset):
        return list(envelope.cases)
    if isinstance(envelope, SYSDS1JourneyDataset):
        return list(envelope.cases)
    raise TypeError(f"unsupported dataset envelope: {type(envelope).__name__}")


def _validate_approvals(
    candidates: dict[str, ReviewableRecord],
    approved: dict[str, ReviewableRecord],
    reviews: dict[str, ReviewLogEntry],
) -> None:
    for record_id, record in approved.items():
        if record.approval is None:
            raise DatasetValidationError(f"approved record {record_id!r} has no approval")
        candidate = candidates.get(record_id)
        if candidate is None:
            raise DatasetValidationError(
                f"approved record {record_id!r} has no retained candidate source"
            )
        approval = record.approval
        if record_digest(candidate) != approval.candidate_sha256:
            raise DatasetValidationError(f"candidate hash mismatch for {record_id!r}")
        if record_digest(record) != approval.approved_record_sha256:
            raise DatasetValidationError(f"approved record hash mismatch for {record_id!r}")
        review = reviews.get(approval.review_id)
        if review is None or review.action != "approve":
            raise DatasetValidationError(f"approval review missing for {record_id!r}")
        if (
            review.record_id != record_id
            or review.reviewer_id != approval.reviewer_id
            or review.candidate_sha256 != approval.candidate_sha256
            or review.resulting_record_sha256 != approval.approved_record_sha256
        ):
            raise DatasetValidationError(f"approval review mismatch for {record_id!r}")


def _load_splits(root: Path) -> dict[DatasetSplit, set[str]]:
    split_ids: dict[DatasetSplit, set[str]] = {}
    for split in DatasetSplit:
        path = root / f"{split.value}_ids.txt"
        if not path.is_file():
            raise DatasetValidationError(f"missing split file: {path}")
        ids = {
            line.strip()
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        }
        split_ids[split] = ids
    return split_ids


def _validate_splits(
    split_ids: dict[DatasetSplit, set[str]],
    candidates: dict[str, ReviewableRecord],
    approved: dict[str, ReviewableRecord],
) -> None:
    seen: dict[str, DatasetSplit] = {}
    all_known = set(candidates) | set(approved)
    for split, ids in split_ids.items():
        unknown = ids - all_known
        if unknown:
            raise DatasetValidationError(
                f"{split.value} split references unknown IDs: {sorted(unknown)}"
            )
        for record_id in ids:
            previous = seen.get(record_id)
            if previous is not None:
                raise DatasetValidationError(
                    f"record {record_id!r} appears in both {previous.value} and {split.value}"
                )
            seen[record_id] = split
        if split in {DatasetSplit.DEV, DatasetSplit.TEST}:
            unapproved = ids - set(approved)
            if unapproved:
                raise DatasetValidationError(
                    f"{split.value} split contains non-approved IDs: {sorted(unapproved)}"
                )
