from __future__ import annotations

import json
from pathlib import Path

from coursepilot.evals.formal_schemas import (
    CPDS3P16PilotDataset,
    CPDS7P16PilotDataset,
    P16BundleManifest,
)

ROOT = Path("datasets/coursepilot_eval/v1")


def test_p16_cp_ds3_candidate_distribution() -> None:
    payload = json.loads(
        (ROOT / "candidates/cp_ds3/p16_ppt_pilot_r1.json").read_text(encoding="utf-8")
    )
    dataset = CPDS3P16PilotDataset.model_validate(payload)
    assert [case.slide_count for case in dataset.cases] == [24, 12, 10]
    assert sum(len(case.slide_targets) for case in dataset.cases) == 46
    assert all(case.review_status.value == "candidate" for case in dataset.cases)


def test_p16_cp_ds7_template_distribution() -> None:
    payload = json.loads(
        (ROOT / "candidates/cp_ds7/p16_template_export_pilot_r1.json").read_text(encoding="utf-8")
    )
    dataset = CPDS7P16PilotDataset.model_validate(payload)
    assert sum(case.case_role == "gold_positive" for case in dataset.cases) == 4
    assert sum(case.case_role == "contract_negative" for case in dataset.cases) == 2
    external = next(case for case in dataset.cases if case.template_id == "p16_external_velis_v1")
    assert external.master_count == 2
    assert external.layout_count == 32
    assert external.license == "CC0-1.0"


def test_p16_r2_candidate_has_renderer_backed_review_material() -> None:
    ds3 = CPDS3P16PilotDataset.model_validate_json(
        (ROOT / "candidates/cp_ds3/p16_ppt_pilot_r2.json").read_text(encoding="utf-8")
    )
    ds7 = CPDS7P16PilotDataset.model_validate_json(
        (ROOT / "candidates/cp_ds7/p16_template_export_pilot_r2.json").read_text(encoding="utf-8")
    )
    manifest = P16BundleManifest.model_validate_json(
        (ROOT / "provenance/p16_cp_ds37_bundle_manifest_r2.json").read_text(encoding="utf-8")
    )

    slides = [target for case in ds3.cases for target in case.slide_targets]
    assert len(slides) == 46
    assert sum(bool(target.risk_flags) for target in slides) == 9

    positives = [case for case in ds7.cases if case.case_role == "gold_positive"]
    assert all(case.render_snapshot is not None for case in positives)
    assert sum(case.render_snapshot.slide_count for case in positives if case.render_snapshot) == 17
    assert all(
        case.render_snapshot.repeat_render_pngs_identical
        for case in positives
        if case.render_snapshot
    )
    external = next(case for case in positives if case.template_id == "p16_external_velis_v1")
    assert external.render_snapshot is not None
    assert external.render_snapshot.slide_count == 8
    assert external.render_snapshot.image_only_slide_count == 0
    assert external.render_snapshot.editable_shape_count > 0

    assert len(manifest.record_hashes) == 55
    assert len(manifest.review_sets["first"]) == 55
    assert len(manifest.review_sets["second"]) == 23
    assert len(manifest.render_artifacts) == 39


def test_p16_r2_review_pages_are_complete_and_exportable() -> None:
    manifest = P16BundleManifest.model_validate_json(
        (ROOT / "provenance/p16_cp_ds37_bundle_manifest_r2.json").read_text(encoding="utf-8")
    )
    review_root = Path("storage_eval/cpds37_p16_review") / manifest.bundle_sha256
    first = (review_root / "index.html").read_text(encoding="utf-8")
    second = (review_root / "second_review.html").read_text(encoding="utf-8")

    assert first.count('<fieldset class="decision" data-review-id="') == 55
    assert second.count('<fieldset class="decision" data-review-id="') == 23
    assert "localStorage" in first
    assert "校验并下载审核 JSON" in first
    assert "Evidence 原文与必要邻接" in first
    assert "assets/p16-ds7-external-velis/" in first
    assert (review_root / "p16_first_review_template.json").is_file()
    assert (review_root / "p16_second_review_template.json").is_file()
