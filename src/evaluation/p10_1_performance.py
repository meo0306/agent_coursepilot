from __future__ import annotations

import argparse
import hashlib
import importlib
import importlib.metadata
import json
import platform
import statistics
import subprocess
import sys
import threading
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import ModuleType
from typing import Protocol, TypeVar

from pydantic import JsonValue, TypeAdapter
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import coursepilot.models  # noqa: F401
import courserag.persistence.models  # noqa: F401
from core.settings import settings
from coursepilot.db.base import Base
from courserag.chunking.profile import load_chunk_profile
from courserag.chunking.splitter import ParentChildChunker
from courserag.chunking.tokenizer import LocalTokenizer
from courserag.domain.document import canonical_json_bytes, sha256_bytes
from courserag.evidence.builder import EvidenceBuilder
from courserag.incremental import (
    IncrementalProfileChange,
    SectionSnapshot,
    build_incremental_plan,
)
from courserag.indexing.dense import LocalSentenceTransformerEmbeddingAdapter
from courserag.jobs.artifacts import FileArtifactStore
from courserag.jobs.enrichment import PendingEnrichment, plan_enrichment_batch
from courserag.jobs.stages import BuildStageRunner, StageContext, StageOutput
from courserag.parsers.docx import StructuredDOCXParser
from courserag.parsers.ocr import OCRImageInput, OCRProviderProfile
from courserag.parsers.pdf import StructuredPDFParser
from courserag.parsers.structure import enrich_document_structure
from courserag.persistence.base import CourseRAGBase
from courserag.persistence.models import (
    BuildJobRecord,
    BuildStageRunRecord,
    KnowledgeBaseRecord,
)
from courserag.persistence.repositories import CourseRAGRepository
from courserag.security import (
    PromptInjectionProfile,
    load_prompt_injection_profile,
    mark_untrusted_instructions,
)
from evaluation.io import atomic_write_json
from evaluation.p05_ocr_eval import _provider, _recognize_page, _resolve_images
from evaluation.p10_schemas import P10DS8Case, P10DS8Dataset

T = TypeVar("T")
_JSON_ADAPTER: TypeAdapter[JsonValue] = TypeAdapter(JsonValue)


class OfflineWorkload(Protocol):
    @property
    def name(self) -> str: ...

    @property
    def version(self) -> str: ...

    def execute(self, context: StageContext) -> StageOutput: ...


@dataclass(frozen=True)
class WorkloadMeasurement:
    duration_seconds: float
    peak_memory_bytes: int
    peak_gpu_memory_bytes: int | None
    artifact_bytes: int
    stage_reuse: bool
    counts: dict[str, int]


_MEASUREMENT_ADAPTER: TypeAdapter[WorkloadMeasurement] = TypeAdapter(WorkloadMeasurement)


