from __future__ import annotations

import hashlib
import json
import subprocess
from collections.abc import Mapping
from datetime import UTC, datetime
from functools import partial
from pathlib import Path
from typing import Protocol, cast

from pydantic import JsonValue

from courserag.evals.p08_metrics import aggregate_metrics, rejection_curve, retrieval_case_metrics
from courserag.evals.schemas import RetrievalQACase
from courserag.retrieval.ports import EmbeddingPort
from evaluation.contracts import DatasetSplit, FallbackPolicy, HashedArtifact, RunIntent
from evaluation.io import atomic_write_json
from evaluation.manifest import RunDatasetRef, RunManifest, sha256_file
from evaluation.p08_corpus import load_p08_child_corpus
from evaluation.p08_dev_loader import load_p08_tuning_cases
from evaluation.p08_systems import P08SystemResult, build_formal_p08_systems
from evaluation.runner import EvaluationRunner

APPROVED_BUNDLE_SHA256 = "ff64abba71d392496e7ce530f7de5c612794616557b65a7aa11e739e20759396"


class P08SearchSystem(Protocol):
    label: str

    def search(self, case: RetrievalQACase) -> P08SystemResult: ...


def run_p08_dev(
    *,
    repository_root: Path,
    output_dir: Path,
    run_id: str,
    systems: Mapping[str, P08SearchSystem],
    resume: bool = False,
) -> Path:
    root = repository_root.resolve()
    dataset_root = root / "datasets/courserag_eval/v1"
    cases = tuple(load_p08_tuning_cases(dataset_root))
    if len(cases) != 54 or any(
        case.split != "dev" or case.evaluation_stratum != "retrieval_main" for case in cases
    ):
        raise ValueError("P08 Runner requires exactly 54 retrieval_main Dev cases")
    if not systems:
        raise ValueError("P08 Runner requires at least one retrieval system")
    bundle_path = dataset_root / "provenance/p08_gold_bundle_manifest.json"
    bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
    if bundle.get("bundle_sha256") != APPROVED_BUNDLE_SHA256:
        raise ValueError("P08 Runner requires the exact Approved r3 Gold bundle")
    split_path = dataset_root / "provenance/p08_ds5_split_r3.json"
    approved_path = dataset_root / "approved/ds5/p08_retrieval.json"
    p06_output = root / "storage_eval/p06_b1_b2/run-4/system_outputs.json"
    p06_report = root / "storage_eval/p06_b1_b2/run-4/report.json"
    commit, dirty = _git_state(root)
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
        input_artifacts=[
            _artifact(root, item)
            for item in (bundle_path, split_path, approved_path, p06_output, p06_report)
        ],
        component_versions={name: system.label for name, system in sorted(systems.items())},
        configuration={
            "approved_bundle_sha256": APPROVED_BUNDLE_SHA256,
            "case_count": 54,
            "candidate_k": 30,
            "top_n": 8,
            "rrf_k": 60,
            "evaluation_failure_policy": "fail_sample",
            "test_access": False,
            "automatic_tuning": False,
        },
        fallback_policy=FallbackPolicy.FAIL_SAMPLE,
        random_seed=0,
        llm_as_judge=False,
    )
    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    atomic_write_json(output_dir / "run_manifest.json", manifest.model_dump(mode="json"))
    runner = EvaluationRunner(
        manifest=manifest,
        checkpoint_path=output_dir / "checkpoint.json",
        partial_report_path=output_dir / "partial_report.json",
        final_report_path=output_dir / "report.json",
        dataset_root=dataset_root,
        resume=resume,
    )
    rows: dict[str, dict[str, P08SystemResult]] = {}
    for system_name, system in sorted(systems.items()):
        for case in cases:
            key = f"{system_name}:{case.record_id}"
            result = P08SystemResult.model_validate(
                runner.run_case(
                    key,
                    _case_sha256(case, system_name),
                    partial(_execute_system, system, case),
                )
            )
            rows.setdefault(system_name, {})[case.record_id] = result
    report_systems: dict[str, JsonValue] = {}
    for system_name, by_case in rows.items():
        metric_rows = [retrieval_case_metrics(case, by_case[case.record_id].hits) for case in cases]
        report_systems[system_name] = cast(
            JsonValue,
            {
                "metrics": aggregate_metrics(metric_rows),
                "result_sha256": _system_result_sha256(by_case),
                "rejection_curve": rejection_curve(
                    cases, {case_id: result.hits for case_id, result in by_case.items()}
                ),
                "fallback_count": sum(item.fallback_applied for item in by_case.values()),
                "warning_count": sum(
                    warning != "RERANK_CACHE_HIT"
                    for item in by_case.values()
                    for warning in item.warnings
                ),
                "cache_hit_count": sum(
                    "RERANK_CACHE_HIT" in item.warnings for item in by_case.values()
                ),
                "provider_request_count": sum(
                    _usage_int(item, "request_count") for item in by_case.values()
                ),
                "provider_input_tokens": sum(
                    _usage_int(item, "input_tokens") for item in by_case.values()
                ),
                "provider_search_units": sum(
                    _usage_int(item, "search_units") for item in by_case.values()
                ),
                "stage_latency_ms": _latency_summary(by_case),
            },
        )
    runner.complete(
        cast(
            dict[str, JsonValue],
            {
                "evaluation_scope": "approved_p08_r3_retrieval_main_dev_only",
                "approved_bundle_sha256": APPROVED_BUNDLE_SHA256,
                "case_count": 54,
                "test_access": False,
                "systems": report_systems,
            },
        )
    )
    return output_dir / "report.json"


