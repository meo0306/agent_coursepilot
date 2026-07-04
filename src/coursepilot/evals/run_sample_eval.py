import argparse
import json
from pathlib import Path

from coursepilot.evals.metrics import (
    AnswerCompletenessCase,
    CitationCase,
    CoursePilotEvalInput,
    CoursePilotEvaluator,
    ExportCase,
    QuestionCountCase,
    RetrievalCase,
    SchemaCase,
)


def build_sample_payload(sample_dir: Path) -> CoursePilotEvalInput:
    sample_files = [path for path in sample_dir.glob("*") if path.is_file()]
    return CoursePilotEvalInput(
        retrieval_cases=[
            RetrievalCase(
                query="state space search",
                expected_chunk_ids=["chunk-textbook-1"],
                retrieved_chunk_ids=["chunk-textbook-1", "chunk-syllabus-1"],
            ),
            RetrievalCase(
                query="knowledge graph",
                expected_chunk_ids=["chunk-kg-1"],
                retrieved_chunk_ids=["chunk-kg-1"],
            ),
        ],
        citation_cases=[
            CitationCase(item_id="lesson-session-1", citation_chunk_ids=["chunk-textbook-1"]),
            CitationCase(item_id="exam-question-1", citation_chunk_ids=["chunk-textbook-1"]),
            CitationCase(item_id="ppt-slide-2", citation_chunk_ids=["chunk-kg-1"]),
        ],
        schema_cases=[
            SchemaCase(item_id="lesson-design", schema_valid=True),
            SchemaCase(item_id="exam-question-set", schema_valid=True),
            SchemaCase(item_id="ppt-outline", schema_valid=True),
        ],
        question_count_cases=[
            QuestionCountCase(
                expected_counts={
                    "single_choice": 5,
                    "multiple_choice": 2,
                    "judgement": 3,
                    "short_answer": 2,
                },
                actual_counts={
                    "single_choice": 5,
                    "multiple_choice": 2,
                    "judgement": 3,
                    "short_answer": 2,
                },
            )
        ],
        duplicate_rate=0.0,
        answer_cases=[
            AnswerCompletenessCase(item_id="q1", has_answer=True, has_explanation=True),
            AnswerCompletenessCase(item_id="q2", has_answer=True, has_explanation=True),
        ],
        export_cases=[
            ExportCase(file_path=str(path), file_role="sample_source") for path in sample_files
        ],
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Run deterministic CoursePilot sample evaluation.")
    parser.add_argument(
        "--sample-dir",
        default="data/coursepilot_sample",
        help="Directory containing sample course files.",
    )
    parser.add_argument(
        "--output",
        default="",
        help="Optional JSON output path.",
    )
    args = parser.parse_args()

    payload = build_sample_payload(Path(args.sample_dir))
    report = CoursePilotEvaluator().evaluate(payload)
    data = report.model_dump()
    text = json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True)
    print(text)
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(text + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
