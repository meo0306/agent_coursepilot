"""Build the deterministic pre-P11 Draft and, only after P10 closes, the full Candidate."""

from __future__ import annotations

import argparse
import html
import json
from pathlib import Path
from typing import Final

from evaluation.contracts import HashedArtifact
from evaluation.corpus_fixtures import sha256_file
from evaluation.io import atomic_write_json, atomic_write_text
from evaluation.p11_schemas import (
    P11CandidateBundleManifest,
    P11CourseRAGContract,
    P11DraftBundleManifest,
    P11FoundationCandidateDataset,
    P11FoundationCase,
    P11FoundationDraftDataset,
    P11FoundationIdentityContract,
    P11ModelGatewayContract,
    P11P10GateAudit,
    P11P10GateCheck,
    P11SourceReference,
    P11TemplateContract,
    identity_sha256,
)

DATASET_ROOT = Path("datasets/coursepilot_eval/v1")
DRAFT_PATH = DATASET_ROOT / "drafts/p11/p11_foundation_independent_r1.json"
DRAFT_MANIFEST_PATH = DATASET_ROOT / "provenance/p11_foundation_draft_manifest.json"
GATE_AUDIT_PATH = DATASET_ROOT / "provenance/p11_p10_gate_audit.json"
REPORT_PATH = Path("docs/refactor/phase_reports/ED_PRE_P11_foundation_input_review.md")
CANDIDATE_PATH = DATASET_ROOT / "candidates/work_packages/p11_foundation_input_r1.json"
CANDIDATE_MANIFEST_PATH = DATASET_ROOT / "provenance/p11_foundation_input_manifest.json"

FROZEN_DOCS: Final[tuple[str, ...]] = (
    "docs/refactor/frozen_v1.0/00_Document_Index_and_Decision_Baseline_v1.0.md",
    "docs/refactor/frozen_v1.0/05_CoursePilot_Agent_Engineering_Upgrade_Plan_v1.0.md",
    "docs/refactor/frozen_v1.0/06_CoursePilot_and_System_Evaluation_Plan_v1.0.md",
    "docs/refactor/frozen_v1.0/07_Implementation_Roadmap_and_Task_Backlog_v1.0.md",
)
B0_PATH = "docs/refactor/baselines/b0/07_interface_snapshot.json"
P10_FROZEN_PATH = "storage_eval/p10/frozen_manifest.json"
P10_AUTH_PATH = "storage_eval/p10/test_authorization.json"
P10_LOCK_PATH = "datasets/courserag_eval/v1/test.lock.json"
P10_PORT_PATH = "src/coursepilot/ports/courserag.py"
P10_D013_DECISION_PATH = "docs/refactor/DECISION_LOG.md"
P10_D013_POLICY_PATH = "docs/refactor/QUALITY_GATE_POLICY.md"
P10_D013_STATUS_PATH = "docs/refactor/EXECUTION_STATUS.md"
P10_3_REPORT_PATH = "storage_eval/p10_3_security/qualification_dev_report_r1.json"
P10_3_BLIND_PATH = "datasets/courserag_eval/releases/p10_3_security/blind_test_commitment.json"
P10_3_REJECTED_REPORT_SHA256 = "26e5eb98bfe08536987cd8a6b36d769ce3e3370319f8479d57c15b1ba596f0bb"
INHERITED_SECURITY_CONSTRAINTS: Final[tuple[str, ...]] = (
    "retrieved_context_is_untrusted_data",
    "system_and_developer_instructions_cannot_be_overridden",
    "tool_execution_is_default_deny",
    "tool_execution_requires_explicit_capability_and_authorization",
    "course_acl_and_trusted_gateway_claims_remain_enforced",
    "secrets_are_excluded_from_context_trace_and_artifacts",
    "security_decisions_are_audited_without_trusting_p10_3_findings",
    "p10_3_candidate_must_remain_default_off",
)

TEMPLATE_SPECS: Final[tuple[tuple[str, str, tuple[str, ...]], ...]] = (
    ("lesson_standard_university_v1", "lesson", ("lesson_default_docx",)),
    ("lesson_seminar_v1", "lesson", ("lesson_default_docx",)),
    ("lesson_lab_practice_v1", "lesson", ("lesson_default_docx",)),
    ("exam_chapter_assignment_v1", "exam", ("exam_default_docx",)),
    ("exam_unit_quiz_v1", "exam", ("exam_default_docx",)),
    ("exam_midterm_final_v1", "exam", ("exam_default_docx",)),
    ("ppt_standard_lecture_v1", "ppt", ("ppt_standard_lecture_pptx",)),
    ("ppt_concept_explanation_v1", "ppt", ("ppt_concept_explanation_pptx",)),
    ("ppt_case_seminar_v1", "ppt", ("ppt_case_seminar_pptx",)),
)
MODEL_PROFILES: Final[tuple[str, ...]] = (
    "planner_main",
    "generator_main",
    "content_repair_main",
    "classifier_light",
    "json_repair_light",
    "compression_light",
)
PHYSICAL_ROLES: Final[tuple[str, ...]] = (
    "lesson_default_docx",
    "exam_default_docx",
    "ppt_standard_lecture_pptx",
    "ppt_concept_explanation_pptx",
    "ppt_case_seminar_pptx",
)
DEFERRED_IDS: Final[tuple[str, ...]] = (
    "p11-runtime-16-courserag-docx-context",
    "p11-runtime-17-courserag-pdf-context",
    "p11-runtime-18-courserag-fail-closed",
)
SECOND_REVIEW_IDS: Final[tuple[str, ...]] = tuple(
    [
        f"p11-template-{index:02d}-{template_id.replace('_v1', '').replace('_', '-')}"
        for index, (template_id, _, _) in enumerate(TEMPLATE_SPECS, 1)
    ]
    + [
        "p11-model-01-main-light-same-model",
        "p11-model-02-main-light-distinct-models",
        "p11-model-03-light-normal-route",
        "p11-model-04-light-explicit-escalation",
        "p11-model-05-omit-unsupported-reasoning",
        "p11-model-06-omit-unsupported-thinking",
        "p11-model-07-structured-output-capability",
        "p11-model-08-timeout-no-silent-switch",
        "p11-model-09-rate-limit-no-silent-switch",
        "p11-model-10-invalid-json-no-fallback",
        "p11-model-11-missing-usage-unknown",
        "p11-model-12-formal-eval-integrity",
    ]
    + [
        "p11-runtime-06-edit-creates-version",
        "p11-runtime-09-template-snapshot-pinned",
        "p11-runtime-11-fingerprint-input-change",
        "p11-runtime-13-bounded-compaction",
        "p11-runtime-15-b0-compatibility",
        "p11-runtime-16-courserag-docx-context",
    ]
)


