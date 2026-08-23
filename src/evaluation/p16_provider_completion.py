"""Provider-complete the nine P16 pages previously closed deterministically."""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from core.settings import settings
from coursepilot.domain.common import canonical_sha256
from coursepilot.domain.ppt import PPTArtifact, SlideContent
from coursepilot.llm import (
    CoursePilotLLMCallError,
    _configured_model_gateway,
    collect_coursepilot_llm_metadata,
    generate_structured,
    get_coursepilot_llm,
)
from evaluation.p16_critical_repair import (
    DATASET,
    DECISIONS,
    SOURCE_REPORT,
    _postprocess,
    _recover_structured_response,
    _target,
)
from evaluation.p16_ppt_eval import _write_json_atomic

ROOT = Path(__file__).resolve().parents[2]
BASE_REPORT = ROOT / "storage_eval/p16_critical_repair/report.json"
TARGET_SOURCE = "deterministic_after_provider_stop"
EXPECTED_TARGETS = 9
BEIJING = ZoneInfo("Asia/Shanghai")
INITIAL_PROFILE_RESOURCE = "resources/model_profiles/p16_provider_completion_v1.yaml"
RETRY_PROFILE_RESOURCE = "resources/model_profiles/p16_provider_completion_retry_v1.yaml"


class _CompletionCheckpoint:
    """Durable response cache with accounting but no monetary/token gate.

    Scope and retry counts provide the bounded execution contract for this owner-authorized
    completion. The checkpoint intentionally does not implement StructuredRequestBudgetGuard.
    """

    def __init__(self, path: Path) -> None:
        self.path = path
        saved = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
        self.cache: dict[str, dict[str, Any]] = dict(saved.get("cache", {}))
        self.failed_invocations: list[dict[str, Any]] = list(saved.get("failed_invocations", []))
        self.current_slide_id: str | None = saved.get("current_slide_id")
        self.current_profile_id: str | None = saved.get("current_profile_id")

    def load(self, request_sha256: str) -> dict[str, Any] | None:
        return self.cache.get(request_sha256)

    def save(self, request_sha256: str, payload: dict[str, Any]) -> None:
        if request_sha256 not in self.cache:
            self.cache[request_sha256] = payload
            self._persist()

    def record_invocation(self, invocation: dict[str, Any]) -> None:
        if invocation.get("status") != "failed":
            return
        enriched = {
            **invocation,
            "slide_id": self.current_slide_id,
            "profile_id_at_failure": self.current_profile_id,
        }
        identity = (
            enriched.get("request_sha256"),
            enriched.get("slide_id"),
            enriched.get("profile_id_at_failure"),
        )
        if not any(
            (
                item.get("request_sha256"),
                item.get("slide_id"),
                item.get("profile_id_at_failure"),
            )
            == identity
            for item in self.failed_invocations
        ):
            self.failed_invocations.append(enriched)
            self._persist()

    def begin(self, *, slide_id: str, profile_id: str) -> None:
        self.current_slide_id = slide_id
        self.current_profile_id = profile_id
        self._persist()

    def finish(self) -> None:
        self.current_slide_id = None
        self.current_profile_id = None
        self._persist()

    def _persist(self) -> None:
        _write_json_atomic(
            self.path,
            {
                "cache": self.cache,
                "failed_invocations": self.failed_invocations,
                "current_slide_id": self.current_slide_id,
                "current_profile_id": self.current_profile_id,
            },
        )

    def usage_summary(self) -> dict[str, Any]:
        success_usage = [item.get("usage") or {} for item in self.cache.values()]
        failed_attempts: list[dict[str, Any]] = []
        all_failed_attempts = 0
        for invocation in self.failed_invocations:
            billable = [
                attempt
                for attempt in invocation.get("attempts", [])
                if attempt.get("billing_status") != "not_sent"
            ]
            all_failed_attempts += len(billable)
            if invocation.get("request_sha256") not in self.cache:
                failed_attempts.extend(billable)
        failed_usage = [item.get("usage") or {} for item in failed_attempts]
        usage = success_usage + failed_usage
        return {
            "successful_responses": len(self.cache),
            "failed_attempts_recorded": all_failed_attempts,
            "unrecovered_billable_or_unknown_attempts": len(failed_attempts),
            "physical_requests": len(self.cache) + len(failed_attempts),
            "input_tokens": sum(int(item.get("input_tokens", 0)) for item in usage),
            "output_tokens": sum(int(item.get("output_tokens", 0)) for item in usage),
        }


