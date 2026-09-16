"""Blinded P18 human-review package and deterministic score aggregation."""

from __future__ import annotations

import argparse
import hashlib
import html
import json
from pathlib import Path
from typing import Any

from coursepilot.evals.p18_metrics import aggregate_human_reviews


def build_review_package(
    *, artifacts: list[dict[str, Any]], output_dir: Path, seed: str
) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    ordered = sorted(artifacts, key=lambda item: _sha(f"{seed}|{item['case_id']}|{item['track']}"))
    public, key = [], []
    for item in ordered:
        blind_payload = f"{seed}|{item['case_id']}|{item['track']}"
        blind_id = f"p18-blind-{_sha(blind_payload)[:20]}"
        public.append(
            {
                "blind_artifact_id": blind_id,
                "artifact_type": item["artifact_type"],
                "artifact": item["artifact"],
            }
        )
        key.append(
            {"blind_artifact_id": blind_id, "case_id": item["case_id"], "track": item["track"]}
        )
    template = {
        "schema_version": "coursepilot.p18-human-review.v1",
        "decisions": [_decision(x) for x in public],
    }
    (output_dir / "review_package.json").write_text(
        json.dumps(public, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (output_dir / "blinding_key.json").write_text(
        json.dumps(key, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (output_dir / "review_decisions_template.json").write_text(
        json.dumps(template, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (output_dir / "review.html").write_text(_html(public, template), encoding="utf-8")
    return {
        "package": str(output_dir / "review_package.json"),
        "review_html": str(output_dir / "review.html"),
        "decisions": str(output_dir / "review_decisions_template.json"),
    }


def build_from_track_rows(
    *, rows_path: Path, export_report_path: Path, output_dir: Path, seed: str
) -> dict[str, str]:
    rows = json.loads(rows_path.read_text(encoding="utf-8"))
    export_report = json.loads(export_report_path.read_text(encoding="utf-8"))
    rendered = {
        (item["record_id"], item["track"]): item for item in export_report.get("results", [])
    }
    component_types = {"cp_ds1": "lesson", "cp_ds2": "exam", "cp_ds3": "ppt"}
    artifacts: list[dict[str, Any]] = []
    for row in rows:
        export = rendered.get((row["record_id"], row["track"]), {})
        artifacts.append(
            {
                "case_id": row["record_id"],
                "track": row["track"],
                "artifact_type": component_types[row["component"]],
                "artifact": {
                    "generation_status": row["status"],
                    "contract_pass": row["contract_pass"],
                    "citations_resolvable": row["citations_resolvable"],
                    "render": export,
                    "content": row.get("artifact"),
                },
            }
        )
    return build_review_package(artifacts=artifacts, output_dir=output_dir, seed=seed)


def finalize_reviews(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    decisions = payload["decisions"]
    if any(item.get("decision") in {None, "pending"} for item in decisions):
        raise ValueError("P18 human review is incomplete")
    return aggregate_human_reviews(decisions)


def _decision(item: dict[str, Any]) -> dict[str, Any]:
    kind = item["artifact_type"]
    count = 8 if kind == "lesson" else 10
    prefix = {"lesson": "L-H", "exam": "E-H", "ppt": "P-H"}[kind]
    return {
        "blind_artifact_id": item["blind_artifact_id"],
        "artifact_type": kind,
        "decision": "pending",
        "artifact_status": None,
        "rubric_scores": {f"{prefix}{i}": None for i in range(1, count + 1)},
        "edit_burden": None,
        "critical_defect": None,
        "notes": "",
    }


def _html(public: list[dict[str, Any]], template: dict[str, Any]) -> str:
    embedded = json.dumps(template, ensure_ascii=False).replace("</", "<\\/")
    cards = "".join(_card(index, item) for index, item in enumerate(public))
    return f"""<!doctype html><meta charset='utf-8'><title>P18 blind review</title>
<style>body{{font-family:sans-serif;max-width:1180px;margin:auto;padding:16px}}section{{border:1px solid #bbb;padding:14px;margin:16px 0}}pre{{white-space:pre-wrap;max-height:560px;overflow:auto;background:#f6f6f6;padding:10px}}label{{margin-right:12px}}input,select,textarea{{margin:4px}}.rubric{{display:grid;grid-template-columns:repeat(5,minmax(110px,1fr));gap:6px}}button{{padding:10px 16px;position:sticky;bottom:12px}}</style>
<h1>P18 Blinded Review</h1><p>请审核全部 24 份输出；生成失败也必须评分并保留在分母中。页面会自动保存到浏览器本地。</p>{cards}
<button id='download'>下载当前审核 JSON</button>
<script>const initial={embedded};const key='p18-formal-review-v1';let data=JSON.parse(localStorage.getItem(key)||JSON.stringify(initial));
function save(){{localStorage.setItem(key,JSON.stringify(data));}}
function update(i,k,v){{data.decisions[i][k]=v;save();}}
function rubric(i,k,v){{data.decisions[i].rubric_scores[k]=v?Number(v):null;save();}}
document.querySelectorAll('[data-i]').forEach(el=>{{const i=Number(el.dataset.i),k=el.dataset.k,r=el.dataset.r,d=data.decisions[i];const value=r?d.rubric_scores[r]:d[k];if(el.type==='checkbox')el.checked=Boolean(value);else if(value!==null&&value!==undefined)el.value=value;el.onchange=()=>{{if(r)rubric(i,r,el.value);else update(i,k,el.type==='checkbox'?el.checked:(k==='edit_burden'&&el.value!==''?Number(el.value):el.value));}};}});
document.getElementById('download').onclick=()=>{{save();const a=document.createElement('a');const url=URL.createObjectURL(new Blob([JSON.stringify(data,null,2)],{{type:'application/json'}}));a.href=url;a.download='p18_review_decisions.json';document.body.appendChild(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);}};</script>"""


def _card(index: int, item: dict[str, Any]) -> str:
    decision = _decision(item)
    rubric = "".join(
        f"<label>{html.escape(name)} <select data-i='{index}' data-r='{html.escape(name)}'><option value=''>--</option>{''.join(f'<option>{score}</option>' for score in range(1, 6))}</select></label>"
        for name in decision["rubric_scores"]
    )
    artifact = html.escape(json.dumps(item["artifact"], ensure_ascii=False, indent=2))
    return f"""<section><h2>{html.escape(item["blind_artifact_id"])} · {html.escape(item["artifact_type"])}</h2>
<pre>{artifact}</pre><div>
<label>Decision <select data-i='{index}' data-k='decision'><option value='pending'>pending</option><option>accepted</option><option>minor</option><option>major</option><option>reject</option></select></label>
<label>Artifact status <select data-i='{index}' data-k='artifact_status'><option value=''>--</option><option>accepted</option><option>minor_edit</option><option>major_edit</option><option>reject</option></select></label>
<label>Edit burden (0-3) <input data-i='{index}' data-k='edit_burden' type='number' min='0' max='3' step='0.5'></label>
<label>Critical defect <input data-i='{index}' data-k='critical_defect' type='checkbox'></label></div>
<div class='rubric'>{rubric}</div><label>Notes<br><textarea data-i='{index}' data-k='notes' rows='3' cols='100'></textarea></label></section>"""


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rows", type=Path, required=True)
    parser.add_argument("--exports", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--seed", required=True)
    args = parser.parse_args()
    print(
        json.dumps(
            build_from_track_rows(
                rows_path=args.rows,
                export_report_path=args.exports,
                output_dir=args.output_dir,
                seed=args.seed,
            ),
            ensure_ascii=False,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
