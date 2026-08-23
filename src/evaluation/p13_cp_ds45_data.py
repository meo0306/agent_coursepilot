"""Build the P13 CP-DS4/5 Pilot Candidates from approved upstream fixtures."""

from __future__ import annotations

import argparse
import copy
import hashlib
import html
import json
import re
from pathlib import Path
from typing import Any, cast

from coursepilot.evals.formal_schemas import (
    CPDS4P13PilotDataset,
    CPDS5P13PilotDataset,
    IssueScope,
    RepairCase,
    ValidationFaultCase,
    ValidationIssue,
)
from evaluation.corpus_fixtures import sha256_file
from evaluation.io import atomic_write_json, atomic_write_text

DATASET_ROOT = Path("datasets/coursepilot_eval/v1")
DS4_PATH = DATASET_ROOT / "candidates/cp_ds4/p13_validation_r1.json"
DS5_PATH = DATASET_ROOT / "candidates/cp_ds5/p13_repair_r1.json"
FIXTURE_PATH = DATASET_ROOT / "provenance/p13_artifact_fixtures.json"
MANIFEST_PATH = DATASET_ROOT / "provenance/p13_gold_bundle_manifest.json"
REPORT_PATH = Path("docs/refactor/phase_reports/ED_PRE_P13_CPDS45_candidate_review.md")


def _digest(value: object) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _path_parts(path: str) -> list[str | int]:
    parts: list[str | int] = []
    for name, index in re.findall(r"([A-Za-z_][A-Za-z0-9_]*)(?:\[(\d+)\])?", path[2:]):
        parts.append(name)
        if index:
            parts.append(int(index))
    return parts


def _mutate(document: dict[str, Any], path: str, value: Any, *, remove: bool = False) -> None:
    parts = _path_parts(path)
    parent: Any = document
    for part in parts[:-1]:
        parent = parent[part]
    leaf = parts[-1]
    if remove:
        if isinstance(parent, dict):
            parent.pop(leaf, None)
        else:
            parent.pop(leaf)
    else:
        parent[leaf] = value


def _upstream(root: Path) -> tuple[dict[str, Any], dict[str, str]]:
    ds2_path = root / "datasets/courserag_eval/v1/approved/ds2/p06_evidence.json"
    ds3_path = root / "datasets/courserag_eval/v1/approved/ds3/p07_knowledge_points.json"
    ds2 = json.loads(ds2_path.read_text(encoding="utf-8"))
    ds3 = json.loads(ds3_path.read_text(encoding="utf-8"))
    evidence_by_course: dict[str, dict[str, Any]] = {}
    for item in ds2["evidence"]:
        evidence_by_course.setdefault(item["course_id"], item)
    kp_by_course: dict[str, dict[str, Any]] = {}
    for item in ds3["knowledge_points"]:
        kp_by_course.setdefault(item["course_id"], item)
    courses = sorted(set(evidence_by_course) & set(kp_by_course))
    if len(courses) < 2:
        raise ValueError("P13 requires both approved CourseRAG courses")
    return {
        "evidence_by_course": evidence_by_course,
        "kp_by_course": kp_by_course,
        "courses": courses,
    }, {"ds2": sha256_file(ds2_path), "ds3": sha256_file(ds3_path)}


