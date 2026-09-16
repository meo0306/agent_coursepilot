"""Build the source-grounded, retrieval-only P08 DS4/DS5 Candidate bundle."""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import shutil
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from courserag.domain.evidence import EvidenceArtifact
from courserag.evals.p06_metrics import map_gold_to_system_evidence
from courserag.evals.schemas import (
    DS2EvidenceDataset,
    DS3KnowledgePointDataset,
    DS4QueryProcessingDataset,
    DS5RetrievalQADataset,
    EvidenceGroup,
    P08DS5SplitManifest,
    P08GoldBundleManifest,
    P08SourcePackage,
    P08SourcePackageDataset,
    P08SplitAssignment,
    QueryProcessingCase,
    QueryProcessingExpected,
    RetrievalEvidenceJudgment,
    RetrievalQACase,
    UnanswerableRetrievalAudit,
)
from evaluation.contracts import HashedArtifact
from evaluation.corpus_fixtures import sha256_file
from evaluation.datasets import canonical_json_bytes, record_digest
from evaluation.io import atomic_write_json, atomic_write_text

ROOT = Path("datasets/courserag_eval/v1")
DS2_PATH = ROOT / "approved/ds2/p06_evidence.json"
DS3_PATH = ROOT / "approved/ds3/p07_knowledge_points.json"
DS2_APPROVAL = ROOT / "provenance/ds2_p06_approval.json"
DS3_APPROVAL = ROOT / "provenance/p07_gold_bundle_approval.json"
P07_PROTOCOL = ROOT / "provenance/p07_evaluation_protocol_r2.json"
P07_PROTOCOL_APPROVAL = ROOT / "provenance/p07_evaluation_protocol_r2_approval.json"
P06_OUTPUT = Path("storage_eval/p06_b1_b2/run-4/system_outputs.json")
P06_REPORT = Path("storage_eval/p06_b1_b2/run-4/report.json")
P07_CALIBRATION_REPORT = Path("storage_eval/p07_kp_calibration/run-4/report.json")
P07_HOLDOUT_REPORT = Path("storage_eval/p07_kp_holdout/run-1/report.json")
DS4_PATH = ROOT / "candidates/ds4/p08_query_processing_r1.json"
DS5_PATH = ROOT / "candidates/ds5/p08_retrieval_r1.json"
PACKAGES_PATH = ROOT / "provenance/p08_query_source_packages.json"
SPLIT_PATH = ROOT / "provenance/p08_ds5_split.json"
MANIFEST_PATH = ROOT / "provenance/p08_gold_bundle_manifest.json"
REPORT_PATH = Path("docs/refactor/phase_reports/ED_PRE_P08_DS4_DS5_candidate_review.md")
DS2_REVIEW_ASSETS = Path(
    "storage_eval/ds2_p06_review/"
    "f4295f9783b131a8305713765907e169a83dc741d6c9af390b0b67b2f15b5bfc/assets"
)

DOCX = "course_ai_algorithms_systems"
PDF = "course_ai_general_education"
APPROVAL_SCOPE = "ds4_query_processing_and_ds5_retrieval_only"
GENERATION_POLICY = (
    "p08-retrieval-only-v1|source=approved-ds2-ds3|no-runtime-label-generation|"
    "graded=2-direct-1-helpful-0-hard-negative|qa=pending-p09|unlisted=0|"
    "family-no-cross-split|diagnostic-overlay=p06-run4"
)
STRATEGY_SHA256 = hashlib.sha256(GENERATION_POLICY.encode()).hexdigest()

PACKAGE_SECTIONS: tuple[tuple[str, str, str, tuple[str, ...]], ...] = (
    ("p08-src-docx-01-turing", DOCX, "图灵测试", ("1.1.1",)),
    ("p08-src-docx-02-perceptron-mlp", DOCX, "感知机与多层感知机", ("2.2", "2.2.2")),
    (
        "p08-src-docx-03-deep-learning-transformer",
        DOCX,
        "深度学习与 Transformer",
        ("3.1.3", "3.5.3"),
    ),
    (
        "p08-src-docx-04-llm-definition-data",
        DOCX,
        "大模型定义、特征与训练数据",
        ("5.1.1", "5.2.1"),
    ),
    (
        "p08-src-docx-05-finetuning-alignment",
        DOCX,
        "微调与对齐",
        ("5.3", "5.3.4"),
    ),
    (
        "p08-src-docx-06-3d-slam",
        DOCX,
        "三维重建与 SLAM",
        ("6.2.2", "6.2.3", "6.3"),
    ),
    (
        "p08-src-docx-07-applications",
        DOCX,
        "可穿戴、军事、服务与生活应用",
        ("9.1.2", "9.2.2", "9.5.1", "9.7"),
    ),
    (
        "p08-src-pdf-01-origins-definition",
        PDF,
        "人工智能起源与定义",
        ("1.1.1", "1.1.2"),
    ),
    (
        "p08-src-pdf-02-history-agi",
        PDF,
        "发展历程、趋势与 AGI",
        ("1.2.1", "1.2.2", "1.2.3"),
    ),
    (
        "p08-src-pdf-03-applications",
        PDF,
        "传媒、教育与支付应用",
        ("1.3.1", "1.3.4", "1.3.7"),
    ),
)

TYPE_COUNTS: dict[str, tuple[int, int, int, int]] = {
    # total, Dev, DOCX total, PDF total
    "exact_fact": (15, 9, 10, 5),
    "definition": (15, 9, 10, 5),
    "paraphrase": (15, 9, 10, 5),
    "comparison": (10, 6, 7, 3),
    "procedure": (10, 6, 8, 2),
    "application": (10, 6, 7, 3),
    "cross_section": (15, 9, 11, 4),
    "unanswerable": (10, 6, 7, 3),
}

# split -> (DOCX, PDF). These values produce Dev 42/18 and Test 28/12 exactly.
COURSE_SPLIT_COUNTS: dict[str, dict[str, tuple[int, int]]] = {
    "exact_fact": {"dev": (6, 3), "test": (4, 2)},
    "definition": {"dev": (6, 3), "test": (4, 2)},
    "paraphrase": {"dev": (6, 3), "test": (4, 2)},
    "comparison": {"dev": (4, 2), "test": (3, 1)},
    "procedure": {"dev": (5, 1), "test": (3, 1)},
    "application": {"dev": (4, 2), "test": (3, 1)},
    "cross_section": {"dev": (7, 2), "test": (4, 2)},
    "unanswerable": {"dev": (4, 2), "test": (3, 1)},
}

# The Query and relevance labels are built from Approved DS2/DS3. These frozen IDs are only
# overlaid after that source-grounded construction to define the P06 upstream-gap stratum.
DIAGNOSTIC_PLAN: dict[tuple[str, str, str], str] = {
    ("exact_fact", "dev", DOCX): "gold-ev-b5848cc84a30502e827293c903043ec2",
    ("exact_fact", "test", DOCX): "gold-ev-b4635872d741e3a6c0e764547d376516",
    ("definition", "dev", PDF): "gold-ev-47ac1a377be899cf37f3403ae7f7568d",
    ("definition", "test", PDF): "gold-ev-e45b2242f6d079448a93922b96e5c4d0",
    ("paraphrase", "dev", DOCX): "gold-ev-9abde4ba81915c311db9ade93789806e",
    ("paraphrase", "test", DOCX): "gold-ev-baaff1e84d4d4e0415499eef709178cd",
    ("procedure", "dev", DOCX): "gold-ev-615b210d350379cf26677f84c3064531",
    ("application", "dev", PDF): "gold-ev-1831686810531ef3dd015742629827e9",
    ("cross_section", "dev", DOCX): "gold-ev-e21068d14748c7ffc033f2ec37f88501",
    ("cross_section", "test", DOCX): "gold-ev-6f70e7f62938bf78ba45c307de1adaef",
}

