"""Run the local, deterministic P00 B0 smoke workflow.

The runner uses the public CoursePilot API in-process with an isolated SQLite database and
temporary Chroma/storage directories. It never calls an external model provider and never
serializes textbook content into its report.
"""

from __future__ import annotations

import argparse
import subprocess
import tempfile
import time
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from core import settings
from coursepilot.db.base import Base
from coursepilot.db.session import get_session
from coursepilot.evals.b0_baseline import (
    B0_REPORT_SCHEMA,
    SampleInput,
    build_sample_manifest,
    discover_sample_inputs,
    select_non_gold_probe,
    sha256_file,
    write_json_atomic,
)
from coursepilot.models import KnowledgeChunk
from coursepilot.rag.vector_store import ChromaVectorStore
from coursepilot.services.task_worker import CoursePilotTaskWorker
from service import app


def run_b0_smoke(
    *,
    repository_root: Path,
    sample_dir: Path,
    output_path: Path,
    baseline_commit: str,
) -> dict[str, Any]:
    repository_root = repository_root.resolve()
    inputs = discover_sample_inputs(sample_dir, repository_root)
    captured_at = datetime.now(UTC).isoformat()
    manifest = build_sample_manifest(
        inputs,
        baseline_commit=baseline_commit,
        captured_at=captured_at,
    )
    started = time.perf_counter()

    with tempfile.TemporaryDirectory(
        prefix="coursepilot-p00-b0-",
        ignore_cleanup_errors=True,
    ) as temporary_directory:
        temporary_root = Path(temporary_directory)
        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(engine)
        session_factory = sessionmaker(
            bind=engine,
            class_=Session,
            autoflush=False,
            autocommit=False,
        )
        previous_settings = _configure_isolated_runtime(temporary_root)
        previous_worker = getattr(app.state, "coursepilot_test_task_worker", None)

        def override_get_session():
            with session_factory() as session:
                yield session

        app.dependency_overrides[get_session] = override_get_session
        worker = CoursePilotTaskWorker(
            session_factory=session_factory,
            poll_seconds=0,
            lease_seconds=30,
        )
        app.state.coursepilot_test_task_worker = worker
        client = TestClient(app)
        try:
            documents: list[dict[str, Any]] = []
            runtime_by_suffix: dict[str, dict[str, Any]] = {}
            for sample_input in inputs:
                result, runtime_context = _run_document_smoke(
                    client=client,
                    worker=worker,
                    session_factory=session_factory,
                    sample_input=sample_input,
                    chroma_dir=temporary_root / "chroma",
                )
                documents.append(result)
                runtime_by_suffix[sample_input.path.suffix.lower()] = runtime_context

            docx_context = runtime_by_suffix[".docx"]
            workflows = _run_workflow_smoke(
                client=client,
                worker=worker,
                course_id=str(docx_context["course_id"]),
            )
        finally:
            client.close()
            app.dependency_overrides.pop(get_session, None)
            app.state.coursepilot_test_task_worker = previous_worker
            _stop_isolated_chroma(temporary_root / "chroma")
            _restore_settings(previous_settings)
            Base.metadata.drop_all(engine)
            engine.dispose()

    report: dict[str, Any] = {
        "schema_version": B0_REPORT_SCHEMA,
        "generated_at": captured_at,
        "baseline_commit": baseline_commit,
        "input_manifest": manifest,
        "runtime": {
            "database": "isolated_sqlite",
            "vector_store": "isolated_chroma",
            "generation_mode": "deterministic",
            "embedding_provider": "hashing",
            "knowledge_points_mode": "deterministic",
            "external_provider_calls_allowed": False,
        },
        "documents": documents,
        "workflows": workflows,
        "elapsed_ms": round((time.perf_counter() - started) * 1000),
        "quality_claims": {
            "retrieval_metrics_published": False,
            "gold_used": False,
            "classification": "non_gold_smoke_only",
        },
    }
    write_json_atomic(output_path, report)
    return report