def _root(path: Path) -> Path:
    return path.resolve()


def _artifact(
    repository_root: Path, path: Path, media_type: str = "application/json"
) -> HashedArtifact:
    resolved = _root(repository_root / path)
    if not resolved.is_file() or not resolved.is_relative_to(repository_root.resolve()):
        raise ValueError(f"P11 artifact is absent or outside repository: {path.as_posix()}")
    return HashedArtifact(
        path=resolved.relative_to(repository_root.resolve()).as_posix(),
        sha256=sha256_file(resolved),
        size_bytes=resolved.stat().st_size,
        media_type=media_type,
    )


def _source(
    repository_root: Path, relative_path: str, section: str, authority: str = "frozen_document"
) -> P11SourceReference:
    path = repository_root / relative_path
    return P11SourceReference(
        authority=authority,
        relative_path=relative_path,
        sha256=sha256_file(path),
        section=section,
    )


def _base_case(
    *,
    record_id: str,
    component: str,
    title: str,
    source: P11SourceReference,
    expected: list[str],
    forbidden: list[str],
    input_fixture: list[str] | None = None,
    pass_conditions: list[str] | None = None,
    **details: object,
) -> P11FoundationCase:
    return P11FoundationCase(
        record_id=record_id,
        component=component,
        title=title,
        input_fixture=input_fixture
        or ["确定性内存 Fixture；无网络、无真实 Provider、无业务数据库写入"],
        expected_behavior=expected,
        forbidden_behavior=forbidden,
        pass_conditions=pass_conditions or ["所有预期断言成立", "所有禁止行为均未发生"],
        source_references=[source],
        **details,
    )


