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


def test_p07_migration_preserves_placeholder_and_roundtrips(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[2]
    versions = root / "alembic" / "versions"
    migrations = [
        _module(versions / "2026_07_29_0008-create_courserag_core_tables.py"),
        _module(versions / "2026_07_29_0009-create_courserag_content_tables.py"),
        _module(versions / "2026_08_02_0010-expand_ocr_page_results.py"),
        _module(versions / "2026_08_04_0011-stable-evidence-parent-child-chunks.py"),
        _module(versions / "2026_08_05_0012-knowledge-point-assets.py"),
    ]
    engine = create_engine(f"sqlite:///{tmp_path / 'p07.db'}")
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
                    "INSERT INTO courserag_knowledge_points "
                    "(id,knowledge_base_id,stable_key,title,status,metadata_json,created_at) VALUES "
                    "('kp','kb','legacy-key','Legacy KP','candidate','{}',CURRENT_TIMESTAMP)"
                )
            )
            p07 = migrations[-1]
            p07.op = Operations(context)
            p07.upgrade()

            tables = set(inspect(connection).get_table_names())
            assert {
                "courserag_kp_extraction_batches",
                "courserag_kp_windows",
                "courserag_kp_window_runs",
                "courserag_knowledge_point_aliases",
            } <= tables
            columns = {
                item["name"]
                for item in inspect(connection).get_columns("courserag_knowledge_points")
            }
            assert {
                "normalized_name",
                "parent_knowledge_point_id",
                "publish_score",
                "version_number",
            } <= columns
            assert (
                connection.scalar(
                    text("SELECT status FROM courserag_knowledge_points WHERE id='kp'")
                )
                == "unreviewed"
            )

            p07.downgrade()
            assert "courserag_kp_windows" not in set(inspect(connection).get_table_names())
            assert "publish_score" not in {
                item["name"]
                for item in inspect(connection).get_columns("courserag_knowledge_points")
            }
            assert (
                connection.scalar(
                    text("SELECT status FROM courserag_knowledge_points WHERE id='kp'")
                )
                == "candidate"
            )

            p07.upgrade()
            assert "courserag_kp_windows" in set(inspect(connection).get_table_names())
            assert (
                connection.scalar(
                    text("SELECT status FROM courserag_knowledge_points WHERE id='kp'")
                )
                == "unreviewed"
            )
        finally:
            Operations.context = old_proxy