class LocalOfflineWorkloadFactory:
    """Real local P10 stages; no network Provider is reachable from this factory."""

    def __init__(
        self,
        repository_root: Path,
        security_profile: PromptInjectionProfile,
        ocr_profile: OCRProviderProfile,
    ) -> None:
        self.root = repository_root.resolve()
        self.security_profile = security_profile
        self.ocr_profile = ocr_profile
        self._embedder: LocalSentenceTransformerEmbeddingAdapter | None = None
        chunk_profile = load_chunk_profile(
            self.root / "resources/chunk_profiles/parent_child_v1.json"
        )
        tokenizer = LocalTokenizer(
            self.root / settings.COURSERAG_CHUNK_TOKENIZER_PATH,
            tokenizer_id=chunk_profile.tokenizer_id,
            expected_sha256=chunk_profile.tokenizer_sha256,
        )
        self.chunker = ParentChildChunker(chunk_profile, tokenizer)

    def create(self, workload_type: str) -> OfflineWorkload:
        if workload_type == "full_build":
            return _BuildWorkload(
                factory=self,
                source_paths=(
                    self.root / "data/sample_files/人工智能通识教程.pdf",
                    self.root / "data/sample_files/教材-人工智能：从算法到系统.docx",
                ),
                name="p10_1_full_build",
            )
        if workload_type == "single_document_build":
            return _BuildWorkload(
                factory=self,
                source_paths=(self.root / "data/sample_files/人工智能通识教程.pdf",),
                name="p10_1_single_document_build",
            )
        if workload_type == "single_section_update":
            return _SectionUpdateWorkload()
        if workload_type == "ocr_batch":
            return _OCRBatchWorkload(self.root, self.ocr_profile)
        if workload_type == "enrichment_batch":
            return _EnrichmentBatchWorkload()
        raise ValueError(f"unsupported offline workload: {workload_type}")

    def build_sources(self, source_paths: tuple[Path, ...]) -> dict[str, object]:
        documents: list[dict[str, object]] = []
        child_texts: list[str] = []
        artifact_bytes = 0
        for ordinal, path in enumerate(source_paths, 1):
            content = path.read_bytes()
            document_id = f"ds8-doc-{ordinal}"
            version_id = f"ds8-version-{ordinal}"
            digest = sha256_bytes(content)
            if path.suffix.casefold() == ".pdf":
                parsed = (
                    StructuredPDFParser()
                    .parse(
                        content,
                        document_id=document_id,
                        document_version_id=version_id,
                        document_sha256=digest,
                    )
                    .document
                )
            else:
                parsed = (
                    StructuredDOCXParser()
                    .parse(
                        content,
                        document_id=document_id,
                        document_version_id=version_id,
                        document_sha256=digest,
                    )
                    .document
                )
            parsed = mark_untrusted_instructions(
                enrich_document_structure(parsed), self.security_profile
            )
            evidence = EvidenceBuilder().build(parsed)
            chunks = self.chunker.build(evidence)
            children = [chunk for chunk in chunks.chunks if chunk.kind == "child"]
            child_texts.extend(chunk.text for chunk in children)
            artifact_bytes += sum(
                len(canonical_json_bytes(value)) for value in (parsed, evidence, chunks)
            )
            documents.append(
                {
                    "source_sha256": digest,
                    "pages": len(parsed.pages),
                    "blocks": sum(len(page.blocks) for page in parsed.pages),
                    "evidence": len(evidence.records),
                    "child_chunks": len(children),
                }
            )
        embeddings = self._embedding().embed_documents(child_texts)
        vector_dimension = len(embeddings[0]) if embeddings else 0
        artifact_bytes += len(embeddings) * vector_dimension * 4
        return {
            "documents": documents,
            "document_count": len(documents),
            "child_chunk_count": len(child_texts),
            "embedding_count": len(embeddings),
            "embedding_dimension": vector_dimension,
            "artifact_bytes": artifact_bytes,
            "security_profile_sha256": self.security_profile.sha256,
        }

    def _embedding(self) -> LocalSentenceTransformerEmbeddingAdapter:
        if self._embedder is None:
            required = {
                "model_path": settings.COURSERAG_EMBEDDING_MODEL_PATH,
                "model_name": settings.COURSERAG_EMBEDDING_MODEL,
                "model_bundle_sha256": settings.COURSERAG_EMBEDDING_MODEL_BUNDLE_SHA256,
                "weights_sha256": settings.COURSERAG_EMBEDDING_WEIGHTS_SHA256,
            }
            missing = [name for name, value in required.items() if not value]
            if missing:
                raise ValueError(f"DS8 local Embedding identity is incomplete: {missing}")
            self._embedder = LocalSentenceTransformerEmbeddingAdapter(
                model_path=str(required["model_path"]),
                model_name=str(required["model_name"]),
                model_bundle_sha256=str(required["model_bundle_sha256"]),
                weights_sha256=str(required["weights_sha256"]),
                device=settings.COURSERAG_EMBEDDING_DEVICE,
                dtype=settings.COURSERAG_EMBEDDING_DTYPE,
                max_length=settings.COURSERAG_EMBEDDING_MAX_LENGTH,
                batch_size=settings.COURSERAG_EMBEDDING_LOCAL_BATCH_SIZE,
                query_prompt_name=settings.COURSERAG_EMBEDDING_QUERY_PROMPT_NAME,
            )
        return self._embedder


