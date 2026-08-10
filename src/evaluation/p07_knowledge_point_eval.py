"""Approved-DS3 P07 Pilot Runner using P06 runtime Evidence as Provider input."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from functools import partial
from pathlib import Path
from typing import Literal, cast

from dotenv import load_dotenv
from pydantic import JsonValue

from courserag.chunking.tokenizer import LocalTokenizer
from courserag.domain.evidence import EvidenceArtifact, EvidenceRecord, normalize_evidence_text
from courserag.domain.knowledge_point import (
    KnowledgePointCandidate,
    SectionWindow,
    WindowEvidence,
    WindowExtractionResult,
)
from courserag.evals.knowledge_point_metrics import (
    knowledge_point_metric_report,
    match_knowledge_points,
    threshold_report,
)
from courserag.evals.p06_metrics import map_gold_to_system_evidence
from courserag.evals.schemas import (
    DS2EvidenceDataset,
    DS3KnowledgePointDataset,
    DS3SectionScopeDataset,
    DS3SplitManifest,
    P07GoldBundleApproval,
)
from courserag.knowledge_points.normalize import consolidate_candidates
from courserag.knowledge_points.profile import load_knowledge_point_profile
from courserag.knowledge_points.provider import (
    KnowledgePointProvider,
    KnowledgePointProviderResponseError,
    KnowledgePointProviderTransientError,
)
from courserag.knowledge_points.scoring import KnowledgePointScorer
from courserag.knowledge_points.windows import SectionSource, SectionWindowBuilder
from evaluation.contracts import DatasetSplit, FallbackPolicy, HashedArtifact, RunIntent
from evaluation.io import atomic_write_json
from evaluation.manifest import RunDatasetRef, RunManifest, sha256_file
from evaluation.p07_split_revision import (
    PROTOCOL_APPROVAL,
    PROTOCOL_CANDIDATE,
    REVISED_SPLIT,
    P07EvaluationProtocolApproval,
    P07EvaluationProtocolCandidate,
    _validate_artifact,
)
from evaluation.p07_threshold_freeze import (
    THRESHOLD_APPROVAL,
    THRESHOLD_CANDIDATE,
    P07ThresholdFreezeApproval,
    P07ThresholdFreezeCandidate,
)
from evaluation.p07_threshold_freeze import (
    _validate_artifact as _validate_threshold_artifact,
)
from evaluation.runner import EvaluationRunner

DATASET_ROOT = Path("datasets/courserag_eval/v1")
APPROVED_DS2 = DATASET_ROOT / "approved/ds2/p06_evidence.json"
APPROVED_DS3 = DATASET_ROOT / "approved/ds3/p07_knowledge_points.json"
P07_APPROVAL = DATASET_ROOT / "provenance/p07_gold_bundle_approval.json"
P07_SCOPES = DATASET_ROOT / "provenance/ds3_p07_section_scopes.json"
P07_SPLIT = REVISED_SPLIT
P06_OUTPUT = Path("storage_eval/p06_b1_b2/run-4/system_outputs.json")
P06_REPORT = Path("storage_eval/p06_b1_b2/run-4/report.json")
PROFILE_PATH = Path("resources/knowledge_point_profiles/default_v1.json")
TOKENIZER_PATH = Path("deepseek_v3_tokenizer/deepseek_v3_tokenizer/tokenizer.json")


def run_p07_pilot(
    *,
    repository_root: Path,
    output_dir: Path,
    run_id: str,
    split_side: Literal["calibration", "holdout"],
    provider: KnowledgePointProvider | None = None,
    resume: bool = False,
    provider_max_retries: int | None = None,
    provider_retry_base_seconds: float | None = None,
    provider_retry_max_seconds: float | None = None,
) -> Path:
    root = repository_root.resolve()
    output_dir = output_dir.resolve()
    dataset_root = (root / DATASET_ROOT).resolve()
    gold_path = root / APPROVED_DS3
    approval = P07GoldBundleApproval.model_validate_json(
        (root / P07_APPROVAL).read_text(encoding="utf-8")
    )
    if approval.approved_knowledge_points.sha256 != sha256_file(gold_path):
        raise ValueError("Approved DS3 file differs from exact Course Owner approval")
    protocol = _validated_protocol_approval(root)
    gold = DS3KnowledgePointDataset.model_validate_json(gold_path.read_text(encoding="utf-8"))
    if len(gold.knowledge_points) != 107 or any(
        item.review_status.value != "approved" for item in gold.knowledge_points
    ):
        raise ValueError("P07 Pilot requires all 107 human-approved DS3 records")
    scopes = DS3SectionScopeDataset.model_validate_json(
        (root / P07_SCOPES).read_text(encoding="utf-8")
    )
    split = DS3SplitManifest.model_validate_json((root / P07_SPLIT).read_text(encoding="utf-8"))
    mixed_scopes = mixed_split_scopes(gold, split)
    if mixed_scopes:
        raise ValueError("P07 r2 Protocol does not isolate Provider Section Windows")
    selected_ids = set(split.calibration_ids if split_side == "calibration" else split.holdout_ids)
    selected_gold = tuple(item for item in gold.knowledge_points if item.gold_kp_id in selected_ids)
    if len(selected_gold) != len(selected_ids):
        raise ValueError("P07 r2 Split references missing Approved Gold records")
    selected_scope_ids = {scope_id for item in selected_gold for scope_id in item.source_scope_ids}
    profile, prompt, prompt_sha256 = load_knowledge_point_profile(
        root / PROFILE_PATH, repository_root=root
    )
    threshold_approval = (
        _validated_threshold_approval(root, profile.scoring.threshold)
        if split_side == "holdout"
        else None
    )
    tokenizer = LocalTokenizer(
        root / TOKENIZER_PATH,
        tokenizer_id=profile.window.tokenizer_id,
        expected_sha256=profile.window.tokenizer_sha256,
    )
    p06_evidence, aliases, baseline_child_calls = _load_p06_runtime(root)
    windows = build_p07_windows(scopes, p06_evidence, aliases, profile.window, tokenizer)
    selected_windows = tuple(
        window for window in windows if window.section_id in selected_scope_ids
    )
    if not selected_windows:
        raise ValueError(f"P07 {split_side} partition has no Provider Windows")
    if provider is None:
        from core.settings import settings as configured_settings
        from courserag.infrastructure.knowledge_point_provider import (
            knowledge_point_provider_from_settings,
        )

        provider = knowledge_point_provider_from_settings()
        provider_max_retries = (
            configured_settings.COURSERAG_KP_MAX_RETRIES
            if provider_max_retries is None
            else provider_max_retries
        )
        provider_retry_base_seconds = (
            configured_settings.COURSERAG_KP_RETRY_BASE_SECONDS
            if provider_retry_base_seconds is None
            else provider_retry_base_seconds
        )
        provider_retry_max_seconds = (
            configured_settings.COURSERAG_KP_RETRY_MAX_SECONDS
            if provider_retry_max_seconds is None
            else provider_retry_max_seconds
        )
    provider_max_retries = provider_max_retries or 0
    provider_retry_base_seconds = provider_retry_base_seconds or 0.0
    provider_retry_max_seconds = provider_retry_max_seconds or 0.0
    commit, dirty = _git_state(root)
    inputs = [
        gold_path,
        root / P07_APPROVAL,
        root / P07_SCOPES,
        root / P07_SPLIT,
        root / PROTOCOL_CANDIDATE,
        root / PROTOCOL_APPROVAL,
        root / APPROVED_DS2,
        root / P06_OUTPUT,
        root / P06_REPORT,
        root / PROFILE_PATH,
        root / TOKENIZER_PATH,
        root / profile.prompt_relative_path,
    ]
    if threshold_approval is not None:
        inputs.extend((root / THRESHOLD_CANDIDATE, root / THRESHOLD_APPROVAL))
    manifest = RunManifest(
        run_id=run_id,
        created_at=datetime.now(UTC),
        dataset=RunDatasetRef(
            dataset_id="courserag-eval",
            dataset_version="v1",
            split=DatasetSplit.PILOT,
            manifest_sha256=sha256_file(dataset_root / "manifest.json"),
            split_sha256=sha256_file(dataset_root / "splits/pilot_ids.txt"),
        ),
        intent=RunIntent.TUNING if split_side == "calibration" else RunIntent.EVALUATION,
        tuning_enabled=split_side == "calibration",
        git_commit=commit,
        git_dirty=dirty,
        input_artifacts=[_artifact(root, item) for item in inputs],
        component_versions={
            "knowledge_point_provider": provider.provider_name,
            "knowledge_point_model": provider.model_name,
            "structured_output_method": provider.structured_output_method,
            "knowledge_point_profile": profile.version,
        },
        configuration={
            "profile_sha256": profile.profile_sha256,
            "prompt_sha256": prompt_sha256,
            "window_profile_sha256": profile.window.profile_sha256,
            "scoring_profile_sha256": profile.scoring.profile_sha256,
            "fixed_publish_threshold": profile.scoring.threshold,
            "evaluation_partition": split_side,
            "evaluation_protocol_bundle_sha256": protocol.protocol_bundle_sha256,
            "provider_fallback": False,
            "automatic_tuning": False,
            "split_isolation_status": "isolated",
            "provider_max_retries": provider_max_retries,
            "provider_retry_base_seconds": provider_retry_base_seconds,
            "provider_retry_max_seconds": provider_retry_max_seconds,
        },
        fallback_policy=FallbackPolicy.FAIL_RUN,
        random_seed=0,
        llm_as_judge=False,
    )
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
    _invalidate_saved_out_of_window_results(runner, selected_windows)
    results = tuple(
        WindowExtractionResult.model_validate(
            runner.run_case(
                window.window_id,
                window.content_sha256,
                partial(
                    _extract,
                    provider,
                    window,
                    prompt,
                    prompt_sha256,
                    profile.profile_sha256,
                    provider_max_retries,
                    provider_retry_base_seconds,
                    provider_retry_max_seconds,
                ),
            )
        )
        for window in selected_windows
    )
    drafts = consolidate_candidates(windows, results)
    scorer = KnowledgePointScorer(profile.scoring)
    scores = {item.stable_key: scorer.score(item) for item in drafts}
    matches, ambiguous = match_knowledge_points(selected_gold, drafts)
    ds2 = DS2EvidenceDataset.model_validate_json((root / APPROVED_DS2).read_text(encoding="utf-8"))
    evidence_matches = map_gold_to_system_evidence(
        ds2.evidence,
        p06_evidence,
        document_aliases=aliases,
    )
    evidence_adapter = {item.system_evidence_id: item.gold_evidence_id for item in evidence_matches}
    resolvable_evidence_ids = set(evidence_adapter.values())
    resolvable_kp_ids = {
        item.gold_kp_id
        for item in selected_gold
        if set(item.evidence_ids).issubset(resolvable_evidence_ids)
    }
    all_metrics = knowledge_point_metric_report(
        selected_gold,
        drafts,
        matches,
        evidence_adapter=evidence_adapter,
    )
    resolvable_metrics = knowledge_point_metric_report(
        selected_gold,
        drafts,
        matches,
        evidence_adapter=evidence_adapter,
        resolvable_gold_ids=resolvable_kp_ids,
    )
    evaluated_thresholds = (
        tuple(round(value / 100, 2) for value in range(50, 100, 5))
        if split_side == "calibration"
        else (profile.scoring.threshold,)
    )
    evaluated_threshold_report = threshold_report(
        selected_gold,
        drafts,
        matches,
        scores,
        evaluated_thresholds,
    )
    threshold_candidate = (
        max(
            evaluated_threshold_report,
            key=lambda row: (
                row["f1"],
                row["precision"],
                row["recall"],
                -abs(float(row["threshold"]) - profile.scoring.threshold),
                row["threshold"],
            ),
        )
        if split_side == "calibration"
        else None
    )
    system_payload: dict[str, JsonValue] = {
        "schema_version": "courserag.p07-system-output.v1",
        "window_results": cast(list[JsonValue], [item.model_dump(mode="json") for item in results]),
        "knowledge_points": cast(
            list[JsonValue], [item.model_dump(mode="json") for item in drafts]
        ),
        "publish_scores": cast(
            dict[str, JsonValue],
            {key: value.model_dump(mode="json") for key, value in scores.items()},
        ),
    }
    atomic_write_json(output_dir / "system_outputs.json", system_payload)
    provider_calls = len(results)
    report: dict[str, JsonValue] = {
        "evaluation_scope": f"approved_ds3_{split_side}",
        "evaluation_protocol_bundle_sha256": protocol.protocol_bundle_sha256,
        "evaluation_partition": split_side,
        "approved_ds3_sha256": sha256_file(gold_path),
        "approved_record_count": len(selected_gold),
        "section_scope_count": len(scopes.scopes),
        "selected_section_scope_count": len(selected_scope_ids),
        "section_window_count": len(selected_windows),
        "system_knowledge_point_count": len(drafts),
        "unambiguous_exact_match_count": len(matches),
        "ambiguous_match_count": len(ambiguous),
        "ambiguous_match_candidates": cast(
            list[JsonValue],
            [
                {
                    "system_stable_key": item.system_stable_key,
                    "candidate_gold_ids": list(item.candidate_gold_ids),
                    "reason": item.reason,
                }
                for item in ambiguous
            ],
        ),
        "all_gold_metrics": cast(dict[str, JsonValue], all_metrics),
        "p06_resolvable_gold_metrics": cast(dict[str, JsonValue], resolvable_metrics),
        "threshold_report": cast(list[JsonValue], list(evaluated_threshold_report)),
        "recommended_threshold_candidate": cast(JsonValue, threshold_candidate),
        "p06_resolvable_gold_count": len(resolvable_kp_ids),
        "provider_call_count": provider_calls,
        "full_pipeline_projected_provider_call_count": len(windows),
        "b0_child_chunk_call_proxy": baseline_child_calls,
        "full_pipeline_projected_call_reduction_ratio": round(
            1 - len(windows) / baseline_child_calls, 6
        )
        if baseline_child_calls
        else None,
        "usage": {
            "input_tokens": sum(item.usage.input_tokens or 0 for item in results),
            "output_tokens": sum(item.usage.output_tokens or 0 for item in results),
            "total_tokens": sum(item.usage.total_tokens or 0 for item in results),
        },
        "split_isolation": {
            "status": "passed",
            "mixed_scope_count": 0,
            "mixed_scope_ids": [],
            "calibration_or_holdout_metrics_emitted": True,
        },
        "fallback_used": False,
        "llm_as_judge_used": False,
        "gold_used_as_provider_input": False,
        "automatic_tuning": False,
        "threshold_change_applied": False,
        "human_approval_required_for_ambiguous_matches": bool(ambiguous),
    }
    runner.complete(report)
    return output_dir / "report.json"


def build_p07_windows(
    scopes: DS3SectionScopeDataset,
    evidence: Sequence[EvidenceRecord],
    document_aliases: Mapping[str, str],
    profile,
    tokenizer,
) -> tuple[SectionWindow, ...]:
    by_logical: dict[str, list[EvidenceRecord]] = {}
    for record in evidence:
        logical_id = document_aliases.get(record.document_id, record.document_id)
        by_logical.setdefault(logical_id, []).append(record)
    output: list[SectionWindow] = []
    builder = SectionWindowBuilder(profile, tokenizer)
    for scope in scopes.scopes:
        normalized_scope = normalize_evidence_text(scope.source_text)
        selected = [
            item
            for item in by_logical.get(scope.source_span.document_id, [])
            if normalize_evidence_text(item.text) in normalized_scope
        ]
        if not selected:
            raise ValueError(f"P06 runtime Evidence cannot resolve DS3 Scope {scope.scope_id}")
        source = SectionSource(
            knowledge_base_id=f"eval-kb-{scope.course_id}",
            course_id=scope.course_id,
            section_id=scope.scope_id,
            section_title=scope.title,
            evidence=tuple(
                WindowEvidence(
                    evidence_id=item.evidence_id,
                    text=item.text,
                    content_sha256=item.content_sha256,
                    ordinal=index,
                    block_id=item.source_units[0].block_id,
                    source_mode=item.source_mode,
                    confidence=item.confidence,
                    warning_codes=item.warning_codes,
                )
                for index, item in enumerate(selected)
            ),
        )
        output.extend(builder.build(source))
    return tuple(output)


def mixed_split_scopes(gold: DS3KnowledgePointDataset, split: DS3SplitManifest) -> tuple[str, ...]:
    calibration = set(split.calibration_ids)
    holdout = set(split.holdout_ids)
    scopes: dict[str, set[str]] = {}
    for item in gold.knowledge_points:
        label = "calibration" if item.gold_kp_id in calibration else "holdout"
        if item.gold_kp_id not in calibration | holdout:
            raise ValueError("DS3 split does not cover every Approved Knowledge Point")
        for scope_id in item.source_scope_ids:
            scopes.setdefault(scope_id, set()).add(label)
    return tuple(sorted(scope_id for scope_id, labels in scopes.items() if len(labels) > 1))


def _validated_protocol_approval(root: Path) -> P07EvaluationProtocolApproval:
    candidate_path = root / PROTOCOL_CANDIDATE
    approval_path = root / PROTOCOL_APPROVAL
    candidate = P07EvaluationProtocolCandidate.model_validate_json(
        candidate_path.read_text(encoding="utf-8")
    )
    approval = P07EvaluationProtocolApproval.model_validate_json(
        approval_path.read_text(encoding="utf-8")
    )
    if approval.protocol_bundle_sha256 != candidate.protocol_bundle_sha256:
        raise ValueError("P07 Protocol approval differs from the exact Candidate Bundle")
    _validate_artifact(root, approval.protocol_candidate)
    _validate_artifact(root, approval.revised_split)
    _validate_artifact(root, approval.approved_knowledge_points)
    if approval.protocol_candidate.sha256 != sha256_file(candidate_path):
        raise ValueError("P07 Protocol approval does not bind the current Candidate file")
    return approval


def _validated_threshold_approval(
    root: Path, configured_threshold: float
) -> P07ThresholdFreezeApproval:
    candidate_path = root / THRESHOLD_CANDIDATE
    approval_path = root / THRESHOLD_APPROVAL
    candidate = P07ThresholdFreezeCandidate.model_validate_json(
        candidate_path.read_text(encoding="utf-8")
    )
    approval = P07ThresholdFreezeApproval.model_validate_json(
        approval_path.read_text(encoding="utf-8")
    )
    if approval.candidate_bundle_sha256 != candidate.candidate_bundle_sha256:
        raise ValueError("P07 threshold approval differs from exact Candidate")
    if approval.approved_threshold != configured_threshold:
        raise ValueError("approved P07 threshold differs from configured Profile")
    _validate_threshold_artifact(root, approval.threshold_candidate)
    for artifact in (
        candidate.calibration_report,
        candidate.calibration_system_outputs,
        candidate.approved_knowledge_points,
    ):
        _validate_threshold_artifact(root, artifact)
    return approval


def _extract(
    provider: KnowledgePointProvider,
    window: SectionWindow,
    prompt: str,
    prompt_sha256: str,
    profile_sha256: str,
    max_retries: int,
    retry_base_seconds: float,
    retry_max_seconds: float,
) -> dict[str, JsonValue]:
    started = time.perf_counter()
    attempt = 0
    while True:
        try:
            extraction = provider.extract(window, prompt)
            _validate_candidate_evidence(window, extraction.candidates)
            break
        except KnowledgePointProviderTransientError:
            if attempt >= max_retries:
                raise
            delay = min(retry_max_seconds, retry_base_seconds * (2**attempt))
            attempt += 1
            time.sleep(delay)
    result = WindowExtractionResult(
        window_id=window.window_id,
        window_content_sha256=window.content_sha256,
        provider=provider.provider_name,
        model=provider.model_name,
        prompt_sha256=prompt_sha256,
        extractor_profile_sha256=profile_sha256,
        candidates=extraction.candidates,
        usage=extraction.usage,
        duration_ms=int((time.perf_counter() - started) * 1000),
    )
    return result.model_dump(mode="json")


def _validate_candidate_evidence(
    window: SectionWindow, candidates: Sequence[KnowledgePointCandidate]
) -> None:
    allowed = {item.evidence_id for item in window.evidence}
    for candidate in candidates:
        if any(item.evidence_id not in allowed for item in candidate.evidence_refs):
            raise KnowledgePointProviderResponseError(
                "Knowledge Point Candidate references Evidence outside its Window"
            )


def _invalidate_saved_out_of_window_results(
    runner: EvaluationRunner,
    windows: Sequence[SectionWindow],
) -> None:
    if not runner.resume:
        return
    for window in windows:
        saved = runner.state.cases.get(window.window_id)
        if saved is None or saved.status != "succeeded":
            continue
        result = WindowExtractionResult.model_validate(saved.result)
        try:
            _validate_candidate_evidence(window, result.candidates)
        except KnowledgePointProviderResponseError:
            runner.invalidate_succeeded_case(
                case_id=window.window_id,
                case_sha256=window.content_sha256,
                reason_code="out_of_window_evidence",
            )


def _load_p06_runtime(
    root: Path,
) -> tuple[tuple[EvidenceRecord, ...], dict[str, str], int]:
    outputs = json.loads((root / P06_OUTPUT).read_text(encoding="utf-8"))
    report_envelope = json.loads((root / P06_REPORT).read_text(encoding="utf-8"))
    report = report_envelope["report"]
    aliases = {str(key): str(value) for key, value in report["document_identity_adapter"].items()}
    selected: dict[str, EvidenceArtifact] = {}
    for raw in outputs["variants"]:
        artifact = EvidenceArtifact.model_validate(raw["evidence"])
        logical_id = aliases.get(artifact.document_id, artifact.document_id)
        selected[logical_id] = artifact
    evidence = tuple(record for artifact in selected.values() for record in artifact.records)
    return evidence, aliases, int(report["b2_child_count"])


def _artifact(root: Path, path: Path) -> HashedArtifact:
    resolved = path.resolve()
    return HashedArtifact(
        path=resolved.relative_to(root).as_posix(),
        sha256=sha256_file(resolved),
        size_bytes=resolved.stat().st_size,
        media_type="application/json" if resolved.suffix == ".json" else None,
    )


def _git_state(root: Path) -> tuple[str, bool]:
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    status = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    return commit, bool(status.strip())


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository-root", type=Path, default=Path.cwd())
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--split-side", choices=("calibration", "holdout"), required=True)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    args = parser.parse_args()
    env_path = (args.repository_root / args.env_file).resolve()
    if not env_path.is_file():
        raise FileNotFoundError("P07 Provider environment file is missing")
    load_dotenv(env_path, override=True)
    try:
        run_p07_pilot(
            repository_root=args.repository_root,
            output_dir=args.output_dir,
            run_id=args.run_id,
            split_side=args.split_side,
            resume=args.resume,
        )
    except Exception as exc:
        print(
            json.dumps(
                {
                    "status": "failed",
                    "error_type": type(exc).__name__,
                    "error_message": str(exc),
                },
                ensure_ascii=False,
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
