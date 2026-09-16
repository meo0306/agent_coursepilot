"""CP-DS1 Lesson pilot runner.

The default is an offline Contract Fake.  ``--mode preflight`` only estimates the
approved provider budget; ``--mode real`` is the single explicitly-authorized
comparison run and never falls back to deterministic output.
"""

from __future__ import annotations

import argparse
import json
import math
import os
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from agents.coursepilot.lesson.generator import LessonGenerator
from agents.coursepilot.lesson.validation import LessonP14Validator
from agents.coursepilot.nodes.lesson_nodes import (
    extract_knowledge_points,
    generate_lesson_design,
    plan_sessions,
    reflect_and_revise,
    validate_lesson_design,
)
from agents.coursepilot.states.lesson_state import LessonGraphState
from core.settings import settings
from coursepilot.domain.common import canonical_sha256
from coursepilot.domain.context import ContextPackageRef
from coursepilot.domain.lesson import LessonArtifact, LessonBlueprint
from coursepilot.evals.formal_schemas import CPDS1P14PilotDataset, P14FixtureBundle
from coursepilot.llm import (
    CoursePilotLLMBudgetExceeded,
    build_coursepilot_system_prompt,
    collect_coursepilot_llm_metadata,
    get_coursepilot_llm,
    summarize_llm_invocations,
)
from coursepilot.prompts.loader import load_prompt
from coursepilot.schemas.kb_schema import KBSearchResult
from courserag.contracts.common import RequestContext, ResponseMeta
from courserag.contracts.knowledge_points import (
    KnowledgePointEvidenceLink,
    KnowledgePointSnapshot,
    KnowledgePointSnapshotItem,
)

INPUT_RATE_CNY_PER_M = 1.0
OUTPUT_RATE_CNY_PER_M = 2.0
MAX_COST_CNY = 0.50
MAX_INPUT_TOKENS = 100_000
MAX_OUTPUT_TOKENS = 200_000
SMOKE_RECORD_ID = "p14-lesson-02-perceptron-lab"
SMOKE_MAX_COST_CNY = 0.03
SMOKE_MAX_OUTPUT_TOKENS = 4096
THINKING_RESERVE_MULTIPLIER = 2.25


