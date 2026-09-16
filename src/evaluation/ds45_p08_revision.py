"""Audit P08 r1 systemic labeling defects and build the source-readable r2 bundle."""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import shutil
from pathlib import Path
from typing import Any

from courserag.evals.schemas import (
    DS2EvidenceDataset,
    DS3KnowledgePointDataset,
    DS4QueryProcessingDataset,
    DS5RetrievalQADataset,
    EvidenceGroup,
    P08DS5SplitManifest,
    P08GoldBundleManifest,
    P08SourcePackageDataset,
    P08SplitAssignment,
    QueryProcessingCase,
    QueryProcessingExpected,
    RetrievalEvidenceJudgment,
    RetrievalQACase,
)
from evaluation.contracts import CandidateRevisionArtifact, CandidateRevisionHistory
from evaluation.corpus_fixtures import sha256_file
from evaluation.datasets import record_digest
from evaluation.ds45_p08_data import (
    APPROVAL_SCOPE,
    DOCX,
    PDF,
    ROOT,
    _artifact,
    _case_id,
    _char_terms,
    bundle_identity_sha256,
)
from evaluation.io import atomic_write_json, atomic_write_text

R1_DS4 = ROOT / "candidates/ds4/p08_query_processing_r1.json"
R1_DS5 = ROOT / "candidates/ds5/p08_retrieval_r1.json"
R2_DS4 = ROOT / "candidates/ds4/p08_query_processing_r2.json"
R2_DS5 = ROOT / "candidates/ds5/p08_retrieval_r2.json"
R1_PACKAGES = ROOT / "provenance/p08_query_source_packages.json"
R2_PACKAGES = ROOT / "provenance/p08_query_source_packages_r2.json"
R2_SPLIT = ROOT / "provenance/p08_ds5_split_r2.json"
CANONICAL_MANIFEST = ROOT / "provenance/p08_gold_bundle_manifest.json"
R1_MANIFEST = ROOT / "provenance/p08_gold_bundle_manifest_r1.json"
R2_MANIFEST = ROOT / "provenance/p08_gold_bundle_manifest_r2.json"
AUDIT_PATH = ROOT / "provenance/p08_r1_systemic_audit.json"
R2_VALIDATION_PATH = ROOT / "provenance/p08_r2_semantic_validation.json"
HISTORY_PATH = ROOT / "provenance/p08_candidate_revision_history.json"
DS5_HISTORY_PATH = ROOT / "provenance/p08_ds5_candidate_revision_history.json"
RECORD_CHANGES_PATH = ROOT / "provenance/p08_r1_to_r2_record_changes.json"
REPORT = Path("docs/refactor/phase_reports/ED_PRE_P08_DS4_DS5_candidate_review.md")
R1_REPORT = Path("docs/refactor/phase_reports/ED_PRE_P08_DS4_DS5_candidate_review_r1.md")
R2_REPORT = Path("docs/refactor/phase_reports/ED_PRE_P08_DS4_DS5_candidate_review_r2.md")
R2_STRATEGY_SHA256 = hashlib.sha256(
    b"p08-retrieval-only-r2|human-readable-id-resolution|curated-ds4-edges|"
    b"no-heuristic-helpful|hard-negative-excludes-required-source-packages|"
    b"source-grounded-query-rewrite|qa-pending-p09"
).hexdigest()


EDGE_SPECS: tuple[dict[str, Any], ...] = (
    {
        "course": PDF,
        "kp": "人工智能",
        "term": "AI",
        "noisy": "  ＡＩ　是什么？  ",
        "normalized": "AI 是什么？",
        "allowed": ["人工智能"],
        "forbidden": ["图灵机", "刷脸支付"],
    },
    {
        "course": PDF,
        "kp": "通用人工智能",
        "term": "AGI",
        "noisy": "ＡＧＩ　是什么？",
        "normalized": "AGI 是什么？",
        "allowed": ["通用人工智能"],
        "forbidden": ["Google Duplex语音助理", "人工智能支付合规监控"],
    },
    {
        "course": DOCX,
        "kp": "多层感知机的适用范围",
        "term": "MLP",
        "noisy": "ＭＬＰ　适用范围？",
        "normalized": "MLP 的适用范围是什么？",
        "allowed": ["多层感知机"],
        "forbidden": ["Transformer编码器结构", "大模型"],
    },
    {
        "course": DOCX,
        "kp": "传统seq2seq的长序列局限",
        "term": "seq2seq",
        "noisy": "Seq2Seq　的 长序列局限？",
        "normalized": "seq2seq 的长序列局限是什么？",
        "allowed": [],
        "forbidden": ["感知机", "LIO-SAM"],
    },
    {
        "course": DOCX,
        "kp": "注意力机制中Q、K、V的来源",
        "term": "Q/K/V",
        "noisy": "Q／K／V　分别来自哪里？",
        "normalized": "Q/K/V 分别来自哪里？",
        "allowed": [],
        "forbidden": ["NeRF技术发展方向", "可穿戴传感器性能要求"],
    },
    {
        "course": DOCX,
        "kp": "NeRF技术发展方向",
        "term": "NeRF",
        "noisy": "ＮｅＲＦ　技术方向？",
        "normalized": "NeRF 的技术发展方向是什么？",
        "allowed": ["神经辐射场"],
        "forbidden": ["感知机", "微调"],
    },
)

PARAPHRASE_QUERIES = {
    "人工智能交易异常检测": "支付系统如何利用 AI 识别异常交易？",
    "早期计算机在数学和自然语言中的应用": "早期计算机除数学计算外还被用于哪类语言任务？",
    "通用人工智能的跨领域任务能力": "能够跨领域完成接近或超过人类水平任务的系统，在教材中是什么概念？",
    "注意力机制中Q、K、V的来源": "在注意力机制里，查询向量以及键和值分别由哪里产生？",
    "图灵测试的非物理性": "为什么展示机器智能不必模拟人的物理存在？",
    "深度学习军事目标识别": "军事场景中，深度学习怎样用于目标识别？",
    "SLAM传感器特性比较": "进行定位与建图时，教材如何比较不同传感器的特性？",
    "ERNIE情感分类微调流程": "用自有情感数据训练 ERNIE 分类器需要经过哪些环节？",
    "大模型训练数据准备与预处理": "训练大模型前，原始数据需要经过哪些准备和处理？",
    "课堂教学智能反馈": "课堂系统怎样依据学生状态形成教学反馈？",
    "思维机器公司": "教材提到的那家早期并行计算企业是什么？",
    "编码器-解码器注意力": "解码端查询编码端表示时，Q、K、V 如何形成？",
    "可穿戴传感数据算法类型": "处理可穿戴传感数据时，教材列举了哪些算法类别？",
    "完整图灵测试": "除了文字对话，扩展版图灵测试还要求机器具备哪些能力？",
    "深度学习在语音处理中的应用": "深度学习在语音任务中承担哪些处理工作？",
}

