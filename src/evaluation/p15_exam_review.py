"""Prepare the blinded CP-B0/P15 exam owner-review package.

The module deliberately separates four operations:

* ``preflight`` estimates the legacy CP-B0 call budget without network access;
* ``baseline`` runs the legacy question generator under the approved fixed blueprint;
* ``package`` combines the legacy output with the existing cached P15 P3 output;
* ``finalize`` validates and summarizes the human decisions without approving them.
"""

from __future__ import annotations

import argparse
import html
import json
import math
import os
import random
import statistics
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from agents.coursepilot.nodes.exam_nodes import (
    generate_exam_questions,
    validate_exam_questions,
)
from agents.coursepilot.states.exam_state import ExamGraphState
from coursepilot.domain.common import canonical_sha256
from coursepilot.llm import (
    CoursePilotLLMBudgetExceeded,
    collect_coursepilot_llm_metadata,
    summarize_llm_invocations,
)
from coursepilot.schemas.exam_schema import (
    ExamBlueprintContent,
    ExamGenerationParams,
    QuestionGroupPlan,
)
from coursepilot.schemas.kb_schema import KBSearchResult
from coursepilot.schemas.question_schema import QuestionSet
from evaluation.p14_lesson_eval import _strict_provider_settings
from evaluation.p15_exam_eval import DATASET, P15ResponseCheckpoint

INPUT_RATE_CNY_PER_M = 1.0
OUTPUT_RATE_CNY_PER_M = 2.0
DEFAULT_P15_STATE = Path("storage_eval/p15_provider_smoke/checkpoint/state.json")
DEFAULT_P15_REPORT = Path("storage_eval/p15_provider_smoke/pilot_report.json")

RUBRIC = {
    "E-H1": "Blueprint 合理性",
    "E-H2": "题干质量",
    "E-H3": "答案正确性",
    "E-H4": "干扰项质量",
    "E-H5": "难度匹配",
    "E-H6": "覆盖与平衡",
    "E-H7": "重复、互相提示与答案泄漏",
    "E-H8": "解析质量",
    "E-H9": "教材证据支持",
    "E-H10": "教师实际可用性",
}
QUESTION_STATUSES = {"accepted", "minor_edit", "major_edit", "reject"}


@dataclass(frozen=True)
class ReviewBudgetLimits:
    """The exact owner-authorized limits for the legacy baseline run."""

    max_cost_cny: float
    max_input_tokens: int
    max_output_tokens: int
    max_requests: int

    def __post_init__(self) -> None:
        if self.max_cost_cny <= 0:
            raise ValueError("max_cost_cny must be positive")
        if min(self.max_input_tokens, self.max_output_tokens, self.max_requests) <= 0:
            raise ValueError("token and request limits must be positive")


@dataclass(frozen=True)
class PriorProviderUsage:
    """Already consumed usage that counts against the cumulative authorization."""

    provider_requests: int = 0
    input_tokens: int = 0
    output_tokens: int = 0

    @property
    def estimated_cost_cny(self) -> float:
        return _usage_cost(self.input_tokens, self.output_tokens)


