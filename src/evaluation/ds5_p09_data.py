"""Build source-grounded P09 QA and Context Gold Candidates from Approved P08 DS5."""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import math
import re
import unicodedata
from collections import Counter
from pathlib import Path
from typing import Any

from courserag.evals.schemas import (
    ClaimEvidenceSupport,
    DS2EvidenceDataset,
    DS3KnowledgePointDataset,
    DS5RetrievalQADataset,
    EvidenceRecord,
    GoldClaim,
    P09AnswerVariant,
    P09ContextGoldCase,
    P09ContextGoldDataset,
    P09ForbiddenClaim,
    P09GoldBundleManifest,
    P09NecessaryContextNeighbor,
    P09QAGoldCase,
    P09QAGoldDataset,
)
from evaluation.contracts import HashedArtifact, ReviewStatus, TestLock
from evaluation.corpus_fixtures import sha256_file
from evaluation.datasets import canonical_json_bytes, record_digest
from evaluation.io import atomic_write_json, atomic_write_text

DATASET_ROOT = Path("datasets/courserag_eval/v1")
P08_PATH = DATASET_ROOT / "approved/ds5/p08_retrieval.json"
DS2_PATH = DATASET_ROOT / "approved/ds2/p06_evidence.json"
DS3_PATH = DATASET_ROOT / "approved/ds3/p07_knowledge_points.json"
P05_PATH = DATASET_ROOT / "approved/ds1/p05_ocr.json"
P08_APPROVAL_PATH = DATASET_ROOT / "provenance/p08_gold_bundle_approval.json"
QA_CANDIDATE_PATH = DATASET_ROOT / "candidates/ds5/p09_qa_r1.json"
CONTEXT_CANDIDATE_PATH = DATASET_ROOT / "candidates/ds5/p09_context_r1.json"
MANIFEST_PATH = DATASET_ROOT / "provenance/p09_gold_bundle_manifest.json"
REPORT_PATH = Path("docs/refactor/phase_reports/ED_PRE_P09_DS5_QA_candidate_review.md")

APPROVAL_SCOPE = "ds5_qa_and_context_only"
GENERATION_POLICY = (
    "p09-qa-context-r1|source=approved-p08-ds5+approved-ds2-ds3-p05|"
    "claims=verbatim-atomic-source-units|required-claims-only|"
    "short-answer=factoid-list-only|forbidden=grounded-comparison-conflation-only|"
    "context=constraint-not-order|max-items=8|max-tokens=4000|"
    "neighbors=approved-ds2-minimal|no-p09-output|no-external-knowledge"
)
STRATEGY_SHA256 = hashlib.sha256(GENERATION_POLICY.encode()).hexdigest()