def _run_document_smoke(
    *,
    client: TestClient,
    worker: CoursePilotTaskWorker,
    session_factory: sessionmaker[Session],
    sample_input: SampleInput,
    chroma_dir: Path,
) -> tuple[dict[str, Any], dict[str, Any]]:
    suffix_name = sample_input.path.suffix.lower().removeprefix(".").upper()
    course = _require_status(
        client.post(
            "/api/coursepilot/courses",
            json={
                "course_name": f"P00 B0 {suffix_name}",
                "course_type": "b0_smoke",
                "student_level": "unspecified",
                "description": "Isolated P00 B0 smoke course.",
            },
        ),
        201,
    )
    course_id = str(course["id"])
    upload = _require_status(
        client.post(
            f"/api/coursepilot/courses/{course_id}/documents/upload",
            files={
                "file": (
                    sample_input.path.name,
                    sample_input.path.read_bytes(),
                    sample_input.media_type,
                )
            },
            data={"source_type": "textbook"},
        ),
        201,
    )
    document_id = str(upload["id"])

    probe = select_non_gold_probe(sample_input.path)
    build_started = time.perf_counter()
    build = _submit_and_complete(
        client,
        worker,
        f"/api/coursepilot/documents/{document_id}/build-kb",
    )
    build_elapsed_ms = round((time.perf_counter() - build_started) * 1000)
    if build.get("parse_status") != "built" or int(build.get("chunk_count", 0)) <= 0:
        raise RuntimeError(f"B0 build failed for {sample_input.path.name}: {build!r}")

    search = _require_status(
        client.post(
            f"/api/coursepilot/courses/{course_id}/kb/search",
            json={"query": probe.query, "top_k": 5},
        ),
        200,
    )
    results = list(search["results"])
    if not results:
        raise RuntimeError(f"B0 search returned no results for {sample_input.path.name}")
    course_scope_passed = all(item["course_id"] == course_id for item in results)
    document_scope_passed = all(item["document_id"] == document_id for item in results)
    if not course_scope_passed or not document_scope_passed:
        raise RuntimeError(f"B0 retrieval scope violation for {sample_input.path.name}")

    with session_factory() as session:
        db_chunk_count = int(
            session.scalar(
                select(func.count())
                .select_from(KnowledgeChunk)
                .where(KnowledgeChunk.document_id == document_id)
            )
            or 0
        )
    vector_chunk_count = int(
        ChromaVectorStore(persist_directory=str(chroma_dir))
        .collection_for_course(course_id)
        ._collection.count()
    )
    build_chunk_count = int(build["chunk_count"])
    if db_chunk_count != build_chunk_count or vector_chunk_count != build_chunk_count:
        raise RuntimeError(
            f"B0 chunk count mismatch for {sample_input.path.name}: "
            f"build={build_chunk_count} db={db_chunk_count} vector={vector_chunk_count}"
        )

    safe_result = {
        "input": sample_input.as_manifest_item(),
        "course_id": course_id,
        "document_id": document_id,
        "parse_status": build["parse_status"],
        "chunk_count": build_chunk_count,
        "database_chunk_count": db_chunk_count,
        "vector_chunk_count": vector_chunk_count,
        "build_elapsed_ms": build_elapsed_ms,
        "probe": {
            **probe.safe_metadata(),
            "result_count": len(results),
            "course_scope_passed": course_scope_passed,
            "document_scope_passed": document_scope_passed,
        },
    }
    return safe_result, {"course_id": course_id, "document_id": document_id}


def _run_workflow_smoke(
    *,
    client: TestClient,
    worker: CoursePilotTaskWorker,
    course_id: str,
) -> dict[str, Any]:
    lesson = _submit_and_complete(
        client,
        worker,
        f"/api/coursepilot/courses/{course_id}/lessons/generate",
        json={
            "chapter_range": "B0 smoke scope",
            "total_sessions": 2,
            "session_duration": 45,
            "teaching_template": "standard",
        },
    )
    lesson_id = str(lesson["lesson_id"])
    lesson_export = _require_status(
        client.post(f"/api/coursepilot/lessons/{lesson_id}/export"),
        200,
    )

    blueprint = _submit_and_complete(
        client,
        worker,
        f"/api/coursepilot/courses/{course_id}/exams/blueprint",
        json={
            "chapter_range": "B0 smoke scope",
            "question_counts": {"single_choice": 1},
            "score_per_question": {"single_choice": 2},
        },
    )
    blueprint_id = str(blueprint["blueprint_id"])
    _require_status(client.post(f"/api/coursepilot/exams/{blueprint_id}/confirm"), 200)
    questions_result = _submit_and_complete(
        client,
        worker,
        f"/api/coursepilot/exams/{blueprint_id}/generate",
    )
    questions = _require_status(
        client.get(f"/api/coursepilot/exams/{blueprint_id}/questions"),
        200,
    )
    exam_export = _require_status(
        client.post(f"/api/coursepilot/exams/{blueprint_id}/export"),
        200,
    )

    ppt = _submit_and_complete(
        client,
        worker,
        f"/api/coursepilot/lessons/{lesson_id}/ppt/generate",
        json={"slide_count": 6, "style_template": "standard", "include_references": True},
    )
    outline_id = str(ppt["outline_id"])
    ppt_export = _require_status(
        client.post(f"/api/coursepilot/ppt/{outline_id}/export"),
        200,
    )

    review_targets = [
        ("lesson_design", lesson_id),
        ("question", str(questions[0]["id"])),
        ("ppt_outline", outline_id),
    ]
    write_backs = []
    for target_type, target_id in review_targets:
        review = _require_status(
            client.post(
                "/api/coursepilot/reviews",
                json={
                    "target_type": target_type,
                    "target_id": target_id,
                    "review_status": "approved",
                    "comment": "P00 deterministic smoke approval.",
                },
            ),
            200,
        )
        write_back = _require_status(
            client.post(f"/api/coursepilot/reviews/{review['id']}/write-back"),
            200,
        )
        write_backs.append(
            {
                "target_type": target_type,
                "write_back_status": write_back["write_back_status"],
                "written_chunk_count": len(write_back["written_chunk_ids"]),
            }
        )

    exports = [
        _safe_export_metadata(lesson_export),
        *(_safe_export_metadata(item) for item in exam_export["files"]),
        _safe_export_metadata(ppt_export),
    ]
    if not all(item["valid_openxml_container"] for item in exports):
        raise RuntimeError("One or more B0 exports is not a valid OpenXML container")
    allowed_write_back_statuses = {
        "written",
        "requires_fragment_selection",
        "requires_evidence_migration",
    }
    if not all(item["write_back_status"] in allowed_write_back_statuses for item in write_backs):
        raise RuntimeError("One or more B0 review write-backs returned an unsafe state")

    return {
        "lesson": {"status": lesson["status"], "exported": True},
        "exam": {
            "blueprint_status": blueprint["status"],
            "question_count": len(questions_result["questions"]),
            "exported_roles": sorted(item["file_role"] for item in exam_export["files"]),
        },
        "ppt": {
            "status": ppt["status"],
            "slide_count": len(ppt["outline"]["slides"]),
            "exported": True,
        },
        "exports": exports,
        "review_write_backs": write_backs,
    }