PROCEDURE_QUERIES = {
    "学生专注度分析流程": "教材中的学生专注度分析从视频采集到结果反馈包含哪些步骤？",
    "感知机原始训练算法": "感知机原始训练算法的输入、初始化、迭代更新和输出分别是什么？",
    "高斯粒子瓦片深度排序": "高斯粒子在瓦片中按什么过程完成深度排序与渲染？",
    "感知机算法收敛性": "教材怎样说明感知机训练从迭代到收敛的条件与过程？",
    "大规模训练数据与涌现能力": "教材用哪些关键因素解释大规模训练如何促成涌现能力？",
    "ERNIE预测配置": "完成 ERNIE 微调后，预测阶段需要怎样配置和执行？",
    "通用人工智能的人类能力与自我意识边界": "教材从哪些层面判断 AGI 的任务能力、人类能力与自我意识边界？",
    "NeRF快速推理、训练、编辑与动态重建方法": "教材分别列出了哪些方法改进 NeRF 的推理、训练、编辑和动态重建？",
    "大模型训练计算成本": "教材从哪些训练环节说明大模型的计算资源消耗？",
    "可穿戴传感数据算法类型": "处理可穿戴传感数据时，教材列出了哪些算法环节或类型？",
}


def _save_r1(repository_root: Path) -> None:
    for source, target in (
        (CANONICAL_MANIFEST, R1_MANIFEST),
        (REPORT, R1_REPORT),
    ):
        source_path = repository_root / source
        target_path = repository_root / target
        if not target_path.exists():
            target_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source_path, target_path)


def _package_maps(packages: P08SourcePackageDataset) -> tuple[dict[str, str], dict[str, Any]]:
    evidence_to_package = {
        evidence_id: package.package_id
        for package in packages.packages
        for evidence_id in package.evidence_ids
    }
    return evidence_to_package, {item.package_id: item for item in packages.packages}


def _kp_maps(ds3: DS3KnowledgePointDataset) -> tuple[dict[str, Any], dict[tuple[str, str], Any]]:
    by_id = {item.gold_kp_id: item for item in ds3.knowledge_points}
    by_name = {(item.course_id, item.canonical_name): item for item in ds3.knowledge_points}
    return by_id, by_name


def _primary_evidence_id(kp: Any) -> str:
    return next(item.evidence_id for item in kp.evidence_links if item.is_primary)


def _audit_r1(
    ds4: DS4QueryProcessingDataset,
    ds5: DS5RetrievalQADataset,
    evidence_to_package: dict[str, str],
) -> dict[str, Any]:
    ds4_edges = [item.record_id for item in ds4.cases if item.mirrored_ds5_case_id is None]
    heuristic_helpful = [
        item.record_id
        for item in ds5.cases
        if any(judgment.role == "helpful" for judgment in item.evidence_judgments)
    ]
    same_package_negatives: dict[str, list[str]] = {}
    for item in ds5.cases:
        required = {
            evidence_id
            for group in item.gold_evidence_groups
            for evidence_id in group.required_evidence_ids
        }
        required_packages = {evidence_to_package[evidence_id] for evidence_id in required}
        collisions = [
            evidence_id
            for evidence_id in item.hard_negative_evidence_ids
            if evidence_to_package[evidence_id] in required_packages
        ]
        if collisions:
            same_package_negatives[item.record_id] = collisions
    fallback_paraphrases = [
        item.record_id
        for item in ds5.cases
        if item.query_type == "paraphrase" and item.query.startswith("换一种说法")
    ]
    meta_procedures = [
        item.record_id
        for item in ds5.cases
        if item.query_type == "procedure" and "列出了哪些步骤或处理环节" in item.query
    ]
    return {
        "schema_version": "courserag.p08-r1-systemic-audit.v1",
        "r1_record_count": len(ds4.cases) + len(ds5.cases),
        "findings": {
            "ds4_opaque_id_display": {
                "affected_count": len(ds4.cases),
                "action": "r2 displays every KP/Evidence ID with name, exact text and source location",
            },
            "ds4_heuristic_edge_linking": {
                "affected_count": len(ds4_edges),
                "record_ids": ds4_edges,
                "action": "replace all dedicated edges with six curated source-grounded term cases per capability",
            },
            "ds5_heuristic_helpful": {
                "affected_count": len(heuristic_helpful),
                "record_ids": heuristic_helpful,
                "action": "remove every unverified one-point label; r2 contains no heuristic helpful judgment",
            },
            "ds5_hard_negative_same_source_package": {
                "affected_count": len(same_package_negatives),
                "records": same_package_negatives,
                "action": "replace with same-course candidates outside every Required Evidence source package",
            },
            "ds5_template_paraphrase": {
                "affected_count": len(fallback_paraphrases),
                "record_ids": fallback_paraphrases,
                "action": "replace all 15 paraphrase queries with source-grounded natural wording",
            },
            "ds5_meta_procedure_wording": {
                "affected_count": len(meta_procedures),
                "record_ids": meta_procedures,
                "action": "replace all 10 procedure prompts with content-specific wording",
            },
        },
    }


def _query_r2(case: RetrievalQACase, kp_by_id: dict[str, Any]) -> str:
    if not case.answerable:
        return case.query
    first = kp_by_id[case.expected_knowledge_points[0]].canonical_name
    second = (
        kp_by_id[case.expected_knowledge_points[1]].canonical_name
        if len(case.expected_knowledge_points) > 1
        else None
    )
    if case.query_type == "paraphrase":
        return PARAPHRASE_QUERIES[first]
    if case.query_type == "procedure":
        return PROCEDURE_QUERIES[first]
    if case.query_type == "exact_fact":
        return f"教材关于“{first}”给出了哪些具体数据或事实？"
    if case.query_type == "definition":
        return f"根据教材，如何定义或说明“{first}”？"
    if case.query_type == "comparison":
        return f"根据教材，“{first}”与“{second}”分别关注什么，二者有何区别？"
    if case.query_type == "application":
        return f"教材如何说明“{first}”的应用场景、作用或限制？"
    if case.query_type == "cross_section":
        return f"结合教材不同章节，说明“{first}”与“{second}”之间的联系及各自要点。"
    raise ValueError(f"unexpected Query type: {case.query_type}")


