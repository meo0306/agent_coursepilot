"""Trusted gateway identity contracts shared by application services."""

from core.security.principal import PrincipalRole, TrustedPrincipal, require_course_role

__all__ = ["PrincipalRole", "TrustedPrincipal", "require_course_role"]
