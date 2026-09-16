"""Build the blinded phase-1 P09 Claim-Citation human review package.

The package is derived only from the fixed Answer Grounding Dev output and
local Evidence artifacts.  It never calls a Provider and deliberately omits
Gold Claims from the phase-1 reviewer view.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
from pathlib import Path
from typing import Literal, cast

from pydantic import JsonValue

from courserag.evals.schemas import (
    P09ClaimCitationPhase1Approval,
    P09ClaimCitationPhase1Decisions,
    P09ClaimCitationPhase1Package,
    P09ClaimCitationPhase2Case,
    P09ClaimCitationPhase2CaseDecision,
    P09ClaimCitationPhase2Citation,
    P09ClaimCitationPhase2ClaimMapping,
    P09ClaimCitationPhase2Decisions,
    P09ClaimCitationPhase2GoldClaim,
    P09ClaimCitationPhase2GoldSupport,
    P09ClaimCitationPhase2Package,
    P09ClaimCitationPhase2SystemClaim,
    P09ClaimCitationReviewCase,
    P09ClaimCitationReviewClaim,
    P09ClaimCitationReviewEvidence,
    P09ClaimCitationReviewLink,
    P09ClaimCitationSupportCaseDecision,
    P09ClaimCitationSupportClaimDecision,
    P09ClaimCitationSupportLinkDecision,
)
from evaluation.io import atomic_write_json, atomic_write_text
from evaluation.manifest import sha256_file
from evaluation.p09_corpus import P09RuntimeCorpus, load_p09_runtime_corpus
from evaluation.p09_dev_loader import load_p09_dev_bundle
from evaluation.p09_retrieval_qa_eval import P09SystemResult

SOURCE_REPORT_SHA256 = "b04fc9b620fccddecaf889c201fa5b8d0cec139b92686a2ac354dffed853f77b"
SOURCE_CHECKPOINT_SHA256 = "2a53b2693592c6810781c05036a9110a39d72599b2c6c36b170bf12e48da4ccc"
GOLD_APPROVAL_FILE_SHA256 = "a19ab29918c4b6b53da0c148c04849ab6e570b8b8ff2350dd58a3c858f4d8cef"
APPROVED_GOLD_BUNDLE_SHA256 = "5a84bac041375310d5bb80f17f7481464d07dbcf75f9f980c6b8a030e58af0c1"
APPROVED_QA_SHA256 = "d3460b0831b5ce7567e0c97c82b0574c2aeb31776944fba9982e3f21d84d62c7"
PHASE1_DECISIONS_SHA256 = "52e0044ecc702e3ecc0cc9c0b3045a0f5a1f4c0aeaa95dc86f37c0a7b50ec314"
PHASE1_APPROVAL_STATEMENT = (
    "批准 P09 Claim-Citation Phase 1 Decisions，SHA-256: " + PHASE1_DECISIONS_SHA256
)


def write_phase1_review_package(repository_root: Path, output_dir: Path) -> dict[str, str]:
    root = repository_root.resolve()
    output = output_dir.resolve()
    report_path = root / "storage_eval/p09_answer_grounding/run-1/report.json"
    checkpoint_path = root / "storage_eval/p09_answer_grounding/run-1/checkpoint.json"
    approval_path = root / "datasets/courserag_eval/v1/provenance/p09_gold_bundle_approval.json"
    qa_path = root / "datasets/courserag_eval/v1/approved/ds5/p09_qa.json"
    _require_hash(report_path, SOURCE_REPORT_SHA256)
    _require_hash(checkpoint_path, SOURCE_CHECKPOINT_SHA256)
    _require_hash(approval_path, GOLD_APPROVAL_FILE_SHA256)
    _require_hash(qa_path, APPROVED_QA_SHA256)
    approval = json.loads(approval_path.read_text(encoding="utf-8"))
    if approval.get("bundle_sha256") != APPROVED_GOLD_BUNDLE_SHA256:
        raise ValueError("phase-1 review requires the exact Approved P09 Gold Bundle")

    bundle = load_p09_dev_bundle(root / "datasets/courserag_eval/v1")
    main = [item for item in bundle.cases if item.qa.evaluation_stratum == "retrieval_main"]
    report = json.loads(report_path.read_text(encoding="utf-8"))
    runtime_corpus = load_p09_runtime_corpus(root)
    cases: list[P09ClaimCitationReviewCase] = []
    required_gold_claim_count = 0
    for item in main:
        required_gold_claim_count += sum(
            claim.importance == "required" for claim in item.qa.gold_claims
        )
        state = report["cases"].get(f"q3:{item.qa.record_id}")
        if not isinstance(state, dict) or not isinstance(state.get("result"), dict):
            raise ValueError(f"fixed Report is missing q3 Case {item.qa.record_id}")
        result = P09SystemResult.model_validate(state["result"])
        cases.append(_review_case(item.qa.record_id, item.qa.query, result, runtime_corpus))
    cases.sort(key=lambda item: item.blinded_sample_id)
    claims = [claim for case in cases for claim in case.claims]
    links = [link for claim in claims for link in claim.citations]
    package = P09ClaimCitationPhase1Package(
        dataset_id="courserag-p09-claim-citation-review",
        dataset_version="phase1-v1",
        source_report_sha256=SOURCE_REPORT_SHA256,
        source_checkpoint_sha256=SOURCE_CHECKPOINT_SHA256,
        approved_gold_bundle_sha256=APPROVED_GOLD_BUNDLE_SHA256,
        approved_qa_sha256=APPROVED_QA_SHA256,
        case_count=len(cases),
        answered_case_count=sum(case.answer_status == "answered" for case in cases),
        abstained_case_count=sum(
            case.answer_status == "abstained_insufficient_evidence" for case in cases
        ),
        failed_case_count=sum(case.answer_status == "failed" for case in cases),
        system_claim_count=len(claims),
        citation_link_count=len(links),
        cases=cases,
    )
    _validate_frozen_scope(package, required_gold_claim_count=required_gold_claim_count)
    output.mkdir(parents=True, exist_ok=True)
    package_path = output / "phase1_package.json"
    atomic_write_json(package_path, cast(JsonValue, package.model_dump(mode="json")))
    package_sha256 = sha256_file(package_path)
    decisions = _decision_template(package, package_sha256)
    decisions_path = output / "phase1_decisions.template.json"
    atomic_write_json(decisions_path, cast(JsonValue, decisions.model_dump(mode="json")))
    export_script_path = output / "recovery_export.js"
    atomic_write_text(export_script_path, _export_script())
    html_path = output / "index.html"
    atomic_write_text(html_path, _review_html(package, package_sha256))
    manifest: dict[str, JsonValue] = {
        "schema_version": "courserag.p09-claim-citation-review-manifest.v1",
        "phase": "claim_citation_support_blinded",
        "status": "awaiting_course_owner_phase1_review",
        "test_access": False,
        "provider_calls": {"deepseek": 0, "cohere": 0, "other": 0},
        "source_report_sha256": SOURCE_REPORT_SHA256,
        "source_checkpoint_sha256": SOURCE_CHECKPOINT_SHA256,
        "approved_gold_bundle_sha256": APPROVED_GOLD_BUNDLE_SHA256,
        "package_sha256": package_sha256,
        "decision_template_sha256": sha256_file(decisions_path),
        "review_index_sha256": sha256_file(html_path),
        "recovery_export_sha256": sha256_file(export_script_path),
        "counts": {
            "cases": package.case_count,
            "answered": package.answered_case_count,
            "abstained": package.abstained_case_count,
            "failed": package.failed_case_count,
            "system_claims": package.system_claim_count,
            "citation_links": package.citation_link_count,
            "required_gold_claims_hidden_from_phase1": required_gold_claim_count,
        },
    }
    manifest_path = output / "review_manifest.json"
    atomic_write_json(manifest_path, manifest)
    return {
        "review_index": str(html_path),
        "review_index_sha256": sha256_file(html_path),
        "package": str(package_path),
        "package_sha256": package_sha256,
        "decision_template": str(decisions_path),
        "decision_template_sha256": sha256_file(decisions_path),
        "recovery_export": str(export_script_path),
        "recovery_export_sha256": sha256_file(export_script_path),
        "manifest": str(manifest_path),
        "manifest_sha256": sha256_file(manifest_path),
    }


def validate_phase1_decisions(package_path: Path, decisions_path: Path) -> dict[str, int | str]:
    package = P09ClaimCitationPhase1Package.model_validate_json(
        package_path.read_text(encoding="utf-8")
    )
    decisions = P09ClaimCitationPhase1Decisions.model_validate_json(
        decisions_path.read_text(encoding="utf-8")
    )
    package_sha256 = sha256_file(package_path)
    if decisions.source_package_sha256 != package_sha256:
        raise ValueError("phase-1 decisions do not bind the exact review Package")
    expected_cases = {case.case_id: case for case in package.cases}
    actual_cases = {case.case_id: case for case in decisions.cases}
    if len(actual_cases) != len(decisions.cases) or set(actual_cases) != set(expected_cases):
        raise ValueError("phase-1 decision Case IDs do not match the review Package")
    for case_id, expected in expected_cases.items():
        actual = actual_cases[case_id]
        if actual.system_answer_id != expected.system_answer_id:
            raise ValueError(f"phase-1 system Answer identity changed: {case_id}")
        if expected.answer_status == "answered" and actual.conciseness_pass is None:
            raise ValueError(f"answered phase-1 Case requires conciseness review: {case_id}")
        if expected.answer_status != "answered" and actual.conciseness_pass is not None:
            raise ValueError(f"non-answered phase-1 Case has inapplicable conciseness: {case_id}")
        expected_claims = {claim.system_claim_id: claim for claim in expected.claims}
        actual_claims = {claim.system_claim_id: claim for claim in actual.claims}
        if len(actual_claims) != len(actual.claims) or set(actual_claims) != set(expected_claims):
            raise ValueError(f"phase-1 Claim IDs do not match the review Package: {case_id}")
        for claim_id, expected_claim in expected_claims.items():
            expected_citations = {link.citation_id for link in expected_claim.citations}
            actual_citations = [link.citation_id for link in actual_claims[claim_id].citations]
            if (
                len(actual_citations) != len(set(actual_citations))
                or set(actual_citations) != expected_citations
            ):
                raise ValueError(
                    f"phase-1 Citation IDs do not match the review Package: {claim_id}"
                )
    return {
        "status": "valid_submitted_phase1_decisions",
        "reviewer_id": decisions.reviewer_id or "",
        "package_sha256": package_sha256,
        "decisions_sha256": sha256_file(decisions_path),
        "case_count": len(decisions.cases),
        "claim_count": sum(len(case.claims) for case in decisions.cases),
        "citation_link_count": sum(
            len(claim.citations) for case in decisions.cases for claim in case.claims
        ),
    }


def write_phase2_review_package(repository_root: Path, output_dir: Path) -> dict[str, str]:
    root = repository_root.resolve()
    output = output_dir.resolve()
    phase1_package_path = output / "phase1_package.json"
    phase1_decisions_path = output / "phase1_decisions.json"
    _require_hash(phase1_decisions_path, PHASE1_DECISIONS_SHA256)
    validation = validate_phase1_decisions(phase1_package_path, phase1_decisions_path)
    if validation["status"] != "valid_submitted_phase1_decisions":
        raise ValueError("phase-2 requires valid submitted phase-1 decisions")

    phase1_package = P09ClaimCitationPhase1Package.model_validate_json(
        phase1_package_path.read_text(encoding="utf-8")
    )
    phase1_decisions = P09ClaimCitationPhase1Decisions.model_validate_json(
        phase1_decisions_path.read_text(encoding="utf-8")
    )
    approval = P09ClaimCitationPhase1Approval(
        dataset_id=phase1_package.dataset_id,
        dataset_version="phase1-approved-v1",
        reviewer_id=phase1_decisions.reviewer_id or "course_owner",
        approval_date="2026-08-09",
        source_package_sha256=sha256_file(phase1_package_path),
        decisions_sha256=PHASE1_DECISIONS_SHA256,
        approval_statement=PHASE1_APPROVAL_STATEMENT,
        approval_statement_sha256=_sha(PHASE1_APPROVAL_STATEMENT),
    )
    approval_path = output / "phase1_approval.json"
    atomic_write_json(approval_path, cast(JsonValue, approval.model_dump(mode="json")))
    approval_sha256 = sha256_file(approval_path)

    bundle = load_p09_dev_bundle(root / "datasets/courserag_eval/v1")
    gold_by_id = {
        item.qa.record_id: item.qa
        for item in bundle.cases
        if item.qa.evaluation_stratum == "retrieval_main"
    }
    decision_by_id = {item.case_id: item for item in phase1_decisions.cases}
    phase2_cases: list[P09ClaimCitationPhase2Case] = []
    for phase1_case in phase1_package.cases:
        gold = gold_by_id.get(phase1_case.case_id)
        phase1_decision = decision_by_id.get(phase1_case.case_id)
        if gold is None or phase1_decision is None:
            raise ValueError(f"phase-2 source identity is missing: {phase1_case.case_id}")
        claim_decisions = {item.system_claim_id: item for item in phase1_decision.claims}
        system_claims: list[P09ClaimCitationPhase2SystemClaim] = []
        for claim in phase1_case.claims:
            locked = claim_decisions[claim.system_claim_id]
            if locked.label is None:
                raise ValueError("phase-2 cannot use an incomplete phase-1 Claim label")
            support_by_citation = {
                item.citation_id: item.supports_claim for item in locked.citations
            }
            system_claims.append(
                P09ClaimCitationPhase2SystemClaim(
                    system_claim_id=claim.system_claim_id,
                    ordinal=claim.ordinal,
                    text=claim.text,
                    text_sha256=claim.text_sha256,
                    phase1_label=locked.label,
                    citations=[
                        P09ClaimCitationPhase2Citation(
                            citation_id=link.citation_id,
                            supports_claim=bool(support_by_citation[link.citation_id]),
                            cited_evidence_id=link.cited_evidence_id,
                            evidence=link.evidence,
                        )
                        for link in claim.citations
                    ],
                )
            )
        required_gold_claims = [
            P09ClaimCitationPhase2GoldClaim(
                gold_claim_id=claim.claim_id,
                text=claim.claim_text,
                text_sha256=claim.claim_text_sha256 or _sha(claim.claim_text),
                required_evidence_ids=list(claim.required_evidence_ids),
                supports=[
                    P09ClaimCitationPhase2GoldSupport(
                        evidence_id=support.evidence_id,
                        support_role=support.support_role,
                        exact_support_excerpt=support.exact_support_excerpt,
                        exact_support_excerpt_sha256=support.exact_support_excerpt_sha256,
                    )
                    for support in claim.evidence_supports
                ],
            )
            for claim in gold.gold_claims
            if claim.importance == "required"
        ]
        phase2_cases.append(
            P09ClaimCitationPhase2Case(
                case_id=phase1_case.case_id,
                system_answer_id=phase1_case.system_answer_id,
                query=phase1_case.query,
                answerable=gold.answerable,
                answer_status=phase1_case.answer_status,
                answer=phase1_case.answer,
                phase1_conciseness_pass=phase1_decision.conciseness_pass,
                system_claims=system_claims,
                required_gold_claims=required_gold_claims,
            )
        )
    phase2_cases.sort(key=lambda item: item.case_id)
    package = P09ClaimCitationPhase2Package(
        dataset_id=phase1_package.dataset_id,
        dataset_version="phase2-v1",
        phase1_package_sha256=sha256_file(phase1_package_path),
        phase1_decisions_sha256=PHASE1_DECISIONS_SHA256,
        phase1_approval_sha256=approval_sha256,
        approved_gold_bundle_sha256=APPROVED_GOLD_BUNDLE_SHA256,
        approved_qa_sha256=APPROVED_QA_SHA256,
        case_count=len(phase2_cases),
        system_claim_count=sum(len(item.system_claims) for item in phase2_cases),
        required_gold_claim_count=sum(len(item.required_gold_claims) for item in phase2_cases),
        cases=phase2_cases,
    )
    _validate_phase2_scope(package)
    package_path = output / "phase2_package.json"
    atomic_write_json(package_path, cast(JsonValue, package.model_dump(mode="json")))
    package_sha256 = sha256_file(package_path)
    decisions = _phase2_decision_template(package, package_sha256)
    decisions_path = output / "phase2_decisions.template.json"
    atomic_write_json(decisions_path, cast(JsonValue, decisions.model_dump(mode="json")))
    export_path = output / "phase2_export.js"
    atomic_write_text(export_path, _phase2_export_script())
    html_path = output / "phase2_index.html"
    atomic_write_text(html_path, _phase2_review_html(package, package_sha256))
    manifest: dict[str, JsonValue] = {
        "schema_version": "courserag.p09-claim-citation-phase2-review-manifest.v1",
        "phase": "gold_claim_mapping",
        "status": "awaiting_course_owner_phase2_review",
        "test_access": False,
        "provider_calls": {"deepseek": 0, "cohere": 0, "other": 0},
        "phase1_package_sha256": package.phase1_package_sha256,
        "phase1_decisions_sha256": package.phase1_decisions_sha256,
        "phase1_approval_sha256": approval_sha256,
        "phase2_package_sha256": package_sha256,
        "phase2_decision_template_sha256": sha256_file(decisions_path),
        "phase2_review_index_sha256": sha256_file(html_path),
        "phase2_export_sha256": sha256_file(export_path),
        "counts": {
            "cases": package.case_count,
            "system_claims": package.system_claim_count,
            "required_gold_claims": package.required_gold_claim_count,
        },
    }
    manifest_path = output / "phase2_review_manifest.json"
    atomic_write_json(manifest_path, manifest)
    return {
        "phase1_approval": str(approval_path),
        "phase1_approval_sha256": approval_sha256,
        "phase2_review_index": str(html_path),
        "phase2_review_index_sha256": sha256_file(html_path),
        "phase2_package": str(package_path),
        "phase2_package_sha256": package_sha256,
        "phase2_decision_template": str(decisions_path),
        "phase2_decision_template_sha256": sha256_file(decisions_path),
        "phase2_export": str(export_path),
        "phase2_export_sha256": sha256_file(export_path),
        "phase2_manifest": str(manifest_path),
        "phase2_manifest_sha256": sha256_file(manifest_path),
    }


def validate_phase2_decisions(package_path: Path, decisions_path: Path) -> dict[str, int | str]:
    package = P09ClaimCitationPhase2Package.model_validate_json(
        package_path.read_text(encoding="utf-8")
    )
    decisions = P09ClaimCitationPhase2Decisions.model_validate_json(
        decisions_path.read_text(encoding="utf-8")
    )
    if decisions.review_status != "submitted":
        raise ValueError("phase-2 decisions must be submitted before validation")
    package_sha256 = sha256_file(package_path)
    if decisions.source_package_sha256 != package_sha256:
        raise ValueError("phase-2 decisions do not bind the exact review Package")
    expected_cases = {item.case_id: item for item in package.cases}
    actual_cases = {item.case_id: item for item in decisions.cases}
    if len(actual_cases) != len(decisions.cases) or set(actual_cases) != set(expected_cases):
        raise ValueError("phase-2 decision Case IDs do not match the review Package")
    mapping_count = 0
    missed_count = 0
    for case_id, expected in expected_cases.items():
        actual = actual_cases[case_id]
        if actual.system_answer_id != expected.system_answer_id:
            raise ValueError(f"phase-2 system Answer identity changed: {case_id}")
        expected_system = {item.system_claim_id: item for item in expected.system_claims}
        actual_mappings = {item.system_claim_id: item for item in actual.mappings}
        if len(actual_mappings) != len(actual.mappings) or set(actual_mappings) != set(
            expected_system
        ):
            raise ValueError(f"phase-2 system Claim IDs do not match the Package: {case_id}")
        gold_ids = {item.gold_claim_id for item in expected.required_gold_claims}
        matched: set[str] = set()
        for claim_id, mapping in actual_mappings.items():
            matches = mapping.matched_gold_claim_ids
            if len(matches) != len(set(matches)) or not set(matches).issubset(gold_ids):
                raise ValueError(f"phase-2 mapping has invalid Gold Claim IDs: {claim_id}")
            if matches and expected_system[claim_id].phase1_label not in {
                "correct_supported",
                "correct_but_uncited",
            }:
                raise ValueError(f"phase-2 cannot map an invalid system Claim: {claim_id}")
            matched.update(matches)
            mapping_count += len(matches)
        missed = actual.missed_gold_claim_ids
        if len(missed) != len(set(missed)) or set(missed) != gold_ids - matched:
            raise ValueError(
                f"phase-2 missed Gold Claims must equal the mapping complement: {case_id}"
            )
        if expected.answer_status == "failed" and (matched or set(missed) != gold_ids):
            raise ValueError("failed phase-2 Cases must mark every Required Gold Claim missed")
        missed_count += len(missed)
    return {
        "status": "valid_submitted_phase2_decisions",
        "reviewer_id": decisions.reviewer_id or "",
        "package_sha256": package_sha256,
        "decisions_sha256": sha256_file(decisions_path),
        "case_count": len(decisions.cases),
        "mapping_count": mapping_count,
        "missed_gold_claim_count": missed_count,
    }


def _phase2_decision_template(
    package: P09ClaimCitationPhase2Package, package_sha256: str
) -> P09ClaimCitationPhase2Decisions:
    return P09ClaimCitationPhase2Decisions(
        dataset_id=package.dataset_id,
        dataset_version=package.dataset_version,
        source_package_sha256=package_sha256,
        cases=[
            P09ClaimCitationPhase2CaseDecision(
                case_id=case.case_id,
                system_answer_id=case.system_answer_id,
                mappings=[
                    P09ClaimCitationPhase2ClaimMapping(system_claim_id=claim.system_claim_id)
                    for claim in case.system_claims
                ],
                missed_gold_claim_ids=[item.gold_claim_id for item in case.required_gold_claims],
            )
            for case in package.cases
        ],
    )


def _validate_phase2_scope(package: P09ClaimCitationPhase2Package) -> None:
    actual = (package.case_count, package.system_claim_count, package.required_gold_claim_count)
    if actual != (54, 150, 117):
        raise ValueError(f"fixed P09 phase-2 scope changed: {actual!r}")
    case_ids = [item.case_id for item in package.cases]
    system_ids = [claim.system_claim_id for item in package.cases for claim in item.system_claims]
    gold_ids = [
        claim.gold_claim_id for item in package.cases for claim in item.required_gold_claims
    ]
    if len(case_ids) != len(set(case_ids)):
        raise ValueError("phase-2 Case IDs must be unique")
    if len(system_ids) != len(set(system_ids)):
        raise ValueError("phase-2 system Claim IDs must be unique")
    if len(gold_ids) != len(set(gold_ids)):
        raise ValueError("phase-2 Gold Claim IDs must be unique")


def _review_case(
    case_id: str,
    query: str,
    result: P09SystemResult,
    corpus: P09RuntimeCorpus,
) -> P09ClaimCitationReviewCase:
    result_json = json.dumps(
        result.model_dump(mode="json"), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    answer_id = f"system-answer-{_sha(f'{SOURCE_REPORT_SHA256}|{case_id}|{result_json}')[:32]}"
    context_ids = list(dict.fromkeys(result.selected_evidence_ids))
    context = [_review_evidence(evidence_id, corpus) for evidence_id in context_ids]
    claims: list[P09ClaimCitationReviewClaim] = []
    for ordinal, claim in enumerate(result.claims):
        claim_id = f"system-claim-{_sha(f'{answer_id}|{ordinal}|{claim.text}')[:32]}"
        citations = [
            P09ClaimCitationReviewLink(
                citation_id=f"system-citation-{_sha(f'{claim_id}|{index}|{evidence_id}')[:32]}",
                cited_evidence_id=evidence_id,
                evidence=_review_evidence(evidence_id, corpus),
            )
            for index, evidence_id in enumerate(claim.evidence_ids)
        ]
        claims.append(
            P09ClaimCitationReviewClaim(
                system_claim_id=claim_id,
                ordinal=ordinal,
                text=claim.text,
                text_sha256=_sha(claim.text),
                citations=citations,
            )
        )
    return P09ClaimCitationReviewCase(
        case_id=case_id,
        blinded_sample_id=f"p09-blind-{_sha(f'p09-phase1|{case_id}')[:24]}",
        system_answer_id=answer_id,
        query=query,
        answer_status=_review_status(result.answer_status),
        answer=result.answer,
        answer_type=result.answer_type,
        context_evidence=context,
        claims=claims,
    )


def _review_evidence(evidence_id: str, corpus: P09RuntimeCorpus) -> P09ClaimCitationReviewEvidence:
    evidence = corpus.evidence_by_id.get(evidence_id)
    if evidence is None:
        matches = [
            system_id
            for system_id, gold_id in corpus.gold_by_system_evidence.items()
            if gold_id == evidence_id
        ]
        if len(matches) != 1:
            raise ValueError(
                f"Citation does not resolve uniquely to runtime Evidence: {evidence_id}"
            )
        evidence = corpus.evidence_by_id.get(matches[0])
    if evidence is None:
        raise ValueError(f"resolved runtime Evidence is missing: {evidence_id}")
    labels = [
        box.display_page_label or str(box.physical_page_index)
        for box in evidence.page_bboxes
        if box.display_page_label is not None or box.physical_page_index is not None
    ]
    return P09ClaimCitationReviewEvidence(
        evidence_id=evidence.evidence_id,
        text=evidence.text,
        text_sha256=evidence.content_sha256,
        document_id=evidence.document_id,
        document_version_id=evidence.document_version_id,
        section_id=evidence.section_id,
        section_path=list(evidence.section_path),
        page_labels=list(dict.fromkeys(labels)),
        source_mode=evidence.source_mode,
        warning_codes=list(evidence.warning_codes),
    )


def _decision_template(
    package: P09ClaimCitationPhase1Package, package_sha256: str
) -> P09ClaimCitationPhase1Decisions:
    return P09ClaimCitationPhase1Decisions(
        dataset_id=package.dataset_id,
        dataset_version=package.dataset_version,
        source_package_sha256=package_sha256,
        cases=[
            P09ClaimCitationSupportCaseDecision(
                case_id=case.case_id,
                system_answer_id=case.system_answer_id,
                claims=[
                    P09ClaimCitationSupportClaimDecision(
                        system_claim_id=claim.system_claim_id,
                        citations=[
                            P09ClaimCitationSupportLinkDecision(citation_id=link.citation_id)
                            for link in claim.citations
                        ],
                    )
                    for claim in case.claims
                ],
            )
            for case in package.cases
        ],
    )


def _validate_frozen_scope(
    package: P09ClaimCitationPhase1Package, *, required_gold_claim_count: int
) -> None:
    expected = {
        "case_count": 54,
        "answered_case_count": 47,
        "abstained_case_count": 6,
        "failed_case_count": 1,
        "system_claim_count": 150,
        "citation_link_count": 150,
    }
    actual = {name: getattr(package, name) for name in expected}
    if actual != expected:
        raise ValueError(f"fixed P09 phase-1 scope changed: {actual!r}")
    if required_gold_claim_count != 117:
        raise ValueError("fixed P09 main-Dev Required Gold Claim count changed")
    case_ids = [case.case_id for case in package.cases]
    claim_ids = [claim.system_claim_id for case in package.cases for claim in case.claims]
    citation_ids = [
        link.citation_id
        for case in package.cases
        for claim in case.claims
        for link in claim.citations
    ]
    if len(case_ids) != len(set(case_ids)):
        raise ValueError("phase-1 Case IDs must be unique")
    if len(claim_ids) != len(set(claim_ids)):
        raise ValueError("phase-1 system Claim IDs must be unique")
    if len(citation_ids) != len(set(citation_ids)):
        raise ValueError("phase-1 Citation IDs must be unique")


def _phase2_review_html(package: P09ClaimCitationPhase2Package, package_sha256: str) -> str:
    cards: list[str] = []
    for index, case in enumerate(package.cases, start=1):
        gold_cards = (
            "".join(
                f"""
            <article class="gold" data-gold-id="{html.escape(gold.gold_claim_id)}">
              <h4>{html.escape(gold.gold_claim_id)}</h4>
              <p>{html.escape(gold.text)}</p>
              <details><summary>查看 Approved Gold 的精确原文支持</summary>
                {"".join(f"<blockquote><code>{html.escape(s.evidence_id)}</code><br>{html.escape(s.exact_support_excerpt)}</blockquote>" for s in gold.supports)}
              </details>
            </article>"""
                for gold in case.required_gold_claims
            )
            or "<p>不可回答样本：没有 Required Gold Claim。</p>"
        )
        system_cards: list[str] = []
        for claim in case.system_claims:
            eligible = claim.phase1_label in {"correct_supported", "correct_but_uncited"}
            mappings = "".join(
                f'<label><input type="checkbox" class="gold-match" value="{html.escape(gold.gold_claim_id)}"> '
                f"{html.escape(gold.gold_claim_id)} — {html.escape(gold.text)}</label>"
                for gold in case.required_gold_claims
            )
            mapping_panel = (
                f"<fieldset><legend>该系统 Claim 等价覆盖哪些 Required Gold Claim？</legend>{mappings or '无可映射 Gold Claim'}</fieldset>"
                if eligible
                else '<p class="locked">Phase 1 判定为无效 Claim；合同禁止映射到 Gold Claim。</p>'
            )
            citations = "".join(
                f"<li>{'支持' if citation.supports_claim else '不支持'} · "
                f"<code>{html.escape(citation.evidence.evidence_id)}</code>"
                f"<blockquote>{html.escape(citation.evidence.text)}</blockquote></li>"
                for citation in claim.citations
            )
            system_cards.append(
                f"""
                <article class="system-claim" data-system-claim-id="{html.escape(claim.system_claim_id)}">
                  <h4>系统 Claim {claim.ordinal + 1} · Phase 1 锁定标签：<code>{claim.phase1_label}</code></h4>
                  <p>{html.escape(claim.text)}</p>
                  <details><summary>查看 Phase 1 已审核引用</summary><ul>{citations}</ul></details>
                  {mapping_panel}
                </article>"""
            )
        cards.append(
            f"""
            <details class="case" data-case-id="{html.escape(case.case_id)}"
                     data-answer-id="{html.escape(case.system_answer_id)}">
              <summary>{index:02d}. {html.escape(case.case_id)} · {html.escape(case.answer_status)}</summary>
              <h3>问题</h3><p>{html.escape(case.query)}</p>
              <h3>系统回答</h3><p>{html.escape(case.answer or "(无回答)")}</p>
              <p>Phase 1 简洁度：<strong>{case.phase1_conciseness_pass}</strong></p>
              <div class="columns"><section><h3>系统 Claims（Phase 1 已锁定）</h3>{"".join(system_cards) or "<p>没有系统 Claim。</p>"}</section>
              <section><h3>Required Gold Claims</h3>{gold_cards}</section></div>
              <label><input type="checkbox" class="case-reviewed"> 本 Case 映射已审核</label>
              <label>Case 备注 <textarea class="case-notes"></textarea></label>
            </details>"""
        )
    bootstrap = json.dumps(
        {
            "schema_version": "courserag.p09-claim-citation-phase2-decisions.v1",
            "dataset_id": package.dataset_id,
            "dataset_version": package.dataset_version,
            "source_package_sha256": package_sha256,
        },
        ensure_ascii=False,
    ).replace("</", "<\\/")
    return f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><title>P09 Claim-Citation Phase 2</title>
<style>
body{{font:15px/1.6 system-ui;margin:0 auto;max-width:1500px;padding:24px;color:#1d2530}}
.notice{{background:#fff4cf;border:1px solid #d8a800;padding:16px}} #toolbar{{position:sticky;top:0;background:#fff;border-bottom:1px solid #ccd3db;padding:12px;z-index:2}}
details.case{{border:1px solid #ccd3db;border-radius:8px;margin:14px 0;padding:12px}} summary{{cursor:pointer;font-weight:700}}
.columns{{display:grid;grid-template-columns:1fr 1fr;gap:16px}} .system-claim,.gold{{border:1px solid #d7dde4;border-radius:6px;margin:12px 0;padding:12px}}
.system-claim{{background:#f5f8fb}} .gold{{background:#f3fbf2}} .locked{{color:#8a2d2d}} blockquote{{white-space:pre-wrap;border-left:3px solid #8b97a4;margin:8px 0;padding-left:12px}}
label{{display:block;margin:8px 0}} textarea{{display:block;width:100%;min-height:52px}} input,button{{font-size:1rem;padding:5px}} code{{word-break:break-all}}
@media(max-width:900px){{.columns{{grid-template-columns:1fr}}}}
</style></head><body>
<h1>P09 Claim–Citation 人工评审：第二阶段 Gold Claim Mapping</h1>
<div class="notice"><strong>Phase 1 标签已按批准 Hash 锁定，不能在本页修改。</strong> 请逐条判断有效系统 Claim 是否等价覆盖右侧一个或多个 Required Gold Claim。未被任何有效系统 Claim 覆盖的 Gold Claim 将由导出器自动记为 missed。不要按词面相似直接映射；以事实含义和精确原文支持为准。</div>
<div id="toolbar"><label>Reviewer ID <input id="reviewer" value="course_owner"></label>
<span id="progress">0 / {package.case_count}</span> <button id="export">校验并下载 Phase 2 决策 JSON</button></div>
{"".join(cards)}
<script id="bootstrap" type="application/json">{bootstrap}</script>
<script src="phase2_export.js"></script></body></html>"""


