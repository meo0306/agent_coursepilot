from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from coursepilot.domain.common import canonical_sha256


class TemplateDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    template_id: str = Field(min_length=1, max_length=160)
    version: str = Field(min_length=1, max_length=80)
    artifact_type: Literal["lesson", "exam", "ppt"]
    input_schema_role: str
    output_schema_role: str
    planner_prompt_profile: str
    generator_prompt_profile: str
    validator_profile: str
    repair_profile: str
    model_route_profiles: tuple[str, ...]
    exporter_profile: str
    physical_resource_roles: tuple[str, ...]
    default_parameters: dict[str, object]

    @property
    def definition_sha256(self) -> str:
        return canonical_sha256(self.model_dump(mode="json"))


class TemplateSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    template_id: str
    template_version: str
    definition_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    resource_hashes: dict[str, str]
    prompt_hashes: dict[str, str]
    model_profile_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    schema_versions: dict[str, str]
    validator_profile: str
    repair_profile: str
    exporter_profile: str
    user_overrides: dict[str, object]

    @property
    def snapshot_sha256(self) -> str:
        return canonical_sha256(self.model_dump(mode="json"))
