from datetime import UTC, datetime
from pathlib import Path

import pytest

from courserag.evals.schemas import DS1ParsingDataset, OCRGold, P05OCRCandidateManifest
from evaluation.contracts import CandidateRevisionHistory
from evaluation.corpus_fixtures import sha256_file
from evaluation.datasets import record_digest
from evaluation.p05_ocr_approval import approve_p05_ocr_candidate
from evaluation.p05_ocr_data import build_p05_ocr_candidate


def test_p05_candidate_is_source_grounded_hash_bound_and_reproducible(tmp_path: Path) -> None:
    repository_root = Path(__file__).resolve().parents[2]
    dataset_root = repository_root / "datasets/courserag_eval/v1"
    first_root = tmp_path / "first"
    second_root = tmp_path / "second"

    first = build_p05_ocr_candidate(
        repository_root=repository_root,
        dataset_root=dataset_root,
        output_root=first_root,
    )
    second = build_p05_ocr_candidate(
        repository_root=repository_root,
        dataset_root=dataset_root,
        output_root=second_root,
    )
    candidate_path = first_root / "candidates/ds1/p05_ocr_r3.json"
    candidate = DS1ParsingDataset.model_validate_json(candidate_path.read_text(encoding="utf-8"))
    manifest = P05OCRCandidateManifest.model_validate_json(
        (first_root / "provenance/p05_ocr_candidate_manifest.json").read_text(encoding="utf-8")
    )
    records = [record for record in candidate.records if isinstance(record, OCRGold)]

    assert first["candidate_file_sha256"] == second["candidate_file_sha256"]
    assert first["review_pack_index_sha256"] == second["review_pack_index_sha256"]
    assert len(records) == 15
    assert all(record.review_status.value == "candidate" for record in records)
    assert {record.candidate_source for record in records} == {
        "native_pdf_geometry_plus_owner_policy",
        "p04_page_gold_plus_owner_policy",
    }
    assert all(record.bbox_coordinate_space == "image_pixels_top_left" for record in records)
    assert all(record.annotation_policy == "p05_body_projection_v2" for record in records)
    assert all(record.regions for record in records)
    assert all(record.reading_order for record in records)
    assert manifest.candidate_file_sha256 == sha256_file(candidate_path)
    assert len(manifest.inherited_page_gold_record_sha256) == 11
    assert set(manifest.newly_annotated_record_ids) == {
        "ds1-ocr-11",
        "ds1-ocr-12",
        "ds1-ocr-13",
        "ds1-ocr-14",
    }
    assert (
        len(list((first_root / "candidates/work_packages/p05_ocr_review_r3").glob("*.png"))) == 15
    )

    by_id = {record.record_id: record for record in records}
    for record in records:
        body_ids = {region.region_id for region in record.regions if region.include_in_body_text}
        assert set(record.reading_order) == body_ids
        assert all(
            not region.include_in_body_text
            for region in record.regions
            if region.role
            in {
                "header",
                "footer",
                "page_number",
                "qr_related",
                "figure",
                "figure_caption",
                "figure_embedded_text",
            }
        )
    for record_id in ("ds1-ocr-01", "ds1-ocr-15"):
        assert any(region.role == "qr_related" for region in by_id[record_id].regions)
    assert any(region.role == "figure_embedded_text" for region in by_id["ds1-ocr-07"].regions)
    assert {region.role for region in by_id["ds1-ocr-12"].regions} >= {
        "figure",
        "figure_caption",
        "header",
        "page_number",
    }
    assert "图1-11　智能翻译机实时翻译示例" not in by_id["ds1-ocr-12"].gold_text

    expected_split_caption_names = {
        "ds1-ocr-02": {"AI合成主播"},
        "ds1-ocr-05": {"Kiva机器人"},
        "ds1-ocr-06": {"科幻电影中的机器人"},
        "ds1-ocr-07": {"图灵测试的示意图", "某次图灵测试中的对话内容"},
        "ds1-ocr-08": {"计算机“深蓝”战胜国际象棋世界冠军卡斯帕罗夫"},
        "ds1-ocr-09": {"作文批阅系统示例"},
        "ds1-ocr-10": {"机器人擦玻璃", "腾讯养老机器人", "2025年春晚机器人表演"},
    }
    for record_id, expected_names in expected_split_caption_names.items():
        caption_names = {
            region.gold_text
            for region in by_id[record_id].regions
            if region.role == "figure_caption" and region.gold_text is not None
        }
        assert expected_names <= caption_names
        assert all(
            not region.include_in_body_text
            for region in by_id[record_id].regions
            if region.gold_text in expected_names
        )

    r2 = DS1ParsingDataset.model_validate_json(
        (dataset_root / "candidates/ds1/p05_ocr_r2.json").read_text(encoding="utf-8")
    )
    r2_hashes = {record.record_id: record_digest(record) for record in r2.records}
    r3_hashes = {record.record_id: record_digest(record) for record in candidate.records}
    assert {
        record_id for record_id in r2_hashes if r2_hashes[record_id] != r3_hashes[record_id]
    } == set(expected_split_caption_names)

    with pytest.raises(ValueError, match="explicit course_owner approval"):
        approve_p05_ocr_candidate(
            dataset_root=first_root,
            expected_candidate_file_sha256="0" * 64,
            reviewer_id="course_owner",
            reviewed_at=datetime(2026, 8, 2, tzinfo=UTC),
            review_id="review-p05-test",
            notes="test only",
        )
    assert not (first_root / "approved/ds1/p05_ocr.json").exists()


def test_p05_r3_approval_preserves_superseded_revisions_in_temporary_dataset(
    tmp_path: Path,
) -> None:
    repository_root = Path(__file__).resolve().parents[2]
    dataset_root = repository_root / "datasets/courserag_eval/v1"
    output_root = tmp_path / "dataset"
    built = build_p05_ocr_candidate(
        repository_root=repository_root,
        dataset_root=dataset_root,
        output_root=output_root,
    )

    approved = approve_p05_ocr_candidate(
        dataset_root=output_root,
        expected_candidate_file_sha256=str(built["candidate_file_sha256"]),
        reviewer_id="course_owner_test_double",
        reviewed_at=datetime(2026, 8, 2, tzinfo=UTC),
        review_id="review-p05-r3-contract-test",
        notes="Contract test only; no repository Gold approval is created.",
    )
    replayed = approve_p05_ocr_candidate(
        dataset_root=output_root,
        expected_candidate_file_sha256=str(built["candidate_file_sha256"]),
        reviewer_id="course_owner_test_double",
        reviewed_at=datetime(2026, 8, 2, tzinfo=UTC),
        review_id="review-p05-r3-contract-test",
        notes="Contract test only; no repository Gold approval is created.",
    )
    history = CandidateRevisionHistory.model_validate_json(
        (output_root / "provenance/p05_ocr_candidate_revision_history.json").read_text(
            encoding="utf-8"
        )
    )

    assert approved["approved_record_count"] == 15
    assert replayed == approved
    assert [revision.status for revision in history.revisions] == [
        "superseded",
        "superseded",
        "approved",
    ]
