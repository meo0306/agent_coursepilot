"""Build the fully audited P08 r3 Candidate after the Course Owner r2 review."""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import shutil
import unicodedata
from collections import defaultdict
from pathlib import Path
from typing import Any

from pydantic import JsonValue

from courserag.evals.schemas import (
    DS2EvidenceDataset,
    DS3KnowledgePointDataset,
    DS4QueryProcessingDataset,
    DS5RetrievalQADataset,
    EvidenceGroup,
    P08GoldBundleManifest,
    P08ReviewDecisions,
    P08SourcePackageDataset,
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
    ROOT,
    _artifact,
    _case_id,
    _char_terms,
    bundle_identity_sha256,
)
from evaluation.ds45_p08_revision import (
    _find_asset,
    _kp_maps,
    _other_kp_names,
    _package_maps,
    _preserve_terms,
    _primary_evidence_id,
    _split,
)
from evaluation.io import atomic_write_json, atomic_write_text

R2_DS4 = ROOT / "candidates/ds4/p08_query_processing_r2.json"
R2_DS5 = ROOT / "candidates/ds5/p08_retrieval_r2.json"
R3_DS4 = ROOT / "candidates/ds4/p08_query_processing_r3.json"
R3_DS5 = ROOT / "candidates/ds5/p08_retrieval_r3.json"
R2_PACKAGES = ROOT / "provenance/p08_query_source_packages_r2.json"
R3_PACKAGES = ROOT / "provenance/p08_query_source_packages_r3.json"
R3_SPLIT = ROOT / "provenance/p08_ds5_split_r3.json"
R2_MANIFEST = ROOT / "provenance/p08_gold_bundle_manifest_r2.json"
R3_MANIFEST = ROOT / "provenance/p08_gold_bundle_manifest_r3.json"
CANONICAL_MANIFEST = ROOT / "provenance/p08_gold_bundle_manifest.json"
DS4_HISTORY = ROOT / "provenance/p08_candidate_revision_history.json"
DS5_HISTORY = ROOT / "provenance/p08_ds5_candidate_revision_history.json"
ADJUDICATION = ROOT / "provenance/p08_r2_first_review_adjudication.json"
R3_AUDIT = ROOT / "provenance/p08_r3_relevance_audit.json"
R3_CHANGES = ROOT / "provenance/p08_r2_to_r3_record_changes.json"
REPORT = Path("docs/refactor/phase_reports/ED_PRE_P08_DS4_DS5_candidate_review.md")
R3_REPORT = Path("docs/refactor/phase_reports/ED_PRE_P08_DS4_DS5_candidate_review_r3.md")
R2_FEEDBACK = Path(
    "storage_eval/ds45_p08_review/"
    "7f6b22556e3261d242dbd2b425812eeb18489dc75f6086697d808bbffbfbdf52/"
    "review/p08_r2_first_review_7f6b22556e32.json"
)
R3_STRATEGY_SHA256 = hashlib.sha256(
    b"p08-retrieval-only-r3|course-owner-r2-adjudication|all-cross-section-no-inferred-link|"
    b"all-ds5-positive-containment-audit|topically-confusable-zero-selection|"
    b"source-readable-review-notes|qa-pending-p09"
).hexdigest()

