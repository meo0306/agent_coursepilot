"""Fail-closed loader for Approved P09 Dev QA/Context evaluation input."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from courserag.evals.schemas import (
    DS5RetrievalQADataset,
    P09ContextGoldCase,
    P09ContextGoldDataset,
    P09QAGoldCase,
    P09QAGoldDataset,
    RetrievalQACase,
)
from evaluation.contracts import TestLock
from evaluation.guard import split_ids_sha256


@dataclass(frozen=True)
class P09DevCase:
    retrieval: RetrievalQACase
    qa: P09QAGoldCase
    context: P09ContextGoldCase


@dataclass(frozen=True)
class P09DevBundle:
    cases: tuple[P09DevCase, ...]
    retrieval_main_count: int
    upstream_gap_diagnostic_count: int


def load_p09_dev_bundle(dataset_root: Path) -> P09DevBundle:
    dataset_root = dataset_root.resolve()
    governance = json.loads((dataset_root / "manifest.json").read_text(encoding="utf-8"))
    components = governance.get("gold_components", {})
    if components.get("ds5_retrieval") != "approved":
        raise ValueError("P09 Dev loader requires Approved DS5 Retrieval Gold")
    if components.get("ds5_qa") != "approved" or components.get("ds5_context") != "approved":
        raise ValueError("P09 Dev loader requires Approved QA and Context Gold")
    p09_status = governance.get("phase_input_status", {}).get("p09")
    if p09_status not in {"formal_dev_eval_ready", "completed_gate_passed"}:
        raise ValueError(
            "P09 Dev loader requires formal_dev_eval_ready or completed_gate_passed governance"
        )
    # A consumed Test lock must not make immutable Dev evidence unreadable. This loader
    # resolves only the frozen Dev ID file and still rejects every non-Dev overlay below.
    TestLock.model_validate_json((dataset_root / "test.lock.json").read_text(encoding="utf-8"))
    retrieval = DS5RetrievalQADataset.model_validate_json(
        (dataset_root / "approved/ds5/p08_retrieval.json").read_text(encoding="utf-8")
    )
    qa = P09QAGoldDataset.model_validate_json(
        (dataset_root / "approved/ds5/p09_qa.json").read_text(encoding="utf-8")
    )
    context = P09ContextGoldDataset.model_validate_json(
        (dataset_root / "approved/ds5/p09_context.json").read_text(encoding="utf-8")
    )
    qa_by_retrieval = {item.retrieval_case_id: item for item in qa.cases}
    context_by_retrieval = {item.retrieval_case_id: item for item in context.cases}
    if set(qa_by_retrieval) != {item.record_id for item in retrieval.cases}:
        raise ValueError("P09 QA overlay must bind every Approved P08 Query exactly once")
    if set(context_by_retrieval) != set(qa_by_retrieval):
        raise ValueError("P09 Context overlay must bind the same P08 Query set as QA")
    dev_ids = set((dataset_root / "splits/dev_ids.txt").read_text(encoding="utf-8").split())
    expected_dev = {item.record_id for item in retrieval.cases if item.split == "dev"}
    if dev_ids != expected_dev or len(dev_ids) != 60:
        raise ValueError("P09 Dev IDs must remain the frozen P08 60-case split")
    cases: list[P09DevCase] = []
    for item in retrieval.cases:
        if item.record_id not in dev_ids:
            continue
        qa_item = qa_by_retrieval[item.record_id]
        context_item = context_by_retrieval[item.record_id]
        if qa_item.split != "dev" or context_item.split != "dev":
            raise ValueError("P09 Dev loader detected a Test overlay in Dev IDs")
        if qa_item.qa_gold_status != "approved" or context_item.context_gold_status != "approved":
            raise ValueError("P09 Dev loader accepts Approved overlays only")
        cases.append(P09DevCase(retrieval=item, qa=qa_item, context=context_item))
    main_count = sum(item.qa.evaluation_stratum == "retrieval_main" for item in cases)
    diagnostic_count = sum(
        item.qa.evaluation_stratum == "upstream_gap_diagnostic" for item in cases
    )
    if len(cases) != 60 or main_count != 54 or diagnostic_count != 6:
        raise ValueError("P09 Dev loader requires exact 60/54/6 P08 strata")
    return P09DevBundle(
        cases=tuple(cases),
        retrieval_main_count=main_count,
        upstream_gap_diagnostic_count=diagnostic_count,
    )


def load_p09_test_bundle(
    dataset_root: Path,
) -> P09DevBundle:
    """Resolve the Approved Test overlay only after an exact frozen-manifest lock."""

    dataset_root = dataset_root.resolve()
    governance = json.loads((dataset_root / "manifest.json").read_text(encoding="utf-8"))
    components = governance.get("gold_components", {})
    if (
        components.get("ds5_retrieval") != "approved"
        or components.get("ds5_qa") != "approved"
        or components.get("ds5_context") != "approved"
    ):
        raise ValueError("P10 Test loader requires every DS5 component to be Approved")
    lock = TestLock.model_validate_json(
        (dataset_root / "test.lock.json").read_text(encoding="utf-8")
    )
    test_ids_path = dataset_root / "splits/test_ids.txt"
    if not lock.locked:
        raise ValueError("P10 Test loader requires an explicit locked Test set")
    test_ids = set(test_ids_path.read_text(encoding="utf-8").split())
    if lock.test_ids_sha256 != split_ids_sha256(test_ids):
        raise ValueError("P10 Test ID identity differs from the Test lock")

    retrieval = DS5RetrievalQADataset.model_validate_json(
        (dataset_root / "approved/ds5/p08_retrieval.json").read_text(encoding="utf-8")
    )
    qa = P09QAGoldDataset.model_validate_json(
        (dataset_root / "approved/ds5/p09_qa.json").read_text(encoding="utf-8")
    )
    context = P09ContextGoldDataset.model_validate_json(
        (dataset_root / "approved/ds5/p09_context.json").read_text(encoding="utf-8")
    )
    qa_by_retrieval = {item.retrieval_case_id: item for item in qa.cases}
    context_by_retrieval = {item.retrieval_case_id: item for item in context.cases}
    expected_test = {item.record_id for item in retrieval.cases if item.split == "test"}
    if test_ids != expected_test or len(test_ids) != 40:
        raise ValueError("P10 Test IDs must remain the frozen 40-case split")

    cases: list[P09DevCase] = []
    for item in retrieval.cases:
        if item.record_id not in test_ids:
            continue
        qa_item = qa_by_retrieval.get(item.record_id)
        context_item = context_by_retrieval.get(item.record_id)
        if qa_item is None or context_item is None:
            raise ValueError("P10 Test overlay does not bind every Test retrieval case")
        if qa_item.split != "test" or context_item.split != "test":
            raise ValueError("P10 Test loader detected a non-Test overlay")
        if qa_item.qa_gold_status != "approved" or context_item.context_gold_status != "approved":
            raise ValueError("P10 Test loader accepts Approved overlays only")
        cases.append(P09DevCase(retrieval=item, qa=qa_item, context=context_item))
    main_count = sum(item.qa.evaluation_stratum == "retrieval_main" for item in cases)
    diagnostic_count = sum(
        item.qa.evaluation_stratum == "upstream_gap_diagnostic" for item in cases
    )
    if len(cases) != 40 or main_count != 36 or diagnostic_count != 4:
        raise ValueError("P10 Test loader requires exact 40/36/4 strata")
    return P09DevBundle(
        cases=tuple(cases),
        retrieval_main_count=main_count,
        upstream_gap_diagnostic_count=diagnostic_count,
    )
