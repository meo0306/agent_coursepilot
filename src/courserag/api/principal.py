from __future__ import annotations

from typing import Annotated

from fastapi import Header

from courserag.api.knowledge_points import CourseRAGAPIError
from courserag.contracts import ErrorResponse, RequestContext, ResponseMeta
from courserag.security import TrustedPrincipal


def trusted_principal(
    principal_id: Annotated[str | None, Header(alias="X-CoursePilot-Principal-ID")] = None,
    authorized_course_id: Annotated[str | None, Header(alias="X-CoursePilot-Course-ID")] = None,
    roles: Annotated[str | None, Header(alias="X-CoursePilot-Roles")] = None,
) -> TrustedPrincipal:
    try:
        return TrustedPrincipal.from_gateway_headers(
            principal_id=principal_id,
            course_id=authorized_course_id,
            roles=roles,
        )
    except (PermissionError, ValueError) as exc:
        context = RequestContext()
        response = ErrorResponse.model_validate(
            {
                "meta": ResponseMeta.from_context(context).model_dump(mode="json"),
                "error": {"code": "FORBIDDEN", "message": str(exc)},
            }
        )
        raise CourseRAGAPIError(403, response) from exc
