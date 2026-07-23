from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from evaluation.contracts import (
    ApprovalRecord,
    DatasetSplit,
    FallbackPolicy,
    ReviewableRecord,
    ReviewStatus,
    RunIntent,
)
from evaluation.contracts import (
    TestLock as EvaluationTestLock,
)
from evaluation.datasets import DatasetInventory
from evaluation.guard import (
    TestLeakageGuardError as LeakageGuardError,
)
from evaluation.guard import (
    approved_inventory_sha256,
    split_ids_sha256,
    validate_test_lock,
)
from evaluation.manifest import RunDatasetRef, RunManifest

HASH_A = "a" * 64
HASH_B = "b" * 64
HASH_C = "c" * 64


def _test_manifest(**updates: object) -> RunManifest:
    payload: dict[str, object] = {
        "run_id": "formal-test-run",
        "created_at": datetime(2026, 7, 23, tzinfo=UTC),
        "dataset": RunDatasetRef(
            dataset_id="courserag-eval",
            dataset_version="v1",
            split=DatasetSplit.TEST,
            manifest_sha256=HASH_A,
            split_sha256=HASH_B,
            test_lock_sha256=HASH_C,
        ),
        "intent": RunIntent.EVALUATION,
        "tuning_enabled": False,
        "git_commit": "e3f4efab0770240752efc5f7f30ff4d69daff2a5",
        "git_dirty": False,
        "fallback_policy": FallbackPolicy.FAIL_RUN,
        "random_seed": 7,
    }
    payload.update(updates)
    return RunManifest.model_validate(payload)


def _approved_record() -> ReviewableRecord:
    return ReviewableRecord(
        record_id="approved-1",
        review_status=ReviewStatus.APPROVED,
        candidate_source="human",
        approval=ApprovalRecord(
            review_id="review-1",
            reviewer_id="reviewer-1",
            reviewed_at=datetime(2026, 7, 23, tzinfo=UTC),
            candidate_sha256=HASH_A,
            approved_record_sha256=HASH_B,
        ),
    )


def _inventory() -> DatasetInventory:
    approved = _approved_record()
    return DatasetInventory(
        candidate_records={},
        approved_records={approved.record_id: approved},
        split_ids={
            DatasetSplit.PILOT: set(),
            DatasetSplit.DEV: set(),
            DatasetSplit.TEST: {approved.record_id},
        },
    )


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("tuning_enabled", True, "automatic tuning"),
        ("intent", RunIntent.SMOKE, "evaluation or replay"),
        ("git_dirty", True, "clean Git"),
        ("fallback_policy", FallbackPolicy.ALLOW_RECORDED, "fail-closed"),
    ],
)
def test_test_manifest_is_fail_closed(field, value, message):
    with pytest.raises(ValidationError, match=message):
        _test_manifest(**{field: value})


def test_legacy_chunk_ids_and_llm_judge_cannot_define_gold():
    with pytest.raises(ValidationError, match="cannot define Gold"):
        _test_manifest(configuration={"expected_chunk_ids": ["legacy-output"]})
    with pytest.raises(ValidationError, match="LLM-as-a-Judge"):
        _test_manifest(llm_as_judge=True)


def test_unlocked_test_split_is_rejected():
    manifest = _test_manifest()
    inventory = _inventory()
    lock = EvaluationTestLock(
        dataset_id="courserag-eval",
        dataset_version="v1",
        locked=False,
    )

    with pytest.raises(LeakageGuardError, match="not locked"):
        validate_test_lock(
            manifest,
            lock,
            inventory,
            lock_file_sha256=HASH_C,
        )


def test_locked_test_hashes_and_approved_records_are_required():
    manifest = _test_manifest()
    inventory = _inventory()
    lock = EvaluationTestLock(
        dataset_id="courserag-eval",
        dataset_version="v1",
        locked=True,
        test_ids_sha256=split_ids_sha256(inventory.split_ids[DatasetSplit.TEST]),
        approved_manifest_sha256=approved_inventory_sha256(inventory),
        locked_at=datetime(2026, 7, 23, tzinfo=UTC),
        locked_by="reviewer-1",
    )

    validate_test_lock(
        manifest,
        lock,
        inventory,
        lock_file_sha256=HASH_C,
    )

    changed = lock.model_copy(update={"test_ids_sha256": HASH_A})
    with pytest.raises(LeakageGuardError, match="Test ID hash"):
        validate_test_lock(
            manifest,
            changed,
            inventory,
            lock_file_sha256=HASH_C,
        )