def write_freeze_candidate(report_paths: list[Path], output_path: Path) -> str:
    if len(report_paths) != 2:
        raise ValueError("P08 Freeze Candidate requires exactly two independent Run reports")
    reports = [json.loads(path.read_text(encoding="utf-8")) for path in report_paths]
    if any(report.get("status") != "completed" for report in reports):
        raise ValueError("P08 Freeze Candidate requires completed reports")
    identities = {report.get("run_identity_sha256") for report in reports}
    if len(identities) != 1:
        raise ValueError("P08 reproducibility reports have different configurations")
    first_systems = reports[0]["report"]["systems"]
    second_systems = reports[1]["report"]["systems"]
    first_hashes = {name: item["result_sha256"] for name, item in first_systems.items()}
    second_hashes = {name: item["result_sha256"] for name, item in second_systems.items()}
    if first_hashes != second_hashes:
        raise ValueError("P08 repeated Runs produced different ranked results")
    threshold_candidates = {
        name: _best_threshold(item["rejection_curve"])
        for name, item in first_systems.items()
        if name.startswith("b5_")
    }
    payload: dict[str, JsonValue] = {
        "schema_version": "courserag.p08-freeze-candidate.v1",
        "status": "pending_course_owner_selection",
        "approved_gold_bundle_sha256": APPROVED_BUNDLE_SHA256,
        "report_sha256": [sha256_file(path) for path in report_paths],
        "run_identity_sha256": str(next(iter(identities))),
        "system_result_sha256": first_hashes,
        "provider_threshold_candidates": cast(dict[str, JsonValue], threshold_candidates),
        "selection_rule": "provider-specific metrics, latency and cost; no cross-provider score threshold",
        "default_profile_written": False,
    }
    atomic_write_json(output_path, payload)
    return sha256_file(output_path)


