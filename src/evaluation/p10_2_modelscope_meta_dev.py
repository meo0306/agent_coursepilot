"""Single-use Approved-Dev qualifier for the owner-accepted ModelScope snapshot."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from courserag.security.prompt_guard import LocalPromptGuardDetector, load_prompt_guard_manifest
from courserag.security.prompt_injection import load_prompt_injection_profile
from courserag.security.windowing import SecurityWindowBuilder
from evaluation.p10_2_security_eval import run_dev_threshold_grid

PROTOCOL_SHA256 = "c1be800a5807d679d6b13ef41fe296f52cfac430cb59b851197e11da12eeaf8f"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-approved-dev", action="store_true")
    parser.add_argument(
        "--protocol",
        type=Path,
        default=Path(
            "resources/security_profiles/p10_2_modelscope_meta_dev_qualification_protocol.json"
        ),
    )
    parser.add_argument(
        "--model-dir",
        type=Path,
        default=Path(r"D:\AI\models\modelscope\LLM-Research\Llama-Prompt-Guard-2-86M"),
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path(
            "resources/security_profiles/"
            "modelscope_llm_research_llama_prompt_guard_2_86m_manifest.json"
        ),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("storage_eval/p10_2_security/dev_grid_report_modelscope_meta_r1.json"),
    )
    parser.add_argument(
        "--candidate",
        type=Path,
        default=Path(
            "resources/security_profiles/p10_2_modelscope_meta_decision_candidate_v1.json"
        ),
    )
    args = parser.parse_args()
    if not args.run_approved_dev:
        raise SystemExit(
            "refusing to consume the one-time qualification without --run-approved-dev"
        )
    if _sha256(args.protocol) != PROTOCOL_SHA256:
        raise SystemExit("qualification protocol differs from the owner-approved SHA-256")
    if args.output.exists() or args.candidate.exists():
        raise SystemExit("qualification output already exists; refusing to overwrite or rerun")
    manifest = load_prompt_guard_manifest(args.manifest)
    detector = LocalPromptGuardDetector(
        model_path=args.model_dir,
        manifest=manifest,
        device="cuda",
        dtype="float16",
        max_tokens=512,
        batch_size=16,
        timeout_seconds=300,
    )
    report, candidate = run_dev_threshold_grid(
        dataset_path=Path("datasets/courserag_eval/releases/p10_2_security/dev_candidate_r1.json"),
        approval_path=Path("datasets/courserag_eval/releases/p10_2_security/dev_approval.json"),
        detector=detector,
        window_builder=SecurityWindowBuilder(detector.tokenizer),
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
                "report_sha256": _sha256(report),
                "candidate": str(candidate.resolve()) if candidate else None,
                "candidate_sha256": _sha256(candidate) if candidate else None,
                "test_access": False,
                "blind_access": False,
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