LIST_MARKERS = ("哪些", "列出", "分别", "包括", "有哪", "哪几")
FACTOID_MARKERS = ("哪个", "何时", "多少", "是什么", "是谁", "哪一年", "哪一项")
PROCEDURE_PREFIX = re.compile(r"^\s*(?:[（(]?[一二三四五六七八九十0-9]+[）).、]|[a-zA-Z][).])")
SENTENCE_SPLIT = re.compile(r"(?<=[。！？；])\s*")


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _normalized(text: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", text).split())


def _stable_id(prefix: str, *parts: str) -> str:
    digest = hashlib.sha256("\x1f".join(parts).encode()).hexdigest()[:32]
    return f"{prefix}-{digest}"


def _artifact(repository_root: Path, path: Path) -> HashedArtifact:
    resolved = path.resolve()
    if not resolved.is_file() or not resolved.is_relative_to(repository_root.resolve()):
        raise ValueError("P09 artifacts must stay inside the repository")
    return HashedArtifact(
        path=resolved.relative_to(repository_root.resolve()).as_posix(),
        sha256=sha256_file(resolved),
        size_bytes=resolved.stat().st_size,
        media_type="application/json" if resolved.suffix == ".json" else "text/html",
    )


def _source_units(text: str) -> list[str]:
    if "\t" in text:
        rows: list[str] = []
        for raw_line in text.splitlines():
            line = raw_line.rstrip()
            if not line.strip():
                continue
            prefix = line.split("\t", 1)[0].strip()
            bullet_continuation = bool(re.match(r"^\d+[、.]", prefix))
            if ("\t" in line and not bullet_continuation) or not rows:
                rows.append(line)
            else:
                rows[-1] = f"{rows[-1]}\n{line}"
        return rows
    units: list[str] = []
    for piece in SENTENCE_SPLIT.split(text):
        value = piece.strip()
        if not value:
            continue
        if "\t" in value and "\n" not in value:
            units.append(value)
        elif len(value) <= 8000:
            units.append(value)
    if not units:
        units = [text.strip()[:8000]]
    return units


def _character_terms(text: str) -> set[str]:
    normalized = re.sub(r"[\s\W_]+", "", _normalized(text).lower())
    terms = {normalized[index : index + 2] for index in range(max(0, len(normalized) - 1))}
    terms.update(re.findall(r"[a-z0-9][a-z0-9+.-]{1,}", _normalized(text).lower()))
    return terms


def _unit_score(query: str, unit: str) -> tuple[float, int, str]:
    query_terms = _character_terms(query)
    unit_terms = _character_terms(unit)
    overlap = len(query_terms.intersection(unit_terms))
    score = overlap / max(1, len(query_terms))
    return score, -len(unit), unit


def _claim_units(query_type: str, query: str, evidence: EvidenceRecord) -> list[str]:
    units = _source_units(evidence.gold_text)
    if "\t" in evidence.gold_text:
        data_rows = units[1:] if len(units) > 1 else units
        matching_rows = [
            row for row in data_rows if any(term and term in query for term in row.split("\t")[:1])
        ]
        broad_table_request = any(
            marker in query
            for marker in (
                "具体数据或事实",
                "实验环境",
                "职业自动化淘汰概率",
                "参数规模演进",
                "政策环境",
                "哪些方法",
                "哪些算法",
                "不同传感器",
                "距离与图像像素尺寸",
            )
        )
        if not broad_table_request:
            if matching_rows:
                return matching_rows
            ranked = sorted(data_rows, key=lambda item: _unit_score(query, item), reverse=True)
            if ranked and _unit_score(query, ranked[0])[0] >= 0.08:
                return [ranked[0]]
        return data_rows[:30]
    if query_type == "procedure":
        physical_lines = [line.strip() for line in evidence.gold_text.splitlines() if line.strip()]
        logical_lines = [
            line
            for line in physical_lines
            if PROCEDURE_PREFIX.match(line)
            or line.startswith(("输入：", "输出：", "初始化：", "for ", "if "))
        ]
        if len(logical_lines) >= 2:
            return logical_lines[:20]
        procedural = [unit for unit in units if PROCEDURE_PREFIX.match(unit)]
        if procedural:
            return procedural[:8]
        return units[: min(6, len(units))]
    if evidence.semantic_unit_type in {"list", "table"}:
        ranked = sorted(units, key=lambda item: _unit_score(query, item), reverse=True)
        if len(units) <= 8:
            return units
        return ranked[:8]
    ranked = sorted(units, key=lambda item: _unit_score(query, item), reverse=True)
    return [ranked[0]]


def _answer_type(case: Any, evidence: dict[str, EvidenceRecord]) -> str:
    if not case.answerable:
        return "unanswerable"
    if case.query_type == "comparison":
        return "comparison"
    if case.query_type == "procedure":
        return "procedure"
    if case.query_type == "cross_section":
        return "explanatory"
    required_ids = {
        evidence_id
        for group in case.gold_evidence_groups
        for evidence_id in group.required_evidence_ids
    }
    if any(marker in case.query for marker in LIST_MARKERS) and any(
        evidence[evidence_id].semantic_unit_type in {"list", "table"}
        or "\t" in evidence[evidence_id].gold_text
        for evidence_id in required_ids
    ):
        return "list"
    if case.query_type == "exact_fact" or any(marker in case.query for marker in FACTOID_MARKERS):
        return "factoid"
    return "explanatory"


def _build_claims(
    case: Any,
    evidence: dict[str, EvidenceRecord],
    evidence_hashes: dict[str, str],
) -> list[GoldClaim]:
    required_ids = []
    for group in case.gold_evidence_groups:
        for evidence_id in group.required_evidence_ids:
            if evidence_id not in required_ids:
                required_ids.append(evidence_id)
    claims: list[GoldClaim] = []
    seen: set[str] = set()
    for evidence_id in required_ids:
        source = evidence[evidence_id]
        for unit in _claim_units(case.query_type, case.query, source):
            normalized = _normalized(unit)
            if normalized in seen:
                continue
            seen.add(normalized)
            claim_id = _stable_id("gold-cl", case.record_id, normalized, evidence_id)
            claims.append(
                GoldClaim(
                    claim_id=claim_id,
                    claim_text=unit,
                    importance="required",
                    required_evidence_ids=[evidence_id],
                    claim_text_sha256=_sha(unit),
                    normalized_claim_sha256=_sha(normalized),
                    evidence_supports=[
                        ClaimEvidenceSupport(
                            evidence_id=evidence_id,
                            evidence_record_sha256=evidence_hashes[evidence_id],
                            support_role="primary",
                            exact_support_excerpt=unit,
                            exact_support_excerpt_sha256=_sha(unit),
                        )
                    ],
                    annotation_rationale=(
                        "该 Claim 是 Approved DS2 Evidence 中与问题最直接对应的逐字完整源单元；"
                        "未使用外部事实或 P09 系统输出。"
                    ),
                )
            )
    if not claims:
        raise ValueError(f"answerable case produced no source-grounded Claims: {case.record_id}")
    return claims


def _list_items(query: str, claims: list[GoldClaim]) -> list[str]:
    if "算法类别" in query:
        categories: list[str] = []
        for claim in claims:
            cells = [cell.strip() for cell in claim.claim_text.split("\t")]
            if len(cells) > 1 and cells[1] and cells[1] not in categories:
                categories.append(cells[1])
            if "强化学习" in claim.claim_text and "强化学习" not in categories:
                categories.append("强化学习")
        if categories:
            return categories
    if "语音任务" in query:
        for claim in claims:
            cells = [cell.strip() for cell in claim.claim_text.split("\t") if cell.strip()]
            if len(cells) >= 2:
                return [item.strip() for item in cells[-1].split("、") if item.strip()]
    items: list[str] = []
    for claim in claims:
        text = claim.claim_text
        if "\t" in text:
            candidates = [_normalized(text)]
        else:
            numbered = re.findall(r"[（(]\d+[）)]\s*([^；。]+)", text)
            candidates = numbered or [text]
        for candidate in candidates:
            for part in re.split(r"[；;]", candidate):
                value = part.strip()
                if value and value not in items:
                    items.append(value)
    return items or [claims[0].claim_text]


def _build_variants(short_answer: str) -> tuple[list[str], list[P09AnswerVariant]]:
    normalized = _normalized(short_answer)
    if normalized == short_answer:
        return [], []
    return [normalized], [
        P09AnswerVariant(
            text=normalized,
            basis="mechanical_normalization",
            source_text_sha256=_sha(short_answer),
            rationale="仅折叠原文换行与连续空白，不改变词语、数值或事实。",
        )
    ]


def _factoid_short_answer(query: str, claims: list[GoldClaim]) -> str:
    text = claims[0].claim_text
    quoted = re.findall(r"“([^”]+)”", text)
    if "哪家" in query and quoted:
        return quoted[0]
    if "是什么概念" in query:
        match = re.match(r"([^，。\n]{2,30})(?:不仅|是)", text)
        if match:
            return match.group(1).strip()
    return text


def _build_forbidden(case: Any) -> tuple[list[str], list[P09ForbiddenClaim]]:
    if case.query_type != "comparison" or not case.answerable:
        return [], []
    quoted = re.findall(r"“([^”]+)”", case.query)
    if len(quoted) < 2:
        return [], []
    claim_text = f"{quoted[0]}与{quoted[1]}在教材中含义和关注点完全相同。"
    basis_ids = []
    for group in case.gold_evidence_groups:
        for evidence_id in group.required_evidence_ids:
            if evidence_id not in basis_ids:
                basis_ids.append(evidence_id)
    detail = P09ForbiddenClaim(
        forbidden_claim_id=_stable_id("gold-fc", case.record_id, claim_text),
        claim_text=claim_text,
        claim_text_sha256=_sha(claim_text),
        risk_type="conflation",
        basis_evidence_ids=basis_ids,
        rationale="两组 Required Evidence 分别描述不同对象或作用；将两者断言为完全相同会造成混淆。",
    )
    return [claim_text], [detail]


def _neighbor_reason(evidence: EvidenceRecord, relation: str, text: str) -> str:
    if relation == "parent_heading":
        if evidence.semantic_unit_type == "definition":
            return "restore_definition_scope"
        return "restore_semantic_dependency"
    if evidence.semantic_unit_type in {"list", "table"} or text.startswith(("表", "上述")):
        return "restore_list_scope"
    if evidence.gold_text.startswith(("它", "这", "其", "上述", "该")):
        return "resolve_reference"
    return "restore_semantic_dependency"


def _necessary_neighbors(
    relevant_ids: list[str], evidence: dict[str, EvidenceRecord]
) -> list[P09NecessaryContextNeighbor]:
    output: list[P09NecessaryContextNeighbor] = []
    seen: set[tuple[str, str]] = set()
    for evidence_id in relevant_ids:
        source = evidence[evidence_id]
        for neighbor in source.necessary_neighbors:
            key = (evidence_id, neighbor.text_sha256)
            if key in seen:
                continue
            seen.add(key)
            output.append(
                P09NecessaryContextNeighbor(
                    neighbor_id=_stable_id(
                        "gold-nb", evidence_id, neighbor.relation, neighbor.text_sha256
                    ),
                    evidence_id=evidence_id,
                    relation=neighbor.relation,
                    text=neighbor.text,
                    text_sha256=neighbor.text_sha256,
                    source_span=neighbor.source_span,
                    necessity_reason=_neighbor_reason(source, neighbor.relation, neighbor.text),
                )
            )
    return output


def _audit_sha(case: Any) -> str | None:
    if case.unanswerable_audit is None:
        return None
    return hashlib.sha256(
        canonical_json_bytes(case.unanswerable_audit.model_dump(mode="json"))
    ).hexdigest()


def _annotation_flags(
    case: Any, evidence: dict[str, EvidenceRecord]
) -> tuple[list[str], str | None]:
    required = [
        evidence[evidence_id]
        for group in case.gold_evidence_groups
        for evidence_id in group.required_evidence_ids
    ]
    truncated = any(item.gold_text.rstrip().endswith(("：", ":")) for item in required)
    weak_specific_fact = "具体数据或事实" in case.query and any(
        "一些问题" in item.gold_text for item in required
    )
    flags: list[str] = []
    reasons: list[str] = []
    if truncated:
        flags.append("source_evidence_appears_truncated")
        reasons.append(
            "至少一条 Approved DS2 Evidence 以冒号或分号结束，可能未覆盖后续公式、列表或说明。"
        )
    if weak_specific_fact:
        flags.append("retrieval_question_support_needs_owner_adjudication")
        reasons.append(
            "问题要求具体事实，但当前 Required Evidence 很短且不含数值，需确认是否足以回答。"
        )
    return flags, " ".join(reasons) or None


def _build_records(
    retrieval: DS5RetrievalQADataset,
    evidence: dict[str, EvidenceRecord],
    evidence_hashes: dict[str, str],
    upstream_hashes: dict[str, str],
) -> tuple[list[P09QAGoldCase], list[P09ContextGoldCase]]:
    qa_records: list[P09QAGoldCase] = []
    context_records: list[P09ContextGoldCase] = []
    for case in retrieval.cases:
        retrieval_hash = record_digest(case)
        qa_id = _stable_id("gold-qa", case.record_id, case.query_sha256 or "")
        answer_type = _answer_type(case, evidence)
        claims = _build_claims(case, evidence, evidence_hashes) if case.answerable else []
        short_answers: list[str] = []
        list_items: list[str] = []
        variants: list[str] = []
        variant_details: list[P09AnswerVariant] = []
        if answer_type == "factoid":
            short_answers = [_factoid_short_answer(case.query, claims)]
            variants, variant_details = _build_variants(short_answers[0])
        elif answer_type == "list":
            list_items = _list_items(case.query, claims)
            short_answers = ["；".join(list_items)]
            variants, variant_details = _build_variants(short_answers[0])
        forbidden, forbidden_details = _build_forbidden(case)
        annotation_flags, manual_review_reason = _annotation_flags(case, evidence)
        qa = P09QAGoldCase(
            record_id=qa_id,
            review_status=ReviewStatus.CANDIDATE,
            candidate_source="source_grounded_approved_evidence_r1",
            retrieval_case_id=case.record_id,
            retrieval_case_sha256=retrieval_hash,
            query=case.query,
            query_sha256=case.query_sha256,
            query_type=case.query_type,
            course_id=case.course_id,
            split=case.split,
            evaluation_stratum=case.evaluation_stratum,
            answerable=case.answerable,
            gold_answer_type=answer_type,
            gold_short_answers=short_answers,
            gold_list_items=list_items,
            allowed_answer_variants=variants,
            answer_variant_details=variant_details,
            gold_claims=claims,
            forbidden_claims=forbidden,
            forbidden_claim_details=forbidden_details,
            annotation_flags=annotation_flags,
            manual_review_reason=manual_review_reason,
            expected_behavior=("answer" if case.answerable else "abstained_insufficient_evidence"),
            unanswerable_audit_sha256=_audit_sha(case),
            upstream_approved_sha256=upstream_hashes,
            generation_strategy_sha256=STRATEGY_SHA256,
            qa_gold_status="candidate",
            approval_scope=APPROVAL_SCOPE,
        )
        relevant_ids = [item.evidence_id for item in case.evidence_judgments if item.relevance > 0]
        neighbors = _necessary_neighbors(relevant_ids, evidence) if case.answerable else []
        context = P09ContextGoldCase(
            record_id=_stable_id("gold-ctx", case.record_id, case.query_sha256 or ""),
            review_status=ReviewStatus.CANDIDATE,
            candidate_source="source_grounded_approved_evidence_r1",
            retrieval_case_id=case.record_id,
            retrieval_case_sha256=retrieval_hash,
            qa_case_id=qa.record_id,
            query_sha256=case.query_sha256,
            course_id=case.course_id,
            split=case.split,
            evaluation_stratum=case.evaluation_stratum,
            answerable=case.answerable,
            complete_evidence_groups=(case.gold_evidence_groups if case.answerable else []),
            relevant_evidence_ids=(relevant_ids if case.answerable else []),
            hard_negative_evidence_ids=case.hard_negative_evidence_ids,
            necessary_neighbors=neighbors,
            parent_expansion=(
                "only_if_necessary_neighbor"
                if any(item.relation == "parent_heading" for item in neighbors)
                else "forbidden"
            ),
            neighbor_expansion=(
                "only_listed_neighbors"
                if any(item.relation in {"previous", "next"} for item in neighbors)
                else "forbidden"
            ),
            p06_runtime_resolvable=case.p06_runtime_resolvable,
            upstream_approved_sha256=upstream_hashes,
            generation_strategy_sha256=STRATEGY_SHA256,
            context_gold_status="candidate",
            approval_scope=APPROVAL_SCOPE,
        )
        qa_records.append(qa)
        context_records.append(context)
    return qa_records, context_records


def bundle_identity_sha256(
    *,
    qa_sha256: str,
    context_sha256: str,
    p08_sha256: str,
    qa_record_sha256: dict[str, str],
    context_record_sha256: dict[str, str],
    p08_record_sha256: dict[str, str],
    upstream_sha256: dict[str, str],
    preserved_sha256: dict[str, str],
    first_review_groups: list[list[str]],
    second_review_ids: list[str],
) -> str:
    payload = {
        "schema_version": "courserag.p09-gold-bundle-identity.v1",
        "revision": 1,
        "approval_scope": APPROVAL_SCOPE,
        "qa_sha256": qa_sha256,
        "context_sha256": context_sha256,
        "p08_sha256": p08_sha256,
        "qa_record_sha256": qa_record_sha256,
        "context_record_sha256": context_record_sha256,
        "p08_record_sha256": p08_record_sha256,
        "upstream_sha256": upstream_sha256,
        "preserved_sha256": preserved_sha256,
        "first_review_groups": first_review_groups,
        "second_review_ids": second_review_ids,
    }
    return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()


def _second_review_ids(
    retrieval: DS5RetrievalQADataset,
    qa_records: list[P09QAGoldCase],
) -> list[str]:
    qa_by_retrieval = {item.retrieval_case_id: item for item in qa_records}
    selected: set[str] = set()
    remaining: list[str] = []
    for case in retrieval.cases:
        qa = qa_by_retrieval[case.record_id]
        high_risk = (
            not case.answerable
            or case.properties.get("multi_evidence", False)
            or case.query_type in {"comparison", "procedure", "cross_section"}
            or any(claim.importance == "optional" for claim in qa.gold_claims)
            or bool(qa.forbidden_claims)
            or any(
                case.properties.get(name, False)
                for name in ("contains_ocr", "contains_formula", "contains_table")
            )
        )
        if high_risk:
            selected.add(qa.record_id)
        else:
            remaining.append(qa.record_id)
    sample_size = math.ceil(len(remaining) * 0.20)
    selected.update(
        sorted(remaining, key=lambda item: _sha(f"p09-second-review|{item}"))[:sample_size]
    )
    return sorted(selected, key=lambda item: _sha(f"p09-blinded-order|{item}"))


def _kp_lookup(dataset: DS3KnowledgePointDataset) -> dict[str, str]:
    return {item.gold_kp_id: item.canonical_name for item in dataset.knowledge_points}


def _evidence_panel(evidence: EvidenceRecord, record_hash: str, *, role: str) -> str:
    span = evidence.source_span.model_dump(mode="json")
    bbox = [item.model_dump(mode="json") for item in evidence.bboxes]
    neighbors = (
        "".join(
            f"<li><b>{html.escape(item.relation)}</b>：{html.escape(item.text)}</li>"
            for item in evidence.necessary_neighbors
        )
        or "<li>无必要邻接</li>"
    )
    return (
        "<details class='evidence'><summary>"
        f"{html.escape(role)} · {html.escape(evidence.evidence_id)} · "
        f"{html.escape(evidence.semantic_unit_type)}</summary>"
        f"<pre>{html.escape(evidence.gold_text)}</pre>"
        f"<p><b>必要邻接</b></p><ul>{neighbors}</ul>"
        f"<p><b>SourceSpan</b> <code>{html.escape(json.dumps(span, ensure_ascii=False))}</code></p>"
        f"<p><b>BBox</b> <code>{html.escape(json.dumps(bbox, ensure_ascii=False))}</code></p>"
        f"<p><b>Evidence record SHA-256</b> <code>{record_hash}</code></p></details>"
    )


def _case_card(
    retrieval_case: Any,
    qa: P09QAGoldCase,
    context: P09ContextGoldCase,
    evidence: dict[str, EvidenceRecord],
    evidence_hashes: dict[str, str],
    kp_names: dict[str, str],
    group_number: int,
) -> str:
    kp = (
        "".join(
            f"<li>{html.escape(item)} — {html.escape(kp_names.get(item, '未找到名称'))}</li>"
            for item in retrieval_case.expected_knowledge_points
        )
        or "<li>无预期知识点（不可回答或无需 KP）</li>"
    )
    claims = (
        "".join(
            "<li>"
            f"<b>{html.escape(claim.importance)}</b> · <code>{claim.claim_id}</code>"
            f"<blockquote>{html.escape(claim.claim_text)}</blockquote>"
            f"支持 Evidence：{html.escape(', '.join(claim.required_evidence_ids))}"
            f"<br>理由：{html.escape(claim.annotation_rationale or '')}</li>"
            for claim in qa.gold_claims
        )
        or "<li>无 Claims；预期拒答。</li>"
    )
    forbidden = (
        "".join(
            f"<li>{html.escape(item.claim_text)}<br>{html.escape(item.rationale)}</li>"
            for item in qa.forbidden_claim_details
        )
        or "<li>没有具备充分原文依据的 Forbidden Claim；未为凑数编造。</li>"
    )
    neighbor_rows = (
        "".join(
            "<li>"
            f"<code>{item.neighbor_id}</code> · {html.escape(item.relation)} · "
            f"{html.escape(item.necessity_reason)}<blockquote>{html.escape(item.text)}</blockquote></li>"
            for item in context.necessary_neighbors
        )
        or "<li>无必要邻接。</li>"
    )
    evidence_ids = list(
        dict.fromkeys(context.relevant_evidence_ids + context.hard_negative_evidence_ids)
    )
    panels = "".join(
        _evidence_panel(
            evidence[item],
            evidence_hashes[item],
            role=("相关" if item in context.relevant_evidence_ids else "0分硬负例"),
        )
        for item in evidence_ids
    )
    short = html.escape(json.dumps(qa.gold_short_answers, ensure_ascii=False))
    variants = html.escape(json.dumps(qa.allowed_answer_variants, ensure_ascii=False))
    groups = html.escape(
        json.dumps(
            [item.model_dump(mode="json") for item in context.complete_evidence_groups],
            ensure_ascii=False,
        )
    )
    flags = ""
    if qa.annotation_flags:
        flags = (
            "<div class='warning'><b>需要重点人工裁定：</b>"
            f"{html.escape(', '.join(qa.annotation_flags))}<br>"
            f"{html.escape(qa.manual_review_reason or '')}</div>"
        )
    return f"""
<article class="card" data-id="{qa.record_id}" data-group="{group_number}">
  <h2>{html.escape(qa.query)}</h2>
  <p><code>{qa.record_id}</code></p>
  <p class="badges">{qa.query_type} · {qa.gold_answer_type} · {qa.course_id} · {qa.split} · {qa.evaluation_stratum}</p>
  {flags}
  <h3>知识点（ID 与名称）</h3><ul>{kp}</ul>
  <h3>答案 Gold</h3>
  <p><b>短答案</b> <code>{short}</code></p>
  <p><b>允许变体</b> <code>{variants}</code></p>
  <h3>原子 Claims</h3><ol>{claims}</ol>
  <h3>Forbidden Claims</h3><ul>{forbidden}</ul>
  <h3>Context 约束</h3>
  <p><b>完整 Evidence Groups</b> <code>{groups}</code></p>
  <p><b>相关 Evidence</b> {html.escape(", ".join(context.relevant_evidence_ids) or "空")}</p>
  <p><b>硬负例</b> {html.escape(", ".join(context.hard_negative_evidence_ids))}</p>
  <p><b>预算</b> max_items=8 / max_tokens=4000；边界保留=true；顺序不固定。</p>
  <h3>最小必要邻接</h3><ul>{neighbor_rows}</ul>
  <h3>Evidence 原文、页码与 BBox</h3>{panels}
  <fieldset><legend>审核决定</legend>
    <label><input type="radio" name="d-{qa.record_id}" value="pass"> 通过</label>
    <label><input type="radio" name="d-{qa.record_id}" value="return"> 退回</label>
    <textarea id="n-{qa.record_id}" placeholder="退回必须填写原因；通过可备注"></textarea>
  </fieldset>
</article>
"""


def _render_review_html(
    *,
    title: str,
    bundle_sha256: str,
    review_pass: str,
    expected_ids: list[str],
    cards: list[str],
) -> str:
    expected_json = json.dumps(expected_ids, ensure_ascii=False)
    return f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><title>{html.escape(title)}</title>
<style>
body{{font-family:system-ui,sans-serif;margin:0;background:#f5f6f8;color:#17202a}}
header{{position:sticky;top:0;background:#fff;padding:16px 24px;border-bottom:1px solid #ccc;z-index:2}}
main{{max-width:1280px;margin:auto;padding:20px}} .card{{background:white;border:1px solid #bbb;border-radius:8px;padding:18px;margin:18px 0}}
pre,blockquote,code{{white-space:pre-wrap;word-break:break-word}} pre,blockquote{{background:#f6f8fa;padding:12px;border-radius:5px}}
.badges{{font-weight:600;color:#38598b}} .warning{{background:#fff3cd;border:1px solid #e0a800;padding:12px}} textarea{{display:block;width:100%;min-height:62px;margin-top:10px}}
details{{margin:10px 0;border:1px solid #ddd;padding:8px}} button,select,input{{font-size:1rem;margin-right:8px}}
</style></head><body><header>
<h1>{html.escape(title)}</h1><p>Bundle <code>{bundle_sha256}</code> · 共 {len(expected_ids)} 条</p>
<label>分组筛选 <select id="group"><option value="all">全部</option>{"".join(f'<option value="{i}">第{i}组</option>' for i in range(1, 6))}</select></label>
<button id="export">导出审核 JSON</button><span id="progress"></span>
</header><main>{"".join(cards)}</main>
<script>
const expected={expected_json}; const bundle="{bundle_sha256}"; const passName="{review_pass}";
const key=`p09-${{bundle}}-${{passName}}`; const saved=JSON.parse(localStorage.getItem(key)||"{{}}");
function refresh(){{let done=0;for(const id of expected){{const d=document.querySelector(`input[name="d-${{id}}"]:checked`);if(d)done++;}}document.getElementById('progress').textContent=` 已审核 ${{done}}/${{expected.length}}`;}}
for(const id of expected){{if(saved[id]){{const radio=document.querySelector(`input[name="d-${{id}}"][value="${{saved[id].decision}}"]`);if(radio)radio.checked=true;const note=document.getElementById(`n-${{id}}`);if(note)note.value=saved[id].notes||"";}}}}
document.addEventListener('change',e=>{{if(e.target.matches('input[type=radio]')){{const id=e.target.name.slice(2);saved[id]={{decision:e.target.value,notes:document.getElementById(`n-${{id}}`).value}};localStorage.setItem(key,JSON.stringify(saved));refresh();}}}});
document.addEventListener('input',e=>{{if(e.target.matches('textarea')){{const id=e.target.id.slice(2);if(saved[id]){{saved[id].notes=e.target.value;localStorage.setItem(key,JSON.stringify(saved));}}}}}});
document.getElementById('group').onchange=e=>{{document.querySelectorAll('.card').forEach(x=>x.style.display=(e.target.value==='all'||x.dataset.group===e.target.value)?'block':'none');}};
document.getElementById('export').onclick=()=>{{const decisions=[];for(const id of expected){{const d=document.querySelector(`input[name="d-${{id}}"]:checked`);if(!d){{alert(`尚未审核：${{id}}`);return;}}const notes=document.getElementById(`n-${{id}}`).value.trim();if(d.value==='return'&&!notes){{alert(`退回必须填写原因：${{id}}`);return;}}decisions.push({{record_id:id,decision:d.value,notes}});}}const payload={{schema_version:'courserag.p09-review-decisions.v1',dataset_id:'courserag-p09-review',dataset_version:'r1',bundle_sha256:bundle,review_pass:passName,expected_record_ids:expected,decisions,reviewer_id:null,reviewed_at:null}};const blob=new Blob([JSON.stringify(payload,null,2)+'\n'],{{type:'application/json'}});const a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download=`p09_${{passName}}_review_${{bundle.slice(0,12)}}.json`;a.click();URL.revokeObjectURL(a.href);}};
refresh();
</script></body></html>"""


def _render_report(
    *,
    bundle_sha256: str,
    qa_sha256: str,
    context_sha256: str,
    qa_records: list[P09QAGoldCase],
    context_records: list[P09ContextGoldCase],
    second_count: int,
) -> str:
    answer_types = Counter(item.gold_answer_type for item in qa_records)
    claims = [claim for item in qa_records for claim in item.gold_claims]
    neighbors = [neighbor for item in context_records for neighbor in item.necessary_neighbors]
    forbidden = [claim for item in qa_records for claim in item.forbidden_claim_details]
    flagged = [item for item in qa_records if item.annotation_flags]
    flagged_lines = (
        "\n".join(f"- `{item.record_id}`：{item.manual_review_reason}" for item in flagged)
        or "- 无。"
    )
    return f"""# ED-PRE09 DS5 QA/Context Candidate 审核报告

## 审批边界

- Bundle SHA-256：`{bundle_sha256}`
- QA Candidate SHA-256：`{qa_sha256}`
- Context Candidate SHA-256：`{context_sha256}`
- 本批仅为 Candidate；没有写入 `approved/ds5/p09_*.json`。
- P08 Retrieval Gold、Query、Split、相关性和正式 B3–B5 结果均保持不变。
- Test 保持未锁定，P09 只能加载 Dev。

## 数量

- Query：100（可回答 90 / 不可回答 10；Dev 60 / Test 40）。
- Answer Type：{dict(sorted(answer_types.items()))}。
- Gold Claims：{len(claims)}（Required {sum(item.importance == "required" for item in claims)} / Optional {sum(item.importance == "optional" for item in claims)}）。
- Forbidden Claims：{len(forbidden)}；只生成有 Required Evidence 对照依据的比较混淆项。
- 最小必要邻接：{len(neighbors)}。
- 首轮审核：100；风险分层二轮审核：{second_count}。

## 必须人工裁定的记录

{flagged_lines}

## 审核重点

1. 先判断问题是否可回答及 Answer Type。
2. 检查短答案、列表项和机械变体是否逐字受原文支持。
3. 检查每个 Claim 是否原子、完整且其 Evidence 能直接支持。
4. 检查 Forbidden Claim 是否确属容易混淆且与 Evidence 对照矛盾。
5. 检查 Context 的完整 Evidence Group 和必要邻接是否是最近、最小依赖。
6. 不可回答问题必须没有答案 Claims，并维持 `abstained_insufficient_evidence`。

审核结束后不得仅回复泛化“批准”。审批口令为：

`批准正式 P09 Gold Bundle {bundle_sha256}`
"""


def generate_p09_candidates(*, repository_root: Path) -> dict[str, Any]:
    repository_root = repository_root.resolve()
    dataset_root = repository_root / DATASET_ROOT
    p08_path = repository_root / P08_PATH
    ds2_path = repository_root / DS2_PATH
    ds3_path = repository_root / DS3_PATH
    p05_path = repository_root / P05_PATH
    p08_approval_path = repository_root / P08_APPROVAL_PATH
    test_lock = TestLock.model_validate_json(
        (dataset_root / "test.lock.json").read_text(encoding="utf-8")
    )
    if test_lock.locked:
        raise ValueError("Pre-P09 Candidate generation requires unlocked Test")
    retrieval = DS5RetrievalQADataset.model_validate_json(p08_path.read_text(encoding="utf-8"))
    ds2 = DS2EvidenceDataset.model_validate_json(ds2_path.read_text(encoding="utf-8"))
    ds3 = DS3KnowledgePointDataset.model_validate_json(ds3_path.read_text(encoding="utf-8"))
    if len(retrieval.cases) != 100 or sum(item.answerable for item in retrieval.cases) != 90:
        raise ValueError("P09 requires exact Approved P08 100/90/10 scope")
    if any(
        item.review_status != ReviewStatus.APPROVED
        or item.retrieval_gold_status != "approved"
        or item.qa_gold_status != "pending_p09"
        for item in retrieval.cases
    ):
        raise ValueError("P09 requires Approved retrieval-only P08 cases with QA pending")
    evidence = {item.evidence_id: item for item in ds2.evidence}
    evidence_hashes = {item.evidence_id: record_digest(item) for item in ds2.evidence}
    referenced = {item.evidence_id for case in retrieval.cases for item in case.evidence_judgments}
    missing = referenced.difference(evidence)
    if missing:
        raise ValueError(f"P08 references missing Approved DS2 Evidence: {sorted(missing)}")
    upstream_hashes = {
        "approved_ds5_p08": sha256_file(p08_path),
        "p08_gold_bundle_approval": sha256_file(p08_approval_path),
        "approved_ds2_p06": sha256_file(ds2_path),
        "approved_ds3_p07": sha256_file(ds3_path),
        "approved_ds1_p05": sha256_file(p05_path),
    }
    qa_records, context_records = _build_records(
        retrieval, evidence, evidence_hashes, upstream_hashes
    )
    qa_dataset = P09QAGoldDataset(
        dataset_id="courserag-ds5-p09-qa",
        dataset_version="p09-r1",
        cases=qa_records,
    )
    context_dataset = P09ContextGoldDataset(
        dataset_id="courserag-ds5-p09-context",
        dataset_version="p09-r1",
        cases=context_records,
    )
    qa_path = repository_root / QA_CANDIDATE_PATH
    context_path = repository_root / CONTEXT_CANDIDATE_PATH
    atomic_write_json(qa_path, qa_dataset.model_dump(mode="json"))
    atomic_write_json(context_path, context_dataset.model_dump(mode="json"))
    qa_hashes = {item.record_id: record_digest(item) for item in qa_records}
    context_hashes = {item.record_id: record_digest(item) for item in context_records}
    p08_hashes = {item.record_id: record_digest(item) for item in retrieval.cases}
    first_groups = [
        [item.record_id for item in qa_records[index : index + 20]] for index in range(0, 100, 20)
    ]
    second_ids = _second_review_ids(retrieval, qa_records)
    preserved = {
        "p08_run_1_report": sha256_file(
            repository_root / "storage_eval/p08_hybrid_retrieval/run-1/report.json"
        ),
        "p08_run_2_report": sha256_file(
            repository_root / "storage_eval/p08_hybrid_retrieval/run-2/report.json"
        ),
        "p08_default_profile": sha256_file(
            repository_root / "resources/retrieval_profiles/default_v1.json"
        ),
    }
    bundle_sha256 = bundle_identity_sha256(
        qa_sha256=sha256_file(qa_path),
        context_sha256=sha256_file(context_path),
        p08_sha256=sha256_file(p08_path),
        qa_record_sha256=qa_hashes,
        context_record_sha256=context_hashes,
        p08_record_sha256=p08_hashes,
        upstream_sha256=upstream_hashes,
        preserved_sha256=preserved,
        first_review_groups=first_groups,
        second_review_ids=second_ids,
    )
    review_dir = repository_root / f"storage_eval/ds5_p09_review/{bundle_sha256}"
    qa_by_id = {item.record_id: item for item in qa_records}
    context_by_qa = {item.qa_case_id: item for item in context_records}
    retrieval_by_id = {item.record_id: item for item in retrieval.cases}
    kp_names = _kp_lookup(ds3)
    group_by_id = {
        record_id: group_number
        for group_number, group in enumerate(first_groups, start=1)
        for record_id in group
    }

    def card(record_id: str) -> str:
        qa = qa_by_id[record_id]
        return _case_card(
            retrieval_by_id[qa.retrieval_case_id],
            qa,
            context_by_qa[record_id],
            evidence,
            evidence_hashes,
            kp_names,
            group_by_id[record_id],
        )

    first_html = _render_review_html(
        title="P09 DS5 QA/Context Gold 首轮审核",
        bundle_sha256=bundle_sha256,
        review_pass="first",
        expected_ids=[item.record_id for item in qa_records],
        cards=[card(item.record_id) for item in qa_records],
    )
    second_html = _render_review_html(
        title="P09 DS5 QA/Context Gold 二轮盲化复核",
        bundle_sha256=bundle_sha256,
        review_pass="second",
        expected_ids=second_ids,
        cards=[card(record_id) for record_id in second_ids],
    )
    atomic_write_text(review_dir / "index.html", first_html)
    atomic_write_text(review_dir / "second_review.html", second_html)
    manifest = P09GoldBundleManifest(
        dataset_id="courserag-p09-qa-context-gold-bundle",
        dataset_version="p09-r1",
        qa_candidate=_artifact(repository_root, qa_path),
        context_candidate=_artifact(repository_root, context_path),
        approved_p08_retrieval=_artifact(repository_root, p08_path),
        qa_candidate_record_sha256=qa_hashes,
        context_candidate_record_sha256=context_hashes,
        p08_retrieval_record_sha256=p08_hashes,
        upstream_approved_sha256=upstream_hashes,
        preserved_p08_sha256=preserved,
        first_review_groups=first_groups,
        second_review_ids=second_ids,
        review_pack_relative_path=review_dir.relative_to(repository_root).as_posix(),
        review_pack_index_sha256=sha256_file(review_dir / "index.html"),
        second_review_index_sha256=sha256_file(review_dir / "second_review.html"),
        bundle_sha256=bundle_sha256,
    )
    manifest_path = repository_root / MANIFEST_PATH
    atomic_write_json(manifest_path, manifest.model_dump(mode="json"))
    atomic_write_text(
        repository_root / REPORT_PATH,
        _render_report(
            bundle_sha256=bundle_sha256,
            qa_sha256=sha256_file(qa_path),
            context_sha256=sha256_file(context_path),
            qa_records=qa_records,
            context_records=context_records,
            second_count=len(second_ids),
        ),
    )
    governance_path = dataset_root / "manifest.json"
    governance = json.loads(governance_path.read_text(encoding="utf-8"))
    if governance.get("gold_components", {}).get("ds5_qa") != "pending_p09":
        raise ValueError("P09 Candidate generation refuses to overwrite non-pending QA governance")
    governance.setdefault("phase_input_status", {})["p08"] = "completed_gate_passed"
    governance["phase_input_status"]["p09"] = "candidate_review_pending"
    atomic_write_json(governance_path, governance)
    claims = [claim for item in qa_records for claim in item.gold_claims]
    return {
        "bundle_sha256": bundle_sha256,
        "qa_candidate_sha256": sha256_file(qa_path),
        "context_candidate_sha256": sha256_file(context_path),
        "qa_record_count": len(qa_records),
        "context_record_count": len(context_records),
        "claim_count": len(claims),
        "required_claim_count": sum(item.importance == "required" for item in claims),
        "optional_claim_count": sum(item.importance == "optional" for item in claims),
        "forbidden_claim_count": sum(len(item.forbidden_claims) for item in qa_records),
        "necessary_neighbor_count": sum(len(item.necessary_neighbors) for item in context_records),
        "second_review_count": len(second_ids),
        "review_pack": review_dir.relative_to(repository_root).as_posix(),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate formal P09 QA/Context Gold Candidates.")
    parser.add_argument("--repository-root", type=Path, default=Path("."))
    args = parser.parse_args()
    print(
        json.dumps(
            generate_p09_candidates(repository_root=args.repository_root),
            ensure_ascii=False,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
