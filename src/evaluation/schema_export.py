from __future__ import annotations

import argparse
import json
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
    HumanScoreDataset,
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
    QAHumanScoreDataset,
)
from evaluation.contracts import TestLock
from evaluation.manifest import RunManifest

SCHEMA_MODELS: dict[str, type[BaseModel]] = {
    "courserag_ds0.schema.json": DS0CorpusDataset,
    "courserag_ds1.schema.json": DS1ParsingDataset,
    "courserag_ds2.schema.json": DS2EvidenceDataset,
    "courserag_ds3.schema.json": DS3KnowledgePointDataset,
    "courserag_ds4.schema.json": DS4QueryProcessingDataset,
    "courserag_ds5.schema.json": DS5RetrievalQADataset,
    "courserag_ds6.schema.json": DS6CitationMigrationDataset,
    "courserag_ds7.schema.json": DS7IncrementalWritebackDataset,
    "courserag_ds8.schema.json": DS8PerformanceDataset,
    "courserag_qa_human_scores.schema.json": QAHumanScoreDataset,
    "courserag_qa_human_score_record.schema.json": QAHumanReviewRecord,
    "coursepilot_cp_ds0.schema.json": CPDS0ManifestDataset,
    "coursepilot_cp_ds1.schema.json": CPDS1LessonDataset,
    "coursepilot_cp_ds2.schema.json": CPDS2ExamDataset,
    "coursepilot_cp_ds3.schema.json": CPDS3PPTDataset,
    "coursepilot_cp_ds4.schema.json": CPDS4ValidationDataset,
    "coursepilot_cp_ds5.schema.json": CPDS5RepairDataset,
    "coursepilot_cp_ds6.schema.json": CPDS6RecoveryDataset,
    "coursepilot_cp_ds7.schema.json": CPDS7ExportDataset,
    "coursepilot_cp_ds8.schema.json": CPDS8FaultSecurityDataset,
    "coursepilot_sys_ds1.schema.json": SYSDS1JourneyDataset,
    "coursepilot_human_scores.schema.json": HumanScoreDataset,
    "coursepilot_human_score_record.schema.json": HumanScoreJsonlRecord,
    "run_manifest.schema.json": RunManifest,
    "test_lock.schema.json": TestLock,
}

DEFAULT_SCHEMA_DIR = Path("datasets/schemas/v1")


def schema_text(model: type[BaseModel]) -> str:
    return (
        json.dumps(
            model.model_json_schema(mode="validation"),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )


def export_schemas(output_dir: Path, *, check: bool) -> list[str]:
    mismatches: list[str] = []
    if not check:
        output_dir.mkdir(parents=True, exist_ok=True)
    for filename, model in SCHEMA_MODELS.items():
        path = output_dir / filename
        expected = schema_text(model)
        if check:
            if not path.is_file() or path.read_text(encoding="utf-8") != expected:
                mismatches.append(filename)
        else:
            path.write_text(expected, encoding="utf-8")
    return mismatches


def main() -> None:
    parser = argparse.ArgumentParser(description="Export or verify P02 JSON Schema artifacts.")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_SCHEMA_DIR)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    mismatches = export_schemas(args.output_dir, check=args.check)
    if mismatches:
        raise SystemExit(f"Schema artifacts differ: {', '.join(mismatches)}")
    action = "verified" if args.check else "exported"
    print(f"{action} {len(SCHEMA_MODELS)} schemas in {args.output_dir}")


if __name__ == "__main__":
    main()
