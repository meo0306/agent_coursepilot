import json
from pathlib import Path

from evaluation.system_optimization.dev_data import write_candidate_data
from evaluation.system_optimization.dev_loader import load_candidate
from evaluation.system_optimization.schemas import ArtifactType, MaterialType


def test_generator_creates_only_candidates_from_non_p18_sources(tmp_path: Path) -> None:
    write_candidate_data(Path.cwd(), tmp_path)
    loaded = load_candidate(tmp_path)

    assert not (tmp_path / "approved").exists()
    assert all(
        item.source_origin == "courserag_approved_non_p18_dev"
        for case in loaded.cases.records
        for item in case.evidence_package.items
    )
    assert all(
        item.dev_context_ids
        and all(context_id.startswith("gold-ctx-") for context_id in item.dev_context_ids)
        for case in loaded.cases.records
        for item in case.evidence_package.items
    )
    assert all(
        not item.evidence_id.casefold().startswith("p18")
        for case in loaded.cases.records
        for item in case.evidence_package.items
    )


def test_every_source_context_is_an_approved_dev_context() -> None:
    contexts = json.loads(
        Path("datasets/courserag_eval/v1/approved/ds5/p09_context.json").read_text(encoding="utf-8")
    )["cases"]
    approved_dev_ids = {
        item["record_id"]
        for item in contexts
        if item["split"] == "dev" and item["review_status"] == "approved"
    }
    loaded = load_candidate()
    referenced = {
        context_id
        for case in loaded.cases.records
        for item in case.evidence_package.items
        for context_id in item.dev_context_ids
    }

    assert referenced
    assert referenced <= approved_dev_ids


def test_each_artifact_covers_quantity_and_material_matrix() -> None:
    records = load_candidate().cases.records
    expected_quantities = {
        ArtifactType.LESSON: {1, 2},
        ArtifactType.EXAM: {2, 4, 6},
        ArtifactType.PPT: {3, 5, 7},
    }
    for artifact, quantities in expected_quantities.items():
        selected = [item for item in records if item.artifact_type is artifact]
        assert {item.task_demand.output_count for item in selected} == quantities
        assert all(
            len(item.task_demand.knowledge_point_ids)
            == {"single": 1, "adjacent": 2, "non_adjacent": 3}[
                item.task_demand.topic_relation.value
            ]
            for item in selected
        )
        assert {
            material for item in selected for material in item.task_demand.required_material_types
        } == set(MaterialType)
        assert all(item.candidate_adequacy.status.value == "adequate" for item in selected)
        assert all(not item.evidence_package.missing_knowledge_point_ids for item in selected)
        assert all(not item.evidence_package.missing_material_types for item in selected)
        assert all(
            {
                evidence_id
                for group in item.evidence_package.groups
                for evidence_id in group.evidence_ids
            }
            == {evidence.evidence_id for evidence in item.evidence_package.items}
            for item in selected
        )


def test_failure_replays_cover_exact_approved_categories() -> None:
    failures = load_candidate().failures.records
    assert {item.category for item in failures} == {
        "schema",
        "timeout",
        "missing_batch",
        "incomplete_group",
        "index_missing",
    }
    assert {item.artifact_type for item in failures if item.category == "schema"} == set(
        ArtifactType
    )


def test_capacity_tiers_use_only_task_evidence_and_increase_mean_tokens() -> None:
    records = load_candidate().cases.records
    mean_tokens = {}
    for tier in ("thin", "medium", "rich"):
        selected = [item for item in records if item.evidence_package.capacity_tier.value == tier]
        mean_tokens[tier] = sum(item.evidence_package.estimated_tokens for item in selected) / len(
            selected
        )

    assert mean_tokens["thin"] < mean_tokens["medium"] < mean_tokens["rich"]
