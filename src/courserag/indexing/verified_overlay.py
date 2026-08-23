from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field

from courserag.jobs.artifacts import FileArtifactStore
from courserag.persistence.base import utc_now
from courserag.persistence.models import ArtifactRecord, VerifiedIndexVersionRecord
from courserag.persistence.writeback_repository import WritebackRepository


class VerifiedOverlayEmbeddingPort(Protocol):
    @property
    def identity(self) -> str: ...

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]: ...

    def embed_query(self, text: str) -> list[float]: ...


class VerifiedOverlayItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    verified_content_id: str
    content_type: str
    title: str
    body: str
    content_sha256: str
    source_tier: str = "teacher_verified"
    evidence_ids: list[str] = Field(default_factory=list)
    knowledge_point_ids: list[str] = Field(default_factory=list)
    dense_vector: list[float] = Field(min_length=1)


class VerifiedOverlayManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = "verified-overlay/v1"
    knowledge_base_id: str
    version_number: int = Field(ge=1)
    embedding_identity: str = Field(min_length=1)
    items: list[VerifiedOverlayItem]


@dataclass(frozen=True)
class VerifiedOverlayHit:
    verified_content_id: str
    title: str
    text: str
    evidence_ids: tuple[str, ...]
    knowledge_point_ids: tuple[str, ...]
    sparse_score: float
    dense_score: float


def retrieval_snapshot_id(primary_index_version: str, verified_overlay_version: str | None) -> str:
    """Stable composite identity for a primary index plus optional overlay."""
    value = f"{primary_index_version}\x1f{verified_overlay_version or 'none'}".encode()
    return f"snapshot_{hashlib.sha256(value).hexdigest()[:32]}"


def fuse_overlay_hits(
    primary: Sequence[tuple[str, float]],
    overlay: Sequence[VerifiedOverlayHit],
    *,
    rrf_k: int = 60,
    top_k: int = 8,
) -> list[tuple[str, float, str]]:
    """Fuse Primary and Verified Overlay ranks without changing Primary data."""
    scores: dict[str, float] = {}
    tiers: dict[str, str] = {}
    for rank, (chunk_id, _score) in enumerate(primary, start=1):
        scores[chunk_id] = scores.get(chunk_id, 0.0) + 1 / (rrf_k + rank)
        tiers[chunk_id] = "primary_source"
    for rank, hit in enumerate(overlay, start=1):
        scores[hit.verified_content_id] = scores.get(hit.verified_content_id, 0.0) + 1 / (
            rrf_k + rank
        )
        tiers[hit.verified_content_id] = "teacher_verified"
    return [
        (identifier, score, tiers[identifier])
        for identifier, score in sorted(scores.items(), key=lambda item: (-item[1], item[0]))[
            :top_k
        ]
    ]


