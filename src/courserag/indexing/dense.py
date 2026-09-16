from __future__ import annotations

import hashlib
import importlib
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Protocol, cast

import httpx

from courserag.retrieval.models import RetrievalCandidate, RetrievalFilter
from courserag.retrieval.ports import EmbeddingPort


class DenseCollection(Protocol):
    def query(self, **kwargs: object) -> Mapping[str, object]: ...

    def upsert(self, **kwargs: object) -> object: ...


class EmbeddingMatrix(Protocol):
    def tolist(self) -> list[list[float]]: ...


class SentenceTransformerModel(Protocol):
    max_seq_length: int

    def encode(
        self,
        sentences: list[str],
        *,
        batch_size: int,
        normalize_embeddings: bool,
        convert_to_numpy: bool,
        show_progress_bar: bool,
        prompt_name: str | None = None,
    ) -> EmbeddingMatrix: ...


class SentenceTransformerFactory(Protocol):
    def __call__(
        self,
        model_name_or_path: str,
        *,
        device: str,
        model_kwargs: Mapping[str, object],
        local_files_only: bool,
    ) -> SentenceTransformerModel: ...


class OpenAICompatibleEmbeddingAdapter:
    def __init__(
        self, *, endpoint: str, api_key: str, model: str, timeout_seconds: float = 30.0
    ) -> None:
        if not endpoint or not api_key or not model:
            raise ValueError("Embedding endpoint, API key, and model are required")
        self.endpoint = endpoint.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout_seconds = timeout_seconds

    @property
    def identity(self) -> str:
        return hashlib.sha256(f"{self.endpoint}|{self.model}".encode()).hexdigest()

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        return self._embed(texts)

    def embed_query(self, text: str) -> list[float]:
        return self._embed([text])[0]

    def _embed(self, texts: Sequence[str]) -> list[list[float]]:
        response = httpx.post(
            f"{self.endpoint}/embeddings",
            headers={"Authorization": f"Bearer {self.api_key}"},
            json={
                "model": self.model,
                "input": list(texts),
                "encoding_format": "float",
            },
            timeout=self.timeout_seconds,
        )
        if response.is_error:
            raise RuntimeError(
                f"Embedding Provider HTTP {response.status_code}: "
                f"{_provider_error_message(response)}"
            )
        data = response.json().get("data")
        if not isinstance(data, list) or len(data) != len(texts):
            raise ValueError("Embedding Provider returned an invalid result count")
        ordered = sorted(data, key=lambda item: int(item["index"]))
        return [[float(value) for value in item["embedding"]] for item in ordered]


class LocalSentenceTransformerEmbeddingAdapter:
    def __init__(
        self,
        *,
        model_path: str | Path,
        model_name: str,
        model_bundle_sha256: str,
        weights_sha256: str,
        device: str = "cuda",
        dtype: str = "bfloat16",
        max_length: int = 2048,
        batch_size: int = 8,
        query_prompt_name: str = "query",
    ) -> None:
        path = Path(model_path).resolve()
        weights_path = path / "model.safetensors"
        if not path.is_dir() or not weights_path.is_file():
            raise ValueError("Local Embedding model path is incomplete")
        if len(model_bundle_sha256) != 64 or len(weights_sha256) != 64:
            raise ValueError("Local Embedding model Hashes must be SHA-256 values")
        actual_bundle_sha256, file_sha256 = _model_bundle_identity(path)
        if actual_bundle_sha256 != model_bundle_sha256:
            raise ValueError(
                "Local Embedding model bundle SHA-256 does not match the frozen Profile"
            )
        actual_weights_sha256 = file_sha256.get("model.safetensors")
        if actual_weights_sha256 != weights_sha256:
            raise ValueError("Local Embedding weights SHA-256 does not match the frozen Profile")
        if dtype not in {"bfloat16", "float16", "float32"}:
            raise ValueError("Unsupported local Embedding dtype")
        try:
            sentence_transformers = importlib.import_module("sentence_transformers")
            torch = importlib.import_module("torch")
        except ImportError as exc:
            raise RuntimeError(
                "Local Embedding dependencies are missing; sync local-embedding-cu126"
            ) from exc
        if device == "cuda" and not bool(torch.cuda.is_available()):
            raise RuntimeError("Local Embedding requested CUDA but no CUDA device is available")
        torch_dtype = getattr(torch, dtype)
        factory = cast(
            SentenceTransformerFactory,
            getattr(sentence_transformers, "SentenceTransformer"),
        )
        self._model = factory(
            str(path),
            device=device,
            model_kwargs={"torch_dtype": torch_dtype, "attn_implementation": "sdpa"},
            local_files_only=True,
        )
        self._model.max_seq_length = max_length
        self.model_path = path
        self.model_name = model_name
        self.model_bundle_sha256 = model_bundle_sha256
        self.weights_sha256 = weights_sha256
        self.device = device
        self.dtype = dtype
        self.max_length = max_length
        self.batch_size = batch_size
        self.query_prompt_name = query_prompt_name

    @property
    def identity(self) -> str:
        payload = "|".join(
            (
                self.model_name,
                self.model_bundle_sha256,
                self.weights_sha256,
                self.device,
                self.dtype,
                str(self.max_length),
                str(self.batch_size),
                self.query_prompt_name,
                "sdpa",
            )
        )
        return hashlib.sha256(payload.encode()).hexdigest()

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        return self._encode(texts, prompt_name=None)

    def embed_query(self, text: str) -> list[float]:
        return self._encode([text], prompt_name=self.query_prompt_name)[0]

    def _encode(self, texts: Sequence[str], *, prompt_name: str | None) -> list[list[float]]:
        if not texts:
            return []
        matrix = self._model.encode(
            list(texts),
            batch_size=self.batch_size,
            normalize_embeddings=True,
            convert_to_numpy=True,
            show_progress_bar=False,
            prompt_name=prompt_name,
        )
        rows = matrix.tolist()
        if len(rows) != len(texts):
            raise ValueError("Local Embedding result count differs from input count")
        return [[float(value) for value in row] for row in rows]


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _model_bundle_identity(root: Path) -> tuple[str, dict[str, str]]:
    """Hash the complete local snapshot using the frozen, case-insensitive path order."""
    files = [path for path in root.rglob("*") if path.is_file()]
    if any(path.is_symlink() for path in files):
        raise ValueError("Local Embedding model bundle must not contain symbolic links")
    files.sort(key=lambda path: path.relative_to(root).as_posix().casefold())
    entries: list[str] = []
    file_sha256: dict[str, str] = {}
    for path in files:
        relative = path.relative_to(root).as_posix()
        digest = _sha256_file(path)
        file_sha256[relative] = digest
        entries.append(f"{relative}\0{path.stat().st_size}\0{digest}\n")
    bundle_sha256 = hashlib.sha256("".join(entries).encode()).hexdigest()
    return bundle_sha256, file_sha256


