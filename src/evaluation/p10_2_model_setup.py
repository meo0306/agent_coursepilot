"""Download and freeze the owner-approved local P10.2 Prompt Guard model."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from huggingface_hub import snapshot_download

from courserag.security.prompt_guard import (
    PromptGuardModelManifest,
    model_directory_identity,
)
from evaluation.io import atomic_write_json

MODEL_ID = "protectai/deberta-v3-base-prompt-injection"
MODEL_REVISION = "373b6af0f8d16739cff5de28be326652246bfaa3"
LICENSE_NAME = "Apache License 2.0"
LICENSE_URL = "https://huggingface.co/protectai/deberta-v3-base-prompt-injection"
MODEL_ALLOW_PATTERNS = (
    "README.md",
    "added_tokens.json",
    "config.json",
    "model.safetensors",
    "special_tokens_map.json",
    "spm.model",
    "tokenizer.json",
    "tokenizer_config.json",
)
MODEL_FILE_SHA256 = {
    "README.md": "57dea1e675451bbb0aa6dd7b71e9b185baebff3d587c8f056f21b76a0231edc0",
    "added_tokens.json": "dc046d04c9b0ada7ae6f1dc89c465801799acdf0c9a6aab8c15a1b2d5ca4e91f",
    "config.json": "7609bf72b5e74a2f3c67ed507c3d6a443131598f37bb68bd68e73629b04faea4",
    "model.safetensors": "4473925f9fa27b99793f61f3a7d4040abe9a5ee7055b88756c901517afdceed1",
    "special_tokens_map.json": "9463f61e1b109a8eb4688b829260d7c6b1e6dff04c98ff7269bb89e2b92369b9",
    "spm.model": "c679fbf93643d19aab7ee10c0b99e460bdbc02fedf34b92b05af343b4af586fd",
    "tokenizer.json": "05402ffae6dd382a8491b1d29bfc139bec5d332662e86a026f433ce54c25c202",
    "tokenizer_config.json": "557b3d33d3f41b81ad769244e506549e98a1857d41dd58160aacd4d98d710b5a",
}


def download_and_freeze(
    *,
    model_dir: Path,
    manifest_path: Path,
    license_accepted_by_owner: bool,
    finalize_existing: bool = False,
) -> tuple[Path, Path]:
    if not license_accepted_by_owner:
        raise ValueError("model download requires explicit owner license acceptance")
    if finalize_existing:
        resolved = model_dir.resolve()
    else:
        resolved = Path(
            snapshot_download(
                repo_id=MODEL_ID,
                revision=MODEL_REVISION,
                local_dir=model_dir,
                token=False,
                allow_patterns=list(MODEL_ALLOW_PATTERNS),
                max_workers=1,
            )
        ).resolve()
    files, bundle_sha256 = model_directory_identity(resolved)
    if files != MODEL_FILE_SHA256:
        raise RuntimeError(
            "downloaded Prompt Guard files differ from the owner-approved upstream snapshot"
        )
    manifest = PromptGuardModelManifest(
        model_id=MODEL_ID,
        revision=MODEL_REVISION,
        model_bundle_sha256=bundle_sha256,
        files=files,
        license=LICENSE_NAME,
        license_url=LICENSE_URL,
        license_accepted_by_owner=True,
        runtime_network_required=False,
    )
    atomic_write_json(manifest_path, manifest.model_dump(mode="json"))
    return resolved, manifest_path.resolve()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--model-dir",
        type=Path,
        default=Path(r"D:\AI\models\huggingface\protectai\deberta-v3-base-prompt-injection"),
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path(
            "resources/security_profiles/protectai_deberta_v3_base_prompt_injection_manifest.json"
        ),
    )
    parser.add_argument("--license-accepted-by-owner", action="store_true")
    parser.add_argument(
        "--finalize-existing",
        action="store_true",
        help="skip all network access and freeze an already downloaded, Hash-matching directory",
    )
    args = parser.parse_args()
    model_dir, manifest = download_and_freeze(
        model_dir=args.model_dir,
        manifest_path=args.manifest,
        license_accepted_by_owner=args.license_accepted_by_owner,
        finalize_existing=args.finalize_existing,
    )
    payload = {
        "model_dir": str(model_dir),
        "manifest": str(manifest),
        "manifest_sha256": __import__("hashlib").sha256(manifest.read_bytes()).hexdigest(),
    }
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
