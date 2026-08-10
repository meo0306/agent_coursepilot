"""Create the source-grounded P07 DS3 Candidate and offline review bundle."""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import shutil
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path
from typing import cast

from pydantic import JsonValue

from courserag.evals.schemas import (
    DS1ParsingDataset,
    DS2EvidenceDataset,
    DS3KnowledgePointDataset,
    DS3ReviewGroup,
    DS3SectionScope,
    DS3SectionScopeDataset,
    DS3SplitManifest,
    EvidenceRecord,
    KnowledgePointAliasAnnotation,
    KnowledgePointEvidenceLink,
    KnowledgePointRecord,
    P07GoldBundleManifest,
    SectionGold,
)
from evaluation.contracts import HashedArtifact, SourceSpan
from evaluation.corpus_fixtures import sha256_file
from evaluation.datasets import canonical_json_bytes, record_digest
from evaluation.ds2_p06_data import (
    DOCX_COURSE_ID,
    DOCX_DOCUMENT_ID,
    DOCX_DOCUMENT_SHA256,
    DOCX_DOCUMENT_VERSION,
    DOCX_SECTIONS,
    PDF_COURSE_ID,
    PDF_DOCUMENT_ID,
    PDF_DOCUMENT_SHA256,
    PDF_DOCUMENT_VERSION,
    PDF_SECTIONS,
    PRIMARY_DOCX,
    PRIMARY_PDF,
    _blocks_for_section,
    _docx_structure,
    _poppler_page,
    _section_path,
)
from evaluation.io import atomic_write_json, atomic_write_text

ROOT = Path("datasets/courserag_eval/v1")
DS1_PATH = ROOT / "approved/ds1/p04_native_docx.json"
DS2_PATH = ROOT / "approved/ds2/p06_evidence.json"
P05_PATH = ROOT / "approved/ds1/p05_ocr.json"
P06_APPROVAL = ROOT / "provenance/ds2_p06_approval.json"
P06_OUTPUT = Path("storage_eval/p06_b1_b2/run-4/system_outputs.json")
CANDIDATE_PATH = ROOT / "candidates/ds3/p07_knowledge_points_r1.json"
SUPPORT_PATH = ROOT / "candidates/ds2/p07_kp_support_r1.json"
SCOPES_PATH = ROOT / "provenance/ds3_p07_section_scopes.json"
SPLIT_PATH = ROOT / "provenance/ds3_p07_split.json"
POLICY_PATH = ROOT / "provenance/ds3_p07_generation_policy.json"
MANIFEST_PATH = ROOT / "provenance/p07_gold_bundle_manifest.json"
HISTORY_PATH = ROOT / "provenance/ds3_p07_candidate_revision_history.json"
REPORT_PATH = Path("docs/refactor/phase_reports/ED_PRE_P07_DS3_candidate_review.md")
R5_REVIEW = Path(
    "storage_eval/ds2_p06_review/f4295f9783b131a8305713765907e169a83dc741d6c9af390b0b67b2f15b5bfc/assets"
)