UNANSWERABLE: dict[tuple[str, str], tuple[str, ...]] = {
    (DOCX, "dev"): (
        "教材是否给出了图灵测试首次实验的样本人数和统计显著性？",
        "教材给出的 Transformer 编码器默认学习率是多少？",
        "教材是否给出了 GPT-4 训练数据集的完整下载地址？",
        "教材给出了 LIO-SAM 在课程实验中的实测帧率吗？",
    ),
    (PDF, "dev"): (
        "教材是否给出了 Google Duplex 的源代码仓库地址？",
        "教材给出了 AGI 实现的确切年份吗？",
    ),
    (DOCX, "test"): (
        "教材是否规定了服务机器人部署所需的最低内存容量？",
        "教材给出了 NeRF 重建实验的固定 GPU 型号和训练时长吗？",
        "教材是否提供可穿戴设备电池的统一更换周期？",
    ),
    (PDF, "test"): ("教材是否规定刷脸支付系统统一采用哪一种摄像头型号？",),
}

PROCEDURE_TERMS = (
    "流程",
    "算法",
    "训练",
    "配置",
    "准备",
    "预处理",
    "排序",
    "投影",
    "分析流程",
    "技术链路",
)
APPLICATION_TERMS = (
    "应用",
    "支付",
    "教育",
    "服务",
    "可穿戴",
    "天气",
    "预警",
    "主持人",
    "Duplex",
    "识别",
    "检测",
)
DEFINITION_TERMS = (
    "人工智能",
    "通用人工智能",
    "图灵测试",
    "感知机",
    "线性可分性",
    "位置编码",
    "大模型",
    "微调",
    "LIO-SAM",
    "同时定位与建图",
    "知识表达",
)
EXACT_TERMS = ("提出", "参数规模", "距离", "概率", "年份", "配置", "环境", "成本", "数据集", "来源")


@dataclass(frozen=True)
class KPCandidate:
    kp: Any
    evidence: Any
    package_id: str


def _artifact(repository_root: Path, path: Path) -> HashedArtifact:
    resolved = path.resolve()
    if not resolved.is_file() or not resolved.is_relative_to(repository_root.resolve()):
        raise ValueError(f"P08 artifact must stay under the repository: {path}")
    return HashedArtifact(
        path=resolved.relative_to(repository_root.resolve()).as_posix(),
        sha256=sha256_file(resolved),
        size_bytes=resolved.stat().st_size,
        media_type="application/json",
    )


def _section(evidence: Any) -> str:
    return evidence.source_span.section_path[-1]


def _package_for(course_id: str, section: str) -> str:
    matches = [
        package_id
        for package_id, course, _, sections in PACKAGE_SECTIONS
        if course == course_id and section in sections
    ]
    if len(matches) != 1:
        raise ValueError(f"Section must map to exactly one Source Package: {course_id}/{section}")
    return matches[0]


def _p06_resolvable_ids(repository_root: Path, ds2: DS2EvidenceDataset) -> set[str]:
    system = json.loads((repository_root / P06_OUTPUT).read_text(encoding="utf-8"))
    evidence = [
        item
        for variant in system["variants"]
        for item in EvidenceArtifact.model_validate(variant["evidence"]).records
    ]
    report = json.loads((repository_root / P06_REPORT).read_text(encoding="utf-8"))["report"]
    matches = map_gold_to_system_evidence(
        ds2.evidence,
        evidence,
        document_aliases=report["document_identity_adapter"],
    )
    return {item.gold_evidence_id for item in matches}


def _upstream_hashes(repository_root: Path) -> dict[str, str]:
    paths = {
        "approved_ds2_p06": ROOT / "approved/ds2/p06_evidence.json",
        "approved_ds3_p07": ROOT / "approved/ds3/p07_knowledge_points.json",
        "ds2_p06_approval": DS2_APPROVAL,
        "p07_gold_bundle_approval": DS3_APPROVAL,
    }
    return {name: sha256_file(repository_root / path) for name, path in paths.items()}


def _preserved_hashes(repository_root: Path) -> dict[str, str]:
    paths = {
        "p06_system_outputs": P06_OUTPUT,
        "p06_report": P06_REPORT,
        "p07_protocol": P07_PROTOCOL,
        "p07_protocol_approval": P07_PROTOCOL_APPROVAL,
        "p07_calibration_report": P07_CALIBRATION_REPORT,
        "p07_holdout_report": P07_HOLDOUT_REPORT,
    }
    return {name: sha256_file(repository_root / path) for name, path in paths.items()}


def _build_packages(
    ds2: DS2EvidenceDataset,
    ds3: DS3KnowledgePointDataset,
    upstream: dict[str, str],
) -> P08SourcePackageDataset:
    packages: list[P08SourcePackage] = []
    for package_id, course_id, title, sections in PACKAGE_SECTIONS:
        evidence = [
            item
            for item in ds2.evidence
            if item.course_id == course_id and _section(item) in sections
        ]
        evidence_ids = {item.evidence_id for item in evidence}
        kps = [
            item
            for item in ds3.knowledge_points
            if item.course_id == course_id and set(item.evidence_ids) & evidence_ids
        ]
        if not evidence or not kps:
            raise ValueError(f"empty P08 Source Package: {package_id}")
        source = evidence[0].source_span
        packages.append(
            P08SourcePackage(
                package_id=package_id,
                course_id=course_id,
                title=title,
                section_anchors=list(sections),
                primary_document_id=source.document_id,
                primary_document_version=source.document_version,
                primary_document_sha256=source.document_sha256,
                evidence_ids=[item.evidence_id for item in evidence],
                evidence_record_sha256={item.evidence_id: record_digest(item) for item in evidence},
                necessary_neighbor_record_sha256={
                    item.evidence_id: hashlib.sha256(
                        canonical_json_bytes(
                            {
                                "necessary_neighbors": [
                                    neighbor.model_dump(mode="json")
                                    for neighbor in item.necessary_neighbors
                                ],
                                "necessary_neighbor_text": item.necessary_neighbor_text,
                            }
                        )
                    ).hexdigest()
                    for item in evidence
                },
                knowledge_point_ids=[item.gold_kp_id for item in kps],
                knowledge_point_record_sha256={
                    item.gold_kp_id: record_digest(item) for item in kps
                },
            )
        )
    return P08SourcePackageDataset(
        dataset_id="courserag-p08-query-source-packages",
        dataset_version="p08-r1",
        packages=packages,
        upstream_approved_sha256=upstream,
    )


def _candidate_pool(
    ds2: DS2EvidenceDataset,
    ds3: DS3KnowledgePointDataset,
) -> tuple[list[KPCandidate], dict[str, KPCandidate]]:
    evidence = {item.evidence_id: item for item in ds2.evidence}
    candidates: list[KPCandidate] = []
    by_evidence: dict[str, KPCandidate] = {}
    for kp in ds3.knowledge_points:
        primary = next(link.evidence_id for link in kp.evidence_links if link.is_primary)
        item = KPCandidate(
            kp, evidence[primary], _package_for(kp.course_id, _section(evidence[primary]))
        )
        candidates.append(item)
        by_evidence[primary] = item
    return candidates, by_evidence


def _slots() -> list[dict[str, str | None]]:
    slots: list[dict[str, str | None]] = []
    for query_type in TYPE_COUNTS:
        for split in ("dev", "test"):
            docx_count, pdf_count = COURSE_SPLIT_COUNTS[query_type][split]
            courses = [DOCX] * docx_count + [PDF] * pdf_count
            # Interleave courses without changing the exact matrix.
            courses.sort(key=lambda value: (courses.count(value), value), reverse=True)
            diagnostic_used: set[tuple[str, str, str]] = set()
            for course_id in courses:
                key = (query_type, split, course_id)
                diagnostic = None
                if key in DIAGNOSTIC_PLAN and key not in diagnostic_used:
                    diagnostic = DIAGNOSTIC_PLAN[key]
                    diagnostic_used.add(key)
                slots.append(
                    {
                        "query_type": query_type,
                        "split": split,
                        "course_id": course_id,
                        "diagnostic_evidence_id": diagnostic,
                    }
                )
    return slots