def _phase2_export_script() -> str:
    return """(() => {
const base=JSON.parse(document.getElementById('bootstrap').textContent);
const cases=[...document.querySelectorAll('.case')];
function progress(){document.getElementById('progress').textContent=`${cases.filter(x=>x.querySelector('.case-reviewed').checked).length} / ${cases.length}`;}
document.addEventListener('change',progress); progress();
window.exportP09Phase2Decisions=()=>{
  const reviewer=document.getElementById('reviewer').value.trim(); if(!reviewer){alert('请填写 Reviewer ID');return;}
  const errors=[]; const output=[];
  for(const c of cases){
    const reviewed=c.querySelector('.case-reviewed').checked;
    if(!reviewed) errors.push(`${c.dataset.caseId} 未勾选已审核`);
    const goldIds=[...c.querySelectorAll('.gold')].map(x=>x.dataset.goldId);
    const matched=new Set(); const mappings=[];
    for(const cl of c.querySelectorAll('.system-claim')){
      const ids=[...cl.querySelectorAll('.gold-match:checked')].map(x=>x.value);
      ids.forEach(x=>matched.add(x));
      mappings.push({system_claim_id:cl.dataset.systemClaimId,matched_gold_claim_ids:ids});
    }
    const missed=goldIds.filter(x=>!matched.has(x));
    output.push({case_id:c.dataset.caseId,system_answer_id:c.dataset.answerId,reviewed,mappings,
      missed_gold_claim_ids:missed,notes:c.querySelector('.case-notes').value});
  }
  if(errors.length){alert(`仍有 ${errors.length} 项未完成：\\n`+errors.slice(0,20).join('\\n'));return;}
  const payload={...base,review_status:'submitted',reviewer_id:reviewer,cases:output};
  const blob=new Blob([JSON.stringify(payload,null,2)+'\\n'],{type:'application/json'});
  const a=document.createElement('a'); a.href=URL.createObjectURL(blob); a.download='phase2_decisions.json'; a.click(); URL.revokeObjectURL(a.href);
};
document.getElementById('export').addEventListener('click',window.exportP09Phase2Decisions);
})();
"""


