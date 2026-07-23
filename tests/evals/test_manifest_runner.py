import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from evaluation.contracts import (
    DatasetSplit,
    FallbackPolicy,
    RunIntent,
)
from evaluation.guard import DatasetIntegrityError
from evaluation.manifest import RunDatasetRef, RunManifest, sha256_file
from evaluation.runner import EvaluationRunner, RunConfigurationMismatch

HASH_A = "a" * 64
HASH_B = "b" * 64


def _dataset_root(tmp_path: Path) -> Path:
    root = tmp_path / "datasets" / "courserag_eval" / "v1"
    (root / "splits").mkdir(parents=True, exist_ok=True)
    (root / "manifest.json").write_text(
        json.dumps(
            {
                "schema_version": "courserag.dataset-manifest.v1",
                "dataset_id": "courserag-eval",
                "dataset_version": "v1",
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    (root / "splits" / "pilot_ids.txt").write_text("case-1\n", encoding="utf-8")
    return root


def _manifest(
    dataset_root: Path,
    *,
    seed: int = 7,
    run_id: str = "run-1",
) -> RunManifest:
    return RunManifest(
        run_id=run_id,
        created_at=datetime(2026, 7, 23, tzinfo=UTC),
        dataset=RunDatasetRef(
            dataset_id="courserag-eval",
            dataset_version="v1",
            split=DatasetSplit.PILOT,
            manifest_sha256=sha256_file(dataset_root / "manifest.json"),
            split_sha256=sha256_file(dataset_root / "splits" / "pilot_ids.txt"),
        ),
        intent=RunIntent.SMOKE,
        tuning_enabled=False,
        git_commit="e3f4efab0770240752efc5f7f30ff4d69daff2a5",
        git_dirty=False,
        component_versions={"adapter": "b0-v1"},
        configuration={"top_k": 5, "overlap_threshold": 0.8},
        fallback_policy=FallbackPolicy.NOT_APPLICABLE,
        random_seed=seed,
    )


def _runner(
    tmp_path: Path,
    manifest: RunManifest,
    dataset_root: Path,
    *,
    resume: bool = False,
):
    return EvaluationRunner(
        manifest=manifest,
        checkpoint_path=tmp_path / "checkpoint.json",
        partial_report_path=tmp_path / "partial.json",
        final_report_path=tmp_path / "report.json",
        dataset_root=dataset_root,
        resume=resume,
    )


def test_manifest_identity_is_canonical_and_rejects_only_secret_values(tmp_path):
    dataset_root = _dataset_root(tmp_path)
    first = _manifest(dataset_root)
    second = _manifest(dataset_root, run_id="different-run-id")

    assert first.identity_sha256 == second.identity_sha256
    safe_payload = first.model_dump(mode="json")
    safe_payload["configuration"] = {
        "qa": {"max_answer_tokens": 600},
        "tokenizer": {"token_budget": 4096},
    }
    assert RunManifest.model_validate(safe_payload).configuration == safe_payload["configuration"]

    payload = first.model_dump(mode="json")
    payload["configuration"] = {"api_key": "not-allowed"}
    with pytest.raises(ValidationError, match="secret-like key"):
        RunManifest.model_validate(payload)


def test_runner_persists_partial_and_final_report(tmp_path):
    dataset_root = _dataset_root(tmp_path)
    manifest = _manifest(dataset_root)
    runner = _runner(tmp_path, manifest, dataset_root)
    result = runner.run_case("case-1", HASH_A, lambda: {"score": 1.0})
    runner.complete({"metric": 1.0})

    assert result == {"score": 1.0}
    checkpoint = json.loads((tmp_path / "checkpoint.json").read_text(encoding="utf-8"))
    report = json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))
    assert checkpoint["status"] == "completed"
    assert report["run_identity_sha256"] == manifest.identity_sha256
    assert report["cases"]["case-1"]["status"] == "succeeded"
    assert not list(tmp_path.glob("*.tmp"))


def test_resume_skips_success_and_retries_failed_case(tmp_path):
    dataset_root = _dataset_root(tmp_path)
    manifest = _manifest(dataset_root)
    runner = _runner(tmp_path, manifest, dataset_root)
    runner.run_case("success", HASH_A, lambda: {"cached": True})
    with pytest.raises(RuntimeError, match="temporary"):
        runner.run_case("failed", HASH_B, lambda: (_ for _ in ()).throw(RuntimeError("temporary")))

    resumed = _runner(tmp_path, manifest, dataset_root, resume=True)
    cached = resumed.run_case(
        "success",
        HASH_A,
        lambda: (_ for _ in ()).throw(AssertionError("successful case reran")),
    )
    recovered = resumed.run_case("failed", HASH_B, lambda: {"recovered": True})

    assert cached == {"cached": True}
    assert recovered == {"recovered": True}
    assert resumed.state.cases["failed"].attempt == 2


def test_resume_rejects_configuration_before_mutating_files(tmp_path):
    dataset_root = _dataset_root(tmp_path)
    _runner(tmp_path, _manifest(dataset_root), dataset_root)
    checkpoint = tmp_path / "checkpoint.json"
    partial = tmp_path / "partial.json"
    before = (checkpoint.read_bytes(), partial.read_bytes())

    with pytest.raises(RunConfigurationMismatch, match="identity differs"):
        _runner(tmp_path, _manifest(dataset_root, seed=8), dataset_root, resume=True)

    assert (checkpoint.read_bytes(), partial.read_bytes()) == before


def test_case_hash_change_and_dataset_output_path_are_rejected(tmp_path):
    dataset_root = _dataset_root(tmp_path)
    manifest = _manifest(dataset_root)
    runner = _runner(tmp_path, manifest, dataset_root)
    runner.run_case("case-1", HASH_A, lambda: {"ok": True})
    resumed = _runner(tmp_path, manifest, dataset_root, resume=True)
    with pytest.raises(RunConfigurationMismatch, match="case hash changed"):
        resumed.run_case("case-1", HASH_B, lambda: {"ok": False})

    runtime_output = tmp_path / "datasets" / "runtime"
    with pytest.raises(ValueError, match="inside datasets"):
        EvaluationRunner(
            manifest=manifest,
            checkpoint_path=runtime_output / "checkpoint.json",
            partial_report_path=tmp_path / "partial-2.json",
            final_report_path=tmp_path / "report-2.json",
            dataset_root=dataset_root,
        )


@pytest.mark.parametrize(
    ("relative_path", "message"),
    [
        ("manifest.json", "Manifest hash"),
        ("splits/pilot_ids.txt", "split hash"),
    ],
)
def test_runner_rejects_dataset_file_hash_drift_before_writing(
    tmp_path,
    relative_path,
    message,
):
    dataset_root = _dataset_root(tmp_path)
    manifest = _manifest(dataset_root)
    changed = dataset_root / relative_path
    changed.write_text(changed.read_text(encoding="utf-8") + "tampered\n", encoding="utf-8")

    with pytest.raises(DatasetIntegrityError, match=message):
        _runner(tmp_path, manifest, dataset_root)

    assert not (tmp_path / "checkpoint.json").exists()
    assert not (tmp_path / "partial.json").exists()


def test_runner_rejects_dataset_identity_even_when_declared_hash_matches(tmp_path):
    dataset_root = _dataset_root(tmp_path)
    manifest = _manifest(dataset_root)
    dataset_manifest_path = dataset_root / "manifest.json"
    payload = json.loads(dataset_manifest_path.read_text(encoding="utf-8"))
    payload["dataset_id"] = "different-evaluation-dataset"
    dataset_manifest_path.write_text(
        json.dumps(payload, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    manifest = manifest.model_copy(
        update={
            "dataset": manifest.dataset.model_copy(
                update={"manifest_sha256": sha256_file(dataset_manifest_path)}
            )
        }
    )

    with pytest.raises(DatasetIntegrityError, match="identity differs"):
        _runner(tmp_path, manifest, dataset_root)


def test_runner_does_not_persist_raw_exception_messages(tmp_path):
    dataset_root = _dataset_root(tmp_path)
    runner = _runner(tmp_path, _manifest(dataset_root), dataset_root)
    sensitive_marker = "AUDIT_SENSITIVE_MARKER"

    with pytest.raises(RuntimeError, match=sensitive_marker):
        runner.run_case(
            "case-1",
            HASH_A,
            lambda: (_ for _ in ()).throw(RuntimeError(sensitive_marker)),
        )

    checkpoint = json.loads((tmp_path / "checkpoint.json").read_text(encoding="utf-8"))
    persisted = checkpoint["cases"]["case-1"]["error_message"]
    assert sensitive_marker not in persisted
    assert persisted == (
        "case execution failed; details are omitted from persisted evaluation artifacts"
    )
