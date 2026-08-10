"""Approve one exact, twice-reviewed P09 QA/Context Gold bundle."""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from courserag.evals.schemas import (
    DS2EvidenceDataset,
    DS5RetrievalQADataset,
    P09ContextGoldDataset,
    P09CoverageAuditDataset,
    P09GoldBundleApproval,
    P09GoldBundleManifest,
    P09QAGoldDataset,
    P09ReviewDecisions,
)
from evaluation.contracts import (
    ApprovalRecord,
    CandidateRevisionHistory,
    HashedArtifact,
    ReviewLogEntry,
    ReviewStatus,
    TestLock,
)
from evaluation.corpus_fixtures import sha256_file
from evaluation.datasets import record_digest
from evaluation.ds5_p09_data import bundle_identity_sha256
from evaluation.ds5_p09_r2_revision import _bundle_sha256 as r2_bundle_identity_sha256
from evaluation.io import atomic_write_json, atomic_write_text


def _artifact(repository_root: Path, path: Path) -> HashedArtifact:
    resolved = path.resolve()
    if not resolved.is_file() or not resolved.is_relative_to(repository_root.resolve()):
        raise ValueError("P09 approval artifacts must stay inside the repository")
    return HashedArtifact(
        path=resolved.relative_to(repository_root.resolve()).as_posix(),
        sha256=sha256_file(resolved),
        size_bytes=resolved.stat().st_size,
        media_type="application/json",
    )


def _validate_artifact(repository_root: Path, artifact: HashedArtifact) -> Path:
    path = repository_root / artifact.path
    if sha256_file(path) != artifact.sha256 or path.stat().st_size != artifact.size_bytes:
        raise ValueError(f"P09 artifact changed: {artifact.path}")
    return path


def _append_log(path: Path, additions: list[ReviewLogEntry]) -> None:
    existing_text = path.read_text(encoding="utf-8") if path.exists() else ""
    if existing_text and not existing_text.endswith("\n"):
        raise ValueError("review log must end with a newline")
    existing = {
        item.review_id: item
        for line in existing_text.splitlines()
        if line.strip()
        for item in [ReviewLogEntry.model_validate_json(line)]
    }
    new_lines: list[str] = []
    for addition in additions:
        current = existing.get(addition.review_id)
        if current is not None and current != addition:
            raise ValueError("existing P09 review-log entry differs")
        if current is None:
            new_lines.append(addition.model_dump_json() + "\n")
    atomic_write_text(path, existing_text + "".join(new_lines))


def _approved_record(
    record: Any,
    *,
    candidate_sha256: str,
    review_id: str,
    reviewer_id: str,
    reviewed_at: datetime,
    status_field: str,
) -> tuple[Any, str]:
    provisional = record.model_copy(
        update={"review_status": ReviewStatus.APPROVED, status_field: "approved", "approval": None}
    )
    approved_sha256 = record_digest(provisional)
    values = provisional.model_dump(mode="json")
    values["approval"] = ApprovalRecord(
        review_id=review_id,
        reviewer_id=reviewer_id,
        reviewed_at=reviewed_at,
        candidate_sha256=candidate_sha256,
        approved_record_sha256=approved_sha256,
        notes="P09 QA/Context Gold component approval; P08 Retrieval Gold unchanged.",
    ).model_dump(mode="json")
    return type(record).model_validate(values), approved_sha256


