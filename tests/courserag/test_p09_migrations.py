from __future__ import annotations

import importlib.util
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect


def _module(path: Path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_p09_additive_migration_roundtrip(tmp_path: Path) -> None:
    versions = Path(__file__).resolve().parents[2] / "alembic" / "versions"
    names = (
        "2026_07_29_0008-create_courserag_core_tables.py",
        "2026_07_29_0009-create_courserag_content_tables.py",
        "2026_08_02_0010-expand_ocr_page_results.py",
        "2026_08_04_0011-stable-evidence-parent-child-chunks.py",
        "2026_08_05_0012-knowledge-point-assets.py",
        "2026_08_07_0013-hybrid-retrieval.py",
        "2026_08_07_0014-query-context-cited-qa.py",
    )
    migrations = [_module(versions / name) for name in names]
    engine = create_engine(f"sqlite:///{tmp_path / 'p09.db'}")
    with engine.begin() as connection:
        context = MigrationContext.configure(connection)
        previous = Operations.context
        Operations.context = context
        try:
            for migration in migrations[:-1]:
                migration.op = Operations(context)
                migration.upgrade()
            p09 = migrations[-1]
            p09.op = Operations(context)
            p09.upgrade()
            inspector = inspect(connection)
            assert "courserag_context_packages" in inspector.get_table_names()
            query_columns = {
                item["name"] for item in inspector.get_columns("courserag_query_processing_runs")
            }
            assert {"step_trace_json", "routes_json", "profile_sha256"} <= query_columns
            qa_columns = {item["name"] for item in inspector.get_columns("courserag_qa_runs")}
            assert {"context_package_id", "repair_count", "structured_output_json"} <= qa_columns
            p09.downgrade()
            inspector = inspect(connection)
            assert "courserag_context_packages" not in inspector.get_table_names()
            assert "step_trace_json" not in {
                item["name"] for item in inspector.get_columns("courserag_query_processing_runs")
            }
            p09.upgrade()
            assert "courserag_context_packages" in inspect(connection).get_table_names()
        finally:
            Operations.context = previous
