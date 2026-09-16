from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from courserag.domain.chunk import ChunkArtifact
from courserag.domain.evidence import EvidenceArtifact, EvidenceRecord
from courserag.evals.p06_metrics import map_gold_to_system_evidence
from courserag.evals.schemas import DS2EvidenceDataset, P08SourcePackageDataset
from courserag.retrieval.models import RetrievalCandidate


@dataclass(frozen=True)
class P09RuntimeCorpus:
    candidates_by_course: dict[str, tuple[RetrievalCandidate, ...]]
    evidence_by_id: dict[str, EvidenceRecord]
    gold_by_system_evidence: dict[str, str]


def load_p09_runtime_corpus(repository_root: Path) -> P09RuntimeCorpus:
    root = repository_root.resolve()
    dataset_root = root / "datasets/courserag_eval/v1"
    payload = json.loads(
        (root / "storage_eval/p06_b1_b2/run-4/system_outputs.json").read_text(encoding="utf-8")
    )
    report = json.loads(
        (root / "storage_eval/p06_b1_b2/run-4/report.json").read_text(encoding="utf-8")
    )
    aliases = report["report"]["document_identity_adapter"]
    packages = P08SourcePackageDataset.model_validate_json(
        (dataset_root / "provenance/p08_query_source_packages_r3.json").read_text(encoding="utf-8")
    )
    course_by_document = {item.primary_document_id: item.course_id for item in packages.packages}
    gold = DS2EvidenceDataset.model_validate_json(
        (dataset_root / "approved/ds2/p06_evidence.json").read_text(encoding="utf-8")
    )
    evidence_artifacts = [
        EvidenceArtifact.model_validate(value["evidence"]) for value in payload["variants"]
    ]
    chunk_artifacts = [
        ChunkArtifact.model_validate(value["chunks"]) for value in payload["variants"]
    ]
    evidence_by_id = {
        record.evidence_id: record for artifact in evidence_artifacts for record in artifact.records
    }
    matches = map_gold_to_system_evidence(
        gold.evidence, list(evidence_by_id.values()), document_aliases=aliases
    )
    gold_by_system = {item.system_evidence_id: item.gold_evidence_id for item in matches}
    output: dict[str, list[RetrievalCandidate]] = {}
    for evidence, chunks in zip(evidence_artifacts, chunk_artifacts, strict=True):
        logical_document = aliases.get(evidence.document_id, evidence.document_id)
        course_id = course_by_document.get(logical_document)
        if course_id is None:
            continue
        for chunk in chunks.chunks:
            if chunk.kind != "child":
                continue
            output.setdefault(course_id, []).append(
                RetrievalCandidate(
                    chunk_id=chunk.chunk_id,
                    document_version_id=chunk.document_version_id,
                    section_id=chunk.section_id,
                    text=chunk.text,
                    evidence_ids=tuple(link.evidence_id for link in chunk.evidence_links),
                )
            )
    return P09RuntimeCorpus(
        candidates_by_course={
            course_id: tuple({item.chunk_id: item for item in values}.values())
            for course_id, values in output.items()
        },
        evidence_by_id=evidence_by_id,
        gold_by_system_evidence=gold_by_system,
    )
