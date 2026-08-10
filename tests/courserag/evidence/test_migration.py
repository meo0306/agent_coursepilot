from pathlib import Path

from courserag.evidence.migration import CitationMigrationRequest, P06CitationMigrationSkeleton
from tests.courserag.evidence.test_resolver import _resolver


def test_citation_migration_skeleton_rejects_legacy_and_defers_cross_version(
    tmp_path: Path,
) -> None:
    resolver, ids = _resolver(tmp_path)
    migration = P06CitationMigrationSkeleton(resolver)

    legacy = migration.migrate(
        CitationMigrationRequest(
            course_id="course-1",
            reference_type="legacy_chunk",
            reference_id="old-chunk",
            source_document_version_id="version-1",
            target_document_version_id="version-1",
        )
    )
    deferred = migration.migrate(
        CitationMigrationRequest(
            course_id="course-1",
            reference_type="evidence",
            reference_id=ids[0],
            source_document_version_id="version-1",
            target_document_version_id="version-2",
        )
    )
    valid = migration.migrate(
        CitationMigrationRequest(
            course_id="course-1",
            reference_type="evidence",
            reference_id=ids[0],
            source_document_version_id="version-1",
            target_document_version_id="version-1",
        )
    )

    assert legacy.reason_code == "LEGACY_CHUNK_IS_NOT_EVIDENCE"
    assert deferred.status == "needs_review"
    assert valid.status == "valid"
    assert valid.target_evidence_id == ids[0]