# Each item follows the five Approved DS2 Evidence records in that Section. None means that
# the source unit is bibliographic, mechanical code, or too weak to be a teachable KP.
LABELS: dict[tuple[str, str], tuple[str | None, ...]] = {
    (DOCX_COURSE_ID, "1.1.1"): ("图灵测试", None, "知识表达", "图灵测试的非物理性", "完整图灵测试"),
    (DOCX_COURSE_ID, "2.2"): (
        "感知机的提出",
        "Scikit-Learn二分类数据构造",
        "感知机模型训练配置",
        "感知机的线性分类局限",
        "多层感知机的适用范围",
    ),
    (DOCX_COURSE_ID, "2.2.2"): (
        "感知机",
        "线性可分性",
        "点到感知机超平面的距离",
        "感知机原始训练算法",
        "感知机算法收敛性",
    ),
    (DOCX_COURSE_ID, "3.1.3"): (
        "深度学习应用领域",
        None,
        "深度学习在语音处理中的应用",
        "深度学习在推荐系统中的应用",
        "深度学习在金融风控中的应用",
    ),
    (DOCX_COURSE_ID, "3.5.3"): (
        "传统seq2seq的长序列局限",
        "注意力机制中Q、K、V的来源",
        "Transformer编码器结构",
        "位置编码",
        "编码器-解码器注意力",
    ),
    (DOCX_COURSE_ID, "5.1.1"): (
        "大模型",
        "大模型参数规模演进",
        "大规模训练数据与涌现能力",
        "大模型发现新知识的能力",
        "大模型训练计算成本",
    ),
    (DOCX_COURSE_ID, "5.2.1"): (
        "大模型训练数据准备与预处理",
        "公开文本训练数据集",
        None,
        "大规模高维数据的计算资源消耗",
        "训练数据隐私保护",
    ),
    (DOCX_COURSE_ID, "5.3"): ("微调", "指令微调", "大模型安全对齐", "大模型对齐的有用性", None),
    (DOCX_COURSE_ID, "5.3.4"): (
        "ERNIE情感分类微调流程",
        "ERNIE微调实验环境",
        "ERNIE预测配置",
        None,
        "微调在自有数据集上的效果",
    ),
    (DOCX_COURSE_ID, "6.2.2"): (
        "神经辐射场三维重建",
        "NeRF累积透射率",
        "NeRF渲染损失",
        "NeRF技术发展方向",
        "NeRF快速推理、训练、编辑与动态重建方法",
    ),
    (DOCX_COURSE_ID, "6.2.3"): (
        "3D高斯点染三维重建",
        "3D高斯点的透视投影",
        "3D高斯二维协方差变换",
        "高斯粒子瓦片深度排序",
        "3D高斯点染技术拓展",
    ),
    (DOCX_COURSE_ID, "6.3"): (
        "同时定位与建图",
        "SLAM传感器特性比较",
        "多传感器异构数据处理挑战",
        "LIO-SAM",
        "视觉-IMU子系统的无特征鲁棒性",
    ),
    (DOCX_COURSE_ID, "9.1.2"): (
        "智能可穿戴系统的技术链路",
        "可穿戴传感器性能要求",
        "可穿戴传感数据算法类型",
        "可穿戴传感数据挖掘",
        "智能可穿戴系统低功耗设计",
    ),
    (DOCX_COURSE_ID, "9.2.2"): (
        "计算机视觉在军用自动驾驶感知中的应用",
        "深度学习军事目标识别",
        "军事目标距离与图像像素尺寸",
        "军事目标毁伤检测",
        "战场SLAM地图",
    ),
    (DOCX_COURSE_ID, "9.5.1"): (
        "智慧服务",
        "智慧服务机器人政策环境",
        "无接触经济与服务机器人",
        "服务机器人软件架构",
        "服务机器人视觉交互",
    ),
    (DOCX_COURSE_ID, "9.7"): (
        "人工智能天气预报",
        "大模型与机器人融合",
        "大模型辅助学生学业预警",
        None,
        None,
    ),
    (PDF_COURSE_ID, "1.1.1"): (
        None,
        None,
        "图灵机",
        "思维机器公司",
        "早期计算机在数学和自然语言中的应用",
    ),
    (PDF_COURSE_ID, "1.1.2"): (
        "人工智能",
        "人工与智能的概念分解",
        None,
        "机器智能的界定难题",
        "Google Duplex语音助理",
    ),
    (PDF_COURSE_ID, "1.2.1"): (
        None,
        "图灵测试",
        "IBM沃森问答系统",
        "深度学习平台推广",
        "大模型区域产业生态",
    ),
    (PDF_COURSE_ID, "1.2.2"): (
        "职业自动化淘汰概率",
        None,
        "不易被人工智能取代的工作特征",
        "职业自动化风险分析",
        "通用人工智能目标",
    ),
    (PDF_COURSE_ID, "1.2.3"): (
        "通用人工智能",
        "通用人工智能的跨领域任务能力",
        "通用人工智能的人类能力与自我意识边界",
        None,
        "安全通用人工智能使命",
    ),
    (PDF_COURSE_ID, "1.3.1"): (
        "特定领域人工智能突破条件",
        "人工智能语音识别、合成与实时翻译",
        "全仿真智能AI主持人",
        "开源语音技术生态",
        "人工智能语音合成风险",
    ),
    (PDF_COURSE_ID, "1.3.4"): (
        "人工智能个性化教育",
        "双AI教学演练",
        "智能测评阅卷",
        "课堂教学智能反馈",
        "学生专注度分析流程",
    ),
    (PDF_COURSE_ID, "1.3.7"): (
        "生物识别支付认证",
        "刷脸支付",
        "人工智能交易异常检测",
        "跨境支付汇率风险",
        "人工智能支付合规监控",
    ),
}