@dataclass
class _BuildWorkload:
    factory: LocalOfflineWorkloadFactory
    source_paths: tuple[Path, ...]
    name: str
    version: str = "1.0"

    def execute(self, context: StageContext) -> StageOutput:
        payload = self.factory.build_sources(self.source_paths)
        document_count = _required_int(payload, "document_count")
        child_chunk_count = _required_int(payload, "child_chunk_count")
        embedding_count = _required_int(payload, "embedding_count")
        artifact_bytes = _required_int(payload, "artifact_bytes")
        return StageOutput(
            content=canonical_json_bytes(payload),
            media_type="application/vnd.courserag.p10-1-performance+json",
            counts={
                "documents": document_count,
                "child_chunks": child_chunk_count,
                "embeddings": embedding_count,
                "artifact_bytes": artifact_bytes,
            },
        )


@dataclass(frozen=True)
class _SectionUpdateWorkload:
    name: str = "p10_1_single_section_update"
    version: str = "1.0"

    def execute(self, context: StageContext) -> StageOutput:
        unchanged = "a" * 64
        before = (
            SectionSnapshot(
                section_id="s1",
                stable_path="/one",
                heading="One",
                ordinal=0,
                content_sha256=unchanged,
            ),
            SectionSnapshot(
                section_id="s2",
                stable_path="/two",
                heading="Two",
                ordinal=1,
                content_sha256="b" * 64,
            ),
            SectionSnapshot(
                section_id="s3",
                stable_path="/three",
                heading="Three",
                ordinal=2,
                content_sha256=unchanged,
            ),
        )
        after = (
            before[0],
            before[1].model_copy(update={"content_sha256": "c" * 64}),
            before[2],
        )
        plan = build_incremental_plan(
            source_document_id="ds8-document",
            source_version_id="before",
            target_version_id="after",
            before=before,
            after=after,
            profile_change=IncrementalProfileChange(),
        )
        payload = plan.model_dump(mode="json")
        return StageOutput(
            content=canonical_json_bytes(payload),
            counts={
                "affected_sections": sum(item.action.value == "reprocess" for item in plan.impacts),
                "change_coverage_ppm": int(plan.change_coverage * 1_000_000),
                "artifact_reuse_ratio_ppm": int(plan.reused_artifact_ratio * 1_000_000),
            },
        )


@dataclass
class _OCRBatchWorkload:
    root: Path
    profile: OCRProviderProfile
    name: str = "p10_1_ocr_batch"
    version: str = "1.0"

    def execute(self, context: StageContext) -> StageOutput:
        dataset_root = self.root / "datasets/courserag_eval/v1"
        profile = self.profile
        from courserag.evals.schemas import DS1ParsingDataset, OCRGold, P05OCRCandidateManifest

        dataset = DS1ParsingDataset.model_validate_json(
            (dataset_root / "approved/ds1/p05_ocr.json").read_text(encoding="utf-8")
        )
        gold = [record for record in dataset.records if isinstance(record, OCRGold)]
        manifest = P05OCRCandidateManifest.model_validate_json(
            (dataset_root / "provenance/p05_ocr_candidate_manifest.json").read_text(
                encoding="utf-8"
            )
        )
        review_root = dataset_root / manifest.review_pack_relative_path.removeprefix(
            "datasets/courserag_eval/v1/"
        )
        images = _resolve_images(review_root, gold)
        provider = _provider(profile)
        provider.validate_environment()
        results = []
        for record in gold:
            content = images[record.record_id].read_bytes()
            image = OCRImageInput(
                page_id=record.record_id,
                png_bytes=content,
                dpi=record.dpi,
                image_width=record.image_width,
                image_height=record.image_height,
                pdf_width_points=record.source_page_width_points,
                pdf_height_points=record.source_page_height_points,
                image_sha256=record.image_sha256,
            )
            results.append(_recognize_page(provider, image, profile))
        ready_count = sum(result.status == "ready" for result in results)
        warning_count = sum(len(result.warnings) for result in results)
        payload = {
            "pages": len(results),
            "ready": ready_count,
            "warnings": warning_count,
            "result_sha256": hashlib.sha256(
                canonical_json_bytes([result.model_dump(mode="json") for result in results])
            ).hexdigest(),
        }
        return StageOutput(
            content=canonical_json_bytes(payload),
            counts={
                "pages": len(results),
                "ready": ready_count,
                "warnings": warning_count,
            },
        )


