from __future__ import annotations

from copy import deepcopy
from typing import Any

from coursepilot.repair.models import PatchOperation


class PatchApplyError(ValueError):
    pass


def _parts(path: str) -> list[str | int]:
    if not path.startswith("$"):
        raise PatchApplyError("JSON path must start with $")
    result: list[str | int] = []
    index = 1
    while index < len(path):
        if path[index] == ".":
            index += 1
            start = index
            while index < len(path) and path[index] not in ".[":
                index += 1
            if start == index:
                raise PatchApplyError(f"invalid path: {path}")
            result.append(path[start:index])
        elif path[index] == "[":
            end = path.find("]", index)
            if end < 0:
                raise PatchApplyError(f"invalid path: {path}")
            value = path[index + 1 : end]
            if not value.isdigit():
                raise PatchApplyError("only numeric array indexes are supported")
            result.append(int(value))
            index = end + 1
        else:
            raise PatchApplyError(f"invalid path: {path}")
    return result


def _get(root: Any, parts: list[str | int]) -> Any:
    value = root
    for part in parts:
        value = value[part]
    return value


def _parent(root: Any, parts: list[str | int]) -> tuple[Any, str | int]:
    if not parts:
        raise PatchApplyError("root replacement is forbidden")
    return _get(root, parts[:-1]), parts[-1]


def _allowed(path: str, allowed: list[str]) -> bool:
    return path in allowed


def apply_patch(
    document: dict[str, Any],
    operations: list[PatchOperation],
    *,
    allowed_paths: list[str],
    forbidden_paths: list[str] | None = None,
) -> dict[str, Any]:
    forbidden = set(forbidden_paths or [])
    candidate = deepcopy(document)
    for operation in operations:
        if not _allowed(operation.path, allowed_paths) or operation.path in forbidden:
            raise PatchApplyError(f"path is not allowed: {operation.path}")
        parts = _parts(operation.path)
        parent, key = _parent(candidate, parts)
        exists = (
            isinstance(parent, dict)
            and key in parent
            or isinstance(parent, list)
            and isinstance(key, int)
            and key < len(parent)
        )
        if operation.expected_value is not None:
            if not exists or parent[key] != operation.expected_value:
                raise PatchApplyError(f"precondition failed: {operation.path}")
        if operation.op == "add" or operation.op == "replace":
            if isinstance(parent, list) and not isinstance(key, int):
                raise PatchApplyError("array patch requires numeric index")
            parent[key] = deepcopy(operation.value)
        elif operation.op == "remove":
            if not exists:
                raise PatchApplyError(f"missing path: {operation.path}")
            del parent[key]
    return candidate
