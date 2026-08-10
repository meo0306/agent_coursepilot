from __future__ import annotations

import importlib.util
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect, text


def _module(path: Path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_p08_additive_migration_roundtrip_preserves_source_document(tmp_path: Path) -> None:
    versions = Path(__file__).resolve().parents[2] / "alembic" / "versions"
    names = (
        "2026_07_29_0008-create_courserag_core_tables.py",
        "2026_07_29_0009-create_courserag_content_tables.py",
        "2026_08_02_0010-expand_ocr_page_results.py",
        "2026_08_04_0011-stable-evidence-parent-child-chunks.py",
        "2026_08_05_0012-knowledge-point-assets.py",
        "2026_08_07_0013-hybrid-retrieval.py",
    )
    migrations = [_module(versions / name) for name in names]
    engine = create_engine(f"sqlite:///{tmp_path / 'p08.db'}")
    with engine.begin() as connection:
        context = MigrationContext.configure(connection)
        old_proxy = Operations.context
        Operations.context = context
        try:
            for migration in migrations[:-1]:
                migration.op = Operations(context)
                migration.upgrade()
            connection.execute(
                text(
                    "INSERT INTO courserag_knowledge_bases "
                    "(id,course_id,name,language,status,created_at,updated_at) VALUES "
                    "('kb','course','name','zh-CN','empty',CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)"
                )
            )
            connection.execute(
                text(
                    "INSERT INTO courserag_source_documents "
                    "(id,knowledge_base_id,filename,document_type,status,created_at,updated_at) VALUES "
                    "('doc','kb','book.pdf','pdf','ready',CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)"
                )
            )
            p08 = migrations[-1]
            p08.op = Operations(context)
            p08.upgrade()
            tables = set(inspect(connection).get_table_names())
            assert {"courserag_index_chunks", "courserag_rerank_cache"} <= tables
            retrieval_columns = {
                item["name"] for item in inspect(connection).get_columns("courserag_retrieval_runs")
            }
            assert {"config_sha256", "debug_trace_json", "fallback_applied"} <= retrieval_columns
            assert (
                connection.scalar(
                    text("SELECT source_tier FROM courserag_source_documents WHERE id='doc'")
                )
                == "primary_source"
            )

            p08.downgrade()
            assert "courserag_index_chunks" not in set(inspect(connection).get_table_names())
            assert "source_tier" not in {
                item["name"]
                for item in inspect(connection).get_columns("courserag_source_documents")
            }
            assert (
                connection.scalar(
                    text("SELECT filename FROM courserag_source_documents WHERE id='doc'")
                )
                == "book.pdf"
            )

            p08.upgrade()
            assert "courserag_rerank_cache" in set(inspect(connection).get_table_names())
        finally:
            Operations.context = old_proxy
