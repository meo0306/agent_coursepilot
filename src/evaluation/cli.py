from __future__ import annotations

import argparse
from pathlib import Path

from evaluation.contracts import TestLock
from evaluation.datasets import (
    COURSEPILOT_SPECS,
    COURSERAG_SPECS,
    load_coursepilot_human_score_jsonl,
    load_dataset_inventory,
    load_qa_human_score_jsonl,
)
from evaluation.schema_export import DEFAULT_SCHEMA_DIR, export_schemas


def validate_datasets(root: Path) -> tuple[int, int]:
    schema_mismatches = export_schemas(root / "schemas" / "v1", check=True)
    if schema_mismatches:
        raise ValueError(f"schema artifacts differ: {', '.join(schema_mismatches)}")
    courserag_root = root / "courserag_eval" / "v1"
    coursepilot_root = root / "coursepilot_eval" / "v1"
    courserag = load_dataset_inventory(courserag_root, COURSERAG_SPECS)
    coursepilot = load_dataset_inventory(coursepilot_root, COURSEPILOT_SPECS)
    load_qa_human_score_jsonl(courserag_root / "human_scores" / "pilot.jsonl")
    load_coursepilot_human_score_jsonl(coursepilot_root / "human_scores" / "pilot.jsonl")
    for dataset_root in (courserag_root, coursepilot_root):
        lock_path = dataset_root / "test.lock.json"
        TestLock.model_validate_json(lock_path.read_text(encoding="utf-8"))
    return (
        len(courserag.candidate_records) + len(courserag.approved_records),
        len(coursepilot.candidate_records) + len(coursepilot.approved_records),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="P02 evaluation data validation tools.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    validate = subparsers.add_parser(
        "validate-datasets",
        help="validate schemas, status boundaries, splits, approvals, and locks",
    )
    validate.add_argument("--root", type=Path, default=Path("datasets"))
    args = parser.parse_args()
    if args.command == "validate-datasets":
        courserag_count, coursepilot_count = validate_datasets(args.root)
        print(
            "validated P02 datasets: "
            f"CourseRAG records={courserag_count}, "
            f"CoursePilot records={coursepilot_count}; "
            f"schemas={DEFAULT_SCHEMA_DIR}"
        )


if __name__ == "__main__":
    main()