def _base_artifact(
    kind: str, index: int, course_id: str, evidence: dict[str, Any], kp: dict[str, Any]
) -> dict[str, Any]:
    ref = {
        "evidence_id": evidence["evidence_id"],
        "knowledge_point_id": kp["gold_kp_id"],
        "course_id": course_id,
    }
    if kind == "lesson":
        return {
            "artifact_id": f"p13-lesson-valid-{index:02d}",
            "artifact_type": "lesson",
            "artifact_version": 1,
            "course_id": course_id,
            "template_id": "lesson_standard_university_v1",
            "title": f"{kp['canonical_name']} 教学设计",
            "total_sessions": 2,
            "session_duration": 45,
            "knowledge_points": [kp["gold_kp_id"]],
            "session_plan": [
                {
                    "session_index": 1,
                    "session_title": "概念与原理",
                    "duration": 45,
                    "knowledge_points": [kp["gold_kp_id"]],
                    "teaching_focus": kp["canonical_name"],
                    "time_allocation": [{"activity": "讲授", "minutes": 45}],
                },
                {
                    "session_index": 2,
                    "session_title": "应用与练习",
                    "duration": 45,
                    "knowledge_points": [kp["gold_kp_id"]],
                    "teaching_focus": "应用练习",
                    "time_allocation": [{"activity": "讨论", "minutes": 45}],
                },
            ],
            "sessions": [
                {
                    "session_index": 1,
                    "session_title": "概念与原理",
                    "teaching_objectives": [f"能够解释{kp['canonical_name']}"],
                    "key_points": [kp["canonical_name"]],
                    "teaching_process": [
                        {"stage": "讲授", "minutes": 45, "content": kp["summary"]}
                    ],
                    "references": [ref],
                },
                {
                    "session_index": 2,
                    "session_title": "应用与练习",
                    "teaching_objectives": [f"能够说明{kp['canonical_name']}的应用"],
                    "key_points": [kp["canonical_name"]],
                    "teaching_process": [
                        {"stage": "讨论", "minutes": 45, "content": "基于证据进行练习"}
                    ],
                    "references": [ref],
                },
            ],
        }
    if kind == "exam":
        return {
            "artifact_id": f"p13-exam-valid-{index:02d}",
            "artifact_type": "exam",
            "artifact_version": 1,
            "course_id": course_id,
            "template_id": "exam_unit_quiz_v1",
            "chapter_range": kp["canonical_name"],
            "blueprint": {
                "question_counts": {"single_choice": 2},
                "total_score": 4,
                "knowledge_points": [kp["gold_kp_id"]],
            },
            "questions": [
                {
                    "question_id": "q1",
                    "question_type": "single_choice",
                    "stem": f"关于{kp['canonical_name']}，下列说法正确的是？",
                    "options": ["A", "B", "C", "D"],
                    "correct_answer": "A",
                    "explanation": kp["summary"],
                    "knowledge_point_ids": [kp["gold_kp_id"]],
                    "evidence_ids": [evidence["evidence_id"]],
                },
                {
                    "question_id": "q2",
                    "question_type": "single_choice",
                    "stem": f"{kp['canonical_name']}的核心特征是什么？",
                    "options": ["A", "B", "C", "D"],
                    "correct_answer": "B",
                    "explanation": kp["summary"],
                    "knowledge_point_ids": [kp["gold_kp_id"]],
                    "evidence_ids": [evidence["evidence_id"]],
                },
            ],
        }
    return {
        "artifact_id": f"p13-ppt-valid-{index:02d}",
        "artifact_type": "ppt",
        "artifact_version": 1,
        "course_id": course_id,
        "template_id": "ppt_standard_lecture_v1",
        "style_template": "standard",
        "slide_count": 4,
        "lesson_id": f"p13-lesson-valid-{index:02d}",
        "slides": [
            {
                "slide_index": 1,
                "slide_type": "title",
                "title": kp["canonical_name"],
                "bullet_points": [kp["canonical_name"]],
                "layout": "title",
                "source_session_index": 1,
                "references": [ref],
            },
            {
                "slide_index": 2,
                "slide_type": "content",
                "title": "核心内容",
                "bullet_points": [kp["summary"]],
                "layout": "content",
                "source_session_index": 1,
                "references": [ref],
            },
            {
                "slide_index": 3,
                "slide_type": "activity",
                "title": "课堂活动",
                "bullet_points": ["基于证据进行讨论"],
                "layout": "content",
                "source_session_index": 2,
                "references": [ref],
            },
            {
                "slide_index": 4,
                "slide_type": "references",
                "title": "参考资料",
                "bullet_points": [evidence["evidence_id"]],
                "layout": "references",
                "source_session_index": 2,
                "references": [ref],
            },
        ],
    }


