"""Build the deterministic P12 CP-DS6 Pilot Candidate."""

from __future__ import annotations

import argparse
import hashlib
import html
import json
from pathlib import Path

from coursepilot.evals.formal_schemas import CPDS6P12PilotDataset, P12InterruptRecoveryCase
from evaluation.io import atomic_write_json, atomic_write_text

DATASET_ROOT = Path("datasets/coursepilot_eval/v1")
CANDIDATE_PATH = DATASET_ROOT / "candidates/cp_ds6/p12_interrupt_recovery_r1.json"
REPORT_PATH = Path("docs/refactor/phase_reports/ED_PRE_P12_CPDS6_candidate_review.md")
INTERRUPTS = (
    ("lesson_session_plan_review", "lesson"),
    ("lesson_final_review", "lesson"),
    ("exam_blueprint_review", "exam"),
    ("exam_global_review", "exam"),
    ("ppt_architecture_review", "ppt"),
    ("ppt_final_review", "ppt"),
)
SCENARIOS = ("approve", "edit_resume", "replan", "reject")


def _case(
    interrupt_type: str, workflow_type: str, scenario: str, ordinal: int
) -> P12InterruptRecoveryCase:
    slug = interrupt_type.replace("_review", "").replace("_", "-")
    case_id = f"p12-{slug}-{scenario.replace('_', '-')}-{ordinal:02d}"
    before, after = 1, 1
    editable: list[str] = []
    patch: dict[str, str] = {}
    invalidated: list[str] = []
    granted: list[str] = []
    error_class: str | None = None
    stale = False
    if scenario == "approve":
        faults = ["long_pause", "service_restart", "duplicate_decision"]
        transitions = ["running->waiting_human", "waiting_human->running", "running->completed"]
        granted = ["continue_generation"]
    elif scenario == "edit_resume":
        faults = ["worker_crash_before_resume", "service_restart", "edit_then_resume"]
        transitions = ["running->waiting_human", "waiting_human->running", "running->completed"]
        after = 2
        editable = (
            ["$.architecture.slides[0].title"] if workflow_type == "ppt" else ["$.plan.title"]
        )
        patch = {editable[0]: "owner-edited-structure"}
        granted = ["continue_generation"]
    elif scenario == "replan":
        faults = ["courserag_index_version_changed", "context_version_changed", "replan_request"]
        transitions = [
            "running->waiting_human",
            "waiting_human->needs_review",
            "needs_review->running",
        ]
        invalidated = ["build_context_ref", "generate_components"]
        granted = ["replan"]
        error_class, stale = "stale_context_version", True
    else:
        faults = ["template_version_changed", "duplicate_cancel", "cancel_request"]
        transitions = ["running->waiting_human", "waiting_human->cancelled", "cancelled->terminal"]
        invalidated = ["generate_components", "export", "writeback"]
        error_class = "task_cancelled"
    return P12InterruptRecoveryCase(
        record_id=case_id,
        candidate_source="p12_deterministic_structure_fixture",
        interrupt_type=interrupt_type,
        workflow_type=workflow_type,
        scenario_type=scenario,
        fixture_id=f"p12-structure-{workflow_type}-{slug}",
        task_ref=f"task:p12:{case_id}",
        thread_ref=f"thread:p12:{workflow_type}-{case_id}",
        checkpoint_ref=f"checkpoint:p12:{case_id}",
        artifact_ref=f"artifact:p12:{case_id}",
        initial_state={
            "queued": "running",
            "running": "waiting_human",
            "artifact": "v1",
            "course_context": "opaque-structure-fixture",
        },
        fault_sequence=faults,
        human_decision=scenario,
        editable_paths=editable,
        edit_patch=patch,
        expected_state_transitions=transitions,
        expected_artifact_version_before=before,
        expected_artifact_version_after=after,
        expected_reused_nodes=["load_template_snapshot", "build_context_ref"],
        expected_invalidated_nodes=invalidated,
        approval_scope_granted=granted,
        approval_scope_forbidden=["verified_writeback"],
        expected_side_effects={
            "decision_records": 1,
            "duplicate_decision_records": 0,
            "artifact_versions_created": int(scenario == "edit_resume"),
            "exports": 0,
            "writebacks": 0,
        },
        expected_error_class=error_class,
        stale_version_detected=stale,
    )


def build_dataset() -> CPDS6P12PilotDataset:
    return CPDS6P12PilotDataset(
        cases=[
            _case(interrupt_type, workflow_type, scenario, ordinal)
            for interrupt_type, workflow_type in INTERRUPTS
            for ordinal, scenario in enumerate(SCENARIOS, 1)
        ]
    )