@dataclass(frozen=True)
class _EnrichmentBatchWorkload:
    name: str = "p10_1_enrichment_batch"
    version: str = "1.0"

    def execute(self, context: StageContext) -> StageOutput:
        now = datetime(2026, 8, 11, tzinfo=UTC)
        pending = [
            PendingEnrichment(
                content_id=f"verified-{index:02d}",
                token_count=320,
                created_at=now - timedelta(hours=index),
            )
            for index in range(1, 11)
        ]
        plan = plan_enrichment_batch(
            pending,
            now=now,
            profile_sha256="e" * 64,
        )
        if plan is None:
            raise RuntimeError("DS8 enrichment workload did not trigger")
        payload = {
            "trigger": plan.trigger.value,
            "content_ids": list(plan.content_ids),
            "identity_sha256": plan.identity_sha256,
            "provider_quality_measured": False,
        }
        return StageOutput(
            content=canonical_json_bytes(payload),
            counts={"records": len(plan.content_ids), "provider_calls": 0},
        )


def run_offline_performance(
    *,
    repository_root: Path,
    output_path: Path,
    work_root: Path,
) -> Path:
    root = repository_root.resolve()
    ds8 = P10DS8Dataset.model_validate_json(
        (root / "datasets/courserag_eval/v1/approved/ds8/p10_performance_workloads.json").read_text(
            encoding="utf-8"
        )
    )
    offline = [case for case in ds8.cases if case.workload_domain == "offline"]
    if len(offline) != 10:
        raise ValueError("P10.1 requires exactly ten Approved offline DS8 templates")
    results: list[dict[str, object]] = []
    pair_reports: dict[str, str] = {}
    for workload_type in dict.fromkeys(case.workload_type for case in offline):
        pair_report = work_root.resolve() / "pair_reports" / f"{workload_type}.json"
        if not _valid_isolated_pair_report(pair_report, workload_type):
            subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "evaluation.p10_1_performance",
                    "--pair-worker",
                    workload_type,
                    "--repository-root",
                    str(root),
                    "--work-root",
                    str(work_root.resolve()),
                    "--output",
                    str(pair_report),
                ],
                cwd=root,
                check=True,
            )
        pair_payload = json.loads(pair_report.read_text(encoding="utf-8"))
        pair_results = pair_payload.get("results")
        if not isinstance(pair_results, list):
            raise ValueError("DS8 isolated pair report contains no results")
        results.extend(_object_dict(item) for item in pair_results)
        pair_reports[workload_type] = _sha256_file(pair_report)
        atomic_write_json(
            work_root.resolve() / "partial_report.json",
            _json_value(
                {
                    "schema_version": "courserag.p10-1-offline-performance-partial.v1",
                    "status": "running",
                    "completed_case_ids": [result["record_id"] for result in results],
                    "pair_report_sha256": pair_reports,
                    "results": results,
                }
            ),
        )
    security_profile = load_prompt_injection_profile(
        root / "resources/security_profiles/prompt_injection_candidate_v2.json"
    )
    ocr_profile = _resolved_rapidocr_profile(root, work_root.resolve() / "runtime_profiles")
    online_report_hashes = {
        "retrieval": _sha256_file(root / "storage_eval/p10/formal/retrieval-run-1/report.json"),
        "qa": _sha256_file(root / "storage_eval/p10/formal/qa-run-1/report.json"),
    }
    checks = {
        "all_offline_templates_executed": len(results) == 10,
        "all_workloads_succeeded": all(result["status"] == "succeeded" for result in results),
        "all_warm_cache_hits": all(
            bool(result["stage_reuse"]) for result in results if result["cache_state"] == "warm"
        ),
        "provider_calls_zero": all(
            _int_value(result.get("provider_calls", 0)) == 0 for result in results
        ),
        "cold_pairs_use_distinct_processes": len(
            {
                _int_value(result["process_id"])
                for result in results
                if result["cache_state"] == "cold"
            }
        )
        == 5,
    }
    payload: dict[str, object] = {
        "schema_version": "courserag.p10-1-offline-performance-report.v1",
        "status": "passed" if all(checks.values()) else "failed",
        "generated_at": datetime.now(UTC).isoformat(),
        "ds8_sha256": _sha256_file(
            root / "datasets/courserag_eval/v1/approved/ds8/p10_performance_workloads.json"
        ),
        "security_profile_sha256": security_profile.sha256,
        "test_access": False,
        "external_provider_calls": 0,
        "environment": {
            "platform": platform.platform(),
            "python": platform.python_version(),
            "cpu_logical_count": _cpu_logical_count(),
            "memory_bytes": _system_memory_bytes(),
            "embedding_device": settings.COURSERAG_EMBEDDING_DEVICE,
            "embedding_dtype": settings.COURSERAG_EMBEDDING_DTYPE,
            "ocr_provider": ocr_profile.provider,
            "ocr_profile_sha256": ocr_profile.sha256,
            "ocr_model_manifest_sha256": ocr_profile.model_manifest_sha256,
        },
        "online_evidence": {
            "status": "reused_immutable_reports_no_provider_replay",
            "report_sha256": online_report_hashes,
            "unavailable_dimensions": [
                "explicit_process-cold/provider-cold separation beyond original reports"
            ],
        },
        "checks": checks,
        "pair_report_sha256": pair_reports,
        "results": results,
    }
    atomic_write_json(output_path.resolve(), _json_value(payload))
    return output_path.resolve()


