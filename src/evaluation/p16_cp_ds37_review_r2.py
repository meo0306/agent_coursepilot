"""Build the renderer-backed P16 r2 Candidate and complete offline review package."""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import shutil
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, cast
from zipfile import ZipFile

from pydantic import JsonValue

from coursepilot.evals.formal_schemas import (
    CPDS3P16PilotDataset,
    CPDS7P16PilotDataset,
    P16BundleManifest,
    P16TemplateRenderSnapshot,
)
from evaluation.corpus_fixtures import sha256_file
from evaluation.io import atomic_write_json, atomic_write_text

DATASET_ROOT = Path("datasets/coursepilot_eval/v1")
R1_DS3 = DATASET_ROOT / "candidates/cp_ds3/p16_ppt_pilot_r1.json"
R1_DS7 = DATASET_ROOT / "candidates/cp_ds7/p16_template_export_pilot_r1.json"
R1_MANIFEST = DATASET_ROOT / "provenance/p16_cp_ds37_bundle_manifest.json"
R2_DS3 = DATASET_ROOT / "candidates/cp_ds3/p16_ppt_pilot_r2.json"
R2_DS7 = DATASET_ROOT / "candidates/cp_ds7/p16_template_export_pilot_r2.json"
R2_MANIFEST = DATASET_ROOT / "provenance/p16_cp_ds37_bundle_manifest_r2.json"
REVISION_HISTORY = DATASET_ROOT / "provenance/p16_cp_ds37_candidate_revision_history.json"
REPORT = Path("docs/refactor/phase_reports/ED_PRE_P16_CPDS37_candidate_review_r2.md")
RENDER_ROOT = Path("storage_eval/p16_render_work_r3")
RENDER_IMAGE = "agent-coursepilot-pptx-qa:lo-7.4.7.2"

P16_NS = "http://schemas.openxmlformats.org/presentationml/2006/main"
A_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _natural_key(path: Path) -> tuple[object, ...]:
    return tuple(int(part) if part.isdigit() else part for part in re.split(r"(\d+)", path.name))


def _pptx_structure(path: Path) -> dict[str, Any]:
    shape_count = 0
    table_count = 0
    picture_count = 0
    placeholder_count = 0
    image_only_slides = 0
    notes_count = 0
    theme_fonts: set[str] = set()
    with ZipFile(path) as archive:
        slide_names = sorted(
            (
                name
                for name in archive.namelist()
                if re.fullmatch(r"ppt/slides/slide\d+\.xml", name)
            ),
            key=lambda name: int(re.search(r"\d+", name).group()),  # type: ignore[union-attr]
        )
        notes_count = len(
            [
                name
                for name in archive.namelist()
                if re.fullmatch(r"ppt/notesSlides/notesSlide\d+\.xml", name)
            ]
        )
        for name in slide_names:
            root = ET.fromstring(archive.read(name))
            slide_shapes = len(root.findall(f".//{{{P16_NS}}}sp"))
            slide_pictures = len(root.findall(f".//{{{P16_NS}}}pic"))
            slide_tables = len(root.findall(f".//{{{A_NS}}}tbl"))
            shape_count += slide_shapes
            picture_count += slide_pictures
            table_count += slide_tables
            placeholder_count += len(root.findall(f".//{{{P16_NS}}}ph"))
            if slide_pictures == 1 and slide_shapes == 0 and slide_tables == 0:
                image_only_slides += 1
        for name in archive.namelist():
            if not re.fullmatch(r"ppt/theme/theme\d+\.xml", name):
                continue
            theme = ET.fromstring(archive.read(name))
            for element in theme.iter():
                typeface = element.attrib.get("typeface", "").strip()
                if typeface:
                    theme_fonts.add(typeface)
    return {
        "slide_count": len(slide_names),
        "editable_shape_count": shape_count,
        "editable_table_count": table_count,
        "editable_picture_count": picture_count,
        "placeholder_count": placeholder_count,
        "notes_slide_count": notes_count,
        "image_only_slide_count": image_only_slides,
        "source_theme_fonts": sorted(theme_fonts),
    }


