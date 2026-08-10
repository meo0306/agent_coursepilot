"""Resolve exact local OCR model files and bind a deployable runtime profile."""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import os
import re
import shutil
import subprocess
from pathlib import Path
from uuid import uuid4

from pydantic import JsonValue

from courserag.domain.document import sha256_bytes
from courserag.parsers.ocr.types import OCRProviderProfile

_MODEL_SUFFIXES = {
    ".json",
    ".onnx",
    ".pdiparams",
    ".pdmodel",
    ".traineddata",
    ".txt",
    ".yaml",
    ".yml",
}


def prepare_runtime_profile(
    *,
    candidate_profile_path: Path,
    output_dir: Path,
) -> dict[str, str]:
    """Bind a checked-in profile to the exact model files in the current image."""
    profile = OCRProviderProfile.model_validate_json(
        candidate_profile_path.read_text(encoding="utf-8")
    )
    files = _model_files(profile.provider)
    if not files:
        raise ValueError("OCR runtime contains no discoverable model artifacts")
    artifacts: list[JsonValue] = [
        {
            "path": str(path),
            "sha256": _sha256_file(path),
            "size_bytes": path.stat().st_size,
        }
        for path in files
    ]
    manifest: dict[str, JsonValue] = {
        "schema_version": "courserag.ocr-model-manifest.v1",
        "provider": profile.provider,
        "distribution": profile.model_name,
        "identity_status": "resolved",
        "license_review_required": True,
        "artifacts": artifacts,
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = output_dir / "model-manifest.json"
    _atomic_write_json(manifest_path, manifest)
    runtime_profile = profile.model_copy(
        update={
            "model_manifest_path": str(manifest_path.resolve()),
            "model_manifest_sha256": _sha256_file(manifest_path),
        }
    )
    runtime_profile_path = output_dir / "runtime-profile.json"
    _atomic_write_json(runtime_profile_path, runtime_profile.model_dump(mode="json"))
    return {
        "model_manifest_path": str(manifest_path),
        "model_manifest_sha256": _sha256_file(manifest_path),
        "profile_path": str(runtime_profile_path),
        "profile_sha256": runtime_profile.sha256,
    }


def _model_files(provider: str) -> list[Path]:
    if provider == "rapidocr":
        distribution = importlib.metadata.distribution("rapidocr")
        paths = [
            Path(str(distribution.locate_file(item))).resolve()
            for item in distribution.files or []
            if Path(str(item)).suffix.casefold() in _MODEL_SUFFIXES
        ]
    elif provider == "tesseract":
        executable = shutil.which("tesseract")
        if executable is None:
            return []
        listing = subprocess.run(
            [executable, "--list-langs"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.splitlines()
        if not listing:
            return []
        match = re.search(r"in\s+(.+?)\s*\(\d+\):", listing[0])
        if match is None:
            return []
        data_dir = match.group(1).strip().strip('"').strip("'")
        paths = list(Path(data_dir).glob("*.traineddata"))
    else:
        roots = [Path("/root/.paddlex"), Path("/root/.paddleocr")]
        paths = [
            path
            for root in roots
            if root.is_dir()
            for path in root.rglob("*")
            if path.is_file() and path.suffix.casefold() in _MODEL_SUFFIXES
        ]
    return sorted({path for path in paths if path.is_file()}, key=str)


def _sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def _atomic_write_json(path: Path, payload: JsonValue) -> None:
    content = (json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode(
        "utf-8"
    )
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        with temporary.open("wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Bind an OCR runtime profile to exact local model files."
    )
    parser.add_argument("--candidate-profile", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    result = prepare_runtime_profile(
        candidate_profile_path=args.candidate_profile,
        output_dir=args.output_dir,
    )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
