from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from coursepilot.templates.models import TemplateDefinition, TemplateSnapshot


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


class TemplateRegistry:
    """Fail-closed loader for immutable logical and physical template identities."""

    def __init__(self, registry_path: Path):
        self.registry_path = registry_path.resolve()
        self.root = self.registry_path.parent
        payload = json.loads(self.registry_path.read_text(encoding="utf-8"))
        if payload.get("schema_version") != "coursepilot.template-registry.v1":
            raise ValueError("Unsupported CoursePilot template registry schema")
        self._payload: dict[str, Any] = payload
        self._definitions = self._load_definitions()
        self._validate_resources()

    @property
    def template_ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._definitions))

    @property
    def resource_roles(self) -> tuple[str, ...]:
        return tuple(sorted(self._payload["resources"]))

    @property
    def registry_sha256(self) -> str:
        return file_sha256(self.registry_path)

    def get(self, template_id: str) -> TemplateDefinition:
        try:
            return self._definitions[template_id]
        except KeyError as exc:
            raise ValueError(f"Unknown CoursePilot template: {template_id}") from exc

    def resource_path(self, role: str) -> Path:
        try:
            entry = self._payload["resources"][role]
        except KeyError as exc:
            raise ValueError(f"Unknown template resource role: {role}") from exc
        return (self.root / entry["path"]).resolve()

    def snapshot(
        self,
        template_id: str,
        *,
        prompt_hashes: dict[str, str],
        model_profile_sha256: str,
        schema_versions: dict[str, str],
        user_overrides: dict[str, object] | None = None,
    ) -> TemplateSnapshot:
        definition = self.get(template_id)
        resource_hashes = {
            role: file_sha256(self.resource_path(role))
            for role in definition.physical_resource_roles
        }
        return TemplateSnapshot(
            template_id=definition.template_id,
            template_version=definition.version,
            definition_sha256=definition.definition_sha256,
            resource_hashes=resource_hashes,
            prompt_hashes=dict(sorted(prompt_hashes.items())),
            model_profile_sha256=model_profile_sha256,
            schema_versions=dict(sorted(schema_versions.items())),
            validator_profile=definition.validator_profile,
            repair_profile=definition.repair_profile,
            exporter_profile=definition.exporter_profile,
            user_overrides=user_overrides or {},
        )

    def _load_definitions(self) -> dict[str, TemplateDefinition]:
        definitions: dict[str, TemplateDefinition] = {}
        for item in self._payload.get("definitions", []):
            path = (self.root / item["path"]).resolve()
            self._assert_under_root(path)
            expected = item["sha256"]
            if file_sha256(path) != expected:
                raise ValueError(f"Template definition hash mismatch: {path}")
            definition = TemplateDefinition.model_validate_json(path.read_text(encoding="utf-8"))
            if definition.template_id != item["template_id"]:
                raise ValueError(f"Template identity mismatch: {path}")
            if definition.template_id in definitions:
                raise ValueError(f"Duplicate template ID: {definition.template_id}")
            definitions[definition.template_id] = definition
        if len(definitions) != 9:
            raise ValueError("CoursePilot template registry must contain exactly nine definitions")
        return definitions

    def _validate_resources(self) -> None:
        if len(self._payload.get("resources", {})) != 5:
            raise ValueError("CoursePilot template registry must contain exactly five resources")
        for role, entry in self._payload["resources"].items():
            path = (self.root / entry["path"]).resolve()
            self._assert_under_root(path)
            if file_sha256(path) != entry["sha256"]:
                raise ValueError(f"Template resource hash mismatch: {role}")

    def _assert_under_root(self, path: Path) -> None:
        if not path.is_relative_to(self.root):
            raise ValueError("Template registry path escapes its root")