ALIASES = {
    "人工智能": ("AI", "Artificial Intelligence"),
    "通用人工智能": ("AGI", "Artificial General Intelligence"),
    "微调": ("Fine-Tuning",),
    "多层感知机的适用范围": ("MLP的适用范围",),
    "传统seq2seq的长序列局限": ("传统Sequence-to-Sequence的长序列局限",),
    "位置编码": ("Positional Encoding",),
    "同时定位与建图": ("SLAM", "Simultaneous Localization and Mapping"),
    "神经辐射场三维重建": ("NeRF三维重建",),
}


def _sha_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _normal(value: str) -> str:
    return "".join(unicodedata.normalize("NFKC", value).lower().split())


def _artifact(path: Path) -> HashedArtifact:
    return HashedArtifact(
        path=path.as_posix(),
        sha256=sha256_file(path),
        size_bytes=path.stat().st_size,
        media_type="application/json",
    )


def _load(repository_root: Path) -> tuple[DS1ParsingDataset, DS2EvidenceDataset]:
    ds1 = DS1ParsingDataset.model_validate_json(
        (repository_root / DS1_PATH).read_text(encoding="utf-8")
    )
    ds2 = DS2EvidenceDataset.model_validate_json(
        (repository_root / DS2_PATH).read_text(encoding="utf-8")
    )
    return ds1, ds2


def _synthetic_pdf_section(repository_root: Path) -> SectionGold:
    _, _, p31 = _poppler_page(repository_root, 31)
    _, _, p32 = _poppler_page(repository_root, 32)
    start = next(item for item in p31 if item.block_number == 15)
    end = next(item for item in p32 if item.block_number == 25)
    return SectionGold(
        record_id="ds3-source-section-pdf-1-3-7",
        document_id=PDF_DOCUMENT_ID,
        document_version=PDF_DOCUMENT_VERSION,
        section_id="gold-sec-doc-ai-general-education-excerpt-1-3-7",
        title="1.3.7　AI＋电子支付",
        level=3,
        parent_section_id="gold-sec-doc-ai-general-education-excerpt-1-3",
        source_span=SourceSpan(
            document_id=PDF_DOCUMENT_ID,
            document_version=PDF_DOCUMENT_VERSION,
            document_sha256=PDF_DOCUMENT_SHA256,
            section_path=_section_path("1.3.7"),
            page_start=31,
            page_end=32,
            block_start=start.source_unit_id,
            block_end=end.source_unit_id,
        ),
        first_text="1.3.7　AI＋电子支付",
        last_text=end.text,
    )


