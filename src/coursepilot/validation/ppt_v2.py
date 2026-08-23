from __future__ import annotations

from coursepilot.domain.ppt import PPTArtifact
from coursepilot.validation.models import (
    IssueLayer,
    IssueScope,
    Severity,
    ValidationIssue,
    ValidationReport,
)


def validate_ppt_artifact(
    artifact: PPTArtifact, *, valid_evidence_ids: set[str] | None = None
) -> ValidationReport:
    allowed = (
        valid_evidence_ids
        if valid_evidence_ids is not None
        else set(artifact.architecture.context_evidence_ids)
    )
    issues: list[ValidationIssue] = []
    for index, slide in enumerate(artifact.slides):
        plan = artifact.architecture.plans[index]
        if plan.notes_required and not slide.speaker_notes.strip():
            issues.append(
                ValidationIssue(
                    issue_id=f"PPT_NOTES_MISSING:{slide.slide_id}",
                    code="PPT_NOTES_MISSING",
                    severity=Severity.ERROR,
                    layer=IssueLayer.L2,
                    scope=IssueScope(
                        artifact_type="ppt",
                        item_id=slide.slide_id,
                        json_path=f"$.slides[{index}].speaker_notes",
                    ),
                )
            )
        cited = {citation.evidence_id for citation in slide.citations}
        if plan.citation_required and set(plan.evidence_ids) - cited:
            issues.append(
                ValidationIssue(
                    issue_id=f"PPT_CITATION_MISSING:{slide.slide_id}",
                    code="PPT_CITATION_MISSING",
                    severity=Severity.ERROR,
                    layer=IssueLayer.L3,
                    scope=IssueScope(
                        artifact_type="ppt",
                        item_id=slide.slide_id,
                        json_path=f"$.slides[{index}].citations",
                    ),
                    evidence_ids=sorted(set(plan.evidence_ids) - cited),
                )
            )
        if not cited <= allowed:
            issues.append(
                ValidationIssue(
                    issue_id=f"PPT_EVIDENCE_OUT_OF_SCOPE:{slide.slide_id}",
                    code="PPT_EVIDENCE_OUT_OF_SCOPE",
                    severity=Severity.CRITICAL,
                    layer=IssueLayer.L3,
                    scope=IssueScope(
                        artifact_type="ppt",
                        item_id=slide.slide_id,
                        json_path=f"$.slides[{index}].citations",
                    ),
                    evidence_ids=sorted(cited - allowed),
                )
            )
    report = ValidationReport(
        artifact_id=artifact.lesson_artifact_id,
        artifact_version=artifact.architecture.architecture_version,
        artifact_type="ppt",
        validator_profile="p16_ppt_v1",
        issues=issues,
    )
    return report.finalize()
