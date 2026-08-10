from courserag.evidence.migration import (
    CitationMigrationRequest,
    MigrationEvidence,
    P10CitationMigrator,
)


class Source:
    def __init__(self, origin: MigrationEvidence, targets: list[MigrationEvidence]):
        self.origin = origin
        self.targets = targets

    def get_source(self, course_id: str, evidence_id: str) -> MigrationEvidence | None:
        return self.origin if evidence_id == self.origin.evidence_id else None

    def list_target(self, course_id: str, document_version_id: str):
        return [item for item in self.targets if item.document_version_id == document_version_id]


def _evidence(evidence_id: str, version: str, text: str, digest: str, path=("1",)):
    return MigrationEvidence(
        evidence_id=evidence_id,
        document_version_id=version,
        text=text,
        content_sha256=digest * 64,
        section_path=path,
    )


def _request() -> CitationMigrationRequest:
    return CitationMigrationRequest(
        course_id="course",
        reference_type="evidence",
        reference_id="old",
        source_document_version_id="v1",
        target_document_version_id="v2",
    )


def test_unique_exact_hash_migrates() -> None:
    origin = _evidence("old", "v1", "alpha", "a")
    target = _evidence("new", "v2", "alpha", "a")
    result = P10CitationMigrator(Source(origin, [target])).migrate(_request())
    assert result.status == "migrated"
    assert result.target_evidence_id == "new"
    assert result.method == "exact"


def test_duplicate_exact_hash_requires_review() -> None:
    origin = _evidence("old", "v1", "alpha", "a")
    targets = [_evidence("a", "v2", "alpha", "a"), _evidence("b", "v2", "alpha", "a")]
    result = P10CitationMigrator(Source(origin, targets)).migrate(_request())
    assert result.status == "needs_review"
    assert len(result.candidates) == 2


def test_deleted_or_dissimilar_source_is_invalid() -> None:
    origin = _evidence("old", "v1", "neural network", "a")
    target = _evidence("new", "v2", "unrelated calculus", "b", path=("9",))
    result = P10CitationMigrator(Source(origin, [target])).migrate(_request())
    assert result.status == "invalid"
