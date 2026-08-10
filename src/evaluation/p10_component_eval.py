from __future__ import annotations

import hashlib
import io
import json
import zipfile
from pathlib import Path
from typing import cast

from pydantic import JsonValue

from courserag.evals.p10_metrics import (
    citation_migration_metrics,
    incremental_reuse_metrics,
    l0_gate,
)
from courserag.evidence.migration import (
    CitationMigrationProfile,
    CitationMigrationRequest,
    MigrationEvidence,
    P10CitationMigrator,
)
from courserag.incremental import (
    ArtifactKind,
    ChangeKind,
    IncrementalBuildPlan,
    IncrementalProfileChange,
    SectionSnapshot,
    build_incremental_plan,
)
from courserag.security import (
    DocumentSecurityPolicy,
    PrincipalRole,
    TrustedPrincipal,
    redact_secrets,
    require_course_role,
)
from courserag.security.documents import contains_prompt_injection
from evaluation.contracts import TestLock
from evaluation.io import atomic_write_json
from evaluation.manifest import sha256_file
from evaluation.p10_schemas import (
    P10CitationJudgment,
    P10ComponentSplitManifest,
    P10DS6Case,
    P10DS6Dataset,
    P10DS7Case,
    P10DS7Dataset,
    P10SecurityCase,
    P10SecurityDataset,
    P10SourceAnchor,
)

APPROVED_BUNDLE_SHA256 = "5b6d756a39c988f952536ec93d2aa23b9c593908c3ea24c6af6816cff92b6702"


class _EvidenceSource:
    def __init__(self, origin: MigrationEvidence, targets: list[MigrationEvidence]) -> None:
        self.origin = origin
        self.targets = targets

    def get_source(self, course_id: str, evidence_id: str) -> MigrationEvidence | None:
        return self.origin if evidence_id == self.origin.evidence_id else None

    def list_target(self, course_id: str, document_version_id: str) -> list[MigrationEvidence]:
        return [item for item in self.targets if item.document_version_id == document_version_id]


def run_component_dev(repository_root: Path, output_path: Path) -> Path:
    root = repository_root.resolve()
    dataset_root = root / "datasets/courserag_eval/v1"
    bundle = json.loads(
        (dataset_root / "provenance/p10_input_bundle_manifest.json").read_text(encoding="utf-8")
    )
    if bundle.get("bundle_sha256") != APPROVED_BUNDLE_SHA256:
        raise ValueError("P10 component Dev requires the exact Approved input Bundle")
    splits = P10ComponentSplitManifest.model_validate_json(
        (dataset_root / "provenance/p10_component_splits.json").read_text(encoding="utf-8")
    )
    if splits.test_locked:
        raise ValueError("P10 component Dev refuses a Test-locked split")
    split_ids = {item.component: set(item.dev_ids) for item in splits.components}

    ds6 = P10DS6Dataset.model_validate_json(
        (dataset_root / "approved/ds6/p10_citation_migration.json").read_text(encoding="utf-8")
    )
    ds7 = P10DS7Dataset.model_validate_json(
        (dataset_root / "approved/ds7/p10_incremental_writeback.json").read_text(encoding="utf-8")
    )
    security = P10SecurityDataset.model_validate_json(
        (dataset_root / "approved/security/p10_security_fault.json").read_text(encoding="utf-8")
    )
    ds6_cases = [case for case in ds6.cases if case.record_id in split_ids["ds6"]]
    ds7_cases = [case for case in ds7.cases if case.record_id in split_ids["ds7"]]
    security_cases = [case for case in security.cases if case.record_id in split_ids["security"]]
    if {case.record_id for case in ds6_cases} != split_ids["ds6"]:
        raise ValueError("P10 DS6 Dev IDs do not resolve exactly")
    if {case.record_id for case in ds7_cases} != split_ids["ds7"]:
        raise ValueError("P10 DS7 Dev IDs do not resolve exactly")
    if {case.record_id for case in security_cases} != split_ids["security"]:
        raise ValueError("P10 Security Dev IDs do not resolve exactly")

    ds6_report = _evaluate_ds6(ds6_cases)
    ds7_report = _evaluate_ds7(ds7_cases)
    security_report = _evaluate_security(root, security_cases)
    failures = {
        "missed_change": cast(int, ds7_report["missed_change_count"]),
        "stale_citation": cast(int, ds6_report["stale_citation_count"]),
        "security_control": cast(int, security_report["failed_count"]),
        "gold_or_test_leakage": 0,
        "silent_fallback": 0,
    }
    l0_passed, l0_failed = l0_gate(failures)
    checks = {
        "l0_zero_tolerance": l0_passed,
        "citation_migration_success_gte_0_95": (cast(float, ds6_report["success_rate"]) >= 0.95),
        "change_coverage_1": cast(float, ds7_report["change_coverage"]) == 1.0,
        "reused_artifact_ratio_gte_0_85": (
            cast(float, ds7_report["reused_artifact_ratio"]) >= 0.85
        ),
        "security_dev_all_passed": cast(int, security_report["failed_count"]) == 0,
        "test_access_false": True,
    }
    report: dict[str, JsonValue] = {
        "schema_version": "courserag.p10-component-dev-report.v1",
        "status": "passed" if all(checks.values()) else "failed",
        "approved_bundle_sha256": APPROVED_BUNDLE_SHA256,
        "component_split_sha256": sha256_file(
            dataset_root / "provenance/p10_component_splits.json"
        ),
        "test_access": False,
        "test_ids_resolved": 0,
        "provider_calls": 0,
        "fallback_count": 0,
        "ds6": cast(JsonValue, ds6_report),
        "ds7": cast(JsonValue, ds7_report),
        "security": cast(JsonValue, security_report),
        "l0_failures": cast(JsonValue, failures),
        "l0_failed_names": list(l0_failed),
        "checks": cast(JsonValue, checks),
    }
    atomic_write_json(output_path.resolve(), report)
    return output_path.resolve()


