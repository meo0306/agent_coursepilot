"""Locked, one-shot P10 formal Test orchestration.

This module is intentionally separate from the Dev runner: Test resolution is impossible until
both the global dataset lock and the P10 frozen-manifest authorization exist.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Mapping
from datetime import UTC, datetime
from functools import partial
from pathlib import Path
from typing import cast

from pydantic import JsonValue

from courserag.evals.p08_metrics import (
    aggregate_metrics,
    rejection_curve,
    retrieval_case_metrics,
)
from courserag.indexing.dense import LocalSentenceTransformerEmbeddingAdapter
from evaluation.contracts import (
    DatasetSplit,
    FallbackPolicy,
    RunIntent,
    TestLock,
)
from evaluation.datasets import COURSERAG_SPECS, load_dataset_inventory
from evaluation.guard import approved_inventory_sha256, split_ids_sha256
from evaluation.io import atomic_write_json
from evaluation.manifest import RunDatasetRef, RunManifest, sha256_file
from evaluation.p08_corpus import load_p08_child_corpus
from evaluation.p08_retrieval_eval import (
    _case_sha256 as _p08_case_sha256,
)
from evaluation.p08_retrieval_eval import (
    _execute_system as _execute_p08_system,
)
from evaluation.p08_retrieval_eval import (
    _latency_summary,
    _system_result_sha256,
    _usage_int,
)
from evaluation.p08_systems import P08SystemResult, build_formal_p08_systems
from evaluation.p09_dev_loader import load_p09_test_bundle
from evaluation.p09_retrieval_qa_eval import (
    P09EvaluationSystem,
    P09SystemResult,
    _artifact,
    _case_hash,
    _execute_system,
    _git_state,
    _system_report,
)
from evaluation.p10_component_eval import run_component_test
from evaluation.p10_eval import (
    P10FrozenManifest,
    P10TestLock,
    _workspace_sha256,
    authorize_test_run,
)
from evaluation.runner import EvaluationRunner

FORMAL_DEEPSEEK_TOKEN_CAP = 1_500_000
FORMAL_COHERE_SEARCH_UNIT_CAP = 240
FORMAL_SYSTEMS = ("b6", "b7", "b8", "q0", "q1", "q2", "q3")


def write_test_locks(
    *,
    repository_root: Path,
    output_dir: Path,
    frozen_manifest_sha256: str,
    owner_approval_sha256: str,
) -> tuple[Path, Path]:
    """Create both locks after exact owner approval, without resolving Test content."""

    root = repository_root.resolve()
    output_dir = output_dir.resolve()
    frozen_path = output_dir / "frozen_manifest.json"
    if sha256_file(frozen_path) != frozen_manifest_sha256:
        raise ValueError("Owner approval does not match the P10 Frozen Manifest")
    frozen = P10FrozenManifest.model_validate_json(frozen_path.read_text(encoding="utf-8"))
    if frozen.workspace_sha256 != _workspace_sha256(root):
        raise ValueError("Workspace identity changed after P10 freeze")
    p10_lock = P10TestLock(
        frozen_manifest_sha256=frozen_manifest_sha256,
        owner_approval_sha256=owner_approval_sha256,
        external_budget_authorized=True,
    )
    authorize_test_run(p10_lock, frozen_manifest_sha256=frozen_manifest_sha256)

    dataset_root = root / "datasets/courserag_eval/v1"
    test_ids = set((dataset_root / "splits/test_ids.txt").read_text(encoding="utf-8").split())
    inventory = load_dataset_inventory(dataset_root, COURSERAG_SPECS)
    dataset_lock = TestLock(
        dataset_id="courserag-eval",
        dataset_version="v1",
        locked=True,
        test_ids_sha256=split_ids_sha256(test_ids),
        approved_manifest_sha256=approved_inventory_sha256(inventory),
        locked_at=datetime.now(UTC),
        locked_by="course_owner",
    )
    p10_lock_path = output_dir / "test_authorization.json"
    dataset_lock_path = dataset_root / "test.lock.json"
    atomic_write_json(p10_lock_path, p10_lock.model_dump(mode="json"))
    atomic_write_json(dataset_lock_path, dataset_lock.model_dump(mode="json"))
    return p10_lock_path, dataset_lock_path


def run_formal_qa_test(
    *,
    repository_root: Path,
    output_dir: Path,
    resume: bool = False,
) -> Path:
    """Run the frozen B6-B8/Q0-Q3 Test track with fail-closed Provider behavior."""

    root = repository_root.resolve()
    output_dir = output_dir.resolve()
    frozen_path = root / "storage_eval/p10/frozen_manifest.json"
    authorization_path = root / "storage_eval/p10/test_authorization.json"
    frozen_sha256 = sha256_file(frozen_path)
    frozen = P10FrozenManifest.model_validate_json(frozen_path.read_text(encoding="utf-8"))
    authorization = P10TestLock.model_validate_json(authorization_path.read_text(encoding="utf-8"))
    authorize_test_run(authorization, frozen_manifest_sha256=frozen_sha256)
    if frozen.workspace_sha256 != _workspace_sha256(root):
        raise ValueError("Formal Test workspace differs from the Frozen Manifest")
    commit, dirty = _git_state(root)
    if dirty:
        raise ValueError("Formal Test requires a clean Git worktree")

    dataset_root = root / "datasets/courserag_eval/v1"
    bundle = load_p09_test_bundle(dataset_root)
    run_dir = output_dir / "qa-run-1"
    manifest_path = run_dir / "run_manifest.json"
    checkpoint_path = run_dir / "checkpoint.json" if resume else None
    from core.settings import settings
    from evaluation.p09_systems import build_formal_p09_suite

    suite = build_formal_p09_suite(
        root,
        settings,
        checkpoint_path=checkpoint_path,
        max_deepseek_tokens=FORMAL_DEEPSEEK_TOKEN_CAP,
        max_cohere_search_units=FORMAL_COHERE_SEARCH_UNIT_CAP,
        label_suffix="p10-locked-test-v1",
        generation_reliability_enabled=True,
        generation_reliability_factoid_enabled=False,
    )
    systems = {name: suite.system(name) for name in FORMAL_SYSTEMS}
    if resume:
        manifest = RunManifest.model_validate_json(manifest_path.read_text(encoding="utf-8"))
        expected_versions = {name: value.label for name, value in sorted(systems.items())}
        if manifest.component_versions != expected_versions:
            raise ValueError("Formal Test Resume system versions changed")
    else:
        manifest = _formal_manifest(
            root=root,
            dataset_root=dataset_root,
            frozen_path=frozen_path,
            authorization_path=authorization_path,
            systems=systems,
            commit=commit,
        )
        run_dir.mkdir(parents=True, exist_ok=True)
        atomic_write_json(manifest_path, manifest.model_dump(mode="json"))

    runner = EvaluationRunner(
        manifest=manifest,
        checkpoint_path=run_dir / "checkpoint.json",
        partial_report_path=run_dir / "partial_report.json",
        final_report_path=run_dir / "report.json",
        dataset_root=dataset_root,
        resume=resume,
    )
    outputs: dict[str, dict[str, P09SystemResult]] = {}
    for system_name, system in sorted(systems.items()):
        for case in bundle.cases:
            key = f"{system_name}:{case.qa.record_id}"
            result = P09SystemResult.model_validate(
                runner.run_case(
                    key,
                    _case_hash(case, system_name),
                    partial(_execute_system, system, case),
                )
            )
            if result.fallback_applied:
                raise RuntimeError("Formal P10 Test contains a forbidden Fallback")
            outputs.setdefault(system_name, {})[case.qa.record_id] = result
    report_systems = {
        name: _system_report(bundle.cases, values) for name, values in outputs.items()
    }
    deepseek_tokens, cohere_units = _formal_usage(report_systems)
    if deepseek_tokens > FORMAL_DEEPSEEK_TOKEN_CAP:
        raise RuntimeError("Formal P10 Test exceeded the DeepSeek token cap")
    if cohere_units > FORMAL_COHERE_SEARCH_UNIT_CAP:
        raise RuntimeError("Formal P10 Test exceeded the Cohere Search Unit cap")
    runner.complete(
        cast(
            dict[str, JsonValue],
            {
                "scope": "approved_p10_locked_test_b6_b8_q0_q3",
                "frozen_manifest_sha256": frozen_sha256,
                "test_access": True,
                "test_case_count": len(bundle.cases),
                "retrieval_main_count": bundle.retrieval_main_count,
                "upstream_gap_diagnostic_count": bundle.upstream_gap_diagnostic_count,
                "post_result_tuning_allowed": False,
                "deepseek_tokens": deepseek_tokens,
                "deepseek_token_cap": FORMAL_DEEPSEEK_TOKEN_CAP,
                "cohere_search_units": cohere_units,
                "cohere_search_unit_cap": FORMAL_COHERE_SEARCH_UNIT_CAP,
                "systems": report_systems,
            },
        )
    )
    return run_dir / "report.json"


def run_formal_retrieval_test(
    *, repository_root: Path, output_dir: Path, resume: bool = False
) -> Path:
    """Run B3-B5 on the exact locked Test slice with local embedding and Cohere."""

    root = repository_root.resolve()
    output_dir = output_dir.resolve()
    frozen_path = root / "storage_eval/p10/frozen_manifest.json"
    authorization_path = root / "storage_eval/p10/test_authorization.json"
    frozen_sha256 = sha256_file(frozen_path)
    frozen = P10FrozenManifest.model_validate_json(frozen_path.read_text(encoding="utf-8"))
    authorization = P10TestLock.model_validate_json(authorization_path.read_text(encoding="utf-8"))
    authorize_test_run(authorization, frozen_manifest_sha256=frozen_sha256)
    if frozen.workspace_sha256 != _workspace_sha256(root):
        raise ValueError("Formal Retrieval Test workspace differs from the Frozen Manifest")
    commit, dirty = _git_state(root)
    if dirty:
        raise ValueError("Formal Retrieval Test requires a clean Git worktree")
    dataset_root = root / "datasets/courserag_eval/v1"
    bundle = load_p09_test_bundle(dataset_root)
    cases = tuple(item.retrieval for item in bundle.cases)
    run_dir = output_dir / "retrieval-run-1"
    checkpoint_path = run_dir / "checkpoint.json"

    from core.settings import settings

    formal_settings = settings.model_copy(
        update={"COURSERAG_COHERE_MAX_SEARCH_UNITS": FORMAL_COHERE_SEARCH_UNIT_CAP}
    )
    embedder = LocalSentenceTransformerEmbeddingAdapter(
        model_path=str(formal_settings.COURSERAG_EMBEDDING_MODEL_PATH),
        model_name=str(formal_settings.COURSERAG_EMBEDDING_MODEL),
        model_bundle_sha256=str(formal_settings.COURSERAG_EMBEDDING_MODEL_BUNDLE_SHA256),
        weights_sha256=str(formal_settings.COURSERAG_EMBEDDING_WEIGHTS_SHA256),
        device=formal_settings.COURSERAG_EMBEDDING_DEVICE,
        dtype=formal_settings.COURSERAG_EMBEDDING_DTYPE,
        max_length=formal_settings.COURSERAG_EMBEDDING_MAX_LENGTH,
        batch_size=formal_settings.COURSERAG_EMBEDDING_LOCAL_BATCH_SIZE,
        query_prompt_name=formal_settings.COURSERAG_EMBEDDING_QUERY_PROMPT_NAME,
    )
    all_systems = build_formal_p08_systems(
        corpus_by_course=load_p08_child_corpus(root),
        embedder=embedder,
        settings=formal_settings,
        initial_cohere_search_units=(_restored_p08_cohere_units(checkpoint_path) if resume else 0),
        reranker_candidates=frozenset({"cohere"}),
    )
    systems = {name: all_systems[name] for name in ("b3_dense", "b4_hybrid_rrf", "b5_cohere")}
    manifest_path = run_dir / "run_manifest.json"
    if resume:
        manifest = RunManifest.model_validate_json(manifest_path.read_text(encoding="utf-8"))
        if manifest.component_versions != {
            name: value.label for name, value in sorted(systems.items())
        }:
            raise ValueError("Formal Retrieval Test Resume system versions changed")
    else:
        dataset_lock_path = dataset_root / "test.lock.json"
        manifest = RunManifest(
            run_id="p10-formal-retrieval-test-run-1",
            created_at=datetime.now(UTC),
            dataset=RunDatasetRef(
                dataset_id="courserag-eval",
                dataset_version="v1",
                split=DatasetSplit.TEST,
                manifest_sha256=sha256_file(dataset_root / "manifest.json"),
                split_sha256=sha256_file(dataset_root / "splits/test_ids.txt"),
                test_lock_sha256=sha256_file(dataset_lock_path),
            ),
            intent=RunIntent.EVALUATION,
            tuning_enabled=False,
            git_commit=commit,
            git_dirty=False,
            input_artifacts=[
                _artifact(root, path)
                for path in (
                    frozen_path,
                    authorization_path,
                    dataset_lock_path,
                    dataset_root / "approved/ds5/p08_retrieval.json",
                    dataset_root / "splits/test_ids.txt",
                )
            ],
            component_versions={name: value.label for name, value in sorted(systems.items())},
            configuration={
                "frozen_manifest_sha256": frozen_sha256,
                "case_count": 40,
                "retrieval_main_count": 36,
                "upstream_gap_diagnostic_count": 4,
                "candidate_k": 30,
                "top_n": 8,
                "rrf_k": 60,
                "cohere_max_search_units": FORMAL_COHERE_SEARCH_UNIT_CAP,
                "post_result_tuning_allowed": False,
            },
            fallback_policy=FallbackPolicy.FAIL_SAMPLE,
            random_seed=0,
            llm_as_judge=False,
        )
        run_dir.mkdir(parents=True, exist_ok=True)
        atomic_write_json(manifest_path, manifest.model_dump(mode="json"))
    runner = EvaluationRunner(
        manifest=manifest,
        checkpoint_path=checkpoint_path,
        partial_report_path=run_dir / "partial_report.json",
        final_report_path=run_dir / "report.json",
        dataset_root=dataset_root,
        resume=resume,
    )
    rows: dict[str, dict[str, P08SystemResult]] = {}
    for system_name, system in sorted(systems.items()):
        for case in cases:
            result = P08SystemResult.model_validate(
                runner.run_case(
                    f"{system_name}:{case.record_id}",
                    _p08_case_sha256(case, system_name),
                    partial(_execute_p08_system, system, case),
                )
            )
            if result.fallback_applied:
                raise RuntimeError("Formal P10 Retrieval Test contains a forbidden Fallback")
            rows.setdefault(system_name, {})[case.record_id] = result
    main = tuple(case for case in cases if case.evaluation_stratum == "retrieval_main")
    diagnostic = tuple(
        case for case in cases if case.evaluation_stratum == "upstream_gap_diagnostic"
    )
    report_systems: dict[str, JsonValue] = {}
    for name, values in rows.items():
        search_units = sum(_usage_int(item, "search_units") for item in values.values())
        if search_units > FORMAL_COHERE_SEARCH_UNIT_CAP:
            raise RuntimeError("Formal Retrieval Test exceeded the Cohere Search Unit cap")
        report_systems[name] = cast(
            JsonValue,
            {
                "retrieval_main_metrics": aggregate_metrics(
                    [retrieval_case_metrics(case, values[case.record_id].hits) for case in main]
                ),
                "upstream_gap_diagnostic_metrics": aggregate_metrics(
                    [
                        retrieval_case_metrics(case, values[case.record_id].hits)
                        for case in diagnostic
                    ]
                ),
                "result_sha256": _system_result_sha256(values),
                "rejection_curve": rejection_curve(
                    main, {case_id: result.hits for case_id, result in values.items()}
                ),
                "fallback_count": 0,
                "provider_search_units": search_units,
                "stage_latency_ms": _latency_summary(values),
            },
        )
    runner.complete(
        cast(
            dict[str, JsonValue],
            {
                "scope": "approved_p10_locked_test_b3_b5",
                "frozen_manifest_sha256": frozen_sha256,
                "test_access": True,
                "post_result_tuning_allowed": False,
                "systems": report_systems,
            },
        )
    )
    return run_dir / "report.json"


def run_formal_component_test(*, repository_root: Path, output_dir: Path) -> Path:
    """Run the locked local DS6/DS7/Security Test controls with no Provider calls."""

    root = repository_root.resolve()
    frozen_path = root / "storage_eval/p10/frozen_manifest.json"
    authorization_path = root / "storage_eval/p10/test_authorization.json"
    frozen_sha256 = sha256_file(frozen_path)
    frozen = P10FrozenManifest.model_validate_json(frozen_path.read_text(encoding="utf-8"))
    authorization = P10TestLock.model_validate_json(authorization_path.read_text(encoding="utf-8"))
    authorize_test_run(authorization, frozen_manifest_sha256=frozen_sha256)
    if frozen.workspace_sha256 != _workspace_sha256(root):
        raise ValueError("Formal Component Test workspace differs from the Frozen Manifest")
    _, dirty = _git_state(root)
    if dirty:
        raise ValueError("Formal Component Test requires a clean Git worktree")
    return run_component_test(root, output_dir.resolve() / "component_test_report.json")


def _formal_manifest(
    *,
    root: Path,
    dataset_root: Path,
    frozen_path: Path,
    authorization_path: Path,
    systems: Mapping[str, P09EvaluationSystem],
    commit: str,
) -> RunManifest:
    dataset_lock_path = dataset_root / "test.lock.json"
    inputs = (
        frozen_path,
        authorization_path,
        dataset_lock_path,
        dataset_root / "provenance/p09_gold_bundle_approval.json",
        dataset_root / "approved/ds5/p08_retrieval.json",
        dataset_root / "approved/ds5/p09_qa.json",
        dataset_root / "approved/ds5/p09_context.json",
        dataset_root / "splits/test_ids.txt",
    )
    return RunManifest(
        run_id="p10-formal-test-run-1",
        created_at=datetime.now(UTC),
        dataset=RunDatasetRef(
            dataset_id="courserag-eval",
            dataset_version="v1",
            split=DatasetSplit.TEST,
            manifest_sha256=sha256_file(dataset_root / "manifest.json"),
            split_sha256=sha256_file(dataset_root / "splits/test_ids.txt"),
            test_lock_sha256=sha256_file(dataset_lock_path),
        ),
        intent=RunIntent.EVALUATION,
        tuning_enabled=False,
        git_commit=commit,
        git_dirty=False,
        input_artifacts=[_artifact(root, path) for path in inputs],
        component_versions={name: value.label for name, value in sorted(systems.items())},
        configuration={
            "frozen_manifest_sha256": sha256_file(frozen_path),
            "case_count": 40,
            "retrieval_main_count": 36,
            "upstream_gap_diagnostic_count": 4,
            "context_max_items": 8,
            "context_max_tokens": 4000,
            "deepseek_max_total_tokens": FORMAL_DEEPSEEK_TOKEN_CAP,
            "cohere_max_search_units": FORMAL_COHERE_SEARCH_UNIT_CAP,
            "post_result_tuning_allowed": False,
        },
        fallback_policy=FallbackPolicy.FAIL_SAMPLE,
        random_seed=0,
        llm_as_judge=False,
    )


def _formal_usage(systems: Mapping[str, Mapping[str, JsonValue]]) -> tuple[int, int]:
    deepseek = 0
    cohere = 0
    for value in systems.values():
        usage = cast(dict[str, JsonValue], value.get("usage") or {})
        raw_deepseek = usage.get("deepseek_total_tokens", 0)
        raw_cohere = usage.get("cohere_search_units", 0)
        if isinstance(raw_deepseek, int | float | str) and not isinstance(raw_deepseek, bool):
            deepseek += int(raw_deepseek)
        if isinstance(raw_cohere, int | float | str) and not isinstance(raw_cohere, bool):
            cohere = max(cohere, int(raw_cohere))
    return deepseek, cohere


def _restored_p08_cohere_units(checkpoint_path: Path) -> int:
    if not checkpoint_path.is_file():
        return 0
    payload = cast(dict[str, object], json.loads(checkpoint_path.read_text(encoding="utf-8")))
    cases = cast(dict[str, dict[str, object]], payload.get("cases") or {})
    total = 0
    for key, state in cases.items():
        if not key.startswith("b5_cohere:") or state.get("status") != "succeeded":
            continue
        result = cast(dict[str, object], state.get("result") or {})
        usage = cast(dict[str, JsonValue], result.get("usage") or {})
        raw = usage.get("search_units", 0)
        if isinstance(raw, int | float | str) and not isinstance(raw, bool):
            total += int(raw)
    return total


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the locked P10 formal Test protocol")
    parser.add_argument(
        "stage",
        choices=("prepare-locks", "retrieval", "qa", "component", "all"),
    )
    parser.add_argument("--repository-root", type=Path, default=Path.cwd())
    parser.add_argument("--output-dir", type=Path, default=Path("storage_eval/p10/formal"))
    parser.add_argument("--frozen-manifest-sha256")
    parser.add_argument("--owner-approval-sha256")
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    root = args.repository_root.resolve()
    output_dir = (root / args.output_dir).resolve()

    if args.stage == "prepare-locks":
        if not args.frozen_manifest_sha256 or not args.owner_approval_sha256:
            parser.error(
                "prepare-locks requires --frozen-manifest-sha256 and --owner-approval-sha256"
            )
        paths = write_test_locks(
            repository_root=root,
            output_dir=root / "storage_eval/p10",
            frozen_manifest_sha256=args.frozen_manifest_sha256,
            owner_approval_sha256=args.owner_approval_sha256,
        )
        print(json.dumps({"test_authorization": str(paths[0]), "test_lock": str(paths[1])}))
        return

    results: dict[str, str] = {}
    if args.stage in {"retrieval", "all"}:
        results["retrieval"] = str(
            run_formal_retrieval_test(
                repository_root=root,
                output_dir=output_dir,
                resume=args.resume,
            )
        )
    if args.stage in {"qa", "all"}:
        results["qa"] = str(
            run_formal_qa_test(
                repository_root=root,
                output_dir=output_dir,
                resume=args.resume,
            )
        )
    if args.stage in {"component", "all"}:
        results["component"] = str(
            run_formal_component_test(repository_root=root, output_dir=output_dir)
        )
    print(json.dumps(results, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
