import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from coursepilot.evals.b0_baseline import (
    B0InputError,
    build_sample_manifest,
    discover_sample_inputs,
    write_json_atomic,
)


def test_sample_manifest_records_hashes_without_source_content(tmp_path):
    sample_dir = tmp_path / "data" / "sample_files"
    sample_dir.mkdir(parents=True)
    (sample_dir / "first.docx").write_bytes(b"docx-placeholder")
    (sample_dir / "second.pdf").write_bytes(b"pdf-placeholder")

    inputs = discover_sample_inputs(sample_dir, tmp_path)
    manifest = build_sample_manifest(
        inputs,
        baseline_commit="abc123",
        captured_at="2026-07-23T00:00:00+00:00",
    )

    assert [item["media_type"] for item in manifest["inputs"]] == [
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/pdf",
    ]
    assert manifest["declared_relationship"] == "independent_documents_with_different_content"
    assert manifest["source_text_included"] is False
    assert all(
        item["redistribution_status"] == "local_only_unverified" for item in manifest["inputs"]
    )
    assert "docx-placeholder" not in json.dumps(manifest)


@pytest.mark.parametrize(
    ("docx_count", "pdf_count"),
    [(0, 1), (1, 0), (2, 1), (1, 2)],
)
def test_sample_discovery_requires_exactly_one_file_per_format(tmp_path, docx_count, pdf_count):
    sample_dir = tmp_path / "data" / "sample_files"
    sample_dir.mkdir(parents=True)
    for index in range(docx_count):
        (sample_dir / f"{index}.docx").write_bytes(b"x")
    for index in range(pdf_count):
        (sample_dir / f"{index}.pdf").write_bytes(b"x")

    with pytest.raises(B0InputError, match="exactly one DOCX and one PDF"):
        discover_sample_inputs(sample_dir, tmp_path)


def test_sample_discovery_rejects_external_directory(tmp_path):
    repository_root = tmp_path / "repository"
    repository_root.mkdir()
    external = tmp_path / "external"
    external.mkdir()
    (external / "one.docx").write_bytes(b"x")
    (external / "two.pdf").write_bytes(b"x")

    with pytest.raises(B0InputError, match="inside the repository"):
        discover_sample_inputs(external, repository_root)


def test_atomic_json_writer_leaves_no_temporary_file(tmp_path):
    output = tmp_path / "report.json"

    write_json_atomic(output, {"safe": True})

    assert json.loads(output.read_text(encoding="utf-8")) == {"safe": True}
    assert not output.with_suffix(".json.tmp").exists()


def test_deterministic_eval_manifest_command_reproduces_saved_report():
    repository_root = Path.cwd()
    baseline_dir = repository_root / "docs" / "refactor" / "baselines" / "b0"
    manifest = json.loads(
        (baseline_dir / "04_deterministic_eval_manifest.json").read_text(encoding="utf-8")
    )
    saved_report = json.loads(
        (baseline_dir / "04_deterministic_eval_report.json").read_text(encoding="utf-8")
    )

    assert manifest["command"] == (
        "$env:PYTHONPATH='src'; uv run python -m coursepilot.evals.run_sample_eval "
        "--sample-dir data/coursepilot_sample "
        "--output docs/refactor/baselines/b0/04_deterministic_eval_report.json"
    )

    environment = {**os.environ, "PYTHONPATH": str(repository_root / "src")}
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "coursepilot.evals.run_sample_eval",
            "--sample-dir",
            "data/coursepilot_sample",
        ],
        cwd=repository_root,
        env=environment,
        check=True,
        capture_output=True,
        text=True,
    )

    assert json.loads(completed.stdout) == saved_report