def run_offline_workload_pair(
    *, repository_root: Path, work_root: Path, workload_type: str, output_path: Path
) -> Path:
    root = repository_root.resolve()
    ds8 = P10DS8Dataset.model_validate_json(
        (root / "datasets/courserag_eval/v1/approved/ds8/p10_performance_workloads.json").read_text(
            encoding="utf-8"
        )
    )
    pair = [
        case
        for case in ds8.cases
        if case.workload_domain == "offline" and case.workload_type == workload_type
    ]
    if {case.cache_state for case in pair} != {"cold", "warm"} or len(pair) != 2:
        raise ValueError(f"DS8 workload lacks an exact cold/warm pair: {workload_type}")
    security_profile = load_prompt_injection_profile(
        root / "resources/security_profiles/prompt_injection_candidate_v2.json"
    )
    ocr_profile = _resolved_rapidocr_profile(root, work_root.resolve() / "runtime_profiles")
    factory = LocalOfflineWorkloadFactory(root, security_profile, ocr_profile)
    workload = factory.create(workload_type)
    results: list[dict[str, object]] = []
    pair_root = work_root.resolve() / workload_type
    pair_root.mkdir(parents=True, exist_ok=True)
    with _stage_environment(pair_root, workload_type, root) as environment:
        for case in sorted(pair, key=lambda item: item.cache_state != "cold"):
            result = _run_case(
                case,
                workload,
                environment,
                work_root.resolve() / "checkpoints" / f"{case.record_id}.json",
            )
            result["process_id"] = _process_id()
            results.append(result)
    payload = {
        "schema_version": "courserag.p10-1-offline-performance-pair.v1",
        "status": "passed",
        "workload_type": workload_type,
        "process_id": _process_id(),
        "process_isolated": True,
        "results": results,
    }
    atomic_write_json(output_path.resolve(), _json_value(payload))
    return output_path.resolve()


