from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
from collections.abc import Mapping
from pathlib import Path
from typing import Literal, cast

from pydantic import BaseModel, ConfigDict, Field, JsonValue

from evaluation.io import atomic_write_json
from evaluation.manifest import sha256_file
from evaluation.p09_dev_loader import P09DevCase, load_p09_dev_bundle
from evaluation.p09_retrieval_qa_eval import (
    P09EvaluationSystem,
    P09SystemResult,
    _aggregate_cases,
    run_p09_dev,
)

FRESH_CASE_IDS = (
    "gold-qa-01fd462adc1638a1a81fcabdf58e0ac9",
    "gold-qa-0ce2025962b5691d0cb3f1522ed1aaa8",
    "gold-qa-10caf16efab833ad40e600359b5239c2",
    "gold-qa-2b8972b47de56a5b6b62e68091320557",
    "gold-qa-3513e4ae011f3940d8b22e9133f521e6",
    "gold-qa-574fc80decab989823e88f69bc850f15",
    "gold-qa-730f317833bc4b6f6d458f42814069be",
    "gold-qa-74304d145c41aaf7ea44b17108ef39ef",
    "gold-qa-7efcb21383c840fa94d106b878b972b1",
    "gold-qa-ae7a2fadc743507c01dc579c6a728f06",
    "gold-qa-f287be490a3c23fdd7bc3d027b70051a",
    "gold-qa-f6ec6bb28fa466f2958eb45ee887480e",
)
AUTHORIZED_PROTOCOL_SHA256 = "0dd9ff64ba94b9a0f6e3389565b17eb7e88d1ffd63b19e0e58775f7e6f462696"
SOURCE_REPORT_SHA256 = "b04fc9b620fccddecaf889c201fa5b8d0cec139b92686a2ac354dffed853f77b"
RETRIEVAL_SNAPSHOT_SHA256 = "d85d9603965ecad620d62e39d2fde15f4b2857d180b9aba2379a568a59656602"


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class P10DevCalibrationProtocol(StrictModel):
    schema_version: Literal["courserag.p10-dev-calibration-protocol.v1"] = (
        "courserag.p10-dev-calibration-protocol.v1"
    )
    approved_p10_bundle_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_p09_protocol_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    candidate_profile_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    fresh_case_ids: tuple[str, ...] = FRESH_CASE_IDS
    reused_case_count: Literal[42] = 42
    deepseek_token_cap: Literal[180000] = 180000
    cohere_search_unit_cap: Literal[0] = 0
    external_data_authorized: bool = False
    test_access: Literal[False] = False
    retrieval_rerun: Literal[False] = False
    single_candidate_only: Literal[True] = True
    post_result_tuning_allowed: Literal[False] = False


class P10FrozenManifest(StrictModel):
    schema_version: Literal["courserag.p10-frozen-manifest.v2"] = "courserag.p10-frozen-manifest.v2"
    protocol_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    qa_dev_report_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    qa_gate_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    component_dev_report_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    usage_audit_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    workspace_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    profile_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    test_ids_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    approved_p10_bundle_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    deepseek_dev_tokens: int = Field(ge=0, le=180000)
    cohere_dev_search_units: Literal[0] = 0
    test_access: Literal[False] = False
    fallback_count: Literal[0] = 0
    status: Literal["awaiting_owner_test_lock"] = "awaiting_owner_test_lock"


class P10TestLock(StrictModel):
    schema_version: Literal["courserag.p10-test-lock.v1"] = "courserag.p10-test-lock.v1"
    frozen_manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    owner_approval_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    external_budget_authorized: bool
    locked: Literal[True] = True


class P10DevDeltaSystem:
    def __init__(
        self,
        *,
        fresh_system: P09EvaluationSystem,
        fixed_results: Mapping[str, P09SystemResult],
        profile_sha256: str,
    ) -> None:
        self.fresh_system = fresh_system
        self.fixed_results = fixed_results
        self.label = f"p10-joint-calibration-v1:{profile_sha256}"

    def run(self, case: P09DevCase) -> P09SystemResult:
        if case.qa.record_id in FRESH_CASE_IDS:
            return self.fresh_system.run(case)
        return self.fixed_results[case.qa.record_id].model_copy(deep=True)


