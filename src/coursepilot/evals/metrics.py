from pathlib import Path

from pydantic import BaseModel, Field


class RetrievalCase(BaseModel):
    query: str
    expected_chunk_ids: list[str] = Field(min_length=1)
    retrieved_chunk_ids: list[str] = Field(default_factory=list)


class CitationCase(BaseModel):
    item_id: str
    citation_chunk_ids: list[str] = Field(default_factory=list)


class SchemaCase(BaseModel):
    item_id: str
    schema_valid: bool


class QuestionCountCase(BaseModel):
    expected_counts: dict[str, int]
    actual_counts: dict[str, int]


class AnswerCompletenessCase(BaseModel):
    item_id: str
    has_answer: bool
    has_explanation: bool


class ExportCase(BaseModel):
    file_path: str
    file_role: str


class CoursePilotEvalInput(BaseModel):
    retrieval_cases: list[RetrievalCase] = Field(default_factory=list)
    citation_cases: list[CitationCase] = Field(default_factory=list)
    schema_cases: list[SchemaCase] = Field(default_factory=list)
    question_count_cases: list[QuestionCountCase] = Field(default_factory=list)
    duplicate_rate: float = 0.0
    answer_cases: list[AnswerCompletenessCase] = Field(default_factory=list)
    export_cases: list[ExportCase] = Field(default_factory=list)


class CoursePilotEvalReport(BaseModel):
    rag_recall_at_k: float
    rag_hit_at_k: float
    rag_mrr: float
    rag_ndcg: float
    context_precision: float
    citation_coverage: float
    schema_pass_rate: float
    question_count_accuracy: float
    duplicate_rate: float
    answer_completeness: float
    export_success_rate: float


class CoursePilotEvaluator:
    def evaluate(self, payload: CoursePilotEvalInput) -> CoursePilotEvalReport:
        return CoursePilotEvalReport(
            rag_recall_at_k=self.rag_recall_at_k(payload.retrieval_cases),
            rag_hit_at_k=self.rag_hit_at_k(payload.retrieval_cases),
            rag_mrr=self.rag_mrr(payload.retrieval_cases),
            rag_ndcg=self.rag_ndcg(payload.retrieval_cases),
            context_precision=self.context_precision(payload.retrieval_cases),
            citation_coverage=self.citation_coverage(payload.citation_cases),
            schema_pass_rate=self.schema_pass_rate(payload.schema_cases),
            question_count_accuracy=self.question_count_accuracy(payload.question_count_cases),
            duplicate_rate=payload.duplicate_rate,
            answer_completeness=self.answer_completeness(payload.answer_cases),
            export_success_rate=self.export_success_rate(payload.export_cases),
        )

    def rag_recall_at_k(self, cases: list[RetrievalCase]) -> float:
        if not cases:
            return 0.0
        scores = []
        for case in cases:
            expected = set(case.expected_chunk_ids)
            retrieved = set(case.retrieved_chunk_ids)
            scores.append(len(expected & retrieved) / len(expected))
        return _mean(scores)

    def rag_hit_at_k(self, cases: list[RetrievalCase]) -> float:
        if not cases:
            return 0.0
        scores = []
        for case in cases:
            expected = set(case.expected_chunk_ids)
            retrieved = set(case.retrieved_chunk_ids)
            scores.append(1.0 if expected & retrieved else 0.0)
        return _mean(scores)

    def rag_mrr(self, cases: list[RetrievalCase]) -> float:
        if not cases:
            return 0.0
        reciprocal_ranks = []
        for case in cases:
            expected = set(case.expected_chunk_ids)
            rank = next(
                (
                    index
                    for index, chunk_id in enumerate(case.retrieved_chunk_ids, start=1)
                    if chunk_id in expected
                ),
                None,
            )
            reciprocal_ranks.append(0.0 if rank is None else 1.0 / rank)
        return _mean(reciprocal_ranks)

    def rag_ndcg(self, cases: list[RetrievalCase]) -> float:
        if not cases:
            return 0.0
        scores = []
        for case in cases:
            expected = set(case.expected_chunk_ids)
            dcg = 0.0
            for index, chunk_id in enumerate(case.retrieved_chunk_ids, start=1):
                if chunk_id in expected:
                    dcg += 1.0 / _log2(index + 1)
            ideal_hits = min(len(expected), len(case.retrieved_chunk_ids))
            idcg = sum(1.0 / _log2(index + 1) for index in range(1, ideal_hits + 1))
            scores.append(0.0 if idcg == 0 else dcg / idcg)
        return _mean(scores)

    def context_precision(self, cases: list[RetrievalCase]) -> float:
        if not cases:
            return 0.0
        scores = []
        for case in cases:
            if not case.retrieved_chunk_ids:
                scores.append(0.0)
                continue
            expected = set(case.expected_chunk_ids)
            retrieved = set(case.retrieved_chunk_ids)
            scores.append(len(expected & retrieved) / len(retrieved))
        return _mean(scores)

    def citation_coverage(self, cases: list[CitationCase]) -> float:
        if not cases:
            return 0.0
        cited = sum(1 for case in cases if case.citation_chunk_ids)
        return cited / len(cases)

    def schema_pass_rate(self, cases: list[SchemaCase]) -> float:
        if not cases:
            return 0.0
        passed = sum(1 for case in cases if case.schema_valid)
        return passed / len(cases)

    def question_count_accuracy(self, cases: list[QuestionCountCase]) -> float:
        if not cases:
            return 0.0
        scores = []
        for case in cases:
            question_types = set(case.expected_counts) | set(case.actual_counts)
            if not question_types:
                scores.append(0.0)
                continue
            matched = sum(
                1
                for question_type in question_types
                if case.expected_counts.get(question_type, 0)
                == case.actual_counts.get(question_type, 0)
            )
            scores.append(matched / len(question_types))
        return _mean(scores)

    def answer_completeness(self, cases: list[AnswerCompletenessCase]) -> float:
        if not cases:
            return 0.0
        complete = sum(1 for case in cases if case.has_answer and case.has_explanation)
        return complete / len(cases)

    def export_success_rate(self, cases: list[ExportCase]) -> float:
        if not cases:
            return 0.0
        successful = 0
        for case in cases:
            path = Path(case.file_path)
            if path.exists() and path.is_file() and path.stat().st_size > 0:
                successful += 1
        return successful / len(cases)


def _mean(values: list[float]) -> float:
    if not values:
        return 0.0
    return sum(values) / len(values)


def _log2(value: int) -> float:
    import math

    return math.log2(value)
