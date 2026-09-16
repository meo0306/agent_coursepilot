import importlib.util
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect

from coursepilot.db.base import Base

ROOT = Path(__file__).resolve().parents[2]
MIGRATION = ROOT / "alembic/versions/2026_08_13_0016-coursepilot-runtime-foundation.py"


def test_p11_orm_registers_runtime_tables_and_task_columns() -> None:
    import coursepilot.models  # noqa: F401

    tables = Base.metadata.tables
    expected = {
        "coursepilot_workflow_runs",
        "coursepilot_artifacts",
        "coursepilot_artifact_versions",
        "coursepilot_node_runs",
        "coursepilot_approval_records",
        "coursepilot_template_snapshots",
        "coursepilot_model_invocations",
    }
    assert expected.issubset(tables)
    task_columns = tables["coursepilot_generation_tasks"].c
    assert {
        "workflow_type",
        "current_stage",
        "thread_id",
        "template_snapshot_id",
        "active_run_id",
        "input_version",
        "active_artifact_version",
    }.issubset(task_columns.keys())


def test_p11_migration_is_additive_and_reversible() -> None:
    content = MIGRATION.read_text(encoding="utf-8")
    assert 'revision: str = "0016_coursepilot_runtime_foundation"' in content
    assert 'down_revision: str | None = "0015_incremental_writeback_security"' in content
    for table in (
        "coursepilot_workflow_runs",
        "coursepilot_artifacts",
        "coursepilot_artifact_versions",
        "coursepilot_node_runs",
        "coursepilot_approval_records",
        "coursepilot_template_snapshots",
        "coursepilot_model_invocations",
    ):
        assert f'"{table}"' in content
        assert f'op.drop_table("{table}")' in content


def _migration_module(path: Path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_p11_additive_migration_roundtrip(tmp_path: Path) -> None:
    versions = ROOT / "alembic" / "versions"
    names = (
        "2026_06_20_0001-initial_coursepilot_base.py",
        "2026_06_21_0002-create_phase1_tables.py",
        "2026_06_22_0003-create_lesson_tables.py",
        "2026_06_30_0004-create_exam_tables.py",
        "2026_07_02_0005-create_ppt_review_tables.py",
        "2026_07_15_0006-create_idempotency_records.py",
        "2026_07_15_0007-add_async_task_queue_fields.py",
        "2026_07_29_0008-create_courserag_core_tables.py",
        "2026_07_29_0009-create_courserag_content_tables.py",
        "2026_08_02_0010-expand_ocr_page_results.py",
        "2026_08_04_0011-stable-evidence-parent-child-chunks.py",
        "2026_08_05_0012-knowledge-point-assets.py",
        "2026_08_07_0013-hybrid-retrieval.py",
        "2026_08_07_0014-query-context-cited-qa.py",
        "2026_08_10_0015-incremental-writeback-security.py",
        "2026_08_13_0016-coursepilot-runtime-foundation.py",
    )
    migrations = [_migration_module(versions / name) for name in names]
    engine = create_engine(f"sqlite:///{tmp_path / 'p11.db'}")
    with engine.begin() as connection:
        context = MigrationContext.configure(connection)
        previous = Operations.context
        Operations.context = context
        try:
            for migration in migrations[:-1]:
                migration.op = Operations(context)
                migration.upgrade()
            p11 = migrations[-1]
            p11.op = Operations(context)
            p11.upgrade()
            inspector = inspect(connection)
            assert {
                "coursepilot_workflow_runs",
                "coursepilot_artifacts",
                "coursepilot_artifact_versions",
                "coursepilot_node_runs",
                "coursepilot_approval_records",
                "coursepilot_template_snapshots",
                "coursepilot_model_invocations",
            } <= set(inspector.get_table_names())
            task_columns = {
                item["name"] for item in inspector.get_columns("coursepilot_generation_tasks")
            }
            assert {"thread_id", "template_snapshot_id", "active_run_id"} <= task_columns
            p11.downgrade()
            inspector = inspect(connection)
            assert "coursepilot_workflow_runs" not in inspector.get_table_names()
            assert "thread_id" not in {
                item["name"] for item in inspector.get_columns("coursepilot_generation_tasks")
            }
            p11.upgrade()
            assert "coursepilot_model_invocations" in inspect(connection).get_table_names()
        finally:
            Operations.context = previous