ACCEPTED_RETURN_IDS = {
    "gold-qp-f2d8efac5f90b9a5f49565d07e7ace08",
    "gold-qp-7b85e02e75b7d33f8cb9d41e92740763",
    "gold-qp-9a7bb5277e494f08086e403e259b1596",
    "gold-qp-ca3f73c937d2f3fc63a319dab0ab56ab",
    "gold-qp-1295e08027ba26ed94310256d4caa620",
    "gold-qp-e4e5466f41b3b4633c96bab9a656f07e",
    "gold-rq-7090618bec396c846333abfb81029d56",
    "gold-rq-d9dd4101ac8fb9efafb64c72e9945dbe",
    "gold-rq-29a425eb2806b4415d1399c7b1108090",
    "gold-rq-1103d3ea159992c9570eb513449849dc",
    "gold-rq-4f1337c82359ed99cacadc072fff7f3e",
    "gold-rq-669a25ccdac0e79134acce61e630d231",
    "gold-rq-46b271bcca79ba38c735ff560695bdaf",
    "gold-rq-2a22ed6208732e08129e8f26d82827c5",
    "gold-rq-2779836e970d177064a610c3ba3da039",
    "gold-rq-b89ee3f2821f58f3ac89f4490b675206",
    "gold-rq-56d560c3f3d460cee13cefde4aa3d139",
}
OVERRIDDEN_RETURN_REASONS = {
    "gold-qp-02603bbe9adeec81f3255460d8e4cd95": (
        "保留：这是 MLP 专名必须保留、同时允许扩展为多层感知机的改写边界。"
    ),
    "gold-qp-0f01916ce1816bb190ce6c806b355ee3": (
        "保留：Q/K/V 是必须原样保留的复合专名，允许扩展为空是合法约束。"
    ),
    "gold-qp-6526a622079ad85f6df4ee79fe5df3d2": (
        "保留：NeRF 必须保留且神经辐射场是原文支持的允许扩展。"
    ),
    "gold-qp-b921b4a7c536cff24e4285a4acd36e34": (
        "保留：支付合规监控与异常交易检测是同课程内可合理区分的近似意图。"
    ),
    "gold-qp-ada746579b9e2d233b2e5e683daa611d": (
        "保留：下载地址在课程中不可回答，KP Linker 应避免错误链接。"
    ),
    "gold-qp-d2f7138edd4205e32b8489f228e927e0": (
        "保留：样本人数与统计显著性在课程中不可回答，Router 应进入审计路由。"
    ),
    "gold-rq-c7768ff4e1d2cf335e9904a63587632a": (
        "保留：Required Evidence 完整定义大模型，微调、应用和有用性片段不回答定义。"
    ),
    "gold-rq-210ff8d07fcc867a6b785dcd9fe9e836": (
        "保留：这是同课程两种不同 AI 应用模式的多证据比较案例。"
    ),
}
QUERY_OVERRIDES = {
    "gold-rq-7090618bec396c846333abfb81029d56": ("教材如何解释机器智能难以准确界定这一事实？"),
    "gold-rq-d9dd4101ac8fb9efafb64c72e9945dbe": ("教材如何说明谷歌为推广深度学习平台采取的行动？"),
    "gold-rq-29a425eb2806b4415d1399c7b1108090": (
        "教材如何说明位置编码与词特征向量的维数关系及组合方式？"
    ),
    "gold-rq-1103d3ea159992c9570eb513449849dc": (
        "教材所述 SLAM 在 GNSS 信号缺失时能够提供哪些能力？"
    ),
    "gold-rq-4f1337c82359ed99cacadc072fff7f3e": (
        "教材在什么分类器背景下、从什么角度引出样本集的线性可分性？"
    ),
    "gold-rq-669a25ccdac0e79134acce61e630d231": ("教材如何概括深度学习方法的应用范围及相对表现？"),
    "gold-rq-46b271bcca79ba38c735ff560695bdaf": (
        "图灵如何看待模拟人的物理存在对于展示智能的必要性？"
    ),
    "gold-rq-2a22ed6208732e08129e8f26d82827c5": (
        "课程实践要求掌握使用 ERNIE 完成哪一项 fine-tune 任务的全过程？"
    ),
    "gold-rq-2779836e970d177064a610c3ba3da039": (
        "数据准备与预处理在大模型开发和训练中处于什么位置？"
    ),
    "gold-rq-b89ee3f2821f58f3ac89f4490b675206": (
        "根据教材，大模型安全对齐关注什么目标，ERNIE 微调实践面向什么具体任务？"
    ),
    "gold-rq-56d560c3f3d460cee13cefde4aa3d139": ("教材如何说明刷脸支付从试点走向商用的应用进展？"),
    "gold-rq-a87fb66d116cd660f46758daa5368b5d": (
        "教材记录了哪个全仿真智能 AI 主持人应用实例，其发布者、时间和场合是什么？"
    ),
}


def _normalized_text(value: str) -> str:
    return "".join(char.lower() for char in unicodedata.normalize("NFKC", value) if char.isalnum())


def _r3_query(case: RetrievalQACase, kp_by_id: dict[str, Any]) -> str:
    if case.query_type == "cross_section":
        names = [kp_by_id[item].canonical_name for item in case.expected_knowledge_points]
        return f"教材分别如何说明“{names[0]}”和“{names[1]}”？"
    return QUERY_OVERRIDES.get(case.record_id, case.query)


def _evidence_kp_map(ds3: DS3KnowledgePointDataset) -> dict[str, list[str]]:
    result: dict[str, list[str]] = defaultdict(list)
    for kp in ds3.knowledge_points:
        for link in kp.evidence_links:
            result[link.evidence_id].append(kp.canonical_name)
    return {key: sorted(values) for key, values in result.items()}


def _containment_positives(
    case: RetrievalQACase,
    evidence: list[Any],
    required_ids: set[str],
) -> tuple[dict[str, int], list[EvidenceGroup], list[dict[str, Any]]]:
    if not case.answerable:
        return {}, [], []
    by_id = {item.evidence_id: item for item in evidence}
    required_text = {item: _normalized_text(by_id[item].gold_text) for item in required_ids}
    positives: dict[str, int] = {}
    groups: list[EvidenceGroup] = []
    audit: list[dict[str, Any]] = []
    for candidate in evidence:
        if candidate.course_id != case.course_id or candidate.evidence_id in required_ids:
            continue
        candidate_text = _normalized_text(candidate.gold_text)
        matches = [
            evidence_id
            for evidence_id, value in required_text.items()
            if min(len(value), len(candidate_text)) >= 8
            and (value in candidate_text or candidate_text in value)
        ]
        if not matches:
            continue
        contains_required = [item for item in matches if required_text[item] in candidate_text]
        if len(required_ids) == 1 and contains_required:
            positives[candidate.evidence_id] = 2
            groups.append(
                EvidenceGroup(
                    group_id=f"eg-alt-{hashlib.sha256(candidate.evidence_id.encode()).hexdigest()[:16]}",
                    sufficiency="complete",
                    required_evidence_ids=[candidate.evidence_id],
                )
            )
            verdict = "alternate_complete"
        else:
            positives[candidate.evidence_id] = 1
            verdict = "partial_containment"
        audit.append(
            {
                "evidence_id": candidate.evidence_id,
                "matched_required_ids": matches,
                "verdict": verdict,
            }
        )
    return positives, groups, audit


def _negative_score(
    *,
    case: RetrievalQACase,
    query: str,
    candidate: Any,
    required: list[Any],
    evidence_to_package: dict[str, str],
    evidence_to_kps: dict[str, list[str]],
    expected_names: list[str],
) -> tuple[int, int, int, int, str]:
    query_terms = _char_terms(query + " ".join(expected_names))
    candidate_basis = candidate.gold_text + " ".join(evidence_to_kps.get(candidate.evidence_id, []))
    lexical = len(query_terms & _char_terms(candidate_basis))
    same_package = int(evidence_to_package[candidate.evidence_id] == case.source_package_id)
    required_types = {item.semantic_unit_type for item in required}
    same_type = int(candidate.semantic_unit_type in required_types)
    same_top_section = int(
        bool(required)
        and candidate.source_span.section_path[:2] == required[0].source_span.section_path[:2]
    )
    total = lexical * 10 + same_package * 7 + same_type * 2 + same_top_section
    tie = hashlib.sha256(f"r3|{case.record_id}|{candidate.evidence_id}".encode()).hexdigest()
    return total, lexical, same_package, same_type, tie