class VerifiedOverlayPublisher:
    """Atomic independent Dense/BM25-style teacher-verified overlay."""

    def __init__(
        self,
        repository: WritebackRepository,
        artifact_store: FileArtifactStore,
        embedder: VerifiedOverlayEmbeddingPort,
    ) -> None:
        self.repository = repository
        self.artifact_store = artifact_store
        self.embedder = embedder

    def publish(
        self, knowledge_base_id: str, *, expected_active_id: str | None
    ) -> VerifiedIndexVersionRecord:
        knowledge_base = self.repository.lock_knowledge_base(knowledge_base_id)
        if knowledge_base is None:
            raise ValueError("Knowledge base not found")
        if knowledge_base.active_verified_index_version_id != expected_active_id:
            raise RuntimeError("Verified overlay active pointer changed")
        version_number = self.repository.next_overlay_version(knowledge_base_id)
        records = self.repository.active_contents(knowledge_base_id)
        content_ids = [item.id for item in records]
        evidence_ids = self.repository.evidence_ids_by_content(content_ids)
        knowledge_point_ids = self.repository.knowledge_point_ids_by_content(content_ids)
        texts = [f"{item.title}\n{item.body}" for item in records]
        vectors = self.embedder.embed_documents(texts)
        if len(vectors) != len(records):
            raise RuntimeError("Verified overlay Embedding result count differs from input")
        dimensions = {len(vector) for vector in vectors}
        if vectors and (0 in dimensions or len(dimensions) != 1):
            raise RuntimeError("Verified overlay Embedding dimensions are inconsistent")
        items = [
            VerifiedOverlayItem(
                verified_content_id=item.id,
                content_type=item.content_type,
                title=item.title,
                body=item.body,
                content_sha256=item.content_sha256
                or hashlib.sha256(item.body.encode()).hexdigest(),
                evidence_ids=evidence_ids[item.id],
                knowledge_point_ids=knowledge_point_ids[item.id],
                dense_vector=vectors[position],
            )
            for position, item in enumerate(records)
        ]
        manifest = VerifiedOverlayManifest(
            knowledge_base_id=knowledge_base_id,
            version_number=version_number,
            embedding_identity=self.embedder.identity,
            items=items,
        )
        payload = json.dumps(
            manifest.model_dump(mode="json"),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        stored = self.artifact_store.put(payload, media_type="application/json")
        if not self.artifact_store.verify(stored.uri, stored.sha256):
            raise RuntimeError("Verified overlay manifest verification failed")
        artifact = self.repository.add_artifact(
            ArtifactRecord(
                uri=stored.uri,
                sha256=stored.sha256,
                size_bytes=stored.size_bytes,
                media_type=stored.media_type,
                status="available",
                last_verified_at=utc_now(),
            )
        )
        candidate = VerifiedIndexVersionRecord(
            knowledge_base_id=knowledge_base_id,
            version_number=version_number,
            status="active",
            manifest_artifact_id=artifact.id,
            manifest_sha256=stored.sha256,
            base_version_id=expected_active_id,
            active_item_count=len(items),
            validated=True,
            published_at=utc_now(),
        )
        self.repository.add(candidate)
        self.repository.flush()
        previous = self.repository.get_overlay_version(expected_active_id)
        if previous is not None:
            previous.status = "retired"
        knowledge_base.active_verified_index_version_id = candidate.id
        self.repository.flush()
        return candidate

    def search(self, manifest_uri: str, query: str, *, top_k: int = 8) -> list[VerifiedOverlayHit]:
        payload = self.artifact_store.read(manifest_uri)
        manifest = VerifiedOverlayManifest.model_validate_json(payload)
        if manifest.embedding_identity != self.embedder.identity:
            raise RuntimeError("Verified overlay query Embedding identity differs from Manifest")
        terms = _terms(query)
        query_vector = self.embedder.embed_query(query)
        hits: list[VerifiedOverlayHit] = []
        for item in manifest.items:
            item_terms = _terms(f"{item.title} {item.body}")
            overlap = len(terms & item_terms)
            dense_score = _cosine(query_vector, item.dense_vector)
            if overlap or dense_score > 0:
                hits.append(
                    VerifiedOverlayHit(
                        verified_content_id=item.verified_content_id,
                        title=item.title,
                        text=item.body,
                        evidence_ids=tuple(item.evidence_ids),
                        knowledge_point_ids=tuple(item.knowledge_point_ids),
                        sparse_score=overlap / max(len(terms), 1),
                        dense_score=dense_score,
                    )
                )
        return sorted(
            hits,
            key=lambda hit: (-(hit.sparse_score + hit.dense_score), hit.verified_content_id),
        )[:top_k]


class VerifiedOverlaySearchService:
    """Resolve and query the active immutable Overlay Manifest."""

    def __init__(
        self,
        repository: WritebackRepository,
        publisher: VerifiedOverlayPublisher,
    ) -> None:
        self.repository = repository
        self.publisher = publisher

    def search(
        self,
        *,
        overlay_version_id: str,
        query: str,
        top_k: int,
        knowledge_point_ids: tuple[str, ...] = (),
    ) -> list[VerifiedOverlayHit]:
        manifest_uri = self.repository.overlay_manifest_uri(overlay_version_id)
        if manifest_uri is None:
            raise RuntimeError("Verified overlay Manifest is unavailable")
        hits = self.publisher.search(manifest_uri, query, top_k=top_k)
        if not knowledge_point_ids:
            return hits
        required = set(knowledge_point_ids)
        return [hit for hit in hits if required.intersection(hit.knowledge_point_ids)]


def _terms(text: str) -> set[str]:
    normalized = "".join(character.lower() if character.isalnum() else " " for character in text)
    words = set(normalized.split())
    compact = "".join(normalized.split())
    words.update(compact[index : index + 2] for index in range(max(0, len(compact) - 1)))
    return {word for word in words if word}


def _cosine(left: Sequence[float], right: Sequence[float]) -> float:
    if len(left) != len(right) or not left:
        raise ValueError("Verified overlay dense vector dimensions differ")
    numerator = sum(a * b for a, b in zip(left, right, strict=True))
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return numerator / (left_norm * right_norm)