FAULTS: dict[str, list[dict[str, Any]]] = {
    "lesson": [
        {"name": "clean", "issues": []},
        {
            "name": "schema-missing",
            "path": "$.session_plan[0].teaching_focus",
            "remove": True,
            "code": "LESSON_SCHEMA_REQUIRED_FIELD_MISSING",
            "severity": "critical",
            "layer": "L0",
        },
        {
            "name": "session-count",
            "path": "$.total_sessions",
            "value": 3,
            "code": "LESSON_SESSION_COUNT_MISMATCH",
            "severity": "error",
            "layer": "L1",
        },
        {
            "name": "time-total",
            "path": "$.session_plan[0].time_allocation[0].minutes",
            "value": 99,
            "code": "LESSON_TIME_ALLOCATION_MISMATCH",
            "severity": "error",
            "layer": "L1",
        },
        {
            "name": "kp-coverage",
            "path": "$.sessions[0].key_points",
            "value": [],
            "code": "LESSON_KP_NOT_COVERED",
            "severity": "error",
            "layer": "L2",
        },
        {
            "name": "grounding-missing",
            "path": "$.sessions[0].references[0].evidence_id",
            "value": "gold-ev-missing",
            "code": "GROUNDING_EVIDENCE_NOT_FOUND",
            "severity": "error",
            "layer": "L3",
        },
        {
            "name": "objective",
            "path": "$.sessions[0].teaching_objectives[0]",
            "value": "了解相关内容",
            "code": "LESSON_OBJECTIVE_NOT_MEASURABLE",
            "severity": "warning",
            "layer": "L4",
        },
        {
            "name": "source-tier",
            "path": "$.sessions[0].references[0].course_id",
            "value": "other-course",
            "code": "GROUNDING_SOURCE_TIER_INVALID",
            "severity": "critical",
            "layer": "L3",
        },
        {
            "name": "count-time-combo",
            "combo": [1, 3],
            "code": "LESSON_SESSION_COUNT_MISMATCH",
            "severity": "error",
            "layer": "L1",
        },
        {
            "name": "grounding-quality-combo",
            "combo": [5, 6],
            "code": "GROUNDING_EVIDENCE_NOT_FOUND",
            "severity": "critical",
            "layer": "L3",
        },
    ],
    "exam": [
        {"name": "clean", "issues": []},
        {
            "name": "schema-missing",
            "path": "$.blueprint.total_score",
            "remove": True,
            "code": "EXAM_SCHEMA_FIELD_MISSING",
            "severity": "critical",
            "layer": "L0",
        },
        {
            "name": "question-count",
            "path": "$.blueprint.question_counts.single_choice",
            "value": 5,
            "code": "EXAM_QUESTION_COUNT_MISMATCH",
            "severity": "error",
            "layer": "L1",
        },
        {
            "name": "score",
            "path": "$.blueprint.total_score",
            "value": 99,
            "code": "EXAM_SCORE_MISMATCH",
            "severity": "error",
            "layer": "L1",
        },
        {
            "name": "answer-option",
            "path": "$.questions[0].correct_answer",
            "value": "Z",
            "code": "EXAM_ANSWER_NOT_IN_OPTIONS",
            "severity": "error",
            "layer": "L1",
        },
        {
            "name": "kp-coverage",
            "path": "$.questions[0].knowledge_point_ids",
            "value": [],
            "code": "EXAM_KP_COVERAGE_MISSING",
            "severity": "error",
            "layer": "L2",
        },
        {
            "name": "duplicate",
            "path": "$.questions[1].stem",
            "value": "关于该知识点，下列说法正确的是？",
            "code": "EXAM_DUPLICATE_QUESTION",
            "severity": "warning",
            "layer": "L2",
        },
        {
            "name": "grounding",
            "path": "$.questions[0].evidence_ids",
            "value": ["gold-ev-missing"],
            "code": "GROUNDING_EVIDENCE_NOT_FOUND",
            "severity": "critical",
            "layer": "L3",
        },
        {
            "name": "explanation",
            "path": "$.questions[0].explanation",
            "value": "答案是其他选项",
            "code": "EXAM_EXPLANATION_ANSWER_CONFLICT",
            "severity": "error",
            "layer": "L4",
        },
        {
            "name": "score-answer-combo",
            "combo": [2, 3],
            "code": "EXAM_SCORE_MISMATCH",
            "severity": "error",
            "layer": "L1",
        },
        {
            "name": "grounding-duplicate-combo",
            "combo": [6, 5],
            "code": "GROUNDING_EVIDENCE_NOT_FOUND",
            "severity": "critical",
            "layer": "L3",
        },
    ],
    "ppt": [
        {"name": "clean", "issues": []},
        {
            "name": "schema-missing",
            "path": "$.style_template",
            "remove": True,
            "code": "PPT_SCHEMA_FIELD_MISSING",
            "severity": "critical",
            "layer": "L0",
        },
        {
            "name": "slide-count",
            "path": "$.slide_count",
            "value": 9,
            "code": "PPT_SLIDE_COUNT_MISMATCH",
            "severity": "error",
            "layer": "L1",
        },
        {
            "name": "slide-type",
            "path": "$.slides[1].slide_type",
            "value": "invalid",
            "code": "PPT_INVALID_SLIDE_TYPE",
            "severity": "error",
            "layer": "L1",
        },
        {
            "name": "session-source",
            "path": "$.slides[1].source_session_index",
            "value": 99,
            "code": "PPT_SESSION_SOURCE_INVALID",
            "severity": "error",
            "layer": "L2",
        },
        {
            "name": "citation",
            "path": "$.slides[2].references",
            "value": [],
            "code": "PPT_CITATION_MISSING",
            "severity": "error",
            "layer": "L3",
        },
        {
            "name": "layout",
            "path": "$.slides[1].layout",
            "remove": True,
            "code": "PPT_LAYOUT_MISSING",
            "severity": "error",
            "layer": "L1",
        },
        {
            "name": "overflow",
            "path": "$.slides[1].bullet_points",
            "value": ["过长内容"] * 12,
            "code": "PPT_CONTENT_OVERFLOW_RISK",
            "severity": "warning",
            "layer": "L4",
        },
        {
            "name": "references",
            "path": "$.slides[3].references",
            "value": [],
            "code": "PPT_REFERENCES_SLIDE_MISSING",
            "severity": "error",
            "layer": "L3",
        },
        {
            "name": "count-source-combo",
            "combo": [2, 4],
            "code": "PPT_SLIDE_COUNT_MISMATCH",
            "severity": "error",
            "layer": "L1",
        },
        {
            "name": "citation-overflow-combo",
            "combo": [5, 7],
            "code": "PPT_CITATION_MISSING",
            "severity": "error",
            "layer": "L3",
        },
    ],
}


def _issue(
    kind: str, case_id: str, spec: dict[str, Any], evidence_id: str, *, suffix: str = "01"
) -> ValidationIssue:
    path = spec.get("path", "$.artifact")
    item_id = (
        "root"
        if "sessions" not in path and "questions" not in path and "slides" not in path
        else path.split(".")[1].split("[")[0]
    )
    return ValidationIssue(
        issue_id=f"{case_id}.issue-{suffix}",
        code=spec["code"],
        severity=spec["severity"],
        layer=spec["layer"],
        scope=IssueScope(artifact_type=kind, item_id=item_id, json_path=path),
        allowed_parent_paths=["$.sessions[0]"] if kind == "lesson" else [],
        auto_repairable=spec["layer"] in {"L0", "L1", "L2"},
        message=f"Injected {spec['code']} for P13 Pilot",
        expected="valid source-grounded value",
        actual=spec.get("value", "mutated"),
        evidence_ids=[evidence_id] if spec["layer"] == "L3" else [],
        repair_strategy="deterministic_patch"
        if spec["layer"] in {"L0", "L1", "L2"}
        else "model_patch",
    )


