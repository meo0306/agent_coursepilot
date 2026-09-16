from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path
from zipfile import ZipFile

from evaluation.p18_formal_data import (
    DOCX_COMMIT,
    DOCX_SOURCE_SHA,
    DOCX_STORAGE,
    build_business,
    build_faults,
    build_journeys,
    build_quality,
)
from evaluation.p18_schemas import P18ReviewTemplate


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_p18_business_split_and_source_scope() -> None:
    datasets = build_business()
    for dataset in datasets:
        assert len(dataset.cases) == 10
        assert Counter(case.split for case in dataset.cases) == {"dev": 6, "test": 4}
        assert Counter(case.course_id for case in dataset.cases) == {
            "course_ai_algorithms_systems": 5,
            "course_ai_general_education": 5,
        }
        assert all(not case.pilot_record_reused for case in dataset.cases)
        assert all(len(case.source_snapshots) == 2 for case in dataset.cases)
        assert all(
            {source.course_id for source in case.source_snapshots} == {case.course_id}
            for case in dataset.cases
        )
        family_splits: dict[str, set[str]] = {}
        for case in dataset.cases:
            family_splits.setdefault(case.task_family_id, set()).add(case.split)
        assert all(len(splits) == 1 for splits in family_splits.values())


def test_p18_quality_counts_and_recovery_contracts() -> None:
    validation, repair, recovery = build_quality(build_business())
    assert len(validation.carried_dev_records) == 30
    assert len(validation.new_cases) == 60
    assert Counter(case.split for case in validation.new_cases) == {
        "dev": 30,
        "test": 30,
    }
    assert Counter(case.artifact_type for case in validation.new_cases) == {
        "lesson": 20,
        "exam": 20,
        "ppt": 20,
    }

    assert len(repair.carried_dev_records) == 15
    assert len(repair.new_cases) == 45
    assert Counter(case.split for case in repair.new_cases) == {
        "dev": 27,
        "test": 18,
    }

    assert len(recovery.cases) == 24
    assert Counter(case.split for case in recovery.cases) == {"dev": 12, "test": 12}
    assert set(Counter(case.interrupt_type for case in recovery.cases).values()) == {4}
    for case in recovery.cases:
        assert case.expected_side_effects["duplicate_side_effects"] == 0
        expected_new_versions = int(case.decision in {"edit_resume", "replan"})
        assert case.expected_side_effects["artifact_versions_created"] == expected_new_versions
        assert case.expected_artifact_version_after == 1 + expected_new_versions


def test_p18_fault_and_journey_holdouts_are_new() -> None:
    fault_dataset, commitment = build_faults()
    assert len(fault_dataset.cases) == 30
    assert Counter(case.split for case in fault_dataset.cases) == {
        "dev": 20,
        "blind": 10,
    }
    assert Counter(case.category for case in fault_dataset.cases) == {
        "provider": 6,
        "courserag": 7,
        "worker": 3,
        "persistence": 4,
        "security": 10,
    }
    assert commitment["record_count"] == 10
    assert all(not case.p17_record_reused for case in fault_dataset.cases)
    assert len({case.scenario_family for case in fault_dataset.cases}) == 30

    journeys = build_journeys(build_business())
    assert len(journeys.cases) == 8
    assert all(case.split == "test" for case in journeys.cases)
    assert all(len(case.p17_signature_difference) >= 2 for case in journeys.cases)
    assert all(len(case.steps) >= 3 for case in journeys.cases)


def test_p18_custom_docx_is_pinned_and_safe() -> None:
    source = DOCX_STORAGE / "combined_areas.docx"
    normalized = DOCX_STORAGE / "combined_areas.coursepilot.normalized.docx"
    assert source.is_file()
    assert normalized.is_file()
    assert _sha256(source) == DOCX_SOURCE_SHA
    assert DOCX_COMMIT in str(source)

    with ZipFile(normalized) as archive:
        names = archive.namelist()
        assert not any("vbaproject" in name.casefold() for name in names)
        assert not any("activex" in name.casefold() for name in names)
        rel_text = "".join(
            archive.read(name).decode("utf-8", "replace")
            for name in names
            if name.endswith(".rels")
        )
        assert 'TargetMode="External"' not in rel_text
        xml = "".join(
            archive.read(name).decode("utf-8", "replace") for name in names if name.endswith(".xml")
        )
        for placeholder in (
            "{title}",
            "{section_title}",
            "{section_content}",
            "{header_title}",
            "{page_number}",
        ):
            assert placeholder in xml


def test_p18_review_templates_validate_as_exported_schema() -> None:
    roots = [
        Path("storage_eval/p18_business_review"),
        Path("storage_eval/p18_quality_recovery_review"),
        Path("storage_eval/p18_integration_export_review"),
    ]
    for root in roots:
        candidates = sorted(root.glob("*/p18_*review*.json"))
        assert candidates
        payload = json.loads(candidates[-1].read_text(encoding="utf-8"))
        review = P18ReviewTemplate.model_validate(payload)
        assert review.review_pass == "single"
        assert review.readable_records
        assert len(review.decisions) == sum(
            len(records) for records in review.readable_records.values()
        )
