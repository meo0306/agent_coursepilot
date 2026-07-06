"""Readable file names for CoursePilot exports."""

import re


def readable_export_filename(
    *,
    course_name: str | None,
    topic: str | None,
    role: str,
    unique_id: str,
    extension: str,
) -> str:
    parts = [_slug(course_name), _slug(topic), _slug(role)]
    stem = "_".join(part for part in parts if part) or _slug(role)
    short_id = _slug(unique_id)[:8] or "export"
    ext = extension.removeprefix(".")
    return f"{stem}_{short_id}.{ext}"


def _slug(value: str | None) -> str:
    if not value:
        return ""
    normalized = re.sub(r"[^\w\u4e00-\u9fff-]+", "_", value.strip(), flags=re.UNICODE)
    normalized = re.sub(r"_+", "_", normalized).strip("_")
    return normalized[:80]