def build_independent_records(repository_root: Path) -> list[P11FoundationCase]:
    doc05 = _source(repository_root, FROZEN_DOCS[1], "P11 Foundation、模板、模型网关与运行时合同")
    doc07 = _source(repository_root, FROZEN_DOCS[3], "P11-T01—T08、必测项与 Exit Gate")
    b0 = _source(repository_root, B0_PATH, "P00 B0 公开接口快照", "b0_snapshot")
    frozen_hashes = {path: sha256_file(repository_root / path) for path in FROZEN_DOCS}
    records: list[P11FoundationCase] = [
        _base_case(
            record_id="p11-foundation-00-manifest",
            component="foundation_manifest",
            title="P11 Foundation 输入身份与未来 Runtime Binding 空槽",
            source=doc07,
            expected=[
                "冻结 9 个逻辑模板、5 个资源角色和 6 个逻辑模型 Profile",
                "P11 实际产物 Hash 在 P11 前保持空值",
            ],
            forbidden=["从未来实现反推 Hash", "把本工作包声明为 CP-DS0 正式 Gold"],
            foundation_contract=P11FoundationIdentityContract(
                frozen_document_hashes=frozen_hashes,
                b0_interface_snapshot_sha256=sha256_file(repository_root / B0_PATH),
                logical_template_ids=[item[0] for item in TEMPLATE_SPECS],
                physical_template_roles=list(PHYSICAL_ROLES),
                model_profile_ids=list(MODEL_PROFILES),
            ),
        )
    ]

    for index, (template_id, artifact_type, resource_roles) in enumerate(TEMPLATE_SPECS, 1):
        records.append(
            _base_case(
                record_id=f"p11-template-{index:02d}-{template_id.replace('_v1', '').replace('_', '-')}",
                component="template_contract",
                title=f"内置模板合同：{template_id}",
                source=doc05,
                expected=["Definition、Snapshot 及 Profile 引用字段完备", "资源角色与产物类型一致"],
                forbidden=["审核视觉质量或生成内容质量", "把模板资源 Hash 在 P11 实现前填成非空"],
                template_contract=P11TemplateContract(
                    template_id=template_id,
                    artifact_type=artifact_type,
                    input_schema_role=f"{artifact_type}_task_input",
                    output_schema_role=f"{artifact_type}_artifact_output",
                    planner_prompt_profile=f"{artifact_type}_planner",
                    generator_prompt_profile=f"{artifact_type}_generator",
                    validator_profile=f"{artifact_type}_validator",
                    repair_profile=f"{artifact_type}_repair",
                    model_route_profile="planner_main/generator_main/content_repair_main",
                    exporter_profile=f"{artifact_type}_exporter",
                    default_parameters=["由版本化 Definition 提供；Snapshot 固定后不可漂移"],
                    required_snapshot_fields=[
                        "template_id",
                        "template_version",
                        "definition_sha256",
                        "resource_sha256",
                        "prompt_profile_sha256",
                    ],
                    physical_resource_roles=list(resource_roles),
                ),
            )
        )

    model_specs: tuple[tuple[str, str, list[str], str], ...] = (
        (
            "main-light-same-model",
            "planner_main + classifier_light",
            [],
            "可解析到同一实际模型，但保留 requested profile",
        ),
        (
            "main-light-distinct-models",
            "generator_main + json_repair_light",
            [],
            "可解析到不同实际模型且路由确定",
        ),
        ("light-normal-route", "classifier_light", ["structured_output"], "不升级，使用 Light"),
        (
            "light-explicit-escalation",
            "json_repair_light",
            ["structured_output"],
            "能力不足时显式升级 Main 或明确失败",
        ),
        ("omit-unsupported-reasoning", "planner_main", [], "请求中完全省略 reasoning"),
        ("omit-unsupported-thinking", "generator_main", [], "请求中完全省略 thinking"),
        (
            "structured-output-capability",
            "classifier_light",
            [],
            "显式升级或能力错误，禁止伪装成功",
        ),
        (
            "timeout-no-silent-switch",
            "generator_main",
            ["timeout"],
            "记录 timeout 并按策略失败，不切模型",
        ),
        (
            "rate-limit-no-silent-switch",
            "generator_main",
            ["429"],
            "记录 429 并按策略失败，不切模型",
        ),
        (
            "invalid-json-no-fallback",
            "json_repair_light",
            ["invalid_json"],
            "显式 repair/失败，不用确定性 Fallback 掩盖",
        ),
        ("missing-usage-unknown", "planner_main", [], "usage/token/cost 保持 unknown"),
        (
            "formal-eval-integrity",
            "planner_main",
            ["formal_eval"],
            "禁止 Fallback、Secret Trace 和未记录 Profile 切换",
        ),
    )
    for index, (slug, profile, capabilities, resolution) in enumerate(model_specs, 1):
        records.append(
            _base_case(
                record_id=f"p11-model-{index:02d}-{slug}",
                component="model_gateway",
                title=f"Model Gateway 合同：{slug}",
                source=doc05,
                expected=[
                    resolution,
                    "Trace 保存 requested/resolved Profile、Capability 决策与错误分类",
                ],
                forbidden=[
                    "调用真实 Provider",
                    "静默切模、静默 Fallback 或编造 usage/cost",
                    "Secret 写入 Trace",
                ],
                model_gateway_contract=P11ModelGatewayContract(
                    requested_profile=profile,
                    fake_provider_capabilities=list(capabilities),
                    invocation_condition=slug.replace("-", " "),
                    expected_resolution=resolution,
                    expected_trace_fields=[
                        "requested_profile",
                        "resolved_profile",
                        "capability_decision",
                        "actual_model_or_unknown",
                        "usage_or_unknown",
                    ],
                ),
            )
        )

    runtime_specs = (
        (
            "stable-task-thread-identity",
            "稳定 Task/Thread 身份",
            "相同幂等键复用身份，不同键不碰撞",
        ),
        ("legal-state-transition", "合法 Typed State 转换", "只接受冻结状态机允许的迁移"),
        (
            "run-context-version-trace",
            "RunContext 版本追踪",
            "Git、模板、Prompt、模型及 CourseRAG 引用可追溯",
        ),
        ("invalid-state-rejected", "非法 State 拒绝", "缺字段或非法迁移 fail closed"),
        ("initial-artifact-version", "Artifact 初始版本", "首次创建得到版本 1 与确定性内容 Hash"),
        ("edit-creates-version", "编辑产生新 Artifact Version", "编辑创建新版本且旧版本不可变"),
        ("old-version-immutable", "旧 Artifact Version 不可变", "历史内容与 Hash 不被覆盖"),
        (
            "deterministic-safe-artifact-ref",
            "确定性 Hash 与安全 ArtifactRef",
            "相同内容 Hash 相同，Ref 无绝对路径或 Secret",
        ),
        ("template-snapshot-pinned", "模板 Snapshot 固定", "任务恢复继续使用原 Snapshot"),
        (
            "fingerprint-safe-reuse",
            "相同 Fingerprint 安全复用",
            "输入、配置和依赖相同才复用 NodeResult",
        ),
        (
            "fingerprint-input-change",
            "输入变化使 Fingerprint 失效",
            "任一身份输入变化均创建新 NodeRun",
        ),
        (
            "failed-node-not-reused",
            "失败或待审核 Node 不复用",
            "failed/waiting_review 结果不得当成功缓存",
        ),
        (
            "bounded-compaction",
            "有界 State Compaction",
            "保留 Artifact/Context Ref、Hash、必要摘要与错误",
        ),
        (
            "compaction-secret-exclusion",
            "Compaction 排除 Secret 与无界历史",
            "Checkpoint 不含凭据、大正文或无界消息历史",
        ),
        (
            "b0-compatibility",
            "P00 B0 公开兼容",
            "27 个 Route、3 条 Graph 和旧 Service 合同 Hash 级不变",
        ),
    )
    for index, (slug, title, expected) in enumerate(runtime_specs, 1):
        records.append(
            _base_case(
                record_id=f"p11-runtime-{index:02d}-{slug}",
                component="runtime",
                title=title,
                source=b0 if slug == "b0-compatibility" else doc07,
                expected=[expected],
                forbidden=["产生真实业务副作用", "使用未记录 Fallback", "修改公开 API 合同"],
            )
        )
    return records