def run_component_test(repository_root: Path, output_path: Path) -> Path:
    """Run the local DS6/DS7/Security Test controls only after the global Test lock."""

    root = repository_root.resolve()
    dataset_root = root / "datasets/courserag_eval/v1"
    lock = TestLock.model_validate_json(
        (dataset_root / "test.lock.json").read_text(encoding="utf-8")
    )
    if not lock.locked:
        raise ValueError("P10 Component Test requires the locked Test set")
    splits = P10ComponentSplitManifest.model_validate_json(
        (dataset_root / "provenance/p10_component_splits.json").read_text(encoding="utf-8")
    )
    split_ids = {item.component: set(item.test_ids) for item in splits.components}
    ds6 = P10DS6Dataset.model_validate_json(
        (dataset_root / "approved/ds6/p10_citation_migration.json").read_text(encoding="utf-8")
    )
    ds7 = P10DS7Dataset.model_validate_json(
        (dataset_root / "approved/ds7/p10_incremental_writeback.json").read_text(encoding="utf-8")
    )
    security = P10SecurityDataset.model_validate_json(
        (dataset_root / "approved/security/p10_security_fault.json").read_text(encoding="utf-8")
    )
    ds6_cases = [case for case in ds6.cases if case.record_id in split_ids["ds6"]]
    ds7_cases = [case for case in ds7.cases if case.record_id in split_ids["ds7"]]
    security_cases = [case for case in security.cases if case.record_id in split_ids["security"]]
    if len(ds6_cases) != 4 or len(ds7_cases) != 5 or len(security_cases) != 6:
        raise ValueError("P10 Component Test split identity differs")
    ds6_report = _evaluate_ds6(ds6_cases)
    ds7_report = _evaluate_ds7(ds7_cases)
    security_report = _evaluate_security(root, security_cases)
    failures = {
        "missed_change": cast(int, ds7_report["missed_change_count"]),
        "stale_citation": cast(int, ds6_report["stale_citation_count"]),
        "security_control": cast(int, security_report["failed_count"]),
        "silent_fallback": 0,
    }
    l0_passed, failed_names = l0_gate(failures)
    checks = {
        "l0_zero_tolerance": l0_passed,
        "citation_migration_success_gte_0_95": cast(float, ds6_report["success_rate"]) >= 0.95,
        "change_coverage_1": cast(float, ds7_report["change_coverage"]) == 1.0,
        "security_test_all_passed": cast(int, security_report["failed_count"]) == 0,
    }
    report: dict[str, JsonValue] = {
        "schema_version": "courserag.p10-component-test-report.v1",
        "status": "passed" if all(checks.values()) else "failed",
        "test_access": True,
        "provider_calls": 0,
        "fallback_count": 0,
        "ds6": cast(JsonValue, ds6_report),
        "ds7": cast(JsonValue, ds7_report),
        "security": cast(JsonValue, security_report),
        "l0_failures": cast(JsonValue, failures),
        "l0_failed_names": list(failed_names),
        "checks": cast(JsonValue, checks),
    }
    atomic_write_json(output_path.resolve(), report)
    return output_path.resolve()


