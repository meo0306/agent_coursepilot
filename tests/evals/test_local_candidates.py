import json
import os
from pathlib import Path

import pytest

from coursepilot.evals.b0_baseline import SampleInput
from coursepilot.rag.types import ParsedDocument, ParsedSection
from evaluation.local_candidates import (
    _evidence_candidates,
    _validate_output_path,
    generate_local_candidates,
)

HASH = "a" * 64


def test_local_candidate_contains_source_text_but_summary_does_not(tmp_path):
    sample = SampleInput(
        path=tmp_path / "source.docx",
        repository_relative_path="data/sample_files/source.docx",
        media_type=("application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
        size_bytes=100,
        sha256=HASH,
    )
    source_text = "This exact private source sentence remains local. " * 4
    records = _evidence_candidates(
        sample,
        ParsedDocument(
            source_path=str(sample.path),
            sections=[ParsedSection(content=source_text)],
        ),
        document_id="local-document",
        document_version="v1",
        limit=2,
    )

    assert records
    assert records[0].gold_text in source_text
    assert records[0].review_status == "candidate"
    assert records[0].approval is None


def test_source_derived_outputs_cannot_enter_tracked_repository_paths(tmp_path):
    repository_root = tmp_path / "repository"
    repository_root.mkdir()

    with pytest.raises(ValueError, match="storage_eval"):
        _validate_output_path(repository_root / "datasets" / "leak", repository_root)
    assert _validate_output_path(
        repository_root / "storage_eval" / "p02",
        repository_root,
    ).is_relative_to(repository_root / "storage_eval")


@pytest.mark.skipif(
    os.getenv("COURSEPILOT_RUN_P02_LOCAL_CANDIDATES") != "1",
    reason="set COURSEPILOT_RUN_P02_LOCAL_CANDIDATES=1 to parse local sample files",
)
def test_owner_samples_generate_local_candidates_without_gold(tmp_path):
    repository_root = Path.cwd().resolve()
    output_dir = tmp_path / "local-candidates"
    summary = generate_local_candidates(
        repository_root=repository_root,
        sample_dir=repository_root / "data" / "sample_files",
        output_dir=output_dir,
        max_per_document=2,
    )

    assert len(summary.artifacts) == 2
    assert all(item.evidence_candidate_count > 0 for item in summary.artifacts)
    summary_text = summary.model_dump_json()
    ds2_text = (output_dir / "ds2_candidates.json").read_text(encoding="utf-8")
    assert '"review_status":"approved"' not in ds2_text.replace(" ", "")
    payload = json.loads(ds2_text)
    assert payload["evidence"]
    assert all(item["gold_text"] not in summary_text for item in payload["evidence"])
