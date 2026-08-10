from __future__ import annotations

import hashlib
import json
import subprocess
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol, cast

from pydantic import BaseModel, ConfigDict, Field, JsonValue

from courserag.evals.p09_metrics import (
    abstention_metrics,
    categorical_accuracy,
    claim_citation_completeness,
    complete_group_coverage,
    context_gold_evidence_coverage,
    evidence_id_overlap_metrics,
    list_set_f1,
    short_answer_exact_match,
    short_answer_token_f1,
)
from evaluation.contracts import DatasetSplit, FallbackPolicy, HashedArtifact, RunIntent
from evaluation.io import atomic_write_json
from evaluation.manifest import RunDatasetRef, RunManifest, sha256_file
from evaluation.p09_dev_loader import P09DevCase, load_p09_dev_bundle
from evaluation.runner import EvaluationRunner

APPROVED_P09_BUNDLE_SHA256 = "5a84bac041375310d5bb80f17f7481464d07dbcf75f9f980c6b8a030e58af0c1"
ANSWER_GROUNDING_SNAPSHOT_SHA256 = (
    "d85d9603965ecad620d62e39d2fde15f4b2857d180b9aba2379a568a59656602"
)
ANSWER_GROUNDING_PROTOCOL_SHA256 = (
    "211bf746f950eae3b8ba78729609b28ce2d8ebd50e95cdccb08358b068f5f9ec"
)
ANSWER_GROUNDING_PROFILE_SHA256 = "345500b79064a2c7e9d454b6f2fa96ca0e191e1c7974a3367eb040795631d6fe"


class P09ClaimResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str
    evidence_ids: list[str] = Field(default_factory=list)


class P09SystemResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    intent_route: str | None = None
    intent_rule_id: str | None = None
    intent_reason: str | None = None
    minimum_source_count: int = Field(default=1, ge=1)
    retrieval_strategy: str | None = None
    selected_evidence_ids: list[str] = Field(default_factory=list)
    context_token_count: int = Field(default=0, ge=0)
    context_item_count: int = Field(default=0, ge=0)
    answer_status: str | None = None
    answer: str | None = None
    answer_type: str | None = None
    list_items: list[str] = Field(default_factory=list)
    claims: list[P09ClaimResult] = Field(default_factory=list)
    resolvable_citations: list[bool] = Field(default_factory=list)
    usage: dict[str, JsonValue] = Field(default_factory=dict)
    usage_is_cumulative: bool = True
    latency_ms: dict[str, int] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    packing_report: dict[str, JsonValue] = Field(default_factory=dict)
    validation_summary: dict[str, JsonValue] = Field(default_factory=dict)
    citation_composer_version: str | None = None
    answer_shape_rule_id: str | None = None
    search_snapshot: dict[str, JsonValue] | None = None
    search_snapshot_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    fallback_applied: bool = False


class P09EvaluationSystem(Protocol):
    label: str

    def run(self, case: P09DevCase) -> P09SystemResult: ...


@dataclass
class P09UsageBudget:
    max_deepseek_tokens: int = 2_500_000
    max_cohere_search_units: int = 180
    deepseek_tokens: int = 0
    cohere_search_units: int = 0

    def reserve(self, *, deepseek_tokens: int = 0, cohere_search_units: int = 0) -> None:
        if self.deepseek_tokens + deepseek_tokens > self.max_deepseek_tokens:
            raise RuntimeError("P09 DeepSeek token budget would be exceeded")
        if self.cohere_search_units + cohere_search_units > self.max_cohere_search_units:
            raise RuntimeError("P09 Cohere Search Unit budget would be exceeded")
        self.deepseek_tokens += deepseek_tokens
        self.cohere_search_units += cohere_search_units


