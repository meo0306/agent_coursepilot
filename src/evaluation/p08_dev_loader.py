"""Fail-closed loader for the Approved P08 retrieval_main Dev tuning slice."""

from __future__ import annotations

import json
from pathlib import Path

from courserag.evals.schemas import (
    DS5RetrievalQADataset,
    P08DS5SplitManifest,
    P08GoldBundleManifest,
)
from evaluation.corpus_fixtures import sha256_file


def _resolve_bundle_artifact(dataset_root: Path, relative_path: str) -> Path:
    artifact = Path(relative_path)
    repository_root = dataset_root.parents[2]
    resolved = (repository_root / artifact).resolve()
    if not resolved.is_relative_to(repository_root):
        raise ValueError("P08 bundle artifact escapes the repository root")
    return resolved


def load_p08_tuning_cases(
    dataset_root: Path,
    *,
    requested_ids: set[str] | None = None,
) -> tuple:
    dataset_root = dataset_root.resolve()
    manifest = json.loads((dataset_root / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("phase_input_status", {}).get("p08") not in {
        "formal_dev_eval_ready",
        "completed_gate_passed",
    }:
        raise ValueError("P08 Dev loader requires explicitly Approved retrieval Gold")
    if manifest.get("gold_components", {}).get("ds5_retrieval") != "approved":
        raise ValueError("P08 Dev loader requires approved ds5_retrieval")
    approved_path = dataset_root / "approved/ds5/p08_retrieval.json"
    if not approved_path.is_file():
        raise ValueError("Approved P08 DS5 artifact is missing")
    dataset = DS5RetrievalQADataset.model_validate_json(approved_path.read_text(encoding="utf-8"))
    bundle_path = dataset_root / "provenance/p08_gold_bundle_manifest.json"
    bundle = P08GoldBundleManifest.model_validate_json(bundle_path.read_text(encoding="utf-8"))
    split_path = _resolve_bundle_artifact(dataset_root, bundle.split_manifest.path)
    if sha256_file(split_path) != bundle.split_manifest.sha256:
        raise ValueError("P08 split artifact hash does not match the approved bundle")
    split = P08DS5SplitManifest.model_validate_json(split_path.read_text(encoding="utf-8"))
    test_ids = {item.case_id for item in split.assignments if item.split == "test"}
    allowed_ids = set(split.p08_tuning_allowed_ids)
    selected_ids = requested_ids if requested_ids is not None else allowed_ids
    if selected_ids & test_ids:
        raise ValueError("P08 tuning loader refuses Test IDs")
    if not selected_ids.issubset(allowed_ids):
        raise ValueError("P08 tuning loader only accepts retrieval_main Dev IDs")
    by_id = {item.record_id: item for item in dataset.cases}
    if not selected_ids.issubset(by_id):
        raise ValueError("P08 tuning selection references missing Approved cases")
    selected = tuple(item for item in dataset.cases if item.record_id in selected_ids)
    if any(item.review_status != "approved" for item in selected):
        raise ValueError("P08 tuning loader refuses unapproved records")
    return selected
