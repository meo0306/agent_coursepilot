import json
from pathlib import Path

import pytest

from coursepilot.evals import (
    AnswerCompletenessCase,
    CitationCase,
    CoursePilotEvalInput,
    CoursePilotEvaluator,
    ExportCase,
    QuestionCountCase,
    RetrievalCase,
    SchemaCase,
)
from coursepilot.evals.run_sample_eval import build_sample_payload


def test_coursepilot_evaluator_computes_core_metrics(tmp_path):
    export_file = tmp_path / "lesson.docx"
    export_file.write_bytes(b"not-empty")
    payload = CoursePilotEvalInput(
        retrieval_cases=[
            RetrievalCase(
                query="search",
                expected_chunk_ids=["a", "b"],
                retrieved_chunk_ids=["a", "c"],
            )
        ],
        citation_cases=[
            CitationCase(item_id="cited", citation_chunk_ids=["a"]),
            CitationCase(item_id="missing"),
        ],
        schema_cases=[
            SchemaCase(item_id="lesson", schema_valid=True),
            SchemaCase(item_id="ppt", schema_valid=False),
        ],
        question_count_cases=[
            QuestionCountCase(
                expected_counts={"single_choice": 2, "short_answer": 1},
                actual_counts={"single_choice": 2, "short_answer": 0},
            )
        ],
        duplicate_rate=0.25,
        answer_cases=[
            AnswerCompletenessCase(item_id="q1", has_answer=True, has_explanation=True),
            AnswerCompletenessCase(item_id="q2", has_answer=True, has_explanation=False),
        ],
        export_cases=[
            ExportCase(file_path=str(export_file), file_role="lesson_docx"),
            ExportCase(file_path=str(tmp_path / "missing.docx"), file_role="pptx"),
        ],
    )

    report = CoursePilotEvaluator().evaluate(payload)

    assert report.rag_recall_at_k == 0.5
    assert report.rag_hit_at_k == 1.0
    assert report.rag_mrr == 1.0
    assert report.rag_ndcg == pytest.approx(0.6131471927654584)
    assert report.context_precision == 0.5
    assert report.citation_coverage == 0.5
    assert report.schema_pass_rate == 0.5
    assert report.question_count_accuracy == 0.5
    assert report.duplicate_rate == 0.25
    assert report.answer_completeness == 0.5
    assert report.export_success_rate == 0.5


def test_sample_eval_payload_uses_sample_course_files():
    payload = build_sample_payload(sample_dir=Path("data/coursepilot_sample"))
    report = CoursePilotEvaluator().evaluate(payload)
    data = json.loads(report.model_dump_json())

    assert data["rag_recall_at_k"] == 1.0
    assert data["schema_pass_rate"] == 1.0
    assert data["question_count_accuracy"] == 1.0
    assert data["export_success_rate"] > 0