def build_dev_protocol(
    repository_root: Path, *, external_data_authorized: bool = False
) -> P10DevCalibrationProtocol:
    bundle = (
        repository_root / "datasets/courserag_eval/v1/provenance/p10_input_bundle_manifest.json"
    )
    source_protocol = (
        repository_root / "storage_eval/p09_generation_reliability/protocol_manifest.json"
    )
    profile = repository_root / "resources/qa_profiles/p10_dev_joint_calibration_candidate_v1.json"
    bundle_payload = json.loads(bundle.read_text(encoding="utf-8"))
    if (
        bundle_payload["bundle_sha256"]
        != "5b6d756a39c988f952536ec93d2aa23b9c593908c3ea24c6af6816cff92b6702"
    ):
        raise ValueError("Approved P10 Bundle identity changed")
    source_payload = json.loads(source_protocol.read_text(encoding="utf-8"))
    if tuple(source_payload["fresh_case_ids"]) != FRESH_CASE_IDS:
        raise ValueError("P09 source delta Case set changed")
    return P10DevCalibrationProtocol(
        approved_p10_bundle_sha256=bundle_payload["bundle_sha256"],
        source_p09_protocol_sha256=_file_sha256(source_protocol),
        candidate_profile_sha256=_file_sha256(profile),
        external_data_authorized=external_data_authorized,
    )


def create_frozen_manifest(
    *,
    protocol: P10DevCalibrationProtocol,
    qa_dev_report_sha256: str,
    qa_gate_sha256: str,
    component_dev_report_sha256: str,
    usage_audit_sha256: str,
    workspace_sha256: str,
    test_ids_sha256: str,
    deepseek_dev_tokens: int,
    gates_passed: bool,
    fallback_count: int,
) -> P10FrozenManifest:
    if not protocol.external_data_authorized:
        raise ValueError("Dev external-data authorization is missing")
    if not gates_passed or fallback_count != 0:
        raise ValueError("Failed Dev gates cannot produce a Frozen Manifest")
    return P10FrozenManifest(
        protocol_sha256=_model_sha256(protocol),
        qa_dev_report_sha256=qa_dev_report_sha256,
        qa_gate_sha256=qa_gate_sha256,
        component_dev_report_sha256=component_dev_report_sha256,
        usage_audit_sha256=usage_audit_sha256,
        workspace_sha256=workspace_sha256,
        profile_sha256=protocol.candidate_profile_sha256,
        test_ids_sha256=test_ids_sha256,
        approved_p10_bundle_sha256=protocol.approved_p10_bundle_sha256,
        deepseek_dev_tokens=deepseek_dev_tokens,
    )


def finalize_frozen_manifest(*, repository_root: Path, output_dir: Path) -> Path:
    root = repository_root.resolve()
    output_dir = output_dir.resolve()
    protocol = _load_authorized_protocol(output_dir / "dev_calibration_protocol.json")
    report_path = output_dir / "run-1/report.json"
    gate_path = output_dir / "automatic_gate_report.json"
    usage_path = output_dir / "usage_audit.json"
    component_path = output_dir / "component_dev_report.json"
    for path in (report_path, gate_path, usage_path, component_path):
        if not path.is_file():
            raise FileNotFoundError(f"P10 Frozen Manifest input is missing: {path.name}")

    gate = cast(dict[str, object], json.loads(gate_path.read_text(encoding="utf-8")))
    component = cast(dict[str, object], json.loads(component_path.read_text(encoding="utf-8")))
    usage = cast(dict[str, object], json.loads(usage_path.read_text(encoding="utf-8")))
    gate_checks = cast(dict[str, bool], gate.get("checks") or {})
    component_checks = cast(dict[str, bool], component.get("checks") or {})
    if not gate_checks or not all(gate_checks.values()):
        raise ValueError("QA Dev gates have not all passed")
    if (
        component.get("status") != "passed"
        or not component_checks
        or not all(component_checks.values())
    ):
        raise ValueError("Component Dev gates have not all passed")
    if gate.get("candidate_report_sha256") != sha256_file(report_path):
        raise ValueError("QA Dev report identity differs from its Gate")
    if usage.get("status") != "within_authorized_limits" or usage.get("test_access") is not False:
        raise ValueError("P10 Dev usage audit is not eligible for freezing")
    deepseek_tokens = cast(int, usage.get("deepseek_tokens"))
    cohere_units = cast(int, usage.get("cohere_search_units"))
    if deepseek_tokens > protocol.deepseek_token_cap or cohere_units != 0:
        raise ValueError("P10 Dev provider usage exceeds the approved contract")
    fallback_count = cast(int, component.get("fallback_count"))
    report = cast(dict[str, object], json.loads(report_path.read_text(encoding="utf-8")))
    report_body = cast(dict[str, object], report.get("report") or {})
    systems = cast(dict[str, dict[str, object]], report_body.get("systems") or {})
    fallback_count += cast(int, systems.get("q3", {}).get("fallback_count", 0))

    manifest = create_frozen_manifest(
        protocol=protocol,
        qa_dev_report_sha256=sha256_file(report_path),
        qa_gate_sha256=sha256_file(gate_path),
        component_dev_report_sha256=sha256_file(component_path),
        usage_audit_sha256=sha256_file(usage_path),
        workspace_sha256=_workspace_sha256(root),
        test_ids_sha256=sha256_file(root / "datasets/courserag_eval/v1/splits/test_ids.txt"),
        deepseek_dev_tokens=deepseek_tokens,
        gates_passed=True,
        fallback_count=fallback_count,
    )
    output_path = output_dir / "frozen_manifest.json"
    _write_atomic(output_path, manifest)
    return output_path