def _review_html(package: P09ClaimCitationPhase1Package, package_sha256: str) -> str:
    cards: list[str] = []
    for index, case in enumerate(package.cases, start=1):
        claim_cards: list[str] = []
        for claim in case.claims:
            citations = "".join(
                f"""
                <div class="citation" data-citation-id="{html.escape(link.citation_id)}">
                  <div>报告引用 <code>{html.escape(link.cited_evidence_id)}</code><br>
                  稳定原文 Evidence <code>{html.escape(link.evidence.evidence_id)}</code></div>
                  <blockquote>{html.escape(link.evidence.text)}</blockquote>
                  <label>该 Evidence 是否直接支持当前 Claim？
                    <select class="citation-support">
                      <option value="">请选择</option><option value="true">是</option>
                      <option value="false">否</option>
                    </select>
                  </label>
                </div>"""
                for link in claim.citations
            )
            claim_cards.append(
                f"""
                <section class="claim" data-claim-id="{html.escape(claim.system_claim_id)}">
                  <h4>Claim {claim.ordinal + 1}</h4>
                  <p class="claim-text">{html.escape(claim.text)}</p>
                  {citations}
                  <label>Claim 标签
                    <select class="claim-label">
                      <option value="">请选择</option>
                      <option value="correct_supported">correct_supported</option>
                      <option value="correct_but_uncited">correct_but_uncited</option>
                      <option value="unsupported">unsupported</option>
                      <option value="contradictory">contradictory</option>
                      <option value="irrelevant">irrelevant</option>
                    </select>
                  </label>
                  <label>备注 <textarea class="claim-notes"></textarea></label>
                </section>"""
            )
        context = "".join(
            f"<li><code>{html.escape(item.evidence_id)}</code><div>{html.escape(item.text)}</div></li>"
            for item in case.context_evidence
        )
        conciseness = (
            """
            <label>回答是否足够简洁？
              <select class="conciseness"><option value="">请选择</option>
                <option value="true">通过</option><option value="false">不通过</option>
              </select>
            </label>"""
            if case.answer_status == "answered"
            else "<p>非 answered Case：简洁度不适用。</p>"
        )
        cards.append(
            f"""
            <details class="case" data-case-id="{html.escape(case.case_id)}"
                     data-answer-id="{html.escape(case.system_answer_id)}"
                     data-status="{html.escape(case.answer_status)}">
              <summary>{index:02d}. {html.escape(case.blinded_sample_id)} · {html.escape(case.answer_status)}</summary>
              <h3>Query</h3><p>{html.escape(case.query)}</p>
              <h3>系统回答</h3><p>{html.escape(case.answer or "(无回答)")}</p>
              {conciseness}
              {"".join(claim_cards) if claim_cards else "<p>此 Case 没有系统 Claim。</p>"}
              <details><summary>查看本次 Context Evidence（不含 Gold 标注）</summary><ol>{context}</ol></details>
              <label><input type="checkbox" class="case-reviewed"> 本 Case 已审核</label>
              <label>Case 备注 <textarea class="case-notes"></textarea></label>
            </details>"""
        )
    bootstrap = json.dumps(
        {
            "schema_version": "courserag.p09-claim-citation-phase1-decisions.v1",
            "dataset_id": package.dataset_id,
            "dataset_version": package.dataset_version,
            "source_package_sha256": package_sha256,
        },
        ensure_ascii=False,
    ).replace("</", "<\\/")
    return f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><title>P09 Claim-Citation Phase 1</title>
