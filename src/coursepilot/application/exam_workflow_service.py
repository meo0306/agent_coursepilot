from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from coursepilot.domain.common import canonical_sha256
from coursepilot.domain.exam import (
    ExamArtifact,
    ExamBlueprintV2,
    ExamGlobalReport,
    ExamQuestion,
    QuestionBatchPlan,
    QuestionBatchResult,
    batch_job_id,
)
from coursepilot.llm import CoursePilotLLMBudgetExceeded
from coursepilot.repair.exam import ExamRepairPlanner, build_exam_conflict_graph
from coursepilot.validation.exam import validate_exam_global


class ExamWorkflowError(ValueError):
    pass


QuestionGenerator = Callable[[QuestionBatchPlan, ExamBlueprintV2], Awaitable[list[ExamQuestion]]]
QuestionRepairer = Callable[
    [ExamQuestion, list[str], list[ExamQuestion], ExamBlueprintV2],
    Awaitable[ExamQuestion],
]


@dataclass(frozen=True)
class BatchExecution:
    result: QuestionBatchResult
    reused: bool = False


class ExamWorkflowService:
    """Deterministic orchestration core for P15; persistence and HTTP stay outside it."""

    def __init__(self, *, max_concurrency: int = 3) -> None:
        self.max_concurrency = max(1, min(max_concurrency, 8))

    async def generate_batches(
        self,
        blueprint: ExamBlueprintV2,
        generator: QuestionGenerator,
        *,
        completed: dict[str, QuestionBatchResult] | None = None,
    ) -> list[QuestionBatchResult]:
        if not blueprint.content_hash:
            blueprint = blueprint.with_hash()
        completed = completed or {}
        semaphore = asyncio.Semaphore(min(self.max_concurrency, blueprint.max_concurrency))

        async def run(batch: QuestionBatchPlan) -> QuestionBatchResult:
            job_id = batch_job_id(blueprint.task_id, blueprint.stable_hash(), batch.batch_id)
            fingerprint = _batch_fingerprint(blueprint, batch)
            cached = completed.get(batch.batch_id)
            if (
                cached is not None
                and cached.status == "succeeded"
                and cached.fingerprint == fingerprint
            ):
                return cached
            async with semaphore:
                try:
                    questions = await generator(batch, blueprint)
                except CoursePilotLLMBudgetExceeded:
                    raise
                except Exception as exc:
                    return QuestionBatchResult(
                        batch_id=batch.batch_id,
                        job_id=job_id,
                        fingerprint=fingerprint,
                        status="failed",
                        issue_codes=[f"BATCH_GENERATION_FAILED:{type(exc).__name__}"],
                    )
            expected = set(batch.slot_ids)
            if {question.slot_id for question in questions} != expected:
                return QuestionBatchResult(
                    batch_id=batch.batch_id,
                    job_id=job_id,
                    fingerprint=fingerprint,
                    status="needs_review",
                    questions=questions,
                    issue_codes=["BATCH_SLOT_MISMATCH"],
                )
            return QuestionBatchResult(
                batch_id=batch.batch_id,
                job_id=job_id,
                fingerprint=fingerprint,
                status="succeeded",
                questions=questions,
            )

        results = await asyncio.gather(*(run(batch) for batch in blueprint.batches))
        return sorted(
            results,
            key=lambda result: next(
                batch.ordinal for batch in blueprint.batches if batch.batch_id == result.batch_id
            ),
        )

    async def build_artifact(
        self,
        blueprint: ExamBlueprintV2,
        generator: QuestionGenerator,
        *,
        completed: dict[str, QuestionBatchResult] | None = None,
        resolvable_evidence_ids: set[str] | None = None,
    ) -> tuple[ExamArtifact, ExamGlobalReport, list[BatchExecution]]:
        if not blueprint.content_hash:
            blueprint = blueprint.with_hash()
        results = await self.generate_batches(blueprint, generator, completed=completed)
        questions: list[ExamQuestion] = []
        for result in results:
            if result.status != "succeeded":
                continue
            questions.extend(result.questions)
        questions.sort(
            key=lambda question: next(
                i for i, slot in enumerate(blueprint.slots) if slot.slot_id == question.slot_id
            )
        )
        questions = [
            question.model_copy(update={"question_number": index})
            for index, question in enumerate(questions, 1)
        ]
        artifact = ExamArtifact(
            task_id=blueprint.task_id,
            course_id=blueprint.course_id,
            blueprint=blueprint,
            questions=questions,
            blueprint_approved=True,
        )
        report = validate_exam_global(
            blueprint, questions, resolvable_evidence_ids=resolvable_evidence_ids
        )
        return artifact, report, [BatchExecution(result=item) for item in results]

    async def repair_global_issues(
        self,
        blueprint: ExamBlueprintV2,
        artifact: ExamArtifact,
        report: ExamGlobalReport,
        repairer: QuestionRepairer,
        *,
        max_repairs: int = 4,
        resolvable_evidence_ids: set[str] | None = None,
    ) -> tuple[ExamArtifact, ExamGlobalReport, list[str]]:
        """Regenerate only questions selected by the P13-bounded RepairPlan.

        Identity, score, difficulty, grounding references and Blueprint order
        are retained by this service even if a model tries to change them.
        Every target is repaired at most once and the whole exam is revalidated
        after each accepted replacement.
        """
        questions = list(artifact.questions)
        repair_events: list[str] = []
        repaired_once: set[str] = set()
        current_report = report
        while len(repaired_once) < max_repairs and not current_report.passed:
            planner = ExamRepairPlanner(max_model_calls=max_repairs - len(repaired_once))
            plan = planner.plan(
                artifact_id=artifact.task_id,
                artifact_version=artifact.blueprint.stable_hash(),
                report=current_report,
                questions=questions,
                excluded_question_ids=repaired_once,
            )
            action = next(
                (
                    candidate
                    for candidate in plan.actions
                    if candidate.target_scope.startswith("$.questions[")
                    and questions[
                        int(candidate.target_scope.removeprefix("$.questions[").removesuffix("]"))
                    ].question_id
                    not in repaired_once
                ),
                None,
            )
            if action is None:
                break
            try:
                index = int(action.target_scope.removeprefix("$.questions[").removesuffix("]"))
            except ValueError:
                continue
            if index < 0 or index >= len(questions):
                continue
            original = questions[index]
            if original.question_id in repaired_once:
                continue
            repaired_once.add(original.question_id)
            try:
                candidate = await repairer(original, action.issue_ids, list(questions), blueprint)
            except CoursePilotLLMBudgetExceeded:
                raise
            except Exception as exc:
                repair_events.append(f"FAILED:{original.question_id}:{type(exc).__name__}")
                continue
            if candidate.slot_id != original.slot_id:
                repair_events.append(f"REJECTED_SLOT_CHANGE:{original.question_id}")
                continue
            if (
                candidate.stimulus == original.stimulus
                and candidate.stem == original.stem
                and candidate.options == original.options
                and candidate.option_assessments == original.option_assessments
                and candidate.answer == original.answer
                and candidate.explanation == original.explanation
            ):
                repair_events.append(f"NOOP:{original.question_id}")
                continue
            questions[index] = original.model_copy(
                update={
                    "stimulus": candidate.stimulus,
                    "stem": candidate.stem,
                    "options": candidate.options,
                    "option_assessments": candidate.option_assessments,
                    "answer": candidate.answer,
                    "explanation": candidate.explanation,
                }
            )
            repair_events.append(f"REPAIRED:{original.question_id}")
            current_report = validate_exam_global(
                blueprint,
                questions,
                resolvable_evidence_ids=resolvable_evidence_ids,
            )
            if current_report.passed:
                break
        repaired_artifact = artifact.model_copy(update={"questions": questions})
        return repaired_artifact, current_report, repair_events

    async def regenerate_conflicts(
        self,
        blueprint: ExamBlueprintV2,
        artifact: ExamArtifact,
        report: ExamGlobalReport,
        regenerator: QuestionRepairer,
        *,
        max_regenerations: int,
        resolvable_evidence_ids: set[str] | None = None,
    ) -> tuple[ExamArtifact, ExamGlobalReport, list[str]]:
        """Run one immutable whole-exam conflict round without rewriting the exam.

        Targets are selected from the initial global report.  A target is
        regenerated at most once; newly introduced conflicts are reported but
        never start another tuning loop.
        """

        questions = list(artifact.questions)
        graph = build_exam_conflict_graph(report, questions)
        by_id = {question.question_id: index for index, question in enumerate(questions)}
        issue_ids: dict[str, list[str]] = {}
        for conflict in graph.conflicts:
            issue_ids.setdefault(conflict.target_question_id, []).extend(conflict.issue_codes)
        target_ids = graph.target_question_ids[: max(0, max_regenerations)]
        events: list[str] = []
        for target_id in target_ids:
            index = by_id[target_id]
            original = questions[index]
            try:
                candidate = await regenerator(
                    original,
                    sorted(set(issue_ids[target_id])),
                    list(questions),
                    blueprint,
                )
            except CoursePilotLLMBudgetExceeded:
                raise
            except Exception as exc:
                events.append(f"FAILED:{target_id}:{type(exc).__name__}")
                continue
            if candidate.slot_id != original.slot_id:
                events.append(f"REJECTED_SLOT_CHANGE:{target_id}")
                continue
            if candidate.question_id != original.question_id:
                events.append(f"REJECTED_QUESTION_ID_CHANGE:{target_id}")
                continue
            questions[index] = original.model_copy(
                update={
                    "stimulus": candidate.stimulus,
                    "stem": candidate.stem,
                    "options": candidate.options,
                    "option_assessments": candidate.option_assessments,
                    "answer": candidate.answer,
                    "explanation": candidate.explanation,
                }
            )
            events.append(f"REGENERATED:{target_id}")

        final_report = validate_exam_global(
            blueprint,
            questions,
            resolvable_evidence_ids=resolvable_evidence_ids,
        )
        return artifact.model_copy(update={"questions": questions}), final_report, events


def _batch_fingerprint(blueprint: ExamBlueprintV2, batch: QuestionBatchPlan) -> str:
    import hashlib

    payload = f"{blueprint.stable_hash()}:{canonical_sha256(batch.model_dump(mode='json'))}"
    return hashlib.sha256(payload.encode()).hexdigest()