def generate(repository_root: Path) -> dict[str, Any]:
    root = repository_root.resolve()
    upstream, upstream_hashes = _upstream(root)
    fixtures: list[dict[str, Any]] = []
    variants: dict[str, dict[str, Any]] = {}
    ds4_cases: list[ValidationFaultCase] = []
    ds5_cases: list[RepairCase] = []
    repair_index = 0
    for kind in ("lesson", "exam", "ppt"):
        for fixture_index in range(1, 4):
            course_id = upstream["courses"][(fixture_index - 1) % len(upstream["courses"])]
            evidence = upstream["evidence_by_course"][course_id]
            kp = upstream["kp_by_course"][course_id]
            base = _base_artifact(kind, fixture_index, course_id, evidence, kp)
            fixture_id = base["artifact_id"]
            fixtures.append(
                {
                    "fixture_id": fixture_id,
                    "artifact_type": kind,
                    "course_id": course_id,
                    "artifact": base,
                    "artifact_sha256": _digest(base),
                    "source_evidence_id": evidence["evidence_id"],
                    "source_knowledge_point_id": kp["gold_kp_id"],
                }
            )
        specs = FAULTS[kind][:10]
        for ordinal, spec in enumerate(specs, 1):
            fixture_index = ((ordinal - 1) % 3) + 1
            base_entry = fixtures[
                [item["artifact_type"] for item in fixtures].index(kind) + fixture_index - 1
            ]
            base = copy.deepcopy(base_entry["artifact"])
            case_id = f"p13-ds4-{kind}-{ordinal:02d}-{spec['name']}"
            mutations: list[dict[str, Any]] = []
            issue_specs = [spec]
            if "combo" in spec:
                issue_specs = [specs[index] for index in spec["combo"]]
            for issue_spec in issue_specs:
                if "path" in issue_spec:
                    mutation = {
                        "path": issue_spec["path"],
                        "operation": "remove" if issue_spec.get("remove") else "replace",
                        "value": issue_spec.get("value"),
                    }
                    mutations.append(mutation)
                    _mutate(
                        base,
                        issue_spec["path"],
                        issue_spec.get("value"),
                        remove=issue_spec.get("remove", False),
                    )
            variant_id = f"{case_id}-variant"
            variants[variant_id] = {
                "variant_id": variant_id,
                "fixture_id": base_entry["fixture_id"],
                "artifact": base,
                "artifact_sha256": _digest(base),
                "mutations": mutations,
            }
            clean = spec["name"] == "clean"
            issues = (
                []
                if clean
                else [
                    _issue(
                        kind, case_id, item, base_entry["source_evidence_id"], suffix=str(index + 1)
                    )
                    for index, item in enumerate(issue_specs)
                ]
            )
            paths = [item["path"] for item in mutations]
            ds4_cases.append(
                ValidationFaultCase(
                    record_id=case_id,
                    candidate_source="p13_hybrid_fixture",
                    artifact_type=kind,
                    artifact_fixture_id=base_entry["fixture_id"],
                    injection_ids=[spec["name"]],
                    gold_issues=issues,
                    clean_artifact=clean,
                    fixture_variant_id=variant_id,
                    injection_paths=paths,
                    source_provenance=[
                        base_entry["source_evidence_id"],
                        base_entry["source_knowledge_point_id"],
                    ],
                )
            )
            if not clean and len(ds5_cases) < 15 and ordinal in {2, 4, 6, 8, 9}:
                repair_index += 1
                allowed = paths or ["$.artifact"]
                ds5_cases.append(
                    RepairCase(
                        record_id=f"p13-ds5-{kind}-{repair_index:02d}",
                        candidate_source="p13_hybrid_fixture",
                        artifact_type=kind,
                        artifact_before_id=variant_id,
                        allowed_paths=allowed,
                        forbidden_paths=["$.artifact_id", "$.artifact_version", "$.course_id"],
                        expected_resolved_issue_codes=[item.code for item in issues],
                        original_correct_paths=["$.artifact_id", "$.course_id", "$.template_id"],
                        max_repair_rounds=2,
                        source_fault_case_id=case_id,
                        fixture_variant_id=variant_id,
                        repair_strategy="deterministic_patch"
                        if all(item.layer in {"L0", "L1", "L2"} for item in issues)
                        else "model_patch",
                        preconditions=["source_version=1", "issue_scope_matches_gold"],
                        preservation_paths=["$.artifact_id", "$.course_id", "$.template_id"],
                        issue_layers=[item.layer for item in issues],
                    )
                )
    fixture_payload = {
        "schema_version": "coursepilot.cp-ds4-ds5-p13-fixtures.v1",
        "source_strategy": "hybrid",
        "upstream": upstream_hashes,
        "fixtures": fixtures,
        "variants": list(variants.values()),
    }
    ds4 = CPDS4P13PilotDataset(dataset_id="coursepilot-eval", cases=ds4_cases)
    ds5 = CPDS5P13PilotDataset(dataset_id="coursepilot-eval", cases=ds5_cases)
    atomic_write_json(root / DS4_PATH, ds4.model_dump(mode="json"))
    atomic_write_json(root / DS5_PATH, ds5.model_dump(mode="json"))
    atomic_write_json(root / FIXTURE_PATH, cast(dict[str, Any], fixture_payload))
    hashes = {
        "ds4": sha256_file(root / DS4_PATH),
        "ds5": sha256_file(root / DS5_PATH),
        "fixtures": sha256_file(root / FIXTURE_PATH),
    }
    bundle_sha = _digest(hashes)
    review_root = root / f"storage_eval/cpds45_p13_review/{bundle_sha}"
    html_page = _review_html(ds4, ds5, fixture_payload, bundle_sha, second=False)
    second_page = _review_html(ds4, ds5, fixture_payload, bundle_sha, second=True)
    atomic_write_text(review_root / "index.html", html_page)
    atomic_write_text(review_root / "second_review.html", second_page)
    manifest = {
        "schema_version": "coursepilot.p13-gold-bundle-manifest.v1",
        "bundle_sha256": bundle_sha,
        "candidate_hashes": hashes,
        "record_counts": {"ds4": len(ds4.cases), "ds5": len(ds5.cases)},
        "source_strategy": "hybrid",
        "upstream": upstream_hashes,
        "review_pack": f"storage_eval/cpds45_p13_review/{bundle_sha}",
        "approval_scope": "cp_ds4_validation_and_cp_ds5_repair_pilot_only",
    }
    atomic_write_json(root / MANIFEST_PATH, cast(dict[str, Any], manifest))
    report = f"""# ED-PRE13 CP-DS4/5 Candidate Review

- CP-DS4 Candidate: `{DS4_PATH.as_posix()}` ({len(ds4.cases)} records)
- CP-DS5 Candidate: `{DS5_PATH.as_posix()}` ({len(ds5.cases)} records)
- Fixture bundle: `{FIXTURE_PATH.as_posix()}`
- CP-DS4 SHA-256: `{hashes["ds4"]}`
- CP-DS5 SHA-256: `{hashes["ds5"]}`
- Fixture SHA-256: `{hashes["fixtures"]}`
- Bundle SHA-256: `{bundle_sha}`
- Strategy: hybrid; structural fixtures are deterministic, grounding references use only Approved DS2/DS3 from the two existing courses.
- Review: `storage_eval/cpds45_p13_review/{bundle_sha}/index.html`
- Blind second review: `storage_eval/cpds45_p13_review/{bundle_sha}/second_review.html`

No P13 output, external Provider, CourseRAG Test/Holdout, Dev/Test split or formal CP-DS1—3 Gold was used.
Candidate status remains `candidate`; approval is required before P13 implementation.

Review all 45 records. Focus on Issue code/layer/severity/scope, clean controls, injected paths,
allowed/forbidden Repair paths, preconditions, preservation paths and grounding provenance.

Review UI v2 presents compact human-readable cards by default: artifact summary, injected
before/after values, expected Issues or Repair boundaries, and one explicit review question.
Raw Gold/Fixture JSON is collapsed for exception handling. Filters, progress, bulk-pass for the
current filter and local decision persistence reduce review effort. This presentation-only change
does not alter Candidate files, record hashes or Bundle SHA-256.
"""
    atomic_write_text(root / REPORT_PATH, report)
    return {
        "bundle_sha256": bundle_sha,
        "ds4_count": len(ds4.cases),
        "ds5_count": len(ds5.cases),
        "review_path": review_root.relative_to(root).as_posix(),
    }


