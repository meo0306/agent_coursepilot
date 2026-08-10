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
    text: str
    sparse_score: float
    dense_score: float


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
                        text=item.body,
                        sparse_score=overlap / max(len(terms), 1),
                        dense_score=dense_score,
                    )
                )
        return sorted(
            hits,
            key=lambda hit: (-(hit.sparse_score + hit.dense_score), hit.verified_content_id),
        )[:top_k]


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