def run_dev_calibration(
    *,
    repository_root: Path,
    output_dir: Path,
    resume: bool = False,
) -> tuple[Path, Path, Path, Path | None]:
    root = repository_root.resolve()
    output_dir = output_dir.resolve()
    protocol_path = output_dir / "dev_calibration_protocol.json"
    protocol = _load_authorized_protocol(protocol_path)
    paths = _dev_paths(root)
    _validate_dev_inputs(paths, protocol)

    from core.settings import settings
    from evaluation.p09_systems import build_formal_p09_suite

    source = json.loads(paths["source_report"].read_text(encoding="utf-8"))
    fixed_results = _results(source, "q3")
    if not set(FRESH_CASE_IDS).issubset(fixed_results):
        raise ValueError("P10 source report does not contain every fresh Dev Case")
    run_dir = output_dir / "run-1"
    checkpoint_path = run_dir / "checkpoint.json" if resume else None
    restored_fresh_tokens = (
        _fresh_checkpoint_tokens(checkpoint_path) if checkpoint_path is not None else 0
    )
    suite = build_formal_p09_suite(
        root,
        settings,
        checkpoint_path=checkpoint_path,
        retrieval_snapshot_path=paths["snapshot"],
        max_deepseek_tokens=protocol.deepseek_token_cap,
        max_cohere_search_units=protocol.cohere_search_unit_cap,
        initial_deepseek_tokens=restored_fresh_tokens,
        label_suffix="p10-joint-calibration-v1",
        generation_reliability_enabled=True,
        generation_reliability_factoid_enabled=False,
    )
    system = P10DevDeltaSystem(
        fresh_system=suite.system("q3"),
        fixed_results=fixed_results,
        profile_sha256=protocol.candidate_profile_sha256,
    )
    report = run_p09_dev(
        repository_root=root,
        output_dir=run_dir,
        run_id="p10-joint-calibration-dev-run-1",
        systems={"q3": system},
        resume=resume,
        max_deepseek_tokens=protocol.deepseek_token_cap,
        max_cohere_search_units=protocol.cohere_search_unit_cap,
        governance_amendments=[
            {
                "p10_protocol_sha256": AUTHORIZED_PROTOCOL_SHA256,
                "p10_profile_sha256": protocol.candidate_profile_sha256,
                "fresh_case_count": len(FRESH_CASE_IDS),
                "reused_retrieval_main_count": protocol.reused_case_count,
                "retrieval_rerun": False,
                "test_access": False,
            }
        ],
    )
    gate_path = output_dir / "automatic_gate_report.json"
    _write_dev_gate(root, report, gate_path)
    usage_path = output_dir / "usage_audit.json"
    _write_usage_audit(report, usage_path, protocol)
    return report, gate_path, usage_path, None


def authorize_test_run(lock: P10TestLock, *, frozen_manifest_sha256: str) -> None:
    if lock.frozen_manifest_sha256 != frozen_manifest_sha256:
        raise ValueError("Test Lock does not match the Frozen Manifest")
    if not lock.external_budget_authorized:
        raise ValueError("Formal Test external budget is not authorized")


def _load_authorized_protocol(path: Path) -> P10DevCalibrationProtocol:
    if not path.is_file():
        raise FileNotFoundError("P10 Dev Calibration requires its authorized protocol")
    protocol = P10DevCalibrationProtocol.model_validate_json(path.read_text(encoding="utf-8"))
    if not protocol.external_data_authorized:
        raise ValueError("P10 Dev Calibration protocol is not externally authorized")
    if _model_sha256(protocol) != AUTHORIZED_PROTOCOL_SHA256:
        raise ValueError("P10 authorized Protocol identity changed")
    return protocol


