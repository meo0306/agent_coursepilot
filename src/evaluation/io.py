from __future__ import annotations

import json
import os
import time
from pathlib import Path
from uuid import uuid4

from pydantic import JsonValue

ATOMIC_REPLACE_MAX_ATTEMPTS = 10
ATOMIC_REPLACE_BASE_DELAY_SECONDS = 0.025
ATOMIC_REPLACE_MAX_DELAY_SECONDS = 0.5


def atomic_write_json(path: Path, payload: JsonValue) -> None:
    text = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    atomic_write_text(path, text)


def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        with temporary.open("w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        _replace_with_retry(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _replace_with_retry(source: Path, destination: Path) -> None:
    for attempt in range(ATOMIC_REPLACE_MAX_ATTEMPTS):
        try:
            os.replace(source, destination)
            return
        except PermissionError:
            if attempt + 1 >= ATOMIC_REPLACE_MAX_ATTEMPTS:
                raise
            delay = min(
                ATOMIC_REPLACE_BASE_DELAY_SECONDS * (2**attempt),
                ATOMIC_REPLACE_MAX_DELAY_SECONDS,
            )
            time.sleep(delay)