class P14BudgetLedger:
    """Durable incremental budget for requests made after the paid smoke."""

    schema_version = "coursepilot.p14-budget-ledger.v1"

    def __init__(self, path: Path, *, resume: bool) -> None:
        self.path = path
        if path.exists():
            if not resume:
                raise RuntimeError("P14 budget ledger exists; pass --resume")
            self.document = json.loads(path.read_text(encoding="utf-8"))
            if self.document.get("schema_version") != self.schema_version:
                raise RuntimeError("P14 budget ledger schema mismatch")
            if float(self.document.get("max_cost_cny", -1)) != MAX_COST_CNY:
                raise RuntimeError("P14 budget ledger authorization mismatch")
        else:
            self.document = {
                "schema_version": self.schema_version,
                "authorized_at": datetime.now(UTC).isoformat(),
                "max_cost_cny": MAX_COST_CNY,
                "max_input_tokens": MAX_INPUT_TOKENS,
                "max_output_tokens": MAX_OUTPUT_TOKENS,
                "thinking_reserve_multiplier": THINKING_RESERVE_MULTIPLIER,
                "requests": {},
            }
            self._save()

    def authorize(
        self,
        *,
        request_sha256: str,
        prompt_name: str,
        profile_id: str,
        estimated_input_tokens: int,
        configured_max_output_tokens: int,
    ) -> None:
        requests = self.document["requests"]
        existing = requests.get(request_sha256)
        if existing is not None:
            raise CoursePilotLLMBudgetExceeded(
                "A paid P14 request has an unresolved or already-settled budget record; "
                "automatic redispatch is forbidden."
            )
        reserved_output = math.ceil(configured_max_output_tokens * THINKING_RESERVE_MULTIPLIER)
        reserved_cost = _usage_cost_cny(estimated_input_tokens, reserved_output)
        summary = self.summary()
        if summary["committed_or_reserved_cost_cny"] + reserved_cost > MAX_COST_CNY:
            self.document["status"] = "paused_budget_exhausted"
            self._save()
            raise CoursePilotLLMBudgetExceeded(
                "P14 request was not dispatched because its conservative reservation "
                "would exceed the authorized CNY 0.50 incremental cap."
            )
        if (
            summary["committed_or_reserved_input_tokens"] + estimated_input_tokens
            > MAX_INPUT_TOKENS
        ):
            self.document["status"] = "paused_input_token_cap"
            self._save()
            raise CoursePilotLLMBudgetExceeded("P14 input token cap would be exceeded")
        if summary["committed_or_reserved_output_tokens"] + reserved_output > MAX_OUTPUT_TOKENS:
            self.document["status"] = "paused_output_token_cap"
            self._save()
            raise CoursePilotLLMBudgetExceeded("P14 output token cap would be exceeded")
        requests[request_sha256] = {
            "prompt_name": prompt_name,
            "profile_id": profile_id,
            "status": "authorized_pending",
            "estimated_input_tokens": estimated_input_tokens,
            "configured_max_output_tokens": configured_max_output_tokens,
            "reserved_output_tokens": reserved_output,
            "reserved_cost_cny": round(reserved_cost, 6),
            "authorized_at": datetime.now(UTC).isoformat(),
        }
        self.document["status"] = "running"
        self._save()

    def settle(self, invocation: dict[str, Any]) -> None:
        request_sha256 = invocation.get("request_sha256")
        if not request_sha256:
            return
        request = self.document["requests"].get(request_sha256)
        if request is None or request.get("status") != "authorized_pending":
            return
        status = invocation.get("status")
        if status == "cached":
            return
        usage = invocation.get("usage") or {}
        provider_called = bool(invocation.get("provider_called"))
        if status == "success":
            input_tokens = int(usage.get("input_tokens") or 0)
            output_tokens = int(usage.get("output_tokens") or 0)
            request.update(
                {
                    "status": "settled_success",
                    "actual_input_tokens": input_tokens,
                    "actual_output_tokens": output_tokens,
                    "actual_cost_cny": round(_usage_cost_cny(input_tokens, output_tokens), 6),
                    "usage_estimated": bool(usage.get("usage_estimated")),
                    "settled_at": datetime.now(UTC).isoformat(),
                }
            )
        elif not provider_called:
            request.update(
                {
                    "status": "released_not_sent",
                    "actual_input_tokens": 0,
                    "actual_output_tokens": 0,
                    "actual_cost_cny": 0.0,
                    "settled_at": datetime.now(UTC).isoformat(),
                }
            )
        else:
            request.update(
                {
                    "status": "settled_ambiguous_reserved",
                    "actual_input_tokens": request["estimated_input_tokens"],
                    "actual_output_tokens": request["reserved_output_tokens"],
                    "actual_cost_cny": request["reserved_cost_cny"],
                    "settled_at": datetime.now(UTC).isoformat(),
                }
            )
        summary = self.summary()
        self.document["status"] = (
            "paused_budget_exhausted"
            if summary["committed_or_reserved_cost_cny"] >= MAX_COST_CNY
            else "running"
        )
        self._save()

    def summary(self) -> dict[str, Any]:
        input_tokens = 0
        output_tokens = 0
        cost = 0.0
        completed = 0
        pending = 0
        for request in self.document.get("requests", {}).values():
            status = request.get("status")
            if status == "released_not_sent":
                continue
            if status == "authorized_pending":
                pending += 1
                input_tokens += int(request["estimated_input_tokens"])
                output_tokens += int(request["reserved_output_tokens"])
                cost += float(request["reserved_cost_cny"])
            else:
                completed += 1
                input_tokens += int(request.get("actual_input_tokens", 0))
                output_tokens += int(request.get("actual_output_tokens", 0))
                cost += float(request.get("actual_cost_cny", 0.0))
        return {
            "authorized_cost_cap_cny": MAX_COST_CNY,
            "committed_or_reserved_cost_cny": round(cost, 6),
            "remaining_cost_cny": round(max(0.0, MAX_COST_CNY - cost), 6),
            "committed_or_reserved_input_tokens": input_tokens,
            "committed_or_reserved_output_tokens": output_tokens,
            "settled_request_count": completed,
            "pending_request_count": pending,
            "status": self.document.get("status", "ready"),
        }

    def mark_completed(self) -> None:
        if self.summary()["pending_request_count"]:
            raise RuntimeError("P14 budget cannot complete with a pending request")
        self.document["status"] = "completed"
        self.document["completed_at"] = datetime.now(UTC).isoformat()
        self._save()

    def _save(self) -> None:
        _atomic_write_json(self.path, self.document)


