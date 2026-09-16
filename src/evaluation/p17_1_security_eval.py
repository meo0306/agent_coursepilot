"""Owner-gated local calibration for the P17.1 dual-hypothesis detector."""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from pydantic import JsonValue, TypeAdapter

from core.settings import settings
from courserag.domain.document import (
    BlockIR,
    PageIR,
    ParsedDocumentIR,
    SourceSpan,
    sha256_text,
)
from courserag.indexing.dense import LocalSentenceTransformerEmbeddingAdapter
from courserag.security.detector import SecurityTextWindow
from courserag.security.dual_hypothesis import (
    DualHypothesisSecurityEnsemble,
    DualHypothesisWindowScore,
    EmbeddingPortSecurityEncoder,
    load_dual_hypothesis_profile,
)
from courserag.security.onnx_prompt_guard import OnnxPromptGuardDetector
from courserag.security.prompt_guard import load_prompt_guard_manifest
from courserag.security.windowing import SecurityWindowBuilder
from evaluation.io import atomic_write_json
from evaluation.p17_1_security_data import P171CalibrationCase, P171CalibrationDataset

DEFAULT_DATASET = Path(
    "datasets/courserag_eval/releases/p17_1_security/candidates/calibration_candidate_r1.json"
)
DEFAULT_REVIEW = Path(
    "datasets/courserag_eval/releases/p17_1_security/reviews/calibration_review_template_r1.json"
)
DEFAULT_PROFILE = Path("resources/security_profiles/p17_1_dual_hypothesis_candidate_v1.json")
DEFAULT_HIKMA_MANIFEST = Path(
    "resources/security_profiles/"
    "hikmaai_mdeberta_v3_base_prompt_injection_multilingual_fp16_manifest.json"
)
DEFAULT_HIKMA_MODEL = Path(
    r"D:\AI\models\huggingface\HikmaAI\hikmaai-mdeberta-v3-base-prompt-injection-multilingual"
)
DEFAULT_OUTPUT = Path("storage_eval/p17_1_security/calibration_report_r1.json")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-approved-calibration", action="store_true")
    parser.add_argument("--run-approved-diagnostic-repair", action="store_true")
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--review", type=Path, default=DEFAULT_REVIEW)
    parser.add_argument("--profile", type=Path, default=DEFAULT_PROFILE)
    parser.add_argument("--hikma-manifest", type=Path, default=DEFAULT_HIKMA_MANIFEST)
    parser.add_argument("--hikma-model", type=Path, default=DEFAULT_HIKMA_MODEL)
    parser.add_argument("--hikma-device", choices=("cpu", "cuda"), default="cpu")
    parser.add_argument("--expected-dataset-sha256", required=True)
    parser.add_argument("--expected-review-sha256", required=True)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    if args.run_approved_calibration == args.run_approved_diagnostic_repair:
        raise SystemExit("select exactly one approved P17.1/P17.2 run mode")
    if args.output.exists():
        raise SystemExit("P17.1 Calibration output exists; refusing rerun/overwrite")
    if _sha256(args.dataset) != args.expected_dataset_sha256:
        raise SystemExit("P17.1 Calibration dataset differs from owner-approved SHA-256")
    if _sha256(args.review) != args.expected_review_sha256:
        raise SystemExit("P17.1 Calibration review differs from owner-approved SHA-256")
    dataset = P171CalibrationDataset.model_validate_json(args.dataset.read_text(encoding="utf-8"))
    _validate_review(dataset, args.dataset, args.review)
    ensemble, window_builder = _build_runtime(
        profile_path=args.profile,
        hikma_manifest_path=args.hikma_manifest,
        hikma_model_path=args.hikma_model,
        hikma_device=args.hikma_device,
    )
    report = run_calibration(
        dataset=dataset,
        dataset_path=args.dataset,
        review_path=args.review,
        profile_path=args.profile,
        ensemble=ensemble,
        window_builder=window_builder,
        diagnostic_repair=args.run_approved_diagnostic_repair,
    )
    atomic_write_json(args.output, TypeAdapter(JsonValue).validate_python(report))
    print(
        json.dumps(
            {
                "report": str(args.output.resolve()),
                "report_sha256": _sha256(args.output),
                "status": report["status"],
                "consumed_blind_access": False,
                "external_provider_calls": 0,
            },
            sort_keys=True,
        )
    )


