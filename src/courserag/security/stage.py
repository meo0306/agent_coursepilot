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
from courserag.security.dual_hypothesis import (
    DualHypothesisSecurityEnsemble,
    TriStateDualHypothesisDecisionLayer,
)
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


@dataclass(frozen=True)
class DualHypothesisSecurityAnnotationStage:
    """Candidate v3 annotation stage; disabled Profiles cannot execute."""

    parsed_artifact: bytes
    document_version_id: str
    ensemble: DualHypothesisSecurityEnsemble
    window_builder: SecurityWindowBuilder
    name: str = "security_annotation"
    version: str = "3.0"

    def execute(self, context: StageContext) -> StageOutput:
        artifact_sha256 = sha256_bytes(self.parsed_artifact)
        if context.input_hashes != (artifact_sha256,):
            raise ValueError("security Stage input Hash differs from parsed Artifact")
        if context.input_identities != (f"{self.document_version_id}:parsed_document",):
            raise ValueError("security Stage input identity differs from document version")
        if not self.ensemble.profile.enabled:
            raise RuntimeError("dual-hypothesis security Profile is not released")
        expected = dual_hypothesis_security_stage_config(self.ensemble)
        if context.config != expected:
            raise ValueError("security Stage config differs from dual-hypothesis Profile")
        document = ParsedDocumentIR.model_validate_json(
            read_bundle_json(self.parsed_artifact, "document_ir.json")
        )
        if document.document_version_id != self.document_version_id:
            raise ValueError("parsed Artifact document version differs from security Stage")
        windows = self.window_builder.build(document)
        scores = self.ensemble.score(windows)
        findings = self.ensemble.decide(document, windows, scores)
        annotated = apply_prompt_injection_findings(
            document,
            findings,
            profile_name=self.ensemble.profile.name,
            profile_sha256=self.ensemble.profile.sha256,
            detector_id="dual_hypothesis_local",
        )
        quality = build_quality_report(annotated)
        preview = build_parse_preview(annotated)
        bundle = replace_parsed_artifact_document(self.parsed_artifact, annotated, quality, preview)
        return StageOutput(
            content=bundle.content,
            media_type="application/vnd.courserag.parsed-document+zip",
            counts={
                "windows": len(windows),
                "findings": len(findings),
                "marked_windows": sum(score.marked for score in scores),
                "warnings": len(annotated.warnings),
            },
            warnings=quality.warning_codes,
        )


def dual_hypothesis_security_stage_config(
    ensemble: DualHypothesisSecurityEnsemble,
) -> dict[str, object]:
    profile = ensemble.profile
    return {
        "provider": "dual_hypothesis_local",
        "decision_profile_name": profile.name,
        "decision_profile_sha256": profile.sha256,
        "semantic_encoder_identity": profile.semantic_encoder_identity,
        "hikma_detector_id": profile.hikma_detector_id,
        "attack_threshold": profile.attack_threshold,
        "minimum_margin": profile.minimum_margin,
    }


@dataclass(frozen=True)
class TriStateSecurityAnnotationStage:
    parsed_artifact: bytes
    document_version_id: str
    ensemble: DualHypothesisSecurityEnsemble
    decision_layer: TriStateDualHypothesisDecisionLayer
    window_builder: SecurityWindowBuilder
    name: str = "security_annotation"
    version: str = "4.0"

    def execute(self, context: StageContext) -> StageOutput:
        artifact_sha256 = sha256_bytes(self.parsed_artifact)
        if context.input_hashes != (artifact_sha256,):
            raise ValueError("security Stage input Hash differs from parsed Artifact")
        if context.input_identities != (f"{self.document_version_id}:parsed_document",):
            raise ValueError("security Stage input identity differs from document version")
        if not self.decision_layer.profile.enabled:
            raise RuntimeError("tri-state security Profile is not released")
        expected = tri_state_security_stage_config(self.ensemble, self.decision_layer)
        if context.config != expected:
            raise ValueError("security Stage config differs from tri-state Profile")
        document = ParsedDocumentIR.model_validate_json(
            read_bundle_json(self.parsed_artifact, "document_ir.json")
        )
        if document.document_version_id != self.document_version_id:
            raise ValueError("parsed Artifact document version differs from security Stage")
        windows = self.window_builder.build(document)
        scores = self.ensemble.score(windows)
        decisions = self.decision_layer.decide_scores(scores)
        findings = self.decision_layer.build_findings(document, windows, scores, decisions)
        annotated = apply_prompt_injection_findings(
            document,
            findings,
            profile_name=self.decision_layer.profile.name,
            profile_sha256=self.decision_layer.profile.sha256,
            detector_id="tri_state_dual_hypothesis_local",
        )
        quality = build_quality_report(annotated)
        preview = build_parse_preview(annotated)
        bundle = replace_parsed_artifact_document(self.parsed_artifact, annotated, quality, preview)
        counts = {
            "windows": len(windows),
            "findings": len(findings),
            "warnings": len(annotated.warnings),
        }
        for decision in ("attack", "needs_review", "safe"):
            counts[f"decision_{decision}"] = sum(item.decision == decision for item in decisions)
        return StageOutput(
            content=bundle.content,
            media_type="application/vnd.courserag.parsed-document+zip",
            counts=counts,
            warnings=quality.warning_codes,
        )


def tri_state_security_stage_config(
    ensemble: DualHypothesisSecurityEnsemble,
    decision_layer: TriStateDualHypothesisDecisionLayer,
) -> dict[str, object]:
    return {
        "provider": "tri_state_dual_hypothesis_local",
        "base_profile_sha256": ensemble.profile.sha256,
        "decision_profile_name": decision_layer.profile.name,
        "decision_profile_sha256": decision_layer.profile.sha256,
        "attack_boundary": decision_layer.profile.attack_boundary,
        "safe_boundary": decision_layer.profile.safe_boundary,
    }
