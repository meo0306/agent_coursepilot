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
    # P12 adds recoverable-workflow request/response contracts.  The frozen
    # B0 contract remains a lower bound; additive schemas must not invalidate
    # the legacy interface capture.
    assert snapshot["pydantic_schemas"]["schema_count"] >= 52
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
    # New versioned workflows add prompts without changing the frozen B0
    # prompt files. The B0 count is therefore a lower bound.
    assert snapshot["prompts"]["prompt_count"] >= 14
    assert all(prompt["file_sha256"] for prompt in snapshot["prompts"]["prompts"])
    assert all(prompt["effective_prompt_sha256"] for prompt in snapshot["prompts"]["prompts"])
    assert snapshot["behavior_changed"] is False


def test_saved_interface_snapshot_matches_runtime_capture():
    snapshot_path = (
        Path.cwd() / "docs" / "refactor" / "baselines" / "b0" / "07_interface_snapshot.json"
    )
    saved = json.loads(snapshot_path.read_text(encoding="utf-8"))

    current = capture_interface_snapshot(Path.cwd(), baseline_commit=saved["baseline_commit"])
    saved_routes = {
        (item["path"], tuple(item["methods"]), item["name"]): item
        for item in saved["public_api"]["routes"]
    }
    current_routes = {
        (item["path"], tuple(item["methods"]), item["name"]): item
        for item in current["public_api"]["routes"]
    }

    assert all(current_routes.get(key) == value for key, value in saved_routes.items())
    assert (
        current["public_api"]["coursepilot_route_count"]
        >= saved["public_api"]["coursepilot_route_count"]
    )
    current["public_api"] = saved["public_api"]
    # P12's recoverable task/interrupt endpoints add schemas without changing
    # any existing model.  Compare the frozen B0 schema projection only.
    saved_schema_names = {
        (item["module"], item["name"]) for item in saved["pydantic_schemas"]["schemas"]
    }
    current["pydantic_schemas"]["schemas"] = [
        item
        for item in current["pydantic_schemas"]["schemas"]
        if (item["module"], item["name"]) in saved_schema_names
    ]
    current["pydantic_schemas"]["schema_count"] = len(current["pydantic_schemas"]["schemas"])
    # P11 adds versioned runtime fact tables and nullable task columns without
    # changing the frozen B0 public contract. Compare the original B0 ORM
    # projection while separate P11 migration tests cover the additive facts.
    saved_table_names = {item["name"] for item in saved["orm"]["tables"]}
    current["orm"]["tables"] = [
        item for item in current["orm"]["tables"] if item["name"] in saved_table_names
    ]
    current["orm"]["table_count"] = len(current["orm"]["tables"])
    for saved_table in saved["orm"]["tables"]:
        if saved_table["name"] != "coursepilot_generation_tasks":
            continue
        saved_columns = {item["name"] for item in saved_table["columns"]}
        current_task = next(
            item
            for item in current["orm"]["tables"]
            if item["name"] == "coursepilot_generation_tasks"
        )
        current_task["columns"] = [
            item for item in current_task["columns"] if item["name"] in saved_columns
        ]
        current_task["constraints"] = saved_table["constraints"]
    saved_prompt_names = {item["name"] for item in saved["prompts"]["prompts"]}
    current["prompts"]["prompts"] = [
        item for item in current["prompts"]["prompts"] if item["name"] in saved_prompt_names
    ]
    current["prompts"]["prompt_count"] = len(current["prompts"]["prompts"])
    assert current == saved


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