def approve_p09_bundle(
    *,
    dataset_root: Path,
    expected_bundle_sha256: str,
    first_review_path: Path,
    second_review_path: Path,
    reviewer_id: str,
    reviewed_at: datetime,
    review_id: str,
    notes: str,
) -> dict[str, object]:
    dataset_root = dataset_root.resolve()
    repository_root = dataset_root.parent.parent.parent
    manifest_path = dataset_root / "provenance/p09_gold_bundle_manifest.json"
    bundle = P09GoldBundleManifest.model_validate_json(manifest_path.read_text(encoding="utf-8"))
    if bundle.bundle_sha256 != expected_bundle_sha256:
        raise ValueError("literal P09 Gold Bundle SHA-256 does not match")
    if bundle.revision == 1:
        recomputed = bundle_identity_sha256(
            qa_sha256=bundle.qa_candidate.sha256,
            context_sha256=bundle.context_candidate.sha256,
            p08_sha256=bundle.approved_p08_retrieval.sha256,
            qa_record_sha256=bundle.qa_candidate_record_sha256,
            context_record_sha256=bundle.context_candidate_record_sha256,
            p08_record_sha256=bundle.p08_retrieval_record_sha256,
            upstream_sha256=bundle.upstream_approved_sha256,
            preserved_sha256=bundle.preserved_p08_sha256,
            first_review_groups=bundle.first_review_groups,
            second_review_ids=bundle.second_review_ids,
        )
    else:
        if (
            bundle.coverage_audit is None
            or bundle.parent_bundle_sha256 is None
            or bundle.inherited_first_review is None
            or bundle.inherited_second_review is None
        ):
            raise ValueError("P09 r2 Manifest lacks coverage or inherited reviews")
        recomputed = r2_bundle_identity_sha256(
            qa_sha256=bundle.qa_candidate.sha256,
            context_sha256=bundle.context_candidate.sha256,
            coverage_sha256=bundle.coverage_audit.sha256,
            r1_manifest=P09GoldBundleManifest.model_validate_json(
                (dataset_root / "provenance/p09_gold_bundle_manifest_r1.json").read_text(
                    encoding="utf-8"
                )
            ),
            first_review_sha256=bundle.inherited_first_review.sha256,
            second_review_sha256=bundle.inherited_second_review.sha256,
            qa_hashes=bundle.qa_candidate_record_sha256,
            context_hashes=bundle.context_candidate_record_sha256,
            changed_ids=[item for group in bundle.first_review_groups for item in group],
            context_changed_ids=bundle.context_changed_record_ids,
            review_groups=bundle.first_review_groups,
            second_ids=bundle.second_review_ids,
        )
    if recomputed != bundle.bundle_sha256:
        raise ValueError("P09 Bundle identity fields do not match bundle_sha256")
    qa_path = _validate_artifact(repository_root, bundle.qa_candidate)
    context_path = _validate_artifact(repository_root, bundle.context_candidate)
    p08_path = _validate_artifact(repository_root, bundle.approved_p08_retrieval)
    coverage = None
    if bundle.coverage_audit is not None:
        coverage_path = _validate_artifact(repository_root, bundle.coverage_audit)
        coverage = P09CoverageAuditDataset.model_validate_json(
            coverage_path.read_text(encoding="utf-8")
        )
    if bundle.revision == 2:
        assert bundle.inherited_first_review is not None
        assert bundle.inherited_second_review is not None
        inherited_first_path = _validate_artifact(repository_root, bundle.inherited_first_review)
        inherited_second_path = _validate_artifact(repository_root, bundle.inherited_second_review)
        inherited_first = P09ReviewDecisions.model_validate_json(
            inherited_first_path.read_text(encoding="utf-8")
        )
        inherited_second = P09ReviewDecisions.model_validate_json(
            inherited_second_path.read_text(encoding="utf-8")
        )
        r1_manifest = P09GoldBundleManifest.model_validate_json(
            (dataset_root / "provenance/p09_gold_bundle_manifest_r1.json").read_text(
                encoding="utf-8"
            )
        )
        if r1_manifest.bundle_sha256 != bundle.parent_bundle_sha256:
            raise ValueError("P09 r2 parent Bundle differs from frozen r1")
        inherited_expected = (
            [item for group in r1_manifest.first_review_groups for item in group],
            r1_manifest.second_review_ids,
        )
        for inherited, pass_name, expected_ids in (
            (inherited_first, "first", inherited_expected[0]),
            (inherited_second, "second", inherited_expected[1]),
        ):
            if (
                inherited.bundle_sha256 != r1_manifest.bundle_sha256
                or inherited.review_pass != pass_name
                or inherited.expected_record_ids != expected_ids
                or inherited.attestation_source != "course_owner_conversation_attestation"
                or {item.record_id for item in inherited.decisions} != set(expected_ids)
                or any(item.decision != "pass" for item in inherited.decisions)
            ):
                raise ValueError(f"P09 r1 inherited {pass_name} review is incomplete")

    upstream_paths = {
        "approved_ds5_p08": p08_path,
        "p08_gold_bundle_approval": dataset_root / "provenance/p08_gold_bundle_approval.json",
        "approved_ds2_p06": dataset_root / "approved/ds2/p06_evidence.json",
        "approved_ds3_p07": dataset_root / "approved/ds3/p07_knowledge_points.json",
        "approved_ds1_p05": dataset_root / "approved/ds1/p05_ocr.json",
    }
    for name, path in upstream_paths.items():
        if sha256_file(path) != bundle.upstream_approved_sha256[name]:
            raise ValueError(f"upstream Approved artifact changed: {name}")
    preserved_paths = {
        "p08_run_1_report": repository_root / "storage_eval/p08_hybrid_retrieval/run-1/report.json",
        "p08_run_2_report": repository_root / "storage_eval/p08_hybrid_retrieval/run-2/report.json",
        "p08_default_profile": repository_root / "resources/retrieval_profiles/default_v1.json",
    }
    for name, path in preserved_paths.items():
        if sha256_file(path) != bundle.preserved_p08_sha256[name]:
            raise ValueError(f"preserved P08 artifact changed: {name}")
    review_dir = repository_root / bundle.review_pack_relative_path
    if sha256_file(review_dir / "index.html") != bundle.review_pack_index_sha256:
        raise ValueError("P09 first-review HTML changed")
    if sha256_file(review_dir / "second_review.html") != bundle.second_review_index_sha256:
        raise ValueError("P09 second-review HTML changed")

    qa = P09QAGoldDataset.model_validate_json(qa_path.read_text(encoding="utf-8"))
    context = P09ContextGoldDataset.model_validate_json(context_path.read_text(encoding="utf-8"))
    retrieval = DS5RetrievalQADataset.model_validate_json(p08_path.read_text(encoding="utf-8"))
    qa_hashes = {item.record_id: record_digest(item) for item in qa.cases}
    context_hashes = {item.record_id: record_digest(item) for item in context.cases}
    p08_hashes = {item.record_id: record_digest(item) for item in retrieval.cases}
    if qa_hashes != bundle.qa_candidate_record_sha256:
        raise ValueError("P09 QA Candidate record hashes differ from Manifest")
    if context_hashes != bundle.context_candidate_record_sha256:
        raise ValueError("P09 Context Candidate record hashes differ from Manifest")
    if p08_hashes != bundle.p08_retrieval_record_sha256:
        raise ValueError("P08 Retrieval records changed after P09 Candidate generation")
    if any(item.review_status != "candidate" or item.approval is not None for item in qa.cases):
        raise ValueError("P09 approval accepts QA Candidate records only")
    if any(
        item.review_status != "candidate" or item.approval is not None for item in context.cases
    ):
        raise ValueError("P09 approval accepts Context Candidate records only")
    if bundle.revision == 2:
        if coverage is None:
            raise ValueError("P09 r2 approval requires the answer-obligation audit")
        coverage_by_id = {item.qa_case_id: item for item in coverage.cases}
        qa_by_id = {item.record_id: item for item in qa.cases}
        context_by_qa = {item.qa_case_id: item for item in context.cases}
        if set(coverage_by_id) != set(qa_by_id):
            raise ValueError("P09 coverage audit does not contain exactly 100 QA records")
        evidence_dataset = DS2EvidenceDataset.model_validate_json(
            (dataset_root / "approved/ds2/p06_evidence.json").read_text(encoding="utf-8")
        )
        evidence_by_id = {item.evidence_id: item for item in evidence_dataset.evidence}
        for qa_id, qa_case in qa_by_id.items():
            audit = coverage_by_id[qa_id]
            claims = {item.claim_id: item for item in qa_case.gold_claims}
            for obligation in audit.obligations:
                if any(item not in claims for item in obligation.claim_ids):
                    raise ValueError(f"P09 obligation references an unknown Claim: {qa_id}")
            neighbors = {
                item.neighbor_id: item for item in context_by_qa[qa_id].necessary_neighbors
            }
            for claim in qa_case.gold_claims:
                for support in claim.evidence_supports:
                    source = evidence_by_id.get(support.evidence_id)
                    if source is None:
                        raise ValueError(f"P09 Claim references unknown Evidence: {qa_id}")
                    if support.support_source == "evidence_text":
                        if support.exact_support_excerpt not in source.gold_text:
                            raise ValueError(f"P09 Claim excerpt is absent from Evidence: {qa_id}")
                    else:
                        neighbor = neighbors.get(support.necessary_neighbor_id or "")
                        if (
                            neighbor is None
                            or neighbor.evidence_id != support.evidence_id
                            or support.exact_support_excerpt not in neighbor.text
                        ):
                            raise ValueError(f"P09 Claim neighbor support is invalid: {qa_id}")

    first = P09ReviewDecisions.model_validate_json(first_review_path.read_text(encoding="utf-8"))
    second = P09ReviewDecisions.model_validate_json(second_review_path.read_text(encoding="utf-8"))
    first_ids = [item for group in bundle.first_review_groups for item in group]
    for decision, pass_name, expected_ids in (
        (first, "first", first_ids),
        (second, "second", bundle.second_review_ids),
    ):
        if decision.bundle_sha256 != bundle.bundle_sha256 or decision.review_pass != pass_name:
            raise ValueError(f"{pass_name} P09 review targets another Bundle or pass")
        if decision.expected_record_ids != expected_ids:
            raise ValueError(f"{pass_name} P09 expected IDs differ from Manifest")
        if {item.record_id for item in decision.decisions} != set(expected_ids):
            raise ValueError(f"{pass_name} P09 review is incomplete")
        if any(item.decision != "pass" for item in decision.decisions):
            raise ValueError(f"{pass_name} P09 review contains unresolved returns")
        if decision.reviewer_id is not None and decision.reviewer_id != reviewer_id:
            raise ValueError(f"{pass_name} P09 reviewer differs from approval reviewer")
        if decision.reviewed_at is not None and decision.reviewed_at > reviewed_at:
            raise ValueError(f"{pass_name} P09 review timestamp is after approval")

    test_lock = TestLock.model_validate_json(
        (dataset_root / "test.lock.json").read_text(encoding="utf-8")
    )
    if test_lock.locked:
        raise ValueError("P09 approval cannot modify a locked Test set")
    dev_ids = set((dataset_root / "splits/dev_ids.txt").read_text(encoding="utf-8").split())
    test_ids = set((dataset_root / "splits/test_ids.txt").read_text(encoding="utf-8").split())
    if dev_ids != {item.record_id for item in retrieval.cases if item.split == "dev"}:
        raise ValueError("P09 approval detected changed Dev IDs")
    if test_ids != {item.record_id for item in retrieval.cases if item.split == "test"}:
        raise ValueError("P09 approval detected changed Test IDs")

    approved_qa_records = []
    approved_context_records = []
    approved_hashes: dict[str, str] = {}
    log_entries: list[ReviewLogEntry] = []
    candidate_hashes = {**qa_hashes, **context_hashes}
    for index, record in enumerate([*qa.cases, *context.cases], start=1):
        item_review_id = f"{review_id}.record.{index:03d}"
        status_field = "qa_gold_status" if index <= len(qa.cases) else "context_gold_status"
        approved, approved_hash = _approved_record(
            record,
            candidate_sha256=candidate_hashes[record.record_id],
            review_id=item_review_id,
            reviewer_id=reviewer_id,
            reviewed_at=reviewed_at,
            status_field=status_field,
        )
        if index <= len(qa.cases):
            approved_qa_records.append(approved)
        else:
            approved_context_records.append(approved)
        approved_hashes[record.record_id] = approved_hash
        log_entries.append(
            ReviewLogEntry(
                review_id=item_review_id,
                record_id=record.record_id,
                action="approve",
                reviewer_id=reviewer_id,
                reviewed_at=reviewed_at,
                candidate_sha256=candidate_hashes[record.record_id],
                resulting_record_sha256=approved_hash,
                notes="P09 QA/Context Gold only; P08 Retrieval Gold preserved.",
            )
        )
    approved_qa = qa.model_copy(update={"cases": approved_qa_records})
    approved_context = context.model_copy(update={"cases": approved_context_records})
    approved_qa_path = dataset_root / "approved/ds5/p09_qa.json"
    approved_context_path = dataset_root / "approved/ds5/p09_context.json"
    atomic_write_json(approved_qa_path, approved_qa.model_dump(mode="json"))
    atomic_write_json(approved_context_path, approved_context.model_dump(mode="json"))
    review_dir_out = dataset_root / "reviews"
    first_out = review_dir_out / "ds5_p09_first_review_decisions.json"
    second_out = review_dir_out / "ds5_p09_second_review_decisions.json"
    atomic_write_json(first_out, first.model_dump(mode="json"))
    atomic_write_json(second_out, second.model_dump(mode="json"))
    governance_path = dataset_root / "manifest.json"
    governance = json.loads(governance_path.read_text(encoding="utf-8"))
    governance.setdefault("gold_components", {}).update(
        {"ds5_retrieval": "approved", "ds5_qa": "approved", "ds5_context": "approved"}
    )
    governance["gold_status"] = "ds5_p09_qa_context_approved"
    governance.setdefault("phase_input_status", {})["p08"] = "completed_gate_passed"
    governance["phase_input_status"]["p09"] = "formal_dev_eval_ready"
    atomic_write_json(governance_path, governance)
    approval = P09GoldBundleApproval(
        dataset_id="courserag-p09-qa-context-gold-bundle",
        dataset_version=bundle.dataset_version,
        review_id=review_id,
        reviewer_id=reviewer_id,
        reviewed_at=reviewed_at,
        bundle_sha256=bundle.bundle_sha256,
        qa_candidate=bundle.qa_candidate,
        context_candidate=bundle.context_candidate,
        first_review_decisions=_artifact(repository_root, first_out),
        second_review_decisions=_artifact(repository_root, second_out),
        approved_qa=_artifact(repository_root, approved_qa_path),
        approved_context=_artifact(repository_root, approved_context_path),
        candidate_record_sha256=candidate_hashes,
        approved_record_sha256=approved_hashes,
        notes=notes,
    )
    approval_path = dataset_root / "provenance/p09_gold_bundle_approval.json"
    if approval_path.exists():
        existing_approval = P09GoldBundleApproval.model_validate_json(
            approval_path.read_text(encoding="utf-8")
        )
        if existing_approval != approval:
            raise ValueError("existing P09 Bundle approval differs")
    else:
        atomic_write_json(approval_path, approval.model_dump(mode="json"))
    _append_log(dataset_root / "reviews/review_log.jsonl", log_entries)
    if bundle.revision == 2:
        for history_name, candidate in (
            ("p09_candidate_revision_history.json", bundle.qa_candidate),
            ("p09_context_candidate_revision_history.json", bundle.context_candidate),
        ):
            history_path = dataset_root / "provenance" / history_name
            history = CandidateRevisionHistory.model_validate_json(
                history_path.read_text(encoding="utf-8")
            )
            current = [
                entry
                for entry in history.revisions
                if entry.candidate_relative_path == candidate.path
                and entry.candidate_file_sha256 == candidate.sha256
            ]
            if len(current) != 1 or current[0].status not in {
                "pending_course_owner_review",
                "approved",
            }:
                raise ValueError("P09 Candidate revision history differs from approved Candidate")
            approved_history = history.model_copy(
                update={
                    "revisions": [
                        entry.model_copy(update={"status": "approved"})
                        if entry == current[0]
                        else entry
                        for entry in history.revisions
                    ]
                }
            )
            atomic_write_json(history_path, approved_history.model_dump(mode="json"))
    return {
        "bundle_sha256": bundle.bundle_sha256,
        "approved_qa_sha256": sha256_file(approved_qa_path),
        "approved_context_sha256": sha256_file(approved_context_path),
        "record_count": len(approved_hashes),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Approve exact P09 QA/Context Gold Bundle.")
    parser.add_argument("--dataset-root", type=Path, default=Path("datasets/courserag_eval/v1"))
    parser.add_argument("--bundle-sha256", required=True)
    parser.add_argument("--first-review", type=Path, required=True)
    parser.add_argument("--second-review", type=Path, required=True)
    parser.add_argument("--reviewer-id", required=True)
    parser.add_argument("--reviewed-at", type=datetime.fromisoformat, required=True)
    parser.add_argument("--review-id", required=True)
    parser.add_argument("--notes", required=True)
    args = parser.parse_args()
    result = approve_p09_bundle(
        dataset_root=args.dataset_root,
        expected_bundle_sha256=args.bundle_sha256,
        first_review_path=args.first_review,
        second_review_path=args.second_review,
        reviewer_id=args.reviewer_id,
        reviewed_at=args.reviewed_at,
        review_id=args.review_id,
        notes=args.notes,
    )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