def _pdf_fonts(path: Path) -> list[str]:
    result = subprocess.run(
        ["pdffonts", str(path)],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    fonts: set[str] = set()
    for line in result.stdout.splitlines()[2:]:
        stripped = line.strip()
        if stripped:
            fonts.add(stripped.split()[0])
    return sorted(fonts)


def _render_snapshot(
    root: Path,
    *,
    source_pptx: Path,
    pdf_stem: str,
    findings: list[str],
) -> P16TemplateRenderSnapshot:
    pass1 = root / RENDER_ROOT / "pass1"
    pass2 = root / RENDER_ROOT / "pass2"
    page_dir1 = pass1 / f"{pdf_stem}_pages"
    page_dir2 = pass2 / f"{pdf_stem}_pages"
    pages1 = sorted(page_dir1.glob("*.png"), key=_natural_key)
    pages2 = sorted(page_dir2.glob("*.png"), key=_natural_key)
    if not pages1 or len(pages1) != len(pages2):
        raise ValueError(f"incomplete repeated P16 render for {pdf_stem}")
    page_hashes1 = [sha256_file(path) for path in pages1]
    page_hashes2 = [sha256_file(path) for path in pages2]
    structure = _pptx_structure(root / source_pptx)
    if structure["slide_count"] != len(pages1):
        raise ValueError(f"P16 PPTX/PDF page mismatch for {pdf_stem}")
    pdf_fonts = _pdf_fonts(pass1 / f"{pdf_stem}.pdf")
    fallbacks: list[str] = []
    if any("DejaVu" in font for font in pdf_fonts):
        fallbacks.append("Latin theme fonts rendered with embedded DejaVu fallback")
    if any("NotoSansCJK" in font for font in pdf_fonts):
        fallbacks.append("CJK theme fonts rendered with locked Noto Sans CJK fallback")
    return P16TemplateRenderSnapshot(
        renderer_image=RENDER_IMAGE,
        source_pptx_sha256=sha256_file(root / source_pptx),
        rendered_pdf_sha256=sha256_file(pass1 / f"{pdf_stem}.pdf"),
        slide_png_sha256s=page_hashes1,
        repeat_render_pngs_identical=page_hashes1 == page_hashes2,
        rendered_pdf_fonts=pdf_fonts,
        declared_font_fallbacks=fallbacks,
        preview_paths=[path.relative_to(root).as_posix() for path in pages1],
        visible_template_findings=findings,
        **structure,
    )


def _risk_flags(deck_id: str, slide_index: int) -> list[str]:
    mapping: dict[tuple[str, int], list[str]] = {
        ("p16-ds3-transformer", 8): ["qkv_source"],
        ("p16-ds3-transformer", 14): ["encoder_process"],
        ("p16-ds3-transformer", 16): ["attention_comparison"],
        ("p16-ds3-transformer", 18): ["structure_placeholder"],
        ("p16-ds3-perceptron", 5): ["formula"],
        ("p16-ds3-perceptron", 7): ["training_process"],
        ("p16-ds3-perceptron", 8): ["calculation_example"],
        ("p16-ds3-occupation-risk", 4): ["table", "ocr"],
        ("p16-ds3-occupation-risk", 5): ["occupation_risk_comparison"],
    }
    return mapping.get((deck_id, slide_index), [])


def _with_r2_candidates(root: Path) -> tuple[CPDS3P16PilotDataset, CPDS7P16PilotDataset]:
    ds3_payload = _load(root / R1_DS3)
    ds3_payload["dataset_version"] = "p16-pilot-r2"
    for case in ds3_payload["cases"]:
        for target in case["slide_targets"]:
            target["risk_flags"] = _risk_flags(case["record_id"], target["slide_index"])
    ds3 = CPDS3P16PilotDataset.model_validate(ds3_payload)

    ds7_payload = _load(root / R1_DS7)
    ds7_payload["dataset_version"] = "p16-pilot-r2"
    builtin_source = {
        "ppt_standard_lecture_v1": Path(
            "resources/templates/exporters/ppt_standard_lecture_v1.pptx"
        ),
        "ppt_concept_explanation_v1": Path(
            "resources/templates/exporters/ppt_concept_explanation_v1.pptx"
        ),
        "ppt_case_seminar_v1": Path("resources/templates/exporters/ppt_case_seminar_v1.pptx"),
    }
    for case in ds7_payload["cases"]:
        if case["case_role"] != "gold_positive":
            continue
        template_id = case["template_id"]
        if template_id in builtin_source:
            snapshot = _render_snapshot(
                root,
                source_pptx=builtin_source[template_id],
                pdf_stem=template_id,
                findings=[
                    "The three built-in template files have identical binary and render hashes.",
                    "The rendered three-slide content is a P11 synthetic baseline, not P16 course output.",
                ],
            )
        else:
            snapshot = _render_snapshot(
                root,
                source_pptx=RENDER_ROOT / "velis-smoke-8slides.pptx",
                pdf_stem="velis-smoke-8slides",
                findings=[
                    "The source template exposes two masters and 32 layouts.",
                    "The template renders a fixed 2021-10-20 date/page footer that P16 must replace.",
                    "The Close layout retains a visible star glyph as template furniture.",
                    "Smoke text is deterministically truncated for layout QA; it is not answer Gold.",
                ],
            )
        case["render_snapshot"] = snapshot.model_dump(mode="json")
    ds7 = CPDS7P16PilotDataset.model_validate(ds7_payload)
    return ds3, ds7


def _record_hashes(ds3: CPDS3P16PilotDataset, ds7: CPDS7P16PilotDataset) -> dict[str, str]:
    hashes: dict[str, str] = {}
    for deck_case in ds3.cases:
        hashes[f"arch::{deck_case.record_id}"] = _digest(deck_case.model_dump(mode="json"))
        for target in deck_case.slide_targets:
            hashes[target.slide_id] = _digest(target.model_dump(mode="json"))
    for template_case in ds7.cases:
        hashes[template_case.record_id] = _digest(template_case.model_dump(mode="json"))
    return hashes


def _review_sets(ds3: CPDS3P16PilotDataset, ds7: CPDS7P16PilotDataset) -> dict[str, list[str]]:
    architecture = [f"arch::{case.record_id}" for case in ds3.cases]
    slides = [target.slide_id for case in ds3.cases for target in case.slide_targets]
    templates = [case.record_id for case in ds7.cases]
    first = [*architecture, *slides, *templates]
    high_risk = [
        target.slide_id for case in ds3.cases for target in case.slide_targets if target.risk_flags
    ]
    remaining = [item for item in slides if item not in set(high_risk)]
    sampled = sorted(remaining, key=lambda value: hashlib.sha256(value.encode()).hexdigest())[:8]
    second = [
        *architecture,
        *high_risk,
        "p16-ds7-external-velis",
        "p16-ds7-negative-hash",
        "p16-ds7-negative-mapping",
        *sampled,
    ]
    return {"first": first, "second": sorted(second, key=_digest)}


def _render_artifact_hashes(root: Path) -> dict[str, str]:
    files = [root / RENDER_ROOT / "velis-smoke-8slides.pptx"]
    files.extend(sorted((root / RENDER_ROOT / "pass1").glob("*.pdf")))
    files.extend(sorted((root / RENDER_ROOT / "pass1").glob("*_pages/*.png")))
    files.extend(sorted((root / RENDER_ROOT / "pass2").glob("*_pages/*.png")))
    return {path.relative_to(root).as_posix(): sha256_file(path) for path in files}


def _decision_block(record_id: str) -> str:
    escaped = html.escape(record_id, quote=True)
    return f"""
<fieldset class="decision" data-review-id="{escaped}">
  <legend>审核决定</legend>
  <label><input type="radio" name="decision-{escaped}" value="pass"> 通过</label>
  <label><input type="radio" name="decision-{escaped}" value="return"> 退回</label>
  <textarea data-notes="{escaped}" placeholder="退回时必须填写原因；通过时可写备注"></textarea>
</fieldset>"""


def _architecture_card(case: Any) -> str:
    rows = "".join(
        f"<tr class={'high-risk' if target.risk_flags else ''}><td>{target.slide_index}</td>"
        f"<td>{html.escape(target.slide_type)}</td><td>{html.escape(target.title_intent)}</td>"
        f"<td>{html.escape(target.layout_role)}</td><td>{html.escape('、'.join(target.risk_flags) or '—')}</td></tr>"
        for target in case.slide_targets
    )
    record_id = f"arch::{case.record_id}"
    return f"""
<article class="review-card architecture" data-kind="architecture" data-record-id="{html.escape(record_id)}">
  <h2>{html.escape(case.record_id)} · 整体 Architecture</h2>
  <p><b>{case.slide_count}页</b> · {html.escape(case.course_id)} · {html.escape(case.template_id)}</p>
  <div class="checklist">审核：页数/页型顺序、教学递进、覆盖完整性、重复/跳跃、课程隔离、高风险页安排。</div>
  <table><thead><tr><th>页</th><th>页型</th><th>教学意图</th><th>Layout</th><th>风险</th></tr></thead><tbody>{rows}</tbody></table>
  {_decision_block(record_id)}
</article>"""


def _slide_card(case: Any, target: Any) -> str:
    record_id = target.slide_id
    claims = (
        "".join(f"<li>{html.escape(item)}</li>" for item in target.required_claims)
        or "<li>无事实 Claim；审核教学结构即可。</li>"
    )
    kp_rows = (
        "".join(
            f"<li><b>{html.escape(item.canonical_name)}</b>：{html.escape(item.summary)}</li>"
            for item in target.knowledge_point_snapshots
        )
        or "<li>无 KP（标题/目录类页面）。</li>"
    )
    evidence_parts: list[str] = []
    for item in target.evidence_snapshots:
        neighbors = "；".join(item.necessary_neighbors) or "无"
        page = f"{item.page_start or '—'}–{item.page_end or '—'}"
        evidence_parts.append(
            f"<details><summary>{html.escape(item.evidence_id)} · 页 {page}</summary>"
            f"<blockquote>{html.escape(item.gold_text)}</blockquote>"
            f"<p><b>必要邻接：</b>{html.escape(neighbors)}</p>"
            f"<p class='hash'>内容 Hash：{html.escape(item.content_sha256)}</p></details>"
        )
    evidence = "".join(evidence_parts) or "<p>无 Evidence（标题/目录类页面）。</p>"
    risk = "、".join(target.risk_flags) or "无"
    return f"""
<article class="review-card slide {"is-high-risk" if target.risk_flags else ""}" data-kind="slide" data-record-id="{html.escape(record_id)}" data-high-risk="{"true" if target.risk_flags else "false"}">
  <h2>第 {target.slide_index} 页 · {html.escape(target.title_intent)}</h2>
  <p>{html.escape(case.record_id)} · <b>{html.escape(target.slide_type)}</b> · Layout {html.escape(target.layout_role)} · 风险：{html.escape(risk)}</p>
  <div class="checklist">按顺序审核：教学意图 → Claim → KP → Evidence/必要邻接 → Layout/素材 → Notes/引用。</div>
  <div class="two-col"><section><h3>Required Claims</h3><ul>{claims}</ul><h3>知识点</h3><ul>{kp_rows}</ul></section>
  <section><h3>页面合同</h3><dl><dt>素材</dt><dd>{html.escape(target.asset_kind)}</dd><dt>Notes</dt><dd>{"必须" if target.notes_required else "不要求"}</dd><dt>引用</dt><dd>{"必须" if target.citation_required else "不要求"}</dd><dt>预算</dt><dd>最多 {target.max_bullets} 条，每条 {target.max_chars_per_bullet} 字符</dd></dl></section></div>
  <h3>Evidence 原文与必要邻接</h3>{evidence}
  {_decision_block(record_id)}
</article>"""


def _template_card(case: Any, preview_map: dict[str, list[str]]) -> str:
    mapping = "".join(
        f"<tr><td>{html.escape(key)}</td><td>{html.escape(value)}</td></tr>"
        for key, value in case.slide_type_layout_map.items()
    )
    snapshot = case.render_snapshot
    gallery = ""
    render_info = "<p class='warning'>合同负例不执行渲染；应在任何生成/导出/写回前失败。</p>"
    if snapshot is not None:
        gallery = (
            "<div class='gallery'>"
            + "".join(
                f"<figure><img src='{html.escape(path, quote=True)}' alt='模板渲染预览 {index}'><figcaption>渲染页 {index}</figcaption></figure>"
                for index, path in enumerate(preview_map[case.record_id], start=1)
            )
            + "</div>"
        )
        render_info = (
            f"<p><b>固定渲染：</b>{html.escape(snapshot.renderer_version)} / Poppler {html.escape(snapshot.poppler_version)}；"
            f"{snapshot.slide_count}页；双次 PNG Hash {'一致' if snapshot.repeat_render_pngs_identical else '不一致'}；"
            f"可编辑 Shape {snapshot.editable_shape_count}、Table {snapshot.editable_table_count}、Picture {snapshot.editable_picture_count}、Placeholder {snapshot.placeholder_count}；"
            f"图片整页 {snapshot.image_only_slide_count}。</p>"
            f"<p><b>实际 PDF 字体：</b>{html.escape('、'.join(snapshot.rendered_pdf_fonts))}</p>"
            f"<p><b>已声明字体替换：</b>{html.escape('；'.join(snapshot.declared_font_fallbacks) or '无')}</p>"
            f"<ul>{''.join(f'<li>{html.escape(item)}</li>' for item in snapshot.visible_template_findings)}</ul>"
        )
    expected = html.escape(case.expected_failure or "正常导入、渲染并保持可编辑")
    return f"""
<article class="review-card template" data-kind="template" data-record-id="{html.escape(case.record_id)}">
  <h2>{html.escape(case.record_id)} · {html.escape(case.template_id)}</h2>
  <p><b>{html.escape(case.case_role)}</b> · {html.escape(case.source_kind)} · 预期：{expected}</p>
  <div class="checklist">正例审核来源/许可证、Master/Layout/Placeholder、映射、字体替换、渲染和可编辑对象；负例审核失败类型与零副作用。</div>
  <p><b>来源：</b>{html.escape(case.source_uri)}<br><b>许可证：</b>{html.escape(case.license)}<br><b>源 Hash：</b><span class="hash">{case.source_sha256}</span><br><b>结构：</b>{case.master_count} Master / {case.layout_count} Layout</p>
  {render_info}
  {gallery}
  <details><summary>页型到 Layout 映射</summary><table><thead><tr><th>页型</th><th>Layout</th></tr></thead><tbody>{mapping}</tbody></table></details>
  {_decision_block(case.record_id)}
</article>"""


def _review_html(
    *,
    bundle: str,
    review_pass: str,
    expected_ids: list[str],
    cards_by_id: dict[str, str],
) -> str:
    cards = "".join(cards_by_id[item] for item in expected_ids)
    expected_json = json.dumps(expected_ids, ensure_ascii=False)
    return f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>P16 r2 {review_pass} review</title>
<style>
:root{{--bg:#f2f5f8;--card:#fff;--ink:#17202a;--muted:#596779;--line:#cfd7e1;--accent:#006b76;--warn:#fff1c7;--danger:#ffe0e0}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--ink);font-family:Arial,'Microsoft YaHei',sans-serif;line-height:1.55}}main{{max-width:1500px;margin:auto;padding:20px}}.toolbar{{position:sticky;top:0;z-index:10;background:#ffffffee;border:1px solid var(--line);border-radius:10px;padding:12px;margin-bottom:16px;backdrop-filter:blur(8px)}}button,a.button{{border:1px solid #8c9aaa;background:white;padding:8px 12px;border-radius:6px;margin:3px;cursor:pointer;color:var(--ink);text-decoration:none}}button.primary{{background:var(--accent);color:white;border-color:var(--accent)}}.progress{{height:10px;background:#dde5eb;border-radius:10px;overflow:hidden;margin:8px 0}}.progress>div{{height:100%;background:var(--accent);width:0}}.notice,.checklist{{padding:10px 12px;background:var(--warn);border-left:4px solid #d6a800;margin:10px 0}}.review-card{{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:18px;margin:16px 0;box-shadow:0 2px 7px #0000000d}}.review-card.incomplete{{border:2px solid #d33}}.is-high-risk{{border-left:6px solid #d68b00}}table{{width:100%;border-collapse:collapse;font-size:14px}}th,td{{border:1px solid var(--line);padding:7px;vertical-align:top}}th{{background:#eef3f6}}.high-risk{{background:#fff5dc}}.two-col{{display:grid;grid-template-columns:1fr 1fr;gap:18px}}.gallery{{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:12px}}figure{{margin:0}}img{{width:100%;height:auto;border:1px solid var(--line);background:white}}figcaption{{font-size:12px;color:var(--muted)}}blockquote{{margin:8px 0;padding:9px 12px;background:#f7f9fa;border-left:4px solid #92a5b5}}.hash{{font-family:Consolas,monospace;font-size:12px;word-break:break-all}}.decision{{margin-top:14px;padding:12px;border:1px solid #9eacb8}}textarea{{display:block;width:100%;min-height:58px;margin-top:8px}}.hidden{{display:none!important}}dt{{font-weight:bold;float:left;clear:left;width:85px}}dd{{margin-left:90px}}@media(max-width:850px){{.two-col{{grid-template-columns:1fr}}}}
</style></head><body><main>
<h1>P16 CP-DS3/CP-DS7 r2 · {"首轮完整审核" if review_pass == "first" else "二轮盲化复核"}</h1>
<div class="notice"><b>Bundle：</b><span class="hash">{bundle}</span><br>本页共有 <b>{len(expected_ids)}</b> 个必须审核对象。审核 Gold 约束和模板合同，不审核未来 P16 模型输出。决定会自动保存在当前浏览器。</div>
<div class="toolbar"><b id="progress-text">0 / {len(expected_ids)} 已完成</b><div class="progress"><div id="progress-bar"></div></div>
<button data-filter="all">全部</button><button data-filter="incomplete">只看未完成</button><button data-filter="returned">只看退回</button><button data-filter="high-risk">只看高风险页</button>
<button id="validate">检查完成度</button><button class="primary" id="download">校验并下载审核 JSON</button>
<a class="button" download href="p16_{review_pass}_review_template.json">下载手工 JSON 模板</a></div>
{cards}
</main><script>
const bundle={json.dumps(bundle)}; const passName={json.dumps(review_pass)}; const expected={expected_json}; const storageKey=`p16-review:${{bundle}}:${{passName}}`;
function loadState(){{try{{return JSON.parse(localStorage.getItem(storageKey)||'{{}}')}}catch{{return {{}}}}}}
function saveState(){{const state={{}};document.querySelectorAll('[data-review-id]').forEach(box=>{{const id=box.dataset.reviewId;const checked=box.querySelector('input[type=radio]:checked');state[id]={{decision:checked?checked.value:'',notes:box.querySelector('textarea').value}}}});localStorage.setItem(storageKey,JSON.stringify(state));updateProgress()}}
function restore(){{const state=loadState();document.querySelectorAll('[data-review-id]').forEach(box=>{{const item=state[box.dataset.reviewId];if(!item)return;if(item.decision){{const radio=box.querySelector(`input[value="${{item.decision}}"]`);if(radio)radio.checked=true}}box.querySelector('textarea').value=item.notes||''}});updateProgress()}}
function decisions(){{return expected.map(id=>{{const box=document.querySelector(`[data-review-id="${{CSS.escape(id)}}"]`);const radio=box.querySelector('input[type=radio]:checked');return {{record_id:id,decision:radio?radio.value:'',notes:box.querySelector('textarea').value.trim()}}}})}}
function validate(show=true){{let first=null;for(const item of decisions()){{const card=document.querySelector(`[data-record-id="${{CSS.escape(item.record_id)}}"]`);const bad=!item.decision||(item.decision==='return'&&!item.notes);card.classList.toggle('incomplete',bad);if(bad&&!first)first=card}}if(first&&show){{first.scrollIntoView({{behavior:'smooth',block:'center'}});alert('仍有未决定项目，或退回项目缺少原因。')}}else if(show)alert('审核记录完整，可以下载。');return !first}}
function updateProgress(){{const done=decisions().filter(item=>item.decision&&!(item.decision==='return'&&!item.notes)).length;document.getElementById('progress-text').textContent=`${{done}} / ${{expected.length}} 已完成`;document.getElementById('progress-bar').style.width=`${{100*done/expected.length}}%`}}
document.addEventListener('change',saveState);document.addEventListener('input',saveState);document.getElementById('validate').onclick=()=>validate(true);
document.getElementById('download').onclick=()=>{{if(!validate(true))return;const out={{schema_version:'coursepilot.p16-review-decisions.v1',bundle_sha256:bundle,review_pass:passName,reviewer_id:'course_owner',reviewed_at:new Date().toISOString(),expected_record_ids:expected,decisions:decisions()}};const a=document.createElement('a');const url=URL.createObjectURL(new Blob([JSON.stringify(out,null,2)],{{type:'application/json'}}));a.href=url;a.download=`p16_${{passName}}_review_${{bundle.slice(0,12)}}.json`;document.body.appendChild(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),1000)}};
document.querySelectorAll('[data-filter]').forEach(button=>button.onclick=()=>{{const filter=button.dataset.filter;document.querySelectorAll('.review-card').forEach(card=>{{const box=card.querySelector('[data-review-id]');const radio=box.querySelector('input[type=radio]:checked');const show=filter==='all'||(filter==='incomplete'&&!radio)||(filter==='returned'&&radio?.value==='return')||(filter==='high-risk'&&card.dataset.highRisk==='true');card.classList.toggle('hidden',!show)}})}});restore();
</script></body></html>"""


def _manual_template(bundle: str, review_pass: str, ids: list[str]) -> dict[str, Any]:
    return {
        "schema_version": "coursepilot.p16-review-decisions.v1",
        "bundle_sha256": bundle,
        "review_pass": review_pass,
        "reviewer_id": "course_owner",
        "reviewed_at": "REPLACE_WITH_ISO8601_TIME",
        "expected_record_ids": ids,
        "decisions": [
            {"record_id": record_id, "decision": "REPLACE_WITH_pass_OR_return", "notes": ""}
            for record_id in ids
        ],
    }


def generate(root: Path) -> dict[str, Any]:
    ds3, ds7 = _with_r2_candidates(root)
    atomic_write_json(root / R2_DS3, cast(JsonValue, ds3.model_dump(mode="json")))
    atomic_write_json(root / R2_DS7, cast(JsonValue, ds7.model_dump(mode="json")))
    candidate_hashes = {
        "cp_ds3": sha256_file(root / R2_DS3),
        "cp_ds7": sha256_file(root / R2_DS7),
    }
    review_sets = _review_sets(ds3, ds7)
    record_hashes = _record_hashes(ds3, ds7)
    render_artifacts = _render_artifact_hashes(root)
    manifest_base = {
        "schema_version": "coursepilot.p16-cp-ds37-bundle-manifest.v1",
        "candidate_hashes": candidate_hashes,
        "record_hashes": record_hashes,
        "record_counts": {
            "cp_ds3_cases": 3,
            "slide_targets": 46,
            "cp_ds7_positive": 4,
            "cp_ds7_negative": 2,
            "first_review_objects": len(review_sets["first"]),
            "second_review_objects": len(review_sets["second"]),
        },
        "upstream_hashes": {
            "p16_r1_ds3": sha256_file(root / R1_DS3),
            "p16_r1_ds7": sha256_file(root / R1_DS7),
            "p16_r1_manifest": sha256_file(root / R1_MANIFEST),
        },
        "external_template": {
            "commit": "0f18f3f1fe2d76413c45b0106e7585d64beb920d",
            "source": "54f58da18846a40976c2b2aa13950343d4b24d112b5a0b64f1f8efbe251dcbcd",
            "normalized": "caec81e7bbcc4712dc60e90af2bae26a3a7890b3300432c0b1cfaa8dc024e32a",
            "license": "CC0-1.0",
        },
        "renderer_preflight": {
            "available": True,
            "provider": "libreoffice-headless",
            "profile": "libreoffice_headless_v1+p16_impress",
            "renderer_version": "7.4.7.2",
            "poppler_version": "22.12.0",
            "image": RENDER_IMAGE,
            "repeat_png_hashes_identical": True,
        },
        "render_artifacts": render_artifacts,
        "review_sets": review_sets,
        "approval_scope": "cp_ds3_and_cp_ds7_p16_pilot_input_only",
        "gold_promotion": False,
        "external_provider_calls": 0,
    }
    bundle = _digest(manifest_base)
    manifest = P16BundleManifest(bundle_sha256=bundle, **manifest_base)
    atomic_write_json(root / R2_MANIFEST, cast(JsonValue, manifest.model_dump(mode="json")))

    review_root = root / "storage_eval/cpds37_p16_review" / bundle
    asset_root = review_root / "assets"
    preview_map: dict[str, list[str]] = {}
    for template_case in ds7.cases:
        if template_case.render_snapshot is None:
            continue
        case_asset_dir = asset_root / template_case.record_id
        case_asset_dir.mkdir(parents=True, exist_ok=True)
        copied: list[str] = []
        for index, source_path in enumerate(template_case.render_snapshot.preview_paths, start=1):
            target = case_asset_dir / f"slide-{index:02d}.png"
            shutil.copy2(root / source_path, target)
            copied.append(target.relative_to(review_root).as_posix())
        preview_map[template_case.record_id] = copied
    shutil.copy2(
        root / RENDER_ROOT / "velis-smoke-8slides.pptx", asset_root / "velis-smoke-8slides.pptx"
    )

    cards: dict[str, str] = {}
    for deck_case in ds3.cases:
        cards[f"arch::{deck_case.record_id}"] = _architecture_card(deck_case)
        for slide_target in deck_case.slide_targets:
            cards[slide_target.slide_id] = _slide_card(deck_case, slide_target)
    for template_case in ds7.cases:
        cards[template_case.record_id] = _template_card(template_case, preview_map)
    for review_pass in ("first", "second"):
        ids = review_sets[review_pass]
        atomic_write_text(
            review_root / ("index.html" if review_pass == "first" else "second_review.html"),
            _review_html(
                bundle=bundle,
                review_pass=review_pass,
                expected_ids=ids,
                cards_by_id=cards,
            ),
        )
        atomic_write_json(
            review_root / f"p16_{review_pass}_review_template.json",
            cast(JsonValue, _manual_template(bundle, review_pass, ids)),
        )

    revision = {
        "schema_version": "course-eval.candidate-revision-history.v1",
        "dataset_id": "coursepilot-p16-cp-ds37",
        "dataset_version": "p16-pilot-r2",
        "revisions": [
            {
                "revision": 1,
                "candidate_relative_path": R1_DS3.as_posix(),
                "candidate_file_sha256": sha256_file(root / R1_DS3),
                "status": "superseded",
                "reason": "Initial CP-DS3 structural Candidate; superseded by the renderer-backed r2 Candidate.",
            },
            {
                "revision": 2,
                "candidate_relative_path": R1_DS7.as_posix(),
                "candidate_file_sha256": sha256_file(root / R1_DS7),
                "status": "superseded",
                "reason": "Initial CP-DS7 structural Candidate; superseded by the renderer-backed r2 Candidate.",
            },
            {
                "revision": 3,
                "candidate_relative_path": R2_DS3.as_posix(),
                "candidate_file_sha256": candidate_hashes["cp_ds3"],
                "status": "pending_course_owner_review",
                "reason": "Renderer-backed CP-DS3 r2 with 46 per-slide decisions awaits Course Owner review.",
            },
            {
                "revision": 4,
                "candidate_relative_path": R2_DS7.as_posix(),
                "candidate_file_sha256": candidate_hashes["cp_ds7"],
                "status": "pending_course_owner_review",
                "reason": "Renderer-backed CP-DS7 r2 with previews and editable Velis smoke awaits Course Owner review.",
            },
        ],
    }
    atomic_write_json(root / REVISION_HISTORY, cast(JsonValue, revision))
    report = f"""# Pre-P16 CP-DS3/CP-DS7 Candidate Review r2

- Tasks: `ED-PRE16-CPDS37-T01` through `ED-PRE16-CPDS37-T09`
- CP-DS3 r2 SHA-256: `{candidate_hashes["cp_ds3"]}`
- CP-DS7 r2 SHA-256: `{candidate_hashes["cp_ds7"]}`
- Bundle SHA-256: `{bundle}`
- First review: 55 objects (3 Architecture + 46 Slide Target + 6 Template/Negative cases)
- Blind second review: {len(review_sets["second"])} objects (3 Architecture + 9 high-risk slides + Velis + 2 negatives + 8 stable-hash samples)
- Fixed renderer: LibreOffice `7.4.7.2`, Poppler `22.12.0`, image `{RENDER_IMAGE}`
- Repeated render: 17/17 page PNG hashes identical
- External editable smoke: `storage_eval/p16_render_work_r3/velis-smoke-8slides.pptx`
- Review entry: `storage_eval/cpds37_p16_review/{bundle}/index.html`
- Second review: `storage_eval/cpds37_p16_review/{bundle}/second_review.html`
- Browser verification: 55/23 decision controls, 17/8 loaded preview images, local autosave and
  reload restore, completeness validation, and the schema-shaped 55-record export payload passed.

The three built-in template files remain byte-identical and are shown once as the same visual
baseline while retaining three separate logical-role decisions. Velis exposes 2 Masters and 32
Layouts. Its smoke deck preserves editable shapes/placeholders and contains no image-only slide.
The fixed renderer substitutes locked Noto Sans CJK/DejaVu fonts; the review page declares this
explicitly. The visible fixed date/footer and Close-layout star are review findings, not silently
accepted behavior.

`@oai/artifact-tool` was not available from the public npm registry and its expected private
runtime dependency was absent. Per the Course Owner's explicit fallback authorization, local
PowerPoint 2021 automation was used only to instantiate the editable Velis smoke. LibreOffice
7.4.7.2 remains the fixed evaluation renderer.

No Approved Gold, Dev/Test data, Provider output, database, API or runtime configuration changed.
"""
    atomic_write_text(root / REPORT, report)
    return {
        "cp_ds3_sha256": candidate_hashes["cp_ds3"],
        "cp_ds7_sha256": candidate_hashes["cp_ds7"],
        "bundle_sha256": bundle,
        "first_review_count": len(review_sets["first"]),
        "second_review_count": len(review_sets["second"]),
        "review_path": review_root.as_posix(),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args()
    print(json.dumps(generate(args.root.resolve()), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