def audit_p10_gate(repository_root: Path) -> P11P10GateAudit:
    execution = (repository_root / "docs/refactor/EXECUTION_STATUS.md").read_text(encoding="utf-8")
    frozen_path = repository_root / P10_FROZEN_PATH
    frozen = json.loads(frozen_path.read_text(encoding="utf-8"))
    lock = json.loads((repository_root / P10_LOCK_PATH).read_text(encoding="utf-8"))
    auth = json.loads((repository_root / P10_AUTH_PATH).read_text(encoding="utf-8"))
    decision_log = (repository_root / P10_D013_DECISION_PATH).read_text(encoding="utf-8")
    quality_policy = (repository_root / P10_D013_POLICY_PATH).read_text(encoding="utf-8")
    p10_3_report_path = repository_root / P10_3_REPORT_PATH
    p10_3_report = json.loads(p10_3_report_path.read_text(encoding="utf-8"))
    blind = json.loads((repository_root / P10_3_BLIND_PATH).read_text(encoding="utf-8"))
    frozen_file_sha = sha256_file(frozen_path)
    lock_file_sha = sha256_file(repository_root / P10_LOCK_PATH)
    qa_run = json.loads(
        (repository_root / "storage_eval/p10/formal/qa-run-1/run_manifest.json").read_text(
            encoding="utf-8"
        )
    )
    retrieval_run = json.loads(
        (repository_root / "storage_eval/p10/formal/retrieval-run-1/run_manifest.json").read_text(
            encoding="utf-8"
        )
    )
    report_paths = (
        repository_root / "storage_eval/p10/formal/qa-run-1/report.json",
        repository_root / "storage_eval/p10/formal/retrieval-run-1/report.json",
        repository_root / "storage_eval/p10/formal/component_test_report.json",
    )
    checks = [
        P11P10GateCheck(
            check_id="p10.d013.dependency_waiver",
            passed=(
                "P10-D013" in decision_log
                and "owner_approved_dependency_waiver_with_security_debt" in decision_log
                and "completed_with_isolated_security_capability_debt" in execution
                and any(
                    f"| P11 | {status}" in execution
                    for status in (
                        "ready_to_start",
                        "gate_pending_owner_snapshot_approval",
                        "completed",
                    )
                )
                and "Last amended: 2026-08-12 under owner-approved P10-D013" in quality_policy
            ),
            observed="P10-D013 owner waiver and a valid P11 lifecycle status are present",
            required="exact owner-approved P10-D013 dependency waiver remains authoritative",
        ),
        P11P10GateCheck(
            check_id="p10.d013.failed_profile_preserved",
            passed=(
                sha256_file(p10_3_report_path) == P10_3_REJECTED_REPORT_SHA256
                and p10_3_report.get("status") == "failed"
                and p10_3_report.get("selected_profile_sha256") is None
                and not (
                    repository_root / "storage_eval/p10_3_security/candidate_profile_r1.json"
                ).exists()
            ),
            observed=(
                f"report={sha256_file(p10_3_report_path)}, status={p10_3_report.get('status')}, "
                "profile_emitted=false"
            ),
            required="failed P10.3 report remains exact and no Profile is emitted",
        ),
        P11P10GateCheck(
            check_id="p10.d013.blind_unread",
            passed=(
                blind.get("content_visible_to_implementation") is False
                and blind.get("status") == "awaiting_independent_construction"
                and blind.get("bundle_sha256") is None
                and p10_3_report.get("blind_access") is False
            ),
            observed=(
                f"blind_status={blind.get('status')}, visible={blind.get('content_visible_to_implementation')}, "
                f"report_blind_access={p10_3_report.get('blind_access')}"
            ),
            required="P10.3 Blind content remains unbuilt, invisible and unread",
        ),
        P11P10GateCheck(
            check_id="p10.frozen_manifest.authorized",
            passed=(
                auth.get("locked") is True
                and auth.get("frozen_manifest_sha256") == frozen_file_sha
                and auth.get("owner_approval_sha256") == frozen_file_sha
            ),
            observed=f"authorization={auth.get('frozen_manifest_sha256')}, file={frozen_file_sha}",
            required="authorization and owner approval bind the exact Frozen Manifest",
        ),
        P11P10GateCheck(
            check_id="p10.lock.and.run.identity",
            passed=(
                lock.get("locked") is True
                and qa_run.get("dataset", {}).get("test_lock_sha256") == lock_file_sha
                and retrieval_run.get("dataset", {}).get("test_lock_sha256") == lock_file_sha
                and qa_run.get("dataset", {}).get("split_sha256") == frozen.get("test_ids_sha256")
                and retrieval_run.get("dataset", {}).get("split_sha256")
                == frozen.get("test_ids_sha256")
                and qa_run.get("configuration", {}).get("frozen_manifest_sha256") == frozen_file_sha
                and retrieval_run.get("configuration", {}).get("frozen_manifest_sha256")
                == frozen_file_sha
            ),
            observed=f"lock_file={lock_file_sha}, canonical_test_ids={lock.get('test_ids_sha256')}, split_file={frozen.get('test_ids_sha256')}, frozen={frozen_file_sha}",
            required="formal runs bind both Test identity layers and the exact Frozen Manifest",
        ),
        P11P10GateCheck(
            check_id="p10.formal_reports.complete",
            passed=all(path.is_file() for path in report_paths),
            observed=", ".join(
                f"{path.name}={'present' if path.is_file() else 'missing'}" for path in report_paths
            ),
            required="QA, retrieval and component final reports all present",
        ),
        P11P10GateCheck(
            check_id="p10.courserag_port.present",
            passed=(repository_root / P10_PORT_PATH).is_file(),
            observed=P10_PORT_PATH,
            required="CoursePilot CourseRAG consumer Port artifact exists",
        ),
    ]
    eligible = all(item.passed for item in checks)
    return P11P10GateAudit(
        eligible_for_full_candidate=eligible,
        checks=checks,
        deferred_record_ids=list(DEFERRED_IDS),
        disposition="eligible_for_candidate" if eligible else "fail_closed_draft_only",
        eligibility_basis="p10_d013_dependency_waiver",
        security_profile_status="candidate_rejected_default_off",
        p11_inherited_security_constraints=list(INHERITED_SECURITY_CONSTRAINTS),
    )