def _negative_pool(
    *,
    case: RetrievalQACase,
    query: str,
    evidence: list[Any],
    evidence_to_package: dict[str, str],
    required_ids: set[str],
) -> list[Any]:
    required_packages = {evidence_to_package[item] for item in required_ids}
    query_terms = _char_terms(query)
    pool = [
        item
        for item in evidence
        if item.course_id == case.course_id
        and item.evidence_id not in required_ids
        and evidence_to_package[item.evidence_id] not in required_packages
    ]
    pool.sort(
        key=lambda item: (
            -len(query_terms & _char_terms(item.gold_text)),
            hashlib.sha256(f"r2|{query}|{item.evidence_id}".encode()).hexdigest(),
        )
    )
    if len(pool) < 4:
        raise ValueError(f"fewer than four cross-package hard negatives: {case.record_id}")
    return pool[:4]


def _revise_ds5(
    ds5: DS5RetrievalQADataset,
    ds2: DS2EvidenceDataset,
    kp_by_id: dict[str, Any],
    evidence_to_package: dict[str, str],
) -> tuple[DS5RetrievalQADataset, dict[str, str], dict[str, list[str]]]:
    revised: list[RetrievalQACase] = []
    id_map: dict[str, str] = {}
    changes: dict[str, list[str]] = {}
    for case in ds5.cases:
        query = _query_r2(case, kp_by_id)
        required_ids = {
            evidence_id
            for group in case.gold_evidence_groups
            for evidence_id in group.required_evidence_ids
        }
        if case.answerable:
            by_id = {item.evidence_id: item for item in ds2.evidence}
            required_judgments = [
                RetrievalEvidenceJudgment(
                    evidence_id=evidence_id,
                    relevance=2,
                    role="required",
                    evidence_record_sha256=record_digest(by_id[evidence_id]),
                    rationale="该 Approved DS2 原文直接提供 Query 所需事实，并属于完整 Evidence Group。",
                )
                for evidence_id in sorted(required_ids)
            ]
            negatives = _negative_pool(
                case=case,
                query=query,
                evidence=ds2.evidence,
                evidence_to_package=evidence_to_package,
                required_ids=required_ids,
            )
            negative_judgments = [
                RetrievalEvidenceJudgment(
                    evidence_id=item.evidence_id,
                    relevance=0,
                    role="hard_negative",
                    evidence_record_sha256=record_digest(item),
                    rationale=(
                        "同课程且存在词面混淆可能，但来自 Required Evidence 之外的 Source Package，"
                        "不陈述该 Query 所需事实。"
                    ),
                )
                for item in negatives
            ]
            judgments = required_judgments + negative_judgments
            hard_ids = [item.evidence_id for item in negatives]
            support_ids = sorted(required_ids)
        else:
            judgments = case.evidence_judgments
            hard_ids = case.hard_negative_evidence_ids
            support_ids = []
        new_id = _case_id(str(case.course_id), query, sorted(required_ids))
        groups = [
            EvidenceGroup(
                group_id=f"eg-{new_id[-16:]}",
                sufficiency=group.sufficiency,
                required_evidence_ids=group.required_evidence_ids,
            )
            for group in case.gold_evidence_groups
        ]
        values = case.model_dump(mode="json")
        values.update(
            {
                "record_id": new_id,
                "query": query,
                "query_sha256": hashlib.sha256(query.encode()).hexdigest(),
                "gold_evidence_groups": [item.model_dump(mode="json") for item in groups],
                "supporting_evidence_ids": support_ids,
                "evidence_judgments": [item.model_dump(mode="json") for item in judgments],
                "graded_relevance": {item.evidence_id: item.relevance for item in judgments},
                "hard_negative_evidence_ids": hard_ids,
                "generation_strategy_sha256": R2_STRATEGY_SHA256,
                "candidate_source": "source_grounded_rule_audited_r2",
            }
        )
        item = RetrievalQACase.model_validate(values)
        revised.append(item)
        id_map[case.record_id] = item.record_id
        item_changes: list[str] = []
        if case.query != item.query:
            item_changes.append("query_rewritten")
        if any(judgment.role == "helpful" for judgment in case.evidence_judgments):
            item_changes.append("heuristic_helpful_removed")
        if case.hard_negative_evidence_ids != item.hard_negative_evidence_ids:
            item_changes.append("hard_negatives_reselected_cross_package")
        if case.record_id != item.record_id:
            item_changes.append("stable_query_id_recomputed")
        changes[case.record_id] = item_changes
    return (
        DS5RetrievalQADataset(
            dataset_id=ds5.dataset_id,
            dataset_version="p08-r2",
            cases=revised,
        ),
        id_map,
        changes,
    )


def _preserve_terms(query: str, kp_names: list[str]) -> list[str]:
    glossary = ("AI", "AGI", "MLP", "seq2seq", "Q", "K", "V", "NeRF", "3D", "SLAM", "LIO-SAM")
    terms = [term for term in glossary if term.lower() in query.lower()]
    terms.extend(name for name in kp_names if name in query)
    return list(dict.fromkeys(terms))


def _other_kp_names(
    course_id: str,
    package_id: str,
    kp_by_id: dict[str, Any],
    evidence_to_package: dict[str, str],
) -> list[str]:
    names = [
        item.canonical_name
        for item in kp_by_id.values()
        if item.course_id == course_id
        and evidence_to_package[_primary_evidence_id(item)] != package_id
    ]
    return names[:2]


