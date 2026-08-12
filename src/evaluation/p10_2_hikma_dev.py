"""Single-use Approved-Dev runner for the HikmaAI ONNX backup candidate."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from courserag.security.onnx_prompt_guard import OnnxPromptGuardDetector
from courserag.security.prompt_guard import load_prompt_guard_manifest
from courserag.security.prompt_injection import load_prompt_injection_profile
from courserag.security.windowing import SecurityWindowBuilder
from evaluation.p10_2_security_eval import run_dev_threshold_grid


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-approved-dev", action="store_true")
    parser.add_argument(
        "--model-dir",
        type=Path,
        default=Path(
            r"D:\AI\models\huggingface\HikmaAI\hikmaai-mdeberta-v3-base-prompt-injection-multilingual"
        ),
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path(
            "resources/security_profiles/"
            "hikmaai_mdeberta_v3_base_prompt_injection_multilingual_fp16_manifest.json"
        ),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("storage_eval/p10_2_security/dev_grid_report_hikma_r1.json"),
    )
    parser.add_argument(
        "--candidate",
        type=Path,
        default=Path("resources/security_profiles/p10_2_hikma_decision_candidate_v1.json"),
    )
    args = parser.parse_args()
    if not args.run_approved_dev:
        raise SystemExit(
            "refusing to consume the single Approved-Dev run without --run-approved-dev"
        )
    if args.output.exists() or args.candidate.exists():
        raise SystemExit(
            "single Approved-Dev output already exists; refusing to overwrite or rerun"
        )
    manifest = load_prompt_guard_manifest(args.manifest)
    detector = OnnxPromptGuardDetector(
        model_path=args.model_dir,
        manifest=manifest,
        device="cuda",
        max_tokens=512,
        batch_size=16,
        timeout_seconds=300,
    )
    builder = SecurityWindowBuilder(detector.tokenizer)
    report, candidate = run_dev_threshold_grid(
        dataset_path=Path("datasets/courserag_eval/releases/p10_2_security/dev_candidate_r1.json"),
        approval_path=Path("datasets/courserag_eval/releases/p10_2_security/dev_approval.json"),
        detector=detector,
        window_builder=builder,
        auxiliary_rules=load_prompt_injection_profile(
            "resources/security_profiles/prompt_injection_candidate_v2.json"
        ),
        model_manifest_sha256=manifest.sha256,
        output_path=args.output,
        candidate_profile_path=args.candidate,
    )
    print(
        json.dumps(
            {
                "report": str(report.resolve()),
                "report_sha256": hashlib.sha256(report.read_bytes()).hexdigest(),
                "candidate": str(candidate.resolve()) if candidate else None,
                "candidate_sha256": (
                    hashlib.sha256(candidate.read_bytes()).hexdigest() if candidate else None
                ),
                "test_access": False,
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