def _scopes(repository_root: Path, ds1: DS1ParsingDataset) -> DS3SectionScopeDataset:
    approved = {
        (r.source_span.document_id, r.source_span.section_path[-1]): r
        for r in ds1.records
        if isinstance(r, SectionGold)
    }
    _, paragraphs, docx_ranges, _ = _docx_structure(repository_root / PRIMARY_DOCX)
    scopes: list[DS3SectionScope] = []
    for section in DOCX_SECTIONS:
        start, end, title = docx_ranges[section]
        excluded: list[str] = []
        skip_ranges: list[tuple[int, int]] = []
        for child in ("2.2.2", "5.3.4"):
            if section == child.rsplit(".", 1)[0]:
                child_start, child_end, _ = docx_ranges[child]
                skip_ranges.append((child_start, child_end))
                excluded.append(child)
        lines = [
            p.text
            for index, p in enumerate(paragraphs[start:end], start=start)
            if p.text.strip() and not any(a <= index < b for a, b in skip_ranges)
        ]
        text = "\n".join(lines)
        upstream = approved.get((DOCX_DOCUMENT_ID, section))
        span = SourceSpan(
            document_id=DOCX_DOCUMENT_ID,
            document_version=DOCX_DOCUMENT_VERSION,
            document_sha256=DOCX_DOCUMENT_SHA256,
            section_path=_section_path(section),
            block_start=f"paragraph:{start}",
            block_end=f"paragraph:{end - 1}",
        )
        scopes.append(
            DS3SectionScope(
                scope_id=f"ds3-scope-docx-{section.replace('.', '-')}",
                course_id=DOCX_COURSE_ID,
                section_path=section,
                title=title,
                source_span=span,
                source_text=text,
                source_text_sha256=_sha_text(text),
                upstream_section_record_id=upstream.record_id if upstream else None,
                upstream_section_record_sha256=record_digest(upstream) if upstream else None,
                excluded_child_section_paths=excluded,
                requires_boundary_review=upstream is None,
            )
        )
    pdf_sections = {
        (r.source_span.section_path[-1]): r
        for r in ds1.records
        if isinstance(r, SectionGold) and r.document_id == PDF_DOCUMENT_ID
    }
    pdf_sections["1.3.7"] = _synthetic_pdf_section(repository_root)
    for section in PDF_SECTIONS:
        source = pdf_sections[section]
        blocks = _blocks_for_section(repository_root, source)
        text = "\n".join(block.text for block in blocks if block.text.strip())
        upstream = approved.get((PDF_DOCUMENT_ID, section))
        scopes.append(
            DS3SectionScope(
                scope_id=f"ds3-scope-pdf-{section.replace('.', '-')}",
                course_id=PDF_COURSE_ID,
                section_path=section,
                title=source.title,
                source_span=source.source_span,
                source_text=text,
                source_text_sha256=_sha_text(text),
                upstream_section_record_id=upstream.record_id if upstream else None,
                upstream_section_record_sha256=record_digest(upstream) if upstream else None,
                requires_boundary_review=upstream is None,
            )
        )
    return DS3SectionScopeDataset(
        dataset_id="courserag-ds3-p07-section-scopes", dataset_version="p07-r1", scopes=scopes
    )


def _role(semantic_type: str) -> str:
    return {
        "definition": "definition",
        "principle": "principle",
        "procedure": "process",
        "formula": "formula",
        "example": "example",
        "application": "application",
        "comparison": "comparison",
    }.get(semantic_type, "support")