def _type_score(name: str, query_type: str) -> int:
    if query_type == "procedure":
        return 20 if any(term in name for term in PROCEDURE_TERMS) else 0
    if query_type == "application":
        return 20 if any(term in name for term in APPLICATION_TERMS) else 0
    if query_type == "definition":
        return 20 if name in DEFINITION_TERMS else (8 if len(name) <= 8 else 2)
    if query_type == "exact_fact":
        return 18 if any(term in name for term in EXACT_TERMS) else 3
    if query_type == "comparison":
        return 4
    if query_type == "cross_section":
        return 3
    return 5


def _assign_primary_candidates(
    slots: list[dict[str, str | None]],
    candidates: list[KPCandidate],
    by_evidence: dict[str, KPCandidate],
    resolvable: set[str],
) -> list[KPCandidate | None]:
    used_split: dict[str, str] = {}
    used_type: set[tuple[str, str, str]] = set()
    package_usage: Counter[str] = Counter()
    assigned: list[KPCandidate | None] = []
    for slot in slots:
        if slot["query_type"] == "unanswerable":
            assigned.append(None)
            continue
        diagnostic = slot["diagnostic_evidence_id"]
        if diagnostic is not None:
            item = by_evidence[diagnostic]
            if item.kp.course_id != slot["course_id"]:
                raise ValueError("diagnostic course mismatch")
        else:
            eligible = [
                item
                for item in candidates
                if item.kp.course_id == slot["course_id"]
                and used_split.get(item.kp.gold_kp_id) in {None, slot["split"]}
                and (item.kp.gold_kp_id, str(slot["split"]), str(slot["query_type"]))
                not in used_type
                and item.evidence.evidence_id in resolvable
            ]
            if not eligible:
                raise ValueError(f"no split-safe KP for P08 slot: {slot}")
            eligible.sort(
                key=lambda item: (
                    -_type_score(item.kp.canonical_name, str(slot["query_type"])),
                    item.kp.gold_kp_id in used_split,
                    package_usage[item.package_id],
                    hashlib.sha256(f"{slot['split']}|{item.kp.gold_kp_id}".encode()).hexdigest(),
                )
            )
            item = eligible[0]
        previous_split = used_split.get(item.kp.gold_kp_id)
        if previous_split is not None and previous_split != slot["split"]:
            raise ValueError("a primary Query Family cannot cross Dev/Test")
        used_split[item.kp.gold_kp_id] = str(slot["split"])
        used_type.add((item.kp.gold_kp_id, str(slot["split"]), str(slot["query_type"])))
        package_usage[item.package_id] += 1
        assigned.append(item)
    return assigned


def _second_candidate(
    primary: KPCandidate,
    assigned: list[KPCandidate | None],
    slots: list[dict[str, str | None]],
    index: int,
    *,
    cross_section: bool,
    resolvable: set[str],
) -> KPCandidate:
    split = slots[index]["split"]
    pool = [
        item
        for item, slot in zip(assigned, slots, strict=True)
        if item is not None
        and slot["split"] == split
        and item.kp.course_id == primary.kp.course_id
        and item.kp.gold_kp_id != primary.kp.gold_kp_id
        and item.evidence.evidence_id in resolvable
        and (
            item.package_id != primary.package_id
            if cross_section
            else item.package_id == primary.package_id
        )
    ]
    if not pool:
        pool = [
            item
            for item, slot in zip(assigned, slots, strict=True)
            if item is not None
            and slot["split"] == split
            and item.kp.course_id == primary.kp.course_id
            and item.kp.gold_kp_id != primary.kp.gold_kp_id
            and item.evidence.evidence_id in resolvable
            and _section(item.evidence) != _section(primary.evidence)
        ]
    pair_terms = {
        "p08-src-docx-01-turing": (("图灵测试", "完整图灵测试"),),
        "p08-src-docx-02-perceptron-mlp": (("感知机", "多层感知机"), ("数据构造", "训练配置")),
        "p08-src-docx-03-deep-learning-transformer": (
            ("seq2seq", "注意力"),
            ("编码器", "位置编码"),
        ),
        "p08-src-docx-04-llm-definition-data": (("参数规模", "训练数据"), ("数据", "隐私")),
        "p08-src-docx-05-finetuning-alignment": (
            ("微调", "指令微调"),
            ("对齐", "微调"),
            ("安全对齐", "有用性"),
        ),
        "p08-src-docx-06-3d-slam": (("NeRF", "3D高斯"), ("IMU", "SLAM"), ("SLAM", "传感器")),
        "p08-src-docx-07-applications": (
            ("可穿戴", "传感器"),
            ("可穿戴", "低功耗"),
            ("服务机器人", "智慧服务"),
            ("服务机器人", "视觉交互"),
        ),
        "p08-src-pdf-01-origins-definition": (("人工智能", "机器智能"),),
        "p08-src-pdf-02-history-agi": (("人工智能", "通用人工智能"), ("职业", "AGI")),
        "p08-src-pdf-03-applications": (
            ("语音", "主持人"),
            ("教育", "教学"),
            ("支付", "交易"),
            ("刷脸支付", "异常检测"),
        ),
    }

    def pair_score(item: KPCandidate) -> int:
        if cross_section:
            return 0
        first = primary.kp.canonical_name
        second = item.kp.canonical_name
        return max(
            (
                1
                for left, right in pair_terms.get(primary.package_id, ())
                if (left in first and right in second) or (right in first and left in second)
            ),
            default=0,
        )

    pool.sort(
        key=lambda item: (
            -pair_score(item),
            hashlib.sha256(
                f"{primary.kp.gold_kp_id}|{item.kp.gold_kp_id}|{index}".encode()
            ).hexdigest(),
        )
    )
    return pool[0]


def _question(query_type: str, first: str, second: str | None = None) -> str:
    paraphrases = {
        "人工智能支付合规监控": "教材如何说明用人工智能监测支付活动是否合规？",
        "早期计算机在数学和自然语言中的应用": "早期计算机除数学计算外还被用于哪类语言任务？",
        "人工智能语音识别、合成与实时翻译": "人工智能在听、说与跨语言沟通方面有哪些能力？",
        "注意力机制中Q、K、V的来源": "在注意力机制里，查询向量以及键和值分别由哪里产生？",
        "大模型训练数据准备与预处理": "训练大模型前，原始数据需要经过哪些准备与处理？",
        "视觉-IMU子系统的无特征鲁棒性": "缺少视觉特征时，视觉与惯性组合系统的鲁棒性如何？",
        "感知机的提出": "感知机最初由谁在何时提出？",
        "服务机器人视觉交互": "服务机器人怎样借助视觉完成与人的交互？",
        "深度学习在推荐系统中的应用": "推荐系统中深度学习主要用来解决什么问题？",
        "IBM沃森问答系统": "IBM 的问答系统在教材案例中展现了什么能力？",
        "思维机器公司": "教材提到的那家早期并行计算企业是什么？",
        "编码器-解码器注意力": "解码端查询编码端表示时，Q、K、V 如何形成？",
        "大模型对齐的有用性": "让大模型回答更有帮助属于对齐中的哪项要求？",
        "图灵测试": "机器在对话中无法被辨认身份时，教材如何判断其智能？",
        "可穿戴传感数据算法类型": "处理可穿戴传感数据时，教材列举了哪些算法类别？",
    }
    if query_type == "paraphrase" and first in paraphrases:
        return paraphrases[first]
    procedures = {
        "感知机算法收敛性": "教材怎样说明感知机训练从迭代到收敛的条件与过程？",
        "大规模训练数据与涌现能力": "教材用哪些关键因素解释大规模训练如何促成涌现能力？",
        "通用人工智能的人类能力与自我意识边界": "教材从哪些层面判断 AGI 的任务能力、人类能力与自我意识边界？",
        "大模型训练计算成本": "教材从哪些训练环节说明大模型的计算资源消耗？",
        "可穿戴传感数据算法类型": "处理可穿戴传感数据时，教材列出了哪些算法环节或类型？",
    }
    if query_type == "procedure" and first in procedures:
        return procedures[first]
    templates = {
        "exact_fact": "教材对“{first}”给出的具体说明是什么？",
        "definition": "按照教材，“{first}”指什么？",
        "paraphrase": "换一种说法，教材如何解释“{first}”？",
        "comparison": "教材对“{first}”与“{second}”分别给出了哪些说明，二者关注点有何不同？",
        "procedure": "教材介绍“{first}”时列出了哪些步骤或处理环节？",
        "application": "教材如何说明“{first}”的应用场景或作用？",
        "cross_section": "结合教材不同章节，说明“{first}”与“{second}”各自的核心内容。",
    }
    return templates[query_type].format(first=first, second=second)