def run_p09_dev(
    *,
    repository_root: Path,
    output_dir: Path,
    run_id: str,
    systems: Mapping[str, P09EvaluationSystem],
    resume: bool = False,
    rerun_system_names: frozenset[str] = frozenset(),
    rerun_minimum_attempts: Mapping[str, int] | None = None,
    rerun_failed_answer_system_names: frozenset[str] = frozenset(),
    max_deepseek_tokens: int = 2_500_000,
    max_cohere_search_units: int = 180,
    governance_amendments: list[dict[str, JsonValue]] | None = None,
) -> Path:
    root = repository_root.resolve()
    dataset_root = root / "datasets/courserag_eval/v1"
    bundle = load_p09_dev_bundle(dataset_root)
    if not systems:
        raise ValueError("P09 Runner requires at least one system")
    approval_path = dataset_root / "provenance/p09_gold_bundle_approval.json"
    approval = json.loads(approval_path.read_text(encoding="utf-8"))
    if approval.get("bundle_sha256") != APPROVED_P09_BUNDLE_SHA256:
        raise ValueError("P09 Runner requires the exact Approved r2 bundle")
    commit, dirty = _git_state(root)
    inputs = (
        approval_path,
        dataset_root / "approved/ds5/p08_retrieval.json",
        dataset_root / "approved/ds5/p09_qa.json",
        dataset_root / "approved/ds5/p09_context.json",
        dataset_root / "splits/dev_ids.txt",
    )
    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = output_dir / "run_manifest.json"
    if resume:
        if not manifest_path.is_file():
            raise FileNotFoundError("P09 Resume requires the original Run Manifest")
        manifest = RunManifest.model_validate_json(manifest_path.read_text(encoding="utf-8"))
        expected_versions = {name: value.label for name, value in sorted(systems.items())}
        if manifest.component_versions != expected_versions:
            raise ValueError("P09 Resume system versions differ from the original Run")
    else:
        manifest = RunManifest(
            run_id=run_id,
            created_at=datetime.now(UTC),
            dataset=RunDatasetRef(
                dataset_id="courserag-eval",
                dataset_version="v1",
                split=DatasetSplit.DEV,
                manifest_sha256=sha256_file(dataset_root / "manifest.json"),
                split_sha256=sha256_file(dataset_root / "splits/dev_ids.txt"),
            ),
            intent=RunIntent.TUNING,
            tuning_enabled=True,
            git_commit=commit,
            git_dirty=dirty,
            input_artifacts=[_artifact(root, value) for value in inputs],
            component_versions={name: value.label for name, value in sorted(systems.items())},
            configuration={
                "approved_bundle_sha256": APPROVED_P09_BUNDLE_SHA256,
                "case_count": 60,
                "retrieval_main_count": 54,
                "upstream_gap_diagnostic_count": 6,
                "test_access": False,
                "context_max_items": 8,
                "context_max_tokens": 4000,
                "deepseek_max_total_tokens": max_deepseek_tokens,
                "cohere_max_search_units": max_cohere_search_units,
            },
            fallback_policy=FallbackPolicy.FAIL_SAMPLE,
            random_seed=0,
            llm_as_judge=False,
        )
        atomic_write_json(manifest_path, manifest.model_dump(mode="json"))
    runner = EvaluationRunner(
        manifest=manifest,
        checkpoint_path=output_dir / "checkpoint.json",
        partial_report_path=output_dir / "partial_report.json",
        final_report_path=output_dir / "report.json",
        dataset_root=dataset_root,
        resume=resume,
    )
    outputs: dict[str, dict[str, P09SystemResult]] = {}
    for system_name, system in sorted(systems.items()):
        for case in bundle.cases:
            key = f"{system_name}:{case.qa.record_id}"
            if resume and system_name in rerun_system_names:
                existing = runner.state.cases.get(key)
                minimum_attempt = (rerun_minimum_attempts or {}).get(system_name, 2)
                failed_answer = bool(
                    existing is not None
                    and isinstance(existing.result, dict)
                    and existing.result.get("answer_status") == "failed"
                )
                if existing is not None and (
                    existing.attempt < minimum_attempt
                    or (system_name in rerun_failed_answer_system_names and failed_answer)
                ):
                    runner.invalidate_succeeded_case(
                        case_id=key,
                        case_sha256=_case_hash(case, system_name),
                        reason_code="P09_QA_CONTRACT_REPAIR_RERUN",
                    )
            result = P09SystemResult.model_validate(
                runner.run_case(
                    key,
                    _case_hash(case, system_name),
                    lambda: _execute_system(system, case),
                )
            )
            if result.fallback_applied:
                raise RuntimeError("Formal P09 result contains a forbidden silent Fallback")
            outputs.setdefault(system_name, {})[case.qa.record_id] = result
    report_systems = {
        name: _system_report(bundle.cases, values) for name, values in outputs.items()
    }
    runner.complete(
        cast(
            dict[str, JsonValue],
            {
                "scope": "approved_p09_r2_dev_only",
                "approved_bundle_sha256": APPROVED_P09_BUNDLE_SHA256,
                "test_access": False,
                "retrieval_main_count": bundle.retrieval_main_count,
                "upstream_gap_diagnostic_count": bundle.upstream_gap_diagnostic_count,
                "governance_amendments": governance_amendments or [],
                "systems": report_systems,
            },
        )
    )
    return output_dir / "report.json"


def write_p09_freeze_candidate(
    report_path: Path,
    output_path: Path,
    *,
    governance_artifacts: dict[str, JsonValue] | None = None,
) -> str:
    report = json.loads(report_path.read_text(encoding="utf-8"))
    if report.get("status") != "completed" or report["report"].get("test_access") is not False:
        raise ValueError("P09 Freeze Candidate requires a completed Dev-only report")
    systems = report["report"]["systems"]
    q3 = systems.get("q3")
    if q3 is None:
        raise ValueError("P09 Freeze Candidate requires Q3")
    payload: dict[str, JsonValue] = {
        "schema_version": "courserag.p09-freeze-candidate.v1",
        "status": "pending_course_owner_approval",
        "approved_bundle_sha256": APPROVED_P09_BUNDLE_SHA256,
        "report_sha256": sha256_file(report_path),
        "run_identity_sha256": report["run_identity_sha256"],
        "q3_main_metrics": q3["retrieval_main_metrics"],
        "sufficiency_profile": "resources/qa_profiles/q3_candidate_v1.json",
        "default_profile_written": False,
    }
    if governance_artifacts:
        payload["governance_artifacts"] = governance_artifacts
    atomic_write_json(output_path, payload)
    return sha256_file(output_path)