class P14ResponseCheckpoint:
    """Atomic per-request response cache and invocation audit for paid evaluation."""

    def __init__(
        self,
        root: Path,
        *,
        resume: bool,
        budget: P14BudgetLedger | None = None,
    ) -> None:
        self.root = root
        self.responses = root / "responses"
        self.audit_path = root / "invocation_audit.json"
        self.resume = resume
        self.budget = budget
        self.responses.mkdir(parents=True, exist_ok=True)
        existing = list(self.responses.glob("*.json"))
        if existing and not resume:
            raise RuntimeError(
                f"P14 response checkpoint already contains {len(existing)} responses; "
                "pass --resume or choose a new output directory"
            )

    def load(self, request_sha256: str) -> dict[str, Any] | None:
        if not self.resume:
            return None
        path = self.responses / f"{request_sha256}.json"
        if not path.exists():
            return None
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("request_sha256") != request_sha256:
            raise RuntimeError(f"P14 checkpoint identity mismatch: {path}")
        return payload

    def save(self, request_sha256: str, payload: dict[str, Any]) -> None:
        path = self.responses / f"{request_sha256}.json"
        document = {**payload, "saved_at": datetime.now(UTC).isoformat()}
        if path.exists():
            existing = json.loads(path.read_text(encoding="utf-8"))
            comparable_existing = {
                key: value for key, value in existing.items() if key != "saved_at"
            }
            comparable_document = {
                key: value for key, value in document.items() if key != "saved_at"
            }
            if comparable_existing != comparable_document:
                raise RuntimeError(f"P14 checkpoint response conflict: {path}")
            return
        _atomic_write_json(path, document)

    def record_invocation(self, invocation: dict[str, Any]) -> None:
        if self.budget is not None:
            self.budget.settle(invocation)
        audit: list[dict[str, Any]] = []
        if self.audit_path.exists():
            audit = json.loads(self.audit_path.read_text(encoding="utf-8"))
        audit.append({**invocation, "recorded_at": datetime.now(UTC).isoformat()})
        _atomic_write_json(self.audit_path, audit)

    def authorize_request(
        self,
        *,
        request_sha256: str,
        prompt_name: str,
        profile_id: str,
        estimated_input_tokens: int,
        configured_max_output_tokens: int,
    ) -> None:
        if self.budget is None:
            return
        self.budget.authorize(
            request_sha256=request_sha256,
            prompt_name=prompt_name,
            profile_id=profile_id,
            estimated_input_tokens=estimated_input_tokens,
            configured_max_output_tokens=configured_max_output_tokens,
        )


def _atomic_write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def _usage_cost_cny(input_tokens: int, output_tokens: int) -> float:
    return (input_tokens * INPUT_RATE_CNY_PER_M + output_tokens * OUTPUT_RATE_CNY_PER_M) / 1_000_000


def _load_inputs(repository_root: Path) -> tuple[CPDS1P14PilotDataset, P14FixtureBundle]:
    root = repository_root / "datasets/coursepilot_eval/v1"
    cases = CPDS1P14PilotDataset.model_validate_json(
        (root / "approved/cp_ds1/p14_lesson_pilot.json").read_text(encoding="utf-8")
    )
    fixtures = P14FixtureBundle.model_validate_json(
        (root / "provenance/p14_agent_fixtures_r1.json").read_text(encoding="utf-8")
    )
    return cases, fixtures


def _snapshot_and_context(
    case: Any, fixture: Any
) -> tuple[KnowledgePointSnapshot, ContextPackageRef, list[dict[str, object]]]:
    snapshot_items = [
        KnowledgePointSnapshotItem(
            knowledge_point_id=item.gold_kp_id,
            course_id=item.course_id,
            canonical_name=item.canonical_name,
            summary=item.summary,
            evidence_links=[
                KnowledgePointEvidenceLink(evidence_id=eid) for eid in item.evidence_ids
            ],
            section_ids=item.section_ids,
        )
        for item in case.knowledge_point_snapshot
    ]
    snapshot_payload = [item.model_dump(mode="json") for item in snapshot_items]
    snapshot = KnowledgePointSnapshot(
        meta=ResponseMeta.from_context(RequestContext()),
        course_id=case.course_id,
        items=snapshot_items,
        snapshot_sha256=canonical_sha256(snapshot_payload),
    )
    context = ContextPackageRef(
        context_id=fixture.context_package_id,
        purpose=fixture.purpose,
        course_id=fixture.course_id,
        index_version=fixture.index_version,
        evidence_ids=fixture.evidence_ids,
        token_count=fixture.token_count,
        content_hash=fixture.content_hash,
        trace_id=fixture.trace_id,
    )
    records = [
        {
            "evidence_id": item.evidence_id,
            "text": item.gold_text,
            "content_sha256": item.content_sha256,
            "source_document_id": item.source_document_id,
            "source_document_version": item.source_document_version,
            "page_start": item.page_start,
            "page_end": item.page_end,
        }
        for item in fixture.evidence_records
    ]
    return snapshot, context, records