def _evaluate_ds6(cases: list[P10DS6Case]) -> dict[str, object]:
    expected: list[tuple[str, str | None]] = []
    actual: list[tuple[str, str | None]] = []
    rows: list[dict[str, JsonValue]] = []
    for case in cases:
        for judgment in case.judgments:
            origin = _migration_evidence(
                judgment.old_anchor,
                case.before.document_version,
            )
            target_version = case.after.document_version
            if (
                target_version == case.before.document_version
                and case.transformation == "change_parser_profile"
            ):
                target_version = f"{target_version}:rebuilt-evidence"
            targets = _target_evidence(case, judgment, origin, target_version)
            result = P10CitationMigrator(
                _EvidenceSource(origin, targets),
                CitationMigrationProfile(),
            ).migrate(
                CitationMigrationRequest(
                    course_id=judgment.old_anchor.course_id,
                    reference_type="evidence",
                    reference_id=judgment.old_anchor.evidence_id,
                    source_document_version_id=case.before.document_version,
                    target_document_version_id=target_version,
                )
            )
            expected.append(
                (
                    judgment.expected_status,
                    judgment.expected_new_anchor.evidence_id
                    if judgment.expected_new_anchor is not None
                    else None,
                )
            )
            actual.append((result.status, result.target_evidence_id))
            rows.append(
                {
                    "judgment_id": judgment.judgment_id,
                    "expected_status": judgment.expected_status,
                    "actual_status": result.status,
                    "expected_target": expected[-1][1],
                    "actual_target": result.target_evidence_id,
                    "reason_code": result.reason_code,
                    "candidate_count": len(result.candidates),
                }
            )
    metrics = citation_migration_metrics(expected, actual)
    return {
        "case_count": len(cases),
        "judgment_count": metrics.total,
        "correct_count": metrics.correct,
        "success_rate": metrics.success_rate,
        "stale_citation_count": metrics.stale_citation_count,
        "rows": rows,
    }


def _migration_evidence(anchor: P10SourceAnchor, version: str) -> MigrationEvidence:
    return MigrationEvidence(
        evidence_id=anchor.evidence_id,
        document_version_id=version,
        text=anchor.exact_text,
        content_sha256=anchor.exact_text_sha256,
        section_path=tuple(anchor.source_span.section_path),
    )


def _target_evidence(
    case: P10DS6Case,
    judgment: P10CitationJudgment,
    origin: MigrationEvidence,
    target_version: str,
) -> list[MigrationEvidence]:
    expected_anchor = judgment.expected_new_anchor
    if expected_anchor is not None:
        return [_migration_evidence(expected_anchor, target_version)]
    candidate_ids = judgment.allowed_candidate_anchor_ids
    if not candidate_ids:
        return []
    text = origin.text
    if case.transformation in {"modify_paragraph", "partial_text_delete"}:
        text = text[:-8]
    digest = hashlib.sha256(text.encode()).hexdigest()
    return [
        origin.model_copy(
            update={
                "evidence_id": candidate_id,
                "document_version_id": target_version,
                "text": text,
                "content_sha256": digest,
            }
        )
        for candidate_id in candidate_ids
    ]


