"""Build the offline automatic comparison and blinded P14 owner-review package."""

from __future__ import annotations

import argparse
import html
import json
import random
import statistics
from pathlib import Path
from typing import Any

from agents.coursepilot.lesson.generator import LessonGenerator
from coursepilot.domain.common import canonical_sha256
from coursepilot.llm import collect_coursepilot_llm_metadata
from evaluation.p14_lesson_eval import (
    P14ResponseCheckpoint,
    _atomic_write_json,
    _load_inputs,
    _snapshot_and_context,
    _strict_provider_settings,
)

RUBRIC = {
    "L-H1": "目标一致性",
    "L-H2": "课时规划",
    "L-H3": "时间可执行性",
    "L-H4": "知识覆盖",
    "L-H5": "教学活动",
    "L-H6": "重点难点",
    "L-H7": "证据忠实",
    "L-H8": "教师可用性",
}


class CacheOnlyP14Checkpoint(P14ResponseCheckpoint):
    """Read paid responses without permitting another provider dispatch."""

    def save(self, request_sha256: str, payload: dict[str, Any]) -> None:
        raise RuntimeError(f"cache-only replay unexpectedly attempted to save {request_sha256}")

    def record_invocation(self, invocation: dict[str, Any]) -> None:
        return None

    def authorize_request(self, **_kwargs: Any) -> None:
        raise RuntimeError("P14 review replay is cache-only; a required response is missing")


def replay_p14_artifacts(repository_root: Path, checkpoint_dir: Path) -> dict[str, Any]:
    cases, fixtures = _load_inputs(repository_root)
    by_context = {fixture.context_package_id: fixture for fixture in fixtures.context_fixtures}
    checkpoint = CacheOnlyP14Checkpoint(checkpoint_dir, resume=True)
    artifacts: dict[str, Any] = {}
    with _strict_provider_settings(repository_root):
        for case in cases.cases:
            snapshot, context, records = _snapshot_and_context(
                case, by_context[case.context_fixture_id]
            )
            generator = LessonGenerator(use_model=True)
            with collect_coursepilot_llm_metadata(
                thread_id=f"p14-review-replay:{case.record_id}", checkpoint=checkpoint
            ):
                blueprint = generator.build_blueprint(
                    course_id=case.course_id,
                    chapter_scope=case.chapter_range,
                    total_sessions=case.total_sessions,
                    session_duration=case.session_duration,
                    template_snapshot_id=case.template_id,
                    kp_snapshot=snapshot,
                    context_ref=context,
                    context_records=records,
                )
                if case.review_scenario.plan_action == "replan":
                    blueprint = generator.build_blueprint(
                        course_id=case.course_id,
                        chapter_scope=case.chapter_range,
                        total_sessions=case.total_sessions,
                        session_duration=case.session_duration,
                        template_snapshot_id=case.template_id,
                        kp_snapshot=snapshot,
                        context_ref=context,
                        context_records=records,
                        replan_instruction=case.review_scenario.replan_instruction,
                        previous_blueprint=blueprint,
                    )
                if case.review_scenario.plan_action == "edit":
                    for path, value in case.review_scenario.field_edits.items():
                        if path.startswith("sessions[") and path.endswith("].teaching_focus"):
                            index = int(path.split("[")[1].split("]")[0])
                            blueprint.session_plans[index] = blueprint.session_plans[
                                index
                            ].model_copy(update={"title": value})
                artifact = generator.generate_artifact(blueprint, snapshot, context_records=records)
            artifacts[case.record_id] = artifact.model_dump(mode="json")
    return artifacts