def _valid_isolated_pair_report(path: Path, workload_type: str) -> bool:
    if not path.is_file():
        return False
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return bool(
        payload.get("status") == "passed"
        and payload.get("process_isolated") is True
        and payload.get("workload_type") == workload_type
    )


def _object_dict(value: object) -> dict[str, object]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise ValueError("DS8 result must be a string-keyed object")
    return value


def _process_id() -> int:
    import os

    return os.getpid()


@dataclass
class _StageEnvironment:
    session: Session
    runner: BuildStageRunner
    context: StageContext
    store: FileArtifactStore


class _stage_environment:
    def __init__(self, root: Path, workload_type: str, repository_root: Path) -> None:
        self.root = root
        self.workload_type = workload_type
        self.repository_root = repository_root
        self.engine = create_engine(f"sqlite:///{root / 'performance.db'}")
        self.session: Session | None = None

    def __enter__(self) -> _StageEnvironment:
        Base.metadata.create_all(self.engine)
        CourseRAGBase.metadata.create_all(self.engine)
        self.session = Session(self.engine, expire_on_commit=False)
        repository = CourseRAGRepository(self.session)
        course_id = f"p10-1-{self.workload_type}"
        kb = (
            self.session.query(KnowledgeBaseRecord)
            .filter(KnowledgeBaseRecord.course_id == course_id)
            .one_or_none()
        )
        if kb is None:
            kb = KnowledgeBaseRecord(course_id=course_id, name="P10.1 DS8")
            repository.add(kb)
            repository.flush()
        request_hash = hashlib.sha256(self.workload_type.encode()).hexdigest()
        job = (
            self.session.query(BuildJobRecord)
            .filter(
                BuildJobRecord.knowledge_base_id == kb.id,
                BuildJobRecord.request_hash == request_hash,
            )
            .one_or_none()
        )
        if job is None:
            job = BuildJobRecord(
                knowledge_base_id=kb.id,
                request_hash=request_hash,
                status="running",
            )
            repository.add(job)
            repository.flush()
        self.session.commit()
        store = FileArtifactStore(self.root / "artifacts")
        approved_ds8 = self.repository_root / (
            "datasets/courserag_eval/v1/approved/ds8/p10_performance_workloads.json"
        )
        security_profile = self.repository_root / (
            "resources/security_profiles/prompt_injection_candidate_v2.json"
        )
        context = StageContext(
            build_job_id=job.id,
            knowledge_base_id=kb.id,
            input_hashes=(_sha256_file(approved_ds8), _sha256_file(security_profile)),
            input_identities=("approved_ds8", "prompt_injection_profile"),
            config={
                "profile": "p10.1",
                "workload_type": self.workload_type,
                "external_provider_calls": 0,
            },
        )
        return _StageEnvironment(
            session=self.session,
            runner=BuildStageRunner(repository, store),
            context=context,
            store=store,
        )

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        if self.session is not None:
            self.session.close()
        self.engine.dispose()