ISSUE_LABELS = {
    "LESSON_SCHEMA_REQUIRED_FIELD_MISSING": "教案缺少必填字段",
    "LESSON_SESSION_COUNT_MISMATCH": "课次数量与计划不一致",
    "LESSON_TIME_ALLOCATION_MISMATCH": "教学活动时长与课时不一致",
    "LESSON_KP_NOT_COVERED": "课程知识点未被教学内容覆盖",
    "GROUNDING_EVIDENCE_NOT_FOUND": "引用的证据不存在",
    "LESSON_OBJECTIVE_NOT_MEASURABLE": "教学目标无法观察或衡量",
    "GROUNDING_SOURCE_TIER_INVALID": "引用来自错误课程或无效来源层级",
    "EXAM_SCHEMA_FIELD_MISSING": "试卷缺少必填字段",
    "EXAM_QUESTION_COUNT_MISMATCH": "题目数量与蓝图不一致",
    "EXAM_SCORE_MISMATCH": "题目总分与蓝图不一致",
    "EXAM_ANSWER_NOT_IN_OPTIONS": "标准答案不在选项中",
    "EXAM_KP_COVERAGE_MISSING": "试卷未覆盖要求的知识点",
    "EXAM_DUPLICATE_QUESTION": "试卷存在重复题目",
    "EXAM_EXPLANATION_ANSWER_CONFLICT": "答案解析与标准答案冲突",
    "PPT_SCHEMA_FIELD_MISSING": "课件缺少必填字段",
    "PPT_SLIDE_COUNT_MISMATCH": "幻灯片数量与声明不一致",
    "PPT_INVALID_SLIDE_TYPE": "幻灯片类型不合法",
    "PPT_SESSION_SOURCE_INVALID": "幻灯片引用了无效课次",
    "PPT_CITATION_MISSING": "课程事实缺少证据引用",
    "PPT_LAYOUT_MISSING": "幻灯片缺少布局信息",
    "PPT_CONTENT_OVERFLOW_RISK": "幻灯片内容存在溢出风险",
    "PPT_REFERENCES_SLIDE_MISSING": "课件缺少参考文献页",
}


def _value_at(document: dict[str, Any], path: str) -> Any:
    current: Any = document
    try:
        for part in _path_parts(path):
            current = current[part]
    except (KeyError, IndexError, TypeError):
        return None
    return current


def _short_value(value: Any) -> str:
    if value is None:
        return "（不存在/已删除）"
    rendered = json.dumps(value, ensure_ascii=False) if not isinstance(value, str) else value
    return rendered if len(rendered) <= 180 else rendered[:177] + "…"