def run_calibration(
    *,
    dataset: P171CalibrationDataset,
    dataset_path: Path,
    review_path: Path,
    profile_path: Path,
    ensemble: DualHypothesisSecurityEnsemble,
    window_builder: SecurityWindowBuilder,
    diagnostic_repair: bool = False,
) -> dict[str, Any]:
    started = time.perf_counter()
    documents: dict[str, ParsedDocumentIR] = {}
    windows_by_record: dict[str, tuple[SecurityTextWindow, ...]] = {}
    all_windows: list[SecurityTextWindow] = []
    for case in dataset.cases:
        document = _document(case)
        windows = window_builder.build(document)
        documents[case.record_id] = document
        windows_by_record[case.record_id] = windows
        all_windows.extend(windows)
    scores = ensemble.score(tuple(all_windows))
    score_by_window = {score.window_id: score for score in scores}
    cases_with_scores = []
    for case in dataset.cases:
        record_scores = [
            score_by_window[window.window_id] for window in windows_by_record[case.record_id]
        ]
        if not record_scores:
            raise ValueError(f"P17.1 Calibration case produced no windows: {case.record_id}")
        representative = max(record_scores, key=lambda item: item.attack_score)
        cases_with_scores.append((case, representative))
    component_scores = [_component_record(case, score) for case, score in cases_with_scores]
    if diagnostic_repair:
        finalists, diagnostic_frontier = select_diagnostic_repair_candidates(
            tuple(cases_with_scores), limit=1
        )
    else:
        finalists = select_calibration_candidates(tuple(cases_with_scores), limit=2)
        diagnostic_frontier = []
    status = "candidate_ready" if finalists else "calibration_failed"
    return {
        "schema_version": (
            "courserag.p17-2-security-diagnostic-repair-report.v1"
            if diagnostic_repair
            else "courserag.p17-1-security-calibration-report.v1"
        ),
        "status": status,
        "dataset_sha256": _sha256(dataset_path),
        "review_sha256": _sha256(review_path),
        "base_profile_sha256": _sha256(profile_path),
        "base_profile_canonical_sha256": ensemble.profile.sha256,
        "record_count": len(dataset.cases),
        "calibration_objective": (
            "maximize_min_language_and_family_recall_subject_to_specificity_gte_0_975"
        ),
        "run_mode": "diagnostic_repair" if diagnostic_repair else "calibration",
        "finalist_limit": 1 if diagnostic_repair else 2,
        "finalists": finalists,
        "diagnostic_frontier": diagnostic_frontier,
        "component_scores": component_scores if diagnostic_repair else [],
        "construction_group_folds": 5,
        "scoring_seconds": time.perf_counter() - started,
        "runtime_network": False,
        "external_provider_calls": 0,
        "fallbacks": 0,
        "consumed_blind_access": False,
        "qualification_access": False,
    }