def _load_inputs() -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    base = json.loads(BASE_REPORT.read_text(encoding="utf-8"))
    source = json.loads(SOURCE_REPORT.read_text(encoding="utf-8"))
    decisions = json.loads(DECISIONS.read_text(encoding="utf-8"))
    dataset = json.loads(DATASET.read_text(encoding="utf-8"))
    return base, source, decisions, dataset


def target_slide_ids(base: dict[str, Any]) -> list[str]:
    return [
        slide_id for slide_id, source in base["repair_sources"].items() if source == TARGET_SOURCE
    ]


def preflight() -> dict[str, Any]:
    base, source, decisions, dataset = _load_inputs()
    targets = target_slide_ids(base)
    decision_ids = {
        item["slide_id"] for item in decisions["records"] if item.get("critical_defect") is True
    }
    source_ids = {
        slide["slide_id"] for case in source["cases"] for slide in case["artifact"]["slides"]
    }
    dataset_ids = {
        target["slide_id"] for case in dataset["cases"] for target in case["slide_targets"]
    }
    exact = (
        len(targets) == EXPECTED_TARGETS
        and len(set(targets)) == EXPECTED_TARGETS
        and set(targets) <= decision_ids & source_ids & dataset_ids
    )
    return {
        "schema_version": "coursepilot.p16-provider-completion-preflight.v1",
        "scope_exact": exact,
        "target_count": len(targets),
        "target_slide_ids": targets,
        "base_report_sha256": canonical_sha256(base),
        "external_calls_made": 0,
        "provider_contract": {
            "initial_profile": "content_repair_main",
            "initial_profile_resource": INITIAL_PROFILE_RESOURCE,
            "initial_timeout_seconds": 120,
            "timeout_retry_profile": "content_repair_main",
            "timeout_retry_profile_resource": RETRY_PROFILE_RESOURCE,
            "timeout_retry_seconds": 360,
            "max_timeout_retries_per_slide": 1,
            "fallback_allowed": False,
            "budget_hard_limit": None,
            "maximum_target_pages": EXPECTED_TARGETS,
            "maximum_physical_requests": EXPECTED_TARGETS * 2,
        },
    }


def _provider_payload(
    *, original: SlideContent, plan: Any, decision: dict[str, Any], target: dict[str, Any]
) -> dict[str, Any]:
    return {
        "original_slide": original.model_dump(mode="json"),
        "slide_plan": plan.model_dump(mode="json"),
        "review_issue": decision["reviewer_notes"],
        "evidence": target.get("evidence_snapshots", []),
        "required_claims": target.get("required_claims", []),
        "allowed_fields": ["title", "bullets", "body_text", "speaker_notes", "assets"],
    }


def _activate_profile_resource(path: str) -> None:
    settings.COURSEPILOT_MODEL_PROFILE_PATH = path
    _configured_model_gateway.cache_clear()
    get_coursepilot_llm.cache_clear()