def run_pilot(repository_root: Path) -> dict[str, Any]:
    """Run the deterministic Contract Fake used by existing offline tests."""
    cases, fixtures = _load_inputs(repository_root)
    by_context = {fixture.context_package_id: fixture for fixture in fixtures.context_fixtures}
    results: list[dict[str, Any]] = []
    for case in cases.cases:
        snapshot, context, records = _snapshot_and_context(
            case, by_context[case.context_fixture_id]
        )
        generator = LessonGenerator()
        blueprint = generator.build_blueprint(
            course_id=case.course_id,
            chapter_scope=case.chapter_range,
            total_sessions=case.total_sessions,
            session_duration=case.session_duration,
            template_snapshot_id=case.template_id,
            kp_snapshot=snapshot,
            context_ref=context,
            context_records=records,
        )
        artifact = generator.generate_artifact(blueprint, snapshot, context_records=records)
        report = LessonP14Validator().validate(artifact, artifact_id=case.record_id)
        results.append(
            {
                "record_id": case.record_id,
                "passed": report.passed,
                "issues": sorted(report.issue_codes()),
                "evidence_coverage": report.coverage_metrics.get("evidence_coverage", 0.0),
                "provider_calls": 0,
                "kp_extractor_calls": 0,
            }
        )
    return {
        "mode": "offline",
        "cases": results,
        "passed": all(item["passed"] for item in results),
        "provider_calls": 0,
    }


