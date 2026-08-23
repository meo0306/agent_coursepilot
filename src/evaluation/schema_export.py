from __future__ import annotations

import argparse
import json
from pathlib import Path

from pydantic import BaseModel

from coursepilot.evals.formal_schemas import (
    CPDS0ManifestDataset,
    CPDS1LessonDataset,
    CPDS1P14PilotDataset,
    CPDS2ExamDataset,
    CPDS2P15PilotDataset,
    CPDS3P16PilotDataset,
    CPDS3PPTDataset,
    CPDS4P13PilotDataset,
    CPDS4ValidationDataset,
    CPDS5P13PilotDataset,
    CPDS5RepairDataset,
    CPDS6P12PilotDataset,
    CPDS6RecoveryDataset,
    CPDS7ExportDataset,
    CPDS7P16PilotDataset,
    CPDS8FaultSecurityDataset,
    CPDS8P17Dataset,
    HumanScoreDataset,
    HumanScoreJsonlRecord,
    P14BundleApproval,
    P14FixtureBundle,
    P14ReviewDecisions,
    P15BundleApproval,
    P15FixtureBundle,
    P15ReviewDecisions,
    P16BundleApproval,
    P16BundleManifest,
    P16ReviewDecisions,
    SYSDS1JourneyDataset,
    SYSDS1P17Dataset,
)
from courserag.evals.schemas import (
    CorpusFixtureManifest,
    DS0CorpusDataset,
    DS1BatchApproval,
    DS1CandidateManifest,
    DS1ParsingDataset,
    DS1ReviewDecisions,
    DS1SamplingPlan,
    DS2BatchApproval,
    DS2CandidateManifest,
    DS2EvidenceDataset,
    DS2ReviewDecisions,
    DS3KnowledgePointDataset,
    DS3ReviewDecisions,
    DS3SectionScopeDataset,
    DS3SplitManifest,
    DS4QueryProcessingDataset,
    DS5RetrievalQADataset,
    DS6CitationMigrationDataset,
    DS7IncrementalWritebackDataset,
    DS8PerformanceDataset,
    P03EvalIdentitySnapshot,
    P04InputWorkPackage,
    P05OCRBatchApproval,
    P05OCRCandidateManifest,
    P07GoldBundleApproval,
    P07GoldBundleManifest,
    P08DS5SplitManifest,
    P08GoldBundleApproval,
    P08GoldBundleManifest,
    P08ReviewDecisions,
    P08SourcePackageDataset,
    P09ClaimCitationPhase1Approval,
    P09ClaimCitationPhase1Decisions,
    P09ClaimCitationPhase1Package,
    P09ClaimCitationPhase2Approval,
    P09ClaimCitationPhase2Decisions,
    P09ClaimCitationPhase2Package,
    P09ContextGoldDataset,
    P09CoverageAuditDataset,
    P09GoldBundleApproval,
    P09GoldBundleManifest,
    P09QAGoldDataset,
    P09ReviewDecisions,
    QAHumanReviewRecord,
    QAHumanScoreDataset,
)
from evaluation.contracts import CandidateRevisionHistory, TestLock
from evaluation.manifest import RunManifest
from evaluation.p10_2_security_data import (
    P102BlindCommitment,
    P102DevApproval,
    P102SecurityDevCandidate,
)
from evaluation.p10_3_security_data import (
    P103BlindCommitment,
    P103DevApproval,
    P103ReviewPass,
    P103SecurityDevCandidate,
)
from evaluation.p10_schemas import (
    P10BundleApproval,
    P10BundleManifest,
    P10ComponentSplitManifest,
    P10DS6Dataset,
    P10DS7Dataset,
    P10DS8Dataset,
    P10FixtureManifest,
    P10ReviewDecisions,
    P10SecurityDataset,
    P17SecurityQualificationDataset,
)

