"""Versioned CoursePilot template registry."""

from coursepilot.templates.models import TemplateDefinition, TemplateSnapshot
from coursepilot.templates.ppt import (
    PPTLayoutProfile,
    PPTTemplateProfile,
    PPTTemplateSnapshot,
    apply_mapping,
    inspect_pptx,
)
from coursepilot.templates.registry import TemplateRegistry

__all__ = [
    "PPTLayoutProfile",
    "PPTTemplateProfile",
    "PPTTemplateSnapshot",
    "TemplateDefinition",
    "TemplateRegistry",
    "TemplateSnapshot",
    "apply_mapping",
    "inspect_pptx",
]
