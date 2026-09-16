"""Human-review packages for EP-00 candidate approval and later Dev artifacts."""

from __future__ import annotations

import argparse
import hashlib
import html
import json
from pathlib import Path
from typing import Any

from evaluation.system_optimization.dev_loader import DEFAULT_ROOT, load_candidate
from evaluation.system_optimization.schemas import (
    ArtifactReviewDecision,
    ArtifactType,
    CaseApprovalDecision,
    SystemOptimizationDevCase,
)


def build_review_packages(root: Path = DEFAULT_ROOT) -> dict[str, str]:
    loaded = load_candidate(root)
    review_dir = root / "candidates" / "review"
    review_dir.mkdir(parents=True, exist_ok=True)
    case_package = {
        "schema_version": "system-optimization.case-review-package.v1",
        "instructions": [
            "逐条审核 Task Demand、Evidence Package 和 Candidate Adequacy。",
            "Codex 生成的 Adequacy 只是候选，不得批量或自动批准。",
            "reject/request_changes 必须填写 notes。",
        ],
        "records": [item.model_dump(mode="json") for item in loaded.cases.records],
    }
    case_decisions = {
        "schema_version": "system-optimization.case-review-decisions.v1",
        "dataset_status": "candidate",
        "decisions": [
            CaseApprovalDecision(record_id=item.record_id).model_dump(mode="json")
            for item in loaded.cases.records
        ],
    }
    public, key, decisions = _artifact_review_template(loaded.cases.records)
    paths = {
        "case_package": review_dir / "case_review_package_r2.json",
        "case_decisions": review_dir / "case_review_decisions_r2_template.json",
        "artifact_package": review_dir / "artifact_review_package_r2_template.json",
        "artifact_decisions": review_dir / "artifact_review_decisions_r2_template.json",
        "artifact_key": review_dir / "artifact_review_r2_blinding_key.json",
    }
    _write_json(paths["case_package"], case_package)
    _write_json(paths["case_decisions"], case_decisions)
    _write_json(paths["artifact_package"], public)
    _write_json(paths["artifact_decisions"], decisions)
    _write_json(paths["artifact_key"], key)
    return {name: str(path) for name, path in paths.items()}


