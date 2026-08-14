from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any

from coursepilot.domain.common import canonical_sha256
from coursepilot.domain.runtime import CommonGraphState, NodeResult

_SECRET_KEYS = frozenset(
    {
        "api_key",
        "apikey",
        "authorization",
        "password",
        "secret",
        "token",
        "access_token",
        "refresh_token",
    }
)


def node_fingerprint(
    *,
    node_name: str,
    inputs: Mapping[str, object],
    template_hash: str,
    model_profile_hash: str | None,
    context_hashes: Sequence[str] = (),
) -> str:
    return canonical_sha256(
        {
            "node_name": node_name,
            "inputs": inputs,
            "template_hash": template_hash,
            "model_profile_hash": model_profile_hash,
            "context_hashes": sorted(context_hashes),
        }
    )


def can_reuse_node(result: NodeResult, fingerprint: str) -> bool:
    return result.reusable and result.input_fingerprint == fingerprint


def compact_state(state: CommonGraphState, *, max_summary_chars: int = 2000) -> CommonGraphState:
    """Return a bounded, secret-free representation suitable for a checkpoint."""

    request = _sanitize(state.get("request", {}), depth=0)
    summaries = {
        key: value[:max_summary_chars] for key, value in state.get("summaries", {}).items()
    }
    compacted: CommonGraphState = {
        "run_context": state["run_context"],
        "request": request if isinstance(request, dict) else {},
        "artifacts": dict(state.get("artifacts", {})),
        "context_packages": dict(state.get("context_packages", {})),
        "node_results": list(state.get("node_results", [])),
        "warnings": list(state.get("warnings", [])),
        "summaries": summaries,
    }
    if "error" in state:
        error = _sanitize(state.get("error"), depth=0)
        compacted["error"] = error if isinstance(error, dict) else None
    _assert_no_secret_material(compacted)
    return compacted


def _sanitize(value: Any, *, depth: int) -> Any:
    if depth > 8:
        return "<compacted>"
    if isinstance(value, Mapping):
        return {
            str(key): _sanitize(item, depth=depth + 1)
            for key, item in value.items()
            if str(key).lower() not in _SECRET_KEYS
            and str(key).lower() not in {"messages", "raw_messages", "raw_response"}
        }
    if isinstance(value, list):
        return [_sanitize(item, depth=depth + 1) for item in value[:100]]
    if isinstance(value, str) and len(value) > 4000:
        return f"<content-ref:{canonical_sha256(value)}>"
    return value


def _assert_no_secret_material(value: object) -> None:
    serialized = json.dumps(value, ensure_ascii=False, default=str).lower()
    if any(f'"{key}"' in serialized for key in _SECRET_KEYS):
        raise ValueError("compacted state contains a secret-bearing field")
