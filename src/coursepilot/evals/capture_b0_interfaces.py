"""Capture P00 public-structure snapshots and safe synthetic export samples."""

from __future__ import annotations

import argparse
import hashlib
import importlib
import inspect
import pkgutil
import tomllib
from pathlib import Path
from typing import Any

from pydantic import BaseModel
from sqlalchemy import MetaData

import coursepilot.schemas
import schema
from agents.coursepilot.graphs.exam_graph import coursepilot_exam_agent
from agents.coursepilot.graphs.lesson_graph import coursepilot_lesson_agent
from agents.coursepilot.graphs.ppt_graph import coursepilot_ppt_agent
from coursepilot.api.router import api_router
from coursepilot.db.base import Base
from coursepilot.evals.b0_baseline import sha256_file, write_json_atomic
from coursepilot.exporters import ExamDocxExporter, LessonDocxExporter, PPTXExporter
from coursepilot.llm import build_coursepilot_system_prompt
from coursepilot.prompts.loader import load_prompt
from coursepilot.schemas.exam_schema import ExamBlueprintContent, QuestionGroupPlan
from coursepilot.schemas.lesson_schema import (
    LessonDesignContent,
    LessonSession,
    Reference,
    SessionPlan,
    TeachingProcessItem,
    TimeAllocation,
)
from coursepilot.schemas.ppt_schema import SlideItem, SlideOutlineContent
from coursepilot.schemas.question_schema import QuestionItem
from service import app as service_app

INTERFACE_SCHEMA = "coursepilot.p00.interface-snapshot.v1"
EXPORT_SCHEMA = "coursepilot.p00.synthetic-export-manifest.v1"
LICENSE_SCHEMA = "coursepilot.p00.license-attribution.v1"


def capture_interface_snapshot(repository_root: Path, *, baseline_commit: str) -> dict[str, Any]:
    return {
        "schema_version": INTERFACE_SCHEMA,
        "baseline_commit": baseline_commit,
        "public_api": _api_snapshot(),
        "orm": _orm_snapshot(Base.metadata),
        "pydantic_schemas": _pydantic_snapshot(),
        "graphs": _graph_snapshot(),
        "prompts": _prompt_snapshot(repository_root),
        "behavior_changed": False,
    }


