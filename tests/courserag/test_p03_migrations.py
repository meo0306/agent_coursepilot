from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from types import ModuleType

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect

import courserag.persistence.models  # noqa: F401
from courserag.persistence.base import CourseRAGBase

P06_TABLES = {
    "courserag_chunk_profiles",
    "courserag_chunk_sets",
    "courserag_evidence_block_links",
    "courserag_evidence_page_bboxes",
    "courserag_evidence_relations",
}
P07_TABLES = {
    "courserag_knowledge_point_aliases",
    "courserag_kp_extraction_batches",
    "courserag_kp_window_runs",
    "courserag_kp_windows",
}
P08_TABLES = {
    "courserag_index_chunks",
    "courserag_rerank_cache",
}
P09_TABLES = {"courserag_context_packages"}
P10_TABLES = {
    "courserag_artifact_reuse_links",
    "courserag_citation_migration_items",
    "courserag_citation_migration_runs",
    "courserag_incremental_build_plans",
    "courserag_section_impacts",
    "courserag_verified_index_versions",
}
P06_COLUMNS = {
    "courserag_chunks": {
        "chunk_set_id",
        "parent_chunk_id",
        "chunk_kind",
        "token_count",
        "profile_sha256",
        "warning_codes_json",
    },
    "courserag_chunk_evidence": {
        "ordinal",
        "evidence_char_start",
        "evidence_char_end",
        "coverage_sha256",
    },
}
P07_COLUMNS = {
    "courserag_knowledge_points": {
        "normalized_name",
        "parent_knowledge_point_id",
        "publish_score",
        "publish_score_components_json",
        "auto_published",
        "origin",
        "extractor_version",
        "extractor_profile_sha256",
        "version_number",
        "updated_at",
    },
    "courserag_knowledge_point_evidence": {
        "role",
        "strength",
        "is_primary",
        "extraction_batch_id",
        "review_status",
        "created_at",
    },
    "courserag_knowledge_point_chunks": {
        "role",
        "strength",
        "use_for_filtering",
        "use_for_ranking",
        "derivation_sha256",
        "created_at",
    },
    "courserag_knowledge_point_reviews": {
        "idempotency_key",
        "request_sha256",
        "before_json",
        "after_json",
        "related_knowledge_point_ids_json",
        "response_json",
        "resulting_version_number",
    },
}
P08_COLUMNS = {
    "courserag_source_documents": {"source_tier"},
    "courserag_retrieval_runs": {
        "status",
        "request_sha256",
        "config_sha256",
        "result_sha256",
        "reranker_provider",
        "reranker_model",
        "candidate_k",
        "top_n",
        "dense_latency_ms",
        "sparse_latency_ms",
        "fusion_latency_ms",
        "rerank_latency_ms",
        "usage_json",
        "cost_json",
        "fallback_applied",
        "warnings_json",
        "debug_trace_json",
        "completed_at",
    },
}
P09_COLUMNS = {
    "courserag_query_processing_runs": {
        "status",
        "raw_query",
        "current_query",
        "config_sha256",
        "profile_sha256",
        "output_sha256",
        "step_trace_json",
        "filters_json",
        "knowledge_points_json",
        "expansions_json",
        "routes_json",
        "warnings_json",
        "usage_json",
        "provider",
        "model_name",
        "duration_ms",
        "completed_at",
    },
    "courserag_qa_runs": {
        "context_package_id",
        "question",
        "answer_status",
        "abstention_reason",
        "provider",
        "model_name",
        "prompt_sha256",
        "profile_sha256",
        "request_sha256",
        "result_sha256",
        "structured_output_json",
        "usage_json",
        "cost_json",
        "repair_count",
        "warnings_json",
        "duration_ms",
        "completed_at",
    },
    "courserag_answer_claims": {"external_claim_id", "validation_status"},
}
P10_COLUMNS = {
    "courserag_document_versions": {"previous_version_id"},
    "courserag_knowledge_bases": {"active_verified_index_version_id"},
    "courserag_verified_content": {
        "content_sha256",
        "version_sha256",
        "request_sha256",
        "approved_by",
        "task_id",
        "approval_record_id",
        "current_overlay_version_id",
        "revoked_by",
        "revoke_idempotency_key",
        "revoke_request_sha256",
        "source_tier",
        "retrieval_active",
        "token_count",
        "revoked_reason",
        "revoked_at",
    },
    "courserag_enrichment_batches": {
        "identity_sha256",
        "trigger_reason",
        "profile_sha256",
        "request_sha256",
        "worker_id",
        "trigger_snapshot_json",
        "locked_until",
        "attempt_count",
        "usage_json",
        "warnings_json",
        "completed_at",
    },
    "courserag_enrichment_batch_items": {
        "attempt_count",
        "profile_sha256",
        "result_json",
        "knowledge_point_links_json",
        "usage_json",
        "warnings_json",
        "completed_at",
    },
}


def _load(path: Path) -> ModuleType:
    spec = spec_from_file_location(path.stem, path)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_p03_migrations_upgrade_and_downgrade(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[2]
    versions = root / "alembic" / "versions"
    core = _load(versions / "2026_07_29_0008-create_courserag_core_tables.py")
    content = _load(versions / "2026_07_29_0009-create_courserag_content_tables.py")
    ocr = _load(versions / "2026_08_02_0010-expand_ocr_page_results.py")
    assert core.metadata is not CourseRAGBase.metadata
    assert content.metadata is not CourseRAGBase.metadata
    engine = create_engine(f"sqlite:///{tmp_path / 'migration.db'}")
    with engine.begin() as connection:
        operations = Operations(MigrationContext.configure(connection))
        core.op = operations
        content.op = operations
        core.upgrade()
        content.upgrade()
        ocr.op = operations
        ocr.upgrade()
        tables = set(inspect(connection).get_table_names())
        assert "courserag_knowledge_bases" in tables
        assert "courserag_index_versions" in tables
        assert "courserag_evidence" in tables
        assert "courserag_qa_runs" in tables
        assert tables == (
            set(CourseRAGBase.metadata.tables)
            - P06_TABLES
            - P07_TABLES
            - P08_TABLES
            - P09_TABLES
            - P10_TABLES
        )
        for table_name, expected_table in CourseRAGBase.metadata.tables.items():
            if table_name in P06_TABLES | P07_TABLES | P08_TABLES | P09_TABLES | P10_TABLES:
                continue
            actual_columns = {
                column["name"] for column in inspect(connection).get_columns(table_name)
            }
            expected_columns = (
                set(expected_table.columns.keys())
                - P06_COLUMNS.get(table_name, set())
                - P07_COLUMNS.get(table_name, set())
                - P08_COLUMNS.get(table_name, set())
                - P09_COLUMNS.get(table_name, set())
                - P10_COLUMNS.get(table_name, set())
            )
            assert actual_columns == expected_columns
        stage_uniques = {
            tuple(constraint["column_names"])
            for constraint in inspect(connection).get_unique_constraints(
                "courserag_build_stage_runs"
            )
        }
        assert stage_uniques == {("build_job_id", "stage_name", "attempt_number")}

        ocr.downgrade()
        legacy_ocr_columns = {
            column["name"]
            for column in inspect(connection).get_columns("courserag_ocr_page_results")
        }
        assert "status" not in legacy_ocr_columns
        assert "engine" in legacy_ocr_columns
        content.downgrade()
        remaining = set(inspect(connection).get_table_names())
        assert "courserag_evidence" not in remaining
        assert "courserag_knowledge_bases" in remaining
        core.downgrade()
        assert not {
            table
            for table in inspect(connection).get_table_names()
            if table.startswith("courserag_")
        }