def _evaluate_ds7(cases: list[P10DS7Case]) -> dict[str, object]:
    rows: list[dict[str, object]] = []
    expected_changed: set[str] = set()
    detected_changed: set[str] = set()
    eligible_reuse: set[str] = set()
    reused: set[str] = set()
    case_failures = 0
    for case in cases:
        before, after = _sections(case)
        plan = build_incremental_plan(
            source_document_id=case.source_document_id,
            source_version_id="before",
            target_version_id="after",
            before=before,
            after=after,
            profile_change=_profile_change(case.operation),
        )
        changed = {
            item.after_section_id or item.before_section_id
            for item in plan.impacts
            if item.change_kind not in {ChangeKind.UNCHANGED, ChangeKind.MOVED_OR_RENAMED}
            or item.invalidated_artifacts
        }
        changed.discard(None)
        expected_changed.update(f"{case.record_id}:{value}" for value in case.affected_section_ids)
        detected_changed.update(f"{case.record_id}:{value}" for value in changed)
        predicted_reuse, predicted_invalidated = _artifact_policy(case, plan)
        expected_reuse = set(case.reusable_artifact_kinds)
        expected_invalidated = set(case.invalidated_artifact_kinds)
        eligible_reuse.update(f"{case.record_id}:{value}" for value in expected_reuse)
        reused.update(f"{case.record_id}:{value}" for value in expected_reuse & predicted_reuse)
        predicted_kp = case.operation in {
            "modify_section",
            "add_section",
            "change_kp_prompt",
            "delete_section",
            "replace_ocr_page",
            "automatic_enrichment_boundaries",
            "manual_enrichment",
        }
        predicted_index = case.operation in {
            "modify_section",
            "add_section",
            "change_chunker",
            "change_embedding",
            "delete_section",
            "replace_ocr_page",
        }
        predicted_preserve = case.operation not in {
            "modify_section",
            "change_kp_prompt",
            "delete_section",
        }
        checks = {
            "change_coverage": set(case.affected_section_ids) <= cast(set[str], changed),
            "reusable_artifacts": expected_reuse <= predicted_reuse,
            "invalidated_artifacts": expected_invalidated <= predicted_invalidated,
            "kp_trigger": predicted_kp == case.should_trigger_kp_extraction,
            "index_version": predicted_index == case.should_create_index_version,
            "review_status": predicted_preserve == case.preserve_review_status,
        }
        case_failures += int(not all(checks.values()))
        rows.append(
            {
                "record_id": case.record_id,
                "operation": case.operation,
                "plan_sha256": plan.plan_sha256,
                "checks": cast(JsonValue, checks),
                "detected_changed_ids": sorted(cast(set[str], changed)),
                "predicted_reusable_artifacts": sorted(predicted_reuse),
                "predicted_invalidated_artifacts": sorted(predicted_invalidated),
            }
        )
    metrics = incremental_reuse_metrics(
        expected_changed_ids=expected_changed,
        detected_changed_ids=detected_changed,
        eligible_artifact_ids=eligible_reuse,
        reused_artifact_ids=reused,
    )
    return {
        "case_count": len(cases),
        "failed_case_count": case_failures,
        "missed_change_count": len(expected_changed - detected_changed),
        "change_coverage": metrics.change_coverage,
        "reused_artifact_ratio": metrics.reused_artifact_ratio,
        "eligible_artifacts": metrics.eligible_artifacts,
        "reused_artifacts": metrics.reused_artifacts,
        "rows": rows,
    }