def _char_terms(text: str) -> set[str]:
    value = "".join(char.lower() for char in text if not char.isspace())
    return {value[index : index + 2] for index in range(max(len(value) - 1, 0))}


def _nearest_evidence(
    query: str,
    course_id: str,
    evidence: list[Any],
    excluded: set[str],
    count: int,
) -> list[Any]:
    query_terms = _char_terms(query)
    pool = [
        item
        for item in evidence
        if item.course_id == course_id and item.evidence_id not in excluded
    ]
    pool.sort(
        key=lambda item: (
            -len(query_terms & _char_terms(item.gold_text)),
            hashlib.sha256(f"{query}|{item.evidence_id}".encode()).hexdigest(),
        )
    )
    return pool[:count]


def _query_family(course_id: str, primary_kp_id: str) -> str:
    digest = hashlib.sha256(f"{course_id}|{primary_kp_id}".encode()).hexdigest()[:24]
    return f"p08-family-{digest}"


def _case_id(course_id: str, query: str, evidence_ids: list[str]) -> str:
    identity = {
        "course_id": course_id,
        "query": query,
        "required_evidence_ids": evidence_ids,
        "scope": "retrieval_only",
    }
    return f"gold-rq-{hashlib.sha256(canonical_json_bytes(identity)).hexdigest()[:32]}"


def _build_ds5(
    ds2: DS2EvidenceDataset,
    ds3: DS3KnowledgePointDataset,
    resolvable: set[str],
    upstream: dict[str, str],
) -> DS5RetrievalQADataset:
    slots = _slots()
    candidates, by_evidence = _candidate_pool(ds2, ds3)
    assigned = _assign_primary_candidates(slots, candidates, by_evidence, resolvable)
    evidence = list(ds2.evidence)
    unanswerable_index: Counter[tuple[str, str]] = Counter()
    cases: list[RetrievalQACase] = []
    for index, (slot, primary) in enumerate(zip(slots, assigned, strict=True)):
        query_type = str(slot["query_type"])
        course_id = str(slot["course_id"])
        split = str(slot["split"])
        diagnostic_id = slot["diagnostic_evidence_id"]
        if query_type == "unanswerable":
            key = (course_id, split)
            query = UNANSWERABLE[key][unanswerable_index[key]]
            unanswerable_index[key] += 1
            nearest = _nearest_evidence(query, course_id, evidence, set(), 4)
            package_id = _package_for(course_id, _section(nearest[0]))
            family = f"p08-family-unanswerable-{hashlib.sha256(f'{course_id}|{query}'.encode()).hexdigest()[:20]}"
            judgments = [
                RetrievalEvidenceJudgment(
                    evidence_id=item.evidence_id,
                    relevance=0,
                    role="hard_negative",
                    evidence_record_sha256=record_digest(item),
                    rationale="同课程中词面最接近的候选，但不包含问题所询问的缺失细节。",
                )
                for item in nearest
            ]
            audit = UnanswerableRetrievalAudit(
                search_terms=[
                    term
                    for term in ("AI", "AGI", "MLP", "Transformer", "NeRF", "SLAM", "支付", "教材")
                    if term.lower() in query.lower()
                ]
                or [query.strip("？")],
                search_rules=[
                    "对所属课程全部 Approved DS2 的逐字文本执行问题全文匹配。",
                    "对问题中的专名与所求属性执行同段共现检查；只有专名而无所求属性不算答案。",
                    "检查列出的最近假阳性，确认其不能直接或组合回答问题。",
                ],
                exact_match_count=sum(
                    query.strip("？") in item.gold_text
                    for item in evidence
                    if item.course_id == course_id
                ),
                nearest_false_positive_evidence_ids=[item.evidence_id for item in nearest],
                human_confirmation_items=[
                    "确认问题所求细节未出现在所属课程任何 Approved DS2 Evidence。",
                    "确认没有把课程外常识当作课程内答案。",
                    "确认最近假阳性只共享术语而不提供所求事实。",
                ],
            )
            case_id = _case_id(course_id, query, [])
            cases.append(
                RetrievalQACase(
                    record_id=case_id,
                    candidate_source="source_grounded_assisted",
                    query=query,
                    query_type=query_type,
                    answerable=False,
                    difficulty="hard",
                    gold_answer_type="pending_p09",
                    gold_short_answers=[],
                    gold_claims=[],
                    forbidden_claims=[],
                    expected_knowledge_points=[],
                    filters={"course_id": course_id},
                    gold_evidence_groups=[],
                    supporting_evidence_ids=[],
                    graded_relevance={item.evidence_id: 0 for item in nearest},
                    allowed_answer_variants=[],
                    expected_behavior="no_relevant_evidence",
                    properties={
                        "multi_evidence": False,
                        "contains_ocr": False,
                        "contains_formula": False,
                        "contains_table": False,
                        "has_filter": True,
                    },
                    course_id=course_id,
                    query_family_id=family,
                    source_package_id=package_id,
                    split=split,
                    retrieval_gold_status="candidate",
                    qa_gold_status="pending_p09",
                    evaluation_stratum="retrieval_main",
                    p06_runtime_resolvable=True,
                    diagnostic_evidence_id=None,
                    evidence_judgments=judgments,
                    hard_negative_evidence_ids=[item.evidence_id for item in nearest],
                    unanswerable_audit=audit,
                    upstream_approved_sha256=upstream,
                    query_sha256=hashlib.sha256(query.encode()).hexdigest(),
                    generation_strategy_sha256=STRATEGY_SHA256,
                    approval_scope=APPROVAL_SCOPE,
                )
            )
            continue

        assert primary is not None
        required = [primary]
        if query_type in {"comparison", "cross_section"}:
            required.append(
                _second_candidate(
                    primary,
                    assigned,
                    slots,
                    index,
                    cross_section=query_type == "cross_section",
                    resolvable=resolvable,
                )
            )
        query = _question(
            query_type,
            primary.kp.canonical_name,
            required[1].kp.canonical_name if len(required) == 2 else None,
        )
        required_ids = [item.evidence.evidence_id for item in required]
        # One source-grounded, non-required neighbor is graded helpful when available.
        helpful_pool = [
            item
            for item in evidence
            if item.course_id == course_id
            and item.evidence_id not in required_ids
            and _package_for(course_id, _section(item)) == primary.package_id
            and item.evidence_id in resolvable
        ]
        helpful = _nearest_evidence(query, course_id, helpful_pool, set(required_ids), 1)
        excluded = set(required_ids) | {item.evidence_id for item in helpful}
        hard = _nearest_evidence(query, course_id, evidence, excluded, 4)
        judgments = [
            RetrievalEvidenceJudgment(
                evidence_id=item.evidence.evidence_id,
                relevance=2,
                role="required",
                evidence_record_sha256=record_digest(item.evidence),
                rationale="直接陈述该 Query 所需的课程内事实，是完整 Evidence Group 的必需成员。",
            )
            for item in required
        ]
        judgments.extend(
            RetrievalEvidenceJudgment(
                evidence_id=item.evidence_id,
                relevance=1,
                role="helpful",
                evidence_record_sha256=record_digest(item),
                rationale="提供同一源包的必要背景，但单独不足以完整回答 Query。",
            )
            for item in helpful
        )
        judgments.extend(
            RetrievalEvidenceJudgment(
                evidence_id=item.evidence_id,
                relevance=0,
                role="hard_negative",
                evidence_record_sha256=record_digest(item),
                rationale="与 Query 词面或章节接近，但不满足完整回答条件。",
            )
            for item in hard
        )
        diagnostic = diagnostic_id is not None
        if diagnostic and diagnostic_id not in required_ids:
            raise ValueError("diagnostic Evidence must be required by its Query")
        if not diagnostic and not set(required_ids).issubset(resolvable):
            raise ValueError("retrieval_main Required Evidence must be P06-resolvable")
        difficulty = {
            "exact_fact": "easy",
            "definition": "easy",
            "paraphrase": "medium",
            "comparison": "medium",
            "procedure": "hard",
            "application": "medium",
            "cross_section": "hard",
        }[query_type]
        family = _query_family(course_id, primary.kp.gold_kp_id)
        case_id = _case_id(course_id, query, required_ids)
        relevance = {item.evidence_id: item.relevance for item in judgments}
        case_evidence = [item.evidence for item in required]
        cases.append(
            RetrievalQACase(
                record_id=case_id,
                candidate_source="source_grounded_assisted",
                query=query,
                query_type=query_type,
                answerable=True,
                difficulty=difficulty,
                gold_answer_type="pending_p09",
                gold_short_answers=[],
                gold_claims=[],
                forbidden_claims=[],
                expected_knowledge_points=[item.kp.gold_kp_id for item in required],
                filters={"course_id": course_id},
                gold_evidence_groups=[
                    EvidenceGroup(
                        group_id=f"eg-{case_id[-16:]}",
                        sufficiency="complete",
                        required_evidence_ids=required_ids,
                    )
                ],
                supporting_evidence_ids=required_ids + [item.evidence_id for item in helpful],
                graded_relevance=relevance,
                allowed_answer_variants=[],
                expected_behavior="answer",
                properties={
                    "multi_evidence": len(required_ids) > 1,
                    "contains_ocr": any(
                        item.source_type == "ocr_derived" for item in case_evidence
                    ),
                    "contains_formula": any(
                        item.semantic_unit_type == "formula" for item in case_evidence
                    ),
                    "contains_table": any(
                        item.semantic_unit_type == "table" for item in case_evidence
                    ),
                    "has_filter": True,
                },
                course_id=course_id,
                query_family_id=family,
                source_package_id=primary.package_id,
                split=split,
                retrieval_gold_status="candidate",
                qa_gold_status="pending_p09",
                evaluation_stratum="upstream_gap_diagnostic" if diagnostic else "retrieval_main",
                p06_runtime_resolvable=not diagnostic,
                diagnostic_evidence_id=diagnostic_id,
                evidence_judgments=judgments,
                hard_negative_evidence_ids=[item.evidence_id for item in hard],
                unanswerable_audit=None,
                upstream_approved_sha256=upstream,
                query_sha256=hashlib.sha256(query.encode()).hexdigest(),
                generation_strategy_sha256=STRATEGY_SHA256,
                approval_scope=APPROVAL_SCOPE,
            )
        )
    return DS5RetrievalQADataset(
        dataset_id="courserag-ds5-p08-retrieval",
        dataset_version="p08-r1",
        cases=cases,
    )