def _records(ds2: DS2EvidenceDataset, scopes: DS3SectionScopeDataset) -> list[KnowledgePointRecord]:
    scope_map = {(s.course_id, s.section_path): s for s in scopes.scopes}
    grouped: dict[tuple[str, str], list[EvidenceRecord]] = defaultdict(list)
    for evidence in ds2.evidence:
        if evidence.course_id is None:
            raise ValueError(f"formal DS2 Evidence has no course_id: {evidence.evidence_id}")
        grouped[(evidence.course_id, evidence.source_span.section_path[-1])].append(evidence)
    result: list[KnowledgePointRecord] = []
    for key in [(DOCX_COURSE_ID, s) for s in DOCX_SECTIONS] + [
        (PDF_COURSE_ID, s) for s in PDF_SECTIONS
    ]:
        evidence_items = grouped[key]
        labels = LABELS[key]
        if len(evidence_items) != 5 or len(labels) != 5:
            raise ValueError(f"frozen five-Evidence Section changed: {key}")
        scope = scope_map[key]
        for evidence, name in zip(evidence_items, labels, strict=True):
            if name is None:
                continue
            normalized = _normal(name)
            identity = {
                "course_id": key[0],
                "normalized_name": normalized,
                "primary_evidence_ids": [evidence.evidence_id],
            }
            kp_id = "gold-kp-" + hashlib.sha256(canonical_json_bytes(identity)).hexdigest()[:32]
            aliases = list(ALIASES.get(name, ()))
            alias_annotations = [
                KnowledgePointAliasAnnotation(
                    alias=a,
                    basis="source_text",
                    evidence_ids=[evidence.evidence_id],
                    rationale="Alias is printed in the bound source Evidence.",
                )
                for a in aliases
            ]
            role = _role(evidence.semantic_unit_type)
            result.append(
                KnowledgePointRecord(
                    record_id=kp_id,
                    gold_kp_id=kp_id,
                    course_id=key[0],
                    canonical_name=name,
                    aliases=aliases,
                    summary=evidence.gold_text,
                    section_ids=[scope.scope_id],
                    evidence_ids=[evidence.evidence_id],
                    roles=[role],
                    importance="core"
                    if role in {"definition", "principle", "formula"}
                    else ("optional" if role == "example" else "supporting"),
                    granularity="atomic",
                    annotation_profile="formal_ds3_v1",
                    normalized_name=normalized,
                    concept_family_id="kp-family-" + _sha_text(key[0] + "\n" + normalized)[:24],
                    evidence_links=[
                        KnowledgePointEvidenceLink(
                            evidence_id=evidence.evidence_id,
                            role=role,
                            is_primary=True,
                            evidence_record_sha256=record_digest(evidence),
                        )
                    ],
                    alias_annotations=alias_annotations,
                    source_scope_ids=[scope.scope_id],
                    annotation_rationale="The Candidate names one teachable concept, method, property, formula, or application stated by the primary Evidence; the summary is verbatim Gold text.",
                )
            )
    if not 80 <= len(result) <= 120:
        raise ValueError(f"source-grounded Candidate count outside 80..120: {len(result)}")
    return result


def _split(records: list[KnowledgePointRecord]) -> DS3SplitManifest:
    families: dict[str, list[KnowledgePointRecord]] = defaultdict(list)
    for item in records:
        families[item.concept_family_id or ""].append(item)
    ordered = sorted(families.items(), key=lambda item: _sha_text("p07-split-v1\n" + item[0]))
    target = round(len(records) * 0.7)
    calibration: list[str] = []
    holdout: list[str] = []
    assignments: dict[str, str] = {}
    for family, items in ordered:
        destination = calibration if len(calibration) < target else holdout
        label = "calibration" if destination is calibration else "holdout"
        destination.extend(item.gold_kp_id for item in items)
        assignments[family] = label
    return DS3SplitManifest(
        dataset_id="courserag-ds3-p07-split",
        dataset_version="p07-r1",
        calibration_ids=calibration,
        holdout_ids=holdout,
        family_assignments=assignments,
        actual_calibration_ratio=len(calibration) / len(records),
        algorithm_profile_sha256=_sha_text("concept-family-stratified-stable-hash-greedy-v1"),
    )


def _groups(
    records: list[KnowledgePointRecord], scopes: DS3SectionScopeDataset
) -> list[DS3ReviewGroup]:
    chunks = [scopes.scopes[i : i + 6] for i in range(0, 24, 6)]
    return [
        DS3ReviewGroup(
            group_id=f"group-{i:02d}",
            section_scope_ids=[s.scope_id for s in chunk],
            knowledge_point_ids=[
                r.gold_kp_id for s in chunk for r in records if s.scope_id in r.source_scope_ids
            ],
        )
        for i, chunk in enumerate(chunks, 1)
    ]


