"""P06 stable Evidence Stage and immutable database projection."""

from __future__ import annotations

from dataclasses import dataclass

from courserag.domain.document import ParsedDocumentIR, canonical_json_bytes, sha256_bytes
from courserag.domain.evidence import EvidenceArtifact
from courserag.evidence.builder import EvidenceBuilder, EvidenceBuilderProfile
from courserag.evidence.materialize import materialize_evidence_artifact
from courserag.jobs.artifacts import FileArtifactStore
from courserag.jobs.stages import BuildStageRunner, StageContext, StageOutput
from courserag.parsers.artifact_bundle import read_bundle_json
from courserag.persistence.models import EvidenceRecord
from courserag.persistence.repositories import CourseRAGRepository


@dataclass(frozen=True)
class EvidenceBuildStage:
    parsed_artifact: bytes
    document_version_id: str
    profile: EvidenceBuilderProfile
    name: str = "build_evidence"
    version: str = "1.0"

    def execute(self, context: StageContext) -> StageOutput:
        digest = sha256_bytes(self.parsed_artifact)
        if context.input_hashes != (digest,):
            raise ValueError("Evidence Stage input hash differs from parsed Artifact")
        if context.input_identities != (f"{self.document_version_id}:parsed_document",):
            raise ValueError("Evidence Stage input identity differs from document version")
        expected_config = {
            "evidence_builder_profile": self.profile.name,
            "evidence_builder_profile_sha256": self.profile.sha256,
            "low_confidence_threshold": self.profile.low_confidence_threshold,
        }
        if context.config != expected_config:
            raise ValueError("Evidence Stage config differs from frozen Profile")
        document = ParsedDocumentIR.model_validate_json(
            read_bundle_json(self.parsed_artifact, "document_ir.json")
        )
        if document.document_version_id != self.document_version_id:
            raise ValueError("Parsed Artifact document version differs from Evidence Stage")
        artifact = EvidenceBuilder(self.profile).build(document)
        return StageOutput(
            content=canonical_json_bytes(artifact),
            media_type="application/vnd.courserag.evidence+json",
            counts={
                "evidence": len(artifact.records),
                "ocr_evidence": sum(record.source_mode != "native" for record in artifact.records),
                "warnings": len(artifact.warning_codes),
            },
            warnings=artifact.warning_codes,
        )


def evidence_stage_config(profile: EvidenceBuilderProfile) -> dict[str, object]:
    return {
        "evidence_builder_profile": profile.name,
        "evidence_builder_profile_sha256": profile.sha256,
        "low_confidence_threshold": profile.low_confidence_threshold,
    }


class EvidenceBuildCoordinator:
    def __init__(
        self,
        repository: CourseRAGRepository,
        stage_runner: BuildStageRunner,
        artifact_store: FileArtifactStore,
    ) -> None:
        self.repository = repository
        self.stage_runner = stage_runner
        self.artifact_store = artifact_store

    def run(
        self, stage: EvidenceBuildStage, context: StageContext, *, force: bool = False
    ) -> tuple[EvidenceRecord, ...]:
        stage_run = self.stage_runner.run(stage, context, force=force)
        if stage_run.artifact_id is None:
            raise RuntimeError("Evidence Stage completed without an Artifact")
        stored = self.repository.get_artifact(stage_run.artifact_id)
        if stored is None:
            raise RuntimeError("Evidence Stage Artifact record disappeared")
        content = self.artifact_store.read(stored.uri, expected_sha256=stored.sha256)
        artifact = EvidenceArtifact.model_validate_json(content)
        parsed = self.repository.get_parsed_document_by_version(stage.document_version_id)
        if parsed is None:
            raise RuntimeError("Evidence Stage requires a materialized ParsedDocument")
        return materialize_evidence_artifact(
            self.repository, parsed_document_id=parsed.id, artifact=artifact
        )
