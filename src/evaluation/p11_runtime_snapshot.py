from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from coursepilot.domain.artifact import ArtifactVersion
from coursepilot.domain.runtime import CommonGraphState
from coursepilot.templates import TemplateRegistry
from evaluation.p11_schemas import P11RuntimeFoundationSnapshot


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def directory_manifest_sha256(root: Path) -> str:
    payload = {
        path.relative_to(root).as_posix(): file_sha256(path)
        for path in sorted(root.rglob("*"))
        if path.is_file() and "__pycache__" not in path.parts
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def write_snapshot(repository_root: Path, output: Path) -> tuple[Path, str]:
    root = repository_root.resolve()
    registry = TemplateRegistry(root / "resources/templates/registry_v1.yaml")
    approval = json.loads(
        (
            root / "datasets/coursepilot_eval/v1/provenance/p11_foundation_input_approval.json"
        ).read_text(encoding="utf-8")
    )
    p10_contract = root / "src/coursepilot/ports/courserag.py"
    p10_manifest = root / "storage_eval/p10/frozen_manifest.json"
    if not p10_contract.exists() or not p10_manifest.exists():
        raise FileNotFoundError("P10 frozen contract/manifest is missing")
    report = root / "docs/refactor/phase_reports/P11_coursepilot_runtime_template_model_gateway.md"
    tests = root / "storage_eval/p11_runtime_foundation/test_report.json"
    compatibility = root / "storage_eval/p11_runtime_foundation/b0_compatibility_report.json"
    for required in (report, tests, compatibility):
        if not required.exists():
            raise FileNotFoundError(required)
    resources = {
        role: file_sha256(registry.resource_path(role)) for role in registry.resource_roles
    }
    snapshot = P11RuntimeFoundationSnapshot(
        bundle_sha256=approval["bundle_sha256"],
        template_resource_hashes=resources,
        model_profile_manifest_sha256=file_sha256(
            root / "resources/model_profiles/default_v1.yaml"
        ),
        capability_manifest_sha256=file_sha256(
            root / "resources/model_profiles/capabilities/deepseek_v4.json"
        ),
        prompt_manifest_sha256=directory_manifest_sha256(root / "src/coursepilot/prompts"),
        state_schema_sha256=hashlib.sha256(
            json.dumps(
                {key: str(value) for key, value in CommonGraphState.__annotations__.items()},
                sort_keys=True,
            ).encode()
        ).hexdigest(),
        artifact_schema_sha256=hashlib.sha256(
            json.dumps(ArtifactVersion.model_json_schema(), sort_keys=True).encode()
        ).hexdigest(),
        template_snapshot_schema_sha256=file_sha256(
            root / "datasets/schemas/v1/coursepilot_p11_runtime_foundation_snapshot.schema.json"
        ),
        p10_contract_sha256=file_sha256(p10_contract),
        p10_frozen_manifest_sha256=file_sha256(p10_manifest),
        migration_version="0016_coursepilot_runtime_foundation",
        migration_sha256=file_sha256(
            root / "alembic/versions/2026_08_13_0016-coursepilot-runtime-foundation.py"
        ),
        b0_compatibility_report_sha256=file_sha256(compatibility),
        p11_test_report_sha256=file_sha256(tests),
        p11_phase_report_sha256=file_sha256(report),
        legacy_compatibility_roles=["validator", "repair", "exporter"],
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(snapshot.model_dump(mode="json"), ensure_ascii=False, sort_keys=True, indent=2)
        + "\n",
        encoding="utf-8",
    )
    return output, file_sha256(output)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository-root", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    path, digest = write_snapshot(args.repository_root, args.output)
    print(json.dumps({"path": str(path.resolve()), "sha256": digest}, ensure_ascii=False))


if __name__ == "__main__":
    main()