def _run_case(
    case: P10DS8Case,
    workload: OfflineWorkload,
    environment: _StageEnvironment,
    checkpoint_path: Path,
) -> dict[str, object]:
    samples = _load_measurement_checkpoint(checkpoint_path, case)
    for _ in range(len(samples), case.repetitions):
        before_runs = environment.session.query(BuildStageRunRecord).count()

        def invoke() -> BuildStageRunRecord:
            return environment.runner.run(
                workload,
                environment.context,
                force=case.cache_state == "cold",
            )

        try:
            run, duration, peak_rss, peak_gpu = _measure(invoke)
        except Exception:
            environment.session.commit()
            raise
        after_runs = environment.session.query(BuildStageRunRecord).count()
        if run.artifact_id is None:
            raise RuntimeError("DS8 workload completed without an Artifact identity")
        artifact = environment.runner.repository.get_artifact(run.artifact_id)
        if artifact is None:
            raise RuntimeError("DS8 workload completed without Artifact")
        samples.append(
            WorkloadMeasurement(
                duration_seconds=duration,
                peak_memory_bytes=peak_rss,
                peak_gpu_memory_bytes=peak_gpu,
                artifact_bytes=int(run.counts_json.get("artifact_bytes", artifact.size_bytes)),
                stage_reuse=(case.cache_state == "warm" and after_runs == before_runs),
                counts={str(key): int(value) for key, value in run.counts_json.items()},
            )
        )
        environment.session.commit()
        atomic_write_json(
            checkpoint_path,
            _json_value(
                {
                    "schema_version": "courserag.p10-1-performance-checkpoint.v1",
                    "record_id": case.record_id,
                    "workload_type": case.workload_type,
                    "cache_state": case.cache_state,
                    "expected_repetitions": case.repetitions,
                    "samples": [asdict(sample) for sample in samples],
                }
            ),
        )
    durations = [sample.duration_seconds for sample in samples]
    counts = samples[-1].counts
    payload: dict[str, object] = {
        "record_id": case.record_id,
        "status": "succeeded",
        "workload_type": case.workload_type,
        "cache_state": case.cache_state,
        "repetitions": case.repetitions,
        "duration_seconds": {
            "samples": durations,
            "mean": statistics.fmean(durations),
            "p50": statistics.median(durations),
            "p95": _percentile(durations, 0.95),
        },
        "peak_memory_bytes": max(sample.peak_memory_bytes for sample in samples),
        "peak_gpu_memory_bytes": max(
            (sample.peak_gpu_memory_bytes or 0 for sample in samples), default=0
        ),
        "artifact_bytes": max(sample.artifact_bytes for sample in samples),
        "stage_reuse": all(sample.stage_reuse for sample in samples),
        "counts": counts,
        "provider_calls": counts.get("provider_calls", 0),
    }
    if case.workload_type == "ocr_batch":
        payload["pages_per_second"] = counts.get("pages", 0) / max(
            statistics.fmean(durations), 1e-9
        )
    if case.workload_type == "single_section_update":
        payload["affected_sections"] = counts.get("affected_sections", 0)
        payload["artifact_reuse_ratio"] = counts.get("artifact_reuse_ratio_ppm", 0) / 1_000_000
        payload["change_coverage"] = counts.get("change_coverage_ppm", 0) / 1_000_000
    return payload


def _load_measurement_checkpoint(path: Path, case: P10DS8Case) -> list[WorkloadMeasurement]:
    if not path.is_file():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    expected = (case.record_id, case.workload_type, case.cache_state, case.repetitions)
    actual = (
        payload.get("record_id"),
        payload.get("workload_type"),
        payload.get("cache_state"),
        payload.get("expected_repetitions"),
    )
    if actual != expected:
        raise ValueError("DS8 checkpoint identity differs from the Approved case")
    raw_samples = payload.get("samples")
    if not isinstance(raw_samples, list) or len(raw_samples) > case.repetitions:
        raise ValueError("DS8 checkpoint sample count is invalid")
    return [_MEASUREMENT_ADAPTER.validate_python(sample) for sample in raw_samples]


