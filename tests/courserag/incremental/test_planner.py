import pytest

from courserag.incremental import (
    ArtifactKind,
    ChangeKind,
    IncrementalProfileChange,
    SectionSnapshot,
    build_incremental_plan,
)
from courserag.jobs.artifacts import FileArtifactStore
from courserag.jobs.incremental import (
    ArtifactReuseError,
    ReusableArtifact,
    verify_artifact_reuse,
)


def _section(section_id: str, path: str, ordinal: int, digest: str) -> SectionSnapshot:
    return SectionSnapshot(
        section_id=section_id,
        stable_path=path,
        heading=path,
        ordinal=ordinal,
        content_sha256=digest * 64,
        block_sha256=(digest * 64,),
    )


def test_section_diff_reuses_unchanged_and_renamed_content() -> None:
    before = (_section("a", "1", 0, "a"), _section("b", "2", 1, "b"))
    after = (_section("a2", "renamed", 0, "a"), _section("b", "2", 1, "b"))
    plan = build_incremental_plan(
        source_document_id="doc",
        source_version_id="v1",
        target_version_id="v2",
        before=before,
        after=after,
    )
    assert [item.change_kind for item in plan.impacts] == [
        ChangeKind.MOVED_OR_RENAMED,
        ChangeKind.UNCHANGED,
    ]
    assert plan.change_coverage == 1
    assert plan.reused_artifact_ratio == 1


def test_modified_section_expands_chunk_boundary_without_destroying_evidence() -> None:
    before = tuple(_section(str(i), str(i), i, chr(97 + i)) for i in range(3))
    after = (
        before[0],
        _section("1", "1", 1, "d"),
        before[2],
    )
    plan = build_incremental_plan(
        source_document_id="doc",
        source_version_id="v1",
        target_version_id="v2",
        before=before,
        after=after,
    )
    neighbors = [item for item in plan.impacts if item.boundary_expansion]
    assert len(neighbors) == 2
    assert all(ArtifactKind.EVIDENCE in item.reusable_artifacts for item in neighbors)
    assert all(ArtifactKind.CHUNK in item.invalidated_artifacts for item in neighbors)


def test_profile_change_matrix_is_conservative() -> None:
    section = _section("a", "1", 0, "a")
    plan = build_incremental_plan(
        source_document_id="doc",
        source_version_id="v1",
        target_version_id="v2",
        before=(section,),
        after=(section,),
        profile_change=IncrementalProfileChange(chunker=True, reranker=True),
    )
    impact = plan.impacts[0]
    assert ArtifactKind.EVIDENCE in impact.reusable_artifacts
    assert ArtifactKind.CHUNK in impact.invalidated_artifacts
    assert "RERANKER_PROFILE_NO_REBUILD" in impact.reason_codes


def test_actual_reuse_requires_artifact_integrity(tmp_path) -> None:
    store = FileArtifactStore(tmp_path)
    stored = store.put(b"same artifact", media_type="application/octet-stream")
    artifact = ReusableArtifact(
        artifact_id="artifact-1",
        uri=stored.uri,
        sha256=stored.sha256,
        artifact_kind="evidence",
    )
    result = verify_artifact_reuse((artifact,), store=store, eligible_count=1)
    assert result.actual_reuse_ratio == 1.0
    corrupt = ReusableArtifact(
        artifact_id="artifact-2",
        uri=stored.uri,
        sha256="0" * 64,
        artifact_kind="evidence",
    )
    with pytest.raises(ArtifactReuseError):
        verify_artifact_reuse((corrupt,), store=store, eligible_count=1)