def _select_negatives(
    *,
    case: RetrievalQACase,
    query: str,
    evidence: list[Any],
    excluded_ids: set[str],
    evidence_to_package: dict[str, str],
    evidence_to_kps: dict[str, list[str]],
    expected_names: list[str],
) -> tuple[list[Any], list[dict[str, Any]]]:
    by_id = {item.evidence_id: item for item in evidence}
    required = [by_id[item] for item in sorted(excluded_ids) if item in by_id]
    ranked: list[tuple[tuple[int, int, int, int, str], Any]] = []
    for candidate in evidence:
        if candidate.course_id != case.course_id or candidate.evidence_id in excluded_ids:
            continue
        score = _negative_score(
            case=case,
            query=query,
            candidate=candidate,
            required=required,
            evidence_to_package=evidence_to_package,
            evidence_to_kps=evidence_to_kps,
            expected_names=expected_names,
        )
        ranked.append((score, candidate))
    ranked.sort(key=lambda item: (-item[0][0], item[0][4]))
    selected = [item[1] for item in ranked[:4]]
    audit = [
        {
            "rank": index,
            "evidence_id": item.evidence_id,
            "score": score[0],
            "lexical_overlap": score[1],
            "same_source_package": bool(score[2]),
            "same_semantic_type": bool(score[3]),
            "linked_knowledge_points": evidence_to_kps.get(item.evidence_id, []),
            "selected_as_zero": index <= 4,
        }
        for index, (score, item) in enumerate(ranked[:8], 1)
    ]
    if len(selected) != 4:
        raise ValueError(f"r3 requires four hard negatives: {case.record_id}")
    return selected, audit


def _revise_ds5(
    ds5: DS5RetrievalQADataset,
    ds2: DS2EvidenceDataset,
    ds3: DS3KnowledgePointDataset,
    evidence_to_package: dict[str, str],
) -> tuple[DS5RetrievalQADataset, dict[str, str], dict[str, Any]]:
    kp_by_id, _ = _kp_maps(ds3)
    evidence_to_kps = _evidence_kp_map(ds3)
    by_id = {item.evidence_id: item for item in ds2.evidence}
    revised: list[RetrievalQACase] = []
    id_map: dict[str, str] = {}
    case_audits: dict[str, Any] = {}
    for case in ds5.cases:
        query = _r3_query(case, kp_by_id)
        required_ids = {
            evidence_id
            for group in case.gold_evidence_groups
            for evidence_id in group.required_evidence_ids
        }
        expected_names = [kp_by_id[item].canonical_name for item in case.expected_knowledge_points]
        containment, alternate_groups, positive_audit = _containment_positives(
            case, ds2.evidence, required_ids
        )
        positive_ids = required_ids | set(containment)
        negatives, negative_audit = _select_negatives(
            case=case,
            query=query,
            evidence=ds2.evidence,
            excluded_ids=positive_ids,
            evidence_to_package=evidence_to_package,
            evidence_to_kps=evidence_to_kps,
            expected_names=expected_names,
        )
        judgments: list[RetrievalEvidenceJudgment] = []
        for evidence_id in sorted(required_ids):
            judgments.append(
                RetrievalEvidenceJudgment(
                    evidence_id=evidence_id,
                    relevance=2,
                    role="required",
                    evidence_record_sha256=record_digest(by_id[evidence_id]),
                    rationale="Approved DS2 原文直接提供问题所需事实，属于主完整 Evidence Group。",
                )
            )
        for evidence_id, relevance in sorted(containment.items()):
            judgments.append(
                RetrievalEvidenceJudgment(
                    evidence_id=evidence_id,
                    relevance=relevance,
                    role="required" if relevance == 2 else "helpful",
                    evidence_record_sha256=record_digest(by_id[evidence_id]),
                    rationale=(
                        "该 Approved DS2 记录完整包含主证据原文，可独立回答本问题。"
                        if relevance == 2
                        else "该 Approved DS2 记录是主证据表格或段落的局部片段，只覆盖问题的一部分。"
                    ),
                )
            )
        for item in negatives:
            kp_names = evidence_to_kps.get(item.evidence_id, [])
            topic = "、".join(kp_names) if kp_names else "同课程相邻主题"
            judgments.append(
                RetrievalEvidenceJudgment(
                    evidence_id=item.evidence_id,
                    relevance=0,
                    role="hard_negative",
                    evidence_record_sha256=record_digest(item),
                    rationale=(
                        f"该片段涉及“{topic}”，在术语、Section 或语义类型上容易混淆；"
                        "但它不提供本问题绑定的完整事实，人工候选审核前标为 0。"
                    ),
                )
            )
        new_id = _case_id(str(case.course_id), query, sorted(required_ids))
        groups = [
            EvidenceGroup(
                group_id=f"eg-{new_id[-16:]}-{index:02d}",
                sufficiency=group.sufficiency,
                required_evidence_ids=group.required_evidence_ids,
            )
            for index, group in enumerate([*case.gold_evidence_groups, *alternate_groups], 1)
        ]
        values = case.model_dump(mode="json")
        unanswerable_audit = case.unanswerable_audit
        if unanswerable_audit is not None:
            unanswerable_audit = unanswerable_audit.model_copy(
                update={
                    "nearest_false_positive_evidence_ids": [item.evidence_id for item in negatives]
                }
            )
        values.update(
            {
                "record_id": new_id,
                "query": query,
                "query_sha256": hashlib.sha256(query.encode()).hexdigest(),
                "gold_evidence_groups": [item.model_dump(mode="json") for item in groups],
                "supporting_evidence_ids": sorted(positive_ids),
                "evidence_judgments": [item.model_dump(mode="json") for item in judgments],
                "graded_relevance": {item.evidence_id: item.relevance for item in judgments},
                "hard_negative_evidence_ids": [item.evidence_id for item in negatives],
                "unanswerable_audit": (
                    unanswerable_audit.model_dump(mode="json")
                    if unanswerable_audit is not None
                    else None
                ),
                "generation_strategy_sha256": R3_STRATEGY_SHA256,
                "candidate_source": "source_grounded_course_owner_adjudicated_r3",
            }
        )
        item = RetrievalQACase.model_validate(values)
        revised.append(item)
        id_map[case.record_id] = item.record_id
        case_audits[item.record_id] = {
            "r2_record_id": case.record_id,
            "r3_record_id": item.record_id,
            "query_changed": case.query != query,
            "positive_containment_audit": positive_audit,
            "negative_ranking_top8": negative_audit,
            "r2_hard_negative_ids": case.hard_negative_evidence_ids,
            "r3_hard_negative_ids": item.hard_negative_evidence_ids,
        }
    revised.sort(key=lambda item: (item.query_type, item.record_id))
    return (
        DS5RetrievalQADataset(
            dataset_id=ds5.dataset_id,
            dataset_version="p08-r3",
            cases=revised,
        ),
        id_map,
        case_audits,
    )