SCHEMA_MODELS: dict[str, type[BaseModel]] = {
    "course_eval_candidate_revision_history.schema.json": CandidateRevisionHistory,
    "courserag_corpus_fixture_manifest.schema.json": CorpusFixtureManifest,
    "courserag_ds0.schema.json": DS0CorpusDataset,
    "courserag_ds1.schema.json": DS1ParsingDataset,
    "courserag_ds1_batch_approval.schema.json": DS1BatchApproval,
    "courserag_ds1_candidate_manifest.schema.json": DS1CandidateManifest,
    "courserag_ds1_review_decisions.schema.json": DS1ReviewDecisions,
    "courserag_ds1_sampling_plan.schema.json": DS1SamplingPlan,
    "courserag_p03_eval_identity_snapshot.schema.json": P03EvalIdentitySnapshot,
    "courserag_p04_input_work_package.schema.json": P04InputWorkPackage,
    "courserag_p05_ocr_batch_approval.schema.json": P05OCRBatchApproval,
    "courserag_p05_ocr_candidate_manifest.schema.json": P05OCRCandidateManifest,
    "courserag_ds2.schema.json": DS2EvidenceDataset,
    "courserag_ds2_batch_approval.schema.json": DS2BatchApproval,
    "courserag_ds2_candidate_manifest.schema.json": DS2CandidateManifest,
    "courserag_ds2_review_decisions.schema.json": DS2ReviewDecisions,
    "courserag_ds3.schema.json": DS3KnowledgePointDataset,
    "courserag_ds3_review_decisions.schema.json": DS3ReviewDecisions,
    "courserag_ds3_section_scopes.schema.json": DS3SectionScopeDataset,
    "courserag_ds3_split.schema.json": DS3SplitManifest,
    "courserag_p07_gold_bundle_approval.schema.json": P07GoldBundleApproval,
    "courserag_p07_gold_bundle_manifest.schema.json": P07GoldBundleManifest,
    "courserag_p08_source_packages.schema.json": P08SourcePackageDataset,
    "courserag_p08_ds5_split.schema.json": P08DS5SplitManifest,
    "courserag_p08_review_decisions.schema.json": P08ReviewDecisions,
    "courserag_p08_gold_bundle_manifest.schema.json": P08GoldBundleManifest,
    "courserag_p08_gold_bundle_approval.schema.json": P08GoldBundleApproval,
    "courserag_p09_qa_gold.schema.json": P09QAGoldDataset,
    "courserag_p09_claim_citation_phase1_approval.schema.json": (P09ClaimCitationPhase1Approval),
    "courserag_p09_claim_citation_phase1_package.schema.json": (P09ClaimCitationPhase1Package),
    "courserag_p09_claim_citation_phase1_decisions.schema.json": (P09ClaimCitationPhase1Decisions),
    "courserag_p09_claim_citation_phase2_package.schema.json": (P09ClaimCitationPhase2Package),
    "courserag_p09_claim_citation_phase2_decisions.schema.json": (P09ClaimCitationPhase2Decisions),
    "courserag_p09_claim_citation_phase2_approval.schema.json": (P09ClaimCitationPhase2Approval),
    "courserag_p09_context_gold.schema.json": P09ContextGoldDataset,
    "courserag_p09_coverage_audit.schema.json": P09CoverageAuditDataset,
    "courserag_p09_review_decisions.schema.json": P09ReviewDecisions,
    "courserag_p09_gold_bundle_manifest.schema.json": P09GoldBundleManifest,
    "courserag_p09_gold_bundle_approval.schema.json": P09GoldBundleApproval,
    "courserag_ds4.schema.json": DS4QueryProcessingDataset,
    "courserag_ds5.schema.json": DS5RetrievalQADataset,
    "courserag_ds6.schema.json": DS6CitationMigrationDataset,
    "courserag_ds7.schema.json": DS7IncrementalWritebackDataset,
    "courserag_ds8.schema.json": DS8PerformanceDataset,
    "courserag_ds6_formal.schema.json": P10DS6Dataset,
    "courserag_ds7_formal.schema.json": P10DS7Dataset,
    "courserag_ds8_formal.schema.json": P10DS8Dataset,
    "courserag_p10_security_control.schema.json": P10SecurityDataset,
    "courserag_p17_security_qualification_dev.schema.json": P17SecurityQualificationDataset,
    "courserag_p10_fixture_manifest.schema.json": P10FixtureManifest,
    "courserag_p10_component_splits.schema.json": P10ComponentSplitManifest,
    "courserag_p10_review_decisions.schema.json": P10ReviewDecisions,
    "courserag_p10_input_bundle_manifest.schema.json": P10BundleManifest,
    "courserag_p10_input_bundle_approval.schema.json": P10BundleApproval,
    "courserag_p10_2_security_dev.schema.json": P102SecurityDevCandidate,
    "courserag_p10_2_security_dev_approval.schema.json": P102DevApproval,
    "courserag_p10_2_security_blind_commitment.schema.json": P102BlindCommitment,
    "courserag_p10_3_security_dev.schema.json": P103SecurityDevCandidate,
    "courserag_p10_3_security_review.schema.json": P103ReviewPass,
    "courserag_p10_3_security_dev_approval.schema.json": P103DevApproval,
    "courserag_p10_3_security_blind_commitment.schema.json": P103BlindCommitment,
    "courserag_qa_human_scores.schema.json": QAHumanScoreDataset,
    "courserag_qa_human_score_record.schema.json": QAHumanReviewRecord,
    "coursepilot_cp_ds0.schema.json": CPDS0ManifestDataset,
    "coursepilot_cp_ds1.schema.json": CPDS1LessonDataset,
    "coursepilot_cp_ds1_p14_pilot.schema.json": CPDS1P14PilotDataset,
    "coursepilot_cp_ds1_p14_fixtures.schema.json": P14FixtureBundle,
    "coursepilot_cp_ds2_p15_pilot.schema.json": CPDS2P15PilotDataset,
    "coursepilot_cp_ds2_p15_fixtures.schema.json": P15FixtureBundle,
    "coursepilot_p15_review_decisions.schema.json": P15ReviewDecisions,
    "coursepilot_p15_bundle_approval.schema.json": P15BundleApproval,
    "coursepilot_p14_review_decisions.schema.json": P14ReviewDecisions,
    "coursepilot_p14_bundle_approval.schema.json": P14BundleApproval,
    "coursepilot_cp_ds2.schema.json": CPDS2ExamDataset,
    "coursepilot_cp_ds3.schema.json": CPDS3PPTDataset,
    "coursepilot_cp_ds3_p16_pilot.schema.json": CPDS3P16PilotDataset,
    "coursepilot_cp_ds4.schema.json": CPDS4ValidationDataset,
    "coursepilot_cp_ds5.schema.json": CPDS5RepairDataset,
    "coursepilot_cp_ds6.schema.json": CPDS6RecoveryDataset,
    "coursepilot_cp_ds6_p12_pilot.schema.json": CPDS6P12PilotDataset,
    "coursepilot_cp_ds4_p13_pilot.schema.json": CPDS4P13PilotDataset,
    "coursepilot_cp_ds5_p13_pilot.schema.json": CPDS5P13PilotDataset,
    "coursepilot_cp_ds7.schema.json": CPDS7ExportDataset,
    "coursepilot_cp_ds7_p16_pilot.schema.json": CPDS7P16PilotDataset,
    "coursepilot_p16_review_decisions.schema.json": P16ReviewDecisions,
    "coursepilot_p16_bundle_manifest.schema.json": P16BundleManifest,
    "coursepilot_p16_bundle_approval.schema.json": P16BundleApproval,
    "coursepilot_cp_ds8.schema.json": CPDS8FaultSecurityDataset,
    "coursepilot_cp_ds8_p17.schema.json": CPDS8P17Dataset,
    "coursepilot_sys_ds1.schema.json": SYSDS1JourneyDataset,
    "coursepilot_sys_ds1_p17.schema.json": SYSDS1P17Dataset,
    "coursepilot_human_scores.schema.json": HumanScoreDataset,
    "coursepilot_human_score_record.schema.json": HumanScoreJsonlRecord,
    "run_manifest.schema.json": RunManifest,
    "test_lock.schema.json": TestLock,
}

DEFAULT_SCHEMA_DIR = Path("datasets/schemas/v1")


def schema_text(model: type[BaseModel]) -> str:
    return (
        json.dumps(
            model.model_json_schema(mode="validation"),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )


def export_schemas(output_dir: Path, *, check: bool) -> list[str]:
    mismatches: list[str] = []
    if not check:
        output_dir.mkdir(parents=True, exist_ok=True)
    for filename, model in SCHEMA_MODELS.items():
        path = output_dir / filename
        expected = schema_text(model)
        if check:
            if not path.is_file() or path.read_text(encoding="utf-8") != expected:
                mismatches.append(filename)
        else:
            path.write_text(expected, encoding="utf-8")
    return mismatches


def main() -> None:
    parser = argparse.ArgumentParser(description="Export or verify P02 JSON Schema artifacts.")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_SCHEMA_DIR)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    mismatches = export_schemas(args.output_dir, check=args.check)
    if mismatches:
        raise SystemExit(f"Schema artifacts differ: {', '.join(mismatches)}")
    action = "verified" if args.check else "exported"
    print(f"{action} {len(SCHEMA_MODELS)} schemas in {args.output_dir}")


if __name__ == "__main__":
    main()