def _artifact_review_template(
    cases: list[SystemOptimizationDevCase],
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    repeated: set[str] = set()
    for artifact in ArtifactType:
        candidates = sorted(
            (item for item in cases if item.artifact_type is artifact),
            key=lambda item: _sha(f"ep00-repeat|{item.record_id}"),
        )
        repeated.update(item.record_id for item in candidates[:2])
    assignments: list[dict[str, Any]] = []
    key: list[dict[str, Any]] = []
    decisions: list[dict[str, Any]] = []
    for case in cases:
        copies = 2 if case.record_id in repeated else 1
        repeat_group_id = f"repeat-{_sha(case.record_id)[:16]}" if copies == 2 else None
        for copy_index in range(copies):
            blind_id = f"sysopt-blind-{_sha(f'{case.record_id}|{copy_index}')[:20]}"
            assignments.append(
                {
                    "blind_artifact_id": blind_id,
                    "artifact_type": case.artifact_type.value,
                    "artifact_payload": None,
                    "artifact_status": "awaiting_baseline_artifact",
                }
            )
            key.append(
                {
                    "blind_artifact_id": blind_id,
                    "case_id": case.record_id,
                    "repeat_group_id": repeat_group_id,
                }
            )
            scores = {item.rubric_id: None for item in case.rubric_profile.dimensions}
            decisions.append(
                ArtifactReviewDecision(
                    blind_artifact_id=blind_id,
                    artifact_type=case.artifact_type,
                    repeat_group_id=repeat_group_id,
                    rubric_scores=scores,
                ).model_dump(mode="json")
            )
    return (
        {
            "schema_version": "system-optimization.artifact-review-package.v1",
            "blinded": True,
            "repeat_reviews": 6,
            "review_units": len(assignments),
            "records": assignments,
        },
        {
            "schema_version": "system-optimization.artifact-review-key.v1",
            "records": key,
        },
        {
            "schema_version": "system-optimization.artifact-review-decisions.v1",
            "rubric_score_range": [1, 5],
            "edit_burden_scale": {
                "0": "无需修改",
                "1": "轻微措辞或格式修改",
                "2": "多处局部修改",
                "3": "结构性重写",
                "4": "无法采用",
            },
            "decisions": decisions,
        },
    )


def _case_html(cases: list[SystemOptimizationDevCase], template: dict[str, Any]) -> str:
    cards = "".join(
        f"<section data-id='{html.escape(case.record_id)}'>"
        f"<h2>{html.escape(case.record_id)} · {html.escape(case.title)}</h2>"
        f"<pre>{html.escape(json.dumps(case.model_dump(mode='json'), ensure_ascii=False, indent=2))}</pre>"
        "<label>Decision<select data-field='decision'><option>pending</option>"
        "<option>approve</option><option>reject</option><option>request_changes</option>"
        "</select></label><label>Adequacy Decision<select data-field='adequacy_decision'>"
        "<option value=''>--</option><option>adequate</option>"
        "<option>needs_more_evidence</option><option>unresolvable</option></select></label>"
        "<label>Reviewer ID<input data-field='reviewer_id'></label>"
        "<label>Reviewed At (ISO-8601)<input data-field='reviewed_at'></label>"
        "<label>Notes<textarea data-field='notes'></textarea></label>"
        "</section>"
        for case in cases
    )
    embedded = json.dumps(template, ensure_ascii=False).replace("</", "<\\/")
    return _html_shell(
        "EP-00 Case approval",
        "逐条审核需求、Evidence 和 Candidate Adequacy；页面不执行自动批准。",
        cards,
        embedded,
        "system_optimization_case_review.json",
        """for(const d of data.decisions){const card=document.querySelector(`[data-id="${d.record_id}"]`);for(const field of ['decision','adequacy_decision','reviewer_id','reviewed_at','notes']){const raw=card.querySelector(`[data-field="${field}"]`).value;d[field]=raw===''?null:raw;}if(d.notes===null)d.notes='';}""",
    )


def _artifact_html(package: dict[str, Any], template: dict[str, Any]) -> str:
    decisions = {item["blind_artifact_id"]: item for item in template["decisions"]}
    cards: list[str] = []
    for record in package["records"]:
        decision = decisions[record["blind_artifact_id"]]
        scores = "".join(
            f"<label>{html.escape(rubric_id)}<select data-rubric='{html.escape(rubric_id)}'>"
            "<option value=''>--</option>"
            + "".join(f"<option>{score}</option>" for score in range(1, 6))
            + "</select></label>"
            for rubric_id in decision["rubric_scores"]
        )
        cards.append(
            f"<section data-id='{html.escape(record['blind_artifact_id'])}'>"
            f"<h2>{html.escape(record['blind_artifact_id'])} · {html.escape(record['artifact_type'])}</h2>"
            "<p>Artifact 尚未生成；完成批准和授权后的 Baseline 才会填充此区域。</p>"
            "<label>Status<select data-field='artifact_status'><option>pending</option>"
            "<option>accepted</option><option>minor_edit</option><option>major_edit</option>"
            "<option>reject</option></select></label>"
            "<label>Edit Burden<select data-field='edit_burden'><option value=''>--</option>"
            + "".join(f"<option>{score}</option>" for score in range(5))
            + "</select></label><label>Critical Defect<select data-field='critical_defect'>"
            "<option value=''>--</option><option value='false'>false</option>"
            "<option value='true'>true</option></select></label>"
            f"<div class='rubric'>{scores}</div><label>Reviewer ID "
            "<input data-field='reviewer_id'></label><label>Reviewed At "
            "<input data-field='reviewed_at' type='datetime-local'></label>"
            "<label>Notes<textarea data-field='notes'></textarea></label></section>"
        )
    embedded = json.dumps(template, ensure_ascii=False).replace("</", "<\\/")
    return _html_shell(
        "EP-00 artifact blind review",
        "共 33 个盲审单元，包含 6 个重复盲审；Edit Burden 必须为整数 0—4。",
        "".join(cards),
        embedded,
        "system_optimization_artifact_review.json",
        """for(const d of data.decisions){const card=document.querySelector(`[data-id="${d.blind_artifact_id}"]`);d.artifact_status=card.querySelector('[data-field="artifact_status"]').value;const burden=card.querySelector('[data-field="edit_burden"]').value;d.edit_burden=burden===''?null:Number(burden);const critical=card.querySelector('[data-field="critical_defect"]').value;d.critical_defect=critical===''?null:critical==='true';for(const field of ['reviewer_id','reviewed_at','notes']){const raw=card.querySelector(`[data-field="${field}"]`).value;d[field]=raw===''?null:raw;}if(d.notes===null)d.notes='';for(const el of card.querySelectorAll('[data-rubric]'))d.rubric_scores[el.dataset.rubric]=el.value===''?null:Number(el.value);}""",
    )


def _html_shell(
    title: str,
    instructions: str,
    cards: str,
    embedded: str,
    filename: str,
    collector_js: str,
) -> str:
    return f"""<!doctype html><meta charset='utf-8'><title>{html.escape(title)}</title>
<style>body{{font-family:sans-serif;max-width:1200px;margin:auto;padding:16px}}section{{border:1px solid #bbb;padding:12px;margin:14px 0}}pre{{white-space:pre-wrap;max-height:520px;overflow:auto;background:#f6f6f6;padding:8px}}label{{display:block;margin:8px 0}}.rubric{{display:grid;grid-template-columns:repeat(5,1fr);gap:6px}}textarea{{width:100%;min-height:70px}}button{{padding:10px 16px;position:sticky;bottom:10px}}</style>
<h1>{html.escape(title)}</h1><p>{html.escape(instructions)}</p>{cards}
<button id='download'>下载审核 JSON</button><script>const data={embedded};
document.getElementById('download').onclick=()=>{{{collector_js}const blob=new Blob([JSON.stringify(data,null,2)],{{type:'application/json'}});const url=URL.createObjectURL(blob);const a=document.createElement('a');a.href=url;a.download='{html.escape(filename)}';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}};</script>"""


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    args = parser.parse_args()
    print(json.dumps(build_review_packages(args.root), ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