def _expected_ids(independent: list[P11FoundationCase]) -> list[str]:
    return [item.record_id for item in independent] + list(DEFERRED_IDS)


def _build_deferred_records(repository_root: Path) -> list[P11FoundationCase]:
    from courserag.evals.schemas import DS5RetrievalQADataset
    from evaluation.datasets import record_digest

    retrieval_path = repository_root / "datasets/courserag_eval/v1/approved/ds5/p08_retrieval.json"
    retrieval = DS5RetrievalQADataset.model_validate_json(
        retrieval_path.read_text(encoding="utf-8")
    )
    by_id = {item.record_id: item for item in retrieval.cases}
    source = _source(
        repository_root,
        retrieval_path.relative_to(repository_root).as_posix(),
        "Approved CourseRAG Dev Retrieval Gold；仅引用身份，不复制课程事实",
        "approved_dev_gold",
    )
    specs = (
        (
            DEFERRED_IDS[0],
            "DOCX Approved Dev Context 正常路径",
            "docx_dev",
            "gold-rq-09de7cd9d09de79322fcfdbc9b1aaae9",
        ),
        (
            DEFERRED_IDS[1],
            "PDF Approved Dev Context 正常路径",
            "pdf_dev",
            "gold-rq-8003dfb64c7c9f5399d50c4cc61af486",
        ),
    )
    records: list[P11FoundationCase] = []
    for record_id, title, scenario, query_id in specs:
        query = by_id.get(query_id)
        if query is None or query.split != "dev":
            raise ValueError(f"P11 Port fixture is not an Approved Dev query: {query_id}")
        records.append(
            P11FoundationCase(
                record_id=record_id,
                component="runtime",
                title=title,
                dependency="p10_d013_waiver",
                input_fixture=[
                    "Approved Dev Query 身份",
                    "固定 Fake CourseRAG Port ContextPackage",
                ],
                expected_behavior=[
                    "只经 CourseRAG Port 返回 ContextPackageRef",
                    "RunContext 保留 course/index/context/evidence/trace 版本引用",
                ],
                forbidden_behavior=[
                    "读取或枚举 Test/DS3 Holdout",
                    "直接导入 CourseRAG Parser、Chunker、Index 或 ORM",
                    "把模型输出当作 Gold",
                ],
                pass_conditions=[
                    "请求与响应通过冻结 Port Schema",
                    "Context/Evidence 引用可解析且课程一致",
                ],
                source_references=[source],
                courserag_contract=P11CourseRAGContract(
                    scenario=scenario,
                    dev_query_id=query_id,
                    expected_course_id=query.course_id,
                    approved_query_record_sha256=record_digest(query),
                    context_contract_version=sha256_file(repository_root / P10_PORT_PATH),
                    expected_context_fields=[
                        "purpose",
                        "course_id",
                        "index_version",
                        "evidence_refs",
                        "token_count",
                        "content_sha256",
                        "trace_id",
                    ],
                ),
            )
        )
    records.append(
        P11FoundationCase(
            record_id=DEFERRED_IDS[2],
            component="runtime",
            title="跨课程、过期或不可解析 Context/Evidence fail closed",
            dependency="p10_d013_waiver",
            input_fixture=["纯结构化、无课程事实的 cross_course/stale/unresolvable Fake 引用"],
            expected_behavior=[
                "返回稳定显式错误并保留安全 Trace",
                "不产生 Artifact、审批或外部调用副作用",
            ],
            forbidden_behavior=["跨课程回退", "猜测内容", "读取 Test/DS3 Holdout", "泄露 Secret"],
            pass_conditions=["三种结构故障均 fail closed", "故障响应不含新增课程事实"],
            source_references=[
                _source(
                    repository_root, P10_PORT_PATH, "冻结 CourseRAG consumer Port", "p10_contract"
                )
            ],
            courserag_contract=P11CourseRAGContract(
                scenario="fail_closed",
                context_contract_version=sha256_file(repository_root / P10_PORT_PATH),
                expected_context_fields=["error_code", "trace_id", "failed_reference_kind"],
            ),
        )
    )
    return records


