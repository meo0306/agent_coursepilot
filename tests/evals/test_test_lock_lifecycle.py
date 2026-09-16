from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from evaluation.p09_dev_loader import load_p09_dev_bundle, load_p09_test_bundle

ROOT = Path(__file__).resolve().parents[2]


def test_prelock_fixture_allows_dev_and_rejects_test(prelock_dataset_root: Path) -> None:
    assert len(load_p09_dev_bundle(prelock_dataset_root).cases) == 60
    with pytest.raises(ValueError, match="locked Test set"):
        load_p09_test_bundle(prelock_dataset_root)


def test_consumed_lock_allows_immutable_dev_replay_and_exact_test_read(
    locked_dataset_root: Path,
) -> None:
    assert len(load_p09_dev_bundle(locked_dataset_root).cases) == 60
    assert len(load_p09_test_bundle(locked_dataset_root).cases) == 40


def test_lifecycle_fixtures_never_mutate_consumed_release(
    prelock_dataset_root: Path,
    locked_dataset_root: Path,
    consumed_formal_release: dict[str, str],
) -> None:
    del prelock_dataset_root, locked_dataset_root
    expected = {
        "lock": "06c6473e3beb8bd22b77de1f9d9387d6a5106fa321c29d0113750e0ad7c477ef",
        "component": "1c10e637344a53ce701330df435501f9d300e40985a73bf16445eb0cb095a3a8",
        "retrieval": "313a7e551287c60c4be55638d1d719e835fd682b335c33689eaaaa3c04259edb",
        "qa": "b5b051ef0d4b3747ff5a21a3821bad49b7d50a83db333ae7d6b064bc98c721d0",
    }
    assert consumed_formal_release == expected
    assert (
        hashlib.sha256(
            (ROOT / "datasets/courserag_eval/v1/test.lock.json").read_bytes()
        ).hexdigest()
        == expected["lock"]
    )