def _review_html(
    bundle: str,
    records: list[KnowledgePointRecord],
    evidence_by_id: dict[str, EvidenceRecord],
    groups: list[DS3ReviewGroup],
    second: list[str],
    review_pass: str = "first",
) -> str:
    cards = []
    group_for = {kp: group.group_id for group in groups for kp in group.knowledge_point_ids}
    for item in records:
        ev = evidence_by_id[item.evidence_ids[0]]
        aliases = "、".join(item.aliases) or "无"
        neighbor = (
            "\n".join(ev.necessary_neighbor_text)
            if isinstance(ev.necessary_neighbor_text, list)
            else (ev.necessary_neighbor_text or "无")
        )
        cards.append(
            f"<article data-group='{group_for[item.gold_kp_id]}' data-second='{'yes' if item.gold_kp_id in second else 'no'}'><h2>{html.escape(item.canonical_name)}</h2><code>{item.gold_kp_id}</code><p><b>课程/Section：</b>{item.course_id} / {html.escape(ev.source_span.section_path[-1])}</p><p><b>Alias：</b>{html.escape(aliases)}　<b>Importance：</b>{item.importance}　<b>Granularity：</b>{item.granularity}</p><img src='assets/{item.gold_kp_id}.png' alt='Evidence 页面与 BBox 覆盖层'><p><b>逐字 Evidence：</b>{html.escape(ev.gold_text)}</p><p><b>必要邻接：</b>{html.escape(neighbor)}</p><p><b>页码：</b>{ev.source_span.page_start or 'DOCX固定渲染定位'}　<b>Evidence：</b>{ev.evidence_id}</p><label>决定 <select data-id='{item.gold_kp_id}'><option value=''>未审</option><option value='pass'>通过</option><option value='return'>退回</option></select></label><label>备注 <input data-note='{item.gold_kp_id}'></label></article>"
        )
    return (
        "<!doctype html><html lang='zh-CN'><meta charset='utf-8'><title>DS3 P07 Review</title><style>body{font:15px/1.55 system-ui;max-width:1200px;margin:auto;padding:24px}article{border:1px solid #bbb;padding:16px;margin:18px 0}article img{display:block;max-width:100%;max-height:900px;margin:12px 0;border:1px solid #ddd}code{word-break:break-all}input{width:60%}nav button{margin:4px}</style><h1>P07 DS3 Candidate 审核包</h1><p>Bundle SHA-256: <code>"
        + bundle
        + "</code></p><p>首轮审核全部记录；二轮审核 data-second=yes 的高风险与固定20%样本。Summary 为逐字 Evidence，避免引入外部事实。</p><nav><button onclick=filter('*')>全部</button>"
        + "".join(f"<button onclick=filter('{g.group_id}')>{g.group_id}</button>" for g in groups)
        + "<button onclick=filter('second')>二轮</button><button onclick=download()>下载决定</button></nav>"
        + "".join(cards)
        + "<script>function filter(x){document.querySelectorAll('article').forEach(a=>a.hidden=!(x==='*'||a.dataset.group===x||(x==='second'&&a.dataset.second==='yes')))}function download(){let reviewed=[],returned=[],notes={};document.querySelectorAll('select').forEach(s=>{if(s.value==='pass')reviewed.push(s.dataset.id);if(s.value==='return')returned.push(s.dataset.id);let n=document.querySelector('[data-note="
        "+s.dataset.id+"
        "]');if(n.value)notes[s.dataset.id]=n.value});let p={schema_version:'courserag.ds3-review-decisions.v1',bundle_sha256:'"
        + bundle
        + f"',review_pass:'{review_pass}',expected_record_ids:"
        + json.dumps([r.gold_kp_id for r in records])
        + f",reviewed_record_ids:reviewed,returned_record_ids:returned,record_notes:notes,notes:''}};let a=document.createElement('a');a.href=URL.createObjectURL(new Blob([JSON.stringify(p,null,2)],{{type:'application/json'}}));a.download='ds3_p07_{review_pass}_review_decisions.json';a.click()}}</script></html>"
    )