def _review_html(dataset: CPDS6P12PilotDataset, candidate_sha: str) -> str:
    cards = []
    for case in dataset.cases:
        payload = html.escape(
            json.dumps(case.model_dump(mode="json"), ensure_ascii=False, indent=2)
        )
        cards.append(
            f"<article><h2>{html.escape(case.record_id)}</h2>"
            f"<h3>{html.escape(case.interrupt_type)} · {html.escape(case.scenario_type)}</h3>"
            f"<p>Workflow: <b>{case.workflow_type}</b> · Fixture: <b>{case.fixture_id}</b></p>"
            f"<h4>Fault sequence</h4><ol>{''.join(f'<li>{html.escape(item)}</li>' for item in case.fault_sequence)}</ol>"
            f"<h4>Expected state transitions</h4><p>{html.escape(' → '.join(case.expected_state_transitions))}</p>"
            f"<h4>Artifact version and editable paths</h4><p>v{case.expected_artifact_version_before} → v{case.expected_artifact_version_after}; "
            f"{html.escape(', '.join(case.editable_paths) or 'no editable paths')}</p>"
            f"<h4>Approval scope</h4><p>Granted: {html.escape(', '.join(case.approval_scope_granted) or 'none')} · "
            f"Forbidden: {html.escape(', '.join(case.approval_scope_forbidden))}</p>"
            f"<h4>Expected side effects</h4><pre>{html.escape(json.dumps(case.expected_side_effects, ensure_ascii=False, indent=2))}</pre>"
            f"<details><summary>Full Candidate JSON</summary><pre>{payload}</pre></details>"
            f"<p><label><input type='radio' name='d-{case.record_id}' value='pass'> Pass</label> "
            f"<label><input type='radio' name='d-{case.record_id}' value='return'> Return</label></p>"
            f"<textarea data-note='{case.record_id}' placeholder='Return reason / notes'></textarea></article>"
        )
    ids = [case.record_id for case in dataset.cases]
    return (
        "<!doctype html><html lang='zh-CN'><meta charset='utf-8'><title>P12 CP-DS6 Pilot review</title>"
        "<style>body{font-family:system-ui;max-width:1200px;margin:auto;padding:24px}article{border:1px solid #bbb;border-radius:8px;padding:18px;margin:16px 0}pre{white-space:pre-wrap}textarea{width:100%;min-height:64px}button{padding:8px 16px}</style>"
        "<h1>P12 CP-DS6 Pilot Candidate review (24 records)</h1>"
        f"<p>Candidate SHA-256: <code>{candidate_sha}</code></p>"
        "<p>Course-agnostic structural fixtures. Review the expected recovery contract before P12 implementation.</p>"
        + "".join(cards)
        + "<p><label>Reviewer <input id='reviewer' value='course_owner'></label></p>"
        + "<button id='export'>Validate and export review JSON</button><script>"
        + f"const ids={json.dumps(ids, ensure_ascii=False)};const sha='{candidate_sha}';"
        + "document.getElementById('export').onclick=()=>{const decisions=[];for(const id of ids){"
        + 'const selected=document.querySelector(`input[name="d-${id}"]:checked`);'
        + "if(!selected){alert('Not reviewed: '+id);return;}const note=document.querySelector(`[data-note=\"${id}\"]`).value.trim();"
        + "if(selected.value==='return'&&!note){alert('Return requires a reason: '+id);return;}decisions.push({record_id:id,decision:selected.value,notes:note});}"
        + "const reviewer=document.getElementById('reviewer').value.trim();if(!reviewer){alert('Enter reviewer id');return;}"
        + "const payload={schema_version:'coursepilot.p12-cp-ds6-review-decisions.v1',candidate_sha256:sha,decisions,reviewer_id:reviewer,reviewed_at:new Date().toISOString()};"
        + "const a=document.createElement('a');a.href=URL.createObjectURL(new Blob([JSON.stringify(payload,null,2)],{type:'application/json'}));a.download=`p12_cp_ds6_review_${sha.slice(0,12)}.json`;a.click();URL.revokeObjectURL(a.href);};</script></html>\n"
    )


def generate(repository_root: Path) -> dict[str, object]:
    root = repository_root.resolve()
    dataset = build_dataset()
    path = root / CANDIDATE_PATH
    atomic_write_json(path, dataset.model_dump(mode="json"))
    sha = hashlib.sha256(path.read_bytes()).hexdigest()
    review_root = root / f"storage_eval/cp_ds6_p12_review/{sha}"
    atomic_write_text(review_root / "index.html", _review_html(dataset, sha))
    report = f"""# ED-PRE12 CP-DS6 Pilot Candidate Review

- Candidate: `{CANDIDATE_PATH.as_posix()}`
- Candidate SHA-256: `{sha}`
- Records: 24 (six interrupt types × four scenarios; four scenario types × six interrupts)
- Fixture: course-agnostic structural cases; no future P12 UUIDs, database rows, model output or CourseRAG content.
- Status: `candidate`; awaiting Course Owner review. No Approved file and no P12 runtime evaluation has been generated.

## Review entry

`storage_eval/cp_ds6_p12_review/{sha}/index.html`

## Review focus

- Every interrupt covers Approve, Edit+Resume, Replan and Reject.
- Edit changes only the listed editable path and creates exactly one new Artifact Version.
- Replan detects stale Context/Index versions and invalidates affected nodes.
- Reject enters `cancelled`, forbids resume, and performs no Export or Writeback.
- Duplicate Decision, duplicate Artifact, Export and Writeback side effects remain zero where expected.
"""
    atomic_write_text(root / REPORT_PATH, report)
    return {
        "candidate_sha256": sha,
        "record_count": len(dataset.cases),
        "review_path": review_root.relative_to(root).as_posix(),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository-root", type=Path, default=Path("."))
    args = parser.parse_args()
    print(json.dumps(generate(args.repository_root), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