class LegacyBaselineCheckpoint(P15ResponseCheckpoint):
    """P15 checkpoint with limits bound to the separate CP-B0 authorization."""

    def __init__(
        self,
        root: Path,
        *,
        resume: bool,
        limits: ReviewBudgetLimits,
        prior_usage: PriorProviderUsage,
    ) -> None:
        self.limits = limits
        self.prior_usage = prior_usage
        super().__init__(root, resume=resume)
        state = json.loads(self.state_path.read_text(encoding="utf-8"))
        expected = asdict(limits)
        existing = state.get("legacy_baseline_budget_limits")
        if existing is not None and existing != expected:
            if any(expected[key] < existing[key] for key in expected):
                raise RuntimeError("P15 legacy baseline limits cannot decrease on resume")
            state.setdefault("legacy_baseline_budget_limit_revisions", []).append(
                {
                    "previous": existing,
                    "current": expected,
                    "revised_at": datetime.now(UTC).isoformat(),
                }
            )
            state["legacy_baseline_budget_limits"] = expected
        if existing is None:
            state["legacy_baseline_budget_limits"] = expected
        expected_prior = asdict(prior_usage)
        existing_prior = state.get("legacy_baseline_prior_usage")
        if existing_prior is not None and existing_prior != expected_prior:
            raise RuntimeError("P15 legacy baseline prior usage differs from checkpoint")
        if existing_prior is None:
            state["legacy_baseline_prior_usage"] = expected_prior
        self._atomic_write(self.state_path, state)

    def authorize_request(
        self,
        *,
        request_sha256: str,
        prompt_name: str,
        profile_id: str,
        estimated_input_tokens: int,
        configured_max_output_tokens: int,
    ) -> None:
        with self._lock:
            state = json.loads(self.state_path.read_text(encoding="utf-8"))
            reservations = state.setdefault("budget_reservations", {})
            if request_sha256 in reservations:
                raise CoursePilotLLMBudgetExceeded(
                    "P15_CP_B0_AMBIGUOUS_REQUEST_PENDING_RECONCILIATION"
                )
            input_tokens, output_tokens, provider_requests = self._provider_usage_totals_unlocked()
            input_tokens += self.prior_usage.input_tokens
            output_tokens += self.prior_usage.output_tokens
            provider_requests += self.prior_usage.provider_requests
            reserved_input = sum(
                int(item["estimated_input_tokens"]) for item in reservations.values()
            )
            reserved_output = sum(
                int(item["configured_max_output_tokens"]) for item in reservations.values()
            )
            projected_input = input_tokens + reserved_input + estimated_input_tokens
            projected_output = output_tokens + reserved_output + configured_max_output_tokens
            projected_requests = provider_requests + len(reservations) + 1
            projected_cost = _usage_cost(projected_input, projected_output)
            if (
                projected_requests > self.limits.max_requests
                or projected_input > self.limits.max_input_tokens
                or projected_output > self.limits.max_output_tokens
                or projected_cost > self.limits.max_cost_cny
            ):
                raise CoursePilotLLMBudgetExceeded("P15_CP_B0_PROVIDER_BUDGET_CAP_EXCEEDED")
            reservations[request_sha256] = {
                "prompt_name": prompt_name,
                "profile_id": profile_id,
                "estimated_input_tokens": estimated_input_tokens,
                "configured_max_output_tokens": configured_max_output_tokens,
                "authorized_at": datetime.now(UTC).isoformat(),
            }
            state["updated_at"] = datetime.now(UTC).isoformat()
            self._atomic_write(self.state_path, state)

    def load_case(self, case_id: str) -> dict[str, Any] | None:
        state = json.loads(self.state_path.read_text(encoding="utf-8"))
        value = state.get("cases", {}).get(f"cp_b0_fixed_blueprint:{case_id}")
        return dict(value) if isinstance(value, dict) else None

    def cumulative_provider_usage_totals(self) -> tuple[int, int, int]:
        input_tokens, output_tokens, requests = self.provider_usage_totals()
        return (
            input_tokens + self.prior_usage.input_tokens,
            output_tokens + self.prior_usage.output_tokens,
            requests + self.prior_usage.provider_requests,
        )

    def reconcile_parseable_failures(self) -> int:
        """Recover billed structured output that the previous schema rejected.

        The provider payload is already present in the local invocation audit.
        Re-validating it locally prevents an unnecessary second paid request.
        Only exact ``QuestionSet`` structured-parse failures are eligible.
        """
        if not self.audit_path.exists():
            return 0
        recovered = 0
        for line in self.audit_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            invocation = json.loads(line)
            request_sha256 = invocation.get("request_sha256")
            if (
                invocation.get("status") != "failed"
                or invocation.get("error_category") != "structured_parse_error"
                or invocation.get("schema") != "QuestionSet"
                or not isinstance(request_sha256, str)
                or self.load(request_sha256) is not None
            ):
                continue
            attempts = invocation.get("attempts")
            if not isinstance(attempts, list) or not attempts:
                continue
            final_attempt = attempts[-1]
            if not isinstance(final_attempt, dict):
                continue
            error_message = final_attempt.get("error_message")
            if not isinstance(error_message, str) or " completion " not in error_message:
                continue
            raw_completion = error_message.split(" completion ", 1)[1].split(". Got:", 1)[0]
            try:
                result = QuestionSet.model_validate(json.loads(raw_completion))
            except (json.JSONDecodeError, ValueError):
                continue
            usage = final_attempt.get("usage")
            self.save(
                request_sha256,
                {
                    "request_sha256": request_sha256,
                    "prompt_name": invocation.get("prompt_name"),
                    "prompt_sha256": invocation.get("prompt_sha256"),
                    "profile_id": invocation.get("profile_id"),
                    "schema": "QuestionSet",
                    "result": result.model_dump(mode="json"),
                    "usage": usage if isinstance(usage, dict) else None,
                    "provider_request_id": invocation.get("provider_request_id"),
                    "reconciled_from_billed_parse_failure": True,
                },
            )
            recovered += 1
        return recovered


def _atomic_write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    os.replace(temporary, path)


def _usage_cost(input_tokens: int, output_tokens: int) -> float:
    return (input_tokens * INPUT_RATE_CNY_PER_M + output_tokens * OUTPUT_RATE_CNY_PER_M) / 1_000_000


def _prior_usage_from_report(path: Path) -> PriorProviderUsage:
    payload = json.loads(path.read_text(encoding="utf-8"))
    actual = payload.get("actual")
    if not isinstance(actual, dict):
        raise ValueError("prior baseline report has no actual usage")
    return PriorProviderUsage(
        provider_requests=int(actual.get("provider_requests", 0)),
        input_tokens=int(actual.get("input_tokens", 0)),
        output_tokens=int(actual.get("output_tokens", 0)),
    )


def _load_dataset(repository_root: Path) -> dict[str, Any]:
    payload = json.loads((repository_root / DATASET).read_text(encoding="utf-8"))
    if len(payload.get("cases", [])) != 3:
        raise ValueError("P15 review requires the approved three CP-DS2 cases")
    return payload