def generate(repository_root: Path) -> P07GoldBundleManifest:
    ds1, ds2 = _load(repository_root)
    scopes = _scopes(repository_root, ds1)
    records = _records(ds2, scopes)
    candidate = DS3KnowledgePointDataset(
        dataset_id="courserag-ds3-p07-knowledge-points",
        dataset_version="p07-r1",
        knowledge_points=records,
    )
    support = DS2EvidenceDataset(
        dataset_id="courserag-ds2-p07-kp-support", dataset_version="p07-r1", evidence=[]
    )
    split = _split(records)
    policy = {
        "schema_version": "courserag.ds3-generation-policy.v1",
        "strategy": "independent_source_grounded_owner_review_candidate",
        "source_unit_selection": "teachable concepts only; no quota filling",
        "summary": "verbatim Approved DS2 gold_text",
        "stable_id_fields": ["course_id", "normalized_name", "ordered_primary_evidence_ids"],
        "excluded_inputs": ["P07 runtime output", "P06 retrieval hits", "external knowledge"],
        "supplemental_evidence_count": 0,
    }
    for path, payload in (
        (CANDIDATE_PATH, candidate.model_dump(mode="json")),
        (SUPPORT_PATH, support.model_dump(mode="json")),
        (SCOPES_PATH, scopes.model_dump(mode="json")),
        (SPLIT_PATH, split.model_dump(mode="json")),
        (POLICY_PATH, policy),
    ):
        atomic_write_json(repository_root / path, cast(JsonValue, payload))
    descriptor = {
        "knowledge_point_candidate_sha256": sha256_file(repository_root / CANDIDATE_PATH),
        "support_candidate_sha256": sha256_file(repository_root / SUPPORT_PATH),
        "section_scopes_sha256": sha256_file(repository_root / SCOPES_PATH),
        "split_sha256": sha256_file(repository_root / SPLIT_PATH),
        "generation_policy_sha256": sha256_file(repository_root / POLICY_PATH),
        "upstream_ds2_sha256": sha256_file(repository_root / DS2_PATH),
    }
    bundle = hashlib.sha256(canonical_json_bytes(descriptor)).hexdigest()
    groups = _groups(records, scopes)
    reasons: dict[str, list[str]] = {}
    for item in records:
        ev = next(e for e in ds2.evidence if e.evidence_id == item.evidence_ids[0])
        why: list[str] = []
        if item.aliases:
            why.append("alias")
        if ev.source_type == "ocr_derived":
            why.append("ocr")
        if ev.semantic_unit_type == "formula":
            why.append("formula")
        if why:
            reasons[item.gold_kp_id] = why
    remainder = [item.gold_kp_id for item in records if item.gold_kp_id not in reasons]
    for kp_id in sorted(remainder, key=lambda value: _sha_text("p07-second-review-v1\n" + value))[
        : max(1, round(len(remainder) * 0.2))
    ]:
        reasons[kp_id] = ["stable_20_percent_sample"]
    second = sorted(reasons, key=lambda value: _sha_text("p07-second-review-order-v1\n" + value))
    pack = Path("storage_eval/ds3_p07_review") / bundle
    index = repository_root / pack / "index.html"
    asset_dir = repository_root / pack / "assets"
    asset_dir.mkdir(parents=True, exist_ok=True)
    review_assets: dict[str, str] = {}
    evidence_by_id = {e.evidence_id: e for e in ds2.evidence}
    for item in records:
        source = repository_root / R5_REVIEW / f"{item.evidence_ids[0]}.png"
        if not source.is_file():
            matches = sorted(
                (repository_root / "storage_eval/ds2_p06_review").glob(
                    f"*/assets/{item.evidence_ids[0]}.png"
                )
            )
            if not matches:
                raise ValueError(f"missing frozen DS2 Evidence review asset: {source}")
            source = matches[-1]
        destination = asset_dir / f"{item.gold_kp_id}.png"
        shutil.copyfile(source, destination)
        review_assets[item.gold_kp_id] = sha256_file(destination)
    atomic_write_text(
        index,
        _review_html(bundle, records, evidence_by_id, groups, second),
    )
    second_index = repository_root / pack / "second_review.html"
    second_records = [
        next(item for item in records if item.gold_kp_id == kp_id) for kp_id in second
    ]
    atomic_write_text(
        second_index,
        _review_html(bundle, second_records, evidence_by_id, groups, second, "second"),
    )
    manifest = P07GoldBundleManifest(
        dataset_id="courserag-p07-gold-bundle",
        dataset_version="p07-r1",
        bundle_sha256=bundle,
        knowledge_point_candidate=_artifact(repository_root / CANDIDATE_PATH),
        support_candidate=_artifact(repository_root / SUPPORT_PATH),
        section_scopes=_artifact(repository_root / SCOPES_PATH),
        split_manifest=_artifact(repository_root / SPLIT_PATH),
        generation_policy=_artifact(repository_root / POLICY_PATH),
        candidate_record_sha256={r.gold_kp_id: record_digest(r) for r in records},
        support_record_sha256={},
        source_artifacts=[
            _artifact(repository_root / PRIMARY_DOCX),
            _artifact(repository_root / PRIMARY_PDF),
        ],
        upstream_approved_file_sha256={
            "ds1_p04": sha256_file(repository_root / DS1_PATH),
            "ds1_p05": sha256_file(repository_root / P05_PATH),
            "ds2_p06": sha256_file(repository_root / DS2_PATH),
        },
        preserved_p06_artifact_sha256={
            "approved_ds2": sha256_file(repository_root / DS2_PATH),
            "approval": sha256_file(repository_root / P06_APPROVAL),
            "b1_b2_system_outputs": sha256_file(repository_root / P06_OUTPUT),
        },
        review_groups=groups,
        first_review_ids=[r.gold_kp_id for r in records],
        second_review_ids=second,
        second_review_reasons=reasons,
        review_pack_relative_path=pack.as_posix(),
        review_pack_index_sha256=sha256_file(index),
        second_review_index_sha256=sha256_file(second_index),
        review_asset_sha256=review_assets,
        constraints=[
            "Only two owner-provided semantic sources are represented.",
            "No P07 output, P06 hit, or external knowledge was used to derive Gold.",
            "Candidates remain unapproved until exact bundle-hash owner approval.",
            "Global Dev/Test remain empty and Test remains unlocked.",
        ],
    )
    atomic_write_json(repository_root / MANIFEST_PATH, manifest.model_dump(mode="json"))
    history = {
        "schema_version": "course-eval.candidate-revision-history.v1",
        "dataset_id": "courserag-ds3-p07-knowledge-points",
        "dataset_version": "p07-r1",
        "revisions": [
            {
                "revision": 1,
                "candidate_relative_path": CANDIDATE_PATH.as_posix(),
                "candidate_file_sha256": sha256_file(repository_root / CANDIDATE_PATH),
                "status": "pending_course_owner_review",
                "reason": "Initial source-grounded formal P07 DS3 Candidate.",
            }
        ],
    }
    atomic_write_json(repository_root / HISTORY_PATH, cast(JsonValue, history))
    counts = Counter(r.course_id for r in records)
    report = f"# ED-PRE07 DS3 Candidate 审核报告\n\n- Bundle SHA-256: `{bundle}`\n- Knowledge Point Candidate SHA-256: `{sha256_file(repository_root / CANDIDATE_PATH)}`\n- DS2-KP Support Candidate SHA-256: `{sha256_file(repository_root / SUPPORT_PATH)}`\n- 知识点：{len(records)}（DOCX {counts[DOCX_COURSE_ID]} / PDF {counts[PDF_COURSE_ID]}）\n- Section：24（DOCX 16 / PDF 8）\n- Supplemental Evidence：0（现有 Approved DS2 足以直接支撑全部入选项）\n- Calibration/Holdout：{len(split.calibration_ids)}/{len(split.holdout_ids)}\n- 首轮：{len(records)} 条；第二轮：{len(second)} 条。\n\n首轮审核入口：`{pack.as_posix()}/index.html`；第二轮盲化入口：`{pack.as_posix()}/second_review.html`。先核对教学意义、名称/Alias、逐字 Summary、粒度、Evidence、Importance、Parent 与重复。\n\n批准语句：`批准正式 P07 Gold Bundle {bundle}`。\n"
    atomic_write_text(repository_root / REPORT_PATH, report)
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository-root", type=Path, default=Path.cwd())
    args = parser.parse_args()
    result = generate(args.repository_root.resolve())
    print(result.bundle_sha256)


if __name__ == "__main__":
    main()