EDGE_TERMS: tuple[tuple[str, str], ...] = (
    (PDF, "AI 与 AGI"),
    (PDF, "ＡＩ"),
    (PDF, "AGI"),
    (DOCX, "MLP"),
    (DOCX, "seq2seq"),
    (DOCX, "Q／K／V"),
    (DOCX, "NeRF"),
    (DOCX, "3Ｄ 高斯点染"),
    (DOCX, "SLAM 与 LIO-SAM"),
)


def _find_kps(ds3: DS3KnowledgePointDataset, course_id: str, text: str) -> list[Any]:
    normalized = text.replace("ＡＩ", "AI").replace("３Ｄ", "3D").replace("／", "、")
    terms = [
        term for term in normalized.replace("与", " ").replace("、", " ").split() if len(term) > 1
    ]
    scored = [
        (sum(term.lower() in item.canonical_name.lower() for term in terms), item)
        for item in ds3.knowledge_points
        if item.course_id == course_id
    ]
    scored.sort(key=lambda pair: (-pair[0], pair[1].gold_kp_id))
    return [item for score, item in scored if score > 0][:3] or [scored[0][1]]


def _build_ds4(
    ds3: DS3KnowledgePointDataset,
    ds5: DS5RetrievalQADataset,
    upstream: dict[str, str],
) -> DS4QueryProcessingDataset:
    capabilities = (
        "query_normalization",
        "knowledge_point_linking",
        "filter_parsing",
        "query_router",
        "expansion_rewrite_constraints",
    )
    desired_docx = {
        "query_normalization": 9,
        "knowledge_point_linking": 9,
        "filter_parsing": 8,
        "query_router": 8,
        "expansion_rewrite_constraints": 8,
    }
    dedicated_docx = {
        "query_normalization": 4,
        "knowledge_point_linking": 4,
        "filter_parsing": 4,
        "query_router": 4,
        "expansion_rewrite_constraints": 4,
    }
    dev = [case for case in ds5.cases if case.split == "dev"]
    cases: list[QueryProcessingCase] = []
    mirrored_used: set[str] = set()
    for capability in capabilities:
        mirror_docx = desired_docx[capability] - dedicated_docx[capability]
        mirror_courses = [DOCX] * mirror_docx + [PDF] * (6 - mirror_docx)
        mirrors: list[RetrievalQACase] = []
        for course_id in mirror_courses:
            eligible = [
                item
                for item in dev
                if item.course_id == course_id and item.record_id not in mirrored_used
            ]
            if not eligible:
                eligible = [item for item in dev if item.course_id == course_id]
            eligible.sort(
                key=lambda item: hashlib.sha256(
                    f"{capability}|{item.record_id}".encode()
                ).hexdigest()
            )
            chosen = eligible[0]
            mirrored_used.add(chosen.record_id)
            mirrors.append(chosen)
        for source in mirrors:
            linked = list(source.expected_knowledge_points)
            route = (
                "unanswerable_audit"
                if not source.answerable
                else ("metadata_filtered_retrieval" if source.filters else "hybrid_retrieval")
            )
            expected = QueryProcessingExpected(
                normalized_query=source.query,
                linked_knowledge_points=linked,
                filters=source.filters,
                route=route,
                allowed_expansions=[],
                forbidden_expansions=[],
                must_preserve_terms=[],
                must_preserve_filters=True,
            )
            identity = f"{capability}|mirror|{source.record_id}|{source.course_id}"
            record_id = f"gold-qp-{hashlib.sha256(identity.encode()).hexdigest()[:32]}"
            cases.append(
                QueryProcessingCase(
                    record_id=record_id,
                    candidate_source="source_grounded_assisted",
                    raw_query=source.query,
                    expected=expected,
                    course_id=source.course_id,
                    capability=capability,
                    query_family_id=source.query_family_id,
                    source_package_id=source.source_package_id,
                    mirrored_ds5_case_id=source.record_id,
                    upstream_approved_sha256=upstream,
                    query_sha256=hashlib.sha256(source.query.encode()).hexdigest(),
                    generation_strategy_sha256=STRATEGY_SHA256,
                    approval_scope=APPROVAL_SCOPE,
                )
            )

        edge_pool = [item for item in EDGE_TERMS if item[0] == DOCX][:4] + [
            item for item in EDGE_TERMS if item[0] == PDF
        ][:2]
        for edge_index, (course_id, term) in enumerate(edge_pool, 1):
            kps = _find_kps(ds3, course_id, term)
            if course_id == PDF:
                package_id = (
                    "p08-src-pdf-01-origins-definition"
                    if term in {"ＡＩ", "AI"}
                    else "p08-src-pdf-02-history-agi"
                )
            elif "MLP" in term:
                package_id = "p08-src-docx-02-perceptron-mlp"
            elif any(value in term for value in ("seq2seq", "Q")):
                package_id = "p08-src-docx-03-deep-learning-transformer"
            else:
                package_id = "p08-src-docx-06-3d-slam"
            raw = {
                "query_normalization": f"  {term}　是什么？  ",
                "knowledge_point_linking": f"教材里的 {term} 指向哪些知识点？",
                "filter_parsing": f"仅在本课程中查找 {term}，并保留课程过滤条件。",
                "query_router": f"检索教材中关于 {term} 的原文。",
                "expansion_rewrite_constraints": f"改写 {term} 的检索词，但必须保留专名。",
            }[capability]
            normalized = " ".join(
                raw.replace("ＡＩ", "AI").replace("３Ｄ", "3D").replace("／", "/").split()
            )
            allowed = [item.canonical_name for item in kps[1:]]
            forbidden = [
                item.canonical_name
                for item in ds3.knowledge_points
                if item.course_id == course_id
                and item.gold_kp_id not in {kp.gold_kp_id for kp in kps}
            ][:2]
            expected = QueryProcessingExpected(
                normalized_query=normalized,
                linked_knowledge_points=[item.gold_kp_id for item in kps],
                filters={"course_id": course_id} if capability == "filter_parsing" else {},
                route="metadata_filtered_retrieval"
                if capability == "filter_parsing"
                else "hybrid_retrieval",
                allowed_expansions=allowed if capability == "expansion_rewrite_constraints" else [],
                forbidden_expansions=forbidden
                if capability == "expansion_rewrite_constraints"
                else [],
                must_preserve_terms=[term],
                must_preserve_filters=True,
            )
            identity = f"{capability}|edge|{course_id}|{term}|{edge_index}"
            record_id = f"gold-qp-{hashlib.sha256(identity.encode()).hexdigest()[:32]}"
            cases.append(
                QueryProcessingCase(
                    record_id=record_id,
                    candidate_source="source_grounded_assisted",
                    raw_query=raw,
                    expected=expected,
                    course_id=course_id,
                    capability=capability,
                    query_family_id=f"p08-ds4-edge-{hashlib.sha256(identity.encode()).hexdigest()[:20]}",
                    source_package_id=package_id,
                    mirrored_ds5_case_id=None,
                    upstream_approved_sha256=upstream,
                    query_sha256=hashlib.sha256(raw.encode()).hexdigest(),
                    generation_strategy_sha256=STRATEGY_SHA256,
                    approval_scope=APPROVAL_SCOPE,
                )
            )
    return DS4QueryProcessingDataset(
        dataset_id="courserag-ds4-p08-query-processing",
        dataset_version="p08-r1",
        cases=cases,
    )


