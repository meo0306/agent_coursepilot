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


def test_p06_migration_upgrade_downgrade_upgrade(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[2]
    versions = root / "alembic" / "versions"
    core = _module(versions / "2026_07_29_0008-create_courserag_core_tables.py")
    content = _module(versions / "2026_07_29_0009-create_courserag_content_tables.py")
    ocr = _module(versions / "2026_08_02_0010-expand_ocr_page_results.py")
    p06 = _module(versions / "2026_08_04_0011-stable-evidence-parent-child-chunks.py")
    engine = create_engine(f"sqlite:///{tmp_path / 'p06.db'}")

    with engine.begin() as connection:
        context = MigrationContext.configure(connection)
        old_proxy = Operations.context
        Operations.context = context
        try:
            core.op = Operations(context)
            content.op = Operations(context)
            ocr.op = Operations(context)
            p06.op = Operations(context)
            core.upgrade()
            content.upgrade()
            ocr.upgrade()
            p06.upgrade()
            tables = set(inspect(connection).get_table_names())
            assert "courserag_evidence_block_links" in tables
            assert "courserag_chunk_sets" in tables
            chunk_columns = {
                column["name"] for column in inspect(connection).get_columns("courserag_chunks")
            }
            assert {"chunk_set_id", "parent_chunk_id", "chunk_kind"} <= chunk_columns

            p06.downgrade()
            tables = set(inspect(connection).get_table_names())
            assert "courserag_chunk_sets" not in tables
            assert "chunk_set_id" not in {
                column["name"] for column in inspect(connection).get_columns("courserag_chunks")
            }

            p06.upgrade()
            assert "courserag_chunk_sets" in set(inspect(connection).get_table_names())
        finally:
            Operations.context = old_proxy
