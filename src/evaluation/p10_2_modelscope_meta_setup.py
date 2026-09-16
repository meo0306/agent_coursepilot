"""Freeze the owner-accepted ModelScope Prompt Guard user-upload snapshot."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from courserag.security.prompt_guard import PromptGuardModelManifest, model_directory_identity
from evaluation.io import atomic_write_json

MODEL_ID = "modelscope/LLM-Research/Llama-Prompt-Guard-2-86M"
MODEL_REVISION = "be11c20dd62e7b5391dab63f212c42e2fc25f3ea"
LICENSE_NAME = "Llama 4 Community License Agreement"
LICENSE_URL = "https://modelscope.cn/models/LLM-Research/Llama-Prompt-Guard-2-86M"
MODEL_FILE_SHA256 = {
    "LICENSE": "73755cee886613ae3135140882289e0a4955d5f0e90f8b1c1ffc962aa9082917",
    "README.md": "5d2a3e0c46397609a784a5034dc823da408aa8b5a414828609f32dc18ee16933",
    "USE_POLICY.md": "5ae40fe842b87b5773c47cfd25992a496cc09b17cbb246968762f06352d89270",
    "config.json": "cd54ac39a1f2c3c5146bd5295b34038f8b4d9069e2f844450da014a523bb7653",
    "model.safetensors": "e72017dbbe89c1232dcbc4a74ce0c389db5b468c42afd05850347b2a8c5f6b09",
    "special_tokens_map.json": "9463f61e1b109a8eb4688b829260d7c6b1e6dff04c98ff7269bb89e2b92369b9",
    "tokenizer.json": "3e7e96867c2acdd575f0862c74822e05d1d15b93d9d9a4a2144b1ce83ae3339f",
    "tokenizer_config.json": "fa09cf22b9d723377f95706967f789ca1a8267e1412385705e1ed51ce0559189",
}


def freeze_existing(*, model_dir: Path, manifest_path: Path) -> Path:
    files, bundle_sha256 = model_directory_identity(model_dir)
    if files != MODEL_FILE_SHA256:
        raise RuntimeError("ModelScope Prompt Guard files differ from the frozen API snapshot")
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
    return manifest_path.resolve()


def main() -> None:
    parser = argparse.ArgumentParser()
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
    parser.add_argument("--owner-accepts-source-and-license-risk", action="store_true")
    args = parser.parse_args()
    if not args.owner_accepts_source_and_license_risk:
        raise SystemExit("explicit owner acceptance of source and license risk is required")
    manifest = freeze_existing(model_dir=args.model_dir, manifest_path=args.manifest)
    print(
        json.dumps(
            {
                "manifest": str(manifest),
                "manifest_sha256": hashlib.sha256(manifest.read_bytes()).hexdigest(),
                "source_provenance": "modelscope_user_upload_unverified_official_origin",
                "upstream_access_status": "owner_official_meta_request_rejected",
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