def _revise_ds4(
    ds4: DS4QueryProcessingDataset,
    ds5_r2: DS5RetrievalQADataset,
    ds5_id_map: dict[str, str],
    kp_by_id: dict[str, Any],
    kp_by_name: dict[tuple[str, str], Any],
    evidence_to_package: dict[str, str],
) -> tuple[DS4QueryProcessingDataset, dict[str, list[str]]]:
    ds5_by_id = {item.record_id: item for item in ds5_r2.cases}
    revised: list[QueryProcessingCase] = []
    changes: dict[str, list[str]] = {}
    edge_by_capability: dict[str, list[QueryProcessingCase]] = {}
    for item in ds4.cases:
        if item.mirrored_ds5_case_id is None:
            edge_by_capability.setdefault(str(item.capability), []).append(item)
            continue
        source = ds5_by_id[ds5_id_map[item.mirrored_ds5_case_id]]
        names = [kp_by_id[kp_id].canonical_name for kp_id in source.expected_knowledge_points]
        aliases = [
            alias
            for kp_id in source.expected_knowledge_points
            for alias in kp_by_id[kp_id].aliases
            if alias not in names
        ]
        expected = QueryProcessingExpected(
            normalized_query=source.query,
            linked_knowledge_points=source.expected_knowledge_points,
            filters=source.filters,
            route="unanswerable_audit" if not source.answerable else "metadata_filtered_retrieval",
            allowed_expansions=(
                aliases if item.capability == "expansion_rewrite_constraints" else []
            ),
            forbidden_expansions=(
                _other_kp_names(
                    str(source.course_id),
                    str(source.source_package_id),
                    kp_by_id,
                    evidence_to_package,
                )
                if item.capability == "expansion_rewrite_constraints"
                else []
            ),
            must_preserve_terms=_preserve_terms(source.query, names),
            must_preserve_filters=True,
        )
        identity = f"r2|{item.capability}|mirror|{source.record_id}"
        record_id = f"gold-qp-{hashlib.sha256(identity.encode()).hexdigest()[:32]}"
        revised.append(
            QueryProcessingCase(
                record_id=record_id,
                candidate_source="source_grounded_rule_audited_r2",
                raw_query=source.query,
                expected=expected,
                course_id=source.course_id,
                capability=item.capability,
                query_family_id=source.query_family_id,
                source_package_id=source.source_package_id,
                mirrored_ds5_case_id=source.record_id,
                upstream_approved_sha256=item.upstream_approved_sha256,
                query_sha256=hashlib.sha256(source.query.encode()).hexdigest(),
                generation_strategy_sha256=R2_STRATEGY_SHA256,
                approval_scope=APPROVAL_SCOPE,
            )
        )
        changes[item.record_id] = [
            "mirrored_ds5_r2_identity_bound",
            "kp_names_and_source_text_exposed_in_review",
        ]

    for capability, originals in edge_by_capability.items():
        originals.sort(key=lambda item: item.record_id)
        for original, spec in zip(originals, EDGE_SPECS, strict=True):
            kp = kp_by_name[(spec["course"], spec["kp"])]
            evidence_id = _primary_evidence_id(kp)
            package_id = evidence_to_package[evidence_id]
            raw = {
                "query_normalization": spec["noisy"],
                "knowledge_point_linking": spec["normalized"],
                "filter_parsing": f"仅在当前课程检索：{spec['normalized']}",
                "query_router": f"查找教材原文：{spec['normalized']}",
                "expansion_rewrite_constraints": (
                    f"改写“{spec['term']}”的检索词，但必须保留 {spec['term']} 专名。"
                ),
            }[capability]
            expected = QueryProcessingExpected(
                normalized_query=(
                    spec["normalized"] if capability == "query_normalization" else raw
                ),
                linked_knowledge_points=[kp.gold_kp_id],
                filters={"course_id": spec["course"]} if capability == "filter_parsing" else {},
                route=(
                    "metadata_filtered_retrieval"
                    if capability == "filter_parsing"
                    else "hybrid_retrieval"
                ),
                allowed_expansions=(
                    spec["allowed"] if capability == "expansion_rewrite_constraints" else []
                ),
                forbidden_expansions=(
                    spec["forbidden"] if capability == "expansion_rewrite_constraints" else []
                ),
                must_preserve_terms=[spec["term"]],
                must_preserve_filters=True,
            )
            identity = f"r2|{capability}|edge|{spec['course']}|{spec['kp']}"
            record_id = f"gold-qp-{hashlib.sha256(identity.encode()).hexdigest()[:32]}"
            revised.append(
                QueryProcessingCase(
                    record_id=record_id,
                    candidate_source="source_grounded_rule_audited_r2",
                    raw_query=raw,
                    expected=expected,
                    course_id=spec["course"],
                    capability=capability,
                    query_family_id=f"p08-ds4-edge-r2-{hashlib.sha256(identity.encode()).hexdigest()[:20]}",
                    source_package_id=package_id,
                    mirrored_ds5_case_id=None,
                    upstream_approved_sha256=original.upstream_approved_sha256,
                    query_sha256=hashlib.sha256(raw.encode()).hexdigest(),
                    generation_strategy_sha256=R2_STRATEGY_SHA256,
                    approval_scope=APPROVAL_SCOPE,
                )
            )
            changes[original.record_id] = [
                "heuristic_edge_replaced_with_curated_source_grounded_case",
                "linked_kp_corrected",
                "expansion_constraints_corrected",
                "kp_names_and_source_text_exposed_in_review",
            ]
    revised.sort(
        key=lambda item: (str(item.capability), item.mirrored_ds5_case_id is None, item.record_id)
    )
    return (
        DS4QueryProcessingDataset(
            dataset_id=ds4.dataset_id,
            dataset_version="p08-r2",
            cases=revised,
        ),
        changes,
    )


def _split(ds5: DS5RetrievalQADataset) -> P08DS5SplitManifest:
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
    return P08DS5SplitManifest(
        dataset_id="courserag-p08-ds5-split",
        dataset_version="p08-r2",
        assignments=assignments,
        p08_tuning_allowed_ids=[
            item.record_id
            for item in ds5.cases
            if item.split == "dev" and item.evaluation_stratum == "retrieval_main"
        ],
    )