def _artifact_summary(artifact: dict[str, Any]) -> list[tuple[str, str]]:
    artifact_type = artifact.get("artifact_type", "")
    rows = [
        ("课程", str(artifact.get("course_id", "—"))),
        ("模板", str(artifact.get("template_id", "—"))),
    ]
    if artifact_type == "lesson":
        sessions = artifact.get("sessions", [])
        source = ""
        if sessions:
            process = sessions[0].get("teaching_process", [])
            source = process[0].get("content", "") if process else ""
        rows.extend(
            [
                ("教案", str(artifact.get("title", "—"))),
                (
                    "规模",
                    f"{artifact.get('total_sessions', '—')} 课次 × {artifact.get('session_duration', '—')} 分钟",
                ),
                ("首个教学内容", _short_value(source)),
            ]
        )
    elif artifact_type == "exam":
        questions = artifact.get("questions", [])
        source = questions[0].get("explanation", "") if questions else ""
        rows.extend(
            [
                ("试卷范围", str(artifact.get("chapter_range", artifact.get("title", "—")))),
                ("题量", str(len(questions))),
                ("首题解析依据", _short_value(source)),
            ]
        )
    else:
        slides = artifact.get("slides", [])
        slide_titles = " / ".join(str(item.get("title", "")) for item in slides[:4])
        rows.extend(
            [
                ("课件", str(artifact.get("title", "—"))),
                ("页数", str(len(slides))),
                ("前几页标题", _short_value(slide_titles)),
            ]
        )
    return rows


def _summary_table(rows: list[tuple[str, str]], css_class: str = "summary") -> str:
    body = "".join(
        f"<tr><th>{html.escape(label)}</th><td>{html.escape(value)}</td></tr>"
        for label, value in rows
    )
    return f"<table class='{css_class}'>{body}</table>"


def _review_css() -> str:
    return """<style>
:root{color-scheme:light;--ink:#172033;--muted:#667085;--line:#d0d5dd}*{box-sizing:border-box}
body{font-family:system-ui,'Microsoft YaHei',sans-serif;color:var(--ink);max-width:1180px;margin:auto;padding:24px;background:#f8fafc}
h1{margin-bottom:8px}h2{font-size:1.12rem;margin:8px 0 0}h3{font-size:1rem;margin:20px 0 8px}code{overflow-wrap:anywhere}
.intro,.toolbar{background:white;border:1px solid var(--line);border-radius:12px;padding:16px;margin:14px 0}.toolbar{position:sticky;top:8px;z-index:5;box-shadow:0 3px 14px #10182814}
.filters,.actions{display:flex;gap:8px;flex-wrap:wrap}.filters button,.actions button{padding:8px 12px;border:1px solid #98a2b3;border-radius:8px;background:white;cursor:pointer}.filters button.active{background:#eff8ff;border-color:#2e90fa;color:#175cd3}
.progress{margin-top:12px;font-weight:650}.card{background:white;border:1px solid var(--line);border-left:6px solid #f79009;border-radius:12px;padding:20px;margin:18px 0}.card.clean{border-left-color:#12b76a}.card.repair{border-left-color:#2e90fa}.card[hidden]{display:none}
.card header{display:flex;justify-content:space-between;gap:12px;align-items:flex-start}.badge{display:inline-block;font-size:.76rem;font-weight:700;background:#f2f4f7;border-radius:999px;padding:4px 8px}.state{color:var(--muted);font-weight:700}.state.pass{color:#067647}.state.return{color:#b42318}
.review-focus{padding:12px 14px;margin:16px 0;border-radius:8px;background:#fffaeb;border:1px solid #fedf89}.clean .review-focus{background:#ecfdf3;border-color:#abefc6}.repair .review-focus{background:#eff8ff;border-color:#b2ddff}
table{width:100%;border-collapse:collapse;background:white}th,td{text-align:left;vertical-align:top;border:1px solid #e4e7ec;padding:9px 10px}th{background:#f9fafb;width:18%}.summary th,.constraints th{width:150px}.clean-note{padding:10px 12px;background:#ecfdf3;border-radius:7px;color:#067647}
details{margin-top:18px;border-top:1px dashed #b8c0cc;padding-top:12px;color:var(--muted)}summary{cursor:pointer;font-weight:650}pre{white-space:pre-wrap;max-height:520px;overflow:auto;background:#101828;color:#e4e7ec;padding:14px;border-radius:8px;font-size:.82rem}
.decision{display:flex;gap:24px;margin:18px 0 8px;font-weight:700}.decision label{padding:8px 14px;border:1px solid var(--line);border-radius:8px;background:#fff}textarea{width:100%;min-height:58px;padding:9px;border:1px solid #98a2b3;border-radius:7px}.actions{margin-top:12px}.muted{color:var(--muted);font-size:.92rem}
</style>"""


def _review_toolbar() -> str:
    return """<section class='toolbar'><div class='filters'>
<button data-filter='all' class='active'>全部</button><button data-filter='DS4'>DS4 校验</button><button data-filter='DS5'>DS5 修复</button>
<button data-filter='lesson'>Lesson</button><button data-filter='exam'>Exam</button><button data-filter='ppt'>PPT</button>
</div><div class='progress' id='progress'></div><div class='actions'><button id='pass-visible'>当前筛选项全部通过</button><button id='export'>导出审核结果</button></div></section>"""


