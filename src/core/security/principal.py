from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class PrincipalRole(StrEnum):
    READER = "reader"
    EDITOR = "editor"
    OWNER = "owner"
    SYSTEM = "system"


class TrustedPrincipal(BaseModel):
    """Identity claim supplied by the trusted gateway boundary."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    principal_id: str = Field(min_length=1)
    course_id: str = Field(min_length=1)
    roles: frozenset[PrincipalRole] = Field(min_length=1)

    @classmethod
    def from_gateway_headers(
        cls,
        *,
        principal_id: str | None,
        course_id: str | None,
        roles: str | None,
    ) -> TrustedPrincipal:
        if not principal_id or not course_id or not roles:
            raise PermissionError("Trusted identity headers are required")
        parsed_roles = frozenset(
            PrincipalRole(value.strip().lower()) for value in roles.split(",") if value.strip()
        )
        return cls(
            principal_id=principal_id.strip(),
            course_id=course_id.strip(),
            roles=parsed_roles,
        )


_ROLE_LEVEL = {
    PrincipalRole.READER: 1,
    PrincipalRole.EDITOR: 2,
    PrincipalRole.OWNER: 3,
    PrincipalRole.SYSTEM: 4,
}


def require_course_role(
    principal: TrustedPrincipal,
    course_id: str,
    minimum_role: PrincipalRole,
) -> None:
    if principal.course_id != course_id:
        raise PermissionError("Principal is not authorized for this course")
    if max((_ROLE_LEVEL[role] for role in principal.roles), default=0) < _ROLE_LEVEL[minimum_role]:
        raise PermissionError(f"Role {minimum_role.value} or higher is required")