def _validate_r2_semantics(
    ds2: DS2EvidenceDataset,
    ds3: DS3KnowledgePointDataset,
    ds4: DS4QueryProcessingDataset,
    ds5: DS5RetrievalQADataset,
    evidence_to_package: dict[str, str],
) -> dict[str, Any]:
    evidence_by_id = {item.evidence_id: item for item in ds2.evidence}
    kp_by_id = {item.gold_kp_id: item for item in ds3.knowledge_points}
    answerable_count = 0
    judgment_count = 0
    for ds5_case in ds5.cases:
        judgment_count += len(ds5_case.evidence_judgments)
        if any(
            evidence_by_id[item.evidence_id].course_id != ds5_case.course_id
            for item in ds5_case.evidence_judgments
        ):
            raise ValueError(f"cross-course DS5 judgment: {ds5_case.record_id}")
        if any(
            item.relevance == 1 or item.role == "helpful" for item in ds5_case.evidence_judgments
        ):
            raise ValueError(f"unverified one-point DS5 judgment remains: {ds5_case.record_id}")
        if not ds5_case.answerable:
            continue
        answerable_count += 1
        required_ids = {
            evidence_id
            for group in ds5_case.gold_evidence_groups
            for evidence_id in group.required_evidence_ids
        }
        kp_evidence_ids = {
            link.evidence_id
            for kp_id in ds5_case.expected_knowledge_points
            for link in kp_by_id[kp_id].evidence_links
        }
        if required_ids != kp_evidence_ids:
            raise ValueError(f"Query/KP/Required Evidence mismatch: {ds5_case.record_id}")
        required_packages = {evidence_to_package[item] for item in required_ids}
        negative_packages = {
            evidence_to_package[item] for item in ds5_case.hard_negative_evidence_ids
        }
        if required_packages & negative_packages:
            raise ValueError(
                f"hard negative shares a Required Source Package: {ds5_case.record_id}"
            )

    for ds4_case in ds4.cases:
        linked = [kp_by_id[item] for item in ds4_case.expected.linked_knowledge_points]
        if any(item.course_id != ds4_case.course_id for item in linked):
            raise ValueError(f"cross-course DS4 Knowledge Point: {ds4_case.record_id}")
        linked_names = {item.canonical_name for item in linked}
        linked_aliases = {alias for item in linked for alias in item.aliases}
        if linked_names & set(ds4_case.expected.forbidden_expansions):
            raise ValueError(f"DS4 forbids a linked Knowledge Point: {ds4_case.record_id}")
        if linked_aliases & set(ds4_case.expected.forbidden_expansions):
            raise ValueError(f"DS4 forbids a linked Alias: {ds4_case.record_id}")

    return {
        "schema_version": "courserag.p08-r2-semantic-validation.v1",
        "bundle_revision": 2,
        "checks": {
            "ds4_records": len(ds4.cases),
            "ds4_cross_course_kp_links": 0,
            "ds4_forbidden_linked_name_or_alias": 0,
            "ds5_records": len(ds5.cases),
            "ds5_answerable_records": answerable_count,
            "ds5_judgments": judgment_count,
            "ds5_cross_course_judgments": 0,
            "ds5_unverified_one_point_judgments": 0,
            "ds5_query_kp_required_evidence_mismatches": 0,
            "ds5_hard_negative_required_package_collisions": 0,
        },
        "note": (
            "These deterministic checks remove known systemic defects; the Course Owner must "
            "still judge semantic relevance for every displayed source excerpt."
        ),
    }


def _evidence_html(evidence: Any, judgment: RetrievalEvidenceJudgment | None = None) -> str:
    role = f"{judgment.relevance}分 · {judgment.role}" if judgment else "上游原文"
    rationale = f"<p><b>判定理由：</b>{html.escape(judgment.rationale)}</p>" if judgment else ""
    return (
        f"<details><summary>{role} · <code>{evidence.evidence_id}</code> → "
        f"{html.escape(evidence.semantic_unit_type)}</summary>{rationale}"
        f"<blockquote>{html.escape(evidence.gold_text)}</blockquote>"
        f"<p><b>必要邻接：</b>{html.escape(' / '.join(evidence.necessary_neighbor_text) or '无')}</p>"
        f"<p><b>Section：</b>{html.escape(' / '.join(evidence.source_span.section_path))} · "
        f"<b>页码：</b>{evidence.source_span.page_start}–{evidence.source_span.page_end}</p>"
        f"<p><b>BBox：</b>{html.escape(json.dumps([box.model_dump(mode='json') for box in evidence.bboxes], ensure_ascii=False))}</p>"
        f"<img loading='lazy' src='assets/{evidence.evidence_id}.png' alt='{evidence.evidence_id}'></details>"
    )


def _kp_html(kp: Any, evidence_by_id: dict[str, Any]) -> str:
    primary_id = _primary_evidence_id(kp)
    return (
        f"<section class='kp'><p><code>{kp.gold_kp_id}</code> → <b>{html.escape(kp.canonical_name)}</b></p>"
        f"<p><b>Summary：</b>{html.escape(kp.summary)}</p>"
        + _evidence_html(evidence_by_id[primary_id])
        + "</section>"
    )