def _case_targets(case: dict[str, Any], targets: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    return [targets[target_id] for target_id in case["blueprint"]["target_ids"]]


def _legacy_context(
    case: dict[str, Any], targets: dict[str, dict[str, Any]]
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for target in _case_targets(case, targets):
        evidence = target["primary_evidence"]
        evidence_id = evidence["evidence_id"]
        if evidence_id in seen:
            continue
        seen.add(evidence_id)
        rows.append(
            KBSearchResult(
                chunk_id=evidence_id,
                course_id=evidence["course_id"],
                document_id=evidence["source_document_id"],
                source_type="primary_source",
                chapter=case["blueprint"]["chapter_range"],
                section=None,
                page=evidence.get("page_start"),
                content=evidence["gold_text"],
                score=1.0,
            ).model_dump(mode="json")
        )
    return rows


def _legacy_exam_params(case: dict[str, Any]) -> dict[str, Any]:
    blueprint = case["blueprint"]
    generation_type = "homework" if "assignment" in blueprint["template_id"] else "exam"
    params = ExamGenerationParams(
        chapter_range=blueprint["chapter_range"],
        generation_type=generation_type,
        total_score=blueprint["required_total_score"],
        question_counts=blueprint["question_counts"],
        score_per_question=blueprint["score_per_question"],
        difficulty_distribution=blueprint["difficulty_distribution"],
        include_answer=True,
        include_explanation=True,
        include_answer_sheet=True,
        additional_requirements=(
            "Use only the supplied course evidence; preserve the requested question counts, "
            "scores and difficulty distribution."
        ),
    ).model_dump(mode="json")
    params["course_name"] = blueprint["course_id"]
    return params


def estimate_legacy_baseline(repository_root: Path) -> dict[str, Any]:
    """Estimate the fixed-blueprint legacy generator without network access."""
    raw = _load_dataset(repository_root)
    targets = {item["target_id"]: item for item in raw["targets"]}
    estimated_input = 0
    planned_questions = 0
    for case in raw["cases"]:
        contexts = _legacy_context(case, targets)
        params = _legacy_exam_params(case)
        planned_questions += sum(case["blueprint"]["question_counts"].values())
        base_chars = len(
            json.dumps(
                {"exam_params": params, "retrieved_contexts": contexts},
                ensure_ascii=False,
            )
        )
        # Four legacy group calls carry the approved blueprint/context plus an
        # increasing list of earlier questions. Planner and whole-exam repair
        # are intentionally excluded from this controlled comparison.
        group_tokens = math.ceil(base_chars / 3 * 1.65)
        estimated_input += 4 * group_tokens
    base_requests = 12
    expected_output = planned_questions * 1050
    maximum_output = base_requests * 8192
    expected_cost = _usage_cost(estimated_input, expected_output)
    conservative_cost = _usage_cost(estimated_input, maximum_output)
    return {
        "mode": "preflight",
        "external_calls_made": 0,
        "case_count": 3,
        "planned_questions": planned_questions,
        "base_requests": base_requests,
        "conditional_repair_requests": 0,
        "maximum_requests": base_requests,
        "input_tokens_estimate_with_margin": estimated_input,
        "expected_output_tokens": expected_output,
        "configured_maximum_output_tokens": maximum_output,
        "expected_cost_cny": round(expected_cost, 6),
        "configured_maximum_cost_cny": round(conservative_cost, 6),
        "pricing": {
            "input_cny_per_million": INPUT_RATE_CNY_PER_M,
            "output_cny_per_million": OUTPUT_RATE_CNY_PER_M,
        },
        "authorization_required": True,
    }


def _fixed_legacy_blueprint(
    case: dict[str, Any], targets: dict[str, dict[str, Any]]
) -> ExamBlueprintContent:
    """Map the approved CP-DS2 blueprint into the legacy generator contract."""
    raw = case["blueprint"]
    contexts = [KBSearchResult.model_validate(item) for item in _legacy_context(case, targets)]
    groups: list[QuestionGroupPlan] = []
    all_points: list[str] = []
    target_ids_by_type: dict[str, list[str]] = {}
    for batch in raw["batch_plan"]:
        target_ids_by_type.setdefault(batch["question_type"], []).extend(batch["target_ids"])
    for question_type, target_ids in target_ids_by_type.items():
        points = [
            str(targets[target_id]["knowledge_point"]["canonical_name"]) for target_id in target_ids
        ]
        all_points.extend(points)
        count = int(raw["question_counts"][question_type])
        score_each = int(raw["score_per_question"][question_type])
        groups.append(
            QuestionGroupPlan(
                question_type=question_type,
                count=count,
                score_each=score_each,
                total_score=count * score_each,
                knowledge_points=list(dict.fromkeys(points)),
                difficulty=max(raw["difficulty_counts"].items(), key=lambda item: int(item[1]))[0],
            )
        )
    return ExamBlueprintContent(
        course_name=raw["course_id"],
        chapter_range=raw["chapter_range"],
        generation_type=("homework" if "assignment" in raw["template_id"] else "exam"),
        total_score=int(raw["required_total_score"]),
        question_groups=groups,
        knowledge_points=list(dict.fromkeys(all_points)),
        retrieved_contexts=contexts,
    )


def _legacy_case(case: dict[str, Any], targets: dict[str, dict[str, Any]]) -> dict[str, Any]:
    state: ExamGraphState = {
        "course_id": case["blueprint"]["course_id"],
        "workflow_phase": "questions",
        "blueprint_id": f"cp-b0:{case['record_id']}",
        "exam_params": _legacy_exam_params(case),
        "retrieved_contexts": _legacy_context(case, targets),
        "exam_blueprint": _fixed_legacy_blueprint(case, targets).model_dump(mode="json"),
    }
    state.update(generate_exam_questions(state))
    state.update(validate_exam_questions(state))
    return {
        "case_id": case["record_id"],
        "blueprint": state.get("exam_blueprint"),
        "questions": state.get("questions", []),
        "validation_report": state.get("validation_report", {}),
    }


def run_legacy_baseline(
    repository_root: Path,
    *,
    output_dir: Path,
    limits: ReviewBudgetLimits,
    resume: bool,
    external_data_authorized: bool,
    prior_usage: PriorProviderUsage | None = None,
) -> dict[str, Any]:
    """Run the legacy generator with the approved blueprint and no repair loop."""
    if not external_data_authorized:
        raise PermissionError("P15 CP-B0 external-data authorization is required")
    raw = _load_dataset(repository_root)
    targets = {item["target_id"]: item for item in raw["targets"]}
    accounted_prior = prior_usage or PriorProviderUsage()
    checkpoint = LegacyBaselineCheckpoint(
        output_dir / "checkpoint",
        resume=resume,
        limits=limits,
        prior_usage=accounted_prior,
    )
    reconciled_response_count = checkpoint.reconcile_parseable_failures()
    cases: list[dict[str, Any]] = []
    failure: dict[str, Any] | None = None
    with _strict_provider_settings(repository_root):
        for case in raw["cases"]:
            cached_case = checkpoint.load_case(case["record_id"])
            if cached_case is not None:
                cases.append(cached_case)
                continue
            collector = None
            try:
                with collect_coursepilot_llm_metadata(
                    thread_id=f"p15-review-cp-b0:{case['record_id']}",
                    checkpoint=checkpoint,
                ) as collector:
                    result = _legacy_case(case, targets)
                result["usage"] = summarize_llm_invocations(collector.invocations)
                cases.append(result)
                checkpoint.save_case(case["record_id"], result, experiment="cp_b0_fixed_blueprint")
            except Exception as exc:
                failure = {
                    "case_id": case["record_id"],
                    "error_category": type(exc).__name__,
                    "usage": summarize_llm_invocations(
                        collector.invocations if collector is not None else []
                    ),
                }
                break
    run_input, run_output, run_requests = checkpoint.provider_usage_totals()
    input_tokens, output_tokens, requests = checkpoint.cumulative_provider_usage_totals()
    cost = _usage_cost(input_tokens, output_tokens)
    report = {
        "schema_version": "coursepilot.p15-cp-b0-baseline.v1",
        "comparison_contract": "fixed_approved_blueprint_legacy_question_generator",
        "status": "completed" if failure is None and len(cases) == 3 else "failed",
        "source_dataset": str(DATASET),
        "test_access": False,
        "fallback_count": sum(int(case["usage"].get("fallback_count", 0)) for case in cases),
        "model_switch_count": 0,
        "reconciled_response_count": reconciled_response_count,
        "cases": cases,
        "failure": failure,
        "actual": {
            "provider_requests": requests,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "estimated_cost_cny": round(cost, 6),
        },
        "prior_actual": {
            **asdict(accounted_prior),
            "estimated_cost_cny": round(accounted_prior.estimated_cost_cny, 6),
        },
        "run_actual": {
            "provider_requests": run_requests,
            "input_tokens": run_input,
            "output_tokens": run_output,
            "estimated_cost_cny": round(_usage_cost(run_input, run_output), 6),
        },
        "limits": asdict(limits),
        "hard_cap_ok": requests <= limits.max_requests
        and input_tokens <= limits.max_input_tokens
        and output_tokens <= limits.max_output_tokens
        and cost <= limits.max_cost_cny,
    }
    _atomic_write_json(output_dir / "baseline_report.json", report)
    checkpoint.finish(report)
    return report


def _load_p15_cases(state_path: Path) -> dict[str, dict[str, Any]]:
    state = json.loads(state_path.read_text(encoding="utf-8"))
    cases = {
        key.removeprefix("p3:"): value
        for key, value in state.get("cases", {}).items()
        if key.startswith("p3:")
    }
    if len(cases) != 3 or any(item.get("status") != "completed" for item in cases.values()):
        raise ValueError("P15 P3 checkpoint does not contain three completed cases")
    return cases


def _normalize_legacy_question(question: dict[str, Any], ordinal: int) -> dict[str, Any]:
    return {
        "ordinal": ordinal,
        "question_type": question["question_type"],
        "difficulty": question["difficulty"],
        "score": question["score"],
        "stem": question["question_text"],
        "options": question.get("options"),
        "answer": question["correct_answer"],
        "explanation": question["explanation"],
        "knowledge_point": question["knowledge_point"],
        "citations": question.get("references", []),
    }


def _normalize_p15_question(question: dict[str, Any], ordinal: int) -> dict[str, Any]:
    return {
        "ordinal": ordinal,
        "question_type": question["question_type"],
        "difficulty": question["difficulty"],
        "score": question["score"],
        "stem": question["stem"],
        "options": question.get("options"),
        "answer": question["answer"],
        "explanation": question["explanation"],
        "knowledge_point_ids": question.get("knowledge_point_ids", []),
        "citations": question.get("evidence_ids", []),
    }


def _blinded_records(
    dataset: dict[str, Any],
    baseline: dict[str, Any],
    p15_cases: dict[str, dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    baseline_cases = {item["case_id"]: item for item in baseline["cases"]}
    dataset_cases = {item["record_id"]: item for item in dataset["cases"]}
    if set(baseline_cases) != set(p15_cases) or set(p15_cases) != set(dataset_cases):
        raise ValueError("CP-B0, P15 and CP-DS2 case identities do not match")
    records: list[dict[str, Any]] = []
    key_items: list[dict[str, Any]] = []
    rng = random.Random(1502)
    for pair_index, case_id in enumerate(sorted(p15_cases), start=1):
        order = ["cp_b0", "p15"]
        rng.shuffle(order)
        case = dataset_cases[case_id]
        for label, track in zip(("A", "B"), order, strict=True):
            blind_exam_id = f"exam-pair-{pair_index:02d}-{label}"
            if track == "cp_b0":
                source = baseline_cases[case_id]
                questions = [
                    _normalize_legacy_question(question, ordinal)
                    for ordinal, question in enumerate(source["questions"], start=1)
                ]
                blueprint = source["blueprint"]
            else:
                source = p15_cases[case_id]
                questions = [
                    _normalize_p15_question(question, ordinal)
                    for ordinal, question in enumerate(source["questions"], start=1)
                ]
                blueprint = {
                    "chapter_range": case["blueprint"]["chapter_range"],
                    "question_counts": case["blueprint"]["question_counts"],
                    "required_total_score": case["blueprint"]["required_total_score"],
                    "difficulty_distribution": case["blueprint"]["difficulty_distribution"],
                }
            blind_questions = []
            for question in questions:
                blind_question_id = f"{blind_exam_id}-q{question['ordinal']:02d}"
                blind_questions.append({"blind_question_id": blind_question_id, **question})
                key_items.append(
                    {
                        "blind_exam_id": blind_exam_id,
                        "blind_question_id": blind_question_id,
                        "case_id": case_id,
                        "track": track,
                        "question_ordinal": question["ordinal"],
                    }
                )
            records.append(
                {
                    "pair_id": f"exam-pair-{pair_index:02d}",
                    "blind_exam_id": blind_exam_id,
                    "blueprint": blueprint,
                    "questions": blind_questions,
                }
            )
    return records, {
        "schema_version": "coursepilot.p15-output-blinding-key.v1",
        "items": key_items,
    }


def build_review_package(
    repository_root: Path,
    *,
    baseline_report_path: Path,
    p15_state_path: Path,
    p15_report_path: Path,
    output_dir: Path,
) -> dict[str, Any]:
    baseline = json.loads(baseline_report_path.read_text(encoding="utf-8"))
    if baseline.get("status") != "completed" or not baseline.get("hard_cap_ok"):
        raise ValueError("P15 CP-B0 baseline is incomplete or outside its authorization")
    if baseline.get("comparison_contract") != "fixed_approved_blueprint_legacy_question_generator":
        raise ValueError("P15 CP-B0 baseline does not use the approved comparison contract")
    if baseline.get("fallback_count") != 0 or baseline.get("model_switch_count") != 0:
        raise ValueError("P15 CP-B0 baseline used a forbidden fallback or model switch")
    p15_report = json.loads(p15_report_path.read_text(encoding="utf-8"))
    if not p15_report.get("functional_gate", {}).get("all_three_cases_completed"):
        raise ValueError("P15 provider report is not functionally complete")
    dataset = _load_dataset(repository_root)
    p15_cases = _load_p15_cases(p15_state_path)
    records, blinding_key = _blinded_records(dataset, baseline, p15_cases)
    source_identity = {
        "dataset_sha256": canonical_sha256(dataset),
        "baseline_report_sha256": canonical_sha256(baseline),
        "p15_report_sha256": canonical_sha256(p15_report),
        "p15_cases_sha256": canonical_sha256(p15_cases),
        "review_records_sha256": canonical_sha256(records),
    }
    source_package_sha256 = canonical_sha256(source_identity)
    decisions = []
    for exam in records:
        for question in exam["questions"]:
            decisions.append(
                {
                    "blind_exam_id": exam["blind_exam_id"],
                    "blind_question_id": question["blind_question_id"],
                    "rubric_scores": {key: None for key in RUBRIC},
                    "edit_burden": None,
                    "critical_defect": None,
                    "question_status": None,
                    "notes": "",
                }
            )
    template = {
        "schema_version": "coursepilot.p15-human-review-decisions.v1",
        "source_package_sha256": source_package_sha256,
        "reviewer_id": "course_owner",
        "reviewed_at": None,
        "decisions": decisions,
    }
    automatic = {
        "schema_version": "coursepilot.p15-automatic-comparison.v1",
        "cp_b0": {
            "case_count": len(baseline["cases"]),
            "question_count": sum(len(item["questions"]) for item in baseline["cases"]),
            "provider_usage": baseline["actual"],
            "all_validation_passed": all(
                all(
                    item["validation_report"].get(key, False)
                    for key in (
                        "schema_valid",
                        "question_count_valid",
                        "score_valid",
                        "option_valid",
                        "answer_valid",
                        "explanation_valid",
                        "knowledge_coverage_valid",
                        "citation_valid",
                        "duplicate_valid",
                    )
                )
                for item in baseline["cases"]
            ),
        },
        "p15": {
            "case_count": len(p15_cases),
            "question_count": sum(len(item["questions"]) for item in p15_cases.values()),
            "provider_usage": p15_report["actual"],
            "all_global_validation_passed": all(
                not item["global_report"].get("errors") for item in p15_cases.values()
            ),
        },
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    _atomic_write_json(output_dir / "automatic_comparison.json", automatic)
    _atomic_write_json(output_dir / "review_items.json", records)
    _atomic_write_json(output_dir / "blinding_key.json", blinding_key)
    _atomic_write_json(output_dir / "review_decisions_template.json", template)
    (output_dir / "review.html").write_text(_review_html(records, template), encoding="utf-8")
    manifest = {
        "schema_version": "coursepilot.p15-owner-review-package.v1",
        "status": "gate_pending_owner_review",
        "source_package_sha256": source_package_sha256,
        "source_identity": source_identity,
        "blind_exam_count": len(records),
        "review_question_count": len(decisions),
        "review_page": str(output_dir / "review.html"),
        "decision_template": str(output_dir / "review_decisions_template.json"),
        "automatic_comparison": str(output_dir / "automatic_comparison.json"),
    }
    _atomic_write_json(output_dir / "package_manifest.json", manifest)
    return manifest


def _review_html(records: list[dict[str, Any]], template: dict[str, Any]) -> str:
    exams = []
    for record in records:
        question_cards = []
        for question in record["questions"]:
            blind_question_id = question["blind_question_id"]
            rubric = "".join(
                f'<label>{key} {html.escape(label)}<select data-field="rubric_scores.{key}">'
                '<option value="">--请选择--</option>'
                + "".join(f'<option value="{score}">{score}</option>' for score in range(1, 6))
                + "</select></label>"
                for key, label in RUBRIC.items()
            )
            question_cards.append(
                f'<article class="question" data-id="{blind_question_id}">'
                f"<h3>{blind_question_id} · {html.escape(question['question_type'])} · "
                f"{html.escape(question['difficulty'])} · {question['score']} 分</h3>"
                f'<div class="content"><strong>题干</strong><p>{html.escape(question["stem"])}</p>'
                f"<strong>选项</strong><pre>{html.escape(json.dumps(question.get('options'), ensure_ascii=False, indent=2))}</pre>"
                f"<strong>答案</strong><p>{html.escape(str(question['answer']))}</p>"
                f"<strong>解析</strong><p>{html.escape(question['explanation'])}</p>"
                f"<strong>引用</strong><pre>{html.escape(json.dumps(question.get('citations'), ensure_ascii=False, indent=2))}</pre></div>"
                f'<div class="grid">{rubric}'
                '<label>Edit Burden<select data-field="edit_burden"><option value="">--请选择--</option>'
                + "".join(f'<option value="{value}">{value}</option>' for value in range(5))
                + '</select></label><label>Critical Defect<select data-field="critical_defect">'
                '<option value="">--请选择--</option><option value="false">否</option>'
                '<option value="true">是</option></select></label>'
                '<label>Question Status<select data-field="question_status">'
                '<option value="">--请选择--</option><option value="accepted">accepted</option>'
                '<option value="minor_edit">minor_edit</option><option value="major_edit">major_edit</option>'
                '<option value="reject">reject</option></select></label>'
                '<label>Notes<textarea data-field="notes"></textarea></label></div></article>'
            )
        exams.append(
            f'<section class="exam"><h2>{record["pair_id"]} · 版本 {record["blind_exam_id"][-1]}</h2>'
            f"<details><summary>查看 Blueprint</summary><pre>{html.escape(json.dumps(record['blueprint'], ensure_ascii=False, indent=2))}</pre></details>"
            + "".join(question_cards)
            + "</section>"
        )
    template_json = json.dumps(template, ensure_ascii=False).replace("</", "<\\/")
    return f"""<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<title>P15 CP-B0/P15 盲化试卷审核</title><style>
body{{font-family:system-ui;margin:24px;background:#f3f5f7;color:#17202a}}.toolbar{{position:sticky;top:0;background:white;padding:12px;border:1px solid #cbd3da;z-index:4}}button{{margin-right:8px;padding:9px 14px}}.guide,.exam,.question{{background:white;border:1px solid #cbd3da;border-radius:8px;padding:16px;margin:16px 0}}.question{{background:#fbfcfd}}.content p{{white-space:pre-wrap}}pre{{white-space:pre-wrap;background:#f4f5f6;padding:10px;max-height:360px;overflow:auto}}.grid{{display:grid;grid-template-columns:repeat(2,minmax(280px,1fr));gap:10px}}label{{display:flex;justify-content:space-between;gap:10px}}select,textarea{{min-width:160px}}textarea{{min-height:48px}}#status{{font-weight:650}}@media(max-width:800px){{.grid{{grid-template-columns:1fr}}}}
</style></head><body><div class="toolbar"><button id="save" type="button">保存到本地</button><button id="download-progress" type="button">下载当前进度 JSON</button><button id="download" type="button">校验并下载最终决策 JSON</button><span id="status">0 / {len(template["decisions"])} 已完成</span></div>
<section class="guide"><h1>P15 CP-B0/P15 盲化试卷审核</h1><p>A/B 身份已隐藏。每题完成 E-H1—E-H10（1=不可用，3=基本可用但需修改，5=完整可靠）、Edit Burden（0—4）、Critical Defect 和 Question Status。严重错误、reject 或 major_edit 请在 Notes 说明。</p></section>{"".join(exams)}
<script>const KEY='coursepilot-p15-output-review-v1:{template["source_package_sha256"]}';const BASE={template_json};
function cloneBase(){{return JSON.parse(JSON.stringify(BASE));}}
function collect(){{const output=cloneBase();output.reviewed_at=new Date().toISOString();for(const d of output.decisions){{const card=document.querySelector(`[data-id="${{d.blind_question_id}}"]`);for(const el of card.querySelectorAll('[data-field]')){{const path=el.dataset.field;const raw=el.value;if(path.startsWith('rubric_scores.'))d.rubric_scores[path.split('.')[1]]=raw===''?null:Number(raw);else if(path==='edit_burden')d[path]=raw===''?null:Number(raw);else if(path==='critical_defect')d[path]=raw===''?null:raw==='true';else d[path]=raw;}}}}return output;}}
function isComplete(d){{return !Object.values(d.rubric_scores).some(v=>v===null)&&d.edit_burden!==null&&d.critical_defect!==null&&Boolean(d.question_status);}}
function updateStatus(message){{const data=collect();const done=data.decisions.filter(isComplete).length;document.getElementById('status').textContent=message||`${{done}} / ${{data.decisions.length}} 已完成`;}}
function save(){{localStorage.setItem(KEY,JSON.stringify(collect()));updateStatus('已保存到本地');}}
function restore(){{const raw=localStorage.getItem(KEY);if(!raw){{updateStatus();return;}}const data=JSON.parse(raw);for(const d of data.decisions){{const card=document.querySelector(`[data-id="${{d.blind_question_id}}"]`);if(!card)continue;for(const [key,value] of Object.entries(d.rubric_scores))card.querySelector(`[data-field="rubric_scores.${{key}}"]`).value=value??'';for(const key of ['edit_burden','critical_defect','question_status','notes'])card.querySelector(`[data-field="${{key}}"]`).value=d[key]??'';}}updateStatus('已恢复本地进度');}}
function validate(data){{for(const d of data.decisions){{if(!isComplete(d))return `请完成 ${{d.blind_question_id}} 的全部必填项`;if((d.critical_defect||d.question_status==='major_edit'||d.question_status==='reject')&&!d.notes.trim())return `请说明 ${{d.blind_question_id}} 的严重问题`;}}return null;}}
function triggerDownload(data,filename){{const blob=new Blob([JSON.stringify(data,null,2)+'\\n'],{{type:'application/json'}});const url=URL.createObjectURL(blob);const link=document.createElement('a');link.href=url;link.download=filename;document.body.appendChild(link);link.click();link.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);}}
function downloadProgress(){{const data=collect();localStorage.setItem(KEY,JSON.stringify(data));triggerDownload(data,'p15_exam_review_progress.json');updateStatus('当前进度 JSON 已下载');}}
function download(){{const data=collect();const error=validate(data);if(error){{updateStatus(error);return;}}localStorage.setItem(KEY,JSON.stringify(data));triggerDownload(data,'p15_exam_review_decisions.json');updateStatus('最终决策 JSON 已下载');}}
document.getElementById('save').addEventListener('click',save);document.getElementById('download-progress').addEventListener('click',downloadProgress);document.getElementById('download').addEventListener('click',download);document.querySelectorAll('select,textarea').forEach(el=>{{el.addEventListener('change',save);el.addEventListener('input',()=>updateStatus());}});restore();</script></body></html>"""


def _validate_decision(decision: dict[str, Any]) -> None:
    scores = decision.get("rubric_scores")
    if not isinstance(scores, dict) or set(scores) != set(RUBRIC):
        raise ValueError("P15 rubric dimensions are incomplete")
    if any(not isinstance(value, int) or not 1 <= value <= 5 for value in scores.values()):
        raise ValueError("P15 rubric scores must be integers from 1 to 5")
    if not isinstance(decision.get("edit_burden"), int) or not 0 <= decision["edit_burden"] <= 4:
        raise ValueError("P15 edit burden must be an integer from 0 to 4")
    if not isinstance(decision.get("critical_defect"), bool):
        raise ValueError("P15 critical_defect must be boolean")
    if decision.get("question_status") not in QUESTION_STATUSES:
        raise ValueError("P15 question status is invalid")
    if (
        decision["critical_defect"] or decision["question_status"] in {"major_edit", "reject"}
    ) and not str(decision.get("notes", "")).strip():
        raise ValueError("P15 serious decisions require notes")


def _track_metrics(items: list[dict[str, Any]]) -> dict[str, Any]:
    rubric_means = {
        key: round(statistics.mean(item["rubric_scores"][key] for item in items), 3)
        for key in RUBRIC
    }
    status_counts = {status: 0 for status in sorted(QUESTION_STATUSES)}
    for item in items:
        status_counts[item["question_status"]] += 1
    acceptable = status_counts["accepted"] + status_counts["minor_edit"]
    return {
        "question_count": len(items),
        "rubric_means": rubric_means,
        "overall_rubric_mean": round(statistics.mean(rubric_means.values()), 3),
        "mean_edit_burden": round(statistics.mean(item["edit_burden"] for item in items), 3),
        "critical_defect_count": sum(item["critical_defect"] for item in items),
        "question_status_counts": status_counts,
        "human_acceptable_rate": round(acceptable / len(items), 4),
    }


def finalize_decisions(
    *,
    package_manifest_path: Path,
    blinding_key_path: Path,
    decisions_path: Path,
    output_path: Path,
) -> dict[str, Any]:
    manifest = json.loads(package_manifest_path.read_text(encoding="utf-8"))
    key = json.loads(blinding_key_path.read_text(encoding="utf-8"))
    decisions = json.loads(decisions_path.read_text(encoding="utf-8"))
    if decisions.get("schema_version") != "coursepilot.p15-human-review-decisions.v1":
        raise ValueError("P15 decision schema mismatch")
    if decisions.get("source_package_sha256") != manifest.get("source_package_sha256"):
        raise ValueError("P15 decisions are not bound to this review package")
    mapping = {item["blind_question_id"]: item for item in key["items"]}
    submitted = decisions.get("decisions", [])
    submitted_ids = [item.get("blind_question_id") for item in submitted]
    if len(submitted_ids) != len(set(submitted_ids)) or set(submitted_ids) != set(mapping):
        raise ValueError("P15 decisions are incomplete or contain duplicate identities")
    tracks: dict[str, list[dict[str, Any]]] = {"cp_b0": [], "p15": []}
    unblinded: list[dict[str, Any]] = []
    for decision in submitted:
        _validate_decision(decision)
        identity = mapping[decision["blind_question_id"]]
        item = {**identity, **decision}
        tracks[identity["track"]].append(item)
        unblinded.append(item)
    metrics = {track: _track_metrics(items) for track, items in tracks.items()}
    p15_has_critical = metrics["p15"]["critical_defect_count"] > 0
    p15_has_reject = metrics["p15"]["question_status_counts"]["reject"] > 0
    p15_quality_lower = (
        metrics["p15"]["overall_rubric_mean"] < metrics["cp_b0"]["overall_rubric_mean"]
        or metrics["p15"]["human_acceptable_rate"] < metrics["cp_b0"]["human_acceptable_rate"]
    )
    result = {
        "schema_version": "coursepilot.p15-owner-review-summary.v1",
        "source_package_sha256": manifest["source_package_sha256"],
        "decision_file_sha256": canonical_sha256(decisions),
        "decision_count": len(unblinded),
        "track_metrics": metrics,
        "p15_minus_cp_b0": {
            "overall_rubric_mean": round(
                metrics["p15"]["overall_rubric_mean"] - metrics["cp_b0"]["overall_rubric_mean"],
                3,
            ),
            "human_acceptable_rate": round(
                metrics["p15"]["human_acceptable_rate"] - metrics["cp_b0"]["human_acceptable_rate"],
                4,
            ),
            "mean_edit_burden": round(
                metrics["p15"]["mean_edit_burden"] - metrics["cp_b0"]["mean_edit_burden"],
                3,
            ),
        },
        "owner_approval_required": True,
        "recommended_phase_status": (
            "gate_failed"
            if p15_has_critical or p15_has_reject
            else "completed_with_quality_debt"
            if p15_quality_lower
            else "completed"
        ),
        "unblinded_decisions": unblinded,
    }
    _atomic_write_json(output_path, result)
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--mode", choices=("preflight", "baseline", "package", "finalize"), required=True
    )
    parser.add_argument("--repository-root", type=Path, default=Path.cwd())
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--baseline-report", type=Path)
    parser.add_argument("--p15-state", type=Path, default=DEFAULT_P15_STATE)
    parser.add_argument("--p15-report", type=Path, default=DEFAULT_P15_REPORT)
    parser.add_argument("--prior-baseline-report", type=Path)
    parser.add_argument("--decisions", type=Path)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--external-data-authorized", action="store_true")
    parser.add_argument("--max-cost-cny", type=float)
    parser.add_argument("--max-input-tokens", type=int)
    parser.add_argument("--max-output-tokens", type=int)
    parser.add_argument("--max-requests", type=int)
    args = parser.parse_args()
    root = args.repository_root.resolve()
    output = args.output_dir.resolve()
    if args.mode == "preflight":
        result = estimate_legacy_baseline(root)
        _atomic_write_json(output / "preflight.json", result)
    elif args.mode == "baseline":
        required = (
            args.max_cost_cny,
            args.max_input_tokens,
            args.max_output_tokens,
            args.max_requests,
        )
        if any(value is None for value in required):
            raise ValueError("baseline mode requires all four explicit budget limits")
        limits = ReviewBudgetLimits(
            max_cost_cny=args.max_cost_cny,
            max_input_tokens=args.max_input_tokens,
            max_output_tokens=args.max_output_tokens,
            max_requests=args.max_requests,
        )
        result = run_legacy_baseline(
            root,
            output_dir=output,
            limits=limits,
            resume=args.resume,
            external_data_authorized=args.external_data_authorized,
            prior_usage=(
                _prior_usage_from_report(args.prior_baseline_report.resolve())
                if args.prior_baseline_report is not None
                else None
            ),
        )
    elif args.mode == "package":
        if args.baseline_report is None:
            raise ValueError("package mode requires --baseline-report")
        result = build_review_package(
            root,
            baseline_report_path=args.baseline_report.resolve(),
            p15_state_path=args.p15_state.resolve(),
            p15_report_path=args.p15_report.resolve(),
            output_dir=output,
        )
    else:
        if args.decisions is None:
            raise ValueError("finalize mode requires --decisions")
        result = finalize_decisions(
            package_manifest_path=output / "package_manifest.json",
            blinding_key_path=output / "blinding_key.json",
            decisions_path=args.decisions.resolve(),
            output_path=output / "owner_review_summary.json",
        )
    print(json.dumps(result, ensure_ascii=True))


if __name__ == "__main__":
    main()