def bundle_identity_sha256(
    *,
    candidate_sha256: str,
    record_sha256: dict[str, str],
    p10_frozen_sha256: str,
    p10_contract_sha256: str,
    p10_d013_decision_sha256: str,
    p10_d013_policy_sha256: str,
    p10_d013_status_sha256: str,
    p10_3_report_sha256: str,
    p10_3_blind_sha256: str,
) -> str:
    return identity_sha256(
        {
            "schema_version": "coursepilot.p11-foundation-bundle-identity.v1",
            "candidate_sha256": candidate_sha256,
            "candidate_record_sha256": record_sha256,
            "p10_frozen_manifest_sha256": p10_frozen_sha256,
            "p10_contract_sha256": p10_contract_sha256,
            "p10_d013_decision_sha256": p10_d013_decision_sha256,
            "p10_d013_policy_sha256": p10_d013_policy_sha256,
            "p10_d013_status_sha256": p10_d013_status_sha256,
            "p10_3_report_sha256": p10_3_report_sha256,
            "p10_3_blind_sha256": p10_3_blind_sha256,
            "p10_3_profile_emitted": False,
            "p10_3_blind_content_visible": False,
            "p10_3_runtime_default": "legacy_rules",
            "inherited_security_constraints": list(INHERITED_SECURITY_CONSTRAINTS),
            "first_review_ids": list(record_sha256),
            "second_review_ids": list(SECOND_REVIEW_IDS),
            "approval_scope": "p11_foundation_input_contract_only",
        }
    )


def _review_html(
    records: list[P11FoundationCase],
    bundle_sha256: str,
    review_ids: list[str],
    title: str,
    review_pass: str,
) -> str:
    by_id = {item.record_id: item for item in records}
    cards: list[str] = []
    for record_id in review_ids:
        item = by_id[record_id]
        payload = html.escape(
            json.dumps(item.model_dump(mode="json"), ensure_ascii=False, indent=2)
        )
        cards.append(
            f"<article><h2>{html.escape(item.record_id)}</h2><h3>{html.escape(item.title)}</h3>"
            f"<p><b>组件：</b>{item.component}　<b>依赖：</b>{item.dependency}</p>"
            f"<h4>输入</h4><ul>{''.join(f'<li>{html.escape(v)}</li>' for v in item.input_fixture)}</ul>"
            f"<h4>预期行为</h4><ul>{''.join(f'<li>{html.escape(v)}</li>' for v in item.expected_behavior)}</ul>"
            f"<h4>禁止行为</h4><ul>{''.join(f'<li>{html.escape(v)}</li>' for v in item.forbidden_behavior)}</ul>"
            f"<h4>通过条件</h4><ul>{''.join(f'<li>{html.escape(v)}</li>' for v in item.pass_conditions)}</ul>"
            f"<details><summary>完整合同 JSON 与依据 Hash</summary><pre>{payload}</pre></details>"
            f"<p><label><input type='radio' name='d-{record_id}' value='pass'>通过</label> "
            f"<label><input type='radio' name='d-{record_id}' value='return'>退回</label></p>"
            f"<textarea data-note='{record_id}' placeholder='退回原因/备注'></textarea></article>"
        )
    ids_json = json.dumps(review_ids, ensure_ascii=False)
    return (
        "<!doctype html><html lang='zh-CN'><meta charset='utf-8'><title>"
        + html.escape(title)
        + "</title><style>body{font-family:system-ui;max-width:1200px;margin:auto;padding:24px}"
        "article{border:1px solid #bbb;border-radius:8px;padding:18px;margin:16px 0}"
        "pre{white-space:pre-wrap}h4{margin-bottom:4px}textarea{width:100%;min-height:64px}"
        "button{padding:8px 16px}</style><h1>"
        + html.escape(title)
        + f"</h1><p>Bundle SHA-256: <code>{bundle_sha256}</code></p>"
        + "<p><label>审核人 <input id='reviewer' value='course_owner'></label></p>"
        + "".join(cards)
        + "<button id='export'>校验并导出审核 JSON</button><script>"
        + f"const ids={ids_json};const sha='{bundle_sha256}';const pass='{review_pass}';"
        + "document.getElementById('export').onclick=()=>{let decisions=[];for(const id of ids){"
        + 'const selected=document.querySelector(`input[name="d-${id}"]:checked`);'
        + "if(!selected){alert('尚未审核：'+id);return;}const note=document.querySelector(`[data-note=\"${id}\"]`).value.trim();"
        + "if(selected.value==='return'&&!note){alert('退回必须填写原因：'+id);return;}"
        + "decisions.push({record_id:id,decision:selected.value,notes:note});}"
        + "const reviewer=document.getElementById('reviewer').value.trim();if(!reviewer){alert('请填写审核人');return;}"
        + "const payload={schema_version:'coursepilot.p11-foundation-review-decisions.v1',bundle_sha256:sha,"
        + "review_pass:pass,expected_record_ids:ids,decisions:decisions,reviewer_id:reviewer,reviewed_at:new Date().toISOString()};"
        + "const a=document.createElement('a');a.href=URL.createObjectURL(new Blob([JSON.stringify(payload,null,2)],{type:'application/json'}));"
        + "a.download=`p11_${pass}_review_${sha.slice(0,12)}.json`;a.click();URL.revokeObjectURL(a.href);};</script></html>\n"
    )


