"""Versioned CoursePilot template registry."""

from coursepilot.templates.models import TemplateDefinition, TemplateSnapshot
from coursepilot.templates.registry import TemplateRegistry

__all__ = ["TemplateDefinition", "TemplateRegistry", "TemplateSnapshot"]