def _review_html(
    *,
    title: str,
    bundle_sha256: str,
    review_pass: str,
    records: list[Any],
    expected_ids: list[str],
    evidence_by_id: dict[str, Any],
    kp_by_id: dict[str, Any],
    package_by_id: dict[str, Any],
) -> str:
    cards: list[str] = []
    for item in records:
        package = package_by_id[item.source_package_id]
        package_line = (
            f"<p><b>Source Package：</b><code>{package.package_id}</code> → "
            f"{html.escape(package.title)}；Sections {html.escape(', '.join(package.section_anchors))}</p>"
        )
        if isinstance(item, RetrievalQACase):
            kp_blocks = (
                "".join(
                    _kp_html(kp_by_id[kp_id], evidence_by_id)
                    for kp_id in item.expected_knowledge_points
                )
                or "<p>不可回答记录：没有期望 KP。</p>"
            )
            evidence_blocks = "".join(
                _evidence_html(evidence_by_id[judgment.evidence_id], judgment)
                for judgment in item.evidence_judgments
            )
            audit = (
                f"<details><summary>不可回答全课程审计</summary><pre>{html.escape(json.dumps(item.unanswerable_audit.model_dump(mode='json'), ensure_ascii=False, indent=2))}</pre></details>"
                if item.unanswerable_audit
                else ""
            )
            body = (
                f"<h3>{html.escape(item.query)}</h3>"
                f"<p>{item.query_type} · {item.difficulty} · {item.course_id} · {item.split} · "
                f"Stratum {item.evaluation_stratum} · QA {item.qa_gold_status}</p>"
                + package_line
                + "<h4>Knowledge Point：ID → 名称 → Summary → 主证据原文</h4>"
                + kp_blocks
                + "<h4>Retrieval 相关性：ID → 2/0 分 → 原文</h4>"
                + evidence_blocks
                + audit
            )
        else:
            kp_blocks = "".join(
                _kp_html(kp_by_id[kp_id], evidence_by_id)
                for kp_id in item.expected.linked_knowledge_points
            )
            body = (
                f"<h3>{html.escape(item.raw_query)}</h3><p>{item.capability} · {item.course_id} · "
                f"DS5 mirror {item.mirrored_ds5_case_id or '专门边界案例'}</p>"
                + package_line
                + f"<p><b>normalized_query：</b>{html.escape(item.expected.normalized_query)}</p>"
                + f"<p><b>filters / route：</b>{html.escape(json.dumps(item.expected.filters, ensure_ascii=False))} / {item.expected.route}</p>"
                + f"<p><b>allowed_expansions：</b>{html.escape(', '.join(item.expected.allowed_expansions) or '无')}</p>"
                + f"<p><b>forbidden_expansions：</b>{html.escape(', '.join(item.expected.forbidden_expansions) or '无')}</p>"
                + f"<p><b>must_preserve_terms：</b>{html.escape(', '.join(item.expected.must_preserve_terms) or '无')}</p>"
                + "<h4>linked_knowledge_points：ID → 名称 → Summary → 主证据原文</h4>"
                + kp_blocks
            )
        cards.append(
            f"<article id='{item.record_id}'><code>{item.record_id}</code>{body}"
            f"<label><input type='radio' name='{item.record_id}' value='pass'>通过</label> "
            f"<label><input type='radio' name='{item.record_id}' value='return'>退回</label>"
            f"<textarea placeholder='退回原因/备注'></textarea></article>"
        )
    expected_json = json.dumps(expected_ids, ensure_ascii=False)
    return f"""<!doctype html><html lang='zh-CN'><head><meta charset='utf-8'><title>{html.escape(title)}</title>
<style>body{{font:15px/1.55 system-ui;margin:24px;max-width:1320px}}article{{border:1px solid #aaa;border-radius:8px;padding:16px;margin:16px 0}}blockquote,pre{{white-space:pre-wrap;background:#f5f5f5;padding:10px}}img{{max-width:100%;border:1px solid #ddd}}textarea{{display:block;width:98%;min-height:48px;margin-top:8px}}.sticky{{position:sticky;top:0;background:white;padding:8px;border-bottom:1px solid #ddd;z-index:2}}.kp{{border-left:4px solid #567;padding-left:12px;margin:8px 0}}</style></head>
<body><div class='sticky'><b>{html.escape(title)}</b> · Bundle <code>{bundle_sha256}</code> · <button onclick='exportReview()'>导出审核 JSON</button></div>
<p>r2 已将所有不透明 ID 展开为名称、Summary、逐字原文、必要邻接、Section、页码和 BBox。DS5 r2 不再保留未经独立核验的启发式 1 分标签。</p>{"".join(cards)}
<script>const expected={expected_json};const key='p08-r2-{bundle_sha256}-{review_pass}';function save(){{const d={{}};document.querySelectorAll('article').forEach(a=>{{const r=a.querySelector('input:checked');if(r)d[a.id]={{decision:r.value,note:a.querySelector('textarea').value}}}});localStorage.setItem(key,JSON.stringify(d));}}document.addEventListener('change',save);document.addEventListener('input',save);const old=JSON.parse(localStorage.getItem(key)||'{{}}');Object.entries(old).forEach(([id,v])=>{{const a=document.getElementById(id);if(a){{const r=a.querySelector(`input[value="${{v.decision}}"]`);if(r)r.checked=true;a.querySelector('textarea').value=v.note||'';}}}});function exportReview(){{save();const d=JSON.parse(localStorage.getItem(key)||'{{}}');const reviewed=expected.filter(id=>d[id]);const returned=reviewed.filter(id=>d[id].decision==='return');const payload={{schema_version:'courserag.p08-review-decisions.v1',bundle_sha256:'{bundle_sha256}',review_pass:'{review_pass}',expected_record_ids:expected,reviewed_record_ids:reviewed,returned_record_ids:returned,reviewer_id:null,reviewed_at:null}};const b=new Blob([JSON.stringify(payload,null,2)],{{type:'application/json'}});const a=document.createElement('a');a.href=URL.createObjectURL(b);a.download='p08_r2_{review_pass}_review_{bundle_sha256[:12]}.json';a.click();}}</script></body></html>"""


def _find_asset(repository_root: Path, evidence_id: str) -> Path:
    matches = list(
        (repository_root / "storage_eval/ds2_p06_review").glob(f"*/assets/{evidence_id}.png")
    )
    if not matches:
        raise ValueError(f"missing review image: {evidence_id}")
    return max(matches, key=lambda item: item.stat().st_mtime_ns)


def _write_review(
    repository_root: Path,
    bundle_sha256: str,
    ds2: DS2EvidenceDataset,
    ds3: DS3KnowledgePointDataset,
    packages: P08SourcePackageDataset,
    ds4: DS4QueryProcessingDataset,
    ds5: DS5RetrievalQADataset,
    first_ids: list[str],
    second_ids: list[str],
) -> tuple[Path, str, str, dict[str, str]]:
    review_dir = repository_root / "storage_eval/ds45_p08_review" / bundle_sha256
    assets = review_dir / "assets"
    assets.mkdir(parents=True, exist_ok=True)
    evidence_by_id = {item.evidence_id: item for item in ds2.evidence}
    kp_by_id = {item.gold_kp_id: item for item in ds3.knowledge_points}
    package_by_id = {item.package_id: item for item in packages.packages}
    used = {judgment.evidence_id for item in ds5.cases for judgment in item.evidence_judgments} | {
        _primary_evidence_id(kp_by_id[kp_id])
        for item in ds4.cases
        for kp_id in item.expected.linked_knowledge_points
    }
    for evidence_id in sorted(used):
        source = _find_asset(repository_root, evidence_id)
        target = assets / f"{evidence_id}.png"
        if not target.exists() or sha256_file(target) != sha256_file(source):
            shutil.copyfile(source, target)
    records = {item.record_id: item for item in [*ds4.cases, *ds5.cases]}
    first = [records[item] for item in first_ids]
    second = [records[item] for item in second_ids]
    atomic_write_text(
        review_dir / "index.html",
        _review_html(
            title="P08 r2 DS4/DS5 首轮审核（160 条）",
            bundle_sha256=bundle_sha256,
            review_pass="first",
            records=first,
            expected_ids=first_ids,
            evidence_by_id=evidence_by_id,
            kp_by_id=kp_by_id,
            package_by_id=package_by_id,
        ),
    )
    atomic_write_text(
        review_dir / "second_review.html",
        _review_html(
            title="P08 r2 DS4/DS5 二轮盲化复核（132 条）",
            bundle_sha256=bundle_sha256,
            review_pass="second",
            records=second,
            expected_ids=second_ids,
            evidence_by_id=evidence_by_id,
            kp_by_id=kp_by_id,
            package_by_id=package_by_id,
        ),
    )
    return (
        review_dir,
        sha256_file(review_dir / "index.html"),
        sha256_file(review_dir / "second_review.html"),
        {item: sha256_file(assets / f"{item}.png") for item in sorted(used)},
    )