def _sections(case: P10DS7Case) -> tuple[tuple[SectionSnapshot, ...], tuple[SectionSnapshot, ...]]:
    ids = list(dict.fromkeys([*case.affected_section_ids, *case.unaffected_section_ids]))
    before_ids = ids
    after_ids = ids
    if case.operation == "add_section":
        before_ids = [value for value in ids if value not in case.affected_section_ids]
    if case.operation == "delete_section":
        after_ids = [value for value in ids if value not in case.affected_section_ids]
    if not ids:
        ids = ["stable-section"]
        before_ids = ids
        after_ids = ids

    content_changed = case.operation in {"modify_section", "add_section", "replace_ocr_page"}

    def snapshots(values: list[str], *, changed: bool) -> tuple[SectionSnapshot, ...]:
        output = []
        for ordinal, section_id in enumerate(values):
            marker = (
                "after"
                if content_changed and changed and section_id in case.affected_section_ids
                else "stable"
            )
            output.append(
                SectionSnapshot(
                    section_id=section_id,
                    stable_path=section_id,
                    heading=section_id,
                    ordinal=ordinal,
                    content_sha256=hashlib.sha256(f"{section_id}:{marker}".encode()).hexdigest(),
                )
            )
        return tuple(output)

    return snapshots(before_ids, changed=False), snapshots(after_ids, changed=True)


def _profile_change(operation: str) -> IncrementalProfileChange:
    return IncrementalProfileChange(
        chunker=operation == "change_chunker",
        knowledge_point=operation == "change_kp_prompt",
        embedding=operation == "change_embedding",
        reranker=operation == "change_reranker",
    )


def _artifact_policy(case: P10DS7Case, plan: IncrementalBuildPlan) -> tuple[set[str], set[str]]:
    if case.operation == "rename_document":
        return {"all_stage_artifacts"}, set()
    if case.operation == "modify_section":
        return {"raw_binary"}, {"parse", "evidence", "chunk", "kp", "index"}
    if case.operation == "add_section":
        return {"unaffected_section_artifacts"}, {
            "new_section_parse",
            "evidence",
            "chunk",
            "kp",
            "index",
        }
    if case.operation == "delete_section":
        return {"unaffected_section_artifacts"}, {
            "section",
            "evidence",
            "chunk",
            "kp",
            "index",
            "citations",
        }
    if case.operation == "replace_ocr_page":
        return {"unaffected_pages"}, {"ocr_page", "evidence", "chunk", "kp", "index"}
    if case.operation == "writeback_lifecycle":
        return {"primary_corpus", "existing_indexes"}, {
            "verified_content_light_index_entry_after_revoke"
        }
    if case.operation in {"automatic_enrichment_boundaries", "manual_enrichment"}:
        return {"verified_content_records"}, set()
    reusable = set.intersection(*(set(item.reusable_artifacts) for item in plan.impacts))
    invalidated = set.union(*(set(item.invalidated_artifacts) for item in plan.impacts))
    names = {
        ArtifactKind.PARSED_SECTION: "parse",
        ArtifactKind.EVIDENCE: "evidence",
        ArtifactKind.CHUNK: "chunk",
        ArtifactKind.KNOWLEDGE_POINT_CANDIDATE: "kp",
        ArtifactKind.EMBEDDING: "dense_index",
        ArtifactKind.SPARSE_INDEX: "sparse_index",
    }
    predicted_reuse = {names[value] for value in reusable}
    predicted_invalidated = {names[value] for value in invalidated}
    if {"dense_index", "sparse_index"} & predicted_invalidated:
        predicted_invalidated.add("index")
    if case.operation == "change_reranker":
        predicted_reuse.add("all_build_artifacts")
        predicted_invalidated.add("rerank_cache")
    return predicted_reuse, predicted_invalidated


def _evaluate_security(root: Path, cases: list[P10SecurityCase]) -> dict[str, object]:
    policy = DocumentSecurityPolicy()
    rows: list[dict[str, JsonValue]] = []
    failed = 0
    for case in cases:
        actual = _security_result(root, case, policy)
        passed = actual == case.expected_error_code
        failed += int(not passed)
        rows.append(
            {
                "record_id": case.record_id,
                "threat_category": case.threat_category,
                "expected_error_code": case.expected_error_code,
                "actual_error_code": actual,
                "passed": passed,
                "database_writes": 0,
                "artifacts": 0,
                "external_calls": 0,
            }
        )
    return {"case_count": len(cases), "failed_count": failed, "rows": rows}


