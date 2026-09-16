from __future__ import annotations

import json
from pathlib import Path

from courserag.domain.chunk import ChunkArtifact
from courserag.domain.evidence import EvidenceArtifact
from courserag.evals.p06_metrics import map_gold_to_system_evidence
from courserag.evals.schemas import DS2EvidenceDataset, P08SourcePackageDataset
from courserag.retrieval.models import RetrievalCandidate


def load_p08_child_corpus(repository_root: Path) -> dict[str, tuple[RetrievalCandidate, ...]]:
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
    evidence_artifacts: list[EvidenceArtifact] = []
    chunk_artifacts: list[ChunkArtifact] = []
    for variant in payload["variants"]:
        evidence_artifacts.append(EvidenceArtifact.model_validate(variant["evidence"]))
        chunk_artifacts.append(ChunkArtifact.model_validate(variant["chunks"]))
    system_evidence = [record for artifact in evidence_artifacts for record in artifact.records]
    matches = map_gold_to_system_evidence(gold.evidence, system_evidence, document_aliases=aliases)
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
            evidence_ids = tuple(
                gold_by_system[link.evidence_id]
                for link in chunk.evidence_links
                if link.evidence_id in gold_by_system
            )
            output.setdefault(course_id, []).append(
                RetrievalCandidate(
                    chunk_id=chunk.chunk_id,
                    document_version_id=chunk.document_version_id,
                    section_id=chunk.section_id,
                    text=chunk.text,
                    evidence_ids=evidence_ids,
                )
            )
    return {
        course_id: tuple({item.chunk_id: item for item in items}.values())
        for course_id, items in output.items()
    }
