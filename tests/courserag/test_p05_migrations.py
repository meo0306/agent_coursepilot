from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from types import ModuleType

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError


def _load(path: Path) -> ModuleType:
    spec = spec_from_file_location(path.stem, path)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_p05_ocr_migration_preserves_legacy_rows_and_requires_complete_ready_rows(
    tmp_path: Path,
) -> None:
    root = Path(__file__).resolve().parents[2]
    versions = root / "alembic" / "versions"
    core = _load(versions / "2026_07_29_0008-create_courserag_core_tables.py")
    content = _load(versions / "2026_07_29_0009-create_courserag_content_tables.py")
    ocr = _load(versions / "2026_08_02_0010-expand_ocr_page_results.py")
    engine = create_engine(f"sqlite:///{tmp_path / 'p05.db'}")
    with engine.begin() as connection:
        operations = Operations(MigrationContext.configure(connection))
        core.op = operations
        content.op = operations
        ocr.op = operations
        core.upgrade()
        content.upgrade()
        ocr.upgrade()
        columns = {column["name"] for column in inspect(connection).get_columns(ocr.TABLE)}
        assert {
            "status",
            "model_name",
            "profile_sha256",
            "regions_json",
            "peak_memory_bytes",
        } <= columns
        connection.execute(
            text(
                "INSERT INTO courserag_knowledge_bases "
                "(id,course_id,name,language,status,created_at,updated_at) "
                "VALUES ('kb','course','name','zh-CN','empty',CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)"
            )
        )
        connection.execute(
            text(
                "INSERT INTO courserag_source_documents "
                "(id,knowledge_base_id,filename,document_type,status,created_at,updated_at) "
                "VALUES ('doc','kb','a.pdf','pdf','registered',CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)"
            )
        )
        connection.execute(
            text(
                "INSERT INTO courserag_document_versions "
                "(id,source_document_id,version_number,content_sha256,object_uri,mime_type,"
                "size_bytes,status,source_metadata_json,created_at) VALUES "
                "('version','doc',1,:sha,'file:///a.pdf','application/pdf',1,'ready','{}',CURRENT_TIMESTAMP)"
            ),
            {"sha": "a" * 64},
        )
        connection.execute(
            text(
                "INSERT INTO courserag_parsed_documents "
                "(id,document_version_id,parser_profile,parser_version,status,warnings_json,created_at,updated_at) "
                "VALUES ('parsed','version','p','1','ready','[]',CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)"
            )
        )
        connection.execute(
            text(
                "INSERT INTO courserag_pages "
                "(id,parsed_document_id,page_index,source_mode,metadata_json) "
                "VALUES ('page','parsed',1,'ocr_pending','{}')"
            )
        )
        with pytest.raises(IntegrityError):
            connection.execute(
                text(
                    "INSERT INTO courserag_ocr_page_results "
                    "(id,page_id,engine,engine_version,image_sha256,confidence,warnings_json,status) "
                    "VALUES ('ocr','page','rapidocr','1',:sha,NULL,'[]','ready')"
                ),
                {"sha": "b" * 64},
            )

        ocr.downgrade()
        downgraded = {column["name"] for column in inspect(connection).get_columns(ocr.TABLE)}
        assert "status" not in downgraded
        ocr.upgrade()
        assert "status" in {column["name"] for column in inspect(connection).get_columns(ocr.TABLE)}