def _provider_error_message(response: httpx.Response) -> str:
    try:
        body = response.json()
    except ValueError:
        return "request failed without a structured error"
    if not isinstance(body, Mapping):
        return "request failed without a structured error"
    errors = body.get("errors")
    if isinstance(errors, Mapping) and isinstance(errors.get("message"), str):
        return str(errors["message"])
    error = body.get("error")
    if isinstance(error, Mapping) and isinstance(error.get("message"), str):
        return str(error["message"])
    return "request failed without a structured error"


class VersionedChromaDenseRetriever:
    def __init__(
        self,
        *,
        index_version_id: str,
        collection: DenseCollection,
        embedder: EmbeddingPort,
    ) -> None:
        self.index_version_id = index_version_id
        self.collection = collection
        self.embedder = embedder

    @staticmethod
    def collection_name(course_id: str, index_version_id: str) -> str:
        digest = hashlib.sha256(f"{course_id}|{index_version_id}".encode()).hexdigest()[:20]
        return f"courserag_{digest}"

    def index(
        self,
        *,
        chunk_ids: Sequence[str],
        texts: Sequence[str],
        metadata: Sequence[Mapping[str, object]],
        batch_size: int = 64,
    ) -> None:
        if not (len(chunk_ids) == len(texts) == len(metadata)):
            raise ValueError("Dense index inputs must have matching lengths")
        for start in range(0, len(texts), batch_size):
            stop = start + batch_size
            self.collection.upsert(
                ids=list(chunk_ids[start:stop]),
                embeddings=self.embedder.embed_documents(texts[start:stop]),
                metadatas=list(metadata[start:stop]),
            )

    def search(
        self, query: str, *, filters: RetrievalFilter, top_k: int
    ) -> list[RetrievalCandidate]:
        if filters.index_version_id != self.index_version_id:
            raise ValueError("Dense query index version differs from loaded index")
        where: dict[str, object] = {"index_version_id": self.index_version_id}
        result = self.collection.query(
            query_embeddings=[self.embedder.embed_query(query)],
            n_results=top_k,
            where=where,
            include=["metadatas", "distances"],
        )
        ids = _first_list(result, "ids")
        metadatas = _first_list(result, "metadatas")
        distances = _first_list(result, "distances")
        output: list[RetrievalCandidate] = []
        for position, chunk_id in enumerate(ids):
            metadata = metadatas[position] if position < len(metadatas) else {}
            if not isinstance(metadata, Mapping):
                metadata = {}
            candidate = RetrievalCandidate(
                chunk_id=str(chunk_id),
                document_id=_optional_string(metadata.get("document_id")),
                document_version_id=str(metadata.get("document_version_id", "")),
                section_id=_optional_string(metadata.get("section_id")),
                source_tier=str(metadata.get("source_tier", "primary_source")),
                knowledge_point_ids=_string_tuple(metadata.get("knowledge_point_ids")),
                dense_score=1.0 - _float_value(distances[position]),
            )
            if _matches(candidate, filters):
                output.append(candidate)
        return output


def _first_list(result: Mapping[str, object], key: str) -> list[object]:
    value = result.get(key)
    if not isinstance(value, list) or not value or not isinstance(value[0], list):
        return []
    return value[0]


def _optional_string(value: object) -> str | None:
    return None if value is None else str(value)


def _string_tuple(value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    return tuple(str(item) for item in value)


def _float_value(value: object) -> float:
    if not isinstance(value, int | float):
        raise ValueError("Dense Provider returned a non-numeric distance")
    return float(value)


def _matches(candidate: RetrievalCandidate, filters: RetrievalFilter) -> bool:
    if (
        filters.document_version_ids
        and candidate.document_version_id not in filters.document_version_ids
    ):
        return False
    if filters.document_ids and candidate.document_id not in filters.document_ids:
        return False
    if filters.section_ids and candidate.section_id not in filters.section_ids:
        return False
    if filters.source_tiers and candidate.source_tier not in filters.source_tiers:
        return False
    return not filters.knowledge_point_ids or bool(
        set(filters.knowledge_point_ids) & set(candidate.knowledge_point_ids)
    )
