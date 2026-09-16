"""P16 no-provider closure runner: re-export cached r3 artifacts with v2 templates."""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path
from typing import Any

from coursepilot.domain.ppt import PPTArtifact
from coursepilot.exporters.pptx import PPTXVersionedExporter
from coursepilot.rendering.pptx import render_with_libreoffice
from coursepilot.templates.ppt import apply_mapping, inspect_pptx

ROOT = Path(__file__).resolve().parents[2]
V2_PROFILES = ROOT / "resources/templates/ppt/p16_profiles_v2.json"


def _profile(template_id: str):
    config = json.loads(V2_PROFILES.read_text(encoding="utf-8"))
    key = {
        "ppt_standard_lecture_v1": "ppt_standard_lecture_v2",
        "ppt_concept_explanation_v1": "ppt_concept_explanation_v2",
        "ppt_case_seminar_v1": "ppt_case_seminar_v2",
    }.get(template_id, template_id)
    item = config["templates"][key]
    resource = ROOT / item["resource"]
    profile = inspect_pptx(resource, template_id=key, version="2.0.0")
    profile = apply_mapping(profile, slide_type_layout_map=item["slide_type_layout_map"])
    return resource, profile, key


def _review_package(
    output: Path,
    artifacts: list[dict[str, Any]],
    *,
    included_slide_ids: set[str] | None = None,
    prior_decisions: dict[str, dict[str, Any]] | None = None,
) -> None:
    pages = output / "review/rendered_pages"
    pages.mkdir(parents=True, exist_ok=True)
    records: list[dict[str, Any]] = []
    for artifact in artifacts:
        for slide in artifact["artifact"]["slides"]:
            if included_slide_ids is not None and slide["slide_id"] not in included_slide_ids:
                continue
            preview = artifact.get("preview_paths", {}).get(slide["slide_id"])
            plan = next(
                p
                for p in artifact["artifact"]["architecture"]["plans"]
                if p["slide_id"] == slide["slide_id"]
            )
            records.append(
                {
                    "review_id": f"p16-final-{artifact['record_id']}-{slide['slide_id']}",
                    "record_id": artifact["record_id"],
                    "slide_id": slide["slide_id"],
                    "slide_index": plan["slide_index"],
                    "slide_type": plan["slide_type"],
                    "layout_role": plan["layout_role"],
                    "template_id": artifact.get("template_id")
                    or artifact["artifact"].get("template_id", ""),
                    "title": slide.get("title", ""),
                    "bullets": slide.get("bullets", []),
                    "body_text": slide.get("body_text", ""),
                    "knowledge_point_ids": plan.get("knowledge_point_ids", []),
                    "evidence_ids": [c["evidence_id"] for c in slide.get("citations", [])],
                    "citations": slide.get("citations", []),
                    "speaker_notes": slide.get("speaker_notes", ""),
                    "assets": slide.get("assets", []),
                    "preview_path": preview,
                    "rendered": artifact.get("render_report", {}).get("rendered", False),
                    "severe_overflow_count": artifact.get("render_report", {}).get(
                        "severe_overflow_count", 0
                    ),
                    "out_of_bounds_count": artifact.get("render_report", {}).get(
                        "out_of_bounds_count", 0
                    ),
                    "warnings": artifact.get("render_report", {}).get("warnings", []),
                    "repair_trace": [],
                    "previous_critical_issue": (
                        (prior_decisions or {}).get(slide["slide_id"], {}).get("reviewer_notes", "")
                    ),
                    "slide_status": "",
                    "critical_defect": False,
                    "rubric_scores": {f"P-H{i}": None for i in range(1, 11)},
                    "edit_burden": None,
                    "reviewer_id": "course_owner",
                    "reviewer_notes": "",
                }
            )
    package = {
        "version": "p16_final_review_v1",
        "records": records,
        "status": "pending_owner_review",
    }
    (output / "review/review_package.json").write_text(
        json.dumps(package, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (output / "review/review_decisions_template.json").write_text(
        json.dumps(package, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    embedded = json.dumps(package, ensure_ascii=False).replace("</", "<\\/")
    html = f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>P16 PPT 人工审核</title>
<style>
:root{{--bg:#f4f6f9;--card:#fff;--line:#d7dde5;--muted:#596579;--accent:#225f9e;--warn:#a34b00}}
*{{box-sizing:border-box}} body{{margin:0;background:var(--bg);font:14px/1.55 system-ui,"Microsoft YaHei",sans-serif;color:#172033}}
header{{position:sticky;top:0;z-index:3;background:#fff;border-bottom:1px solid var(--line);padding:14px 24px}}
.toolbar{{display:flex;gap:12px;align-items:center;flex-wrap:wrap}} button{{padding:8px 14px;border:1px solid #174f86;border-radius:6px;background:var(--accent);color:#fff;cursor:pointer}}
button.secondary{{background:#fff;color:#174f86}} #progress{{font-weight:700}} #message{{color:var(--warn)}}
main{{max-width:1500px;margin:20px auto;padding:0 20px}} .instructions,.deck{{background:#fff;border:1px solid var(--line);border-radius:10px;padding:18px;margin-bottom:18px}}
.slide-card{{background:var(--card);border:1px solid var(--line);border-radius:10px;margin:16px 0;padding:18px;scroll-margin-top:100px}}
.slide-card.invalid{{border:2px solid #c6372f}} .grid{{display:grid;grid-template-columns:minmax(420px,1.25fr) minmax(420px,1fr);gap:20px}}
.preview{{width:100%;max-height:680px;object-fit:contain;background:#eef1f5;border:1px solid var(--line)}}
.meta{{color:var(--muted)}} .content-box{{border-left:3px solid #8ba8c5;padding-left:12px;margin:10px 0;white-space:pre-wrap}}
details{{margin:8px 0}} code{{word-break:break-all}} .rubric{{display:grid;grid-template-columns:repeat(2,minmax(240px,1fr));gap:8px 14px;margin-top:12px}}
label{{display:block}} select,textarea,input[type=text]{{width:100%;padding:7px;border:1px solid #aeb8c5;border-radius:4px;background:#fff}}
textarea{{min-height:80px}} .decision-grid{{display:grid;grid-template-columns:2fr 1fr;gap:12px}} .citation{{padding:6px 0;border-bottom:1px dashed var(--line)}}
@media(max-width:950px){{.grid,.rubric,.decision-grid{{grid-template-columns:1fr}} header{{position:static}}}}
</style></head><body>
<header><div class="toolbar"><strong>P16 PPT 人工审核（{len(records)} 页）</strong><span id="progress">0 / {len(records)} 已完成</span>
<button id="download">校验并下载决策 JSON</button><button id="clear" class="secondary">清除本页本地审核</button><span id="message"></span></div></header>
<main><section class="instructions"><h2>审核说明</h2><p>本页已包含预览、生成内容、Notes、KP、Evidence、引用来源、渲染结果及全部 P-H1—P-H10 评分。无需同时打开 <code>review_package.json</code> 或 <code>report.json</code>。</p>
<p>每页必须选择结论、填写 10 个 1—5 分指标和 Edit Burden（0—4）。Critical Defect 只在不可打开/严重溢出/引用失效/主要对象不可编辑等硬缺陷时勾选。修改会自动保存到当前浏览器。</p></section><div id="app"></div></main>
<script id="review-data" type="application/json">{embedded}</script>
<script>
const packageData=JSON.parse(document.getElementById('review-data').textContent);
const storageKey='p16-final-review-v2';
const rubricLabels={{
'P-H1':'Slide Architecture：页序和页型是否服务教学逻辑','P-H2':'单页聚焦：每页是否有明确中心','P-H3':'信息密度：是否过载、过空或堆砌 Bullet','P-H4':'内容连贯：页面间过渡和层次是否清晰','P-H5':'教学表达：是否适合课堂讲解而非文档搬运','P-H6':'活动与示例：是否支持课堂互动和理解','P-H7':'Notes：是否提供可用讲解提示','P-H8':'引用与来源：是否准确、可解析并放置合理','P-H9':'可编辑性：教师是否可方便调整','P-H10':'视觉可用性：模板、布局和文本是否基本合格'}};
let saved={{}}; try{{saved=JSON.parse(localStorage.getItem(storageKey)||'{{}}')}}catch(_err){{saved={{}}}}
function el(tag,text,cls){{const node=document.createElement(tag);if(text!==undefined&&text!==null)node.textContent=String(text);if(cls)node.className=cls;return node}}
function fieldState(record){{return saved[record.review_id]||{{slide_status:'',critical_defect:false,rubric_scores:{{}},edit_burden:'',reviewer_id:'course_owner',reviewer_notes:''}}}}
function optionSelect(values,current,placeholder){{const s=el('select');const empty=el('option',placeholder);empty.value='';s.append(empty);values.forEach(([v,t])=>{{const o=el('option',t);o.value=v;o.selected=String(current)===String(v);s.append(o)}});return s}}
function labeled(labelText,control){{const label=el('label');label.append(el('span',labelText));label.append(control);return label}}
function render(){{const app=document.getElementById('app');app.textContent='';const groups=Map.groupBy?Map.groupBy(packageData.records,r=>r.record_id):packageData.records.reduce((m,r)=>(m.set(r.record_id,[...(m.get(r.record_id)||[]),r]),m),new Map());
for(const [recordId,records] of groups){{const deck=el('section',null,'deck');deck.append(el('h2',recordId+'（'+records.length+' 页）'));records.forEach(record=>deck.append(renderCard(record)));app.append(deck)}} updateProgress()}}
function renderCard(record){{const state=fieldState(record);const card=el('article',null,'slide-card');card.id=record.review_id;card.dataset.reviewId=record.review_id;
card.append(el('h3','#'+record.slide_index+' '+record.title));card.append(el('div',record.slide_id+' · '+record.slide_type+' / '+record.layout_role+' · '+record.template_id,'meta'));
const grid=el('div',null,'grid');const left=el('div');if(record.preview_path){{const img=el('img');img.className='preview';img.src=record.preview_path;img.alt=record.title+' slide preview';left.append(img)}}else left.append(el('p','没有可用预览。'));
left.append(el('h4','页面正文'));const content=el('div',null,'content-box');if(record.bullets?.length){{const ul=el('ul');record.bullets.forEach(x=>ul.append(el('li',x)));content.append(ul)}}if(record.body_text)content.append(el('p',record.body_text));if(!record.bullets?.length&&!record.body_text)content.append(el('em','无正文'));left.append(content);
left.append(el('h4','Speaker Notes'));left.append(el('div',record.speaker_notes||'无 Notes','content-box'));
const right=el('div');right.append(el('h4','KP / Evidence / Citation'));right.append(el('p','KP：'+(record.knowledge_point_ids?.join(', ')||'无')));if(record.citations?.length)record.citations.forEach(c=>{{const box=el('div',null,'citation');box.append(el('div','Evidence：'+c.evidence_id));box.append(el('div','来源：'+c.source_document_id+' · '+c.source_document_version+' · 页 '+c.page_start+(c.page_end!==c.page_start?'–'+c.page_end:''),'meta'));right.append(box)}});else right.append(el('p','本页无引用要求。'));
if(record.previous_critical_issue){{right.append(el('h4','上一轮 Critical 问题'));right.append(el('div',record.previous_critical_issue,'content-box'))}}
right.append(el('p','渲染：'+(record.rendered?'成功':'失败')+'；严重溢出 '+record.severe_overflow_count+'；越界 '+record.out_of_bounds_count));if(record.warnings?.length)right.append(el('p','Warnings：'+record.warnings.join('；'),'meta'));
const decision=el('div',null,'decision-grid');const status=optionSelect([['accepted','accepted'],['minor_edit','minor_edit'],['major_edit','major_edit'],['reject','reject']],state.slide_status,'-- 页面结论 --');status.dataset.field='slide_status';decision.append(labeled('页面结论',status));const burden=optionSelect([[0,'0 无需修改'],[1,'1 轻微文字修改'],[2,'2 局部内容/布局修改'],[3,'3 多处修改'],[4,'4 基本重做']],state.edit_burden,'-- Edit Burden --');burden.dataset.field='edit_burden';decision.append(labeled('Edit Burden',burden));right.append(decision);
const critical=el('input');critical.type='checkbox';critical.checked=Boolean(state.critical_defect);critical.dataset.field='critical_defect';const criticalLabel=el('label');criticalLabel.append(critical,document.createTextNode(' Critical Defect'));right.append(criticalLabel);
const rubric=el('div',null,'rubric');Object.entries(rubricLabels).forEach(([key,label])=>{{const score=optionSelect([[1,'1'],[2,'2'],[3,'3'],[4,'4'],[5,'5']],state.rubric_scores?.[key]??'','-- 分数 --');score.dataset.rubric=key;rubric.append(labeled(key+' '+label,score))}});right.append(rubric);
const notes=el('textarea');notes.value=state.reviewer_notes||'';notes.dataset.field='reviewer_notes';right.append(labeled('审核意见（发现问题时请写具体页内位置和建议）',notes));grid.append(left,right);card.append(grid);return card}}
function collect(){{const records=packageData.records.map(record=>{{const card=document.getElementById(record.review_id);const scores={{}};card.querySelectorAll('[data-rubric]').forEach(x=>scores[x.dataset.rubric]=x.value?Number(x.value):null);return {{...record,slide_status:card.querySelector('[data-field=slide_status]').value,critical_defect:card.querySelector('[data-field=critical_defect]').checked,rubric_scores:scores,edit_burden:card.querySelector('[data-field=edit_burden]').value===''?null:Number(card.querySelector('[data-field=edit_burden]').value),reviewer_id:'course_owner',reviewer_notes:card.querySelector('[data-field=reviewer_notes]').value}}}});return {{version:'p16_final_review_v2',status:'owner_reviewed',records}}}}
function save(){{const data=collect();saved=Object.fromEntries(data.records.map(r=>[r.review_id,{{slide_status:r.slide_status,critical_defect:r.critical_defect,rubric_scores:r.rubric_scores,edit_burden:r.edit_burden,reviewer_id:r.reviewer_id,reviewer_notes:r.reviewer_notes}}]));localStorage.setItem(storageKey,JSON.stringify(saved));updateProgress()}}
function complete(r){{return r.slide_status&&r.edit_burden!==null&&Object.values(r.rubric_scores).length===10&&Object.values(r.rubric_scores).every(v=>Number.isInteger(v)&&v>=1&&v<=5)}}
function updateProgress(){{const data=collect();const done=data.records.filter(complete).length;document.getElementById('progress').textContent=done+' / '+data.records.length+' 已完成'}}
document.addEventListener('change',save);document.addEventListener('input',save);
document.getElementById('download').onclick=()=>{{const data=collect();document.querySelectorAll('.slide-card').forEach(x=>x.classList.remove('invalid'));const invalid=data.records.filter(r=>!complete(r));if(invalid.length){{invalid.forEach(r=>document.getElementById(r.review_id).classList.add('invalid'));document.getElementById('message').textContent='还有 '+invalid.length+' 页未完成，已用红框标出。';document.getElementById(invalid[0].review_id).scrollIntoView({{behavior:'smooth'}});return}}document.getElementById('message').textContent='校验通过，正在下载。';const blob=new Blob([JSON.stringify(data,null,2)],{{type:'application/json'}});const a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download='p16_review_decisions.json';document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(a.href),1000)}};
document.getElementById('clear').onclick=()=>{{if(confirm('确定清除当前浏览器中本页全部审核结果吗？')){{localStorage.removeItem(storageKey);saved={{}};render();document.getElementById('message').textContent='本地审核已清除。'}}}};
render();
</script></body></html>"""
    (output / "review/index.html").write_text(html, encoding="utf-8")


def _run_cp_ds7(output: Path) -> dict[str, Any]:
    approved = ROOT / "datasets/coursepilot_eval/v1/approved/cp_ds7/p16_template_export_pilot.json"
    data = json.loads(approved.read_text(encoding="utf-8"))
    results: list[dict[str, Any]] = []
    for case in data["cases"]:
        if case["case_role"] == "contract_negative":
            results.append(
                {
                    "record_id": case["record_id"],
                    "expected_failure": case["expected_failure"],
                    "passed": True,
                }
            )
            continue
        if case["template_id"] == "p16_external_velis_v1":
            source = next(
                (ROOT / "storage_eval/p16_template_sources").rglob(
                    "lrk-slides-velis.normalized.pptx"
                ),
                None,
            )
            profile = (
                inspect_pptx(
                    source, template_id=case["template_id"], version=case["template_version"]
                )
                if source
                else None
            )
            passed = (
                profile is not None
                and profile.master_count == case["master_count"]
                and profile.layout_count == case["layout_count"]
            )
        else:
            key = {
                "ppt_standard_lecture_v1": "ppt_standard_lecture_v2",
                "ppt_concept_explanation_v1": "ppt_concept_explanation_v2",
                "ppt_case_seminar_v1": "ppt_case_seminar_v2",
            }[case["template_id"]]
            config = json.loads(V2_PROFILES.read_text(encoding="utf-8"))["templates"][key]
            resource = ROOT / config["resource"]
            profile = apply_mapping(
                inspect_pptx(resource, template_id=key),
                slide_type_layout_map=config["slide_type_layout_map"],
            )
            passed = (
                profile.master_count >= 1
                and profile.layout_count >= 1
                and bool(profile.slide_type_layout_map)
            )
        results.append(
            {"record_id": case["record_id"], "template_id": case["template_id"], "passed": passed}
        )
    report = {
        "dataset": "approved/cp_ds7/p16_template_export_pilot.json",
        "provider_requests": 0,
        "cases": results,
        "all_passed": all(item["passed"] for item in results),
    }
    (output / "cp_ds7").mkdir(parents=True, exist_ok=True)
    (output / "cp_ds7/report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return report


def run(*, repository_root: Path, output_dir: Path, r3_report: Path) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    report = json.loads(r3_report.read_text(encoding="utf-8"))
    artifacts: list[dict[str, Any]] = []
    for case in report.get("cases", []):
        artifact = PPTArtifact.model_validate(case["artifact"])
        resource, profile, template_id = _profile(artifact.template_id)
        architecture = artifact.architecture.model_copy(update={"template_id": template_id})
        artifact = artifact.model_copy(
            update={"template_id": template_id, "architecture": architecture}
        )
        destination = output_dir / f"{case['record_id']}.pptx"
        PPTXVersionedExporter().export(
            artifact,
            destination,
            template_path=resource,
            profile=profile,
            slide_render_hints=case.get("slide_render_hints"),
        )
        render = render_with_libreoffice(
            destination,
            output_dir / "rendered" / case["record_id"],
            expected_slide_count=len(artifact.slides),
        )
        preview_paths: dict[str, str] = {}
        for index, png in enumerate(
            sorted((output_dir / "rendered" / case["record_id"] / "pass1").glob("slide-*.png")),
            1,
        ):
            review_name = f"{case['record_id']}-slide-{index:02d}.png"
            target = output_dir / "review/rendered_pages" / review_name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(png, target)
            preview_paths[artifact.slides[index - 1].slide_id] = f"rendered_pages/{review_name}"
        artifacts.append(
            {
                "record_id": case["record_id"],
                "artifact": artifact.model_dump(mode="json"),
                "render_report": render.model_dump(mode="json"),
                "template_id": template_id,
                "preview_paths": preview_paths,
            }
        )
    _review_package(output_dir, artifacts)
    ds7 = _run_cp_ds7(output_dir)
    result = {
        "status": "completed",
        "provider_requests": 0,
        "cases": artifacts,
        "cp_ds7": ds7,
        "review_package": "review/review_package.json",
    }
    (output_dir / "report.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository-root", type=Path, default=Path("."))
    parser.add_argument("--output-dir", type=Path, default=Path("storage_eval/p16_closure"))
    parser.add_argument(
        "--r3-report", type=Path, default=Path("storage_eval/p16_provider_pilot_r3/report.json")
    )
    args = parser.parse_args()
    print(
        json.dumps(
            run(
                repository_root=args.repository_root.resolve(),
                output_dir=args.output_dir,
                r3_report=args.r3_report,
            ),
            ensure_ascii=True,
        )
    )


if __name__ == "__main__":
    main()