def compile_candidate(
    repository_root: Path,
    draft: P11FoundationDraftDataset,
    gate: P11P10GateAudit,
) -> dict[str, object]:
    if not gate.eligible_for_full_candidate:
        raise ValueError("P10-D013 dependency waiver is not valid; P11 Candidate is fail closed")
    records = list(draft.records)
    foundation = records[0]
    contract = foundation.foundation_contract
    if contract is None:
        raise ValueError("P11 Foundation Manifest contract is absent")
    records[0] = foundation.model_copy(
        update={
            "foundation_contract": contract.model_copy(
                update={
                    "p10_frozen_manifest_sha256": sha256_file(repository_root / P10_FROZEN_PATH),
                    "p10_contract_sha256": sha256_file(repository_root / P10_PORT_PATH),
                }
            )
        }
    )
    records.extend(_build_deferred_records(repository_root))
    candidate = P11FoundationCandidateDataset(records=records)
    candidate_path = repository_root / CANDIDATE_PATH
    atomic_write_json(candidate_path, candidate.model_dump(mode="json"))
    record_hashes = {
        item.record_id: identity_sha256(item.model_dump(mode="json")) for item in records
    }
    candidate_sha = sha256_file(candidate_path)
    frozen_sha = sha256_file(repository_root / P10_FROZEN_PATH)
    contract_sha = sha256_file(repository_root / P10_PORT_PATH)
    decision_sha = sha256_file(repository_root / P10_D013_DECISION_PATH)
    policy_sha = sha256_file(repository_root / P10_D013_POLICY_PATH)
    status_sha = sha256_file(repository_root / P10_D013_STATUS_PATH)
    rejected_report_sha = sha256_file(repository_root / P10_3_REPORT_PATH)
    blind_sha = sha256_file(repository_root / P10_3_BLIND_PATH)
    bundle_sha = bundle_identity_sha256(
        candidate_sha256=candidate_sha,
        record_sha256=record_hashes,
        p10_frozen_sha256=frozen_sha,
        p10_contract_sha256=contract_sha,
        p10_d013_decision_sha256=decision_sha,
        p10_d013_policy_sha256=policy_sha,
        p10_d013_status_sha256=status_sha,
        p10_3_report_sha256=rejected_report_sha,
        p10_3_blind_sha256=blind_sha,
    )
    review_root = repository_root / f"storage_eval/p11_foundation_review/{bundle_sha}"
    atomic_write_text(
        review_root / "index.html",
        _review_html(
            records,
            bundle_sha,
            [item.record_id for item in records],
            "P11 Foundation 首轮审核（40 条）",
            "first",
        ),
    )
    atomic_write_text(
        review_root / "second_review.html",
        _review_html(
            records,
            bundle_sha,
            list(SECOND_REVIEW_IDS),
            "P11 Foundation 二轮盲化审核（27 条）",
            "second",
        ),
    )
    manifest = P11CandidateBundleManifest(
        bundle_sha256=bundle_sha,
        predecessor_draft_sha256=sha256_file(repository_root / DRAFT_PATH),
        candidate=_artifact(repository_root, CANDIDATE_PATH),
        candidate_record_sha256=record_hashes,
        first_review_ids=[item.record_id for item in records],
        second_review_ids=list(SECOND_REVIEW_IDS),
        review_pack_relative_path=review_root.relative_to(repository_root).as_posix(),
        review_pack_index_sha256=sha256_file(review_root / "index.html"),
        second_review_index_sha256=sha256_file(review_root / "second_review.html"),
        p10_frozen_manifest=_artifact(repository_root, Path(P10_FROZEN_PATH)),
        p10_contract=_artifact(repository_root, Path(P10_PORT_PATH), "text/x-python"),
        p10_d013_decision_log=_artifact(
            repository_root, Path(P10_D013_DECISION_PATH), "text/markdown"
        ),
        p10_d013_quality_policy=_artifact(
            repository_root, Path(P10_D013_POLICY_PATH), "text/markdown"
        ),
        p10_d013_execution_status=_artifact(
            repository_root, Path(P10_D013_STATUS_PATH), "text/markdown"
        ),
        p10_3_failed_profile_report=_artifact(repository_root, Path(P10_3_REPORT_PATH)),
        p10_3_blind_commitment=_artifact(repository_root, Path(P10_3_BLIND_PATH)),
        inherited_security_constraints=list(INHERITED_SECURITY_CONSTRAINTS),
    )
    atomic_write_json(repository_root / CANDIDATE_MANIFEST_PATH, manifest.model_dump(mode="json"))
    return {
        "bundle_sha256": bundle_sha,
        "candidate_sha256": candidate_sha,
        "record_count": 40,
    }