def _call_provider(
    *,
    checkpoint: _CompletionCheckpoint,
    original: SlideContent,
    plan: Any,
    decision: dict[str, Any],
    target: dict[str, Any],
) -> tuple[SlideContent, str]:
    payload = _provider_payload(original=original, plan=plan, decision=decision, target=target)
    initial_profile = "content_repair_main"
    _activate_profile_resource(INITIAL_PROFILE_RESOURCE)
    checkpoint.begin(slide_id=original.slide_id, profile_id=f"{initial_profile}@120s")
    print(
        json.dumps(
            {
                "event": "provider_page_started",
                "slide_id": original.slide_id,
                "timeout_seconds": 120,
            },
            ensure_ascii=False,
        ),
        flush=True,
    )
    try:
        candidate = generate_structured(
            prompt_name="ppt/p16_repair_slide",
            output_schema=SlideContent,
            payload=payload,
            fallback=lambda: (_ for _ in ()).throw(
                RuntimeError("P16_PROVIDER_COMPLETION_FALLBACK_FORBIDDEN")
            ),
            profile_id=initial_profile,
            allow_fallback=False,
        )
        checkpoint.finish()
        return candidate, "provider_completion"
    except CoursePilotLLMCallError as exc:
        if exc.category == "structured_parse_error":
            candidate = _recover_structured_response(checkpoint)
            checkpoint.finish()
            return candidate, "provider_completion_recovered_response"
        if exc.category != "timeout":
            raise

    retry_profile = "content_repair_main"
    print(
        json.dumps(
            {
                "event": "provider_page_timeout_retry",
                "slide_id": original.slide_id,
                "timeout_seconds": 360,
            },
            ensure_ascii=False,
        ),
        flush=True,
    )
    _activate_profile_resource(RETRY_PROFILE_RESOURCE)
    checkpoint.begin(slide_id=original.slide_id, profile_id=f"{retry_profile}@360s")
    try:
        candidate = generate_structured(
            prompt_name="ppt/p16_repair_slide",
            output_schema=SlideContent,
            payload=payload,
            fallback=lambda: (_ for _ in ()).throw(
                RuntimeError("P16_PROVIDER_COMPLETION_FALLBACK_FORBIDDEN")
            ),
            profile_id=retry_profile,
            allow_fallback=False,
        )
        checkpoint.finish()
        return candidate, "provider_completion_timeout_retry"
    except CoursePilotLLMCallError as exc:
        if exc.category == "structured_parse_error":
            candidate = _recover_structured_response(checkpoint)
            checkpoint.finish()
            return candidate, "provider_completion_timeout_retry_recovered_response"
        raise
    finally:
        _activate_profile_resource(INITIAL_PROFILE_RESOURCE)