def _review_script(ids: list[str], bundle_sha: str, review_pass: str, export_name: str) -> str:
    return (
        "<script>"
        f"const ids={json.dumps(ids, ensure_ascii=False)};const sha='{bundle_sha}';const reviewPass='{review_pass}';const exportName='{export_name}';"
        "const key=`p13-review:${sha}:${reviewPass}`;let active='all';const cards=[...document.querySelectorAll('.card')];"
        "function saved(){try{return JSON.parse(localStorage.getItem(key)||'{}')}catch{return {}}}"
        'function persist(){const data={};for(const id of ids){const s=document.querySelector(`input[name="d-${id}"]:checked`);const note=document.querySelector(`[data-note="${id}"]`).value;data[id]={decision:s?.value||\'\',notes:note}}localStorage.setItem(key,JSON.stringify(data));update()}'
        "function update(){let reviewed=0,visible=0,visibleReviewed=0;for(const c of cards){const show=active==='all'||c.dataset.kind===active||c.dataset.type===active;c.hidden=!show;if(show)visible++;const id=c.dataset.id;const s=document.querySelector(`input[name=\"d-${id}\"]:checked`);const state=document.querySelector(`[data-state=\"${id}\"]`);state.textContent=s?(s.value==='pass'?'已通过':'已退回'):'未审核';state.className='state '+(s?.value||'');if(s){reviewed++;if(show)visibleReviewed++}}document.getElementById('progress').textContent=`总进度 ${reviewed}/${ids.length}；当前筛选 ${visibleReviewed}/${visible}`}"
        'const old=saved();for(const id of ids){if(old[id]?.decision){const input=document.querySelector(`input[name="d-${id}"][value="${old[id].decision}"]`);if(input)input.checked=true}document.querySelector(`[data-note="${id}"]`).value=old[id]?.notes||\'\'}'
        "document.addEventListener('change',persist);document.addEventListener('input',e=>{if(e.target.matches('textarea,#reviewer'))persist()});"
        "document.querySelectorAll('[data-filter]').forEach(b=>b.onclick=()=>{active=b.dataset.filter;document.querySelectorAll('[data-filter]').forEach(x=>x.classList.toggle('active',x===b));update()});"
        "document.getElementById('pass-visible').onclick=()=>{for(const c of cards){if(!c.hidden)c.querySelector('input[value=\"pass\"]').checked=true}persist()};"
        "document.getElementById('export').onclick=()=>{const decisions=[];for(const id of ids){const s=document.querySelector(`input[name=\"d-${id}\"]:checked`);const n=document.querySelector(`[data-note=\"${id}\"]`).value.trim();if(!s){alert('还有未审核记录：'+id);return}if(s.value==='return'&&!n){alert('退回项必须填写原因：'+id);return}decisions.push({record_id:id,decision:s.value,notes:n})}const p={schema_version:'coursepilot.p13-review-decisions.v1',bundle_sha256:sha,review_pass:reviewPass,decisions,reviewer_id:document.getElementById('reviewer').value,reviewed_at:new Date().toISOString()};const a=document.createElement('a');a.href=URL.createObjectURL(new Blob([JSON.stringify(p,null,2)],{type:'application/json'}));a.download=exportName;a.click()};update();"
        "</script>"
    )