def _revise_ds4(
    ds4: DS4QueryProcessingDataset,
    ds5_r3: DS5RetrievalQADataset,
    ds5_id_map: dict[str, str],
    ds3: DS3KnowledgePointDataset,
    evidence_to_package: dict[str, str],
) -> tuple[DS4QueryProcessingDataset, dict[str, str]]:
    kp_by_id, _ = _kp_maps(ds3)
    ds5_by_id = {item.record_id: item for item in ds5_r3.cases}
    revised: list[QueryProcessingCase] = []
    id_map: dict[str, str] = {}
    for case in ds4.cases:
        if case.mirrored_ds5_case_id is None:
            revised.append(case)
            id_map[case.record_id] = case.record_id
            continue
        source = ds5_by_id[ds5_id_map[case.mirrored_ds5_case_id]]
        names = [kp_by_id[item].canonical_name for item in source.expected_knowledge_points]
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
                aliases if case.capability == "expansion_rewrite_constraints" else []
            ),
            forbidden_expansions=(
                _other_kp_names(
                    str(source.course_id),
                    str(source.source_package_id),
                    kp_by_id,
                    evidence_to_package,
                )
                if case.capability == "expansion_rewrite_constraints"
                else []
            ),
            must_preserve_terms=_preserve_terms(source.query, names),
            must_preserve_filters=True,
        )
        if case.record_id == "gold-qp-f2d8efac5f90b9a5f49565d07e7ace08":
            expected = expected.model_copy(
                update={
                    "allowed_expansions": ["谷歌Duplex个人助理"],
                    "forbidden_expansions": ["图灵测试", "IBM沃森问答系统"],
                    "must_preserve_terms": ["Google Duplex", "源代码仓库地址"],
                }
            )
        unchanged = (
            source.record_id == case.mirrored_ds5_case_id
            and source.query == case.raw_query
            and expected == case.expected
        )
        if unchanged:
            item = case
        else:
            identity = f"r3|{case.capability}|mirror|{source.record_id}"
            record_id = f"gold-qp-{hashlib.sha256(identity.encode()).hexdigest()[:32]}"
            item = QueryProcessingCase(
                record_id=record_id,
                candidate_source="source_grounded_course_owner_adjudicated_r3",
                raw_query=source.query,
                expected=expected,
                course_id=source.course_id,
                capability=case.capability,
                query_family_id=source.query_family_id,
                source_package_id=source.source_package_id,
                mirrored_ds5_case_id=source.record_id,
                upstream_approved_sha256=case.upstream_approved_sha256,
                query_sha256=hashlib.sha256(source.query.encode()).hexdigest(),
                generation_strategy_sha256=R3_STRATEGY_SHA256,
                approval_scope=APPROVAL_SCOPE,
            )
        revised.append(item)
        id_map[case.record_id] = item.record_id
    revised.sort(
        key=lambda item: (str(item.capability), item.mirrored_ds5_case_id is None, item.record_id)
    )
    return (
        DS4QueryProcessingDataset(
            dataset_id=ds4.dataset_id,
            dataset_version="p08-r3",
            cases=revised,
        ),
        id_map,
    )


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
    return (
        f"<section class='kp'><p><code>{kp.gold_kp_id}</code> → "
        f"<b>{html.escape(kp.canonical_name)}</b></p>"
        f"<p><b>Summary：</b>{html.escape(kp.summary)}</p>"
        + _evidence_html(evidence_by_id[_primary_evidence_id(kp)])
        + "</section>"
    )