<style>
body{{font:16px/1.6 system-ui;margin:0 auto;max-width:1180px;padding:24px;color:#1d2530}}
.notice{{background:#fff4cf;border:1px solid #d8a800;padding:16px}} details.case{{border:1px solid #ccd3db;border-radius:8px;margin:14px 0;padding:12px}}
summary{{cursor:pointer;font-weight:700}} .claim{{background:#f5f8fb;border-left:4px solid #4378a8;margin:16px 0;padding:12px}}
.claim-text{{font-size:1.05rem;font-weight:600}} .citation{{background:white;border:1px solid #d7dde4;margin:10px 0;padding:10px}}
blockquote{{white-space:pre-wrap;border-left:3px solid #8b97a4;margin:8px 0;padding-left:12px}} label{{display:block;margin:10px 0}}
textarea{{display:block;width:100%;min-height:52px}} select,input,button{{font-size:1rem;padding:5px}} code{{word-break:break-all}}
#toolbar{{position:sticky;top:0;background:#fff;border-bottom:1px solid #ccd3db;padding:12px;z-index:2}}
</style></head><body>
<h1>P09 Claim—Citation 人工评审：第一阶段</h1>
<div class="notice"><strong>本阶段不显示 Gold Claim。</strong>只判断系统 Claim 是否正确、其实际 Citation 是否直接支持该 Claim，以及回答是否简洁。完成后下载 JSON；不要修改 Package。</div>
<div id="toolbar"><label>Reviewer ID <input id="reviewer" value="course_owner"></label>
<span id="progress">0 / {package.case_count}</span> <button id="export">校验并下载决策 JSON</button></div>
{"".join(cards)}
<script id="bootstrap" type="application/json">{bootstrap}</script>
<script src="recovery_export.js"></script></body></html>"""


def _export_script() -> str:
    return """(() => {
const base=JSON.parse(document.getElementById('bootstrap').textContent);
const cases=[...document.querySelectorAll('.case')];
function progress(){document.getElementById('progress').textContent=`${cases.filter(x=>x.querySelector('.case-reviewed').checked).length} / ${cases.length}`;}
document.addEventListener('change',progress); progress();
window.recoverP09Decisions=()=>{
  const reviewer=document.getElementById('reviewer').value.trim(); if(!reviewer){alert('请填写 Reviewer ID');return;}
  const errors=[]; const output=[];
  for(const c of cases){
    const reviewed=c.querySelector('.case-reviewed').checked;
    if(!reviewed) errors.push(`${c.dataset.caseId} 未勾选已审核`);
    const conc=c.querySelector('.conciseness');
    if(c.dataset.status==='answered' && (!conc || conc.value==='')) errors.push(`${c.dataset.caseId} 未评简洁度`);
    const claims=[];
    for(const cl of c.querySelectorAll('.claim')){
      const label=cl.querySelector('.claim-label').value;
      if(!label) errors.push(`${cl.dataset.claimId} 未选择 Claim 标签`);
      const citations=[];
      for(const ci of cl.querySelectorAll('.citation')){
        const value=ci.querySelector('.citation-support').value;
        if(value==='') errors.push(`${ci.dataset.citationId} 未判断支持关系`);
        citations.push({citation_id:ci.dataset.citationId,supports_claim:value===''?null:value==='true'});
      }
      const supported=citations.some(x=>x.supports_claim===true);
      if(label==='correct_supported' && !supported) errors.push(`${cl.dataset.claimId} 标签与 Citation 判断冲突`);
      if(label && label!=='correct_supported' && supported) errors.push(`${cl.dataset.claimId} 非 correct_supported 不能含支持 Citation`);
      claims.push({system_claim_id:cl.dataset.claimId,label:label||null,citations,notes:cl.querySelector('.claim-notes').value});
    }
    output.push({case_id:c.dataset.caseId,system_answer_id:c.dataset.answerId,reviewed,
      conciseness_pass:conc&&conc.value!==''?conc.value==='true':null,claims,notes:c.querySelector('.case-notes').value});
  }
  if(errors.length){alert(`仍有 ${errors.length} 项未完成：\\n`+errors.slice(0,20).join('\\n'));return;}
  const payload={...base,review_status:'submitted',reviewer_id:reviewer,cases:output};
  const blob=new Blob([JSON.stringify(payload,null,2)+'\\n'],{type:'application/json'});
  const a=document.createElement('a'); a.href=URL.createObjectURL(blob); a.download='phase1_decisions.json'; a.click(); URL.revokeObjectURL(a.href);
};
document.getElementById('export').addEventListener('click',window.recoverP09Decisions);
})();
"""


def _require_hash(path: Path, expected: str) -> None:
    if not path.is_file() or sha256_file(path) != expected:
        raise ValueError(f"fixed P09 input Hash mismatch: {path}")


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _review_status(
    value: str | None,
) -> Literal["answered", "abstained_insufficient_evidence", "failed"]:
    if value == "answered":
        return "answered"
    if value == "abstained_insufficient_evidence":
        return "abstained_insufficient_evidence"
    if value == "failed":
        return "failed"
    raise ValueError(f"unsupported fixed P09 answer status: {value!r}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build P09 Claim-Citation human review packs.")
    parser.add_argument("--repository-root", type=Path, default=Path.cwd())
    parser.add_argument(
        "--output-dir", type=Path, default=Path("storage_eval/p09_claim_citation_review")
    )
    parser.add_argument("--phase2", action="store_true")
    parser.add_argument("--validate-decisions", type=Path)
    parser.add_argument("--validate-phase2-decisions", type=Path)
    args = parser.parse_args()
    if args.validate_phase2_decisions is not None:
        print(
            json.dumps(
                validate_phase2_decisions(
                    args.output_dir / "phase2_package.json", args.validate_phase2_decisions
                ),
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        return
    if args.validate_decisions is not None:
        print(
            json.dumps(
                validate_phase1_decisions(
                    args.output_dir / "phase1_package.json", args.validate_decisions
                ),
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        return
    if args.phase2:
        print(
            json.dumps(
                write_phase2_review_package(args.repository_root, args.output_dir),
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        return
    print(
        json.dumps(
            write_phase1_review_package(args.repository_root, args.output_dir),
            ensure_ascii=False,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