def _write_current_report(
    repository_root: Path,
    gate: P11P10GateAudit,
    result: dict[str, object],
) -> None:
    candidate_state = (
        f"已生成 40 条 Candidate；Bundle `{result['bundle_sha256']}`"
        if result["candidate_generated"]
        else "未生成；仍为 37 条 Draft"
    )
    report = (
        f"""# ED-PRE11 P11 Foundation Input 工作包报告

## 当前结果

- 依赖判断：`{gate.disposition}`，依据 `{gate.eligibility_basis}`。
- 独立 Draft：37 条（1 Foundation、9 Template、12 Model Gateway、15 Runtime）。
- 完整 Candidate：{candidate_state}。
- CoursePilot 正式 Gold：未生成，`gold_status=skeleton_no_formal_gold`。
- P10.3 安全 Profile：`candidate_rejected_default_off`，失败报告未改写为通过。

## 文件

- Draft：`{DRAFT_PATH.as_posix()}`
- Candidate：`{CANDIDATE_PATH.as_posix()}`
- Candidate Manifest：`{CANDIDATE_MANIFEST_PATH.as_posix()}`
- P10 Gate/Waiver Audit：`{GATE_AUDIT_PATH.as_posix()}`

## P10-D013 精确检查

"""
        + "\n".join(
            f"- {'PASS' if check.passed else 'FAIL'} `{check.check_id}`：{check.observed}；要求：{check.required}"
            for check in gate.checks
        )
        + """

## 继承的安全边界

"""
        + "\n".join(f"- `{item}`" for item in INHERITED_SECURITY_CONSTRAINTS)
        + """

## 审批边界

完整 Candidate 仍为待审核状态。审批只会提升为 P11 实施输入工作包，不构成 CP-DS0—8
正式 Gold；Dev/Test 继续为空，CoursePilot Test 继续未锁定。P10.3 Blind 未构建、未读取，
失败候选无 Profile 且 Runtime 默认仍为 `legacy_rules`。

本批没有修改产品 HTTP API、业务数据库、迁移、运行配置或三条业务 Graph。
"""
    )
    atomic_write_text(repository_root / REPORT_PATH, report)


def generate_draft(repository_root: Path) -> dict[str, object]:
    repository_root = repository_root.resolve()
    independent = build_independent_records(repository_root)
    draft = P11FoundationDraftDataset(records=independent)
    gate = audit_p10_gate(repository_root)
    atomic_write_json(repository_root / DRAFT_PATH, draft.model_dump(mode="json"))
    atomic_write_json(repository_root / GATE_AUDIT_PATH, gate.model_dump(mode="json"))
    strategy = {
        "task_ids": [f"ED-PRE11-FOUNDATION-T{index:02d}" for index in range(1, 8)],
        "target_distribution": {
            "foundation_manifest": 1,
            "template_contract": 9,
            "model_gateway": 12,
            "runtime": 18,
        },
        "deferred_ids": list(DEFERRED_IDS),
        "second_review_ids": list(SECOND_REVIEW_IDS),
        "rules": [
            "draft_is_not_candidate",
            "p10_gate_fail_closed",
            "no_provider_or_database_calls",
            "no_formal_cp_gold",
        ],
    }
    manifest = P11DraftBundleManifest(
        expected_record_ids=_expected_ids(independent),
        present_record_ids=[item.record_id for item in independent],
        missing_record_ids=list(DEFERRED_IDS),
        draft_artifact=_artifact(repository_root, DRAFT_PATH),
        generation_strategy_sha256=identity_sha256(strategy),
        p10_gate_audit=_artifact(repository_root, GATE_AUDIT_PATH),
    )
    atomic_write_json(repository_root / DRAFT_MANIFEST_PATH, manifest.model_dump(mode="json"))
    report = (
        f"""# ED-PRE11 P11 Foundation Input 工作包报告

## 当前结果

- 状态：`{gate.disposition}`
- 已生成：37 条独立 Draft（1 Foundation Manifest、9 Template Contract、12 Model Gateway、15 Runtime）
- 已延后：3 条 CourseRAG Port/Context 记录
- 正式 Candidate：未生成
- 可审批 Bundle SHA-256：未生成
- CoursePilot 正式 Gold：未生成，`gold_status=skeleton_no_formal_gold`

## 文件

- Draft：`{DRAFT_PATH.as_posix()}`
- Draft Manifest：`{DRAFT_MANIFEST_PATH.as_posix()}`
- P10 Gate Audit：`{GATE_AUDIT_PATH.as_posix()}`

## Fail-closed 原因

"""
        + "\n".join(
            f"- {'PASS' if check.passed else 'FAIL'} `{check.check_id}`：{check.observed}；要求：{check.required}"
            for check in gate.checks
        )
        + """

## 审批边界

本 Draft 不是 Candidate，不能人工审批或提升。只有 P10 Exit Gate 通过，且 Test Lock、最终报告、Frozen Manifest 和 CourseRAG Port 身份一致后，生成器才允许补齐 3 条记录并产生 40 条 Candidate、两轮审核页和精确 Bundle SHA-256。

本批没有修改产品 HTTP API、业务数据库、运行配置、三条业务 Graph、CoursePilot Dev/Test 或 Test Lock。
"""
    )
    if not gate.eligible_for_full_candidate:
        atomic_write_text(repository_root / REPORT_PATH, report)
    result: dict[str, object] = {
        "draft_sha256": sha256_file(repository_root / DRAFT_PATH),
        "draft_manifest_sha256": sha256_file(repository_root / DRAFT_MANIFEST_PATH),
        "present_records": len(independent),
        "missing_records": list(DEFERRED_IDS),
        "candidate_generated": False,
        "p10_eligible": gate.eligible_for_full_candidate,
    }
    if gate.eligible_for_full_candidate:
        result.update(compile_candidate(repository_root, draft, gate))
        result["candidate_generated"] = True
    _write_current_report(repository_root, gate, result)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository-root", type=Path, default=Path("."))
    args = parser.parse_args()
    result = generate_draft(args.repository_root)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
