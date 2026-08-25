"""P18 orchestration and durable budget/checkpoint contracts."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import shutil
import threading
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, time
from decimal import Decimal
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from coursepilot.evals.p18_metrics import aggregate_run_rows
from coursepilot.llm import CoursePilotLLMBudgetExceeded
from evaluation.datasets import canonical_json_bytes
from evaluation.p18_loader import P18LoadedSplit, load_p18_dev, load_p18_test


class P18BudgetExceeded(CoursePilotLLMBudgetExceeded):
    pass


class P18ProviderPeakPause(CoursePilotLLMBudgetExceeded):
    pass


BEIJING = ZoneInfo("Asia/Shanghai")


def is_provider_off_peak(now: datetime | None = None) -> bool:
    current = (now or datetime.now(tz=BEIJING)).astimezone(BEIJING)
    if current.weekday() >= 5:
        return True
    local_time = current.time().replace(tzinfo=None)
    return not (time(9, 0) <= local_time < time(12, 0) or time(14, 0) <= local_time < time(18, 0))


def require_provider_off_peak(now: datetime | None = None) -> None:
    if not is_provider_off_peak(now):
        raise P18ProviderPeakPause("P18_PROVIDER_PAUSED_PEAK_PERIOD")


@dataclass(frozen=True)
class P18Budget:
    max_cost_cny: Decimal = Decimal("5")
    max_input_tokens: int = 2_000_000
    max_output_tokens: int = 1_500_000
    max_requests: int = 300
    cache_miss_input_cny_per_million: Decimal = Decimal("1")
    output_cny_per_million: Decimal = Decimal("2")


P18_FORMAL_TEST_BUDGET = P18Budget(
    max_cost_cny=Decimal("4.00"),
    max_input_tokens=1_200_000,
    max_output_tokens=1_200_000,
    max_requests=260,
)


class P18Ledger:
    def __init__(
        self,
        path: Path,
        budget: P18Budget,
        *,
        resume: bool,
        provider_window_guard: Callable[[], None] | None = None,
    ) -> None:
        self.path, self.budget = path, budget
        self.provider_window_guard = provider_window_guard
        self._lock = threading.RLock()
        if path.exists():
            if not resume:
                raise RuntimeError("P18 checkpoint exists; pass resume=True")
            self.data = json.loads(path.read_text(encoding="utf-8"))
            if self.data["budget"] != _budget_json(budget):
                raise RuntimeError("P18 resume budget identity mismatch")
            if self._drop_unsent_failures_unlocked():
                self._save()
        else:
            self.data = {
                "schema_version": "coursepilot.p18-ledger.v1",
                "budget": _budget_json(budget),
                "requests": {},
            }
            self._save()

    def reserve(self, identity: str, estimated_input: int, max_output: int) -> None:
        with self._lock:
            if identity in self.data["requests"]:
                item = self.data["requests"][identity]
                if item.get("response") is not None:
                    return
                raise P18BudgetExceeded("P18_AMBIGUOUS_REQUEST_PENDING_RECONCILIATION")
            totals = self._totals_unlocked()
            requests = totals["requests"] + 1
            input_tokens = totals["input_tokens"] + estimated_input
            output_tokens = totals["output_tokens"] + max_output
            cost = _cost(input_tokens, output_tokens, self.budget)
            if (
                requests > self.budget.max_requests
                or input_tokens > self.budget.max_input_tokens
                or output_tokens > self.budget.max_output_tokens
                or cost > self.budget.max_cost_cny
            ):
                raise P18BudgetExceeded("P18 provider hard budget would be exceeded")
            self.data["requests"][identity] = {
                "status": "reserved",
                "reserved_at": datetime.now(tz=UTC).isoformat(),
                "estimated_input_tokens": estimated_input,
                "max_output_tokens": max_output,
            }
            self._save()

    def load(self, request_sha256: str) -> dict[str, Any] | None:
        with self._lock:
            item = self.data["requests"].get(request_sha256)
            if item and item.get("response") is not None:
                return item.get("response")
            return None

    def seed_successful_responses(self, source_path: Path, *, thread_id: str) -> int:
        """Reuse completed responses from an immutable prior run without rebilling them."""

        source = json.loads(source_path.read_text(encoding="utf-8"))
        copied = 0
        with self._lock:
            for identity, item in source.get("requests", {}).items():
                invocation = item.get("invocation") or {}
                if invocation.get("thread_id") != thread_id or item.get("response") is None:
                    continue
                existing = self.data["requests"].get(identity)
                if existing is not None and existing.get("response") != item.get("response"):
                    raise RuntimeError("P18 carried response checkpoint conflict")
                if existing is None:
                    self.data["requests"][identity] = {
                        **item,
                        "status": "cached_prior_run",
                        "carried_from_prior_run": True,
                    }
                    copied += 1
            if copied:
                self._save()
        return copied

    def save(self, request_sha256: str, payload: dict[str, Any]) -> None:
        with self._lock:
            item = self.data["requests"].setdefault(request_sha256, {})
            existing = item.get("response")
            if existing is not None and existing != payload:
                raise RuntimeError("P18 response checkpoint conflict")
            item["response"] = payload
            self._save()

    def authorize_request(
        self,
        *,
        request_sha256: str,
        prompt_name: str,
        profile_id: str,
        estimated_input_tokens: int,
        configured_max_output_tokens: int,
    ) -> None:
        del prompt_name, profile_id
        if self.provider_window_guard is not None:
            self.provider_window_guard()
        self.reserve(request_sha256, estimated_input_tokens, configured_max_output_tokens)

    def record_invocation(self, invocation: dict[str, Any]) -> None:
        request_sha256 = invocation.get("request_sha256")
        if not isinstance(request_sha256, str):
            return
        with self._lock:
            if (
                invocation.get("status") == "failed"
                and not invocation.get("provider_called")
                and request_sha256 not in self.data["requests"]
            ):
                return
            item = self.data["requests"].setdefault(request_sha256, {})
            item["invocation"] = {
                key: value
                for key, value in invocation.items()
                if key not in {"raw_response", "error_message"}
            }
            usage = invocation.get("usage") or {}
            input_tokens = int(usage.get("input_tokens", usage.get("prompt_tokens", 0)) or 0)
            output_tokens = int(usage.get("output_tokens", usage.get("completion_tokens", 0)) or 0)
            status = invocation.get("status")
            if status == "success" and item.get("response") is not None:
                item.update(
                    status="succeeded", input_tokens=input_tokens, output_tokens=output_tokens
                )
            elif status == "cached" and item.get("response") is not None:
                item["status"] = "succeeded"
            elif status == "failed":
                item["status"] = "failed_billable_or_unknown"
                item["input_tokens"] = input_tokens
                item["output_tokens"] = output_tokens
            self._save()

    def settle(
        self, identity: str, *, input_tokens: int, output_tokens: int, response_sha256: str
    ) -> None:
        with self._lock:
            item = self.data["requests"][identity]
            item.update(
                status="succeeded",
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                response_sha256=response_sha256,
            )
            self._save()

    def totals(self) -> dict[str, Any]:
        with self._lock:
            return self._totals_unlocked()

    def _totals_unlocked(self) -> dict[str, Any]:
        items = [
            item
            for item in self.data["requests"].values()
            if not item.get("carried_from_prior_run")
        ]
        inp = sum(int(x.get("input_tokens", x.get("estimated_input_tokens", 0))) for x in items)
        out = sum(int(x.get("output_tokens", x.get("max_output_tokens", 0))) for x in items)
        return {
            "requests": len(items),
            "input_tokens": inp,
            "output_tokens": out,
            "cost_cny": str(_cost(inp, out, self.budget)),
        }

    def _save(self) -> None:
        _atomic_json(self.path, self.data)

    def _drop_unsent_failures_unlocked(self) -> bool:
        removable = [
            identity
            for identity, item in self.data.get("requests", {}).items()
            if item.get("response") is None
            and item.get("invocation", {}).get("status") == "failed"
            and not item.get("invocation", {}).get("provider_called")
            and "estimated_input_tokens" not in item
        ]
        for identity in removable:
            self.data["requests"].pop(identity, None)
        return bool(removable)


def run_p18(
    *,
    repository_root: Path,
    output_dir: Path,
    mode: str,
    executor: Callable[[Any, str, P18Ledger], dict[str, Any]],
    resume: bool = False,
    budget: P18Budget | None = None,
) -> dict[str, Any]:
    if mode == "test":
        from evaluation.p18_test_release import validate_test_execution_authorization

        validate_test_execution_authorization(repository_root=repository_root)
    dataset_root = repository_root / "datasets/coursepilot_eval/v1"
    loaded: P18LoadedSplit = (
        load_p18_dev(dataset_root) if mode == "dev" else load_p18_test(dataset_root)
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    ledger = P18Ledger(output_dir / "ledger.json", budget or P18Budget(), resume=resume)
    checkpoint_path = output_dir / "rows.json"
    rows = (
        json.loads(checkpoint_path.read_text(encoding="utf-8"))
        if resume and checkpoint_path.exists()
        else []
    )
    done = {(x["component"], x["record_id"], x["track"]) for x in rows}
    for component in ("cp_ds1", "cp_ds2", "cp_ds3"):
        for case in loaded.components[component]:
            for track in ("cp_b0", "cp_b10"):
                key = (component, getattr(case, "record_id"), track)
                if key in done:
                    continue
                row = executor(case, track, ledger)
                row.update(component=component, record_id=key[1], track=track)
                rows.append(row)
                _atomic_json(checkpoint_path, rows)
    report = {
        "mode": mode,
        "loaded_records": loaded.record_count,
        "ledger": ledger.totals(),
        "metrics": aggregate_run_rows(rows),
        "rows_path": str(checkpoint_path),
    }
    _atomic_json(output_dir / "report.json", report)
    return report


def prepare_dev_revision_checkpoint(*, source_dir: Path, target_dir: Path) -> dict[str, Any]:
    """Carry forward r1 and reopen only successful B10 rows that failed validation.

    Provider/schema failures and all legacy B0 observations remain immutable.  The
    revision therefore exercises only the pre-registered bounded repair path.
    """

    if target_dir.exists():
        raise RuntimeError("P18 revision target already exists")
    rows = json.loads((source_dir / "rows.json").read_text(encoding="utf-8"))
    reopened = [
        (row["component"], row["record_id"], row["track"])
        for row in rows
        if row["track"] == "cp_b10"
        and row.get("status") == "succeeded"
        and not row.get("contract_pass")
    ]
    carried = [
        row
        for row in rows
        if (row["component"], row["record_id"], row["track"]) not in set(reopened)
    ]
    target_dir.mkdir(parents=True)
    shutil.copy2(source_dir / "ledger.json", target_dir / "ledger.json")
    _atomic_json(target_dir / "rows.json", carried)
    manifest = {
        "schema_version": "coursepilot.p18-dev-revision.v1",
        "source_dir": str(source_dir.resolve()),
        "source_rows": len(rows),
        "carried_rows": len(carried),
        "reopened_rows": [
            {"component": component, "record_id": record_id, "track": track}
            for component, record_id, track in reopened
        ],
        "policy": "successful_cp_b10_contract_failures_only",
        "test_access": False,
    }
    _atomic_json(target_dir / "revision_manifest.json", manifest)
    return manifest


def request_identity(payload: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()


def build_dev_preflight(
    *, repository_root: Path, output_path: Path, budget: P18Budget | None = None
) -> dict[str, Any]:
    """Estimate the approved Dev run without invoking any Provider."""

    selected_budget = budget or P18Budget()
    loaded = load_p18_dev(repository_root / "datasets/coursepilot_eval/v1")
    requests = 0
    estimated_input = 0
    estimated_output = 0
    by_component: dict[str, dict[str, int]] = {}
    for component in ("cp_ds1", "cp_ds2", "cp_ds3"):
        component_requests = 0
        for case in loaded.components[component]:
            base_input = max(len(canonical_json_bytes(case.model_dump(mode="json"))) // 3, 800)
            if component == "cp_ds1":
                units = int(getattr(case, "total_sessions"))
                calls = 3 + 1 + units
            elif component == "cp_ds2":
                units = int(getattr(case, "question_count"))
                calls = 3 + 1 + math.ceil(units / 5)
            else:
                units = int(getattr(case, "slide_count"))
                calls = 2 + 1 + units
            component_requests += calls
            estimated_input += calls * (base_input + 2400)
            estimated_output += calls * 2200
        requests += component_requests
        by_component[component] = {
            "requests": component_requests,
            "cases": len(loaded.components[component]),
        }
    # MR-0/MR-1 on three tasks plus bounded repair reserve.
    requests += 18
    estimated_input = int(estimated_input * 1.3)
    estimated_output = int(estimated_output * 1.3)
    estimated_cost = _cost(estimated_input, estimated_output, selected_budget)
    payload = {
        "schema_version": "coursepilot.p18-dev-preflight.v1",
        "external_calls_executed": 0,
        "test_access": False,
        "approved_dev_records": loaded.record_count,
        "provider": "openai-compatible",
        "model": "configured_deepseek_v4_flash",
        "data_scope": "approved Dev tasks plus bounded KP/Evidence only; no Gold labels, Test, identity, or Secret",
        "estimate": {
            "requests": requests,
            "input_tokens": estimated_input,
            "output_and_thinking_tokens": estimated_output,
            "cost_cny_cache_miss_upper_estimate": str(estimated_cost),
        },
        "hard_limits": _budget_json(selected_budget),
        "authorization_required": True,
        "components": by_component,
    }
    _atomic_json(output_path, payload)
    payload["protocol_sha256"] = hashlib.sha256(output_path.read_bytes()).hexdigest()
    return payload


def _cost(inp: int, out: int, budget: P18Budget) -> Decimal:
    return (
        Decimal(inp) * budget.cache_miss_input_cny_per_million
        + Decimal(out) * budget.output_cny_per_million
    ) / Decimal(1_000_000)


def _budget_json(budget: P18Budget) -> dict[str, Any]:
    return {
        "max_cost_cny": str(budget.max_cost_cny),
        "max_input_tokens": budget.max_input_tokens,
        "max_output_tokens": budget.max_output_tokens,
        "max_requests": budget.max_requests,
    }


def _atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the approved P18 Track-A evaluation")
    parser.add_argument("--repository-root", type=Path, default=Path.cwd())
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--mode", choices=("dev", "test"), default="dev")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--revision-from", type=Path)
    execution = parser.add_mutually_exclusive_group(required=True)
    execution.add_argument("--offline-smoke", action="store_true")
    execution.add_argument("--real-provider", action="store_true")
    args = parser.parse_args()

    from evaluation.p18_case_adapters import P18TrackAExecutor

    if args.revision_from is not None:
        if args.mode != "dev" or not args.real_provider or args.resume:
            parser.error("--revision-from requires a fresh real-provider Dev run")
        prepare_dev_revision_checkpoint(
            source_dir=args.revision_from.resolve(), target_dir=args.output_dir.resolve()
        )
        args.resume = True

    report = run_p18(
        repository_root=args.repository_root.resolve(),
        output_dir=args.output_dir.resolve(),
        mode=args.mode,
        executor=P18TrackAExecutor(
            repository_root=args.repository_root.resolve(),
            use_provider=args.real_provider,
        ),
        resume=args.resume,
        budget=P18_FORMAL_TEST_BUDGET if args.mode == "test" else None,
    )
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