def _dev_paths(root: Path) -> dict[str, Path]:
    return {
        "source_report": root / "storage_eval/p09_answer_grounding/run-1/report.json",
        "snapshot": root / "storage_eval/p09_gate_repair/b7_retrieval_snapshot.json",
        "profile": root / "resources/qa_profiles/p10_dev_joint_calibration_candidate_v1.json",
    }


def _validate_dev_inputs(paths: Mapping[str, Path], protocol: P10DevCalibrationProtocol) -> None:
    expected = {
        "source_report": SOURCE_REPORT_SHA256,
        "snapshot": RETRIEVAL_SNAPSHOT_SHA256,
        "profile": protocol.candidate_profile_sha256,
    }
    for key, digest in expected.items():
        path = paths[key]
        if not path.is_file() or sha256_file(path) != digest:
            raise ValueError(f"P10 Dev input identity differs: {key}")


def _write_dev_gate(root: Path, report_path: Path, output_path: Path) -> tuple[bool, int]:
    bundle = load_p09_dev_bundle(root / "datasets/courserag_eval/v1")
    main = [case for case in bundle.cases if case.qa.evaluation_stratum == "retrieval_main"]
    factoid = [case for case in main if case.qa.gold_answer_type == "factoid"]
    lists = [case for case in main if case.qa.gold_answer_type == "list"]
    payload = json.loads(report_path.read_text(encoding="utf-8"))
    q3 = _results(payload, "q3")
    metrics = _aggregate_cases(main, q3)
    factoid_metrics = _aggregate_cases(factoid, q3)
    list_contract_ok = len(lists) == 2 and all(
        q3[case.qa.record_id].answer_status == "answered"
        and bool(q3[case.qa.record_id].list_items)
        and len(q3[case.qa.record_id].claims) == len(q3[case.qa.record_id].list_items)
        and all(claim.evidence_ids for claim in q3[case.qa.record_id].claims)
        and bool(q3[case.qa.record_id].resolvable_citations)
        and all(q3[case.qa.record_id].resolvable_citations)
        for case in lists
    )
    fallback_count = int(payload["report"]["systems"]["q3"]["fallback_count"])
    checks = {
        "false_answer_count_0": _number(metrics, "false_answer_rate") == 0,
        "invalid_citation_count_0": _number(metrics, "citation_resolvability") == 1,
        "silent_fallback_count_0": fallback_count == 0,
        "citation_resolvability_1": _number(metrics, "citation_resolvability") == 1,
        "claim_citation_completeness_1": (_number(metrics, "claim_citation_completeness") == 1),
        "unanswerable_recall_1": _number(metrics, "unanswerable_recall") == 1,
        "qa_failure_count_0": _number(metrics, "qa_failure_rate") == 0,
        "factoid_token_f1_floor": (_number(factoid_metrics, "short_answer_token_f1") >= 0.406108),
        "all_list_cases_answered_with_cited_items": list_contract_ok,
        "dev_only": payload["report"].get("test_access") is False,
    }
    passed = all(checks.values())
    gate: dict[str, JsonValue] = {
        "schema_version": "courserag.p10-dev-calibration-gate.v1",
        "status": "passed_qa_calibration_component_pending"
        if passed
        else "failed_no_further_tuning",
        "protocol_sha256": AUTHORIZED_PROTOCOL_SHA256,
        "candidate_report_sha256": sha256_file(report_path),
        "fresh_case_ids": list(FRESH_CASE_IDS),
        "test_access": False,
        "post_result_tuning_allowed": False,
        "main_metrics": cast(dict[str, JsonValue], metrics),
        "factoid_metrics": cast(dict[str, JsonValue], factoid_metrics),
        "checks": cast(dict[str, JsonValue], checks),
    }
    atomic_write_json(output_path, gate)
    return passed, fallback_count


