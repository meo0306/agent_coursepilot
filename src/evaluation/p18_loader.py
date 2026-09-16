"""P18 split-aware loaders.

Dev loading deliberately never materialises Test or blind case bodies.  Test
loading is available only after the repository Test lock is valid for the
exact approved inventory.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel

from evaluation.contracts import DatasetSplit, TestLock
from evaluation.datasets import COURSEPILOT_SPECS, load_dataset_inventory
from evaluation.guard import approved_inventory_sha256, split_ids_sha256
from evaluation.p18_schemas import (
    P18ExamDataset,
    P18FaultDataset,
    P18JourneyDataset,
    P18LessonDataset,
    P18PPTDataset,
    P18RecoveryDataset,
    P18RepairDataset,
    P18TemplateDataset,
    P18ValidationDataset,
)


class P18DatasetBoundaryError(ValueError):
    """Raised before a P18 run crosses its approved split boundary."""


_MODELS: dict[str, type[BaseModel]] = {
    "cp_ds1": P18LessonDataset,
    "cp_ds2": P18ExamDataset,
    "cp_ds3": P18PPTDataset,
    "cp_ds4": P18ValidationDataset,
    "cp_ds5": P18RepairDataset,
    "cp_ds6": P18RecoveryDataset,
    "cp_ds7": P18TemplateDataset,
    "cp_ds8": P18FaultDataset,
    "sys_ds1": P18JourneyDataset,
}


@dataclass(frozen=True)
class P18LoadedSplit:
    split: DatasetSplit
    components: dict[str, tuple[BaseModel, ...]]

    @property
    def record_count(self) -> int:
        return sum(len(items) for items in self.components.values())


def load_p18_dev(dataset_root: Path) -> P18LoadedSplit:
    """Load only Dev-visible records; Test and blind bodies never escape."""

    components: dict[str, tuple[BaseModel, ...]] = {}
    for component, model in _MODELS.items():
        envelope = _load_approved(dataset_root, component, model)
        components[component] = _select_split(envelope, DatasetSplit.DEV)
    if components["sys_ds1"]:
        raise P18DatasetBoundaryError("P18 Dev must not materialise SYS-DS1 Test journeys")
    return P18LoadedSplit(split=DatasetSplit.DEV, components=components)


def load_p18_test(dataset_root: Path) -> P18LoadedSplit:
    """Load Test/blind records after validating the exact global Test lock."""

    lock_path = dataset_root / "test.lock.json"
    lock = TestLock.model_validate_json(lock_path.read_text(encoding="utf-8"))
    inventory = load_dataset_inventory(dataset_root, COURSEPILOT_SPECS)
    test_ids = inventory.split_ids[DatasetSplit.TEST]
    if not lock.locked:
        raise P18DatasetBoundaryError("P18 Test is not locked")
    if lock.test_ids_sha256 != split_ids_sha256(test_ids):
        raise P18DatasetBoundaryError("P18 Test ID hash differs from the lock")
    if lock.approved_manifest_sha256 != approved_inventory_sha256(inventory):
        raise P18DatasetBoundaryError("P18 approved inventory differs from the lock")

    components: dict[str, tuple[BaseModel, ...]] = {}
    for component, model in _MODELS.items():
        envelope = _load_approved(dataset_root, component, model)
        components[component] = _select_split(envelope, DatasetSplit.TEST)
    return P18LoadedSplit(split=DatasetSplit.TEST, components=components)


def _select_split(envelope: BaseModel, split: DatasetSplit) -> tuple[BaseModel, ...]:
    """Select the formal records for one split across the three envelope shapes.

    CP-DS4/5 deliberately combine approved P13 Dev carry-forwards with new
    formal records.  The other datasets use a regular ``cases`` collection.
    Keeping that distinction here prevents the runner from silently reporting
    the wrong Dev denominator.
    """

    allowed = (
        {"dev", "dev_contract"}
        if split == DatasetSplit.DEV
        else {"test", "blind", "heldout_custom"}
    )
    selected: list[BaseModel] = []
    if split == DatasetSplit.DEV:
        selected.extend(getattr(envelope, "carried_dev_records", ()))
    candidates = getattr(envelope, "new_cases", getattr(envelope, "cases", ()))
    selected.extend(
        case
        for case in candidates
        if getattr(case, "split", getattr(case, "split_role", None)) in allowed
    )
    return tuple(selected)


def _load_approved(dataset_root: Path, component: str, model: type[BaseModel]) -> BaseModel:
    path = dataset_root / "approved" / component / "p18_formal.json"
    if not path.is_file():
        raise P18DatasetBoundaryError(f"missing approved P18 component: {component}")
    return model.model_validate(json.loads(path.read_text(encoding="utf-8")))