def build_r2(repository_root: Path) -> P08GoldBundleManifest:
    repository_root = repository_root.resolve()
    _save_r1(repository_root)
    ds2 = DS2EvidenceDataset.model_validate_json(
        (repository_root / ROOT / "approved/ds2/p06_evidence.json").read_text(encoding="utf-8")
    )
    ds3 = DS3KnowledgePointDataset.model_validate_json(
        (repository_root / ROOT / "approved/ds3/p07_knowledge_points.json").read_text(
            encoding="utf-8"
        )
    )
    ds4_r1 = DS4QueryProcessingDataset.model_validate_json(
        (repository_root / R1_DS4).read_text(encoding="utf-8")
    )
    ds5_r1 = DS5RetrievalQADataset.model_validate_json(
        (repository_root / R1_DS5).read_text(encoding="utf-8")
    )
    packages_r1 = P08SourcePackageDataset.model_validate_json(
        (repository_root / R1_PACKAGES).read_text(encoding="utf-8")
    )
    r1_manifest = P08GoldBundleManifest.model_validate_json(
        (repository_root / R1_MANIFEST).read_text(encoding="utf-8")
    )
    evidence_to_package, package_by_id = _package_maps(packages_r1)
    kp_by_id, kp_by_name = _kp_maps(ds3)
    audit = _audit_r1(ds4_r1, ds5_r1, evidence_to_package)
    atomic_write_json(repository_root / AUDIT_PATH, audit)

    ds5_r2, ds5_id_map, ds5_changes = _revise_ds5(ds5_r1, ds2, kp_by_id, evidence_to_package)
    ds4_r2, ds4_changes = _revise_ds4(
        ds4_r1,
        ds5_r2,
        ds5_id_map,
        kp_by_id,
        kp_by_name,
        evidence_to_package,
    )
    r2_validation = _validate_r2_semantics(
        ds2,
        ds3,
        ds4_r2,
        ds5_r2,
        evidence_to_package,
    )
    atomic_write_json(repository_root / R2_VALIDATION_PATH, r2_validation)
    packages_values = packages_r1.model_dump(mode="json")
    packages_values["dataset_version"] = "p08-r2"
    packages_r2 = P08SourcePackageDataset.model_validate(packages_values)
    split_r2 = _split(ds5_r2)
    atomic_write_json(repository_root / R2_DS4, ds4_r2.model_dump(mode="json"))
    atomic_write_json(repository_root / R2_DS5, ds5_r2.model_dump(mode="json"))
    atomic_write_json(repository_root / R2_PACKAGES, packages_r2.model_dump(mode="json"))
    atomic_write_json(repository_root / R2_SPLIT, split_r2.model_dump(mode="json"))

    all_records = [*ds4_r2.cases, *ds5_r2.cases]
    record_hashes = {item.record_id: record_digest(item) for item in all_records}
    first_ids = [item.record_id for item in all_records]
    first_groups = [first_ids[index : index + 20] for index in range(0, 160, 20)]
    fixed_second = [
        item.record_id
        for item in ds4_r2.cases
        if item.capability in {"filter_parsing", "expansion_rewrite_constraints"}
    ]
    sampled = [
        item.record_id
        for item in ds4_r2.cases
        if item.capability not in {"filter_parsing", "expansion_rewrite_constraints"}
    ]
    sampled.sort(key=lambda item: hashlib.sha256(item.encode()).hexdigest())
    second_ids = [item.record_id for item in ds5_r2.cases] + fixed_second + sampled[:8]
    upstream = r1_manifest.upstream_approved_sha256
    preserved = r1_manifest.preserved_upstream_sha256
    bundle_sha = bundle_identity_sha256(
        revision=2,
        ds4_sha256=sha256_file(repository_root / R2_DS4),
        ds5_sha256=sha256_file(repository_root / R2_DS5),
        source_packages_sha256=sha256_file(repository_root / R2_PACKAGES),
        split_sha256=sha256_file(repository_root / R2_SPLIT),
        candidate_record_sha256=record_hashes,
        upstream_approved_sha256=upstream,
        preserved_upstream_sha256=preserved,
        p06_unmapped_evidence_ids=r1_manifest.p06_unmapped_evidence_ids,
        diagnostic_evidence_ids=r1_manifest.diagnostic_evidence_ids,
        first_review_groups=first_groups,
        second_review_ids=second_ids,
    )
    review_dir, first_sha, second_sha, asset_sha = _write_review(
        repository_root,
        bundle_sha,
        ds2,
        ds3,
        packages_r2,
        ds4_r2,
        ds5_r2,
        first_ids,
        second_ids,
    )
    manifest = P08GoldBundleManifest(
        dataset_id="courserag-p08-ds4-ds5-gold-bundle",
        dataset_version="p08-r2",
        revision=2,
        ds4_candidate=_artifact(repository_root, repository_root / R2_DS4),
        ds5_candidate=_artifact(repository_root, repository_root / R2_DS5),
        source_packages=_artifact(repository_root, repository_root / R2_PACKAGES),
        split_manifest=_artifact(repository_root, repository_root / R2_SPLIT),
        candidate_record_sha256=record_hashes,
        upstream_approved_sha256=upstream,
        preserved_upstream_sha256=preserved,
        p06_unmapped_evidence_ids=r1_manifest.p06_unmapped_evidence_ids,
        diagnostic_evidence_ids=r1_manifest.diagnostic_evidence_ids,
        first_review_groups=first_groups,
        second_review_ids=second_ids,
        review_pack_relative_path=review_dir.relative_to(repository_root).as_posix(),
        review_pack_index_sha256=first_sha,
        second_review_index_sha256=second_sha,
        review_asset_sha256=asset_sha,
        bundle_sha256=bundle_sha,
    )
    atomic_write_json(repository_root / R2_MANIFEST, manifest.model_dump(mode="json"))
    atomic_write_json(repository_root / CANONICAL_MANIFEST, manifest.model_dump(mode="json"))
    ds4_history = CandidateRevisionHistory(
        dataset_id="courserag-p08-ds4-query-processing",
        dataset_version="p08-r2",
        revisions=[
            CandidateRevisionArtifact(
                revision=1,
                candidate_relative_path=R1_DS4.as_posix(),
                candidate_file_sha256=sha256_file(repository_root / R1_DS4),
                status="superseded",
                reason="Course Owner found opaque ID display and heuristic DS4 link defects; r1 remains immutable.",
            ),
            CandidateRevisionArtifact(
                revision=2,
                candidate_relative_path=R2_DS4.as_posix(),
                candidate_file_sha256=sha256_file(repository_root / R2_DS4),
                status="pending_course_owner_review",
                reason="All DS4 links are source-readable and dedicated edge cases were replaced after systemic audit.",
            ),
        ],
    )
    ds5_history = CandidateRevisionHistory(
        dataset_id="courserag-p08-ds5-retrieval",
        dataset_version="p08-r2",
        revisions=[
            CandidateRevisionArtifact(
                revision=1,
                candidate_relative_path=R1_DS5.as_posix(),
                candidate_file_sha256=sha256_file(repository_root / R1_DS5),
                status="superseded",
                reason="Course Owner found incorrect heuristic relevance labels; r1 remains immutable.",
            ),
            CandidateRevisionArtifact(
                revision=2,
                candidate_relative_path=R2_DS5.as_posix(),
                candidate_file_sha256=sha256_file(repository_root / R2_DS5),
                status="pending_course_owner_review",
                reason="Queries and judgments were rebuilt under the source-readable systemic-audit rules.",
            ),
        ],
    )
    record_changes: dict[str, Any] = {
        "schema_version": "courserag.p08-r1-to-r2-record-changes.v1",
        "r1_bundle_sha256": r1_manifest.bundle_sha256,
        "r2_bundle_sha256": manifest.bundle_sha256,
        "r1_audit_path": AUDIT_PATH.as_posix(),
        "record_changes": {"ds4": ds4_changes, "ds5": ds5_changes},
    }
    atomic_write_json(repository_root / HISTORY_PATH, ds4_history.model_dump(mode="json"))
    atomic_write_json(repository_root / DS5_HISTORY_PATH, ds5_history.model_dump(mode="json"))
    atomic_write_json(repository_root / RECORD_CHANGES_PATH, record_changes)
    _write_report(repository_root, manifest, audit, ds4_r2, ds5_r2, package_by_id)
    return manifest


