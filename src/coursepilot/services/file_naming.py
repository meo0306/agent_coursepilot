"""
生成可读的导出文件名，只把 UUID 作为短后缀保留
"""

import re


def readable_export_filename(
    *,
    course_name: str | None,
    topic: str | None,
    role: str,
    unique_id: str,
    extension: str,
) -> str:
    # course_name: 课程名，例如 AI Search。
    # topic: 章节/主题，例如 Chapter 1。
    # role: 文件用途，例如 lesson_design、student_exam、ppt_outline。
    parts = [_slug(course_name), _slug(topic), _slug(role)]
    # 过滤空值后用下划线拼接。
    # 如果课程名和主题都缺失，至少保留 role。
    stem = "_".join(part for part in parts if part) or _slug(role)
    # UUID 不再作为主体文件名，只截取前 8 位作为短后缀
    short_id = _slug(unique_id)[:8] or "export"
    ext = extension.removeprefix(".")
    return f"{stem}_{short_id}.{ext}"


def _slug(value: str | None) -> str:
    if not value:
        return ""
    normalized = re.sub(r"[^\w\u4e00-\u9fff-]+", "_", value.strip(), flags=re.UNICODE)
    normalized = re.sub(r"_+", "_", normalized).strip("_")
    return normalized[:80]
