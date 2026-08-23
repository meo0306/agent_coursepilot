"""Build the deterministic P16 CP-DS3/CP-DS7 Pilot input bundle.

The bundle is an independently authored architecture contract.  It consumes the
owner-reviewed P14 lesson snapshots and Approved CourseRAG records, but never
uses a P16 runtime result or a Provider response to create Gold.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import re
import urllib.request
from pathlib import Path
from typing import Any, cast
from zipfile import ZIP_STORED, ZipFile, ZipInfo

from pydantic import JsonValue

from coursepilot.evals.formal_schemas import (
    CPDS3P16PilotDataset,
    CPDS7P16PilotDataset,
    P16BundleManifest,
    P16EvidenceSnapshot,
    P16KnowledgePointSnapshot,
    P16PPTPilotCase,
    P16SlideTargetGold,
    P16TemplateImportCase,
)
from evaluation.corpus_fixtures import sha256_file
from evaluation.io import atomic_write_bytes, atomic_write_json, atomic_write_text

ROOT = Path("datasets/coursepilot_eval/v1")
DS2_PATH = Path("datasets/courserag_eval/v1/approved/ds2/p06_evidence.json")
DS3_PATH = Path("datasets/courserag_eval/v1/approved/ds3/p07_knowledge_points.json")
DS3_SPLIT_PATH = Path("datasets/courserag_eval/v1/provenance/ds3_p07_split.json")
P14_PATH = ROOT / "approved/cp_ds1/p14_lesson_pilot.json"
P14_REVIEW = Path("storage_eval/p14_closure/review/review.html")
DS3_CANDIDATE = ROOT / "candidates/cp_ds3/p16_ppt_pilot_r1.json"
DS7_CANDIDATE = ROOT / "candidates/cp_ds7/p16_template_export_pilot_r1.json"
MANIFEST_PATH = ROOT / "provenance/p16_cp_ds37_bundle_manifest.json"
REPORT_PATH = Path("docs/refactor/phase_reports/ED_PRE_P16_CPDS37_candidate_review.md")
EXTERNAL_COMMIT = "0f18f3f1fe2d76413c45b0106e7585d64beb920d"
EXTERNAL_URL = (
    f"https://raw.githubusercontent.com/lrkrol/powerpoint/{EXTERNAL_COMMIT}/lrk-slides-velis.potx"
)
EXTERNAL_NAME = "lrk-slides-velis.potx"
EXTERNAL_SHA = "54f58da18846a40976c2b2aa13950343d4b24d112b5a0b64f1f8efbe251dcbcd"


def _digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _record_sha(item: dict[str, Any]) -> str:
    approval = item.get("approval", {})
    value = approval.get("approved_record_sha256")
    if not isinstance(value, str):
        raise ValueError(f"upstream record has no approved hash: {item.get('record_id')}")
    return value


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _p14_artifacts() -> dict[str, tuple[dict[str, Any], str]]:
    if not P14_REVIEW.is_file():
        raise FileNotFoundError(f"owner-reviewed P14 artifact review is missing: {P14_REVIEW}")
    source = html.unescape(P14_REVIEW.read_text(encoding="utf-8"))
    result: dict[str, tuple[dict[str, Any], str]] = {}
    for match in re.finditer(
        r'<section class="card" data-id="([^"]+)">.*?<pre>(.*?)</pre>', source, re.S
    ):
        review_id, raw = match.groups()
        if review_id not in {"lesson-review-02", "lesson-review-05", "lesson-review-06"}:
            continue
        artifact = json.loads(raw)
        if "chapter_scope" not in artifact:
            continue
        record_id = {
            "lesson-review-05": "p14-lesson-01-transformer",
            "lesson-review-02": "p14-lesson-02-perceptron-lab",
            "lesson-review-06": "p14-lesson-03-occupation-risk-seminar",
        }[review_id]
        result[record_id] = (artifact, _digest(artifact))
    if set(result) != {
        "p14-lesson-01-transformer",
        "p14-lesson-02-perceptron-lab",
        "p14-lesson-03-occupation-risk-seminar",
    }:
        raise ValueError("P14 owner-reviewed final artifact snapshots are incomplete")
    return result


def _evidence_snapshot(item: dict[str, Any]) -> P16EvidenceSnapshot:
    span = item["source_span"]
    return P16EvidenceSnapshot(
        evidence_id=item["evidence_id"],
        record_sha256=_record_sha(item),
        course_id=item["course_id"],
        gold_text=item["gold_text"],
        necessary_neighbors=[str(x["text"]) for x in item.get("necessary_neighbors", [])],
        source_document_id=span["document_id"],
        source_document_version=span["document_version"],
        page_start=span.get("page_start"),
        page_end=span.get("page_end"),
        source_type=item["source_type"],
        content_sha256=item["content_sha256"],
    )


def _kp_snapshot(item: dict[str, Any]) -> P16KnowledgePointSnapshot:
    return P16KnowledgePointSnapshot(
        gold_kp_id=item["gold_kp_id"],
        record_sha256=_record_sha(item),
        course_id=item["course_id"],
        canonical_name=item["canonical_name"],
        summary=item["summary"],
        importance=item["importance"],
        evidence_ids=list(item["evidence_ids"]),
    )


def _slide_targets(
    case: dict[str, Any],
    evidence: dict[str, dict[str, Any]],
    kps: dict[str, dict[str, Any]],
    sequence: list[str],
    kp_groups: list[list[int]],
    intents: list[str],
    assets: dict[int, str],
) -> list[P16SlideTargetGold]:
    kp_ids = list(case["required_knowledge_point_ids"])
    targets: list[P16SlideTargetGold] = []
    for index, slide_type in enumerate(sequence, 1):
        indexes = kp_groups[index - 1]
        selected_kp_ids = [kp_ids[i] for i in indexes]
        selected_evidence_ids: list[str] = []
        for kp_id in selected_kp_ids:
            for evidence_id in kps[kp_id]["evidence_ids"]:
                if evidence_id not in selected_evidence_ids:
                    selected_evidence_ids.append(evidence_id)
                break
        if slide_type in {"title", "agenda"}:
            selected_kp_ids = []
            selected_evidence_ids = []
        evidence_items = [evidence[item] for item in selected_evidence_ids]
        layout = {
            "title": "title",
            "agenda": "title_content",
            "objectives": "title_content",
            "concept": "title_content",
            "process": "two_content",
            "comparison": "comparison",
            "example": "picture_caption" if index in assets else "title_content",
            "activity": "title_content",
            "summary": "title_content",
            "references": "title_content",
        }[slide_type]
        claims = [item["gold_text"] for item in evidence_items[:2]]
        targets.append(
            P16SlideTargetGold(
                slide_id=f"{case['record_id']}-slide-{index:02d}",
                slide_index=index,
                slide_type=slide_type,
                title_intent=intents[index - 1],
                source_session_index=1
                if index <= max(2, case["total_sessions"])
                else min(2, case["total_sessions"]),
                knowledge_point_ids=selected_kp_ids,
                evidence_ids=selected_evidence_ids,
                required_claims=claims,
                layout_role=layout,
                max_bullets=4 if slide_type not in {"title", "references"} else 2,
                max_chars_per_bullet=72 if slide_type != "references" else 120,
                notes_required=slide_type not in {"title", "references"},
                citation_required=slide_type not in {"title", "agenda"},
                asset_kind=assets.get(index, "none"),
                evidence_snapshots=[_evidence_snapshot(item) for item in evidence_items],
                knowledge_point_snapshots=[_kp_snapshot(kps[item]) for item in selected_kp_ids],
            )
        )
    return targets


def _case(
    root: Path,
    source: dict[str, Any],
    artifact: tuple[dict[str, Any], str],
    evidence: dict[str, dict[str, Any]],
    kps: dict[str, dict[str, Any]],
    sequence: list[str],
    kp_groups: list[list[int]],
    intents: list[str],
    assets: dict[int, str],
    template_id: str,
) -> P16PPTPilotCase:
    targets = _slide_targets(source, evidence, kps, sequence, kp_groups, intents, assets)
    record_id = {
        "ppt_standard_lecture_v1": "p16-ds3-transformer",
        "ppt_concept_explanation_v1": "p16-ds3-perceptron",
        "ppt_case_seminar_v1": "p16-ds3-occupation-risk",
    }[template_id]
    return P16PPTPilotCase(
        record_id=record_id,
        course_id=source["course_id"],
        template_id=template_id,
        lesson_artifact_id=source["record_id"],
        lesson_artifact_sha256=artifact[1],
        slide_count=len(targets),
        required_slide_types=sorted({item.slide_type for item in targets}),
        slide_targets=targets,
        required_interrupts=["ppt_architecture_review", "ppt_final_review"],
        source_provenance=[
            f"approved/cp_ds1/p14_lesson_pilot.json:{sha256_file(root / P14_PATH)}",
            f"storage_eval/p14_closure/review/review.html:{sha256_file(root / P14_REVIEW)}",
        ],
        forbidden_claims=list(source.get("forbidden_claims", [])),
    )


def _template_structure(path: Path) -> tuple[int, int]:
    with ZipFile(path) as archive:
        masters = len(
            [
                x
                for x in archive.namelist()
                if re.fullmatch(r"ppt/slideMasters/slideMaster\d+\.xml", x)
            ]
        )
        layouts = len(
            [
                x
                for x in archive.namelist()
                if re.fullmatch(r"ppt/slideLayouts/slideLayout\d+\.xml", x)
            ]
        )
    return masters, layouts


def _normalize_potx(source: bytes) -> bytes:
    """Convert the package content type to a presentation without changing XML."""
    result: dict[str, bytes] = {}
    with __import__("io").BytesIO(source) as buffer, ZipFile(buffer) as archive:
        for name in archive.namelist():
            value = archive.read(name)
            if name == "[Content_Types].xml":
                value = value.replace(
                    b"presentationml.template.main+xml", b"presentationml.presentation.main+xml"
                )
            result[name] = value
    output = __import__("io").BytesIO()
    with ZipFile(output, "w", compression=ZIP_STORED) as archive:
        for name in sorted(result):
            info = ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = ZIP_STORED
            archive.writestr(info, result[name])
    return output.getvalue()


def _external_template(root: Path) -> tuple[P16TemplateImportCase, dict[str, str]]:
    source_dir = root / "storage_eval/p16_template_sources" / EXTERNAL_COMMIT
    source_path = source_dir / EXTERNAL_NAME
    source_dir.mkdir(parents=True, exist_ok=True)
    if not source_path.is_file():
        temp_path = (
            Path(os.environ.get("TEMP", "")) / "coursepilot_p16_template_inspect" / EXTERNAL_NAME
        )
        if temp_path.is_file():
            source_path.write_bytes(temp_path.read_bytes())
        else:
            with urllib.request.urlopen(EXTERNAL_URL, timeout=30) as response:
                source_path.write_bytes(response.read())
    source_hash = sha256_file(source_path)
    if source_hash != EXTERNAL_SHA:
        raise ValueError(f"external template hash mismatch: {source_hash}")
    normalized = _normalize_potx(source_path.read_bytes())
    normalized_path = source_dir / "lrk-slides-velis.normalized.pptx"
    atomic_write_bytes(normalized_path, normalized)
    normalized_hash = sha256_file(normalized_path)
    masters, layouts = _template_structure(source_path)
    mapping = {
        "title": "Presentation Title",
        "agenda": "Title and Content",
        "objectives": "Title and Content",
        "concept": "Title and Content",
        "process": "Two Columns",
        "comparison": "Two Columns",
        "example": "Two Columns, Picture Right",
        "activity": "Title and Content",
        "summary": "Close",
        "references": "Title and Content",
    }
    case = P16TemplateImportCase(
        record_id="p16-ds7-external-velis",
        case_role="gold_positive",
        template_id="p16_external_velis_v1",
        template_version=f"{EXTERNAL_COMMIT[:12]}-cc0",
        custom_template=True,
        source_kind="owner_selected_external",
        source_uri=EXTERNAL_URL,
        source_sha256=source_hash,
        normalized_pptx_sha256=normalized_hash,
        license="CC0-1.0",
        master_count=masters,
        layout_count=layouts,
        required_layout_roles=[
            "Presentation Title",
            "Title and Content",
            "Two Columns",
            "Two Columns, Picture Right",
            "Close",
        ],
        slide_type_layout_map=mapping,
        required_placeholders=["title", "body", "picture", "slide_number"],
        expected_file_roles=["master", "layout", "theme", "font_mapping"],
        source_provenance=[f"github:{EXTERNAL_COMMIT}", f"source_sha256:{source_hash}"],
    )
    return case, {"source": source_hash, "normalized": normalized_hash}


def _builtin_cases(root: Path) -> list[P16TemplateImportCase]:
    roles = [
        ("ppt_standard_lecture_v1", "ppt_standard_lecture_pptx"),
        ("ppt_concept_explanation_v1", "ppt_concept_explanation_pptx"),
        ("ppt_case_seminar_v1", "ppt_case_seminar_pptx"),
    ]
    result: list[P16TemplateImportCase] = []
    for template_id, role in roles:
        path = root / "resources/templates/exporters" / f"{template_id}.pptx"
        source_hash = sha256_file(path)
        masters, layouts = _template_structure(path)
        result.append(
            P16TemplateImportCase(
                record_id=f"p16-ds7-{template_id}",
                case_role="gold_positive",
                template_id=template_id,
                template_version="1.0.0",
                custom_template=False,
                source_kind="builtin",
                source_uri=path.as_posix(),
                source_sha256=source_hash,
                normalized_pptx_sha256=source_hash,
                license="project-mit-attribution",
                master_count=masters,
                layout_count=layouts,
                required_layout_roles=[
                    "Title Slide",
                    "Title and Content",
                    "Two Content",
                    "Comparison",
                    "Picture with Caption",
                ],
                slide_type_layout_map={
                    "title": "Title Slide",
                    "agenda": "Title and Content",
                    "objectives": "Title and Content",
                    "concept": "Title and Content",
                    "process": "Two Content",
                    "comparison": "Comparison",
                    "example": "Picture with Caption",
                    "activity": "Title and Content",
                    "summary": "Title Only",
                    "references": "Title and Content",
                },
                required_placeholders=["title", "content", "picture", "slide_number"],
                expected_file_roles=[role],
                source_provenance=[f"template_registry:{role}", f"source_sha256:{source_hash}"],
            )
        )
    return result


def _negative_templates(root: Path) -> list[P16TemplateImportCase]:
    path = root / "resources/templates/exporters/ppt_standard_lecture_v1.pptx"
    source_hash = sha256_file(path)
    base = {
        "template_version": "1.0.0",
        "custom_template": False,
        "source_uri": path.as_posix(),
        "source_sha256": source_hash,
        "normalized_pptx_sha256": source_hash,
        "license": "project-mit-attribution",
        "master_count": 1,
        "layout_count": 11,
        "required_layout_roles": ["Title Slide", "Title and Content"],
        "slide_type_layout_map": {"title": "Title Slide"},
        "required_placeholders": ["title", "content"],
        "expected_file_roles": ["master", "layout"],
        "source_provenance": ["deterministic_contract_negative"],
    }
    return [
        P16TemplateImportCase(
            record_id="p16-ds7-negative-hash",
            case_role="contract_negative",
            template_id="p16_external_velis_v1",
            source_kind="tampered",
            expected_failure="template_identity_mismatch",
            **base,
        ),
        P16TemplateImportCase(
            record_id="p16-ds7-negative-mapping",
            case_role="contract_negative",
            template_id="p16_external_velis_v1",
            source_kind="incomplete_mapping",
            expected_failure="template_mapping_incomplete",
            **{**base, "source_sha256": EXTERNAL_SHA, "master_count": 2, "layout_count": 32},
        ),
    ]


def _render_review(
    cpds3: CPDS3P16PilotDataset, cpds7: CPDS7P16PilotDataset, bundle: str, second: bool
) -> str:
    cards: list[str] = []
    for case in cpds3.cases:
        rows = []
        for target in case.slide_targets:
            kp_names = (
                "、".join(item.canonical_name for item in target.knowledge_point_snapshots) or "—"
            )
            evidence = "；".join(item.gold_text for item in target.evidence_snapshots) or "—"
            rows.append(
                f"<tr><td>{target.slide_index}</td><td>{html.escape(target.slide_type)}</td>"
                f"<td>{html.escape(target.title_intent)}</td><td>{html.escape(kp_names)}</td>"
                f"<td>{html.escape(evidence)}</td><td>{html.escape(target.layout_role)}</td>"
                f"<td>{html.escape(target.asset_kind)}</td><td>{'是' if target.notes_required else '否'}</td></tr>"
            )
        cards.append(
            f"<article class='card'><h2>{html.escape(case.record_id)} · {html.escape(case.template_id)}</h2>"
            f"<p>{case.slide_count} 页 · {html.escape(case.course_id)} · Artifact {html.escape(case.lesson_artifact_id)}</p>"
            "<table><thead><tr><th>页</th><th>页型</th><th>教学意图</th><th>KP</th><th>Evidence 原文</th><th>Layout</th><th>素材</th><th>Notes</th></tr></thead>"
            f"<tbody>{''.join(rows)}</tbody></table><label>记录决定 <select data-id='{case.record_id}'><option value=''>请选择</option><option value='pass'>通过</option><option value='return'>退回</option></select></label><textarea data-notes='{case.record_id}' placeholder='退回原因/备注'></textarea></article>"
        )
    for template_case in cpds7.cases:
        compact = json.dumps(template_case.model_dump(mode="json"), ensure_ascii=False, indent=2)
        cards.append(
            f"<article class='card'><h2>{html.escape(template_case.record_id)} · {html.escape(template_case.template_id)}</h2>"
            f"<p>{html.escape(template_case.case_role)} · {html.escape(template_case.source_kind)} · {template_case.master_count} Master · {template_case.layout_count} Layout · {html.escape(template_case.license)}</p>"
            f"<p>映射：{html.escape(json.dumps(template_case.slide_type_layout_map, ensure_ascii=False))}</p>"
            f"<details><summary>完整 Gold JSON</summary><pre>{html.escape(compact)}</pre></details>"
            f"<label>记录决定 <select data-id='{template_case.record_id}'><option value=''>请选择</option><option value='pass'>通过</option><option value='return'>退回</option></select></label><textarea data-notes='{template_case.record_id}' placeholder='退回原因/备注'></textarea></article>"
        )
    blind = (
        "二轮盲化：隐藏首轮决定；请复核 Architecture、高风险页、外部模板映射和两个负例。"
        if second
        else "首轮：逐项核对 3 个 Architecture、46 个 Slide Target、4 个模板正例和 2 个负例。"
    )
    return f"""<!doctype html><meta charset='utf-8'><title>P16 CP-DS3/7 Review</title>