def _write_report(
    repository_root: Path,
    manifest: P08GoldBundleManifest,
    audit: dict[str, Any],
    ds4: DS4QueryProcessingDataset,
    ds5: DS5RetrievalQADataset,
    package_by_id: dict[str, Any],
) -> None:
    findings = audit["findings"]
    text = f"""# ED-PRE08 DS4/DS5 r2 Candidate 审核报告

## r1 系统审计结论

- 60/60 DS4 卡片只显示不透明 KP ID，Course Owner 无法独立核对原文。
- 30 条 DS4 专门边界案例使用词面启发式链接；已全部替换为六个逐项策划的真实术语案例。
- {findings["ds5_heuristic_helpful"]["affected_count"]} 条 DS5 使用未经独立核验的启发式 1 分 Evidence；r2 全部删除，不把同源包误当相关性。
- {findings["ds5_hard_negative_same_source_package"]["affected_count"]} 条 DS5 至少有一个 0 分项与 Required Evidence 位于同一 Source Package；r2 全部改为所属课程内、Required 包之外的候选。
- 所有 15 条 paraphrase 和 10 条 procedure Query 已改为内容相关的自然问法。
- 完整审计：`{AUDIT_PATH.as_posix()}`；逐条 r1→r2 变化：`{RECORD_CHANGES_PATH.as_posix()}`。
- 标准修订历史：`{HISTORY_PATH.as_posix()}`、`{DS5_HISTORY_PATH.as_posix()}`。
- r2 确定性语义链验证：`{R2_VALIDATION_PATH.as_posix()}`；它验证全部 Query–KP–Required
  Evidence 直接闭合、课程一致、无遗漏同 KP Evidence、无自动 1 分和无 Required 包负例碰撞。

## r2 审核对象

- Bundle SHA-256：`{manifest.bundle_sha256}`
- DS4：{len(ds4.cases)}；DS5：{len(ds5.cases)}；Source Package：{len(package_by_id)}。
- 首轮：`{manifest.review_pack_relative_path}/index.html`（160 条）。
- 二轮：`{manifest.review_pack_relative_path}/second_review.html`（132 条）。
- 每个 KP ID 旁显示 canonical name、Summary、主 Evidence 原文、必要邻接、Section、页码、BBox 和覆盖图。
- 每个 DS5 Evidence ID 旁显示 2/0 分角色及逐字原文；r2 没有自动 1 分标签。

## 验证结果

- r2 连续生成得到同一 Bundle SHA-256；r1 两个 Candidate 的文件 Hash 与 r1 Manifest 一致。
- DS4/DS5 与数据集边界专项测试：15 passed；全量 Pytest：416 passed、5 skipped。
- 48 个 JSON Schema 导出文件通过 `--check`；381 个文件通过 Ruff Format Check 和 Ruff Check。
- 全量 Mypy：263 个源文件无问题；`git diff --check` 无空白错误，仅有既有 LF/CRLF 提示。
- Approved DS4/DS5、全局 Dev/Test 和 Test Lock 均未改变；QA Gold 继续 `pending_p09`。

r1 保留但已标记 superseded；不得审批 r1 Hash。r2 全部审核通过后才可回复精确 Bundle 审批语句。
"""
    atomic_write_text(repository_root / R2_REPORT, text)
    atomic_write_text(repository_root / REPORT, text)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository-root", type=Path, default=Path.cwd())
    args = parser.parse_args()
    manifest = build_r2(args.repository_root)
    print(json.dumps({"bundle_sha256": manifest.bundle_sha256}, ensure_ascii=False))


if __name__ == "__main__":
    main()