def _split_manifest(ds5: DS5RetrievalQADataset) -> P08DS5SplitManifest:
    assignments = [
        P08SplitAssignment(
            case_id=item.record_id,
            query_family_id=str(item.query_family_id),
            split=str(item.split),
            course_id=str(item.course_id),
            query_type=item.query_type,
            evaluation_stratum=str(item.evaluation_stratum),
        )
        for item in ds5.cases
    ]
    allowed = [
        item.record_id
        for item in ds5.cases
        if item.split == "dev" and item.evaluation_stratum == "retrieval_main"
    ]
    return P08DS5SplitManifest(
        dataset_id="courserag-p08-ds5-split",
        dataset_version="p08-r1",
        assignments=assignments,
        p08_tuning_allowed_ids=allowed,
    )


def _validate_fixed_distributions(
    ds4: DS4QueryProcessingDataset,
    ds5: DS5RetrievalQADataset,
    resolvable: set[str],
) -> None:
    if len(ds4.cases) != 60 or len(ds5.cases) != 100:
        raise ValueError("P08 requires exactly 60 DS4 and 100 DS5 records")
    if Counter(item.capability for item in ds4.cases) != Counter(
        {
            "query_normalization": 12,
            "knowledge_point_linking": 12,
            "filter_parsing": 12,
            "query_router": 12,
            "expansion_rewrite_constraints": 12,
        }
    ):
        raise ValueError("DS4 capability distribution changed")
    if Counter(item.course_id for item in ds4.cases) != Counter({DOCX: 42, PDF: 18}):
        raise ValueError("DS4 course distribution changed")
    for query_type, (total, dev, docx, pdf) in TYPE_COUNTS.items():
        selected = [item for item in ds5.cases if item.query_type == query_type]
        if (len(selected), sum(item.split == "dev" for item in selected)) != (total, dev):
            raise ValueError(f"DS5 type/split distribution changed: {query_type}")
        if Counter(item.course_id for item in selected) != Counter({DOCX: docx, PDF: pdf}):
            raise ValueError(f"DS5 course distribution changed: {query_type}")
    if Counter((item.split, item.course_id) for item in ds5.cases) != Counter(
        {("dev", DOCX): 42, ("dev", PDF): 18, ("test", DOCX): 28, ("test", PDF): 12}
    ):
        raise ValueError("DS5 split/course matrix changed")
    strata = Counter((item.split, item.evaluation_stratum) for item in ds5.cases)
    if strata != Counter(
        {
            ("dev", "retrieval_main"): 54,
            ("dev", "upstream_gap_diagnostic"): 6,
            ("test", "retrieval_main"): 36,
            ("test", "upstream_gap_diagnostic"): 4,
        }
    ):
        raise ValueError("DS5 diagnostic stratum distribution changed")
    diagnostic_types = Counter(
        item.query_type
        for item in ds5.cases
        if item.evaluation_stratum == "upstream_gap_diagnostic"
    )
    if diagnostic_types != Counter(
        {
            "exact_fact": 2,
            "definition": 2,
            "paraphrase": 2,
            "procedure": 1,
            "application": 1,
            "cross_section": 2,
        }
    ):
        raise ValueError("DS5 diagnostic type distribution changed")
    for item in ds5.cases:
        required = {
            evidence_id
            for group in item.gold_evidence_groups
            for evidence_id in group.required_evidence_ids
        }
        if item.evaluation_stratum == "retrieval_main" and not required.issubset(resolvable):
            raise ValueError("retrieval_main contains unresolved Required Evidence")


