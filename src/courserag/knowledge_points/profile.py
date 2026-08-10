"""Versioned Knowledge Point pipeline Profile loader."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import Field

from courserag.domain.knowledge_point import (
    StrictKnowledgePointModel,
    WindowProfile,
    canonical_json_bytes,
    sha256_bytes,
)
from courserag.knowledge_points.scoring import ScoringProfile


class KnowledgePointPipelineProfile(StrictKnowledgePointModel):
    schema_version: Literal["courserag.kp-pipeline-profile.v1"] = "courserag.kp-pipeline-profile.v1"
    name: str = Field(min_length=1, max_length=160)
    version: str = Field(min_length=1, max_length=80)
    window: WindowProfile
    scoring: ScoringProfile
    prompt_relative_path: str = Field(min_length=1, max_length=1024)
    temperature: float = Field(default=0.1, ge=0, le=2)
    max_candidates_per_window: int = Field(default=40, ge=1, le=40)

    @property
    def profile_sha256(self) -> str:
        return sha256_bytes(canonical_json_bytes(self))


def load_knowledge_point_profile(
    profile_path: Path, *, repository_root: Path
) -> tuple[KnowledgePointPipelineProfile, str, str]:
    resolved_root = repository_root.resolve()
    resolved_profile = profile_path.resolve()
    if not resolved_profile.is_relative_to(resolved_root):
        raise ValueError("Knowledge Point Profile must remain inside the repository")
    profile = KnowledgePointPipelineProfile.model_validate_json(
        resolved_profile.read_text(encoding="utf-8")
    )
    prompt_path = (resolved_root / profile.prompt_relative_path).resolve()
    if not prompt_path.is_relative_to(resolved_root) or not prompt_path.is_file():
        raise ValueError("Knowledge Point Prompt path is missing or outside the repository")
    prompt = prompt_path.read_text(encoding="utf-8")
    return profile, prompt, sha256_bytes(prompt.encode("utf-8"))
