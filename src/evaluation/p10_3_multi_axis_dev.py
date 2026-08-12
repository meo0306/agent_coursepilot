"""Single-use owner-approved P10.3 real multi-axis Qualification Dev runner."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from courserag.security.ensemble import MultiAxisSecurityEnsemble, load_multi_axis_profile
from courserag.security.multi_axis import SemanticModelAxis
from courserag.security.onnx_prompt_guard import OnnxPromptGuardDetector
from courserag.security.prompt_guard import LocalPromptGuardDetector, load_prompt_guard_manifest
from courserag.security.structured_axes import StructuredCapabilityAxes
from courserag.security.windowing import SecurityWindowBuilder
from evaluation.p10_3_security_eval import run_qualification_dev


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-approved-qualification-dev", action="store_true")
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--expected-protocol-sha256", required=True)
    parser.add_argument(
        "--dataset",
        type=Path,
        default=Path(
            "datasets/courserag_eval/releases/p10_3_security/qualification_dev_candidate_r1.json"
        ),
    )
    parser.add_argument(
        "--approval",
        type=Path,
        default=Path("datasets/courserag_eval/releases/p10_3_security/dev_approval.json"),
    )
    parser.add_argument(
        "--profile",
        type=Path,
        default=Path("resources/security_profiles/p10_3_multi_axis_candidate_v1.json"),
    )
    parser.add_argument(
        "--hikma-dir",
        type=Path,
        default=Path(
            r"D:\AI\models\huggingface\HikmaAI\hikmaai-mdeberta-v3-base-prompt-injection-multilingual"
        ),
    )
    parser.add_argument(
        "--llama-dir",
        type=Path,
        default=Path(r"D:\AI\models\modelscope\LLM-Research\Llama-Prompt-Guard-2-86M"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("storage_eval/p10_3_security/qualification_dev_report_r1.json"),
    )
    parser.add_argument(
        "--candidate-output",
        type=Path,
        default=Path("resources/security_profiles/p10_3_multi_axis_default_candidate_v1.json"),
    )
    args = parser.parse_args()
    if not args.run_approved_qualification_dev:
        raise SystemExit("refusing P10.3 Dev without explicit run flag")
    if _sha256(args.protocol) != args.expected_protocol_sha256:
        raise SystemExit("P10.3 Protocol differs from owner-approved SHA-256")
    protocol = json.loads(args.protocol.read_text(encoding="utf-8"))
    _validate_protocol(
        protocol,
        dataset=args.dataset,
        profile=args.profile,
        approval=args.approval,
    )
    profile = load_multi_axis_profile(args.profile)
    hikma_axis = next(
        axis for axis in profile.axes if axis.axis_id == "general_untrusted_instruction"
    )
    override_axis = next(axis for axis in profile.axes if axis.axis_id == "policy_override")
    assert hikma_axis.decision_threshold is not None
    assert override_axis.decision_threshold is not None
    hikma_manifest = load_prompt_guard_manifest(
        "resources/security_profiles/hikmaai_mdeberta_v3_base_prompt_injection_multilingual_fp16_manifest.json"
    )
    llama_manifest = load_prompt_guard_manifest(
        "resources/security_profiles/modelscope_llm_research_llama_prompt_guard_2_86m_manifest.json"
    )
    hikma_detector = OnnxPromptGuardDetector(
        model_path=args.hikma_dir,
        manifest=hikma_manifest,
        device="cuda",
        max_tokens=512,
        batch_size=16,
        timeout_seconds=300,
    )
    llama_detector = LocalPromptGuardDetector(
        model_path=args.llama_dir,
        manifest=llama_manifest,
        device="cuda",
        dtype="float16",
        max_tokens=512,
        batch_size=16,
        timeout_seconds=300,
    )
    ensemble = MultiAxisSecurityEnsemble(
        profile,
        (
            SemanticModelAxis(
                hikma_detector,
                axis_id="general_untrusted_instruction",
                decision_threshold=hikma_axis.decision_threshold,
            ),
            SemanticModelAxis(
                llama_detector,
                axis_id="policy_override",
                decision_threshold=override_axis.decision_threshold,
            ),
            StructuredCapabilityAxes(),
        ),
    )
    report, candidate = run_qualification_dev(
        dataset_path=args.dataset,
        approval_path=args.approval,
        ensemble=ensemble,
        window_builder=SecurityWindowBuilder(hikma_detector.tokenizer),
        output_path=args.output,
        candidate_profile_path=args.candidate_output,
    )
    print(
        json.dumps(
            {
                "report": str(report.resolve()),
                "report_sha256": _sha256(report),
                "candidate": str(candidate.resolve()) if candidate else None,
                "candidate_sha256": _sha256(candidate) if candidate else None,
                "blind_access": False,
                "test_access": False,
            },
            sort_keys=True,
        )
    )


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _validate_protocol(
    protocol: object,
    *,
    dataset: Path,
    profile: Path,
    approval: Path | None = None,
) -> None:
    if not isinstance(protocol, dict):
        raise SystemExit("P10.3 Protocol must be a JSON object")
    if (
        protocol.get("maximum_runs") != 1
        or protocol.get("blind_access") is not False
        or protocol.get("test_access") is not False
        or protocol.get("external_provider_calls") != 0
        or protocol.get("fallbacks") != 0
        or protocol.get("runtime_network") is not False
    ):
        raise SystemExit("P10.3 Protocol does not enforce one local Dev and no Blind/Test access")
    if protocol.get("dataset_sha256") != _sha256(dataset):
        raise SystemExit("P10.3 dataset differs from Protocol")
    if approval is not None and protocol.get("approval_sha256") != _sha256(approval):
        raise SystemExit("P10.3 Dev Approval differs from Protocol")
    if protocol.get("profile_file_sha256") != _sha256(profile):
        raise SystemExit("P10.3 Profile file differs from Protocol")
    loaded_profile = load_multi_axis_profile(profile)
    if protocol.get("profile_canonical_sha256") != loaded_profile.sha256:
        raise SystemExit("P10.3 canonical Profile differs from Protocol")
    identities = protocol.get("model_identities")
    if not isinstance(identities, dict):
        raise SystemExit("P10.3 Protocol model identities are missing")
    _validate_manifest_identity(
        identities,
        key="hikma",
        path=Path(
            "resources/security_profiles/"
            "hikmaai_mdeberta_v3_base_prompt_injection_multilingual_fp16_manifest.json"
        ),
    )
    _validate_manifest_identity(
        identities,
        key="llama_override",
        path=Path(
            "resources/security_profiles/"
            "modelscope_llm_research_llama_prompt_guard_2_86m_manifest.json"
        ),
    )
    structured_path = Path("resources/security_profiles/p10_3_structured_axes_candidate_v1.json")
    if identities.get("structured_axes_profile_file_sha256") != _sha256(structured_path):
        raise SystemExit("P10.3 structured-axis Profile differs from Protocol")
    implementation = protocol.get("implementation_sha256")
    if not isinstance(implementation, dict) or not implementation:
        raise SystemExit("P10.3 implementation identity set is missing")
    for path_value, expected_sha in implementation.items():
        if not isinstance(path_value, str) or not isinstance(expected_sha, str):
            raise SystemExit("P10.3 implementation identity is invalid")
        if _sha256(Path(path_value)) != expected_sha:
            raise SystemExit(f"P10.3 implementation differs from Protocol: {path_value}")


def _validate_manifest_identity(identities: dict[object, object], *, key: str, path: Path) -> None:
    identity = identities.get(key)
    if not isinstance(identity, dict):
        raise SystemExit(f"P10.3 {key} identity is missing")
    manifest = load_prompt_guard_manifest(path)
    if identity.get("manifest_file_sha256") != _sha256(path):
        raise SystemExit(f"P10.3 {key} Manifest file differs from Protocol")
    if identity.get("manifest_canonical_sha256") != manifest.sha256:
        raise SystemExit(f"P10.3 {key} canonical Manifest differs from Protocol")


if __name__ == "__main__":
    main()