def select_calibration_candidates(
    cases_with_scores: tuple[tuple[P171CalibrationCase, DualHypothesisWindowScore], ...],
    *,
    limit: int,
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for threshold_step in range(45, 86):
        threshold = threshold_step / 100
        for margin_step in range(-10, 31):
            margin = margin_step / 100
            metrics = _candidate_metrics(cases_with_scores, threshold, margin)
            if float(metrics["specificity"]) < 0.975:
                continue
            candidates.append(
                {
                    "attack_threshold": threshold,
                    "minimum_margin": margin,
                    **metrics,
                }
            )
    candidates.sort(
        key=lambda item: (
            -float(item["minimum_group_recall"]),
            -float(item["recall"]),
            -float(item["specificity"]),
            float(item["attack_threshold"]),
            float(item["minimum_margin"]),
        )
    )
    return candidates[:limit]


def select_diagnostic_repair_candidates(
    cases_with_scores: tuple[tuple[P171CalibrationCase, DualHypothesisWindowScore], ...],
    *,
    limit: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Search soft-feature weights without invoking either local model again."""

    eligible: list[dict[str, Any]] = []
    frontier: list[dict[str, Any]] = []

    def ordering(item: dict[str, Any]) -> tuple[float, ...]:
        return (
            -float(item["minimum_group_recall"]),
            -float(item["recall"]),
            -float(item["specificity"]),
            abs(float(item["minimum_margin"])),
            -float(item["attack_threshold"]),
            -float(item["structured_weight"]),
        )

    for hikma_step in range(2, 7):
        hikma_weight = hikma_step / 10
        for semantic_step in range(2, 8):
            attack_semantic_weight = semantic_step / 10
            structured_weight = 1 - hikma_weight - attack_semantic_weight
            if structured_weight < 0 or structured_weight > 0.4:
                continue
            for safe_semantic_step in range(4, 10):
                safe_semantic_weight = safe_semantic_step / 10
                scope_weight = 1 - safe_semantic_weight
                weighted = tuple(
                    (
                        case,
                        _weighted_hypotheses(
                            score,
                            hikma_weight=hikma_weight,
                            attack_semantic_weight=attack_semantic_weight,
                            structured_weight=structured_weight,
                            safe_semantic_weight=safe_semantic_weight,
                            scope_weight=scope_weight,
                        ),
                    )
                    for case, score in cases_with_scores
                )
                malicious = [values for case, values in weighted if case.label == "malicious"]
                # Under the frozen Recall=1 requirement, these are the strictest
                # possible cut-offs. Lower values can only reduce specificity.
                threshold = min(attack for attack, _safe in malicious) - 1e-9
                margin = min(attack - safe for attack, safe in malicious) - 1e-9
                metrics = _weighted_candidate_metrics(weighted, threshold, margin)
                candidate = {
                    "hikma_weight": hikma_weight,
                    "attack_semantic_weight": attack_semantic_weight,
                    "structured_weight": round(structured_weight, 10),
                    "safe_semantic_weight": safe_semantic_weight,
                    "scope_weight": round(scope_weight, 10),
                    "attack_threshold": threshold,
                    "minimum_margin": margin,
                    **metrics,
                }
                if (
                    float(metrics["recall"]) == 1
                    and float(metrics["minimum_group_recall"]) == 1
                    and float(metrics["specificity"]) >= 0.975
                ):
                    eligible.append(candidate)
                frontier.append(candidate)
    eligible.sort(key=ordering)
    frontier.sort(key=ordering)
    return eligible[:limit], frontier[:10]


def _weighted_hypotheses(
    score: DualHypothesisWindowScore,
    *,
    hikma_weight: float,
    attack_semantic_weight: float,
    structured_weight: float,
    safe_semantic_weight: float,
    scope_weight: float,
) -> tuple[float, float]:
    attack = (
        hikma_weight * score.hikma_score
        + attack_semantic_weight * score.attack_semantic_score
        + structured_weight * score.structured_score
    )
    safe = safe_semantic_weight * score.safe_semantic_score + scope_weight * score.scope_score
    return attack, safe


def _weighted_candidate_metrics(
    weighted: tuple[tuple[P171CalibrationCase, tuple[float, float]], ...],
    threshold: float,
    margin: float,
) -> dict[str, Any]:
    overall: Counter[str] = Counter()
    malicious_groups: dict[str, Counter[str]] = defaultdict(Counter)
    folds: dict[int, Counter[str]] = defaultdict(Counter)
    false_positive_ids: list[str] = []
    false_negative_ids: list[str] = []
    for case, (attack, safe) in weighted:
        predicted = attack >= threshold and attack - safe >= margin
        expected = case.label == "malicious"
        outcome = _outcome(expected, predicted)
        overall[outcome] += 1
        if outcome == "fp":
            false_positive_ids.append(case.record_id)
        elif outcome == "fn":
            false_negative_ids.append(case.record_id)
        if expected:
            malicious_groups[f"language:{case.language}"][outcome] += 1
            malicious_groups[f"family:{case.family}"][outcome] += 1
        fold = int(hashlib.sha256(case.construction_group.encode()).hexdigest()[:8], 16) % 5
        folds[fold][outcome] += 1
    metrics = _metrics(overall)
    group_recalls = {
        name: _metrics(counts)["recall"] for name, counts in sorted(malicious_groups.items())
    }
    return {
        **metrics,
        "minimum_group_recall": min(group_recalls.values()),
        "group_recall": group_recalls,
        "fold_metrics": {str(fold): _metrics(folds[fold]) for fold in range(5)},
        "false_positive_ids": false_positive_ids,
        "false_negative_ids": false_negative_ids,
    }


def _component_record(
    case: P171CalibrationCase, score: DualHypothesisWindowScore
) -> dict[str, Any]:
    return {
        "record_id": case.record_id,
        "label": case.label,
        "language": case.language,
        "family": case.family,
        "construction_group": case.construction_group,
        "scope": score.scope,
        "hikma_score": score.hikma_score,
        "attack_semantic_score": score.attack_semantic_score,
        "safe_semantic_score": score.safe_semantic_score,
        "structured_score": score.structured_score,
        "scope_score": score.scope_score,
        "attack_prototype_id": score.attack_prototype_id,
        "safe_prototype_id": score.safe_prototype_id,
    }


def _candidate_metrics(
    cases_with_scores: tuple[tuple[P171CalibrationCase, DualHypothesisWindowScore], ...],
    threshold: float,
    margin: float,
) -> dict[str, Any]:
    overall: Counter[str] = Counter()
    malicious_groups: dict[str, Counter[str]] = defaultdict(Counter)
    folds: dict[int, Counter[str]] = defaultdict(Counter)
    for case, score in cases_with_scores:
        predicted = score.attack_score >= threshold and score.decision_margin >= margin
        expected = case.label == "malicious"
        outcome = _outcome(expected, predicted)
        overall[outcome] += 1
        if expected:
            malicious_groups[f"language:{case.language}"][outcome] += 1
            malicious_groups[f"family:{case.family}"][outcome] += 1
        fold = int(hashlib.sha256(case.construction_group.encode()).hexdigest()[:8], 16) % 5
        folds[fold][outcome] += 1
    metrics = _metrics(overall)
    group_recalls = {
        name: _metrics(counts)["recall"] for name, counts in sorted(malicious_groups.items())
    }
    fold_metrics = {str(fold): _metrics(folds[fold]) for fold in range(5)}
    return {
        **metrics,
        "minimum_group_recall": min(group_recalls.values()),
        "group_recall": group_recalls,
        "fold_metrics": fold_metrics,
    }


def _build_runtime(
    *,
    profile_path: Path,
    hikma_manifest_path: Path,
    hikma_model_path: Path,
    hikma_device: str,
) -> tuple[DualHypothesisSecurityEnsemble, SecurityWindowBuilder]:
    required = (
        settings.COURSERAG_EMBEDDING_MODEL_PATH,
        settings.COURSERAG_EMBEDDING_MODEL,
        settings.COURSERAG_EMBEDDING_MODEL_BUNDLE_SHA256,
        settings.COURSERAG_EMBEDDING_WEIGHTS_SHA256,
    )
    if not all(required):
        raise SystemExit("P17.1 Calibration requires the frozen local Qwen3 configuration")
    embedder = LocalSentenceTransformerEmbeddingAdapter(
        model_path=str(settings.COURSERAG_EMBEDDING_MODEL_PATH),
        model_name=str(settings.COURSERAG_EMBEDDING_MODEL),
        model_bundle_sha256=str(settings.COURSERAG_EMBEDDING_MODEL_BUNDLE_SHA256),
        weights_sha256=str(settings.COURSERAG_EMBEDDING_WEIGHTS_SHA256),
        device=settings.COURSERAG_EMBEDDING_DEVICE,
        dtype=settings.COURSERAG_EMBEDDING_DTYPE,
        max_length=settings.COURSERAG_EMBEDDING_MAX_LENGTH,
        batch_size=settings.COURSERAG_EMBEDDING_LOCAL_BATCH_SIZE,
        query_prompt_name=settings.COURSERAG_EMBEDDING_QUERY_PROMPT_NAME,
    )
    semantic_encoder = EmbeddingPortSecurityEncoder(embedder)
    manifest = load_prompt_guard_manifest(hikma_manifest_path)
    hikma = OnnxPromptGuardDetector(
        model_path=hikma_model_path,
        manifest=manifest,
        device=hikma_device,
        max_tokens=512,
        batch_size=16,
        timeout_seconds=1200,
    )
    profile = load_dual_hypothesis_profile(profile_path)
    ensemble = DualHypothesisSecurityEnsemble(
        profile=profile,
        hikma_detector=hikma,
        semantic_encoder=semantic_encoder,
    )
    return ensemble, SecurityWindowBuilder(hikma.tokenizer)


def _validate_review(
    dataset: P171CalibrationDataset, dataset_path: Path, review_path: Path
) -> None:
    review = json.loads(review_path.read_text(encoding="utf-8"))
    if review.get("review_status") != "owner_approved":
        raise SystemExit("P17.1 Calibration review is not owner-approved")
    if review.get("dataset_sha256") != _sha256(dataset_path):
        raise SystemExit("P17.1 Calibration review does not bind the exact dataset")
    decisions = review.get("decisions")
    if not isinstance(decisions, list):
        raise SystemExit("P17.1 Calibration review decisions are missing")
    by_id = {item.get("record_id"): item for item in decisions if isinstance(item, dict)}
    expected_ids = {case.record_id for case in dataset.cases}
    if set(by_id) != expected_ids or any(
        by_id[record_id].get("decision") != "pass" for record_id in expected_ids
    ):
        raise SystemExit("P17.1 Calibration requires one PASS decision per case")


def _document(case: P171CalibrationCase) -> ParsedDocumentIR:
    block_id = f"{case.record_id}-block-1"
    block = BlockIR(
        block_id=block_id,
        block_type="paragraph",
        text=case.text,
        order_index=0,
        source_span=SourceSpan(
            document_id=case.record_id,
            document_version_id=f"{case.record_id}-version",
            page_start=1,
            page_end=1,
            block_start_id=block_id,
            block_end_id=block_id,
            char_start=0,
            char_end=len(case.text),
        ),
        content_sha256=sha256_text(case.text),
    )
    return ParsedDocumentIR(
        document_id=case.record_id,
        document_version_id=f"{case.record_id}-version",
        document_sha256=sha256_text(case.text),
        source_format="pdf",
        parser_profile="p17_1_security_calibration",
        parser_version="1",
        pages=(
            PageIR(
                page_id=f"{case.record_id}-page-1",
                physical_page_index=1,
                width=100,
                height=100,
                source_mode="native_text",
                blocks=(block,),
                content_sha256=sha256_text(case.text),
            ),
        ),
        sections=(),
    )


def _outcome(expected: bool, predicted: bool) -> str:
    if expected and predicted:
        return "tp"
    if expected:
        return "fn"
    if predicted:
        return "fp"
    return "tn"


def _metrics(counts: Counter[str]) -> dict[str, float | int]:
    tp, fn, fp, tn = (counts[key] for key in ("tp", "fn", "fp", "tn"))
    return {
        "tp": tp,
        "fn": fn,
        "fp": fp,
        "tn": tn,
        "recall": tp / (tp + fn) if tp + fn else 1.0,
        "specificity": tn / (tn + fp) if tn + fp else 1.0,
    }


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


if __name__ == "__main__":
    main()