def _review_html(
    ds4: CPDS4P13PilotDataset,
    ds5: CPDS5P13PilotDataset,
    fixtures: dict[str, Any],
    bundle_sha: str,
    *,
    second: bool,
) -> str:
    variant_map = {item["variant_id"]: item for item in fixtures["variants"]}
    fixture_map = {item["fixture_id"]: item for item in fixtures["fixtures"]}
    ds4_map = {item.record_id: item for item in ds4.cases}
    cards: list[str] = []
    records: list[tuple[str, Any]] = [("DS4", item) for item in ds4.cases] + [
        ("DS5", item) for item in ds5.cases
    ]
    if second:
        records = [
            (kind, item)
            for kind, item in records
            if kind == "DS5"
            or any(issue.layer in {"L3", "L4"} for issue in getattr(item, "gold_issues", []))
            or len(getattr(item, "gold_issues", [])) > 1
        ]
    for kind, item in records:
        variant = variant_map.get(item.fixture_variant_id or item.artifact_before_id, {})
        fixture = fixture_map.get(variant.get("fixture_id", ""), {})
        base = cast(dict[str, Any], fixture.get("artifact", {}))
        faulty = cast(dict[str, Any], variant.get("artifact", {}))
        mutations = cast(list[dict[str, Any]], variant.get("mutations", []))
        change_rows = "".join(
            "<tr>"
            f"<td><code>{html.escape(str(mutation['path']))}</code></td>"
            f"<td>{html.escape(_short_value(_value_at(base, str(mutation['path']))))}</td>"
            f"<td>{html.escape('（字段已删除）' if mutation['operation'] == 'remove' else _short_value(_value_at(faulty, str(mutation['path']))))}</td>"
            "</tr>"
            for mutation in mutations
        )
        changes = (
            "<table><thead><tr><th>修改位置</th><th>正确值</th><th>故障值</th></tr></thead>"
            f"<tbody>{change_rows}</tbody></table>"
            if change_rows
            else "<p class='clean-note'>这是无故障对照样本，没有注入任何修改。</p>"
        )
        summary = _summary_table(_artifact_summary(base))
        if kind == "DS4":
            body = {
                "issues": [issue.model_dump(mode="json") for issue in item.gold_issues],
                "injection_paths": item.injection_paths,
                "variant": variant,
            }
            issue_rows = "".join(
                "<tr>"
                f"<td><strong>{html.escape(ISSUE_LABELS.get(issue.code, issue.code))}</strong><br><code>{html.escape(issue.code)}</code></td>"
                f"<td>{html.escape(issue.layer)} / {html.escape(issue.severity)}</td>"
                f"<td><code>{html.escape(issue.scope.json_path)}</code></td>"
                f"<td>{'是' if issue.auto_repairable else '否'}</td></tr>"
                for issue in item.gold_issues
            )
            issues = (
                "<table><thead><tr><th>应识别的问题</th><th>层级/严重度</th><th>问题位置</th><th>可自动修复</th></tr></thead>"
                f"<tbody>{issue_rows}</tbody></table>"
                if issue_rows
                else "<p class='clean-note'>Gold Issues 为空：系统应判定该成品通过校验。</p>"
            )
            check = (
                "确认成品摘要本身合理，并且它确实不应产生任何 Gold Issue。"
                if item.clean_artifact
                else "确认“正确值→故障值”确实会造成所列问题，并检查问题名称、层级/严重度和定位路径是否合理。"
            )
            main = f"<h3>1. 原始成品摘要</h3>{summary}<h3>2. 注入了什么故障</h3>{changes}<h3>3. 期望系统报出什么问题</h3>{issues}"
            tone = "clean" if item.clean_artifact else "fault"
        else:
            body = {
                "allowed_paths": item.allowed_paths,
                "forbidden_paths": item.forbidden_paths,
                "expected_resolved_issue_codes": item.expected_resolved_issue_codes,
                "preservation_paths": item.preservation_paths,
                "preconditions": item.preconditions,
                "variant": variant,
            }
            source_case = ds4_map.get(item.source_fault_case_id or "")
            source_issues = (
                []
                if source_case is None
                else [
                    f"{ISSUE_LABELS.get(issue.code, issue.code)}（{issue.code}）"
                    for issue in source_case.gold_issues
                ]
            )
            constraints = _summary_table(
                [
                    ("必须修复", "；".join(source_issues or item.expected_resolved_issue_codes)),
                    ("只允许修改", "；".join(item.allowed_paths)),
                    ("禁止修改", "；".join(item.forbidden_paths) or "—"),
                    ("必须保持", "；".join(item.preservation_paths) or "—"),
                    ("修复策略", item.repair_strategy),
                    ("最多轮次", str(item.max_repair_rounds)),
                ],
                "constraints",
            )
            check = "确认允许修改的路径足以修好上述故障；禁止/保持路径能防止整份重写或破坏原本正确内容；修复后不应新增 Error/Critical。"
            main = f"<h3>1. 待修成品摘要</h3>{summary}<h3>2. 当前故障</h3>{changes}<h3>3. 修复边界</h3>{constraints}"
            tone = "repair"
        raw = html.escape(json.dumps(body, ensure_ascii=False, indent=2))
        cards.append(
            f"<article class='card {tone}' data-kind='{kind}' data-type='{html.escape(item.artifact_type)}' data-id='{html.escape(item.record_id)}'>"
            f"<header><div><span class='badge'>{kind}</span> <span class='badge'>{html.escape(item.artifact_type.upper())}</span><h2>{html.escape(item.record_id)}</h2></div><span class='state' data-state='{html.escape(item.record_id)}'>未审核</span></header>"
            f"<div class='review-focus'><strong>你只需要判断：</strong>{html.escape(check)}</div>{main}"
            f"<details><summary>存疑时再看：完整 Gold / Fixture JSON</summary><pre>{raw}</pre></details>"
            f"<div class='decision'><label><input type='radio' name='d-{item.record_id}' value='pass'> 通过</label> <label><input type='radio' name='d-{item.record_id}' value='return'> 退回</label></div>"
            f"<textarea data-note='{item.record_id}' placeholder='仅退回时必填：指出哪一项不准确；通过时可留空'></textarea></article>"
        )
    ids = [item.record_id for _, item in records]
    review_pass = "second" if second else "first"
    heading = "盲化二轮审核" if second else "首轮审核"
    intro = (
        "<!doctype html><html lang='zh-CN'><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        "<title>P13 CP-DS4/5 审核</title>"
        + _review_css()
        + f"<body><h1>P13 CP-DS4/5 {heading}</h1>"
        + "<section class='intro'><p><strong>审核方法：</strong>每张卡只看“你只需要判断”、正确值→故障值、以及 Gold 问题或修复边界。只有存疑时才展开完整 JSON。</p>"
        + f"<p class='muted'>Bundle SHA-256: <code>{bundle_sha}</code> · 共 {len(records)} 条 · 页面调整不改变 Candidate 或 Bundle。</p></section>"
    )
    footer = (
        "<section class='intro'><label>审核人 <input id='reviewer' value='course_owner'></label>"
        "<p class='muted'>决定会自动保存在本浏览器；导出前会检查是否全部完成，以及退回项是否填写原因。</p></section>"
        + _review_script(
            ids,
            bundle_sha,
            review_pass,
            f"p13_{review_pass}_review_{bundle_sha[:12]}.json",
        )
        + "</body></html>\n"
    )
    return intro + _review_toolbar() + "".join(cards) + footer


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository-root", type=Path, default=Path("."))
    args = parser.parse_args()
    print(json.dumps(generate(args.repository_root), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
