from __future__ import annotations

from coursepilot.domain.ppt import SlideContent


def repair_slide_deterministic(slide: SlideContent, *, allowed_paths: set[str]) -> SlideContent:
    """Apply only safe text normalization; never changes identity or citations."""
    if not allowed_paths <= {"$.title", "$.bullets", "$.body_text", "$.speaker_notes", "$.assets"}:
        raise ValueError("PPT_REPAIR_PATH_NOT_ALLOWED")
    updates: dict[str, object] = {}
    if "$.title" in allowed_paths:
        updates["title"] = slide.title.strip()
    if "$.bullets" in allowed_paths:
        updates["bullets"] = [item.strip() for item in slide.bullets if item.strip()]
    if "$.body_text" in allowed_paths:
        updates["body_text"] = slide.body_text.strip()
    if "$.speaker_notes" in allowed_paths:
        updates["speaker_notes"] = slide.speaker_notes.strip()
    return slide.model_copy(update=updates)
