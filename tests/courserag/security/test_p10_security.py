from __future__ import annotations

import io
import zipfile

import pytest

from courserag.security import (
    DocumentSecurityPolicy,
    PrincipalRole,
    TrustedPrincipal,
    redact_secrets,
    require_course_role,
)


def _docx(entry_name: str = "word/document.xml", body: bytes = b"<doc/>") -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(entry_name, body)
    return output.getvalue()


def test_mime_path_and_zip_traversal_fail_closed() -> None:
    policy = DocumentSecurityPolicy()
    with pytest.raises(ValueError, match="MIME_MISMATCH"):
        policy.inspect(filename="x.pdf", declared_mime="application/pdf", content=_docx())
    with pytest.raises(ValueError, match="UNSAFE_PATH"):
        policy.inspect(
            filename="../x.docx",
            declared_mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            content=_docx(),
        )
    with pytest.raises(ValueError, match="UNSAFE_ARCHIVE_PATH"):
        policy.inspect(
            filename="x.docx",
            declared_mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            content=_docx("../evil.xml"),
        )


def test_acl_and_redaction() -> None:
    principal = TrustedPrincipal(
        principal_id="p1", course_id="course-1", roles={PrincipalRole.EDITOR}
    )
    require_course_role(principal, "course-1", PrincipalRole.READER)
    with pytest.raises(PermissionError):
        require_course_role(principal, "course-2", PrincipalRole.READER)
    with pytest.raises(PermissionError):
        require_course_role(principal, "course-1", PrincipalRole.OWNER)
    value = redact_secrets("api_key=secret-value Authorization: Bearer-abc sk-123456789")
    assert "secret-value" not in value
    assert "Bearer-abc" not in value
    assert "sk-123456789" not in value


def test_runtime_resource_limits() -> None:
    policy = DocumentSecurityPolicy(max_ocr_dpi=300, parse_timeout_seconds=10)
    policy.validate_runtime_limits(dpi=300, elapsed_seconds=10)
    with pytest.raises(ValueError, match="DPI_LIMIT"):
        policy.validate_runtime_limits(dpi=301, elapsed_seconds=1)
    with pytest.raises(TimeoutError, match="PARSE_TIMEOUT"):
        policy.validate_runtime_limits(dpi=200, elapsed_seconds=11)
