"""Offline P16 CP-DS3/CP-DS7 runner; external calls are explicitly opt-in."""

from __future__ import annotations

import argparse
import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, time
from decimal import Decimal
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from agents.coursepilot.ppt.generator import PPTGenerator
from coursepilot.domain.ppt import PPTArtifact
from coursepilot.exporters.pptx import PPTXVersionedExporter
from coursepilot.llm import CoursePilotLLMBudgetExceeded, collect_coursepilot_llm_metadata
from coursepilot.rendering.pptx import inspect_renderable_pptx
from coursepilot.validation.ppt_v2 import validate_ppt_artifact


def run_offline(*, output_dir: Path, course_id: str = "p16-course") -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    generator = PPTGenerator()
    architecture = generator.build_architecture(
        course_id=course_id,
        lesson_artifact_id="lesson-p16",
        template_id="ppt_standard_lecture_v1",
        template_snapshot_id="p16-local",
        context_evidence_ids=["p16-evidence-1"],
        slide_targets=[],
    )
    artifact = generator.build_artifact(
        architecture,
        evidence_records=[{"evidence_id": "p16-evidence-1", "content_sha256": "0" * 64}],
    )
    path = PPTXVersionedExporter().export(artifact, output_dir / "p16_offline.pptx")
    render = inspect_renderable_pptx(path, expected_slide_count=artifact.architecture.slide_count)
    validation = validate_ppt_artifact(artifact)
    report = {
        "mode": "offline",
        "artifact": artifact.model_dump(mode="json"),
        "render_report": render.model_dump(mode="json"),
        "validation_report": validation.model_dump(mode="json"),
        "external_requests": 0,
    }
    (output_dir / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return report


_BEIJING = ZoneInfo("Asia/Shanghai")


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def _now_beijing() -> datetime:
    return datetime.now(tz=_BEIJING)


def _is_off_peak(value: datetime) -> bool:
    local = value.astimezone(_BEIJING).time()
    return not (time(9) <= local < time(12) or time(14) <= local < time(18))


@dataclass(frozen=True)
class _DeepSeekFlashPricing:
    cache_hit_input_per_million: Decimal = Decimal("0.05")
    cache_miss_input_per_million: Decimal = Decimal("1.50")
    output_per_million: Decimal = Decimal("4.50")
    identity: str = "deepseek-v4-flash-cny-off-peak-2026-08-17"

    def cost(
        self,
        *,
        input_tokens: int,
        output_tokens: int,
        cache_hit_input_tokens: int | None = None,
        cache_miss_input_tokens: int | None = None,
    ) -> Decimal:
        hit = max(cache_hit_input_tokens or 0, 0)
        miss = max(cache_miss_input_tokens or 0, 0)
        unclassified = max(input_tokens - hit - miss, 0)
        # Provider details may be absent. Treat all unclassified input as cache-miss.
        miss += unclassified
        million = Decimal(1_000_000)
        return (
            Decimal(hit) * self.cache_hit_input_per_million
            + Decimal(miss) * self.cache_miss_input_per_million
            + Decimal(max(output_tokens, 0)) * self.output_per_million
        ) / million


class _BudgetCheckpoint:
    def __init__(
        self,
        *,
        additional_max_input: int,
        additional_max_output: int,
        additional_max_requests: int,
        additional_max_cost_cny: Decimal,
        console_baseline_cny: Decimal,
        console_total_cap_cny: Decimal,
        path: Path | None = None,
        pricing: _DeepSeekFlashPricing | None = None,
        now: Callable[[], datetime] = _now_beijing,
        enforce_off_peak: bool = True,
        manual_retry_request_sha256s: frozenset[str] = frozenset(),
        approved_previous_additional_max_output: int | None = None,
    ) -> None:
        self.additional_max_input = additional_max_input
        self.additional_max_output = additional_max_output
        self.additional_max_requests = additional_max_requests
        self.additional_max_cost_cny = additional_max_cost_cny
        self.console_baseline_cny = console_baseline_cny
        self.console_total_cap_cny = console_total_cap_cny
        self.pricing = pricing or _DeepSeekFlashPricing()
        self.now = now
        self.enforce_off_peak = enforce_off_peak
        self.manual_retry_request_sha256s = manual_retry_request_sha256s
        self.approved_previous_additional_max_output = approved_previous_additional_max_output
        self.input_tokens = 0
        self.output_tokens = 0
        self.requests = 0
        self.incremental_cost_cny = Decimal("0")
        self.cache: dict[str, dict[str, Any]] = {}
        self.failed_invocations: list[dict[str, Any]] = []
        self.path = path
        saved: dict[str, Any] = {}
        if path and path.is_file():
            saved = json.loads(path.read_text(encoding="utf-8"))
            self.input_tokens = int(saved.get("input_tokens", 0))
            self.output_tokens = int(saved.get("output_tokens", 0))
            self.requests = int(saved.get("requests", 0))
            self.cache = dict(saved.get("cache", {}))
            self.failed_invocations = list(saved.get("failed_invocations", []))
        authorization = saved.get("authorization")
        if authorization:
            self._validate_authorization(authorization)
            self.start_input_tokens = int(authorization["start_input_tokens"])
            self.start_output_tokens = int(authorization["start_output_tokens"])
            self.start_requests = int(authorization["start_requests"])
            self.incremental_cost_cny = Decimal(str(saved.get("incremental_cost_cny", "0")))
        else:
            self.start_input_tokens = self.input_tokens
            self.start_output_tokens = self.output_tokens
            self.start_requests = self.requests

    def load(self, request_sha256: str) -> dict[str, Any] | None:
        return self.cache.get(request_sha256)

    def authorize_request(
        self,
        *,
        request_sha256: str,
        prompt_name: str,
        profile_id: str,
        estimated_input_tokens: int,
        configured_max_output_tokens: int,
    ) -> None:
        if self.enforce_off_peak and not _is_off_peak(self.now()):
            raise CoursePilotLLMBudgetExceeded("P16_PROVIDER_NOT_OFF_PEAK")
        previous_failures = sum(
            1
            for invocation in self.failed_invocations
            if invocation.get("request_sha256") == request_sha256
        )
        if previous_failures:
            if request_sha256 not in self.manual_retry_request_sha256s:
                raise CoursePilotLLMBudgetExceeded("P16_PROVIDER_MANUAL_RETRY_APPROVAL_REQUIRED")
            if previous_failures >= 2:
                raise CoursePilotLLMBudgetExceeded("P16_PROVIDER_MANUAL_RETRY_EXHAUSTED")
        incremental_requests = self.requests - self.start_requests
        incremental_input = self.input_tokens - self.start_input_tokens
        incremental_output = self.output_tokens - self.start_output_tokens
        reserved_cost = self.pricing.cost(
            input_tokens=estimated_input_tokens,
            output_tokens=configured_max_output_tokens,
        )
        if (
            incremental_requests + 1 > self.additional_max_requests
            or incremental_input + estimated_input_tokens > self.additional_max_input
            or incremental_output + configured_max_output_tokens > self.additional_max_output
            or self.incremental_cost_cny + reserved_cost > self.additional_max_cost_cny
            or self.console_baseline_cny + self.incremental_cost_cny + reserved_cost
            > self.console_total_cap_cny
        ):
            raise CoursePilotLLMBudgetExceeded("P16_PROVIDER_BUDGET_EXCEEDED")

    def save(self, request_sha256: str, payload: dict[str, Any]) -> None:
        if request_sha256 in self.cache:
            return
        self.cache[request_sha256] = payload
        usage = payload.get("usage") or {}
        self.requests += 1
        input_tokens = int(usage.get("input_tokens", 0))
        output_tokens = int(usage.get("output_tokens", 0))
        self.input_tokens += input_tokens
        self.output_tokens += output_tokens
        self.incremental_cost_cny += self.pricing.cost(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cache_hit_input_tokens=_optional_int(usage.get("cache_hit_input_tokens")),
            cache_miss_input_tokens=_optional_int(usage.get("cache_miss_input_tokens")),
        )
        self._persist()

    def record_invocation(self, invocation: dict[str, Any]) -> None:
        if invocation.get("status") != "failed":
            return
        billable_attempts = [
            attempt
            for attempt in invocation.get("attempts", [])
            if attempt.get("billing_status") != "not_sent"
        ]
        if not billable_attempts:
            return
        self.failed_invocations.append(invocation)
        for attempt in billable_attempts:
            usage = attempt.get("usage") or {}
            input_tokens = int(usage.get("input_tokens", 0))
            output_tokens = int(usage.get("output_tokens", 0))
            self.requests += 1
            self.input_tokens += input_tokens
            self.output_tokens += output_tokens
            self.incremental_cost_cny += self.pricing.cost(
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cache_hit_input_tokens=_optional_int(usage.get("cache_hit_input_tokens")),
                cache_miss_input_tokens=_optional_int(usage.get("cache_miss_input_tokens")),
            )
        self._persist()

    def summary(self) -> dict[str, Any]:
        return {
            "requests": self.requests,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "incremental_requests": self.requests - self.start_requests,
            "incremental_input_tokens": self.input_tokens - self.start_input_tokens,
            "incremental_output_tokens": self.output_tokens - self.start_output_tokens,
            "incremental_cost_cny": str(self.incremental_cost_cny.quantize(Decimal("0.000001"))),
            "estimated_console_total_cny": str(
                (self.console_baseline_cny + self.incremental_cost_cny).quantize(
                    Decimal("0.000001")
                )
            ),
            "pricing_identity": self.pricing.identity,
            "additional_max_requests": self.additional_max_requests,
            "additional_max_input_tokens": self.additional_max_input,
            "additional_max_output_tokens": self.additional_max_output,
            "additional_max_cost_cny": str(self.additional_max_cost_cny),
            "console_baseline_cny": str(self.console_baseline_cny),
            "console_total_cap_cny": str(self.console_total_cap_cny),
            "failed_billable_or_unknown_invocations": len(self.failed_invocations),
        }

    def _authorization(self) -> dict[str, Any]:
        return {
            "start_input_tokens": self.start_input_tokens,
            "start_output_tokens": self.start_output_tokens,
            "start_requests": self.start_requests,
            "additional_max_input": self.additional_max_input,
            "additional_max_output": self.additional_max_output,
            "additional_max_requests": self.additional_max_requests,
            "additional_max_cost_cny": str(self.additional_max_cost_cny),
            "console_baseline_cny": str(self.console_baseline_cny),
            "console_total_cap_cny": str(self.console_total_cap_cny),
            "pricing_identity": self.pricing.identity,
            "off_peak_only": self.enforce_off_peak,
        }

    def _validate_authorization(self, authorization: dict[str, Any]) -> None:
        expected = {
            "additional_max_input": self.additional_max_input,
            "additional_max_output": self.additional_max_output,
            "additional_max_requests": self.additional_max_requests,
            "additional_max_cost_cny": str(self.additional_max_cost_cny),
            "console_baseline_cny": str(self.console_baseline_cny),
            "console_total_cap_cny": str(self.console_total_cap_cny),
            "pricing_identity": self.pricing.identity,
            "off_peak_only": self.enforce_off_peak,
        }
        saved_output_limit = authorization.get("additional_max_output")
        output_extension_is_approved = (
            self.approved_previous_additional_max_output is not None
            and saved_output_limit == self.approved_previous_additional_max_output
            and self.additional_max_output > self.approved_previous_additional_max_output
        )
        comparable_expected = dict(expected)
        comparable_actual = {key: authorization.get(key) for key in expected}
        if output_extension_is_approved:
            comparable_expected.pop("additional_max_output")
            comparable_actual.pop("additional_max_output")
        if comparable_actual != comparable_expected:
            raise RuntimeError("P16_PROVIDER_AUTHORIZATION_MISMATCH")

    def _persist(self) -> None:
        if self.path is None:
            return
        _write_json_atomic(
            self.path,
            {
                "input_tokens": self.input_tokens,
                "output_tokens": self.output_tokens,
                "requests": self.requests,
                "incremental_cost_cny": str(self.incremental_cost_cny),
                "authorization": self._authorization(),
                "cache": self.cache,
                "failed_invocations": self.failed_invocations,
            },
        )


def _optional_int(value: Any) -> int | None:
    return int(value) if value is not None else None


def _saved_budget_summary(saved: dict[str, Any]) -> dict[str, Any]:
    authorization = saved.get("authorization") or {}
    requests = int(saved.get("requests", 0))
    input_tokens = int(saved.get("input_tokens", 0))
    output_tokens = int(saved.get("output_tokens", 0))
    start_requests = int(authorization.get("start_requests", requests))
    start_input = int(authorization.get("start_input_tokens", input_tokens))
    start_output = int(authorization.get("start_output_tokens", output_tokens))
    incremental_cost = Decimal(str(saved.get("incremental_cost_cny", "0")))
    console_baseline = Decimal(str(authorization.get("console_baseline_cny", "0")))
    return {
        "requests": requests,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "incremental_requests": requests - start_requests,
        "incremental_input_tokens": input_tokens - start_input,
        "incremental_output_tokens": output_tokens - start_output,
        "incremental_cost_cny": str(incremental_cost.quantize(Decimal("0.000001"))),
        "estimated_console_total_cny": str(
            (console_baseline + incremental_cost).quantize(Decimal("0.000001"))
        ),
        "pricing_identity": authorization.get("pricing_identity"),
        "additional_max_requests": authorization.get("additional_max_requests"),
        "additional_max_input_tokens": authorization.get("additional_max_input"),
        "additional_max_output_tokens": authorization.get("additional_max_output"),
        "additional_max_cost_cny": authorization.get("additional_max_cost_cny"),
        "console_baseline_cny": authorization.get("console_baseline_cny"),
        "console_total_cap_cny": authorization.get("console_total_cap_cny"),
        "failed_billable_or_unknown_invocations": len(saved.get("failed_invocations", [])),
    }


def run_provider_pilot(
    *,
    output_dir: Path,
    additional_max_input: int = 230_000,
    additional_max_output: int = 90_000,
    additional_max_requests: int = 32,
    additional_max_cost_cny: Decimal = Decimal("0.80"),
    console_baseline_cny: Decimal = Decimal("1.02"),
    console_total_cap_cny: Decimal = Decimal("1.82"),
    enforce_off_peak: bool = True,
    manual_retry_request_sha256s: frozenset[str] = frozenset(),
    approved_previous_additional_max_output: int | None = None,
    refresh_derived_reports: bool = False,
) -> dict[str, Any]:
    dataset = json.loads(
        Path("datasets/coursepilot_eval/v1/approved/cp_ds3/p16_ppt_pilot.json").read_text(
            encoding="utf-8"
        )
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    checkpoint = _BudgetCheckpoint(
        additional_max_input=additional_max_input,
        additional_max_output=additional_max_output,
        additional_max_requests=additional_max_requests,
        additional_max_cost_cny=additional_max_cost_cny,
        console_baseline_cny=console_baseline_cny,
        console_total_cap_cny=console_total_cap_cny,
        path=output_dir / "checkpoint.json",
        enforce_off_peak=enforce_off_peak,
        manual_retry_request_sha256s=manual_retry_request_sha256s,
        approved_previous_additional_max_output=approved_previous_additional_max_output,
    )
    progress_path = output_dir / "progress.json"
    progress = (
        json.loads(progress_path.read_text(encoding="utf-8")) if progress_path.is_file() else {}
    )
    case_reports: list[dict[str, Any]] = list(progress.get("case_reports", []))
    if refresh_derived_reports:
        refreshed_reports: list[dict[str, Any]] = []
        for case_report in case_reports:
            artifact = PPTArtifact.model_validate(case_report["artifact"])
            validation = validate_ppt_artifact(
                artifact,
                valid_evidence_ids=set(artifact.architecture.context_evidence_ids),
            )
            path = output_dir / f"{case_report['record_id']}.pptx"
            render = inspect_renderable_pptx(
                path, expected_slide_count=artifact.architecture.slide_count
            )
            refreshed_reports.append(
                {
                    **case_report,
                    "validation_passed": validation.passed,
                    "render_passed": render.passed,
                    "validation_report": validation.model_dump(mode="json"),
                    "render_report": render.model_dump(mode="json"),
                }
            )
        case_reports = refreshed_reports
        _write_json_atomic(
            progress_path,
            {
                "completed_cases": [item["record_id"] for item in case_reports],
                "case_reports": case_reports,
                "budget": checkpoint.summary(),
            },
        )
    completed_ids = set(progress.get("completed_cases", []))
    with collect_coursepilot_llm_metadata(
        thread_id="p16-provider-pilot", checkpoint=checkpoint
    ) as collector:
        for case in dataset["cases"]:
            if case["record_id"] in completed_ids:
                continue
            targets = case["slide_targets"]
            evidence_records = [
                snapshot for target in targets for snapshot in target.get("evidence_snapshots", [])
            ]
            evidence_records = list(
                {str(item.get("evidence_id")): item for item in evidence_records}.values()
            )
            evidence_ids = [str(item.get("evidence_id")) for item in evidence_records]
            architecture = PPTGenerator(use_model=True).build_architecture(
                course_id=case["course_id"],
                lesson_artifact_id=case["lesson_artifact_id"],
                template_id=case["template_id"],
                template_snapshot_id=f"p16-{case['record_id']}",
                context_evidence_ids=evidence_ids,
                slide_targets=targets,
            )
            artifact = PPTGenerator(use_model=True).build_artifact(
                architecture, evidence_records=evidence_records
            )
            validation = validate_ppt_artifact(artifact, valid_evidence_ids=set(evidence_ids))
            path = PPTXVersionedExporter().export(
                artifact, output_dir / f"{case['record_id']}.pptx"
            )
            render = inspect_renderable_pptx(
                path, expected_slide_count=artifact.architecture.slide_count
            )
            case_reports.append(
                {
                    "record_id": case["record_id"],
                    "slide_count": artifact.architecture.slide_count,
                    "validation_passed": validation.passed,
                    "render_passed": render.passed,
                    "artifact": artifact.model_dump(mode="json"),
                    "validation_report": validation.model_dump(mode="json"),
                    "render_report": render.model_dump(mode="json"),
                }
            )
            _write_json_atomic(
                progress_path,
                {
                    "completed_cases": [item["record_id"] for item in case_reports],
                    "case_reports": case_reports,
                    "budget": checkpoint.summary(),
                },
            )
    report = {
        "mode": "provider",
        "status": "completed",
        "cases": case_reports,
        "usage": collector.to_task_metadata(),
        "budget": checkpoint.summary(),
    }
    _write_json_atomic(output_dir / "report.json", report)
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=Path("storage_eval/p16_ppt"))
    parser.add_argument("--external-data-authorized", action="store_true")
    parser.add_argument("--provider-pilot", action="store_true")
    parser.add_argument("--additional-max-input", type=int, default=230_000)
    parser.add_argument("--additional-max-output", type=int, default=90_000)
    parser.add_argument("--additional-max-requests", type=int, default=32)
    parser.add_argument("--additional-max-cost-cny", type=Decimal, default=Decimal("0.80"))
    parser.add_argument("--console-baseline-cny", type=Decimal, default=Decimal("1.02"))
    parser.add_argument("--console-total-cap-cny", type=Decimal, default=Decimal("1.82"))
    parser.add_argument(
        "--manual-retry-request-sha256",
        action="append",
        default=[],
        help="Explicitly authorize one retry for an already billed failed request hash.",
    )
    parser.add_argument(
        "--approved-previous-additional-max-output",
        type=int,
        help=(
            "Allow a resume-only output budget increase when this value exactly "
            "matches the output limit stored in the checkpoint."
        ),
    )
    parser.add_argument(
        "--refresh-derived-reports",
        action="store_true",
        help="Recompute local validation/render reports from cached completed artifacts.",
    )
    args = parser.parse_args()
    # This first runner is intentionally offline; real Provider execution is a separate gated step.
    if args.provider_pilot:
        if not args.external_data_authorized:
            parser.error("--provider-pilot requires --external-data-authorized")
        try:
            report = run_provider_pilot(
                output_dir=args.output_dir,
                additional_max_input=args.additional_max_input,
                additional_max_output=args.additional_max_output,
                additional_max_requests=args.additional_max_requests,
                additional_max_cost_cny=args.additional_max_cost_cny,
                console_baseline_cny=args.console_baseline_cny,
                console_total_cap_cny=args.console_total_cap_cny,
                manual_retry_request_sha256s=frozenset(args.manual_retry_request_sha256),
                approved_previous_additional_max_output=(
                    args.approved_previous_additional_max_output
                ),
                refresh_derived_reports=args.refresh_derived_reports,
            )
        except Exception as exc:
            checkpoint_path = args.output_dir / "checkpoint.json"
            checkpoint = (
                json.loads(checkpoint_path.read_text(encoding="utf-8"))
                if checkpoint_path.is_file()
                else {}
            )
            progress_path = args.output_dir / "progress.json"
            progress = (
                json.loads(progress_path.read_text(encoding="utf-8"))
                if progress_path.is_file()
                else {}
            )
            report = {
                "mode": "provider",
                "status": "stopped",
                "stop_reason": str(exc),
                "cases": progress.get("case_reports", []),
                "budget": _saved_budget_summary(checkpoint),
            }
            args.output_dir.mkdir(parents=True, exist_ok=True)
            _write_json_atomic(args.output_dir / "report.json", report)
    else:
        report = run_offline(output_dir=args.output_dir)
    # Keep the CLI usable on Windows consoles that still default to GBK. The
    # canonical report on disk remains UTF-8 with readable Unicode; stdout is
    # only a transport-safe summary representation.
    print(json.dumps(report, ensure_ascii=True))


if __name__ == "__main__":
    main()