<style>body{{font-family:Arial,'Microsoft YaHei',sans-serif;margin:24px;background:#f5f6f8}}.notice{{background:#fff4ce;padding:14px;border:1px solid #e5c65a}}.card{{background:white;border:1px solid #ccd2da;border-radius:8px;padding:16px;margin:16px 0;overflow:auto}}table{{border-collapse:collapse;width:100%;font-size:13px}}td,th{{border:1px solid #d8dde5;padding:6px;vertical-align:top}}textarea{{width:100%;min-height:48px;margin-top:8px}}pre{{white-space:pre-wrap;max-height:420px;overflow:auto}}</style>
<main><h1>P16 CP-DS3/CP-DS7 Pilot Candidate</h1><div class='notice'><b>Bundle：</b>{bundle}<br>{blind}<br>本页只审核 Gold 约束，不审核未来系统输出；当前三套内置 PPTX 相同 Hash 是已记录的 P16 基线缺陷。</div>{"".join(cards)}<button onclick='download()'>下载审核 JSON</button></main>
<script>function download(){{const out={{schema_version:'coursepilot.p16-review-decisions.v1',bundle_sha256:'{bundle}',review_pass:{'"second"' if second else '"first"'},reviewer_id:'course_owner',reviewed_at:new Date().toISOString(),expected_record_ids:[],decisions:[]}};document.querySelectorAll('select[data-id]').forEach(s=>{{out.expected_record_ids.push(s.dataset.id);out.decisions.push({{record_id:s.dataset.id,decision:s.value,notes:document.querySelector('textarea[data-notes="'+s.dataset.id+'"]').value}})}});const a=document.createElement('a');a.href=URL.createObjectURL(new Blob([JSON.stringify(out,null,2)],{{type:'application/json'}}));a.download='p16_review_decisions.json';a.click()}}</script>"""


def generate(root: Path) -> dict[str, str]:
    p14 = _load_json(root / P14_PATH)
    ds2 = _load_json(root / DS2_PATH)
    ds3 = _load_json(root / DS3_PATH)
    split = _load_json(root / DS3_SPLIT_PATH)
    calibration = set(split["calibration_ids"])
    evidence = {item["evidence_id"]: item for item in ds2["evidence"]}
    all_kps = {item["gold_kp_id"]: item for item in ds3["knowledge_points"]}
    artifacts = _p14_artifacts()
    cases_by_id = {item["record_id"]: item for item in p14["cases"]}
    for record_id in artifacts:
        for kp_id in cases_by_id[record_id]["required_knowledge_point_ids"]:
            if kp_id not in calibration:
                raise ValueError(f"P16 cannot use DS3 Holdout KP: {kp_id}")
    transformer = _case(
        root,
        cases_by_id["p14-lesson-01-transformer"],
        artifacts["p14-lesson-01-transformer"],
        evidence,
        all_kps,
        [
            "title",
            "objectives",
            "agenda",
            "concept",
            "example",
            "comparison",
            "process",
            "concept",
            "activity",
            "summary",
            "concept",
            "process",
            "concept",
            "process",
            "concept",
            "comparison",
            "example",
            "concept",
            "process",
            "activity",
            "comparison",
            "summary",
            "references",
            "summary",
        ],
        [
            [0],
            [0, 1],
            [],
            [0],
            [0],
            [0, 1],
            [1],
            [1],
            [1],
            [0, 1],
            [2],
            [2],
            [2],
            [2],
            [3],
            [1, 3],
            [3],
            [2],
            [2],
            [2],
            [0, 2],
            [0, 1, 2, 3],
            [0, 1, 2, 3],
            [0, 1, 2, 3],
        ],
        [
            "传统 seq2seq 的长序列局限",
            "本课学习目标：从 seq2seq 过渡到 Transformer",
            "本课内容路线",
            "固定长度状态对长距离依赖的限制",
            "长句建模中的信息保留问题",
            "固定向量与动态注意力的差异",
            "注意力计算流程",
            "Q、K、V 的来源",
            "判断不同注意力中的 Q/K/V 来源",
            "第一部分小结",
            "Transformer 编码器总体结构",
            "输入嵌入与位置信息",
            "编码器模块组成",
            "单层编码器处理流程",
            "编码器—解码器注意力",
            "自注意力与编码器—解码器注意力比较",
            "Q/K/V 角色示例",
            "多头注意力与前馈网络",
            "编码器整体数据流",
            "绘制编码器结构并标注子层",
            "从 seq2seq 到 Transformer 的演进",
            "核心概念回顾",
            "来源与引用",
            "本课结束与后续学习",
        ],
        {18: "editable_shape"},
        "ppt_standard_lecture_v1",
    )
    perceptron = _case(
        root,
        cases_by_id["p14-lesson-02-perceptron-lab"],
        artifacts["p14-lesson-02-perceptron-lab"],
        evidence,
        all_kps,
        [
            "title",
            "objectives",
            "concept",
            "concept",
            "process",
            "example",
            "process",
            "example",
            "activity",
            "comparison",
            "summary",
            "references",
        ],
        [[0], [0, 1, 2, 3], [0], [1], [2], [2], [3], [3], [3], [0, 1], [0, 1, 2, 3], [0, 1, 2, 3]],
        [
            "感知机实验：概念解释",
            "本课学习目标：理解感知机及其训练",
            "感知机的定义与结构",
            "线性可分性的含义",
            "点到感知机超平面的距离公式",
            "距离计算示例",
            "感知机原始训练算法",
            "训练迭代示例",
            "手算一次权重更新",
            "线性可分与不可分的比较",
            "实验要点回顾",
            "来源与引用",
        ],
        {5: "editable_shape", 8: "editable_shape"},
        "ppt_concept_explanation_v1",
    )
    occupation = _case(
        root,
        cases_by_id["p14-lesson-03-occupation-risk-seminar"],
        artifacts["p14-lesson-03-occupation-risk-seminar"],
        evidence,
        all_kps,
        [
            "title",
            "objectives",
            "concept",
            "example",
            "comparison",
            "concept",
            "example",
            "activity",
            "summary",
            "references",
        ],
        [[0], [0, 1, 2], [0], [1], [1, 2], [2], [1], [0, 2], [0, 1, 2], [0, 1, 2]],
        [
            "职业自动化风险案例研讨",
            "本课学习目标：阅读表格并讨论职业风险",
            "人工智能影响职业的分析框架",
            "职业淘汰概率表",
            "不同职业风险的比较",
            "不易被人工智能取代的工作特征",
            "表格中的具体职业示例",
            "小组讨论：如何解释表格数据",
            "案例讨论结论",
            "来源与引用",
        ],
        {4: "editable_table", 7: "replaceable_image"},
        "ppt_case_seminar_v1",
    )
    cpds3 = CPDS3P16PilotDataset(cases=[transformer, perceptron, occupation])
    positives = _builtin_cases(root)
    external, external_hashes = _external_template(root)
    negatives = _negative_templates(root)
    cpds7 = CPDS7P16PilotDataset(cases=[*positives, external, *negatives])
    ds3_payload = cpds3.model_dump(mode="json")
    ds7_payload = cpds7.model_dump(mode="json")
    atomic_write_json(root / DS3_CANDIDATE, ds3_payload)
    atomic_write_json(root / DS7_CANDIDATE, ds7_payload)
    ds3_hash = sha256_file(root / DS3_CANDIDATE)
    ds7_hash = sha256_file(root / DS7_CANDIDATE)
    record_hashes = {
        item.record_id: _digest(item.model_dump(mode="json"))
        for item in [*cpds3.cases, *cpds7.cases]
    }
    renderer = {
        "provider": "libreoffice-headless",
        "profile": "libreoffice_headless_v1",
        "available": False,
    }
    manifest_base = {
        "schema_version": "coursepilot.p16-cp-ds37-bundle-manifest.v1",
        "candidate_hashes": {"cp_ds3": ds3_hash, "cp_ds7": ds7_hash},
        "record_hashes": record_hashes,
        "record_counts": {
            "cp_ds3_cases": 3,
            "slide_targets": 46,
            "cp_ds7_positive": 4,
            "cp_ds7_negative": 2,
        },
        "upstream_hashes": {
            "p14_approved": sha256_file(root / P14_PATH),
            "ds2_approved": sha256_file(root / DS2_PATH),
            "ds3_approved": sha256_file(root / DS3_PATH),
            "ds3_split": sha256_file(root / DS3_SPLIT_PATH),
        },
        "external_template": {
            "commit": EXTERNAL_COMMIT,
            "source": external_hashes["source"],
            "normalized": external_hashes["normalized"],
            "license": "CC0-1.0",
        },
        "renderer_preflight": renderer,
        "approval_scope": "cp_ds3_and_cp_ds7_p16_pilot_input_only",
        "gold_promotion": False,
        "external_provider_calls": 0,
    }
    bundle = _digest(manifest_base)
    manifest = P16BundleManifest(bundle_sha256=bundle, **manifest_base)
    atomic_write_json(root / MANIFEST_PATH, cast(JsonValue, manifest.model_dump(mode="json")))
    review_root = root / "storage_eval/cpds37_p16_review" / bundle
    atomic_write_text(review_root / "index.html", _render_review(cpds3, cpds7, bundle, False))
    atomic_write_text(
        review_root / "second_review.html", _render_review(cpds3, cpds7, bundle, True)
    )
    report = f"""# Pre-P16 CP-DS3/CP-DS7 PPT Pilot Candidate Review

任务：`ED-PRE16-CPDS37-T01` 至 `ED-PRE16-CPDS37-T09`

本批生成 3 条 CP-DS3 Pilot（24/12/10 页）、4 条 CP-DS7 正例和 2 条合同负例。所有事实来自 Approved P14/P06/P07；未调用 Provider、未读取 Test/Holdout、未生成 P16 输出。

- CP-DS3 Candidate SHA-256：`{ds3_hash}`
- CP-DS7 Candidate SHA-256：`{ds7_hash}`
- Bundle SHA-256：`{bundle}`
- 记录：3 个 Deck、46 个 Slide Target、4 个模板正例、2 个负例
- 审核入口：`storage_eval/cpds37_p16_review/{bundle}/index.html`
- 二轮入口：`storage_eval/cpds37_p16_review/{bundle}/second_review.html`
- 外部模板：lrkrol/powerpoint Velis，提交 `{EXTERNAL_COMMIT}`，CC0，源 Hash `{external_hashes["source"]}`，规范化 PPTX Hash `{external_hashes["normalized"]}`

## 当前限制

本机未发现可执行的 `soffice`，Docker Engine 也未运行，因此 Manifest 的 Renderer Preflight 为 `available=false`。结构、Hash、Master/Layout/Placeholder 已检查；固定 LibreOffice Render Preview 尚未完成。按照 P16 计划，当前 Bundle 不应直接审批，需在 Renderer 可用后补跑并重新绑定 Candidate/Bundle Hash。

Candidate 保持 `candidate`，没有写入 `approved/`。
"""
    atomic_write_text(root / REPORT_PATH, report)
    return {
        "cp_ds3_sha256": ds3_hash,
        "cp_ds7_sha256": ds7_hash,
        "bundle_sha256": bundle,
        "review_path": str(review_root).replace("\\", "/"),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args()
    print(json.dumps(generate(args.root.resolve()), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
