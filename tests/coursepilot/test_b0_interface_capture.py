import json
import zipfile
from pathlib import Path

from coursepilot.evals.capture_b0_interfaces import (
    capture_interface_snapshot,
    capture_license_attribution,
    generate_safe_export_samples,
)


def test_interface_snapshot_captures_api_models_graphs_and_prompts():
    snapshot = capture_interface_snapshot(Path.cwd(), baseline_commit="test-baseline")

    assert snapshot["public_api"]["route_count"] > 0
    assert (
        snapshot["public_api"]["route_count"] >= snapshot["public_api"]["coursepilot_route_count"]
    )
    assert snapshot["orm"]["table_count"] >= 11
    assert snapshot["pydantic_schemas"]["schema_count"] == 52
    root_schemas = {
        item["name"]
        for item in snapshot["pydantic_schemas"]["schemas"]
        if item["module"] == "schema.schema"
    }
    assert root_schemas == {
        "AgentInfo",
        "ServiceMetadata",
        "UserInput",
        "StreamInput",
        "ChatMessage",
        "ChatHistoryInput",
        "ChatHistory",
    }
    assert {graph["name"] for graph in snapshot["graphs"]} == {
        "coursepilot_lesson_agent",
        "coursepilot_exam_agent",
        "coursepilot_ppt_agent",
    }
    assert snapshot["prompts"]["prompt_count"] == 14
    assert all(prompt["file_sha256"] for prompt in snapshot["prompts"]["prompts"])
    assert all(prompt["effective_prompt_sha256"] for prompt in snapshot["prompts"]["prompts"])
    assert snapshot["behavior_changed"] is False


def test_saved_interface_snapshot_matches_runtime_capture():
    snapshot_path = (
        Path.cwd() / "docs" / "refactor" / "baselines" / "b0" / "07_interface_snapshot.json"
    )
    saved = json.loads(snapshot_path.read_text(encoding="utf-8"))

    assert capture_interface_snapshot(Path.cwd(), baseline_commit=saved["baseline_commit"]) == saved


def test_safe_export_samples_are_valid_openxml_and_do_not_use_owner_text(tmp_path):
    manifest = generate_safe_export_samples(tmp_path)

    assert manifest["contains_owner_sample_text"] is False
    assert len(manifest["files"]) == 6
    for item in manifest["files"]:
        path = tmp_path / item["path"]
        assert path.exists()
        assert zipfile.is_zipfile(path)
        assert item["sha256"]


def test_license_snapshot_preserves_upstream_attribution():
    snapshot = capture_license_attribution(Path.cwd())

    assert snapshot["license"]["spdx"] == "MIT"
    assert snapshot["license"]["copyright_notice"] == "Copyright (c) 2024 Joshua Carroll"
    assert snapshot["upstream_attribution_preserved"] is True
    assert snapshot["p00_author_metadata_changed"] is False
