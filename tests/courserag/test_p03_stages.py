from dataclasses import dataclass
from pathlib import Path

import pytest
from sqlalchemy.orm import Session

from courserag.jobs.artifacts import FileArtifactStore
from courserag.jobs.stages import BuildStageRunner, StageContext, StageOutput, stage_fingerprint
from courserag.persistence.models import (
    BuildJobRecord,
    BuildStageRunRecord,
    KnowledgeBaseRecord,
)
from courserag.persistence.repositories import CourseRAGRepository


@dataclass
class CountingStage:
    calls: int = 0
    name: str = "test_stage"
    version: str = "1.0"

    def execute(self, context: StageContext) -> StageOutput:
        self.calls += 1
        return StageOutput(content=b'{"ok":true}', counts={"items": 1})


def _job(session: Session, request_hash: str) -> BuildJobRecord:
    knowledge_base = session.query(KnowledgeBaseRecord).first()
    if knowledge_base is None:
        knowledge_base = KnowledgeBaseRecord(course_id="course-1", name="Course")
        session.add(knowledge_base)
        session.flush()
    job = BuildJobRecord(
        knowledge_base_id=knowledge_base.id,
        request_hash=request_hash,
        status="queued",
    )
    session.add(job)
    session.flush()
    return job


def test_fingerprint_changes_with_relevant_configuration() -> None:
    stage = CountingStage()
    first = StageContext("job", "kb", ("a" * 64,), ("document-a",), {"parser": "v1"})
    second = StageContext("job", "kb", ("a" * 64,), ("document-a",), {"parser": "v2"})
    assert stage_fingerprint(stage, first) != stage_fingerprint(stage, second)


def test_fingerprint_is_scoped_by_knowledge_base_and_semantic_identity() -> None:
    stage = CountingStage()
    first = StageContext("job-a", "kb-a", ("a" * 64,), ("document-a",), {})
    other_kb = StageContext("job-b", "kb-b", ("a" * 64,), ("document-a",), {})
    other_document = StageContext("job-c", "kb-a", ("a" * 64,), ("document-b",), {})
    assert stage_fingerprint(stage, first) != stage_fingerprint(stage, other_kb)
    assert stage_fingerprint(stage, first) != stage_fingerprint(stage, other_document)


def test_provider_metadata_rejects_secret_bearing_keys() -> None:
    context = StageContext(
        "job",
        "kb",
        ("a" * 64,),
        ("document",),
        {},
        provider_metadata={"api_key": "must-not-persist"},
    )
    with pytest.raises(ValueError, match="Unsupported provider metadata keys"):
        stage_fingerprint(CountingStage(), context)


def test_stage_cache_reuses_verified_artifact(p03_session: Session, tmp_path: Path) -> None:
    repository = CourseRAGRepository(p03_session)
    first_job = _job(p03_session, "a" * 64)
    second_job = _job(p03_session, "b" * 64)
    stage = CountingStage()
    runner = BuildStageRunner(repository, FileArtifactStore(tmp_path / "artifacts"))
    first = runner.run(
        stage,
        StageContext(
            first_job.id,
            first_job.knowledge_base_id,
            ("c" * 64,),
            ("document",),
            {"parser": "v1"},
        ),
    )
    second = runner.run(
        stage,
        StageContext(
            second_job.id,
            second_job.knowledge_base_id,
            ("c" * 64,),
            ("document",),
            {"parser": "v1"},
        ),
    )
    assert first.status == "succeeded"
    assert second.status == "cached"
    assert second.artifact_id == first.artifact_id
    assert stage.calls == 1


def test_missing_cached_artifact_causes_reexecution(p03_session: Session, tmp_path: Path) -> None:
    repository = CourseRAGRepository(p03_session)
    first_job = _job(p03_session, "d" * 64)
    second_job = _job(p03_session, "e" * 64)
    stage = CountingStage()
    store = FileArtifactStore(tmp_path / "artifacts")
    runner = BuildStageRunner(repository, store)
    first = runner.run(
        stage,
        StageContext(
            first_job.id,
            first_job.knowledge_base_id,
            ("f" * 64,),
            ("document",),
            {},
        ),
    )
    artifact = repository.get_artifact(first.artifact_id or "")
    assert artifact is not None
    store.delete(artifact.uri)
    second = runner.run(
        stage,
        StageContext(
            second_job.id,
            second_job.knowledge_base_id,
            ("f" * 64,),
            ("document",),
            {},
        ),
    )
    assert second.status == "succeeded"
    assert stage.calls == 2


def test_one_job_supports_multiple_stages_resume_and_manual_retry(
    p03_session: Session, tmp_path: Path
) -> None:
    repository = CourseRAGRepository(p03_session)
    job = _job(p03_session, "1" * 64)
    runner = BuildStageRunner(repository, FileArtifactStore(tmp_path / "artifacts"))
    context = StageContext(
        job.id,
        job.knowledge_base_id,
        ("2" * 64,),
        ("document",),
        {},
    )
    first_stage = CountingStage(name="first")
    second_stage = CountingStage(name="second")

    first = runner.run(first_stage, context)
    resumed = runner.run(first_stage, context)
    second = runner.run(second_stage, context)
    retried = runner.run(first_stage, context, force=True)

    assert resumed.id == first.id
    assert first_stage.calls == 2
    assert second_stage.calls == 1
    assert second.stage_name == "second"
    assert retried.attempt_number == 2
    assert p03_session.query(BuildStageRunRecord).filter_by(build_job_id=job.id).count() == 3


def test_stale_running_attempt_is_closed_before_takeover(
    p03_session: Session, tmp_path: Path
) -> None:
    repository = CourseRAGRepository(p03_session)
    job = _job(p03_session, "3" * 64)
    stage = CountingStage()
    context = StageContext(
        job.id,
        job.knowledge_base_id,
        ("4" * 64,),
        ("document",),
        {},
    )
    stale = BuildStageRunRecord(
        build_job_id=job.id,
        stage_name=stage.name,
        stage_version=stage.version,
        fingerprint=stage_fingerprint(stage, context),
        attempt_number=1,
        status="running",
        config_hash="5" * 64,
    )
    p03_session.add(stale)
    p03_session.flush()

    recovered = BuildStageRunner(repository, FileArtifactStore(tmp_path / "artifacts")).run(
        stage, context
    )

    assert stale.status == "failed"
    assert stale.error_code == "STALE_STAGE_RECOVERED"
    assert recovered.attempt_number == 2
    assert recovered.status == "succeeded"


def test_replay_adopts_content_addressed_artifact_left_before_crash(
    p03_session: Session, tmp_path: Path
) -> None:
    repository = CourseRAGRepository(p03_session)
    job = _job(p03_session, "6" * 64)
    store = FileArtifactStore(tmp_path / "artifacts")
    orphan = store.put(b'{"ok":true}', media_type="application/json")
    stage = CountingStage()
    context = StageContext(
        job.id,
        job.knowledge_base_id,
        ("7" * 64,),
        ("document",),
        {},
    )

    recovered = BuildStageRunner(repository, store).run(stage, context)
    artifact = repository.get_artifact(recovered.artifact_id or "")

    assert artifact is not None
    assert artifact.uri == orphan.uri
    assert artifact.sha256 == orphan.sha256
    assert len(tuple((tmp_path / "artifacts").rglob(orphan.sha256))) == 1
