from __future__ import annotations

import json
from pathlib import Path

from evaluation.p18_formal_data import _record_hash
from evaluation.p18_schemas import (
    P18FaultDataset,
    P18JourneyDataset,
    P18RepairDataset,
    P18ReviewTemplate,
    P18TemplateDataset,
)

ROOT = Path("datasets/coursepilot_eval/v1")
QUALITY_SHA = "d724a1c430ed1c02ae42b770b46714fe3ff0b73abb94d83906d9e6268470a082"
INTEGRATION_SHA = "5d42d4428aad1f31b07434febcd9ff9b487436095c5c99d3f3e2348627a46683"


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _cases_by_id(payload: dict, field: str = "cases") -> dict[str, dict]:
    return {item["record_id"]: item for item in payload[field]}


def test_p18_r2_reviews_are_incremental_and_complete() -> None:
    quality = P18ReviewTemplate.model_validate(
        _load(
            Path(f"storage_eval/p18_quality_recovery_review/{QUALITY_SHA}")
            / "p18_quality_recovery_r2_review.json"
        )
    )
    integration = P18ReviewTemplate.model_validate(
        _load(
            Path(f"storage_eval/p18_integration_export_review/{INTEGRATION_SHA}")
            / "p18_integration_export_r2_review.json"
        )
    )
    assert quality.bundle_sha256 == QUALITY_SHA
    assert integration.bundle_sha256 == INTEGRATION_SHA
    assert len(quality.decisions) == 18
    assert len(integration.decisions) == 8
    assert all(item.decision == "approve" for item in quality.decisions)
    assert all(item.decision == "approve" for item in integration.decisions)


def test_quality_r2_changes_exactly_the_rejected_repairs() -> None:
    r1 = _load(ROOT / "candidates/cp_ds5/p18_repair_formal_r1.json")
    r2 = _load(ROOT / "candidates/cp_ds5/p18_repair_formal_r2.json")
    P18RepairDataset.model_validate(r2)
    first = _cases_by_id(r1, "new_cases")
    second = _cases_by_id(r2, "new_cases")
    changed = {
        record_id
        for record_id in first
        if _record_hash(first[record_id]) != _record_hash(second[record_id])
    }
    assert len(changed) == 18
    for record_id, item in second.items():
        assert set(item["allowed_paths"]).isdisjoint(item["forbidden_paths"])
        if record_id not in changed:
            assert _record_hash(item) == _record_hash(first[record_id])


def test_integration_r2_repairs_render_fault_and_journey_contracts() -> None:
    templates = P18TemplateDataset.model_validate(
        _load(ROOT / "candidates/cp_ds7/p18_export_templates_formal_r2.json")
    )
    custom = next(case for case in templates.cases if case.source_kind == "github_public")
    assert custom.source_repository == "https://github.com/sverrejb/docxide-template"
    assert custom.source_repository_path == "test-crate/templates/combined_areas.docx"
    assert custom.render_status == "verified_current"
    assert custom.render_evidence is not None
    assert custom.render_evidence.renderer_version == "7.4.7.2"
    assert custom.render_evidence.repeat_render_equal
    assert custom.render_evidence.page_count == 1

    faults = P18FaultDataset.model_validate(
        _load(ROOT / "candidates/cp_ds8/p18_fault_security_formal_r2.json")
    )
    by_fault = {case.record_id: case for case in faults.cases}
    assert by_fault["p18-ds8-17"].initial_state["approval_scope"] == "export"
    assert by_fault["p18-ds8-17"].variants[0].expected_side_effect_count == 1
    assert "不重写导出文件" in by_fault["p18-ds8-17"].variants[0].resume_rule
    assert by_fault["p18-ds8-18"].initial_state["approval_scope"] == "verified_writeback"
    assert "不得重复写入" in by_fault["p18-ds8-18"].variants[0].resume_rule

    journeys = P18JourneyDataset.model_validate(
        _load(ROOT / "candidates/sys_ds1/p18_system_journeys_formal_r2.json")
    )
    by_journey = {case.record_id: case for case in journeys.cases}
    assert sum(step.expected_side_effect_count for step in by_journey["p18-sys-ds1-04"].steps) == 2
    assert "worker_crash" in by_journey["p18-sys-ds1-05"].steps[1].action
    assert "缺少 Required Evidence" in by_journey["p18-sys-ds1-06"].steps[0].version_assertion
    assert "FAKE_TOKEN_CANARY_P18" in by_journey["p18-sys-ds1-07"].steps[0].assertions[0]
    assert by_journey["p18-sys-ds1-08"].steps[2].expected_state == "stale_requires_re_review"
    assert by_journey["p18-sys-ds1-08"].steps[-1].expected_state == "completed"
