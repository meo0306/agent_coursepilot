from __future__ import annotations

import hashlib
import os
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path


@dataclass(frozen=True)
class StoredArtifact:
    uri: str
    sha256: str
    size_bytes: int
    media_type: str


class ArtifactIntegrityError(RuntimeError):
    pass


class FileArtifactStore:
    """Content-addressed store whose public URI never exposes a host path."""

    URI_PREFIX = "artifact://sha256/"

    def __init__(self, root: Path) -> None:
        self.root = root.resolve()

    def put(self, content: bytes, *, media_type: str) -> StoredArtifact:
        digest = hashlib.sha256(content).hexdigest()
        target = self._path(digest)
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            existing = target.read_bytes()
            if hashlib.sha256(existing).hexdigest() != digest:
                raise ArtifactIntegrityError(
                    f"Existing artifact is corrupt: {self.URI_PREFIX}{digest}"
                )
        else:
            fd, temporary_name = tempfile.mkstemp(prefix=".p03-", dir=target.parent)
            try:
                with os.fdopen(fd, "wb") as output:
                    output.write(content)
                    output.flush()
                    os.fsync(output.fileno())
                os.replace(temporary_name, target)
            finally:
                if os.path.exists(temporary_name):
                    os.unlink(temporary_name)
        return StoredArtifact(
            uri=f"{self.URI_PREFIX}{digest}",
            sha256=digest,
            size_bytes=len(content),
            media_type=media_type,
        )

    def read(self, uri: str, *, expected_sha256: str | None = None) -> bytes:
        digest = self._digest(uri)
        content = self._path(digest).read_bytes()
        actual = hashlib.sha256(content).hexdigest()
        if actual != digest or (expected_sha256 is not None and actual != expected_sha256):
            raise ArtifactIntegrityError(f"Artifact hash mismatch for {uri}")
        return content

    def verify(self, uri: str, expected_sha256: str) -> bool:
        try:
            self.read(uri, expected_sha256=expected_sha256)
        except (FileNotFoundError, ArtifactIntegrityError):
            return False
        return True

    def delete(self, uri: str) -> bool:
        path = self._path(self._digest(uri))
        if not path.exists():
            return False
        path.unlink()
        return True

    def list_physical_orphans(
        self, known_uris: set[str], *, older_than: datetime
    ) -> tuple[str, ...]:
        orphans: list[str] = []
        if not self.root.exists():
            return ()
        for path in self.root.rglob("*"):
            if not path.is_file():
                continue
            digest = path.name
            if len(digest) != 64 or any(
                character not in "0123456789abcdef" for character in digest
            ):
                continue
            if path.resolve() != self._path(digest).resolve():
                continue
            uri = f"{self.URI_PREFIX}{digest}"
            modified_at = datetime.fromtimestamp(path.stat().st_mtime, UTC)
            if uri not in known_uris and modified_at < older_than:
                orphans.append(uri)
        return tuple(sorted(orphans))

    def _digest(self, uri: str) -> str:
        if not uri.startswith(self.URI_PREFIX):
            raise ValueError("Unsupported artifact URI")
        digest = uri.removeprefix(self.URI_PREFIX)
        if len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest):
            raise ValueError("Invalid artifact digest")
        return digest

    def _path(self, digest: str) -> Path:
        return self.root / digest[:2] / digest[2:4] / digest