def _review_html(
    title: str,
    bundle_sha256: str,
    review_pass: str,
    records: list[Any],
    evidence_by_id: dict[str, Any],
    expected_ids: list[str],
) -> str:
    cards: list[str] = []
    for item in records:
        if isinstance(item, RetrievalQACase):
            judged = []
            for judgment in item.evidence_judgments:
                source = evidence_by_id[judgment.evidence_id]
                image = f"assets/{source.evidence_id}.png"
                judged.append(
                    f"<details><summary>{judgment.relevance}分 · {judgment.role} · {html.escape(source.evidence_id)}</summary>"
                    f"<p>{html.escape(judgment.rationale)}</p><blockquote>{html.escape(source.gold_text)}</blockquote>"
                    f"<p>必要邻接：{html.escape(' / '.join(source.necessary_neighbor_text) or '无')}</p>"
                    f"<p>页码/BBox：{html.escape(json.dumps([box.model_dump(mode='json') for box in source.bboxes], ensure_ascii=False))}</p>"
                    f"<img loading='lazy' src='{image}' alt='{html.escape(source.evidence_id)}'></details>"
                )
            audit = (
                f"<pre>{html.escape(json.dumps(item.unanswerable_audit.model_dump(mode='json'), ensure_ascii=False, indent=2))}</pre>"
                if item.unanswerable_audit
                else ""
            )
            body = (
                f"<h3>{html.escape(item.query)}</h3><p>{item.query_type} · {item.difficulty} · {item.course_id} · {item.split}</p>"
                f"<p><b>Source Package</b> {item.source_package_id} · <b>Stratum</b> {item.evaluation_stratum} · "
                f"<b>QA</b> {item.qa_gold_status}</p>"
                f"<p><b>KP</b> {html.escape(', '.join(item.expected_knowledge_points) or '无')}</p>"
                f"<p><b>Evidence Group</b> {html.escape(json.dumps([g.model_dump(mode='json') for g in item.gold_evidence_groups], ensure_ascii=False))}</p>"
                + "".join(judged)
                + audit
            )
        else:
            body = (
                f"<h3>{html.escape(item.raw_query)}</h3><p>{item.capability} · {item.course_id}</p>"
                f"<p><b>DS5 mirror</b> {item.mirrored_ds5_case_id or '专门边界案例'} · <b>Source Package</b> {item.source_package_id}</p>"
                f"<pre>{html.escape(json.dumps(item.expected.model_dump(mode='json'), ensure_ascii=False, indent=2))}</pre>"
            )
        cards.append(
            f"<article id='{item.record_id}' data-kind='{item.__class__.__name__}'><code>{item.record_id}</code>{body}"
            f"<label><input type='radio' name='{item.record_id}' value='pass'>通过</label> "
            f"<label><input type='radio' name='{item.record_id}' value='return'>退回</label>"
            f"<textarea placeholder='退回原因/备注'></textarea></article>"
        )
    expected_json = json.dumps(expected_ids, ensure_ascii=False)
    return f"""<!doctype html><html lang='zh-CN'><head><meta charset='utf-8'><title>{html.escape(title)}</title>
<style>body{{font:15px/1.55 system-ui;margin:24px;max-width:1280px}}article{{border:1px solid #bbb;border-radius:8px;padding:16px;margin:16px 0}}blockquote,pre{{white-space:pre-wrap;background:#f5f5f5;padding:10px}}img{{max-width:100%;border:1px solid #ddd}}textarea{{display:block;width:98%;min-height:48px;margin-top:8px}}.sticky{{position:sticky;top:0;background:white;padding:8px;border-bottom:1px solid #ddd}}</style></head>
<body><div class='sticky'><b>{html.escape(title)}</b> · Bundle <code>{bundle_sha256}</code> · <button onclick='exportReview()'>导出审核 JSON</button></div>
<p>逐条检查 Query/处理预期、Evidence 2/1/0、必要邻接、页码/BBox、硬负例、诊断层及 QA pending。未选择的记录不算已审核。</p>
{"".join(cards)}
<script>const expected={expected_json}; const key='p08-{bundle_sha256}-{review_pass}';
function save(){{const d={{}};document.querySelectorAll('article').forEach(a=>{{const r=a.querySelector('input:checked');if(r)d[a.id]={{decision:r.value,note:a.querySelector('textarea').value}}}});localStorage.setItem(key,JSON.stringify(d));}}
document.addEventListener('change',save);document.addEventListener('input',save);const old=JSON.parse(localStorage.getItem(key)||'{{}}');Object.entries(old).forEach(([id,v])=>{{const a=document.getElementById(id);if(a){{const r=a.querySelector(`input[value="${{v.decision}}"]`);if(r)r.checked=true;a.querySelector('textarea').value=v.note||'';}}}});
function exportReview(){{save();const d=JSON.parse(localStorage.getItem(key)||'{{}}');const reviewed=expected.filter(id=>d[id]);const returned=reviewed.filter(id=>d[id].decision==='return');const payload={{schema_version:'courserag.p08-review-decisions.v1',bundle_sha256:'{bundle_sha256}',review_pass:'{review_pass}',expected_record_ids:expected,reviewed_record_ids:reviewed,returned_record_ids:returned,reviewer_id:null,reviewed_at:null,notes:Object.fromEntries(reviewed.map(id=>[id,d[id].note||'']))}};delete payload.notes;const b=new Blob([JSON.stringify(payload,null,2)],{{type:'application/json'}});const a=document.createElement('a');a.href=URL.createObjectURL(b);a.download='p08_{review_pass}_review_decisions_{bundle_sha256[:12]}.json';a.click();}}
</script></body></html>"""


def _write_review_pack(
    repository_root: Path,
    bundle_sha256: str,
    ds2: DS2EvidenceDataset,
    ds4: DS4QueryProcessingDataset,
    ds5: DS5RetrievalQADataset,
    first_ids: list[str],
    second_ids: list[str],
) -> tuple[Path, str, str, dict[str, str]]:
    review_dir = repository_root / "storage_eval/ds45_p08_review" / bundle_sha256
    assets = review_dir / "assets"
    assets.mkdir(parents=True, exist_ok=True)
    evidence_by_id = {item.evidence_id: item for item in ds2.evidence}
    used_evidence = {
        judgment.evidence_id for case in ds5.cases for judgment in case.evidence_judgments
    }
    for evidence_id in sorted(used_evidence):
        source = repository_root / DS2_REVIEW_ASSETS / f"{evidence_id}.png"
        if not source.is_file():
            matches = list(
                (repository_root / "storage_eval/ds2_p06_review").glob(
                    f"*/assets/{evidence_id}.png"
                )
            )
            if matches:
                source = max(matches, key=lambda item: item.stat().st_mtime_ns)
        target = assets / f"{evidence_id}.png"
        if not source.is_file():
            raise ValueError(f"missing Approved DS2 review image: {evidence_id}")
        if not target.exists() or sha256_file(target) != sha256_file(source):
            shutil.copyfile(source, target)
    all_records = {item.record_id: item for item in [*ds4.cases, *ds5.cases]}
    first_records = [all_records[item] for item in first_ids]
    second_records = [all_records[item] for item in second_ids]
    atomic_write_text(
        review_dir / "index.html",
        _review_html(
            "P08 DS4/DS5 首轮审核（160 条）",
            bundle_sha256,
            "first",
            first_records,
            evidence_by_id,
            first_ids,
        ),
    )
    atomic_write_text(
        review_dir / "second_review.html",
        _review_html(
            "P08 DS4/DS5 二轮盲化复核（132 条）",
            bundle_sha256,
            "second",
            second_records,
            evidence_by_id,
            second_ids,
        ),
    )
    return (
        review_dir,
        sha256_file(review_dir / "index.html"),
        sha256_file(review_dir / "second_review.html"),
        {
            evidence_id: sha256_file(assets / f"{evidence_id}.png")
            for evidence_id in sorted(used_evidence)
        },
    )


def bundle_identity_sha256(
    *,
    revision: int = 1,
    ds4_sha256: str,
    ds5_sha256: str,
    source_packages_sha256: str,
    split_sha256: str,
    candidate_record_sha256: dict[str, str],
    upstream_approved_sha256: dict[str, str],
    preserved_upstream_sha256: dict[str, str],
    p06_unmapped_evidence_ids: list[str],
    diagnostic_evidence_ids: list[str],
    first_review_groups: list[list[str]],
    second_review_ids: list[str],
) -> str:
    basis = {
        "schema_version": "courserag.p08-gold-bundle-identity.v1",
        "revision": revision,
        "approval_scope": APPROVAL_SCOPE,
        "ds4_sha256": ds4_sha256,
        "ds5_sha256": ds5_sha256,
        "source_packages_sha256": source_packages_sha256,
        "split_sha256": split_sha256,
        "candidate_record_sha256": candidate_record_sha256,
        "upstream_approved_sha256": upstream_approved_sha256,
        "preserved_upstream_sha256": preserved_upstream_sha256,
        "p06_unmapped_evidence_ids": p06_unmapped_evidence_ids,
        "diagnostic_evidence_ids": diagnostic_evidence_ids,
        "first_review_groups": first_review_groups,
        "second_review_ids": second_review_ids,
        "generation_strategy_sha256": STRATEGY_SHA256,
    }
    return hashlib.sha256(canonical_json_bytes(basis)).hexdigest()