def run(*, output_dir: Path) -> dict[str, Any]:
    check = preflight()
    if not check["scope_exact"]:
        raise RuntimeError("P16_PROVIDER_COMPLETION_SCOPE_MISMATCH")
    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / "report.json"
    if report_path.is_file():
        existing = json.loads(report_path.read_text(encoding="utf-8"))
        if existing.get("status") == "completed":
            return existing

    base, source, decisions, dataset = _load_inputs()
    target_ids = set(check["target_slide_ids"])
    dataset_by_case = {item["record_id"]: item for item in dataset["cases"]}
    decision_by_slide = {
        item["slide_id"]: item for item in decisions["records"] if item["slide_id"] in target_ids
    }
    checkpoint = _CompletionCheckpoint(output_dir / "checkpoint.json")
    progress_path = output_dir / "progress.json"
    progress = (
        json.loads(progress_path.read_text(encoding="utf-8"))
        if progress_path.is_file()
        else {"slides": {}}
    )
    completed: dict[str, Any] = dict(progress.get("slides", {}))
    print(
        json.dumps(
            {
                "event": "provider_completion_resumed",
                "already_completed": len(completed),
                "remaining": len(target_ids - set(completed)),
            },
            ensure_ascii=False,
        ),
        flush=True,
    )

    with collect_coursepilot_llm_metadata(
        thread_id="p16:provider-completion-nine-pages", checkpoint=checkpoint
    ) as collector:
        for case in source["cases"]:
            original_artifact = PPTArtifact.model_validate(case["artifact"])
            case_spec = dataset_by_case[case["record_id"]]
            for index, original in enumerate(original_artifact.slides):
                if original.slide_id not in target_ids or original.slide_id in completed:
                    continue
                decision = decision_by_slide[original.slide_id]
                target = _target(case_spec, original.slide_id)
                candidate, provider_source = _call_provider(
                    checkpoint=checkpoint,
                    original=original,
                    plan=original_artifact.architecture.plans[index],
                    decision=decision,
                    target=target,
                )
                allowed_citations = {item.evidence_id for item in original.citations}
                if (
                    candidate.slide_id != original.slide_id
                    or {item.evidence_id for item in candidate.citations} - allowed_citations
                ):
                    raise RuntimeError("P16_PROVIDER_COMPLETION_IDENTITY_OR_CITATION_CHANGED")
                repaired, hints = _postprocess(
                    candidate,
                    original=original,
                    target=target,
                    issue=decision["reviewer_notes"],
                )
                repaired = SlideContent.model_validate(
                    {**repaired.model_dump(mode="json"), "content_sha256": None}
                )
                completed[original.slide_id] = {
                    "slide": repaired.model_dump(mode="json"),
                    "render_hints": hints,
                    "repair_source": provider_source,
                }
                _write_json_atomic(progress_path, {"slides": completed})
                print(
                    json.dumps(
                        {
                            "event": "provider_page_completed",
                            "slide_id": original.slide_id,
                            "source": provider_source,
                            "completed": len(completed),
                            "remaining": len(target_ids - set(completed)),
                        },
                        ensure_ascii=False,
                    ),
                    flush=True,
                )

        if set(completed) != target_ids:
            raise RuntimeError("P16_PROVIDER_COMPLETION_INCOMPLETE")

        result_cases: list[dict[str, Any]] = []
        for base_case in base["cases"]:
            artifact = PPTArtifact.model_validate(base_case["artifact"])
            before = {slide.slide_id: slide.content_sha256 for slide in artifact.slides}
            slides = [
                SlideContent.model_validate(completed[slide.slide_id]["slide"])
                if slide.slide_id in target_ids
                else slide
                for slide in artifact.slides
            ]
            merged = artifact.model_copy(update={"slides": slides})
            if any(
                slide.content_sha256 != before[slide.slide_id]
                for slide in merged.slides
                if slide.slide_id not in target_ids
            ):
                raise RuntimeError("P16_PROVIDER_COMPLETION_OUT_OF_SCOPE_CHANGE")
            hints = dict(base_case.get("slide_render_hints", {}))
            for slide_id in target_ids:
                if slide_id in completed:
                    hints[slide_id] = completed[slide_id]["render_hints"]
            result_cases.append(
                {
                    **base_case,
                    "artifact": merged.model_dump(mode="json"),
                    "slide_render_hints": hints,
                    "unchanged_outside_completion_scope": True,
                }
            )

        repair_sources = dict(base["repair_sources"])
        repair_sources.update(
            {slide_id: completed[slide_id]["repair_source"] for slide_id in target_ids}
        )
        valid_provider_sources = {
            "provider_checkpoint",
            "provider",
            "recovered_billed_response",
            "provider_completion",
            "provider_completion_recovered_response",
            "provider_completion_timeout_retry",
            "provider_completion_timeout_retry_recovered_response",
        }
        all_critical_provider_complete = all(
            repair_sources.get(slide_id) in valid_provider_sources
            for slide_id in base["repaired_slide_ids"]
        )
        if not all_critical_provider_complete:
            raise RuntimeError("P16_ALL_CRITICAL_PROVIDER_COMPLETION_NOT_PROVEN")

        result = {
            "schema_version": "coursepilot.p16-provider-completion-report.v1",
            "status": "completed",
            "completed_at": datetime.now(tz=BEIJING).isoformat(),
            "preflight": check,
            "provider_completion_slide_ids": sorted(target_ids),
            "provider_completion_count": len(target_ids),
            "all_17_critical_pages_provider_complete": True,
            "repair_sources": repair_sources,
            "usage": checkpoint.usage_summary(),
            "provider_trace": collector.to_task_metadata(),
            "cases": result_cases,
        }
    _write_json_atomic(report_path, result)
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("storage_eval/p16_provider_completion"),
    )
    parser.add_argument("--preflight", action="store_true")
    parser.add_argument("--external-data-authorized", action="store_true")
    args = parser.parse_args()
    if args.preflight:
        result = preflight()
    else:
        if not args.external_data_authorized:
            parser.error("provider completion requires --external-data-authorized")
        result = run(output_dir=args.output_dir)
    print(json.dumps(result, ensure_ascii=True))


if __name__ == "__main__":
    main()
