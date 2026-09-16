"""Build the approved-scope EP-00 candidate data deterministically.

Only non-P18, human-approved CourseRAG Dev Evidence and Knowledge Points are
used as source material.  The generated Adequacy labels remain candidates and
the command never creates ``approved/`` data.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from evaluation.system_optimization.schemas import (
    AdequacyCandidate,
    AdequacyStatus,
    ArtifactRubricProfile,
    ArtifactType,
    CapacityTier,
    DevCaseDataset,
    EvidenceGroup,
    EvidenceItem,
    EvidencePackageCandidate,
    FailureExpectation,
    FailureReplayCase,
    FailureReplayDataset,
    MaterialType,
    NextAction,
    RubricDimension,
    SystemOptimizationDevCase,
    TaskDemandCandidate,
    TopicRelation,
)

_EVIDENCE_PATH = Path("datasets/courserag_eval/v1/approved/ds2/p06_evidence.json")
_KP_PATH = Path("datasets/courserag_eval/v1/approved/ds3/p07_knowledge_points.json")
_CONTEXT_PATH = Path("datasets/courserag_eval/v1/approved/ds5/p09_context.json")

_MATERIAL_PATTERNS: tuple[tuple[MaterialType, ...], ...] = (
    (MaterialType.DEFINITION,),
    (MaterialType.COMPARISON,),
    (MaterialType.PROCESS,),
    (MaterialType.FORMULA, MaterialType.NUMERIC),
    (MaterialType.TABLE,),
    (MaterialType.CASE,),
    (MaterialType.CASE,),
    (MaterialType.COMPARISON, MaterialType.PROCESS),
    (MaterialType.FORMULA, MaterialType.TABLE, MaterialType.NUMERIC),
)

_OUTPUT_COUNTS = {
    ArtifactType.LESSON: (1, 1, 2, 1, 1, 2, 1, 1, 2),
    ArtifactType.EXAM: (2, 4, 6, 2, 4, 6, 2, 4, 6),
    ArtifactType.PPT: (3, 5, 7, 3, 5, 7, 3, 5, 7),
}

_OUTPUT_UNITS = {
    ArtifactType.LESSON: "sessions",
    ArtifactType.EXAM: "questions",
    ArtifactType.PPT: "slides",
}

_RUBRICS: dict[ArtifactType, tuple[tuple[str, str, str], ...]] = {
    ArtifactType.LESSON: (
        ("L-H1", "目标一致性", "目标是否与章节、知识点和学生层次一致"),
        ("L-H2", "课时规划", "Session 划分、顺序和负担是否合理"),
        ("L-H3", "时间可执行性", "各活动在给定时间内是否现实"),
        ("L-H4", "知识覆盖", "核心知识点是否充分且不过度扩展"),
        ("L-H5", "教学活动", "活动是否具体、可操作并服务目标"),
        ("L-H6", "重点难点", "是否真正识别并处理学习难点"),
        ("L-H7", "证据忠实", "事实性内容是否有来源且不超出资料"),
        ("L-H8", "教师可用性", "教师是否能低成本修改后使用"),
    ),
    ArtifactType.EXAM: (
        ("E-H1", "Blueprint 合理性", "题型、分值、覆盖和难度规划"),
        ("E-H2", "题干质量", "题干是否清晰、无歧义且条件完整"),
        ("E-H3", "正确性", "答案是否正确且唯一或集合合理"),
        ("E-H4", "干扰项质量", "干扰项是否有辨识度且不明显荒谬"),
        ("E-H5", "难度匹配", "实际认知要求是否符合标签"),
        ("E-H6", "覆盖与平衡", "知识点、内容角色和题型是否均衡"),
        ("E-H7", "重复与泄漏", "是否重复、互相提示或答案泄漏"),
        ("E-H8", "解析质量", "解析是否解释关键依据而非复述答案"),
        ("E-H9", "Grounding", "题目、答案和解析是否由资料支持"),
        ("E-H10", "可用性", "是否可直接进入教师复核流程"),
    ),
    ArtifactType.PPT: (
        ("P-H1", "Slide Architecture", "页序和页型是否服务教学逻辑"),
        ("P-H2", "单页聚焦", "每页是否有明确中心"),
        ("P-H3", "信息密度", "是否过载、过空或堆砌 Bullet"),
        ("P-H4", "内容连贯", "页面间过渡和层次是否清晰"),
        ("P-H5", "教学表达", "是否适合课堂讲解而非文档搬运"),
        ("P-H6", "活动与示例", "是否支持课堂互动和理解"),
        ("P-H7", "Notes", "是否提供可用讲解提示"),
        ("P-H8", "引用与来源", "是否准确、可解析并放置合理"),
        ("P-H9", "可编辑性", "教师是否可方便调整"),
        ("P-H10", "视觉可用性", "模板、布局和文本是否基本合格"),
    ),
}

_EDIT_BURDEN = {
    "0": "无需修改",
    "1": "轻微措辞或格式修改",
    "2": "多处局部修改",
    "3": "结构性重写",
    "4": "无法采用",
}


def build_candidate_data(repository_root: Path) -> tuple[DevCaseDataset, FailureReplayDataset]:
    source_rows = _load_source_rows(repository_root)
    records: list[SystemOptimizationDevCase] = []
    for artifact_index, artifact in enumerate(ArtifactType):
        for case_index in range(9):
            records.append(_build_case(source_rows, artifact, artifact_index, case_index))
    return DevCaseDataset(records=records), _build_failures()


def _load_source_rows(repository_root: Path) -> list[dict[str, Any]]:
    evidence_payload = _load_json(repository_root / _EVIDENCE_PATH)
    kp_payload = _load_json(repository_root / _KP_PATH)
    context_payload = _load_json(repository_root / _CONTEXT_PATH)
    dev_contexts_by_evidence: dict[str, set[str]] = {}
    for context in context_payload["cases"]:
        if context.get("split") != "dev" or context.get("review_status") != "approved":
            continue
        context_evidence_ids = set(context.get("relevant_evidence_ids", []))
        for group in context.get("complete_evidence_groups", []):
            context_evidence_ids.update(group.get("required_evidence_ids", []))
        for evidence_id in context_evidence_ids:
            dev_contexts_by_evidence.setdefault(evidence_id, set()).add(context["record_id"])
    evidence_by_id = {
        item["evidence_id"]: item
        for item in evidence_payload["evidence"]
        if item.get("review_status") == "approved"
        and not _is_p18_identifier(item["evidence_id"])
        and item["evidence_id"] in dev_contexts_by_evidence
    }
    rows: list[dict[str, Any]] = []
    for kp in kp_payload["knowledge_points"]:
        kp_evidence_ids = [item for item in kp["evidence_ids"] if item in evidence_by_id]
        if (
            kp.get("review_status") != "approved"
            or _is_p18_identifier(kp["record_id"])
            or not kp_evidence_ids
        ):
            continue
        evidence = evidence_by_id[kp_evidence_ids[0]]
        rows.append(
            {
                "kp": kp,
                "evidence": evidence,
                "material_types": _material_types(evidence["semantic_unit_type"]),
                "dev_context_ids": sorted(dev_contexts_by_evidence[evidence["evidence_id"]]),
            }
        )
    if len(rows) < 27:
        raise ValueError("non-P18 approved CourseRAG source assets are insufficient")
    return rows


def _build_case(
    rows: list[dict[str, Any]],
    artifact: ArtifactType,
    artifact_index: int,
    case_index: int,
) -> SystemOptimizationDevCase:
    tier = tuple(CapacityTier)[case_index // 3]
    relation = tuple(TopicRelation)[case_index % 3]
    required_materials = _MATERIAL_PATTERNS[case_index]
    kp_count = {TopicRelation.SINGLE: 1, TopicRelation.ADJACENT: 2, TopicRelation.NON_ADJACENT: 3}[
        relation
    ]
    selection_offset = artifact_index * 9 + case_index
    course_id = _choose_course(
        rows,
        required_materials,
        count=kp_count,
        tier=tier,
        offset=selection_offset,
    )
    chosen = _choose_kps(
        rows,
        course_id=course_id,
        required_materials=required_materials,
        count=kp_count,
        tier=tier,
        offset=selection_offset,
    )
    visible = _visible_sources(chosen)
    items = [
        _evidence_item(item["evidence"], dev_context_ids=item["dev_context_ids"])
        for item in visible
    ]
    visible_ids = {item.evidence_id for item in items}
    groups: list[EvidenceGroup] = []
    missing_kps: list[str] = []
    for group_index, source in enumerate(chosen, start=1):
        evidence_id = source["evidence"]["evidence_id"]
        present = evidence_id in visible_ids
        if not present:
            missing_kps.append(source["kp"]["gold_kp_id"])
        groups.append(
            EvidenceGroup(
                group_id=f"sysopt-v1-{artifact.value}-{case_index + 1:02d}-g{group_index}",
                knowledge_point_id=source["kp"]["gold_kp_id"],
                evidence_ids=[evidence_id] if present else [],
                complete=present,
                missing_reasons=[]
                if present
                else ["required knowledge point has no visible Evidence"],
            )
        )
    visible_materials = {material for item in items for material in item.material_types}
    missing_materials = [
        material for material in required_materials if material not in visible_materials
    ]
    package = EvidencePackageCandidate(
        capacity_tier=tier,
        items=items,
        groups=groups,
        estimated_tokens=max(1, sum(len(item.excerpt) for item in items) // 4),
        distinct_semantic_units=len({item.semantic_unit_type for item in items}),
        missing_knowledge_point_ids=missing_kps,
        missing_material_types=missing_materials,
    )
    adequacy = _candidate_adequacy(
        missing_kps=missing_kps,
        missing_materials=missing_materials,
    )
    kp_names = "、".join(source["kp"]["canonical_name"] for source in chosen)
    output_count = _OUTPUT_COUNTS[artifact][case_index]
    record_id = f"sysopt-v1-{artifact.value}-{case_index + 1:02d}"
    return SystemOptimizationDevCase(
        record_id=record_id,
        candidate_source="codex_ep00_r2_scope_reduced_non_p18_approved_dev",
        artifact_type=artifact,
        course_id=course_id,
        title=f"{artifact.value.upper()}：{kp_names}（{tier.value} Evidence）",
        task_demand=TaskDemandCandidate(
            artifact_type=artifact,
            output_count=output_count,
            output_unit=_OUTPUT_UNITS[artifact],
            knowledge_point_ids=[source["kp"]["gold_kp_id"] for source in chosen],
            required_material_types=list(required_materials),
            topic_relation=relation,
            audience="高校本科生",
            difficulty_profile={"easy": 0.3, "medium": 0.5, "hard": 0.2},
        ),
        evidence_package=package,
        candidate_adequacy=adequacy,
        rubric_profile=_rubric(artifact),
        coverage_tags=[
            f"capacity:{tier.value}",
            f"topic_relation:{relation.value}",
            *(f"material:{material.value}" for material in required_materials),
            f"quantity:{output_count}_{_OUTPUT_UNITS[artifact]}",
            "scope:reduced_to_available_approved_evidence",
        ],
    )


def _choose_course(
    rows: list[dict[str, Any]],
    required_materials: tuple[MaterialType, ...],
    *,
    count: int,
    tier: CapacityTier,
    offset: int,
) -> str:
    courses = sorted({item["kp"]["course_id"] for item in rows})
    eligible = [
        course
        for course in courses
        if all(
            any(
                row["kp"]["course_id"] == course and material in row["material_types"]
                for row in rows
            )
            for material in required_materials
        )
    ]
    if not eligible:
        raise ValueError(f"no course covers required materials: {required_materials}")
    capacities = {
        course: sum(
            _evidence_tokens(item)
            for item in _choose_kps(
                rows,
                course_id=course,
                required_materials=required_materials,
                count=count,
                tier=tier,
                offset=offset,
            )
        )
        for course in eligible
    }
    ranked = sorted(eligible, key=capacities.__getitem__)
    if tier is CapacityTier.THIN:
        return ranked[0]
    if tier is CapacityTier.RICH:
        return ranked[-1]
    target = 16 * count
    return min(ranked, key=lambda course: abs(capacities[course] - target))


def _choose_kps(
    rows: list[dict[str, Any]],
    *,
    course_id: str,
    required_materials: tuple[MaterialType, ...],
    count: int,
    tier: CapacityTier,
    offset: int,
) -> list[dict[str, Any]]:
    course_rows = [item for item in rows if item["kp"]["course_id"] == course_id]
    ordered = course_rows[offset % len(course_rows) :] + course_rows[: offset % len(course_rows)]
    selected: list[dict[str, Any]] = []
    uncovered = set(required_materials)
    while uncovered and len(selected) < count:
        match = max(
            (item for item in ordered if item not in selected),
            key=lambda item: (
                len(uncovered & set(item["material_types"])),
                _tier_preference(item, tier),
            ),
        )
        covered = uncovered & set(match["material_types"])
        if not covered:
            break
        selected.append(match)
        uncovered -= covered
    remaining = sorted(
        (item for item in ordered if item not in selected),
        key=lambda item: _tier_preference(item, tier),
        reverse=True,
    )
    selected.extend(remaining)
    return selected[:count]


def _visible_sources(
    chosen: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    return list(chosen)


def _tier_preference(item: dict[str, Any], tier: CapacityTier) -> int:
    tokens = _evidence_tokens(item)
    if tier is CapacityTier.THIN:
        return -tokens
    if tier is CapacityTier.MEDIUM:
        return -abs(tokens - 16)
    return tokens


def _evidence_tokens(item: dict[str, Any]) -> int:
    return max(1, len(item["evidence"]["gold_text"]) // 4)


def _evidence_item(evidence: dict[str, Any], *, dev_context_ids: list[str]) -> EvidenceItem:
    return EvidenceItem(
        evidence_id=evidence["evidence_id"],
        source_record_id=evidence["record_id"],
        course_id=evidence["course_id"],
        content_sha256=evidence["content_sha256"],
        semantic_unit_type=evidence["semantic_unit_type"],
        source_type=evidence["source_type"],
        excerpt=evidence["gold_text"],
        material_types=list(_material_types(evidence["semantic_unit_type"])),
        dev_context_ids=dev_context_ids,
    )


def _material_types(semantic_unit_type: str) -> tuple[MaterialType, ...]:
    mapping = {
        "definition": (MaterialType.DEFINITION,),
        "principle": (MaterialType.DEFINITION,),
        "list": (MaterialType.COMPARISON,),
        "procedure": (MaterialType.PROCESS,),
        "formula": (MaterialType.FORMULA, MaterialType.NUMERIC),
        "table": (MaterialType.TABLE, MaterialType.COMPARISON),
        "example": (MaterialType.CASE,),
        "application": (MaterialType.CASE,),
        "other": (MaterialType.CASE,),
    }
    return mapping.get(semantic_unit_type, (MaterialType.CASE,))


def _candidate_adequacy(
    *,
    missing_kps: list[str],
    missing_materials: list[MaterialType],
) -> AdequacyCandidate:
    unmet = [*(f"missing_kp:{item}" for item in missing_kps)]
    unmet.extend(f"missing_material:{item.value}" for item in missing_materials)
    if missing_kps:
        return AdequacyCandidate(
            status=AdequacyStatus.UNRESOLVABLE,
            rationale="任务知识点缺少可见 Evidence，当前候选不可生成。",
            unmet_requirements=unmet,
            allowed_actions=[NextAction.REDUCE_SCOPE, NextAction.HUMAN_REVIEW],
        )
    if missing_materials:
        return AdequacyCandidate(
            status=AdequacyStatus.NEEDS_MORE_EVIDENCE,
            rationale="Evidence 未覆盖任务要求的材料类型。",
            unmet_requirements=unmet,
            allowed_actions=[NextAction.SUPPLEMENT_RETRIEVAL, NextAction.REDUCE_SCOPE],
        )
    return AdequacyCandidate(
        status=AdequacyStatus.ADEQUATE,
        rationale="缩减后的输出规模与现有 approved Evidence、知识点和材料覆盖相匹配。",
        allowed_actions=[NextAction.GENERATE],
    )


def _rubric(artifact: ArtifactType) -> ArtifactRubricProfile:
    return ArtifactRubricProfile(
        artifact_type=artifact,
        dimensions=[
            RubricDimension(rubric_id=rubric_id, label=label, description=description)
            for rubric_id, label, description in _RUBRICS[artifact]
        ],
        edit_burden_scale=_EDIT_BURDEN,
    )


def _build_failures() -> FailureReplayDataset:
    records = [
        _failure(
            "01",
            "schema",
            ArtifactType.LESSON,
            "lesson.generator.response",
            "invalid_model_output",
            "failed_closed",
        ),
        _failure(
            "02",
            "schema",
            ArtifactType.EXAM,
            "exam.batch.response",
            "invalid_model_output",
            "failed_closed",
        ),
        _failure(
            "03",
            "schema",
            ArtifactType.PPT,
            "ppt.slide.response",
            "invalid_model_output",
            "failed_closed",
        ),
        _failure(
            "04",
            "timeout",
            None,
            "provider.request",
            "provider_timeout",
            "needs_reconciliation",
            resume=True,
        ),
        _failure(
            "05",
            "missing_batch",
            ArtifactType.EXAM,
            "exam.fan_in",
            "missing_batch",
            "resuming",
            resume=True,
        ),
        _failure(
            "06",
            "incomplete_group",
            None,
            "courserag.generation_context",
            "incomplete_evidence_group",
            "needs_more_evidence",
        ),
        _failure(
            "07",
            "index_missing",
            None,
            "courserag.index_probe",
            "index_missing",
            "blocked_missing_index",
        ),
    ]
    return FailureReplayDataset(records=records)


def _failure(
    suffix: str,
    category: str,
    artifact: ArtifactType | None,
    injection_point: str,
    error_class: str,
    user_status: str,
    *,
    resume: bool = False,
) -> FailureReplayCase:
    return FailureReplayCase(
        record_id=f"sysopt-v1-failure-{suffix}",
        candidate_source="codex_ep00_failure_class_replay",
        category=category,
        artifact_type=artifact,
        injection_point=injection_point,
        fixture={"injected": True, "source": "new_ep00_fixture", "attempt": 1},
        expectation=FailureExpectation(
            error_class=error_class,
            user_status=user_status,
            retry_allowed=False,
            resume_allowed=resume,
            maximum_side_effects=0,
        ),
    )


def historical_baseline() -> dict[str, Any]:
    return {
        "schema_version": "system-optimization.historical-dev-baseline.v1",
        "optimization_eligible": False,
        "reason": "historical scopes are not a unified new-Dev human comparison",
        "automatic_dev": {
            "source": "storage_eval/p18/dev_freeze_candidate_r2/dev_freeze_summary.json",
            "source_kind": "ignored_local_historical_aggregate",
            "cp_b0": {
                "samples": 18,
                "succeeded": 14,
                "contract_pass_rate": 0.6111111111111112,
                "citation_resolvability": 0.7777777777777778,
                "p50_latency_ms": 88894.0,
                "p95_latency_ms": 359699.35,
                "input_tokens": 160283,
                "output_tokens": 253214,
                "cost_cny": 0.666711,
            },
            "cp_b10": {
                "samples": 18,
                "succeeded": 18,
                "contract_pass_rate": 1.0,
                "citation_resolvability": 1.0,
                "p50_latency_ms": 123409.5,
                "p95_latency_ms": 297824.4,
                "input_tokens": 504595,
                "output_tokens": 292248,
                "cost_cny": 1.089091,
            },
        },
        "human_dev": {
            "lesson": {
                "source": "docs/refactor/phase_reports/P14_lesson_workflow_closure.md",
                "cp_b0_mean_rubric": 3.833,
                "cp_b0_mean_edit_burden": 2.0,
                "candidate_mean_rubric": 3.5,
                "candidate_mean_edit_burden": 2.667,
            },
            "exam": {
                "source": "docs/refactor/phase_reports/P15_exam_blueprint_fanout_global_repair.md",
                "cp_b0_mean_rubric": 3.122,
                "cp_b0_mean_edit_burden": 1.667,
                "cp_b0_acceptable_rate": 0.6444,
                "candidate_mean_rubric": 3.524,
                "candidate_mean_edit_burden": 1.311,
                "candidate_acceptable_rate": 0.4889,
            },
            "ppt": {
                "source": "docs/refactor/phase_reports/P16_ppt_architecture_template_rendering.md",
                "comparable_aggregate_available": False,
            },
        },
        "new_dev_baseline": {
            "status": "pending_human_approval_and_provider_authorization",
            "provider_calls": 0,
        },
    }


def write_candidate_data(repository_root: Path, output_root: Path) -> dict[str, str]:
    cases, failures = build_candidate_data(repository_root)
    candidate_dir = output_root / "candidates"
    candidate_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        "dev_cases": candidate_dir / "dev_cases.json",
        "failure_replays": candidate_dir / "failure_replays.json",
        "historical_baseline": candidate_dir / "historical_baseline.json",
    }
    _write_json(paths["dev_cases"], cases.model_dump(mode="json"))
    _write_json(paths["failure_replays"], failures.model_dump(mode="json"))
    _write_json(paths["historical_baseline"], historical_baseline())
    return {key: str(path) for key, path in paths.items()}


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _is_p18_identifier(value: str) -> bool:
    return value.casefold().startswith(("p18-", "p18_", "p18:"))


def _assert_no_approved_directory(paths: Iterable[Path]) -> None:
    if any(path.name.casefold() == "approved" for path in paths):
        raise ValueError("EP-00 candidate generation must never create approved data")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository-root", type=Path, default=Path.cwd())
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path("datasets/system_optimization/v1"),
    )
    args = parser.parse_args()
    _assert_no_approved_directory(args.output_root.parts and [args.output_root] or [])
    result = write_candidate_data(args.repository_root.resolve(), args.output_root)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