def _estimate_tokens(payload: object) -> int:
    # Conservative local estimate for the preflight only.  Real usage is taken from
    # provider metadata, or the repository tokenizer estimate when usage is absent.
    return max(1, len(json.dumps(payload, ensure_ascii=False, default=str)) // 3)


def estimate_budget(repository_root: Path) -> dict[str, Any]:
    cases, fixtures = _load_inputs(repository_root)
    by_context = {fixture.context_package_id: fixture for fixture in fixtures.context_fixtures}
    legacy_input = 0
    p14_input = 0
    for case in cases.cases:
        fixture = by_context[case.context_fixture_id]
        context = [item.model_dump(mode="json") for item in fixture.evidence_records]
        legacy_payload = {
            "lesson_params": case.model_dump(mode="json"),
            "retrieved_contexts": context,
            "knowledge_points": case.required_knowledge_point_ids,
        }
        legacy_input += 3 * _estimate_tokens(legacy_payload)
        p14_input += (2 + case.total_sessions) * _estimate_tokens(
            {"case": case.model_dump(mode="json"), "context": context}
        )
        if case.review_scenario.plan_action == "replan":
            p14_input += _estimate_tokens(case.review_scenario.model_dump(mode="json"))
    # Output caps are the route maxima, not a claim that the provider will consume all of them.
    max_output = 9 * 8192 + 4 * 4096 + 5 * 8192
    estimated_cost = (legacy_input + p14_input) * INPUT_RATE_CNY_PER_M / 1_000_000
    estimated_cost += max_output * OUTPUT_RATE_CNY_PER_M / 1_000_000
    thinking_reserved_output = math.ceil(max_output * THINKING_RESERVE_MULTIPLIER)
    thinking_aware_cost = _usage_cost_cny(legacy_input + p14_input, thinking_reserved_output)
    return {
        "logical_request_count": 18,
        "request_breakdown": {
            "cp_b0_base": 9,
            "p14_initial_blueprint": 3,
            "p14_replan": 1,
            "p14_sessions": 5,
            "conditional_repairs": "not included; dispatched only inside remaining budget",
        },
        "legacy_input_tokens_estimate": legacy_input,
        "p14_input_tokens_estimate": p14_input,
        "combined_input_tokens_estimate": legacy_input + p14_input,
        "max_output_tokens": max_output,
        "estimated_upper_bound_cny": round(estimated_cost, 4),
        "thinking_reserve_multiplier": THINKING_RESERVE_MULTIPLIER,
        "thinking_reserved_output_tokens": thinking_reserved_output,
        "thinking_aware_planning_cost_cny": round(thinking_aware_cost, 4),
        "execution_policy": "per_request_reservation_then_safe_pause",
        "limits": {
            "max_cost_cny": MAX_COST_CNY,
            "max_input_tokens": MAX_INPUT_TOKENS,
            "max_output_tokens": MAX_OUTPUT_TOKENS,
        },
        "within_limits": (
            legacy_input + p14_input <= MAX_INPUT_TOKENS
            and max_output <= MAX_OUTPUT_TOKENS
            and estimated_cost <= MAX_COST_CNY
        ),
    }


def _blueprint_smoke_payload(case: Any, snapshot: KnowledgePointSnapshot, records: list) -> dict:
    return {
        "course_id": case.course_id,
        "chapter_scope": case.chapter_range,
        "total_sessions": case.total_sessions,
        "session_duration": case.session_duration,
        "template_snapshot_id": case.template_id,
        "context_package_id": case.context_fixture_id,
        "approved_knowledge_points": [item.model_dump(mode="json") for item in snapshot.items],
        "context_evidence": records,
        "replan_instruction": None,
    }


def estimate_blueprint_smoke_budget(repository_root: Path) -> dict[str, Any]:
    cases, fixtures = _load_inputs(repository_root)
    case = next(item for item in cases.cases if item.record_id == SMOKE_RECORD_ID)
    fixture = next(
        item
        for item in fixtures.context_fixtures
        if item.context_package_id == case.context_fixture_id
    )
    snapshot, _context, records = _snapshot_and_context(case, fixture)
    human_payload = {
        "input": _blueprint_smoke_payload(case, snapshot, records),
        "schema": LessonBlueprint.model_json_schema(),
    }
    system_prompt = build_coursepilot_system_prompt(load_prompt("lesson/p14_plan_blueprint"))
    raw_input_estimate = _estimate_tokens({"system": system_prompt, "human": human_payload})
    input_tokens = int(raw_input_estimate * 1.3)
    upper_cost = (
        input_tokens * INPUT_RATE_CNY_PER_M + SMOKE_MAX_OUTPUT_TOKENS * OUTPUT_RATE_CNY_PER_M
    ) / 1_000_000
    return {
        "record_id": SMOKE_RECORD_ID,
        "logical_request_count": 1,
        "input_tokens_estimate_with_margin": input_tokens,
        "max_output_tokens": SMOKE_MAX_OUTPUT_TOKENS,
        "estimated_upper_bound_cny": round(upper_cost, 6),
        "authorized_cost_cap_cny": SMOKE_MAX_COST_CNY,
        "within_limits": upper_cost <= SMOKE_MAX_COST_CNY,
    }


@contextmanager
def _strict_provider_settings(repository_root: Path) -> Iterator[None]:
    old_mode = settings.COURSEPILOT_GENERATION_MODE
    old_fallback = settings.COURSEPILOT_DISABLE_DETERMINISTIC_FALLBACK
    old_gateway_mode = settings.COURSEPILOT_MODEL_GATEWAY_MODE
    old_max_retries = settings.COURSEPILOT_LLM_MAX_RETRIES
    old_profile_path = settings.COURSEPILOT_MODEL_PROFILE_PATH
    settings.COURSEPILOT_GENERATION_MODE = "llm"
    settings.COURSEPILOT_DISABLE_DETERMINISTIC_FALLBACK = True
    settings.COURSEPILOT_MODEL_GATEWAY_MODE = "evaluation"
    # Only a proven pre-response connection failure may be retried by the shared caller.
    settings.COURSEPILOT_LLM_MAX_RETRIES = 1
    settings.COURSEPILOT_MODEL_PROFILE_PATH = str(
        repository_root / "resources/model_profiles/p14_closure_v1.yaml"
    )
    get_coursepilot_llm.cache_clear()
    # The gateway cache captures provider/model configuration, so clear it for each run.
    from coursepilot import llm as llm_module

    llm_module._configured_model_gateway.cache_clear()
    try:
        yield
    finally:
        settings.COURSEPILOT_GENERATION_MODE = old_mode
        settings.COURSEPILOT_DISABLE_DETERMINISTIC_FALLBACK = old_fallback
        settings.COURSEPILOT_MODEL_GATEWAY_MODE = old_gateway_mode
        settings.COURSEPILOT_LLM_MAX_RETRIES = old_max_retries
        settings.COURSEPILOT_MODEL_PROFILE_PATH = old_profile_path
        get_coursepilot_llm.cache_clear()
        llm_module._configured_model_gateway.cache_clear()


def _legacy_context(fixture: Any) -> list[dict[str, Any]]:
    return [
        KBSearchResult(
            chunk_id=item.evidence_id,
            course_id=item.course_id,
            document_id=item.source_document_id,
            source_type="primary_source",
            chapter=None,
            section=None,
            page=item.page_start,
            content=item.gold_text,
            score=1.0,
        ).model_dump(mode="json")
        for item in fixture.evidence_records
    ]


def _run_legacy_case(case: Any, fixture: Any) -> dict[str, Any]:
    state: LessonGraphState = {
        "course_id": case.course_id,
        "lesson_params": {
            "chapter_range": case.chapter_range,
            "total_sessions": case.total_sessions,
            "session_duration": case.session_duration,
            "teaching_focus": case.teaching_focus,
            "teaching_template": case.template_id,
            "course_name": case.course_id,
        },
        "retrieved_contexts": _legacy_context(fixture),
    }
    state.update(extract_knowledge_points(state))
    state.update(plan_sessions(state))
    state.update(generate_lesson_design(state))
    state.update(validate_lesson_design(state))
    if state.get("validation_report", {}).get("needs_repair"):
        state.update(reflect_and_revise(state))
        state.update(validate_lesson_design(state))
    return {
        "lesson_design": state.get("lesson_design"),
        "validation_report": state.get("validation_report", {}),
        "kp_extractor_calls": 1,
        "repair_calls": int(state.get("validation_report", {}).get("repair_attempts", 0)),
    }


def _repair_p14_artifact(
    generator: LessonGenerator,
    artifact: LessonArtifact,
    *,
    context_records: list[dict[str, object]],
) -> tuple[LessonArtifact, Any, int]:
    validator = LessonP14Validator()
    report = validator.validate(artifact, artifact_id=artifact.course_id)
    repaired_sessions = list(artifact.sessions)
    repair_calls = 0
    plans = {plan.session_id: plan for plan in artifact.blueprint.session_plans}
    for position, session in enumerate(artifact.sessions):
        prefix = f"$.sessions[{position}]."
        issues = [
            issue
            for issue in report.issues
            if issue.auto_repairable
            and issue.scope.item_id == session.session_id
            and issue.scope.json_path.startswith(prefix)
        ]
        if not issues:
            continue
        allowed_fields = {
            issue.scope.json_path[len(prefix) :].split("[", 1)[0].split(".", 1)[0]
            for issue in issues
        }
        plan = plans[session.session_id]
        repaired_sessions[position] = generator.repair_session(
            session,
            issue_payloads=[issue.model_dump(mode="json") for issue in issues],
            allowed_fields=allowed_fields,
            allowed_evidence_ids=set(plan.required_evidence_ids),
            context_records=context_records,
        )
        repair_calls += 1
    if repair_calls:
        artifact = artifact.model_copy(update={"sessions": repaired_sessions})
        report = validator.validate(artifact, artifact_id=artifact.course_id)
    return artifact, report, repair_calls


def run_blueprint_smoke(
    repository_root: Path,
    *,
    checkpoint_dir: Path,
) -> dict[str, Any]:
    """Run one authorized P14 Blueprint request and no downstream stage."""
    preflight = estimate_blueprint_smoke_budget(repository_root)
    if not preflight["within_limits"]:
        raise RuntimeError(f"P14 Blueprint smoke exceeds approved budget: {preflight}")
    cases, fixtures = _load_inputs(repository_root)
    case = next(item for item in cases.cases if item.record_id == SMOKE_RECORD_ID)
    fixture = next(
        item
        for item in fixtures.context_fixtures
        if item.context_package_id == case.context_fixture_id
    )
    snapshot, context, records = _snapshot_and_context(case, fixture)
    checkpoint = P14ResponseCheckpoint(checkpoint_dir, resume=False)
    collector = None
    blueprint: LessonBlueprint | None = None
    failure: dict[str, str] | None = None
    with _strict_provider_settings(repository_root):
        try:
            with collect_coursepilot_llm_metadata(
                thread_id=f"p14-smoke:{case.record_id}", checkpoint=checkpoint
            ) as collector:
                blueprint = LessonGenerator(use_model=True).build_blueprint(
                    course_id=case.course_id,
                    chapter_scope=case.chapter_range,
                    total_sessions=case.total_sessions,
                    session_duration=case.session_duration,
                    template_snapshot_id=case.template_id,
                    kp_snapshot=snapshot,
                    context_ref=context,
                    context_records=records,
                )
        except Exception as exc:
            failure = {"error_category": type(exc).__name__, "error": str(exc)}
    usage = summarize_llm_invocations(collector.invocations if collector is not None else [])
    input_tokens = int(usage.get("input_tokens") or 0)
    output_tokens = int(usage.get("output_tokens") or 0)
    measured_cost = (
        input_tokens * INPUT_RATE_CNY_PER_M + output_tokens * OUTPUT_RATE_CNY_PER_M
    ) / 1_000_000
    if measured_cost > SMOKE_MAX_COST_CNY:
        failure = {
            "error_category": "budget_exceeded",
            "error": "Provider usage exceeded the authorized P14 Blueprint smoke cap.",
        }
    return {
        "mode": "blueprint_smoke",
        "status": "completed" if failure is None else "provider_failed",
        "preflight": preflight,
        "record_id": case.record_id,
        "executed_stages": ["p14_blueprint"],
        "excluded_stages": ["cp_b0", "session_generation", "repair", "full_pilot"],
        "blueprint_sha256": (
            canonical_sha256(blueprint.model_dump(mode="json")) if blueprint is not None else None
        ),
        "session_plan_count": len(blueprint.session_plans) if blueprint is not None else 0,
        "usage": usage,
        "measured_or_estimated_cost_cny": round(measured_cost, 6),
        "billing_reconciliation_required": any(
            attempt.get("billing_status") == "unknown_pending_reconciliation"
            for invocation in (collector.invocations if collector is not None else [])
            for attempt in invocation.get("attempts", [])
        ),
        "checkpoint_dir": str(checkpoint_dir),
        "failure": failure,
    }


def run_real_pilot(
    repository_root: Path,
    *,
    checkpoint_dir: Path,
    resume: bool,
) -> dict[str, Any]:
    """Run exactly one strict CP-B0/P14 provider comparison."""
    preflight = estimate_budget(repository_root)
    if not preflight["within_limits"]:
        raise RuntimeError(f"P14 provider preflight exceeds approved budget: {preflight}")
    cases, fixtures = _load_inputs(repository_root)
    by_context = {fixture.context_package_id: fixture for fixture in fixtures.context_fixtures}
    legacy_results: list[dict[str, Any]] = []
    p14_results: list[dict[str, Any]] = []
    provider_failure: dict[str, Any] | None = None
    budget = P14BudgetLedger(checkpoint_dir / "full_budget_ledger.json", resume=resume)
    checkpoint = P14ResponseCheckpoint(checkpoint_dir, resume=resume, budget=budget)
    with _strict_provider_settings(repository_root):
        for case in cases.cases:
            fixture = by_context[case.context_fixture_id]
            try:
                with collect_coursepilot_llm_metadata(
                    thread_id=f"p14-b0:{case.record_id}", checkpoint=checkpoint
                ) as collector:
                    legacy = _run_legacy_case(case, fixture)
            except Exception as exc:
                provider_failure = {
                    "track": "cp_b0",
                    "record_id": case.record_id,
                    "error_category": type(exc).__name__,
                    "error": str(exc),
                    "usage": summarize_llm_invocations(collector.invocations),
                }
                break
            legacy["record_id"] = case.record_id
            legacy["usage"] = summarize_llm_invocations(collector.invocations)
            legacy_results.append(legacy)

            snapshot, context, records = _snapshot_and_context(case, fixture)
            generator = LessonGenerator(use_model=True)
            try:
                with collect_coursepilot_llm_metadata(
                    thread_id=f"p14:{case.record_id}", checkpoint=checkpoint
                ) as p14_collector:
                    blueprint = generator.build_blueprint(
                        course_id=case.course_id,
                        chapter_scope=case.chapter_range,
                        total_sessions=case.total_sessions,
                        session_duration=case.session_duration,
                        template_snapshot_id=case.template_id,
                        kp_snapshot=snapshot,
                        context_ref=context,
                        context_records=records,
                    )
                    if case.review_scenario.plan_action == "replan":
                        blueprint = generator.build_blueprint(
                            course_id=case.course_id,
                            chapter_scope=case.chapter_range,
                            total_sessions=case.total_sessions,
                            session_duration=case.session_duration,
                            template_snapshot_id=case.template_id,
                            kp_snapshot=snapshot,
                            context_ref=context,
                            context_records=records,
                            replan_instruction=case.review_scenario.replan_instruction,
                            previous_blueprint=blueprint,
                        )
                    # Apply the approved review scenario without asking the model to redo an edit.
                    if case.review_scenario.plan_action == "edit":
                        for path, value in case.review_scenario.field_edits.items():
                            if path.startswith("sessions[") and path.endswith("].teaching_focus"):
                                index = int(path.split("[")[1].split("]")[0])
                                if index >= len(blueprint.session_plans):
                                    raise ValueError(f"review edit path out of range: {path}")
                                blueprint.session_plans[index] = blueprint.session_plans[
                                    index
                                ].model_copy(update={"title": value})
                    artifact = generator.generate_artifact(
                        blueprint, snapshot, context_records=records
                    )
                    artifact, validation, repair_calls = _repair_p14_artifact(
                        generator,
                        artifact,
                        context_records=records,
                    )
            except Exception as exc:
                provider_failure = {
                    "track": "p14",
                    "record_id": case.record_id,
                    "error_category": type(exc).__name__,
                    "error": str(exc),
                    "usage": summarize_llm_invocations(p14_collector.invocations),
                }
                break
            p14_results.append(
                {
                    "record_id": case.record_id,
                    "passed": validation.passed,
                    "issues": sorted(validation.issue_codes()),
                    "evidence_coverage": validation.coverage_metrics.get("evidence_coverage", 0.0),
                    "kp_extractor_calls": 0,
                    "interrupts": ["lesson_session_plan_review", "lesson_final_review"],
                    "repair_calls": repair_calls,
                    "usage": summarize_llm_invocations(p14_collector.invocations),
                }
            )
    failure_usage = provider_failure.get("usage", {}) if provider_failure else {}
    if provider_failure is None:
        budget.mark_completed()
    paused_for_budget = bool(
        provider_failure
        and provider_failure.get("error_category") == "CoursePilotLLMBudgetExceeded"
    )
    return {
        "mode": "real",
        "preflight": preflight,
        "cp_b0": legacy_results,
        "p14": p14_results,
        "provider_calls": sum(item["usage"]["provider_request_count"] for item in legacy_results)
        + sum(item["usage"]["provider_request_count"] for item in p14_results)
        + int(failure_usage.get("provider_request_count", 0)),
        "cache_hits": sum(item["usage"]["cache_hit_count"] for item in legacy_results)
        + sum(item["usage"]["cache_hit_count"] for item in p14_results)
        + int(failure_usage.get("cache_hit_count", 0)),
        "checkpoint_dir": str(checkpoint_dir),
        "budget": budget.summary(),
        "p14_kp_extractor_calls": 0,
        "status": (
            "budget_paused"
            if paused_for_budget
            else "provider_failed"
            if provider_failure
            else "completed"
        ),
        "provider_failure": provider_failure,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository-root", type=Path, default=Path("."))
    parser.add_argument("--output", type=Path)
    parser.add_argument("--checkpoint-dir", type=Path)
    parser.add_argument(
        "--mode",
        choices=("offline", "preflight", "smoke-preflight", "smoke", "real"),
        default="offline",
    )
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    if args.mode == "offline":
        report = run_pilot(args.repository_root)
    elif args.mode == "preflight":
        report = estimate_budget(args.repository_root)
    elif args.mode == "smoke-preflight":
        report = estimate_blueprint_smoke_budget(args.repository_root)
    elif args.mode == "smoke":
        checkpoint_dir = args.checkpoint_dir or (
            args.output.parent / "checkpoint"
            if args.output
            else args.repository_root / "storage_eval/p14_closure/smoke/checkpoint"
        )
        report = run_blueprint_smoke(
            args.repository_root,
            checkpoint_dir=checkpoint_dir,
        )
    else:
        checkpoint_dir = args.checkpoint_dir or (
            args.output.parent / "checkpoint"
            if args.output
            else args.repository_root / "storage_eval/p14_closure/checkpoint"
        )
        report = run_real_pilot(
            args.repository_root,
            checkpoint_dir=checkpoint_dir,
            resume=args.resume,
        )
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        _atomic_write_json(args.output, report)
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
