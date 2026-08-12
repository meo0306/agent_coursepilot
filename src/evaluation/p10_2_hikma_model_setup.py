"""Download and freeze the approved HikmaAI FP16 ONNX snapshot."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from huggingface_hub import snapshot_download

from courserag.security.prompt_guard import PromptGuardModelManifest, model_directory_identity
from evaluation.io import atomic_write_json

MODEL_ID = "HikmaAI/hikmaai-mdeberta-v3-base-prompt-injection-multilingual"
MODEL_REVISION = "aef60fed9674e497a7ba08e43b41e8666483934e"
LICENSE_NAME = "Apache License 2.0"
LICENSE_URL = f"https://huggingface.co/{MODEL_ID}"
MODEL_ALLOW_PATTERNS = (
    "README.md",
    "config.json",
    "model_card.json",
    "threshold.json",
    "onnx/fp16/model.onnx",
    "tokenizer/special_tokens_map.json",
    "tokenizer/tokenizer.json",
    "tokenizer/tokenizer_config.json",
)
UPSTREAM_LFS_SHA256 = {
    "onnx/fp16/model.onnx": "52b3cd13715689772c8608edf31cc0a1261f684d4600521b2283d0a8f8f8afb0",
    "tokenizer/tokenizer.json": "9ddbe35b768b22d6cd0d61a0a88ea3a188b7c00bbb7b825f9f247cf0b79c2365",
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
    resolved = (
        model_dir.resolve()
        if finalize_existing
        else Path(
            snapshot_download(
                repo_id=MODEL_ID,
                revision=MODEL_REVISION,
                local_dir=model_dir,
                token=False,
                allow_patterns=list(MODEL_ALLOW_PATTERNS),
                max_workers=1,
            )
        ).resolve()
    )
    files, bundle_sha256 = model_directory_identity(resolved)
    if set(files) != set(MODEL_ALLOW_PATTERNS):
        raise RuntimeError("downloaded HikmaAI snapshot has a missing or unexpected file set")
    for relative_path, expected_sha256 in UPSTREAM_LFS_SHA256.items():
        if files[relative_path] != expected_sha256:
            raise RuntimeError(f"HikmaAI upstream Hash mismatch: {relative_path}")
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
    parser.add_argument("--license-accepted-by-owner", action="store_true")
    parser.add_argument("--finalize-existing", action="store_true")
    args = parser.parse_args()
    model_dir, manifest = download_and_freeze(
        model_dir=args.model_dir,
        manifest_path=args.manifest,
        license_accepted_by_owner=args.license_accepted_by_owner,
        finalize_existing=args.finalize_existing,
    )
    print(
        json.dumps(
            {
                "model_dir": str(model_dir),
                "manifest": str(manifest),
                "manifest_sha256": hashlib.sha256(manifest.read_bytes()).hexdigest(),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