def _submit_and_complete(
    client: TestClient,
    worker: CoursePilotTaskWorker,
    path: str,
    *,
    json: dict[str, Any] | None = None,
) -> dict[str, Any]:
    accepted = client.post(path, json=json)
    accepted_payload = _require_status(accepted, 202)
    if worker.run_once() is not True:
        raise RuntimeError(f"No async task was available after submitting {path}")
    task = _require_status(
        client.get(f"/api/coursepilot/tasks/{accepted_payload['task_id']}"),
        200,
    )
    if task["status"] not in {"completed", "needs_review"} or task["result"] is None:
        raise RuntimeError(f"B0 task failed for {path}: status={task['status']}")
    return dict(task["result"])


def _require_status(response: Any, expected_status: int) -> Any:
    if response.status_code != expected_status:
        raise RuntimeError(
            f"Unexpected API status {response.status_code}; expected {expected_status}: "
            f"{response.text[:500]}"
        )
    return response.json()


def _safe_export_metadata(payload: dict[str, Any]) -> dict[str, Any]:
    path = Path(payload["file_path"])
    return {
        "file_name": path.name,
        "file_role": payload["file_role"],
        "size_bytes": path.stat().st_size,
        "sha256": sha256_file(path),
        "valid_openxml_container": zipfile.is_zipfile(path),
        "source_text_included_in_report": False,
    }


def _configure_isolated_runtime(temporary_root: Path) -> dict[str, Any]:
    values = {
        "COURSEPILOT_GENERATION_MODE": "deterministic",
        "COURSEPILOT_EMBEDDING_PROVIDER": "hashing",
        "COURSEPILOT_RAG_KNOWLEDGE_POINTS_MODE": "deterministic",
        "COURSEPILOT_ASYNC_WORKER_ENABLED": False,
        "COURSEPILOT_STORAGE_DIR": str(temporary_root / "storage"),
        "COURSEPILOT_CHROMA_DIR": str(temporary_root / "chroma"),
    }
    previous = {name: getattr(settings, name) for name in values}
    for name, value in values.items():
        setattr(settings, name, value)
    return previous


def _restore_settings(previous: dict[str, Any]) -> None:
    for name, value in previous.items():
        setattr(settings, name, value)


def _stop_isolated_chroma(chroma_dir: Path) -> None:
    """Release Chroma's shared Windows file handles before removing the temp directory."""

    from chromadb.api.shared_system_client import SharedSystemClient

    target = str(chroma_dir.resolve())
    systems = SharedSystemClient._identifier_to_system
    system = systems.pop(target, None)
    if system is not None:
        system.stop()


def _git_head(repository_root: Path) -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repository_root,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run deterministic P00 B0 smoke.")
    parser.add_argument("--repository-root", default=".")
    parser.add_argument("--sample-dir", default="data/sample_files")
    parser.add_argument(
        "--output",
        default="docs/refactor/baselines/b0/05_b0_smoke_report.json",
    )
    parser.add_argument("--baseline-commit", default="")
    args = parser.parse_args()

    repository_root = Path(args.repository_root).resolve()
    baseline_commit = args.baseline_commit or _git_head(repository_root)
    run_b0_smoke(
        repository_root=repository_root,
        sample_dir=(repository_root / args.sample_dir),
        output_path=(repository_root / args.output),
        baseline_commit=baseline_commit,
    )


if __name__ == "__main__":
    main()