def _measure(call: Callable[[], T]) -> tuple[T, float, int, int | None]:
    psutil_module = _optional_module("psutil")
    process = psutil_module.Process() if psutil_module is not None else None
    peak = int(process.memory_info().rss) if process is not None else 0
    stop = threading.Event()

    def sample() -> None:
        nonlocal peak
        while not stop.wait(0.02):
            if process is not None:
                peak = max(peak, int(process.memory_info().rss))

    gpu_peak: int | None = None
    torch_module = _optional_module("torch")
    cuda = getattr(torch_module, "cuda", None)
    if cuda is not None and bool(cuda.is_available()):
        cuda.reset_peak_memory_stats()
    sampler = threading.Thread(target=sample, daemon=True)
    sampler.start()
    started = time.perf_counter()
    try:
        result = call()
    finally:
        duration = time.perf_counter() - started
        stop.set()
        sampler.join(timeout=1)
    if cuda is not None and bool(cuda.is_available()):
        gpu_peak = int(cuda.max_memory_allocated())
    return result, duration, peak, gpu_peak


def _optional_module(name: str) -> ModuleType | None:
    try:
        return importlib.import_module(name)
    except ImportError:
        return None


def _cpu_logical_count() -> int | None:
    psutil_module = _optional_module("psutil")
    if psutil_module is None:
        return None
    value = psutil_module.cpu_count(logical=True)
    return int(value) if value is not None else None


def _system_memory_bytes() -> int | None:
    psutil_module = _optional_module("psutil")
    if psutil_module is None:
        return None
    return int(psutil_module.virtual_memory().total)


def _json_value(value: object) -> JsonValue:
    return _JSON_ADAPTER.validate_python(value)


def _required_int(payload: dict[str, object], key: str) -> int:
    if key not in payload:
        raise ValueError(f"missing integer result field: {key}")
    return _int_value(payload[key])


def _int_value(value: object) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError("performance result field must be an integer")
    return value


def _percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * fraction
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    weight = position - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _resolved_rapidocr_profile(repository_root: Path, output_directory: Path) -> OCRProviderProfile:
    repository_root = repository_root.resolve()
    output_directory = output_directory.resolve()
    base = OCRProviderProfile.model_validate_json(
        (repository_root / "resources/ocr_profiles/default_v1.json").read_text(encoding="utf-8")
    )
    rapidocr_module = _optional_module("rapidocr")
    if rapidocr_module is None or rapidocr_module.__file__ is None:
        raise RuntimeError("RapidOCR is unavailable for the approved DS8 workload")
    package_root = Path(rapidocr_module.__file__).resolve().parent
    model_files = sorted((package_root / "models").glob("*.onnx"))
    if not model_files:
        raise RuntimeError("RapidOCR has no locally bundled ONNX model artifacts")
    artifacts = [
        {
            "package_relative_path": path.relative_to(package_root).as_posix(),
            "sha256": _sha256_file(path),
            "size_bytes": path.stat().st_size,
        }
        for path in model_files
    ]
    manifest = {
        "schema_version": "courserag.ocr-model-manifest.v1",
        "provider": "rapidocr",
        "distribution": "rapidocr",
        "distribution_version": importlib.metadata.version("rapidocr"),
        "identity_status": "resolved",
        "license_review_required": True,
        "artifacts": artifacts,
    }
    output_directory.mkdir(parents=True, exist_ok=True)
    manifest_path = output_directory / "rapidocr_ds8_runtime.model-manifest.json"
    atomic_write_json(manifest_path, _json_value(manifest))
    manifest_sha256 = _sha256_file(manifest_path)
    relative_manifest_path = manifest_path.relative_to(repository_root).as_posix()
    return base.model_copy(
        update={
            "model_manifest_path": relative_manifest_path,
            "model_manifest_sha256": manifest_sha256,
        }
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="P10.1 isolated DS8 offline performance runner")
    parser.add_argument("--pair-worker", required=True)
    parser.add_argument("--repository-root", type=Path, required=True)
    parser.add_argument("--work-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    run_offline_workload_pair(
        repository_root=arguments.repository_root,
        work_root=arguments.work_root,
        workload_type=arguments.pair_worker,
        output_path=arguments.output,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
