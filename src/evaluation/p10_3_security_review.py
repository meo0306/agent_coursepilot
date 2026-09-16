"""Offline two-pass review package for P10.3 Qualification Dev."""

from __future__ import annotations

import argparse
import html
import json
from pathlib import Path

from evaluation.io import atomic_write_text
from evaluation.p10_3_security_data import P103SecurityDevCandidate, sha256_file


def write_review_package(dataset_path: Path, output_path: Path, *, pass_number: int) -> Path:
    if pass_number not in {1, 2}:
        raise ValueError("P10.3 review pass must be 1 or 2")
    dataset = P103SecurityDevCandidate.model_validate_json(dataset_path.read_text(encoding="utf-8"))
    cards = []
    for case in dataset.cases:
        blocks = "".join(f"<pre>{html.escape(text)}</pre>" for text in case.blocks)
        cards.append(
            "<section class='card'>"
            f"<h3>{case.record_id}</h3>"
            f"<p>family={case.family} · language={case.language} · "
            f"construction={case.construction} · expected={case.expected_marked}</p>"
            f"<p>expected_axes={html.escape(', '.join(case.expected_axes))}</p>"
            f"{blocks}"
            f"<label><select data-id='{case.record_id}'>"
            "<option value=''>-- decision --</option>"
            "<option value='pass'>pass</option>"
            "<option value='return'>return</option>"
            "</select></label> "
            f"<input data-note='{case.record_id}' placeholder='note'>"
            "</section>"
        )
    payload = {
        "schema_version": "courserag.p10-3-security-review.v1",
        "dataset_sha256": sha256_file(dataset_path),
        "pass_number": pass_number,
        "reviewer": "course_owner",
    }
    template = """<!doctype html><meta charset='utf-8'>
<title>P10.3 Security Review</title>
<style>body{font-family:system-ui;max-width:1100px;margin:2rem auto}.card{border:1px solid #bbb;padding:1rem;margin:1rem 0}pre{white-space:pre-wrap;background:#f6f6f6;padding:.7rem}input{width:55%}.sticky{position:sticky;top:0;background:white;padding:1rem;border-bottom:2px solid #333}</style>
<div class='sticky'><b>P10.3 Qualification Dev — Review Pass __PASS__</b>
<button id='download'>校验并下载决策 JSON</button><span id='status'></span></div>
__CARDS__
<script>
const identity=__IDENTITY__;
function collectDecisions(){
 const selects=[...document.querySelectorAll('select[data-id]')];
 const missing=selects.filter(x=>!x.value);
 if(missing.length){return {missing,decisions:[]};}
 const decisions=selects.map(x=>({record_id:x.dataset.id,decision:x.value,note:document.querySelector(`[data-note="${x.dataset.id}"]`).value}));
 return {missing:[],decisions};
}
function buildReviewJson(decisions){
 const result={...identity,reviewed_at:new Date().toISOString(),decisions};
 return JSON.stringify(result,null,2)+'\\n';
}
function downloadReviewJson(){
 const collected=collectDecisions();
 if(collected.missing.length){document.getElementById('status').textContent=` 尚有 ${collected.missing.length} 条未审核`;collected.missing[0].scrollIntoView();return;}
 const blob=new Blob([buildReviewJson(collected.decisions)],{type:'application/json'});
 const link=document.createElement('a');link.href=URL.createObjectURL(blob);link.download=`p10_3_review_pass_${identity.pass_number}.json`;document.body.appendChild(link);link.click();setTimeout(()=>{URL.revokeObjectURL(link.href);link.remove()},1000);
 document.getElementById('status').textContent=' 已下载';
}
document.getElementById('download').addEventListener('click',downloadReviewJson);
if(new URLSearchParams(window.location.search).get('export-self-test')==='1'){
 try{
  document.querySelectorAll('select[data-id]').forEach(x=>{x.value='pass'});
  const collected=collectDecisions();
  const blob=new Blob([buildReviewJson(collected.decisions)],{type:'application/json'});
  if(collected.missing.length===0 && collected.decisions.length===120 && blob.size>1000){document.body.textContent='EXPORT_SELF_TEST_PASSED';}
 }catch(error){document.body.textContent='EXPORT_SELF_TEST_FAILED '+String(error);}
}
</script>"""
    rendered = (
        template.replace("__PASS__", str(pass_number))
        .replace("__CARDS__", "\n".join(cards))
        .replace("__IDENTITY__", json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
    )
    atomic_write_text(output_path, rendered)
    return output_path.resolve()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--pass-number", type=int, choices=(1, 2), required=True)
    args = parser.parse_args()
    path = write_review_package(args.dataset, args.output, pass_number=args.pass_number)
    print(json.dumps({"review_package": str(path)}, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
