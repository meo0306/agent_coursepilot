"""Independent post-OCR security annotation build stage."""

from __future__ import annotations

from dataclasses import dataclass

from courserag.domain.document import ParsedDocumentIR, sha256_bytes
from courserag.jobs.artifacts import FileArtifactStore
from courserag.jobs.stages import BuildStageRunner, StageContext, StageOutput
from courserag.parsers.artifact_bundle import (
    read_bundle_json,
    replace_parsed_artifact_document,
)
from courserag.parsers.quality import build_parse_preview, build_quality_report
from courserag.persistence.models import ArtifactRecord
from courserag.persistence.repositories import CourseRAGRepository
from courserag.security.detector import PromptInjectionDetector
from courserag.security.ensemble import MultiAxisSecurityEnsemble
from courserag.security.policy import PromptInjectionDecisionPolicy
from courserag.security.prompt_injection import apply_prompt_injection_findings
from courserag.security.windowing import SecurityWindowBuilder


@dataclass(frozen=True)
class SecurityAnnotationStage:
    parsed_artifact: bytes
    document_version_id: str
    detector: PromptInjectionDetector
    window_builder: SecurityWindowBuilder
    policy: PromptInjectionDecisionPolicy
    name: str = "security_annotation"
    version: str = "1.0"

    def execute(self, context: StageContext) -> StageOutput:
        artifact_sha256 = sha256_bytes(self.parsed_artifact)
        if context.input_hashes != (artifact_sha256,):
            raise ValueError("security Stage input Hash differs from parsed Artifact")
        if context.input_identities != (f"{self.document_version_id}:parsed_document",):
            raise ValueError("security Stage input identity differs from document version")
        expected = security_annotation_stage_config(self.policy)
        if context.config != expected:
            raise ValueError("security Stage config differs from frozen decision Profile")
        self.detector.validate_environment()
        document = ParsedDocumentIR.model_validate_json(
            read_bundle_json(self.parsed_artifact, "document_ir.json")
        )
        if document.document_version_id != self.document_version_id:
            raise ValueError("parsed Artifact document version differs from security Stage")
        windows = self.window_builder.build(document)
        scores = self.detector.score(windows)
        annotated = self.policy.annotate(document, windows, scores)
        quality = build_quality_report(annotated)
        preview = build_parse_preview(annotated)
        bundle = replace_parsed_artifact_document(self.parsed_artifact, annotated, quality, preview)
        marked_blocks = 0
        for page in annotated.pages:
            for block in page.blocks:
                warning_codes = block.style.get("warning_codes", [])
                if isinstance(warning_codes, list) and any(
                    str(code) == "PROMPT_INJECTION_MARKED" for code in warning_codes
                ):
                    marked_blocks += 1
        return StageOutput(
            content=bundle.content,
            media_type="application/vnd.courserag.parsed-document+zip",
            counts={
                "windows": len(windows),
                "marked_blocks": marked_blocks,
                "warnings": len(annotated.warnings),
            },
            warnings=quality.warning_codes,
        )


def security_annotation_stage_config(
    policy: PromptInjectionDecisionPolicy,
) -> dict[str, object]:
    profile = policy.profile
    return {
        "provider": profile.provider,
        "decision_profile_name": profile.name,
        "decision_profile_sha256": profile.sha256,
        "model_manifest_sha256": profile.model_manifest_sha256,
        "auxiliary_rules_sha256": profile.auxiliary_rules_sha256,
        "threshold_low": profile.threshold_low,
        "threshold_high": profile.threshold_high,
        "max_tokens": profile.max_tokens,
        "content_tokens": profile.content_tokens,
        "stride_tokens": profile.stride_tokens,
    }


class SecurityAnnotationCoordinator:
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
        self,
        stage: SecurityAnnotationStage,
        context: StageContext,
        *,
        force: bool = False,
    ) -> ArtifactRecord:
        run = self.stage_runner.run(stage, context, force=force)
        if run.artifact_id is None:
            raise RuntimeError("security Stage completed without an Artifact")
        artifact = self.repository.get_artifact(run.artifact_id)
        if artifact is None:
            raise RuntimeError("security Stage Artifact record disappeared")
        if not self.artifact_store.verify(artifact.uri, artifact.sha256):
            raise RuntimeError("security Stage Artifact failed verification")
        return artifact


@dataclass(frozen=True)
class MultiAxisSecurityAnnotationStage:
    parsed_artifact: bytes
    document_version_id: str
    ensemble: MultiAxisSecurityEnsemble
    window_builder: SecurityWindowBuilder
    name: str = "security_annotation"
    version: str = "2.0"

    def execute(self, context: StageContext) -> StageOutput:
        artifact_sha256 = sha256_bytes(self.parsed_artifact)
        if context.input_hashes != (artifact_sha256,):
            raise ValueError("security Stage input Hash differs from parsed Artifact")
        if context.input_identities != (f"{self.document_version_id}:parsed_document",):
            raise ValueError("security Stage input identity differs from document version")
        expected = multi_axis_security_stage_config(self.ensemble)
        if context.config != expected:
            raise ValueError("security Stage config differs from frozen multi-axis Profile")
        self.ensemble.validate_environment()
        document = ParsedDocumentIR.model_validate_json(
            read_bundle_json(self.parsed_artifact, "document_ir.json")
        )
        if document.document_version_id != self.document_version_id:
            raise ValueError("parsed Artifact document version differs from security Stage")
        windows = self.window_builder.build(document)
        signals = self.ensemble.detect(windows)
        findings = self.ensemble.decide(document, windows, signals)
        annotated = apply_prompt_injection_findings(
            document,
            findings,
            profile_name=self.ensemble.profile.name,
            profile_sha256=self.ensemble.profile.sha256,
            detector_id="multi_axis_local",
        )
        quality = build_quality_report(annotated)
        preview = build_parse_preview(annotated)
        bundle = replace_parsed_artifact_document(self.parsed_artifact, annotated, quality, preview)
        ready_by_axis: dict[str, int] = {}
        for signal in signals:
            if signal.decision_ready:
                ready_by_axis[signal.axis_id] = ready_by_axis.get(signal.axis_id, 0) + 1
        counts = {
            "windows": len(windows),
            "signals": len(signals),
            "findings": len(findings),
            "warnings": len(annotated.warnings),
        }
        counts.update({f"axis_{axis}": count for axis, count in sorted(ready_by_axis.items())})
        return StageOutput(
            content=bundle.content,
            media_type="application/vnd.courserag.parsed-document+zip",
            counts=counts,
            warnings=quality.warning_codes,
        )


def multi_axis_security_stage_config(
    ensemble: MultiAxisSecurityEnsemble,
) -> dict[str, object]:
    profile = ensemble.profile
    return {
        "provider": "multi_axis_local",
        "decision_profile_name": profile.name,
        "decision_profile_sha256": profile.sha256,
        "decision": profile.decision,
        "hikma_manifest_sha256": profile.hikma_manifest_sha256,
        "override_manifest_sha256": profile.override_manifest_sha256,
        "structured_profile_sha256": profile.structured_profile_sha256,
        "axes": [axis.model_dump(mode="json") for axis in profile.axes],
    }