def generate_safe_export_samples(output_dir: Path) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    design, blueprint, question, outline = _synthetic_export_models()

    paths_with_roles = [
        (LessonDocxExporter().export(design, output_dir / "lesson_sample.docx"), "lesson_docx"),
        (
            ExamDocxExporter().export_student_exam(
                blueprint,
                [question],
                output_dir / "student_exam_sample.docx",
            ),
            "student_exam",
        ),
        (
            ExamDocxExporter().export_teacher_answer(
                blueprint,
                [question],
                output_dir / "teacher_answer_sample.docx",
            ),
            "teacher_answer",
        ),
        (
            ExamDocxExporter().export_explanation(
                blueprint,
                [question],
                output_dir / "explanation_sample.docx",
            ),
            "detailed_explanation",
        ),
        (
            ExamDocxExporter().export_answer_sheet(
                blueprint,
                [question],
                output_dir / "answer_sheet_sample.docx",
            ),
            "answer_sheet",
        ),
        (PPTXExporter().export(outline, output_dir / "ppt_sample.pptx"), "pptx"),
    ]
    return {
        "schema_version": EXPORT_SCHEMA,
        "content_origin": "fixed_synthetic_fixture",
        "contains_owner_sample_text": False,
        "files": [
            {
                "path": path.name,
                "file_role": role,
                "size_bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
            for path, role in paths_with_roles
        ],
    }


def capture_license_attribution(repository_root: Path) -> dict[str, Any]:
    license_path = repository_root / "LICENSE"
    project_data = tomllib.loads((repository_root / "pyproject.toml").read_text(encoding="utf-8"))
    return {
        "schema_version": LICENSE_SCHEMA,
        "license": {
            "spdx": "MIT",
            "path": "LICENSE",
            "sha256": sha256_file(license_path),
            "copyright_notice": "Copyright (c) 2024 Joshua Carroll",
        },
        "package_authors": project_data["project"]["authors"],
        "readme_references": [
            "README.md: MIT License",
            "README.zh-CN.md: MIT License",
        ],
        "upstream_attribution_preserved": True,
        "p00_author_metadata_changed": False,
        "follow_up_task": (
            "Review package author/maintainer metadata in a later repository-packaging phase "
            "without removing the MIT notice or upstream attribution."
        ),
    }


def _api_snapshot() -> dict[str, Any]:
    routes = []
    for route in service_app.routes:
        methods = sorted(getattr(route, "methods", set()) or set())
        response_model = getattr(route, "response_model", None)
        routes.append(
            {
                "path": getattr(route, "path", ""),
                "methods": methods,
                "name": getattr(route, "name", ""),
                "response_model": _type_name(response_model),
            }
        )
    routes.sort(key=lambda item: (item["path"], item["methods"], item["name"]))
    return {
        "route_count": len(routes),
        "coursepilot_route_count": len(api_router.routes),
        "routes": routes,
    }


def _orm_snapshot(metadata: MetaData) -> dict[str, Any]:
    tables = []
    for table in sorted(metadata.tables.values(), key=lambda item: item.name):
        columns = []
        for column in table.columns:
            columns.append(
                {
                    "name": column.name,
                    "type": str(column.type),
                    "nullable": column.nullable,
                    "primary_key": column.primary_key,
                    "unique": bool(column.unique),
                    "foreign_keys": sorted(key.target_fullname for key in column.foreign_keys),
                }
            )
        tables.append(
            {
                "name": table.name,
                "columns": columns,
                "constraints": sorted(
                    constraint.__class__.__name__ for constraint in table.constraints
                ),
            }
        )
    return {"table_count": len(tables), "tables": tables}


def _pydantic_snapshot() -> dict[str, Any]:
    schemas = []
    for package in (coursepilot.schemas, schema):
        package_file = package.__file__
        if package_file is None:
            raise RuntimeError(f"Cannot locate schema package: {package.__name__}")
        package_path = Path(package_file).parent
        for module_info in pkgutil.iter_modules([str(package_path)]):
            module = importlib.import_module(f"{package.__name__}.{module_info.name}")
            for name, candidate in inspect.getmembers(module, inspect.isclass):
                if candidate is BaseModel or not issubclass(candidate, BaseModel):
                    continue
                if candidate.__module__ != module.__name__:
                    continue
                fields = [
                    {
                        "name": field_name,
                        "annotation": _type_name(field.annotation),
                        "required": field.is_required(),
                    }
                    for field_name, field in candidate.model_fields.items()
                ]
                schemas.append(
                    {
                        "module": module.__name__,
                        "name": name,
                        "fields": fields,
                    }
                )
    schemas.sort(key=lambda item: (item["module"], item["name"]))
    return {"schema_count": len(schemas), "schemas": schemas}


def _graph_snapshot() -> list[dict[str, Any]]:
    compiled_graphs: dict[str, Any] = {
        "coursepilot_lesson_agent": coursepilot_lesson_agent,
        "coursepilot_exam_agent": coursepilot_exam_agent,
        "coursepilot_ppt_agent": coursepilot_ppt_agent,
    }
    result = []
    for name, compiled in compiled_graphs.items():
        graph = compiled.get_graph()
        result.append(
            {
                "name": name,
                "nodes": sorted(graph.nodes),
                "edges": sorted(
                    (
                        {
                            "source": edge.source,
                            "target": edge.target,
                            "conditional": edge.conditional,
                        }
                        for edge in graph.edges
                    ),
                    key=lambda item: (
                        item["source"],
                        item["target"],
                        item["conditional"],
                    ),
                ),
            }
        )
    return result


def _prompt_snapshot(repository_root: Path) -> dict[str, Any]:
    prompt_root = repository_root / "src" / "coursepilot" / "prompts"
    prompts = []
    for path in sorted(prompt_root.rglob("*.md")):
        name = path.relative_to(prompt_root).with_suffix("").as_posix()
        # P14's provider prompts are additive and are intentionally outside the
        # frozen pre-P14 B0 interface snapshot.
        if name.startswith("lesson/p14_"):
            continue
        raw_prompt = load_prompt(name)
        effective_prompt = build_coursepilot_system_prompt(raw_prompt)
        prompts.append(
            {
                "name": name,
                "path": path.relative_to(repository_root).as_posix(),
                "file_sha256": sha256_file(path),
                "effective_prompt_sha256": hashlib.sha256(
                    effective_prompt.encode("utf-8")
                ).hexdigest(),
            }
        )
    return {"prompt_count": len(prompts), "prompts": prompts}


def _synthetic_export_models() -> tuple[
    LessonDesignContent,
    ExamBlueprintContent,
    QuestionItem,
    SlideOutlineContent,
]:
    reference = Reference(chunk_id="synthetic-chunk-1", source_type="synthetic")
    design = LessonDesignContent(
        course_name="B0 Synthetic Course",
        chapter="Synthetic Topic",
        total_sessions=1,
        session_duration=45,
        knowledge_points=["synthetic concept"],
        session_plan=[
            SessionPlan(
                session_index=1,
                session_title="Synthetic Session",
                duration=45,
                knowledge_points=["synthetic concept"],
                teaching_focus="synthetic concept",
                time_allocation=[
                    TimeAllocation(activity="Introduction", minutes=5),
                    TimeAllocation(activity="Instruction", minutes=30),
                    TimeAllocation(activity="Practice", minutes=5),
                    TimeAllocation(activity="Summary", minutes=5),
                ],
            )
        ],
        sessions=[
            LessonSession(
                session_index=1,
                session_title="Synthetic Session",
                teaching_objectives=["Explain the synthetic concept"],
                key_points=["synthetic concept"],
                teaching_process=[
                    TeachingProcessItem(
                        stage="Instruction",
                        minutes=30,
                        content="Use a fixed synthetic example.",
                    )
                ],
                references=[reference],
            )
        ],
    )
    blueprint = ExamBlueprintContent(
        course_name="B0 Synthetic Course",
        chapter_range="Synthetic Topic",
        generation_type="exam",
        total_score=2,
        question_groups=[
            QuestionGroupPlan(
                question_type="single_choice",
                count=1,
                score_each=2,
                total_score=2,
                knowledge_points=["synthetic concept"],
                difficulty="medium",
            )
        ],
        knowledge_points=["synthetic concept"],
    )
    question = QuestionItem(
        question_type="single_choice",
        knowledge_point="synthetic concept",
        difficulty="medium",
        score=2,
        question_text="Which option is the fixed synthetic answer?",
        options={"A": "Synthetic answer", "B": "Distractor"},
        correct_answer="A",
        explanation="This is a fixed synthetic explanation.",
        references=[reference],
    )
    outline = SlideOutlineContent(
        course_name="B0 Synthetic Course",
        chapter="Synthetic Topic",
        lesson_id="synthetic-lesson-1",
        slides=[
            SlideItem(
                slide_index=1,
                slide_type="title",
                title="B0 Synthetic Course",
                bullet_points=["Synthetic Topic"],
            ),
            SlideItem(
                slide_index=2,
                slide_type="content",
                title="Synthetic Concept",
                bullet_points=["Fixed point one", "Fixed point two"],
                references=[reference],
                source_session_index=1,
            ),
            SlideItem(
                slide_index=3,
                slide_type="references",
                title="References",
                bullet_points=["synthetic-chunk-1"],
                references=[reference],
            ),
        ],
    )
    return design, blueprint, question, outline


def _type_name(value: Any) -> str:
    if value is None:
        return "None"
    if isinstance(value, type):
        return f"{value.__module__}.{value.__qualname__}"
    return str(value)


def main() -> None:
    parser = argparse.ArgumentParser(description="Capture P00 interface and attribution snapshots.")
    parser.add_argument("--repository-root", default=".")
    parser.add_argument("--output-dir", default="docs/refactor/baselines/b0")
    parser.add_argument("--baseline-commit", required=True)
    args = parser.parse_args()

    repository_root = Path(args.repository_root).resolve()
    output_dir = repository_root / args.output_dir
    write_json_atomic(
        output_dir / "07_interface_snapshot.json",
        capture_interface_snapshot(repository_root, baseline_commit=args.baseline_commit),
    )
    export_manifest = generate_safe_export_samples(output_dir / "export_samples")
    for item in export_manifest["files"]:
        item["path"] = f"export_samples/{item['path']}"
    write_json_atomic(output_dir / "07_export_sample_manifest.json", export_manifest)
    write_json_atomic(
        output_dir / "08_license_attribution.json",
        capture_license_attribution(repository_root),
    )


if __name__ == "__main__":
    main()