def _test_purpose(item: Any) -> str:
    if isinstance(item, RetrievalQACase):
        purposes = {
            "cross_section": "同时召回两个不同 Section 的完整证据；不要求或暗示二者存在原文未说明的联系。",
            "unanswerable": "验证全课程检索后仍无完整正例，并避免最近假阳性被误判为答案。",
            "comparison": "区分两个同课程概念或应用，并完整召回双方证据。",
        }
        return purposes.get(
            str(item.query_type), "验证 Query 与完整正例、部分正例及同课程易混淆 0 分项的排序。"
        )
    purposes = {
        "query_normalization": "验证噪声归一化或已经规范 Query 的幂等保持。",
        "knowledge_point_linking": "验证正确 KP 链接；不可回答的专门边界案例允许空链接。",
        "filter_parsing": "course_id 来自课程级检索作用域，不要求 Query 文本显式写出课程名。",
        "query_router": "验证可回答检索路由和不可回答审计路由的区分。",
        "expansion_rewrite_constraints": "验证允许扩展、禁止主题漂移及专名/过滤条件保持。",
    }
    return purposes[str(item.capability)]


def _review_html(
    *,
    title: str,
    bundle_sha256: str,
    review_pass: str,
    displayed_records: list[Any],
    expected_ids: list[str],
    carried_pass_ids: list[str],
    adjudication_notes: dict[str, str],
    evidence_by_id: dict[str, Any],
    kp_by_id: dict[str, Any],
    package_by_id: dict[str, Any],
) -> str:
    cards: list[str] = []
    for item in displayed_records:
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
            body = (
                f"<h3>{html.escape(item.query)}</h3>"
                f"<p>{item.query_type} · {item.difficulty} · {item.course_id} · {item.split} · "
                f"Stratum {item.evaluation_stratum} · QA {item.qa_gold_status}</p>"
                + package_line
                + "<h4>Knowledge Point：ID → 名称 → Summary → 主证据原文</h4>"
                + kp_blocks
                + "<h4>Retrieval 相关性：ID → 2/1/0 分 → 原文</h4>"
                + evidence_blocks
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
        adjudication = (
            f"<p class='adjudication'><b>r2 退回裁决：</b>"
            f"{html.escape(adjudication_notes[item.record_id])}</p>"
            if item.record_id in adjudication_notes
            else ""
        )
        cards.append(
            f"<article id='{item.record_id}'><code>{item.record_id}</code>"
            f"<p class='purpose'><b>测试目的：</b>{html.escape(_test_purpose(item))}</p>"
            f"{adjudication}{body}"
            f"<label><input type='radio' name='{item.record_id}' value='pass'>通过</label> "
            f"<label><input type='radio' name='{item.record_id}' value='return'>退回</label>"
            f"<textarea placeholder='退回必须填写原因；备注会写入导出 JSON'></textarea></article>"
        )
    expected_json = json.dumps(expected_ids, ensure_ascii=False)
    carried_json = json.dumps(carried_pass_ids, ensure_ascii=False)
    return f"""<!doctype html><html lang='zh-CN'><head><meta charset='utf-8'><title>{html.escape(title)}</title>
<style>body{{font:15px/1.55 system-ui;margin:24px;max-width:1320px}}article{{border:1px solid #aaa;border-radius:8px;padding:16px;margin:16px 0}}blockquote,pre{{white-space:pre-wrap;background:#f5f5f5;padding:10px}}img{{max-width:100%;border:1px solid #ddd}}textarea{{display:block;width:98%;min-height:48px;margin-top:8px}}.sticky{{position:sticky;top:0;background:white;padding:8px;border-bottom:1px solid #ddd;z-index:2}}.kp{{border-left:4px solid #567;padding-left:12px;margin:8px 0}}.purpose{{background:#eef6ff;padding:8px}}.adjudication{{background:#fff3cd;padding:8px}}</style></head>
<body><div class='sticky'><b>{html.escape(title)}</b> · Bundle <code>{bundle_sha256}</code> · 审核人 <input id='reviewer' value='course_owner'> · <button onclick='exportReview()'>导出审核 JSON</button></div>
<p>本页只显示需要重新首审的变化记录；{len(carried_pass_ids)} 条 Hash 未变化的 r2 首审决定由裁决记录继承。退回时必须填写原因，导出 JSON 会保存备注。</p>{"".join(cards)}
<script>const expected={expected_json};const carried={carried_json};const key='p08-r3-{bundle_sha256}-{review_pass}';function save(){{const d=JSON.parse(localStorage.getItem(key)||'{{}}');document.querySelectorAll('article').forEach(a=>{{const r=a.querySelector('input:checked');if(r)d[a.id]={{decision:r.value,note:a.querySelector('textarea').value}}}});localStorage.setItem(key,JSON.stringify(d));}}document.addEventListener('change',save);document.addEventListener('input',save);const old=JSON.parse(localStorage.getItem(key)||'{{}}');Object.entries(old).forEach(([id,v])=>{{const a=document.getElementById(id);if(a){{const r=a.querySelector(`input[value="${{v.decision}}"]`);if(r)r.checked=true;a.querySelector('textarea').value=v.note||'';}}}});function exportReview(){{save();const d=JSON.parse(localStorage.getItem(key)||'{{}}');const reviewed=expected.filter(id=>carried.includes(id)||d[id]);const returned=reviewed.filter(id=>d[id]&&d[id].decision==='return');const missingNotes=returned.filter(id=>!(d[id].note||'').trim());if(missingNotes.length){{alert('以下退回记录缺少原因：'+missingNotes.join(', '));return;}}const notes={{}};Object.entries(d).forEach(([id,v])=>{{if((v.note||'').trim())notes[id]=v.note.trim();}});const payload={{schema_version:'courserag.p08-review-decisions.v1',bundle_sha256:'{bundle_sha256}',review_pass:'{review_pass}',expected_record_ids:expected,reviewed_record_ids:reviewed,returned_record_ids:returned,record_notes:notes,reviewer_id:document.getElementById('reviewer').value||'course_owner',reviewed_at:new Date().toISOString()}};const b=new Blob([JSON.stringify(payload,null,2)],{{type:'application/json'}});const a=document.createElement('a');a.href=URL.createObjectURL(b);a.download='p08_r3_{review_pass}_review_{bundle_sha256[:12]}.json';a.click();}}</script></body></html>"""


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
    changed_ids: set[str],
    adjudication_notes: dict[str, str],
) -> tuple[Path, str, str, dict[str, str]]:
    review_dir = repository_root / "storage_eval/ds45_p08_review" / bundle_sha256
    assets = review_dir / "assets"
    assets.mkdir(parents=True, exist_ok=True)
    evidence_by_id = {item.evidence_id: item for item in ds2.evidence}
    kp_by_id, _ = _kp_maps(ds3)
    package_by_id = {item.package_id: item for item in packages.packages}
    all_records: dict[str, QueryProcessingCase | RetrievalQACase] = {
        item.record_id: item for item in ds4.cases
    }
    all_records.update({item.record_id: item for item in ds5.cases})
    displayed_first = [all_records[item] for item in first_ids if item in changed_ids]
    second = [all_records[item] for item in second_ids]
    used: set[str] = set()
    for item in [*displayed_first, *second]:
        if isinstance(item, RetrievalQACase):
            used.update(judgment.evidence_id for judgment in item.evidence_judgments)
            for kp_id in item.expected_knowledge_points:
                used.add(_primary_evidence_id(kp_by_id[kp_id]))
        else:
            for kp_id in item.expected.linked_knowledge_points:
                used.add(_primary_evidence_id(kp_by_id[kp_id]))
    for evidence_id in sorted(used):
        shutil.copyfile(_find_asset(repository_root, evidence_id), assets / f"{evidence_id}.png")
    carried = [item for item in first_ids if item not in changed_ids]
    atomic_write_text(
        review_dir / "index.html",
        _review_html(
            title=f"P08 r3 变化记录首轮复核（{len(displayed_first)} 条）",
            bundle_sha256=bundle_sha256,
            review_pass="first",
            displayed_records=displayed_first,
            expected_ids=first_ids,
            carried_pass_ids=carried,
            adjudication_notes=adjudication_notes,
            evidence_by_id=evidence_by_id,
            kp_by_id=kp_by_id,
            package_by_id=package_by_id,
        ),
    )
    atomic_write_text(
        review_dir / "second_review.html",
        _review_html(
            title="P08 r3 盲化二轮审核（132 条）",
            bundle_sha256=bundle_sha256,
            review_pass="second",
            displayed_records=second,
            expected_ids=second_ids,
            carried_pass_ids=[],
            adjudication_notes=adjudication_notes,
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


def _write_histories(repository_root: Path) -> None:
    histories = (
        (
            DS4_HISTORY,
            "courserag-p08-ds4-query-processing",
            ((1, ROOT / "candidates/ds4/p08_query_processing_r1.json"), (2, R2_DS4), (3, R3_DS4)),
        ),
        (
            DS5_HISTORY,
            "courserag-p08-ds5-retrieval",
            ((1, ROOT / "candidates/ds5/p08_retrieval_r1.json"), (2, R2_DS5), (3, R3_DS5)),
        ),
    )
    for output, dataset_id, revisions in histories:
        entries = []
        for revision, path in revisions:
            status = "pending_course_owner_review" if revision == 3 else "superseded"
            reason = (
                "Comprehensive r3 relevance audit and source-readable review await Course Owner approval."
                if revision == 3
                else "Superseded without deletion by the next immutable Candidate revision."
            )
            entries.append(
                CandidateRevisionArtifact(
                    revision=revision,
                    candidate_relative_path=path.as_posix(),
                    candidate_file_sha256=sha256_file(repository_root / path),
                    status=status,
                    reason=reason,
                )
            )
        history = CandidateRevisionHistory(
            dataset_id=dataset_id,
            dataset_version="p08-r3",
            revisions=entries,
        )
        atomic_write_json(repository_root / output, history.model_dump(mode="json"))


def build_r3(repository_root: Path) -> P08GoldBundleManifest:
    repository_root = repository_root.resolve()
    ds2 = DS2EvidenceDataset.model_validate_json(
        (repository_root / ROOT / "approved/ds2/p06_evidence.json").read_text(encoding="utf-8")
    )
    ds3 = DS3KnowledgePointDataset.model_validate_json(
        (repository_root / ROOT / "approved/ds3/p07_knowledge_points.json").read_text(
            encoding="utf-8"
        )
    )
    ds4_r2 = DS4QueryProcessingDataset.model_validate_json(
        (repository_root / R2_DS4).read_text(encoding="utf-8")
    )
    ds5_r2 = DS5RetrievalQADataset.model_validate_json(
        (repository_root / R2_DS5).read_text(encoding="utf-8")
    )
    packages_r2 = P08SourcePackageDataset.model_validate_json(
        (repository_root / R2_PACKAGES).read_text(encoding="utf-8")
    )
    manifest_r2 = P08GoldBundleManifest.model_validate_json(
        (repository_root / R2_MANIFEST).read_text(encoding="utf-8")
    )
    feedback = P08ReviewDecisions.model_validate_json(
        (repository_root / R2_FEEDBACK).read_text(encoding="utf-8")
    )
    if feedback.bundle_sha256 != manifest_r2.bundle_sha256 or feedback.review_pass != "first":
        raise ValueError("r2 first-review feedback targets another Bundle")
    if set(feedback.returned_record_ids) != ACCEPTED_RETURN_IDS | set(OVERRIDDEN_RETURN_REASONS):
        raise ValueError("r2 returned IDs differ from the adjudicated set")
    evidence_to_package, _ = _package_maps(packages_r2)
    ds5_r3, ds5_id_map, relevance_audit = _revise_ds5(ds5_r2, ds2, ds3, evidence_to_package)
    ds4_r3, ds4_id_map = _revise_ds4(ds4_r2, ds5_r3, ds5_id_map, ds3, evidence_to_package)
    packages_values = packages_r2.model_dump(mode="json")
    packages_values["dataset_version"] = "p08-r3"
    packages_r3 = P08SourcePackageDataset.model_validate(packages_values)
    split_r3 = _split(ds5_r3)
    atomic_write_json(repository_root / R3_DS4, ds4_r3.model_dump(mode="json"))
    atomic_write_json(repository_root / R3_DS5, ds5_r3.model_dump(mode="json"))
    atomic_write_json(repository_root / R3_PACKAGES, packages_r3.model_dump(mode="json"))
    atomic_write_json(repository_root / R3_SPLIT, split_r3.model_dump(mode="json"))

    all_records = [*ds4_r3.cases, *ds5_r3.cases]
    record_hashes = {item.record_id: record_digest(item) for item in all_records}
    first_ids = [item.record_id for item in all_records]
    first_groups = [first_ids[index : index + 20] for index in range(0, 160, 20)]
    fixed_second = [
        item.record_id
        for item in ds4_r3.cases
        if item.capability in {"filter_parsing", "expansion_rewrite_constraints"}
    ]
    sampled = [
        item.record_id
        for item in ds4_r3.cases
        if item.capability not in {"filter_parsing", "expansion_rewrite_constraints"}
    ]
    sampled.sort(key=lambda item: hashlib.sha256(item.encode()).hexdigest())
    second_ids = [item.record_id for item in ds5_r3.cases] + fixed_second + sampled[:8]
    bundle_sha = bundle_identity_sha256(
        revision=3,
        ds4_sha256=sha256_file(repository_root / R3_DS4),
        ds5_sha256=sha256_file(repository_root / R3_DS5),
        source_packages_sha256=sha256_file(repository_root / R3_PACKAGES),
        split_sha256=sha256_file(repository_root / R3_SPLIT),
        candidate_record_sha256=record_hashes,
        upstream_approved_sha256=manifest_r2.upstream_approved_sha256,
        preserved_upstream_sha256=manifest_r2.preserved_upstream_sha256,
        p06_unmapped_evidence_ids=manifest_r2.p06_unmapped_evidence_ids,
        diagnostic_evidence_ids=manifest_r2.diagnostic_evidence_ids,
        first_review_groups=first_groups,
        second_review_ids=second_ids,
    )
    r2_hashes = manifest_r2.candidate_record_sha256
    changed_ids = {
        item.record_id
        for item in all_records
        if item.record_id not in r2_hashes or record_digest(item) != r2_hashes[item.record_id]
    }
    accepted_r3_ids = {
        ds4_id_map[record_id] for record_id in ACCEPTED_RETURN_IDS if record_id in ds4_id_map
    } | {ds5_id_map[record_id] for record_id in ACCEPTED_RETURN_IDS if record_id in ds5_id_map}
    if len(accepted_r3_ids) != len(ACCEPTED_RETURN_IDS) or not accepted_r3_ids.issubset(
        changed_ids
    ):
        raise ValueError("every accepted r2 return must have a substantive r3 record change")
    adjudication_notes = {
        ds4_id_map[record_id]: reason
        for record_id, reason in OVERRIDDEN_RETURN_REASONS.items()
        if record_id in ds4_id_map
    }
    adjudication_notes.update(
        {
            ds5_id_map[record_id]: reason
            for record_id, reason in OVERRIDDEN_RETURN_REASONS.items()
            if record_id in ds5_id_map
        }
    )
    changed_ids.update(adjudication_notes)
    review_dir, first_sha, second_sha, asset_sha = _write_review(
        repository_root,
        bundle_sha,
        ds2,
        ds3,
        packages_r3,
        ds4_r3,
        ds5_r3,
        first_ids,
        second_ids,
        changed_ids,
        adjudication_notes,
    )
    manifest = P08GoldBundleManifest(
        dataset_id=manifest_r2.dataset_id,
        dataset_version="p08-r3",
        revision=3,
        ds4_candidate=_artifact(repository_root, repository_root / R3_DS4),
        ds5_candidate=_artifact(repository_root, repository_root / R3_DS5),
        source_packages=_artifact(repository_root, repository_root / R3_PACKAGES),
        split_manifest=_artifact(repository_root, repository_root / R3_SPLIT),
        candidate_record_sha256=record_hashes,
        upstream_approved_sha256=manifest_r2.upstream_approved_sha256,
        preserved_upstream_sha256=manifest_r2.preserved_upstream_sha256,
        p06_unmapped_evidence_ids=manifest_r2.p06_unmapped_evidence_ids,
        diagnostic_evidence_ids=manifest_r2.diagnostic_evidence_ids,
        first_review_groups=first_groups,
        second_review_ids=second_ids,
        review_pack_relative_path=review_dir.relative_to(repository_root).as_posix(),
        review_pack_index_sha256=first_sha,
        second_review_index_sha256=second_sha,
        review_asset_sha256=asset_sha,
        bundle_sha256=bundle_sha,
    )
    atomic_write_json(repository_root / R3_MANIFEST, manifest.model_dump(mode="json"))
    atomic_write_json(repository_root / CANONICAL_MANIFEST, manifest.model_dump(mode="json"))
    adjudication: dict[str, JsonValue] = {
        "schema_version": "courserag.p08-r2-first-review-adjudication.v1",
        "source_feedback": {
            "path": R2_FEEDBACK.as_posix(),
            "sha256": sha256_file(repository_root / R2_FEEDBACK),
            "record_notes_present": bool(feedback.record_notes),
        },
        "r2_bundle_sha256": manifest_r2.bundle_sha256,
        "accepted_return_ids": list(sorted(ACCEPTED_RETURN_IDS)),
        "overridden_return_reasons": dict(OVERRIDDEN_RETURN_REASONS),
        "decision": "option_b_comprehensive_r3",
    }
    atomic_write_json(repository_root / ADJUDICATION, adjudication)
    atomic_write_json(
        repository_root / R3_AUDIT,
        {
            "schema_version": "courserag.p08-r3-relevance-audit.v1",
            "r3_bundle_sha256": manifest.bundle_sha256,
            "case_count": len(ds5_r3.cases),
            "cases": relevance_audit,
        },
    )
    reverse_ds4 = {value: key for key, value in ds4_id_map.items()}
    reverse_ds5 = {value: key for key, value in ds5_id_map.items()}
    changes: dict[str, JsonValue] = {
        "schema_version": "courserag.p08-r2-to-r3-record-changes.v1",
        "r2_bundle_sha256": manifest_r2.bundle_sha256,
        "r3_bundle_sha256": manifest.bundle_sha256,
        "changed_record_ids": list(sorted(changed_ids)),
        "carried_record_ids": list(sorted(set(first_ids) - changed_ids)),
        "r3_to_r2_id": {**reverse_ds4, **reverse_ds5},
    }
    atomic_write_json(repository_root / R3_CHANGES, changes)
    _write_histories(repository_root)
    _write_report(repository_root, manifest, ds4_r3, ds5_r3, changed_ids)
    return manifest


def _write_report(
    repository_root: Path,
    manifest: P08GoldBundleManifest,
    ds4: DS4QueryProcessingDataset,
    ds5: DS5RetrievalQADataset,
    changed_ids: set[str],
) -> None:
    cross = sum(item.query_type == "cross_section" for item in ds5.cases)
    helpful = sum(
        judgment.relevance == 1 for item in ds5.cases for judgment in item.evidence_judgments
    )
    attestation_text = ""
    first_attestation_path = ROOT / "reviews/p08_r3_first_review_decisions.json"
    second_attestation_path = ROOT / "reviews/p08_r3_second_review_decisions.json"
    if (repository_root / first_attestation_path).is_file() and (
        repository_root / second_attestation_path
    ).is_file():
        first_attestation = P08ReviewDecisions.model_validate_json(
            (repository_root / first_attestation_path).read_text(encoding="utf-8")
        )
        second_attestation = P08ReviewDecisions.model_validate_json(
            (repository_root / second_attestation_path).read_text(encoding="utf-8")
        )
        first_ids = [item for group in manifest.first_review_groups for item in group]
        if (
            first_attestation.bundle_sha256 != manifest.bundle_sha256
            or second_attestation.bundle_sha256 != manifest.bundle_sha256
            or first_attestation.reviewed_record_ids != first_ids
            or second_attestation.reviewed_record_ids != manifest.second_review_ids
            or first_attestation.returned_record_ids
            or second_attestation.returned_record_ids
        ):
            raise ValueError("P08 review attestations do not cover the current r3 Bundle")
        attestation_text = f"""

## Course Owner 审核结论

2026-08-06，Course Owner 在会话中明确确认两轮审核全部通过、零退回，并要求不再提供
浏览器导出的 JSON。该结论已固化为 `{first_attestation_path.as_posix()}` 和
`{second_attestation_path.as_posix()}`；正式提升仍等待独立的精确 Bundle 批准语句。
"""
    text = f"""# ED-PRE08 DS4/DS5 r3 Candidate 审核报告

## r2 首轮裁决与全面修订

- r2 首轮反馈包含 160 条已审记录、25 条退回；导出文件未携带文本备注。
- 独立复核接受 17 条退回，8 条按测试目的保留；裁决见 `{ADJUDICATION.as_posix()}`。
- 全部 {cross} 条 Cross-section 改为分别说明两项，不再要求推断原文未建立的联系。
- 全部 100 条 DS5 均重新执行正例包含关系和同课程混淆负例审计；完整 Top-8 排名见 `{R3_AUDIT.as_posix()}`。
- r3 恢复经原文包含关系证明的部分相关 1 分项，共 {helpful} 个，不为配额制造 1 分。
- 审核导出现在保存 `record_notes`、`reviewer_id` 和 `reviewed_at`，退回但未写原因时禁止导出。

## r3 审核入口

- Bundle SHA-256：`{manifest.bundle_sha256}`
- DS4：{len(ds4.cases)}；DS5：{len(ds5.cases)}；变化记录：{len(changed_ids)}。
- 变化记录首轮复核：`{manifest.review_pack_relative_path}/index.html`。
- 固定 132 条盲化二轮：`{manifest.review_pack_relative_path}/second_review.html`。
- 未变化记录通过精确记录 Hash 继承 r2 首轮决定；不会继承发生任何字段变化的记录。

r3 仍是 Candidate；Approved、Dev/Test 和 Test Lock 均未改变。{attestation_text}
"""
    atomic_write_text(repository_root / R3_REPORT, text)
    atomic_write_text(repository_root / REPORT, text)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository-root", type=Path, default=Path.cwd())
    args = parser.parse_args()
    manifest = build_r3(args.repository_root)
    print(json.dumps({"bundle_sha256": manifest.bundle_sha256}, ensure_ascii=False))


if __name__ == "__main__":
    main()