def write_p09_retrieval_snapshot(report_path: Path, output_path: Path) -> str:
    report = json.loads(report_path.read_text(encoding="utf-8"))
    cases: dict[str, JsonValue] = {}
    for case_id, state in sorted(report.get("cases", {}).items()):
        if not case_id.startswith("b7:") or state.get("status") != "succeeded":
            continue
        result = state.get("result") or {}
        snapshot = result.get("search_snapshot")
        digest = result.get("search_snapshot_sha256")
        if not isinstance(snapshot, dict) or not isinstance(digest, str):
            raise ValueError("P09 Retrieval Snapshot requires complete B7 Search responses")
        calculated = hashlib.sha256(
            json.dumps(snapshot, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        if calculated != digest:
            raise ValueError("P09 Retrieval Snapshot Hash mismatch")
        if "gold-ev-" in json.dumps(snapshot, ensure_ascii=False):
            raise ValueError("P09 Retrieval Snapshot must not contain Gold Evidence IDs")
        cases[case_id.split(":", 1)[1]] = {
            "search_response": snapshot,
            "search_response_sha256": digest,
        }
    if len(cases) != 60:
        raise ValueError("P09 Retrieval Snapshot requires exactly 60 Dev B7 cases")
    payload: dict[str, JsonValue] = {
        "schema_version": "courserag.p09-retrieval-snapshot.v1",
        "scope": "approved_dev_b7_top8_non_gold",
        "approved_bundle_sha256": APPROVED_P09_BUNDLE_SHA256,
        "report_sha256": sha256_file(report_path),
        "test_access": False,
        "cases": cases,
    }
    atomic_write_json(output_path, payload)
    return sha256_file(output_path)


def run_formal_p09_candidate(
    *,
    repository_root: Path,
    output_dir: Path,
    external_data_authorized: bool,
    resume: bool = False,
    rerun_qa: bool = False,
    rerun_system_names: frozenset[str] = frozenset(),
) -> tuple[Path, Path, str]:
    if not external_data_authorized:
        raise RuntimeError("Formal P09 requires explicit external-data authorization")
    from core.settings import settings
    from evaluation.p09_systems import build_formal_p09_suite

    checkpoint_path = output_dir / "run-1/checkpoint.json" if resume else None
    suite = build_formal_p09_suite(repository_root, settings, checkpoint_path=checkpoint_path)
    systems = {name: suite.system(name) for name in ("b6", "b7", "b8", "q0", "q1", "q2", "q3")}
    report = run_p09_dev(
        repository_root=repository_root,
        output_dir=output_dir / "run-1",
        run_id="p09-formal-run-1",
        systems=systems,
        resume=resume,
        rerun_system_names=(
            frozenset({"q0", "q1", "q2", "q3"}) if rerun_qa else rerun_system_names
        ),
    )
    candidate = output_dir / "freeze_candidate.json"
    digest = write_p09_freeze_candidate(report, candidate)
    return report, candidate, digest


def run_p09_gate_repair(
    *,
    repository_root: Path,
    output_dir: Path,
    external_data_authorized: bool,
    resume: bool = False,
    rerun_context_qa: bool = False,
) -> tuple[Path, Path, Path, str]:
    if not external_data_authorized:
        raise RuntimeError("P09 Gate Repair requires explicit external-data authorization")
    from core.settings import settings
    from evaluation.p09_systems import build_formal_p09_suite

    run_dir = output_dir / "repair-run-1"
    if rerun_context_qa and not resume:
        raise ValueError("P09 context/QA Gate Repair rerun requires Resume")
    checkpoint_path = run_dir / "checkpoint.json" if resume else None
    amendment_path = output_dir / "budget_amendment_20260808.json"
    amendment = _load_gate_repair_budget_amendment(amendment_path)
    amendment_sha256 = sha256_file(amendment_path)
    consumed_before_resume = _gate_repair_deepseek_consumed(output_dir) if resume else 0
    suite = build_formal_p09_suite(
        repository_root,
        settings,
        checkpoint_path=checkpoint_path,
        max_deepseek_tokens=350_000,
        max_cohere_search_units=60,
        label_suffix="freeze-gate-repair-v2",
        discard_restored_variants=(frozenset({"b8", "q3"}) if rerun_context_qa else frozenset()),
        initial_deepseek_tokens=consumed_before_resume,
    )
    systems = {name: suite.system(name) for name in ("b7", "b8", "q3")}
    report = run_p09_dev(
        repository_root=repository_root,
        output_dir=run_dir,
        run_id="p09-freeze-gate-repair-run-1",
        systems=systems,
        resume=resume,
        rerun_system_names=(frozenset({"b8", "q3"}) if rerun_context_qa else frozenset()),
        rerun_minimum_attempts={"b8": 2, "q3": 2},
        rerun_failed_answer_system_names=(frozenset({"q3"}) if rerun_context_qa else frozenset()),
        max_deepseek_tokens=350_000,
        max_cohere_search_units=60,
        governance_amendments=[
            {
                "path": amendment_path.resolve().relative_to(repository_root.resolve()).as_posix(),
                "sha256": amendment_sha256,
                "effective_deepseek_repair_token_cap": amendment[
                    "effective_deepseek_repair_token_cap"
                ],
                "phase_deepseek_total_token_cap": amendment["phase_deepseek_total_token_cap"],
                "effective_cohere_repair_search_unit_cap": amendment[
                    "effective_cohere_repair_search_unit_cap"
                ],
                "deepseek_repair_tokens_consumed_before_amendment": amendment[
                    "deepseek_repair_tokens_consumed_before_amendment"
                ],
            }
        ],
    )
    snapshot = output_dir / "b7_retrieval_snapshot.json"
    write_p09_retrieval_snapshot(report, snapshot)
    usage_audit = output_dir / "usage_audit.json"
    write_p09_gate_repair_usage_audit(
        report_path=report,
        amendment_path=amendment_path,
        original_p09_report=repository_root / "storage_eval/p09_query_context_qa/run-1/report.json",
        failed_attempt_report=run_dir / "report_attempt1.json",
        output_path=usage_audit,
    )
    candidate = output_dir / "freeze_candidate.json"
    digest = write_p09_freeze_candidate(
        report,
        candidate,
        governance_artifacts={
            "budget_amendment_sha256": amendment_sha256,
            "usage_audit_sha256": sha256_file(usage_audit),
            "retrieval_snapshot_sha256": sha256_file(snapshot),
        },
    )
    return report, snapshot, candidate, digest


def run_p09_answer_grounding(
    *,
    repository_root: Path,
    output_dir: Path,
    external_data_authorized: bool,
    resume: bool = False,
) -> tuple[Path, Path, Path, Path | None, str | None]:
    """Run the one-shot, preregistered Q3 Answer Grounding candidate.

    Retrieval is restored from the frozen B7 snapshot.  The suite therefore has a zero
    Cohere budget and can only call the configured QA Provider for fresh Q3 cases.
    """

    if not external_data_authorized:
        raise RuntimeError("P09 Answer Grounding requires explicit external-data authorization")
    from core.settings import settings
    from evaluation.p09_gate_repair_analysis import write_answer_grounding_report
    from evaluation.p09_systems import build_formal_p09_suite

    root = repository_root.resolve()
    output_dir = output_dir.resolve()
    protocol_path = root / "storage_eval/p09_answer_grounding/protocol_manifest.json"
    profile_path = root / "resources/qa_profiles/p09_answer_grounding_candidate_v1.json"
    snapshot_path = root / "storage_eval/p09_gate_repair/b7_retrieval_snapshot.json"
    _validate_answer_grounding_inputs(protocol_path, profile_path, snapshot_path)
    run_dir = output_dir / "run-1"
    checkpoint_path = run_dir / "checkpoint.json" if resume else None
    suite = build_formal_p09_suite(
        root,
        settings,
        checkpoint_path=checkpoint_path,
        retrieval_snapshot_path=snapshot_path,
        max_deepseek_tokens=375_000,
        max_cohere_search_units=0,
        label_suffix="answer-grounding-candidate-v1",
    )
    report = run_p09_dev(
        repository_root=root,
        output_dir=run_dir,
        run_id="p09-answer-grounding-run-1",
        systems={"q3": suite.system("q3")},
        resume=resume,
        max_deepseek_tokens=375_000,
        max_cohere_search_units=0,
        governance_amendments=[
            {
                "protocol_manifest_sha256": ANSWER_GROUNDING_PROTOCOL_SHA256,
                "answer_grounding_profile_sha256": ANSWER_GROUNDING_PROFILE_SHA256,
                "b7_retrieval_snapshot_sha256": ANSWER_GROUNDING_SNAPSHOT_SHA256,
                "deepseek_additional_token_cap": 375_000,
                "p09_phase_total_token_cap": 2_500_000,
                "cohere_additional_search_units": 0,
                "single_candidate_only": True,
            }
        ],
    )
    usage_audit = output_dir / "usage_audit.json"
    write_p09_answer_grounding_usage_audit(report, usage_audit)
    evaluation_path = output_dir / "evaluation_protocol_r2.json"
    evaluation_sha256 = write_answer_grounding_report(root, report, evaluation_path)
    evaluation = json.loads(evaluation_path.read_text(encoding="utf-8"))
    candidate_path: Path | None = None
    candidate_sha256: str | None = None
    if evaluation.get("status") == "passed":
        candidate_path = output_dir / "freeze_candidate.json"
        candidate_sha256 = _write_answer_grounding_freeze_candidate(
            report,
            evaluation_path,
            usage_audit,
            candidate_path,
            evaluation_sha256=evaluation_sha256,
        )
    return report, evaluation_path, usage_audit, candidate_path, candidate_sha256


def _validate_answer_grounding_inputs(
    protocol_path: Path, profile_path: Path, snapshot_path: Path
) -> None:
    expected = {
        protocol_path: ANSWER_GROUNDING_PROTOCOL_SHA256,
        profile_path: ANSWER_GROUNDING_PROFILE_SHA256,
        snapshot_path: ANSWER_GROUNDING_SNAPSHOT_SHA256,
    }
    for path, digest in expected.items():
        if not path.is_file() or sha256_file(path) != digest:
            raise ValueError(f"P09 Answer Grounding input identity differs: {path.name}")
    protocol = json.loads(protocol_path.read_text(encoding="utf-8"))
    required = {
        "status": "preregistered_before_provider_calls",
        "test_access": False,
        "single_candidate_only": True,
        "post_run_prompt_tuning_allowed": False,
        "external_data_authorized": True,
    }
    for key, value in required.items():
        if protocol.get(key) != value:
            raise ValueError(f"P09 Answer Grounding Protocol has invalid {key}")


def write_p09_answer_grounding_usage_audit(report_path: Path, output_path: Path) -> str:
    report = json.loads(report_path.read_text(encoding="utf-8"))
    q3_usage = report["report"]["systems"]["q3"]["usage"]
    answer_grounding_tokens = int(q3_usage.get("deepseek_total_tokens", 0))
    cohere_units = int(q3_usage.get("cohere_search_units", 0))
    prior_path = report_path.parents[2] / "p09_gate_repair/usage_audit.json"
    if not prior_path.is_file():
        prior_path = Path.cwd() / "storage_eval/p09_gate_repair/usage_audit.json"
    prior = json.loads(prior_path.read_text(encoding="utf-8"))
    phase_before = int(prior["phase_deepseek_tokens"])
    phase_after = phase_before + answer_grounding_tokens
    if answer_grounding_tokens > 375_000:
        raise RuntimeError("P09 Answer Grounding DeepSeek token cap was exceeded")
    if phase_after > 2_500_000:
        raise RuntimeError("P09 phase DeepSeek token cap was exceeded")
    if cohere_units != 0:
        raise RuntimeError("P09 Answer Grounding must not consume Cohere Search Units")
    payload: dict[str, JsonValue] = {
        "schema_version": "courserag.p09-answer-grounding-usage-audit.v1",
        "status": "within_authorized_limits",
        "answer_grounding_deepseek_tokens": answer_grounding_tokens,
        "answer_grounding_deepseek_token_cap": 375_000,
        "phase_deepseek_tokens_before": phase_before,
        "phase_deepseek_tokens_after": phase_after,
        "phase_deepseek_token_cap": 2_500_000,
        "answer_grounding_cohere_search_units": cohere_units,
        "answer_grounding_cohere_search_unit_cap": 0,
        "provider_usage_policy": "provider_usage_when_available_else_local_estimate_x1.5",
    }
    atomic_write_json(output_path, payload)
    return sha256_file(output_path)


def _write_answer_grounding_freeze_candidate(
    report_path: Path,
    evaluation_path: Path,
    usage_audit_path: Path,
    output_path: Path,
    *,
    evaluation_sha256: str,
) -> str:
    report = json.loads(report_path.read_text(encoding="utf-8"))
    payload: dict[str, JsonValue] = {
        "schema_version": "courserag.p09-answer-grounding-freeze-candidate.v1",
        "status": "pending_course_owner_approval",
        "approved_bundle_sha256": APPROVED_P09_BUNDLE_SHA256,
        "report_sha256": sha256_file(report_path),
        "evaluation_protocol_r2_sha256": evaluation_sha256,
        "usage_audit_sha256": sha256_file(usage_audit_path),
        "answer_grounding_profile_sha256": ANSWER_GROUNDING_PROFILE_SHA256,
        "b7_retrieval_snapshot_sha256": ANSWER_GROUNDING_SNAPSHOT_SHA256,
        "run_identity_sha256": report["run_identity_sha256"],
        "q3_main_metrics": report["report"]["systems"]["q3"]["retrieval_main_metrics"],
        "default_profile_written": False,
        "runtime_default_activated": False,
        "test_access": False,
        "evaluation_path": evaluation_path.name,
    }
    atomic_write_json(output_path, payload)
    return sha256_file(output_path)


def _load_gate_repair_budget_amendment(path: Path) -> dict[str, JsonValue]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    expected = {
        "status": "accepted",
        "effective_deepseek_repair_token_cap": 350_000,
        "phase_deepseek_total_token_cap": 2_500_000,
        "effective_cohere_repair_search_unit_cap": 60,
        "cohere_additional_search_units": 0,
    }
    for key, value in expected.items():
        if payload.get(key) != value:
            raise ValueError(f"P09 budget amendment has invalid {key}")
    return cast(dict[str, JsonValue], payload)


def _gate_repair_deepseek_consumed(output_dir: Path) -> int:
    run_dir = output_dir / "repair-run-1"
    first = json.loads((run_dir / "report_attempt1.json").read_text(encoding="utf-8"))
    first_usage = int(first["report"]["systems"]["q3"]["usage"]["deepseek_total_tokens"])
    checkpoint = json.loads((run_dir / "checkpoint.json").read_text(encoding="utf-8"))
    preserved_paths = sorted(run_dir.glob("report_attempt*_pre_retry.json"))
    if preserved_paths:
        first_preserved = json.loads(preserved_paths[0].read_text(encoding="utf-8"))
        continued_usage = int(
            first_preserved["report"]["systems"]["q3"]["usage"]["deepseek_total_tokens"]
        )
        seen_attempts = _q3_attempts(first_preserved)
        for path in preserved_paths[1:]:
            preserved = json.loads(path.read_text(encoding="utf-8"))
            continued_usage += _new_q3_attempt_usage(preserved, seen_attempts)
            seen_attempts.update(_q3_attempts(preserved))
        continued_usage += _new_q3_attempt_usage(checkpoint, seen_attempts)
        return first_usage + continued_usage
    continued_usage = 0
    for case_id, state in checkpoint.get("cases", {}).items():
        if (
            case_id.startswith("q3:")
            and state.get("status") == "succeeded"
            and int(state.get("attempt", 0)) >= 2
        ):
            continued_usage += int(
                (state.get("result") or {}).get("usage", {}).get("deepseek_total_tokens", 0)
            )
    return first_usage + continued_usage


def _q3_attempts(payload: Mapping[str, JsonValue]) -> dict[str, int]:
    cases = payload.get("cases", {})
    if not isinstance(cases, dict):
        return {}
    return {
        case_id: _json_int(state.get("attempt", 0))
        for case_id, state in cases.items()
        if case_id.startswith("q3:") and isinstance(state, dict)
    }


def _new_q3_attempt_usage(
    payload: Mapping[str, JsonValue], seen_attempts: Mapping[str, int]
) -> int:
    cases = payload.get("cases", {})
    if not isinstance(cases, dict):
        return 0
    usage = 0
    for case_id, state in cases.items():
        if not case_id.startswith("q3:") or not isinstance(state, dict):
            continue
        if state.get("status") != "succeeded":
            continue
        if _json_int(state.get("attempt", 0)) <= seen_attempts.get(case_id, 0):
            continue
        result = state.get("result", {})
        if not isinstance(result, dict):
            continue
        result_usage = result.get("usage", {})
        if isinstance(result_usage, dict):
            usage += _json_int(result_usage.get("deepseek_total_tokens", 0))
    return usage


def _json_int(value: JsonValue | None) -> int:
    if isinstance(value, bool) or not isinstance(value, int | float | str):
        return 0
    return int(value)


def write_p09_gate_repair_usage_audit(
    *,
    report_path: Path,
    amendment_path: Path,
    original_p09_report: Path,
    failed_attempt_report: Path,
    output_path: Path,
) -> str:
    report = json.loads(report_path.read_text(encoding="utf-8"))
    original = json.loads(original_p09_report.read_text(encoding="utf-8"))
    failed = json.loads(failed_attempt_report.read_text(encoding="utf-8"))
    repair_attempt1 = int(failed["report"]["systems"]["q3"]["usage"]["deepseek_total_tokens"])
    repair_total = _gate_repair_deepseek_consumed(report_path.parents[1])
    repair_attempt2 = repair_total - repair_attempt1
    original_total = sum(
        int(system["usage"]["deepseek_total_tokens"])
        for system in original["report"]["systems"].values()
    )
    phase_total = original_total + repair_total
    if repair_total > 350_000:
        raise RuntimeError("P09 Gate Repair DeepSeek token cap was exceeded")
    if phase_total > 2_500_000:
        raise RuntimeError("P09 phase DeepSeek token cap was exceeded")
    cohere_units = int(report["report"]["systems"]["b7"]["usage"]["cohere_search_units"])
    if cohere_units > 60:
        raise RuntimeError("P09 Gate Repair Cohere Search Unit cap was exceeded")
    payload: dict[str, JsonValue] = {
        "schema_version": "courserag.p09-gate-repair-usage-audit.v1",
        "status": "within_authorized_limits",
        "budget_amendment_sha256": sha256_file(amendment_path),
        "original_p09_deepseek_tokens": original_total,
        "repair_attempt1_deepseek_tokens": repair_attempt1,
        "repair_attempt2_deepseek_tokens": repair_attempt2,
        "repair_deepseek_tokens": repair_total,
        "repair_deepseek_token_cap": 350_000,
        "phase_deepseek_tokens": phase_total,
        "phase_deepseek_token_cap": 2_500_000,
        "repair_cohere_search_units": cohere_units,
        "repair_cohere_search_unit_cap": 60,
        "provider_usage_policy": "provider_usage_when_available_else_local_estimate_x1.5",
    }
    atomic_write_json(output_path, payload)
    return sha256_file(output_path)


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Run the Approved-Dev-only formal P09 candidate")
    parser.add_argument("--repository-root", type=Path, default=Path.cwd())
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--external-data-authorized", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--rerun-qa", action="store_true")
    parser.add_argument("--gate-repair", action="store_true")
    parser.add_argument("--answer-grounding", action="store_true")
    parser.add_argument("--gate-repair-rerun-context-qa", action="store_true")
    parser.add_argument(
        "--rerun-system", action="append", choices=("q0", "q1", "q2", "q3"), default=[]
    )
    args = parser.parse_args()
    evaluation = None
    usage_audit = None
    if args.answer_grounding:
        report, evaluation, usage_audit, candidate, digest = run_p09_answer_grounding(
            repository_root=args.repository_root,
            output_dir=args.output_dir,
            external_data_authorized=args.external_data_authorized,
            resume=args.resume,
        )
        snapshot = None
    elif args.gate_repair:
        report, snapshot, candidate, digest = run_p09_gate_repair(
            repository_root=args.repository_root,
            output_dir=args.output_dir,
            external_data_authorized=args.external_data_authorized,
            resume=args.resume,
            rerun_context_qa=args.gate_repair_rerun_context_qa,
        )
    else:
        report, candidate, digest = run_formal_p09_candidate(
            repository_root=args.repository_root,
            output_dir=args.output_dir,
            external_data_authorized=args.external_data_authorized,
            resume=args.resume,
            rerun_qa=args.rerun_qa,
            rerun_system_names=frozenset(args.rerun_system),
        )
        snapshot = None
    print(
        json.dumps(
            {
                "report": str(report),
                "freeze_candidate": str(candidate) if candidate else None,
                "freeze_candidate_sha256": digest,
                "retrieval_snapshot": str(snapshot) if snapshot else None,
                "evaluation": str(evaluation) if evaluation else None,
                "usage_audit": str(usage_audit) if usage_audit else None,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )


def _system_report(
    cases: tuple[P09DevCase, ...], values: Mapping[str, P09SystemResult]
) -> dict[str, JsonValue]:
    main = [case for case in cases if case.qa.evaluation_stratum == "retrieval_main"]
    diagnostic = [case for case in cases if case.qa.evaluation_stratum == "upstream_gap_diagnostic"]
    result: dict[str, object] = {
        "retrieval_main_metrics": _aggregate_cases(main, values),
        "upstream_gap_diagnostic_metrics": _aggregate_cases(diagnostic, values),
        "result_sha256": hashlib.sha256(
            json.dumps(
                {key: value.model_dump(mode="json") for key, value in sorted(values.items())},
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        ).hexdigest(),
        "usage": _usage(values.values()),
        "fallback_count": sum(value.fallback_applied for value in values.values()),
    }
    return cast(dict[str, JsonValue], result)


def _aggregate_cases(
    cases: list[P09DevCase], values: Mapping[str, P09SystemResult]
) -> dict[str, JsonValue]:
    if not cases:
        return {"case_count": 0}
    selected_coverages = []
    group_coverages = []
    evidence_id_overlap_precision = []
    evidence_id_overlap_recall = []
    evidence_id_overlap_f1 = []
    claim_complete = []
    citation_resolvability = []
    short_answer_em = []
    short_answer_f1 = []
    list_f1 = []
    predicted_answerable = []
    gold_answerable = []
    intent_predictions: list[str] = []
    intent_gold: list[str] = []
    for case in cases:
        result = values[case.qa.record_id]
        selected_coverages.append(
            context_gold_evidence_coverage(
                result.selected_evidence_ids, case.context.complete_evidence_groups
            ).value
            or 0.0
        )
        group_coverages.append(
            complete_group_coverage(
                result.selected_evidence_ids, case.context.complete_evidence_groups
            ).value
            or 0.0
        )
        if result.answer_status == "answered":
            predicted_ids = [value for claim in result.claims for value in claim.evidence_ids]
            gold_ids = [
                evidence_id
                for claim in case.qa.gold_claims
                for evidence_id in claim.required_evidence_ids
            ]
            overlap = evidence_id_overlap_metrics(
                predicted_evidence_ids=predicted_ids, gold_evidence_ids=gold_ids
            )
            evidence_id_overlap_precision.append(
                overlap["evidence_id_overlap_precision"].value or 0.0
            )
            evidence_id_overlap_recall.append(overlap["evidence_id_overlap_recall"].value or 0.0)
            evidence_id_overlap_f1.append(overlap["evidence_id_overlap_f1"].value or 0.0)
            claim_complete.append(
                claim_citation_completeness(
                    claims_with_citations=sum(bool(value.evidence_ids) for value in result.claims),
                    total_claims=len(result.claims),
                ).value
                or 0.0
            )
            citation_resolvability.append(
                float(bool(result.resolvable_citations) and all(result.resolvable_citations))
            )
        predicted_answerable.append(result.answer_status == "answered")
        gold_answerable.append(case.qa.answerable)
        if case.qa.gold_answer_type == "factoid":
            answer = result.answer or ""
            short_answer_em.append(
                short_answer_exact_match(answer, case.qa.gold_short_answers).value or 0.0
            )
            short_answer_f1.append(
                short_answer_token_f1(answer, case.qa.gold_short_answers).value or 0.0
            )
        if case.qa.gold_answer_type == "list":
            list_f1.append(list_set_f1(result.list_items, case.qa.gold_list_items).value or 0.0)
        if case.qa.query_type != "unanswerable" and result.intent_route:
            intent_predictions.append(result.intent_route)
            intent_gold.append(_intent_gold(case.qa.query_type))
    abstention = abstention_metrics(
        predicted_answerable=predicted_answerable, gold_answerable=gold_answerable
    )
    return {
        "case_count": len(cases),
        "context_gold_evidence_coverage": _mean(selected_coverages),
        "complete_group_coverage": _mean(group_coverages),
        "evidence_id_overlap_precision": _mean(evidence_id_overlap_precision),
        "evidence_id_overlap_recall": _mean(evidence_id_overlap_recall),
        "macro_evidence_id_overlap_f1": _mean(evidence_id_overlap_f1),
        "claim_citation_completeness": _mean(claim_complete),
        "citation_resolvability": _mean(citation_resolvability),
        "short_answer_exact_match": _mean(short_answer_em),
        "short_answer_token_f1": _mean(short_answer_f1),
        "short_answer_case_count": len(short_answer_f1),
        "list_set_f1": _mean(list_f1),
        "list_case_count": len(list_f1),
        "answer_status_accuracy": categorical_accuracy(
            "answer_status_accuracy",
            ["answer" if value else "abstain" for value in predicted_answerable],
            ["answer" if value else "abstain" for value in gold_answerable],
        ).value,
        "intent_accuracy": categorical_accuracy(
            "intent_accuracy", intent_predictions, intent_gold
        ).value,
        "unanswerable_recall": abstention["unanswerable_recall"].value,
        "false_answer_rate": abstention["false_answer_rate"].value,
        "false_abstention_rate": abstention["false_abstention_rate"].value,
        "qa_failure_rate": sum(
            values[case.qa.record_id].answer_status == "failed" for case in cases
        )
        / len(cases),
    }


def _usage(values: Iterable[P09SystemResult]) -> dict[str, int]:
    cumulative = {"deepseek_total_tokens": 0, "cohere_search_units": 0}
    incremental = {"deepseek_total_tokens": 0, "cohere_search_units": 0}
    for result in values:
        destination = cumulative if result.usage_is_cumulative else incremental
        for key in cumulative:
            value = _usage_int(result, key)
            if result.usage_is_cumulative:
                destination[key] = max(destination[key], value)
            else:
                destination[key] += value
    return {key: cumulative[key] + incremental[key] for key in cumulative}


def _usage_int(result: P09SystemResult, key: str) -> int:
    value = result.usage.get(key, 0)
    return int(value) if isinstance(value, int | float | str) else 0


def _execute_system(system: P09EvaluationSystem, case: P09DevCase) -> JsonValue:
    return cast(JsonValue, system.run(case).model_dump(mode="json"))


def _intent_gold(query_type: str) -> str:
    return {
        "exact_fact": "fact",
        "paraphrase": "fact",
        "definition": "definition",
        "comparison": "comparison",
        "procedure": "procedure",
        "application": "example_application",
        "cross_section": "cross_section",
    }[query_type]


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _case_hash(case: P09DevCase, system_name: str) -> str:
    payload = {
        "system": system_name,
        "retrieval": case.retrieval.model_dump(mode="json"),
        "qa": case.qa.model_dump(mode="json"),
        "context": case.context.model_dump(mode="json"),
    }
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _artifact(root: Path, path: Path) -> HashedArtifact:
    return HashedArtifact(
        path=path.resolve().relative_to(root).as_posix(),
        sha256=sha256_file(path),
        size_bytes=path.stat().st_size,
    )


def _git_state(root: Path) -> tuple[str, bool]:
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=root, check=True, capture_output=True, text=True
    ).stdout.strip()
    dirty = bool(
        subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    )
    return commit, dirty


if __name__ == "__main__":
    main()