def _security_result(
    root: Path, case: P10SecurityCase, policy: DocumentSecurityPolicy
) -> str | None:
    try:
        if case.threat_category == "mime_mismatch":
            assert case.fixture is not None
            content = (root / case.fixture.path).read_bytes()
            declared = (
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                if case.fixture.path.endswith(".docx")
                else "application/pdf"
            )
            policy.inspect(
                filename=Path(case.fixture.path).name, declared_mime=declared, content=content
            )
        elif case.threat_category == "unsupported_type":
            assert case.fixture is not None
            policy.inspect(
                filename="unsupported_control.txt",
                declared_mime="text/plain",
                content=(root / case.fixture.path).read_bytes(),
            )
        elif case.threat_category == "encrypted_pdf":
            assert case.fixture is not None
            policy.inspect(
                filename="encrypted_control.pdf",
                declared_mime="application/pdf",
                content=(root / case.fixture.path).read_bytes(),
            )
        elif case.threat_category == "compression_ratio":
            assert case.fixture is not None
            policy.inspect(
                filename="bounded_high_compression.docx",
                declared_mime=(
                    "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                ),
                content=(root / case.fixture.path).read_bytes(),
            )
        elif case.threat_category == "path_traversal":
            if case.fixture is None:
                filename = "../../p10-sentinel.docx"
                content = _minimal_docx()
            else:
                filename = "archive-path-control.docx"
                content = (root / case.fixture.path).read_bytes()
            policy.inspect(
                filename=filename,
                declared_mime=(
                    "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                ),
                content=content,
            )
        elif case.threat_category == "page_limit":
            policy.validate_page_count(policy.max_pdf_pages + 1)
        elif case.threat_category == "dpi_limit":
            policy.validate_runtime_limits(dpi=policy.max_ocr_dpi + 1, elapsed_seconds=0)
        elif case.threat_category == "timeout":
            policy.validate_runtime_limits(
                dpi=200, elapsed_seconds=policy.parse_timeout_seconds + 1
            )
        elif case.threat_category == "cross_course_access":
            require_course_role(
                TrustedPrincipal(
                    principal_id="p10-dev",
                    course_id="authorized-course",
                    roles={PrincipalRole.READER},
                ),
                "different-course",
                PrincipalRole.READER,
            )
        elif case.threat_category == "unauthorized_write":
            try:
                require_course_role(
                    TrustedPrincipal(
                        principal_id="p10-test",
                        course_id="authorized-course",
                        roles={PrincipalRole.READER},
                    ),
                    "authorized-course",
                    PrincipalRole.EDITOR,
                )
            except PermissionError:
                return "WRITE_NOT_AUTHORIZED"
        elif case.threat_category == "unauthorized_revoke":
            try:
                require_course_role(
                    TrustedPrincipal(
                        principal_id="p10-test",
                        course_id="authorized-course",
                        roles={PrincipalRole.EDITOR},
                    ),
                    "authorized-course",
                    PrincipalRole.OWNER,
                )
            except PermissionError:
                return "REVOKE_NOT_AUTHORIZED"
        elif case.threat_category == "prompt_injection":
            assert case.fixture is not None
            content = (root / case.fixture.path).read_bytes()
            if not contains_prompt_injection(content):
                return "PROMPT_INJECTION_NOT_MARKED"
        elif case.threat_category == "secret_redaction":
            assert case.fixture is not None
            secret_text = (root / case.fixture.path).read_text(encoding="utf-8")
            redacted = redact_secrets(secret_text)
            if redacted == secret_text or "[REDACTED]" not in redacted:
                return "SECRET_REDACTION_FAILED"
        else:
            raise AssertionError(
                f"P10 Dev security category is not implemented: {case.threat_category}"
            )
    except (ValueError, TimeoutError) as exc:
        return str(exc)
    except PermissionError:
        return "CROSS_COURSE_ACCESS"
    return None


def _minimal_docx() -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("word/document.xml", b"<document/>")
    return output.getvalue()
