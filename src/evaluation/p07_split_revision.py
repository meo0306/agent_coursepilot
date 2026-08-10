"""Create and approve a Section-Window-isolated P07 evaluation protocol revision."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator

from courserag.evals.schemas import (
    DS3KnowledgePointDataset,
    DS3SplitManifest,
    P07GoldBundleApproval,
)
from evaluation.contracts import HashedArtifact, Sha256, StrictModel
from evaluation.datasets import canonical_json_bytes
from evaluation.io import atomic_write_json
from evaluation.manifest import sha256_file

DATASET_ROOT = Path("datasets/courserag_eval/v1")
APPROVED_DS3 = DATASET_ROOT / "approved/ds3/p07_knowledge_points.json"
PRIOR_SPLIT = DATASET_ROOT / "provenance/ds3_p07_split.json"
REVISED_SPLIT = DATASET_ROOT / "provenance/ds3_p07_split_r2.json"
PRIOR_APPROVAL = DATASET_ROOT / "provenance/p07_gold_bundle_approval.json"
PROTOCOL_CANDIDATE = DATASET_ROOT / "provenance/p07_evaluation_protocol_r2.json"
PROTOCOL_APPROVAL = DATASET_ROOT / "provenance/p07_evaluation_protocol_r2_approval.json"
ALGORITHM_ID = "course-section-window-connected-component-stratified-dp-v1"


class P07EvaluationProtocolCandidate(StrictModel):
    schema_version: Literal["courserag.p07-evaluation-protocol.v1"] = (
        "courserag.p07-evaluation-protocol.v1"
    )
    dataset_id: Literal["courserag-p07-evaluation-protocol"] = "courserag-p07-evaluation-protocol"
    dataset_version: Literal["p07-r2"] = "p07-r2"
    protocol_bundle_sha256: Sha256
    prior_approved_bundle_sha256: Sha256
    prior_approval: HashedArtifact
    approved_knowledge_points: HashedArtifact
    prior_split: HashedArtifact
    revised_split: HashedArtifact
    split_unit: Literal["provider_section_window_connected_component"]
    algorithm_profile_sha256: Sha256
    semantic_artifacts_unchanged: Literal[True] = True
    mixed_scope_count: Literal[0] = 0
    constraints: list[str] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_bundle_identity(self) -> P07EvaluationProtocolCandidate:
        if self.protocol_bundle_sha256 != _protocol_digest(self):
            raise ValueError("P07 evaluation protocol Bundle SHA-256 differs from its identity")
        return self


class P07EvaluationProtocolApproval(StrictModel):
    schema_version: Literal["courserag.p07-evaluation-protocol-approval.v1"] = (
        "courserag.p07-evaluation-protocol-approval.v1"
    )
    review_id: str = Field(min_length=1, max_length=160)
    reviewer_id: str = Field(min_length=1, max_length=160)
    reviewed_at: datetime
    protocol_bundle_sha256: Sha256
    protocol_candidate: HashedArtifact
    revised_split: HashedArtifact
    approved_knowledge_points: HashedArtifact
    notes: str = Field(min_length=1, max_length=4000)


def generate_protocol_revision(repository_root: Path) -> P07EvaluationProtocolCandidate:
    root = repository_root.resolve()
    gold_path = root / APPROVED_DS3
    prior_approval_path = root / PRIOR_APPROVAL
    prior_split_path = root / PRIOR_SPLIT
    gold = DS3KnowledgePointDataset.model_validate_json(gold_path.read_text(encoding="utf-8"))
    prior_approval = P07GoldBundleApproval.model_validate_json(
        prior_approval_path.read_text(encoding="utf-8")
    )
    if prior_approval.approved_knowledge_points.sha256 != sha256_file(gold_path):
        raise ValueError("Approved DS3 differs from the prior exact Bundle approval")
    revised = build_section_isolated_split(gold)
    revised_path = root / REVISED_SPLIT
    atomic_write_json(revised_path, revised.model_dump(mode="json"))
    prior_approval_artifact = _artifact(root, prior_approval_path)
    approved_knowledge_points = _artifact(root, gold_path)
    prior_split = _artifact(root, prior_split_path)
    revised_split = _artifact(root, revised_path)
    constraints = [
        "Approved DS3 Knowledge Point and Evidence content is byte-unchanged.",
        "Every Provider Section Window belongs to exactly one split side.",
        "Every concept family belongs to exactly one split side.",
        "Calibration precedes a single Holdout run; Test remains empty and unlocked.",
        "No Provider output, retrieval hit, or external fact defines Gold or split membership.",
    ]
    provisional = P07EvaluationProtocolCandidate.model_construct(
        protocol_bundle_sha256="0" * 64,
        prior_approved_bundle_sha256=prior_approval.bundle_sha256,
        prior_approval=prior_approval_artifact,
        approved_knowledge_points=approved_knowledge_points,
        prior_split=prior_split,
        revised_split=revised_split,
        split_unit="provider_section_window_connected_component",
        algorithm_profile_sha256=revised.algorithm_profile_sha256,
        constraints=constraints,
    )
    candidate = P07EvaluationProtocolCandidate(
        protocol_bundle_sha256=_protocol_digest(provisional),
        prior_approved_bundle_sha256=prior_approval.bundle_sha256,
        prior_approval=prior_approval_artifact,
        approved_knowledge_points=approved_knowledge_points,
        prior_split=prior_split,
        revised_split=revised_split,
        split_unit="provider_section_window_connected_component",
        algorithm_profile_sha256=revised.algorithm_profile_sha256,
        constraints=constraints,
    )
    atomic_write_json(root / PROTOCOL_CANDIDATE, candidate.model_dump(mode="json"))
    return candidate


def approve_protocol_revision(
    *,
    repository_root: Path,
    expected_bundle_sha256: str,
    reviewer_id: str,
    reviewed_at: datetime,
    review_id: str,
    notes: str,
) -> P07EvaluationProtocolApproval:
    root = repository_root.resolve()
    candidate_path = root / PROTOCOL_CANDIDATE
    candidate = P07EvaluationProtocolCandidate.model_validate_json(
        candidate_path.read_text(encoding="utf-8")
    )
    if candidate.protocol_bundle_sha256 != expected_bundle_sha256:
        raise ValueError("literal P07 protocol Bundle SHA-256 differs from Candidate")
    _validate_artifact(root, candidate.prior_approval)
    _validate_artifact(root, candidate.approved_knowledge_points)
    _validate_artifact(root, candidate.prior_split)
    _validate_artifact(root, candidate.revised_split)
    revised = DS3SplitManifest.model_validate_json(
        (root / candidate.revised_split.path).read_text(encoding="utf-8")
    )
    gold = DS3KnowledgePointDataset.model_validate_json(
        (root / candidate.approved_knowledge_points.path).read_text(encoding="utf-8")
    )
    if _mixed_scopes(gold, revised):
        raise ValueError("revised P07 split still mixes Provider Section Windows")
    approval = P07EvaluationProtocolApproval(
        review_id=review_id,
        reviewer_id=reviewer_id,
        reviewed_at=reviewed_at,
        protocol_bundle_sha256=candidate.protocol_bundle_sha256,
        protocol_candidate=_artifact(root, candidate_path),
        revised_split=candidate.revised_split,
        approved_knowledge_points=candidate.approved_knowledge_points,
        notes=notes,
    )
    approval_path = root / PROTOCOL_APPROVAL
    if approval_path.exists():
        existing = P07EvaluationProtocolApproval.model_validate_json(
            approval_path.read_text(encoding="utf-8")
        )
        if existing != approval:
            raise ValueError("existing P07 evaluation protocol approval differs")
    else:
        atomic_write_json(approval_path, approval.model_dump(mode="json"))
    return approval


def build_section_isolated_split(gold: DS3KnowledgePointDataset) -> DS3SplitManifest:
    records = gold.knowledge_points
    by_id = {item.gold_kp_id: item for item in records}
    scopes = sorted({scope for item in records for scope in item.source_scope_ids})
    parent = {scope: scope for scope in scopes}

    def find(scope: str) -> str:
        while parent[scope] != scope:
            parent[scope] = parent[parent[scope]]
            scope = parent[scope]
        return scope

    def union(first: str, second: str) -> None:
        first_root, second_root = find(first), find(second)
        if first_root != second_root:
            parent[max(first_root, second_root)] = min(first_root, second_root)

    families: dict[str, list[str]] = defaultdict(list)
    for item in records:
        family = item.concept_family_id or item.gold_kp_id
        families[family].extend(item.source_scope_ids)
        for scope in item.source_scope_ids[1:]:
            union(item.source_scope_ids[0], scope)
    for family_scopes in families.values():
        unique = sorted(set(family_scopes))
        for scope in unique[1:]:
            union(unique[0], scope)

    component_records: dict[str, set[str]] = defaultdict(set)
    for item in records:
        roots = {find(scope) for scope in item.source_scope_ids}
        if len(roots) != 1:
            raise ValueError("Knowledge Point spans disconnected split components")
        component_records[next(iter(roots))].add(item.gold_kp_id)

    components_by_course: dict[str, list[tuple[str, tuple[str, ...]]]] = defaultdict(list)
    for component, ids in component_records.items():
        courses = {by_id[item_id].course_id for item_id in ids}
        if len(courses) != 1:
            raise ValueError("P07 split component crosses courses")
        components_by_course[next(iter(courses))].append((component, tuple(sorted(ids))))

    calibration: set[str] = set()
    component_labels: dict[str, Literal["calibration", "holdout"]] = {}
    for course_id, components in sorted(components_by_course.items()):
        selected_components = _select_calibration_components(course_id, components)
        for component, knowledge_point_ids in components:
            label: Literal["calibration", "holdout"] = (
                "calibration" if component in selected_components else "holdout"
            )
            component_labels[component] = label
            if label == "calibration":
                calibration.update(knowledge_point_ids)
    holdout = set(by_id) - calibration
    assignments: dict[str, Literal["calibration", "holdout"]] = {}
    for family, family_scopes in families.items():
        labels = {component_labels[find(scope)] for scope in family_scopes}
        if len(labels) != 1:
            raise ValueError("Concept family crosses revised split sides")
        assignments[family] = next(iter(labels))
    revised = DS3SplitManifest(
        dataset_id="courserag-ds3-p07-split",
        dataset_version="p07-r2",
        calibration_ids=sorted(calibration),
        holdout_ids=sorted(holdout),
        family_assignments=assignments,
        actual_calibration_ratio=len(calibration) / len(records),
        algorithm_profile_sha256=hashlib.sha256(ALGORITHM_ID.encode("utf-8")).hexdigest(),
    )
    if _mixed_scopes(gold, revised):
        raise ValueError("Section-isolated split construction produced mixed Scopes")
    return revised


def _select_calibration_components(
    course_id: str, components: list[tuple[str, tuple[str, ...]]]
) -> set[str]:
    ordered = sorted(
        components,
        key=lambda item: hashlib.sha256(
            f"{ALGORITHM_ID}\n{course_id}\n{item[0]}".encode()
        ).hexdigest(),
    )
    total = sum(len(ids) for _, ids in ordered)
    target = total * 0.7
    states: dict[int, tuple[str, ...]] = {0: ()}
    for component, ids in ordered:
        weight = len(ids)
        additions = {
            count + weight: (*selection, component)
            for count, selection in states.items()
            if count + weight < total
        }
        for count, selection in additions.items():
            current = states.get(count)
            if current is None or selection < current:
                states[count] = selection
    valid = [(count, selected) for count, selected in states.items() if 0 < count < total]
    if not valid:
        raise ValueError("Each course requires at least two Section split components")
    _, chosen_components = min(
        valid,
        key=lambda item: (abs(item[0] - target), abs(item[0] / total - 0.7), item[1]),
    )
    return set(chosen_components)


def _mixed_scopes(gold: DS3KnowledgePointDataset, split: DS3SplitManifest) -> tuple[str, ...]:
    calibration = set(split.calibration_ids)
    labels: dict[str, set[str]] = defaultdict(set)
    for item in gold.knowledge_points:
        label = "calibration" if item.gold_kp_id in calibration else "holdout"
        for scope in item.source_scope_ids:
            labels[scope].add(label)
    return tuple(sorted(scope for scope, values in labels.items() if len(values) > 1))


def _protocol_digest(candidate: P07EvaluationProtocolCandidate) -> str:
    payload = candidate.model_dump(mode="json")
    payload.pop("protocol_bundle_sha256", None)
    return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()


def _artifact(root: Path, path: Path) -> HashedArtifact:
    resolved = path.resolve()
    return HashedArtifact(
        path=resolved.relative_to(root).as_posix(),
        sha256=sha256_file(resolved),
        size_bytes=resolved.stat().st_size,
        media_type="application/json",
    )


def _validate_artifact(root: Path, artifact: HashedArtifact) -> None:
    path = (root / artifact.path).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        raise ValueError("P07 protocol artifact path is missing or outside repository")
    if path.stat().st_size != artifact.size_bytes or sha256_file(path) != artifact.sha256:
        raise ValueError("P07 protocol artifact identity changed")


def main() -> None:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    generate = subparsers.add_parser("generate")
    generate.add_argument("--repository-root", type=Path, default=Path.cwd())
    approve = subparsers.add_parser("approve")
    approve.add_argument("--repository-root", type=Path, default=Path.cwd())
    approve.add_argument("--expected-bundle-sha256", required=True)
    approve.add_argument("--reviewer-id", required=True)
    approve.add_argument("--reviewed-at", type=datetime.fromisoformat, required=True)
    approve.add_argument("--review-id", required=True)
    approve.add_argument("--notes", required=True)
    args = parser.parse_args()
    if args.command == "generate":
        candidate = generate_protocol_revision(args.repository_root)
        print(json.dumps(candidate.model_dump(mode="json"), ensure_ascii=False, sort_keys=True))
        return
    approval = approve_protocol_revision(
        repository_root=args.repository_root,
        expected_bundle_sha256=args.expected_bundle_sha256,
        reviewer_id=args.reviewer_id,
        reviewed_at=args.reviewed_at,
        review_id=args.review_id,
        notes=args.notes,
    )
    print(json.dumps(approval.model_dump(mode="json"), ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