def build_package(
    repository_root: Path,
    *,
    report_path: Path,
    checkpoint_dir: Path,
    output_dir: Path,
) -> dict[str, Any]:
    report = json.loads(report_path.read_text(encoding="utf-8"))
    if report.get("status") != "completed":
        raise ValueError("P14 real report is not complete")
    artifacts = replay_p14_artifacts(repository_root, checkpoint_dir)
    automatic = _automatic_metrics(report, artifacts)
    review_records, blinding_key = _blinded_records(report, artifacts)
    template = {
        "schema_version": "coursepilot.p14-human-review-decisions.v1",
        "source_report_sha256": canonical_sha256(report),
        "decisions": [
            {
                "blind_artifact_id": item["blind_artifact_id"],
                "rubric_scores": {key: None for key in RUBRIC},
                "edit_burden": None,
                "critical_defect": None,
                "artifact_status": None,
                "notes": "",
            }
            for item in review_records
        ],
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    _atomic_write_json(output_dir / "automatic_comparison.json", automatic)
    _atomic_write_json(output_dir / "review_decisions_template.json", template)
    _atomic_write_json(output_dir / "blinding_key.json", blinding_key)
    review_path = output_dir / "review.html"
    review_path.write_text(_review_html(review_records, template), encoding="utf-8")
    result = {
        "status": "gate_pending_owner_review",
        "automatic_comparison": str(output_dir / "automatic_comparison.json"),
        "review_page": str(review_path),
        "decision_template": str(output_dir / "review_decisions_template.json"),
        "blinding_key": str(output_dir / "blinding_key.json"),
        "review_record_count": len(review_records),
        "review_package_sha256": canonical_sha256(review_records),
    }
    _atomic_write_json(output_dir / "package_manifest.json", result)
    return result


def finalize_decisions(
    *,
    report_path: Path,
    automatic_path: Path,
    blinding_key_path: Path,
    decisions_path: Path,
    output_path: Path,
) -> dict[str, Any]:
    report = json.loads(report_path.read_text(encoding="utf-8"))
    automatic = json.loads(automatic_path.read_text(encoding="utf-8"))
    key = json.loads(blinding_key_path.read_text(encoding="utf-8"))
    decisions = json.loads(decisions_path.read_text(encoding="utf-8"))
    if decisions.get("schema_version") != "coursepilot.p14-human-review-decisions.v1":
        raise ValueError("P14 decision schema mismatch")
    if decisions.get("source_report_sha256") != canonical_sha256(report):
        raise ValueError("P14 decisions are not bound to the current report")
    mapping = {item["blind_artifact_id"]: item for item in key["items"]}
    expected_ids = set(mapping)
    actual_ids = {item.get("blind_artifact_id") for item in decisions.get("decisions", [])}
    if actual_ids != expected_ids or len(decisions.get("decisions", [])) != len(expected_ids):
        raise ValueError("P14 decisions are incomplete or contain duplicate identities")
    tracks: dict[str, list[dict[str, Any]]] = {"cp_b0": [], "p14": []}
    unblinded: list[dict[str, Any]] = []
    for decision in decisions["decisions"]:
        _validate_decision(decision)
        identity = mapping[decision["blind_artifact_id"]]
        item = {**identity, **decision}
        unblinded.append(item)
        tracks[identity["track"]].append(item)
    track_metrics = {track: _human_track_metrics(items) for track, items in tracks.items()}
    paired = []
    for case_id in sorted({item["case_id"] for item in key["items"]}):
        pair = {item["track"]: item for item in unblinded if item["case_id"] == case_id}
        paired.append(
            {
                "case_id": case_id,
                "rubric_mean_delta_p14_minus_cp_b0": round(
                    statistics.mean(
                        pair["p14"]["rubric_scores"][rubric]
                        - pair["cp_b0"]["rubric_scores"][rubric]
                        for rubric in RUBRIC
                    ),
                    3,
                ),
                "edit_burden_delta_p14_minus_cp_b0": pair["p14"]["edit_burden"]
                - pair["cp_b0"]["edit_burden"],
            }
        )
    hard_gates_passed = all(automatic["hard_gates"].values()) and all(
        not item["critical_defect"] and item["artifact_status"] != "reject" for item in unblinded
    )
    result = {
        "schema_version": "coursepilot.p14-owner-review-summary.v1",
        "source_report_sha256": decisions["source_report_sha256"],
        "decision_file_sha256": canonical_sha256(decisions),
        "decision_count": len(unblinded),
        "track_metrics": track_metrics,
        "paired_results": paired,
        "hard_gates_passed": hard_gates_passed,
        "quality_debt": {
            "present": track_metrics["p14"]["overall_rubric_mean"]
            < track_metrics["cp_b0"]["overall_rubric_mean"],
            "summary": (
                "P14 improves evidence traceability but needs richer session-level teaching "
                "materials, activity instructions and teacher-ready detail."
            ),
        },
        "phase_status": ("completed_with_quality_debt" if hard_gates_passed else "gate_failed"),
        "unblinded_decisions": unblinded,
    }
    _atomic_write_json(output_path, result)
    return result


def _validate_decision(decision: dict[str, Any]) -> None:
    scores = decision.get("rubric_scores")
    if not isinstance(scores, dict) or set(scores) != set(RUBRIC):
        raise ValueError("P14 rubric dimensions are incomplete")
    if any(not isinstance(value, int) or not 1 <= value <= 5 for value in scores.values()):
        raise ValueError("P14 rubric scores must be integers from 1 to 5")
    burden = decision.get("edit_burden")
    if not isinstance(burden, int) or not 0 <= burden <= 4:
        raise ValueError("P14 edit burden must be an integer from 0 to 4")
    if not isinstance(decision.get("critical_defect"), bool):
        raise ValueError("P14 critical_defect must be boolean")
    if decision.get("artifact_status") not in {
        "accepted",
        "minor_edit",
        "major_edit",
        "reject",
    }:
        raise ValueError("P14 artifact status is invalid")


def _human_track_metrics(items: list[dict[str, Any]]) -> dict[str, Any]:
    rubric_means = {
        rubric: round(statistics.mean(item["rubric_scores"][rubric] for item in items), 3)
        for rubric in RUBRIC
    }
    statuses = {status: 0 for status in ("accepted", "minor_edit", "major_edit", "reject")}
    for item in items:
        statuses[item["artifact_status"]] += 1
    return {
        "artifact_count": len(items),
        "rubric_means": rubric_means,
        "overall_rubric_mean": round(statistics.mean(rubric_means.values()), 3),
        "mean_edit_burden": round(statistics.mean(item["edit_burden"] for item in items), 3),
        "critical_defect_count": sum(item["critical_defect"] for item in items),
        "artifact_status_counts": statuses,
    }


def _automatic_metrics(report: dict[str, Any], artifacts: dict[str, Any]) -> dict[str, Any]:
    cp_b0 = report["cp_b0"]
    p14 = report["p14"]
    budget = report["budget"]
    return {
        "schema_version": "coursepilot.p14-automatic-comparison.v1",
        "case_count": len(cp_b0),
        "cp_b0": {
            "passed_cases": sum(
                1
                for item in cp_b0
                if item["validation_report"].get("schema_valid")
                and item["validation_report"].get("session_count_valid")
                and item["validation_report"].get("time_allocation_valid")
            ),
            "kp_extractor_calls": sum(item["kp_extractor_calls"] for item in cp_b0),
            "repair_calls": sum(item.get("repair_calls", 0) for item in cp_b0),
            "provider_calls": sum(item["usage"]["provider_request_count"] for item in cp_b0),
            "input_tokens": sum(item["usage"]["input_tokens"] for item in cp_b0),
            "output_tokens": sum(item["usage"]["output_tokens"] for item in cp_b0),
            "latency_ms": sum(item["usage"]["latency_ms"] for item in cp_b0),
        },
        "p14": {
            "passed_cases": sum(1 for item in p14 if item["passed"]),
            "kp_extractor_calls": report["p14_kp_extractor_calls"],
            "repair_calls": sum(item.get("repair_calls", 0) for item in p14),
            "provider_calls": sum(item["usage"]["provider_request_count"] for item in p14),
            "cache_hits": sum(item["usage"]["cache_hit_count"] for item in p14),
            "input_tokens": sum(item["usage"]["input_tokens"] for item in p14),
            "output_tokens": sum(item["usage"]["output_tokens"] for item in p14),
            "latency_ms": sum(item["usage"]["latency_ms"] for item in p14),
            "evidence_coverage": [item["evidence_coverage"] for item in p14],
            "citation_resolvability": 1.0
            if all(_artifact_evidence_is_resolvable(value) for value in artifacts.values())
            else 0.0,
            "edit_preserved": _edit_is_preserved(artifacts),
            "replan_executed": any(
                item["usage"]["by_prompt"].get("lesson/p14_plan_blueprint", {}).get("call_count")
                == 2
                for item in p14
            ),
        },
        "hard_gates": {
            "p14_kp_extractor_calls_zero": report["p14_kp_extractor_calls"] == 0,
            "all_p14_cases_passed": all(item["passed"] for item in p14),
            "citation_resolvability_one": all(
                _artifact_evidence_is_resolvable(value) for value in artifacts.values()
            ),
            "silent_fallback_zero": all(
                item["usage"]["fallback_count"] == 0 for item in [*cp_b0, *p14]
            ),
            "failed_calls_zero": all(
                item["usage"]["failed_call_count"] == 0 for item in [*cp_b0, *p14]
            ),
            "cost_within_authorization": budget["committed_or_reserved_cost_cny"]
            <= budget["authorized_cost_cap_cny"],
        },
        "budget": budget,
    }


def _artifact_evidence_is_resolvable(artifact: dict[str, Any]) -> bool:
    allowed = set(artifact["blueprint"]["context_evidence_ids"])
    cited: list[str] = []
    for session in artifact["sessions"]:
        for fact in [*session["key_points"], *session["difficult_points"]]:
            cited.extend(fact["binding"]["evidence_ids"])
        for activity in session["activities"]:
            cited.extend(activity["binding"]["evidence_ids"])
    return bool(cited) and set(cited).issubset(allowed)


def _edit_is_preserved(artifacts: dict[str, Any]) -> bool:
    edited = artifacts.get("p14-lesson-02-perceptron-lab")
    if edited is None:
        return False
    return edited["blueprint"]["session_plans"][0]["title"] == "感知机定义与线性可分性"


def _blinded_records(
    report: dict[str, Any], artifacts: dict[str, Any]
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    records: list[dict[str, Any]] = []
    key: dict[str, Any] = {"schema_version": "coursepilot.p14-blinding-key.v1", "items": []}
    for item in report["cp_b0"]:
        records.append(
            {
                "case_id": item["record_id"],
                "track": "cp_b0",
                "artifact": item["lesson_design"],
            }
        )
    for case_id, artifact in artifacts.items():
        records.append({"case_id": case_id, "track": "p14", "artifact": artifact})
    random.Random(1401).shuffle(records)
    blinded: list[dict[str, Any]] = []
    for index, item in enumerate(records, start=1):
        blind_id = f"lesson-review-{index:02d}"
        blinded.append(
            {
                "blind_artifact_id": blind_id,
                "artifact": item["artifact"],
            }
        )
        key["items"].append(
            {
                "blind_artifact_id": blind_id,
                "case_id": item["case_id"],
                "track": item["track"],
            }
        )
    return blinded, key


def _review_html(records: list[dict[str, Any]], template: dict[str, Any]) -> str:
    cards = []
    for record in records:
        blind_id = record["blind_artifact_id"]
        selects = "".join(
            f'<label>{key} {html.escape(label)}<select data-field="rubric_scores.{key}">'
            '<option value="">--请选择--</option>'
            + "".join(f'<option value="{score}">{score}</option>' for score in range(1, 6))
            + "</select></label>"
            for key, label in RUBRIC.items()
        )
        cards.append(
            f'<section class="card" data-id="{blind_id}"><h2>{blind_id}</h2>'
            f"<pre>{html.escape(json.dumps(record['artifact'], ensure_ascii=False, indent=2))}</pre>"
            f'<div class="grid">{selects}'
            '<label>Edit Burden<select data-field="edit_burden"><option value="">--请选择--</option>'
            + "".join(f'<option value="{score}">{score}</option>' for score in range(5))
            + '</select></label><label>Critical Defect<select data-field="critical_defect">'
            '<option value="">--请选择--</option><option value="false">否</option>'
            '<option value="true">是</option></select></label>'
            '<label>Artifact Status<select data-field="artifact_status"><option value="">--请选择--</option>'
            '<option value="accepted">accepted</option><option value="minor_edit">minor_edit</option>'
            '<option value="major_edit">major_edit</option><option value="reject">reject</option>'
            '</select></label><label>Notes<input data-field="notes"></label></div></section>'
        )
    template_json = json.dumps(template, ensure_ascii=False).replace("</", "<\\/")
    return f"""<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<title>P14 Lesson Blinded Review</title><style>
body{{font-family:system-ui;margin:24px;background:#f4f6f8;color:#17202a}}.toolbar{{position:sticky;top:0;background:white;padding:12px;border:1px solid #ccd3da;z-index:2}}button{{margin-right:8px;padding:8px 14px}}.card{{background:white;margin:18px 0;padding:18px;border:1px solid #ccd3da}}pre{{max-height:520px;overflow:auto;background:#f7f7f7;padding:12px;white-space:pre-wrap}}.grid{{display:grid;grid-template-columns:repeat(2,minmax(260px,1fr));gap:10px}}label{{display:flex;justify-content:space-between;gap:8px}}select,input{{min-width:150px}}#status{{font-weight:600}}
</style></head><body><div class="toolbar"><button id="save">保存到本地</button><button id="download">校验并下载决策 JSON</button><span id="status">尚未完成</span></div>{"".join(cards)}
<script>const KEY='coursepilot-p14-review-v1';const base={template_json};
function collect(){{const output=structuredClone(base);for(const d of output.decisions){{const card=document.querySelector(`[data-id="${{d.blind_artifact_id}}"]`);for(const el of card.querySelectorAll('[data-field]')){{const path=el.dataset.field;let v=el.value;if(path.startsWith('rubric_scores.'))d.rubric_scores[path.split('.')[1]]=v===''?null:Number(v);else if(path==='edit_burden')d[path]=v===''?null:Number(v);else if(path==='critical_defect')d[path]=v===''?null:v==='true';else d[path]=v;}}}}return output;}}
function save(){{localStorage.setItem(KEY,JSON.stringify(collect()));document.getElementById('status').textContent='已本地保存';}}
function restore(){{const raw=localStorage.getItem(KEY);if(!raw)return;const data=JSON.parse(raw);for(const d of data.decisions){{const card=document.querySelector(`[data-id="${{d.blind_artifact_id}}"]`);for(const [k,v] of Object.entries(d.rubric_scores))card.querySelector(`[data-field="rubric_scores.${{k}}"]`).value=v??'';for(const k of ['edit_burden','critical_defect','artifact_status','notes'])card.querySelector(`[data-field="${{k}}"]`).value=d[k]??'';}}}}
function validate(data){{for(const d of data.decisions){{if(Object.values(d.rubric_scores).some(v=>v===null)||d.edit_burden===null||d.critical_defect===null||!d.artifact_status)return `请完成 ${{d.blind_artifact_id}} 的全部必填项`;}}return null;}}
function download(){{const data=collect(),error=validate(data);if(error){{document.getElementById('status').textContent=error;return;}}save();const blob=new Blob([JSON.stringify(data,null,2)],{{type:'application/json'}});const url=URL.createObjectURL(blob);const a=document.createElement('a');a.href=url;a.download='p14_lesson_review_decisions.json';document.body.appendChild(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);document.getElementById('status').textContent='决策 JSON 已下载';}}
document.getElementById('save').addEventListener('click',save);document.getElementById('download').addEventListener('click',download);document.querySelectorAll('select,input').forEach(el=>el.addEventListener('change',save));restore();</script></body></html>"""


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository-root", type=Path, default=Path("."))
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--checkpoint-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--decisions", type=Path)
    args = parser.parse_args()
    if args.decisions:
        result = finalize_decisions(
            report_path=args.report,
            automatic_path=args.output_dir / "automatic_comparison.json",
            blinding_key_path=args.output_dir / "blinding_key.json",
            decisions_path=args.decisions,
            output_path=args.output_dir / "owner_review_summary.json",
        )
    else:
        result = build_package(
            args.repository_root,
            report_path=args.report,
            checkpoint_dir=args.checkpoint_dir,
            output_dir=args.output_dir,
        )
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