def run_formal_p08_candidate(
    *,
    repository_root: Path,
    output_dir: Path,
    embedding_key_rotated: bool,
    external_data_authorized: bool,
) -> tuple[Path, Path, str]:
    if not embedding_key_rotated:
        raise RuntimeError("Formal P08 is blocked until the exposed Embedding key is rotated")
    from core.settings import settings
    from courserag.indexing.dense import (
        LocalSentenceTransformerEmbeddingAdapter,
        OpenAICompatibleEmbeddingAdapter,
    )

    if settings.COURSERAG_EMBEDDING_MODEL is None:
        raise ValueError("Formal P08 CourseRAG Embedding model is missing")
    embedder: EmbeddingPort
    if settings.COURSERAG_EMBEDDING_PROVIDER == "local_sentence_transformers":
        if (
            settings.COURSERAG_EMBEDDING_MODEL_PATH is None
            or settings.COURSERAG_EMBEDDING_MODEL_BUNDLE_SHA256 is None
            or settings.COURSERAG_EMBEDDING_WEIGHTS_SHA256 is None
        ):
            raise ValueError("Formal P08 local Embedding configuration is incomplete")
        embedder = LocalSentenceTransformerEmbeddingAdapter(
            model_path=settings.COURSERAG_EMBEDDING_MODEL_PATH,
            model_name=settings.COURSERAG_EMBEDDING_MODEL,
            model_bundle_sha256=settings.COURSERAG_EMBEDDING_MODEL_BUNDLE_SHA256,
            weights_sha256=settings.COURSERAG_EMBEDDING_WEIGHTS_SHA256,
            device=settings.COURSERAG_EMBEDDING_DEVICE,
            dtype=settings.COURSERAG_EMBEDDING_DTYPE,
            max_length=settings.COURSERAG_EMBEDDING_MAX_LENGTH,
            batch_size=settings.COURSERAG_EMBEDDING_LOCAL_BATCH_SIZE,
            query_prompt_name=settings.COURSERAG_EMBEDDING_QUERY_PROMPT_NAME,
        )
    elif settings.COURSERAG_EMBEDDING_PROVIDER == "openai-compatible":
        if (
            settings.COURSERAG_EMBEDDING_BASE_URL is None
            or settings.COURSERAG_EMBEDDING_API_KEY is None
        ):
            raise ValueError("Formal P08 remote Embedding configuration is incomplete")
        if not external_data_authorized:
            raise RuntimeError("Formal P08 requires authorization for remote Embedding excerpts")
        embedder = OpenAICompatibleEmbeddingAdapter(
            endpoint=str(settings.COURSERAG_EMBEDDING_BASE_URL),
            api_key=settings.COURSERAG_EMBEDDING_API_KEY.get_secret_value(),
            model=settings.COURSERAG_EMBEDDING_MODEL,
            timeout_seconds=settings.COURSERAG_EMBEDDING_TIMEOUT_SECONDS,
        )
    else:
        raise ValueError("Formal P08 requires an enabled Embedding Provider")
    corpus = load_p08_child_corpus(repository_root)
    systems = build_formal_p08_systems(
        corpus_by_course=corpus,
        embedder=embedder,
        settings=settings,
    )
    first = run_p08_dev(
        repository_root=repository_root,
        output_dir=output_dir / "run-1",
        run_id="p08-formal-run-1",
        systems=systems,
    )
    second = run_p08_dev(
        repository_root=repository_root,
        output_dir=output_dir / "run-2",
        run_id="p08-formal-run-2",
        systems=systems,
    )
    candidate_path = output_dir / "freeze_candidate.json"
    candidate_sha256 = write_freeze_candidate([first, second], candidate_path)
    return first, second, candidate_sha256


def _latency_summary(by_case: Mapping[str, P08SystemResult]) -> dict[str, JsonValue]:
    stages = {name for result in by_case.values() for name in result.stage_latency_ms}
    output: dict[str, JsonValue] = {}
    for stage in sorted(stages):
        values = sorted(result.stage_latency_ms.get(stage, 0) for result in by_case.values())
        output[stage] = {
            "p50": _percentile(values, 0.50),
            "p95": _percentile(values, 0.95),
        }
    return output


def _execute_system(system: P08SearchSystem, case: RetrievalQACase) -> JsonValue:
    return cast(JsonValue, system.search(case).model_dump(mode="json"))


def _usage_int(result: P08SystemResult, key: str) -> int:
    value = result.usage.get(key, 0)
    return int(value) if isinstance(value, int | float | str) else 0


def _system_result_sha256(by_case: Mapping[str, P08SystemResult]) -> str:
    payload = {
        case_id: [hit.model_dump(mode="json") for hit in result.hits]
        for case_id, result in sorted(by_case.items())
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _best_threshold(curve: list[dict[str, float]]) -> dict[str, float]:
    return max(curve, key=lambda item: (item["answerability_accuracy"], -item["threshold"]))


def _percentile(values: list[int], fraction: float) -> int:
    if not values:
        return 0
    return values[min(len(values) - 1, math_ceil(len(values) * fraction) - 1)]


def math_ceil(value: float) -> int:
    integer = int(value)
    return integer if integer == value else integer + 1


def _case_sha256(case: RetrievalQACase, system_name: str) -> str:
    payload = json.dumps(
        {"system": system_name, "case": case.model_dump(mode="json")},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return hashlib.sha256(payload).hexdigest()


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