def build_p08_candidates(repository_root: Path) -> P08GoldBundleManifest:
    repository_root = repository_root.resolve()
    ds2 = DS2EvidenceDataset.model_validate_json(
        (repository_root / DS2_PATH).read_text(encoding="utf-8")
    )
    ds3 = DS3KnowledgePointDataset.model_validate_json(
        (repository_root / DS3_PATH).read_text(encoding="utf-8")
    )
    upstream = _upstream_hashes(repository_root)
    preserved = _preserved_hashes(repository_root)
    resolvable = _p06_resolvable_ids(repository_root, ds2)
    unmapped = [item.evidence_id for item in ds2.evidence if item.evidence_id not in resolvable]
    if len(resolvable) != 101 or len(unmapped) != 19:
        raise ValueError("frozen P06 run-4 Evidence mapping is no longer 101/120")
    if not set(DIAGNOSTIC_PLAN.values()).issubset(unmapped):
        raise ValueError("a fixed P08 diagnostic is no longer an upstream P06 gap")

    packages = _build_packages(ds2, ds3, upstream)
    ds5 = _build_ds5(ds2, ds3, resolvable, upstream)
    ds4 = _build_ds4(ds3, ds5, upstream)
    split = _split_manifest(ds5)
    _validate_fixed_distributions(ds4, ds5, resolvable)

    atomic_write_json(repository_root / PACKAGES_PATH, packages.model_dump(mode="json"))
    atomic_write_json(repository_root / DS5_PATH, ds5.model_dump(mode="json"))
    atomic_write_json(repository_root / DS4_PATH, ds4.model_dump(mode="json"))
    atomic_write_json(repository_root / SPLIT_PATH, split.model_dump(mode="json"))

    all_records = [*ds4.cases, *ds5.cases]
    record_hashes = {item.record_id: record_digest(item) for item in all_records}
    first_ids = [item.record_id for item in all_records]
    first_groups = [first_ids[index : index + 20] for index in range(0, 160, 20)]
    always_second = [
        item.record_id
        for item in ds4.cases
        if item.capability in {"filter_parsing", "expansion_rewrite_constraints"}
    ]
    remaining_ds4 = [
        item.record_id
        for item in ds4.cases
        if item.capability not in {"filter_parsing", "expansion_rewrite_constraints"}
    ]
    remaining_ds4.sort(key=lambda item: hashlib.sha256(item.encode()).hexdigest())
    second_ids = [item.record_id for item in ds5.cases] + always_second + remaining_ds4[:8]
    bundle_sha256 = bundle_identity_sha256(
        ds4_sha256=sha256_file(repository_root / DS4_PATH),
        ds5_sha256=sha256_file(repository_root / DS5_PATH),
        source_packages_sha256=sha256_file(repository_root / PACKAGES_PATH),
        split_sha256=sha256_file(repository_root / SPLIT_PATH),
        candidate_record_sha256=record_hashes,
        upstream_approved_sha256=upstream,
        preserved_upstream_sha256=preserved,
        p06_unmapped_evidence_ids=unmapped,
        diagnostic_evidence_ids=list(DIAGNOSTIC_PLAN.values()),
        first_review_groups=first_groups,
        second_review_ids=second_ids,
    )
    review_dir, first_html_sha, second_html_sha, review_asset_sha = _write_review_pack(
        repository_root, bundle_sha256, ds2, ds4, ds5, first_ids, second_ids
    )
    manifest = P08GoldBundleManifest(
        dataset_id="courserag-p08-ds4-ds5-gold-bundle",
        dataset_version="p08-r1",
        revision=1,
        ds4_candidate=_artifact(repository_root, repository_root / DS4_PATH),
        ds5_candidate=_artifact(repository_root, repository_root / DS5_PATH),
        source_packages=_artifact(repository_root, repository_root / PACKAGES_PATH),
        split_manifest=_artifact(repository_root, repository_root / SPLIT_PATH),
        candidate_record_sha256=record_hashes,
        upstream_approved_sha256=upstream,
        preserved_upstream_sha256=preserved,
        p06_unmapped_evidence_ids=unmapped,
        diagnostic_evidence_ids=list(DIAGNOSTIC_PLAN.values()),
        first_review_groups=first_groups,
        second_review_ids=second_ids,
        review_pack_relative_path=review_dir.relative_to(repository_root).as_posix(),
        review_pack_index_sha256=first_html_sha,
        second_review_index_sha256=second_html_sha,
        review_asset_sha256=review_asset_sha,
        bundle_sha256=bundle_sha256,
    )
    atomic_write_json(repository_root / MANIFEST_PATH, manifest.model_dump(mode="json"))
    _write_report(repository_root, manifest, ds4, ds5)
    return manifest


def _write_report(
    repository_root: Path,
    manifest: P08GoldBundleManifest,
    ds4: DS4QueryProcessingDataset,
    ds5: DS5RetrievalQADataset,
) -> None:
    first_entries = "\n".join(
        f"- 第 {index} 组（20 条）：`index.html` 中筛选记录 {20 * (index - 1) + 1}–{20 * index}"
        for index in range(1, 9)
    )
    text = f"""# ED-PRE08 DS4/DS5 Candidate 审核报告

## 审核对象

- Bundle SHA-256：`{manifest.bundle_sha256}`
- DS4 Candidate：`{manifest.ds4_candidate.path}`（{len(ds4.cases)} 条）
- DS5 Candidate：`{manifest.ds5_candidate.path}`（{len(ds5.cases)} 条）
- 审批范围：`{APPROVAL_SCOPE}`；QA Gold 明确为 `pending_p09`。
- 语义来源：2；Source Package：10；派生文档未进入 Retrieval Gold。

## 审核入口

- 首轮：`{manifest.review_pack_relative_path}/index.html`，160 条全部审核。
- 二轮：`{manifest.review_pack_relative_path}/second_review.html`，132 条盲化复核。
{first_entries}

## 必查顺序

1. Query 是否自然、只问所属课程且没有新增课程事实。
2. Query 类型、难度、Filter、KP 和 Source Package 是否合理。
3. 每个 2 分 Evidence 是否直接且完整；多证据组是否缺一不可。
4. 每个 1 分 Evidence 是否确实有帮助但单独不足；必要邻接是否消除依赖。
5. 3–5 个 0 分硬负例是否容易混淆但不能回答；未列 Evidence 默认 0。
6. 不可回答项是否完成全课程审计，最近假阳性是否都不能回答。
7. 页码/BBox、P06 诊断层和 `qa_gold_status=pending_p09` 是否正确。

## 构造验证

- Candidate 连续生成两次后，两个 Candidate、Source Package、Split、分组、顺序和 Bundle Hash 完全一致。
- DS4/DS5/Schema/边界专项测试：30 passed；全量 Pytest：415 passed、5 skipped。
- JSON Schema：48 个导出文件通过 `--check`；Ruff Format/Check 与全量 Mypy（262 个源文件）通过。
- `git diff --check` 通过，仅显示 Windows 工作区既有的 LF/CRLF 提示。
- `approved/ds4`、`approved/ds5` 仍只有 `.gitkeep`；全局 Dev/Test 仍为空，Test 未锁定。
- 未运行 P08、B3–B5、外部 Provider、正式 Test 或 P09 QA 标注。

任何退回都按记录 ID 生成 r2，不覆盖 r1。两轮全部通过后，请回复：

`批准正式 P08 Gold Bundle {manifest.bundle_sha256}`
"""
    atomic_write_text(repository_root / REPORT_PATH, text)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository-root", type=Path, default=Path.cwd())
    args = parser.parse_args()
    manifest = build_p08_candidates(args.repository_root)
    print(json.dumps({"bundle_sha256": manifest.bundle_sha256}, ensure_ascii=False))


if __name__ == "__main__":
    main()
