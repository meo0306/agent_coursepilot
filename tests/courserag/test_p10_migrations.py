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


def test_p10_additive_migration_roundtrip(tmp_path: Path) -> None:
    versions = Path(__file__).resolve().parents[2] / "alembic" / "versions"
    names = (
        "2026_07_29_0008-create_courserag_core_tables.py",
        "2026_07_29_0009-create_courserag_content_tables.py",
        "2026_08_02_0010-expand_ocr_page_results.py",
        "2026_08_04_0011-stable-evidence-parent-child-chunks.py",
        "2026_08_05_0012-knowledge-point-assets.py",
        "2026_08_07_0013-hybrid-retrieval.py",
        "2026_08_07_0014-query-context-cited-qa.py",
        "2026_08_10_0015-incremental-writeback-security.py",
    )
    migrations = [_module(versions / name) for name in names]
    engine = create_engine(f"sqlite:///{tmp_path / 'p10.db'}")
    with engine.begin() as connection:
        context = MigrationContext.configure(connection)
        previous = Operations.context
        Operations.context = context
        try:
            for migration in migrations[:-1]:
                migration.op = Operations(context)
                migration.upgrade()
            p10 = migrations[-1]
            p10.op = Operations(context)
            p10.upgrade()
            inspector = inspect(connection)
            tables = set(inspector.get_table_names())
            assert {
                "courserag_incremental_build_plans",
                "courserag_section_impacts",
                "courserag_citation_migration_runs",
                "courserag_verified_index_versions",
            } <= tables
            version_columns = {
                item["name"] for item in inspector.get_columns("courserag_document_versions")
            }
            assert "previous_version_id" in version_columns
            verified_columns = {
                item["name"] for item in inspector.get_columns("courserag_verified_content")
            }
            assert {"content_sha256", "retrieval_active", "revoked_at"} <= verified_columns
            p10.downgrade()
            inspector = inspect(connection)
            assert "courserag_incremental_build_plans" not in inspector.get_table_names()
            assert "previous_version_id" not in {
                item["name"] for item in inspector.get_columns("courserag_document_versions")
            }
            p10.upgrade()
            assert "courserag_verified_index_versions" in inspect(connection).get_table_names()
        finally:
            Operations.context = previous