def _write_usage_audit(
    report_path: Path, output_path: Path, protocol: P10DevCalibrationProtocol
) -> None:
    results = _results(json.loads(report_path.read_text(encoding="utf-8")), "q3")
    total_tokens = sum(
        _json_int(results[case_id].usage.get("deepseek_total_tokens", 0))
        for case_id in FRESH_CASE_IDS
    )
    if total_tokens > protocol.deepseek_token_cap:
        raise RuntimeError("P10 Dev DeepSeek token cap exceeded")
    audit: dict[str, JsonValue] = {
        "schema_version": "courserag.p10-dev-calibration-usage.v1",
        "status": "within_authorized_limits",
        "fresh_case_count": len(FRESH_CASE_IDS),
        "deepseek_tokens": total_tokens,
        "deepseek_token_cap": protocol.deepseek_token_cap,
        "cohere_search_units": 0,
        "cohere_search_unit_cap": 0,
        "test_access": False,
    }
    atomic_write_json(output_path, audit)


def _fresh_checkpoint_tokens(path: Path) -> int:
    if not path.is_file():
        return 0
    payload = json.loads(path.read_text(encoding="utf-8"))
    cases = cast(dict[str, dict[str, object]], payload.get("cases", {}))
    total = 0
    for key, state in cases.items():
        if key.split(":", 1)[-1] not in FRESH_CASE_IDS or state.get("status") != "succeeded":
            continue
        result = cast(dict[str, object], state.get("result") or {})
        usage = cast(dict[str, JsonValue], result.get("usage") or {})
        total += _json_int(usage.get("deepseek_total_tokens"))
    return total


def _results(report: Mapping[str, object], variant: str) -> dict[str, P09SystemResult]:
    cases = cast(dict[str, dict[str, object]], report["cases"])
    return {
        key.split(":", 1)[1]: P09SystemResult.model_validate(state["result"])
        for key, state in cases.items()
        if key.startswith(f"{variant}:") and state.get("status") == "succeeded"
    }


def _workspace_sha256(root: Path) -> str:
    files: list[Path] = []
    for relative in ("src", "alembic", "resources", "datasets/schemas"):
        files.extend(
            path
            for path in (root / relative).rglob("*")
            if path.is_file()
            and "__pycache__" not in path.parts
            and path.suffix not in {".pyc", ".pyo"}
        )
    files.extend(root / name for name in ("pyproject.toml", "uv.lock", ".env.example"))
    digest = hashlib.sha256()
    for path in sorted(files, key=lambda value: value.relative_to(root).as_posix()):
        digest.update(path.relative_to(root).as_posix().encode())
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def _number(payload: Mapping[str, JsonValue], key: str) -> float:
    value = payload.get(key, 0.0)
    if isinstance(value, bool) or not isinstance(value, int | float | str):
        return 0.0
    return float(value)


def _json_int(value: JsonValue | None) -> int:
    if isinstance(value, bool) or not isinstance(value, int | float | str):
        return 0
    return int(value)


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _model_sha256(model: BaseModel) -> str:
    payload = json.dumps(model.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()


def _write_atomic(path: Path, model: BaseModel) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(
        model.model_dump(mode="json"), ensure_ascii=False, sort_keys=True, indent=2
    )
    descriptor, temporary = tempfile.mkstemp(prefix=".p10-", suffix=".json", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as output:
            output.write(payload + "\n")
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository-root", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--run-dev", action="store_true")
    parser.add_argument("--finalize-frozen-manifest", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--external-data-authorized", action="store_true")
    args = parser.parse_args()
    if args.finalize_frozen_manifest:
        if args.output_dir is None:
            parser.error("--finalize-frozen-manifest requires --output-dir")
        final_manifest = finalize_frozen_manifest(
            repository_root=args.repository_root,
            output_dir=args.output_dir,
        )
        print(
            json.dumps(
                {
                    "frozen_manifest": str(final_manifest),
                    "sha256": sha256_file(final_manifest),
                }
            )
        )
        return
    if args.run_dev:
        if args.output_dir is None:
            parser.error("--run-dev requires --output-dir")
        report, gate, usage, frozen = run_dev_calibration(
            repository_root=args.repository_root,
            output_dir=args.output_dir,
            resume=args.resume,
        )
        print(
            json.dumps(
                {
                    "report": str(report),
                    "gate": str(gate),
                    "usage": str(usage),
                    "frozen_manifest": str(frozen) if frozen else None,
                    "frozen_manifest_sha256": sha256_file(frozen) if frozen else None,
                }
            )
        )
        return
    if args.output is None:
        parser.error("protocol preparation requires --output")
    protocol = build_dev_protocol(
        args.repository_root.resolve(),
        external_data_authorized=args.external_data_authorized,
    )
    _write_atomic(args.output.resolve(), protocol)
    print(json.dumps({"protocol": str(args.output.resolve()), "sha256": _model_sha256(protocol)}))


if __name__ == "__main__":
    main()
