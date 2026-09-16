import hashlib
from collections.abc import Mapping, Sequence
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import httpx
import pytest

from courserag.indexing.dense import (
    LocalSentenceTransformerEmbeddingAdapter,
    OpenAICompatibleEmbeddingAdapter,
    VersionedChromaDenseRetriever,
    _model_bundle_identity,
)
from courserag.indexing.sparse import SparseDocument, VersionedBM25Index
from courserag.retrieval.models import RetrievalFilter
from courserag.retrieval.tokenizer import search_tokens


class FakeEmbedder:
    identity = "fake"

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        return [[float(len(item))] for item in texts]

    def embed_query(self, text: str) -> list[float]:
        return [float(len(text))]


class FakeCollection:
    def __init__(self) -> None:
        self.upserts: list[dict[str, object]] = []

    def upsert(self, **kwargs: object) -> None:
        self.upserts.append(kwargs)

    def query(self, **kwargs: object) -> Mapping[str, object]:
        assert kwargs["where"] == {"index_version_id": "iv-1"}
        return {
            "ids": [["chunk-1"]],
            "metadatas": [
                [
                    {
                        "document_version_id": "dv-1",
                        "section_id": "s-1",
                        "source_tier": "primary_source",
                    }
                ]
            ],
            "distances": [[0.1]],
            "documents": [["untrusted chroma text"]],
        }


class FakeEmbeddingMatrix:
    def __init__(self, rows: list[list[float]]) -> None:
        self.rows = rows

    def tolist(self) -> list[list[float]]:
        return self.rows


class FakeSentenceTransformer:
    def __init__(self) -> None:
        self.max_seq_length = 0
        self.calls: list[dict[str, object]] = []

    def encode(self, sentences: list[str], **kwargs: object) -> FakeEmbeddingMatrix:
        self.calls.append({"sentences": sentences, **kwargs})
        return FakeEmbeddingMatrix([[float(index), 1.0] for index, _ in enumerate(sentences)])


def test_openai_compatible_embedding_requests_float_encoding() -> None:
    request = httpx.Request("POST", "https://embedding.invalid/v1/embeddings")
    response = httpx.Response(
        200,
        request=request,
        json={"data": [{"index": 0, "embedding": [0.25, 0.75]}]},
    )
    with patch("courserag.indexing.dense.httpx.post", return_value=response) as post:
        adapter = OpenAICompatibleEmbeddingAdapter(
            endpoint="https://embedding.invalid/v1",
            api_key="test-key",
            model="test-model",
        )
        assert adapter.embed_query("query") == [0.25, 0.75]

    assert post.call_args.kwargs["json"] == {
        "model": "test-model",
        "input": ["query"],
        "encoding_format": "float",
    }


def test_openai_compatible_embedding_exposes_only_structured_provider_error() -> None:
    request = httpx.Request("POST", "https://embedding.invalid/v1/embeddings")
    response = httpx.Response(
        400,
        request=request,
        json={"errors": {"message": "input is too large"}, "request_id": "request-1"},
    )
    with (
        patch("courserag.indexing.dense.httpx.post", return_value=response),
        pytest.raises(
            RuntimeError,
            match=r"^Embedding Provider HTTP 400: input is too large$",
        ),
    ):
        OpenAICompatibleEmbeddingAdapter(
            endpoint="https://embedding.invalid/v1",
            api_key="must-not-appear",
            model="test-model",
        ).embed_query("must-not-appear")


def test_local_sentence_transformer_is_hash_bound_and_uses_query_prompt(tmp_path: Path) -> None:
    weights = tmp_path / "model.safetensors"
    weights.write_bytes(b"frozen-weights")
    weights_sha256 = hashlib.sha256(b"frozen-weights").hexdigest()
    bundle_sha256, _ = _model_bundle_identity(tmp_path)
    model = FakeSentenceTransformer()
    factory_calls: list[dict[str, object]] = []

    def factory(path: str, **kwargs: object) -> FakeSentenceTransformer:
        factory_calls.append({"path": path, **kwargs})
        return model

    fake_sentence_transformers = SimpleNamespace(SentenceTransformer=factory)
    fake_torch = SimpleNamespace(
        cuda=SimpleNamespace(is_available=lambda: True),
        bfloat16="bf16",
        float16="fp16",
        float32="fp32",
    )

    def import_module(name: str) -> object:
        return fake_sentence_transformers if name == "sentence_transformers" else fake_torch

    with patch("courserag.indexing.dense.importlib.import_module", side_effect=import_module):
        adapter = LocalSentenceTransformerEmbeddingAdapter(
            model_path=tmp_path,
            model_name="Qwen/Qwen3-Embedding-0.6B",
            model_bundle_sha256=bundle_sha256,
            weights_sha256=weights_sha256,
            max_length=2048,
            batch_size=8,
        )
        assert adapter.embed_documents(["doc-a", "doc-b"]) == [[0.0, 1.0], [1.0, 1.0]]
        assert adapter.embed_query("query") == [0.0, 1.0]

    assert factory_calls[0]["local_files_only"] is True
    assert model.max_seq_length == 2048
    assert model.calls[0]["prompt_name"] is None
    assert model.calls[1]["prompt_name"] == "query"
    assert len(adapter.identity) == 64


def test_local_sentence_transformer_rejects_bundle_drift(tmp_path: Path) -> None:
    weights = tmp_path / "model.safetensors"
    weights.write_bytes(b"frozen-weights")
    weights_sha256 = hashlib.sha256(b"frozen-weights").hexdigest()

    with pytest.raises(ValueError, match="bundle SHA-256"):
        LocalSentenceTransformerEmbeddingAdapter(
            model_path=tmp_path,
            model_name="Qwen/Qwen3-Embedding-0.6B",
            model_bundle_sha256="1" * 64,
            weights_sha256=weights_sha256,
        )


def test_search_tokenizer_preserves_special_terms() -> None:
    tokens = search_tokens("C++ 与 A* 在 Python 3.11 中")
    assert "c++" in tokens
    assert "a*" in tokens
    assert "3.11" in tokens


def test_bm25_is_version_bound_and_searches_chinese() -> None:
    index = VersionedBM25Index(
        index_version_id="iv-1",
        documents=[
            SparseDocument("c1", "dv", "启发式搜索使用领域知识"),
            SparseDocument("c2", "dv", "数据库事务保证一致性"),
        ],
    )
    result = index.search(
        "启发式搜索",
        filters=RetrievalFilter(course_id="course", index_version_id="iv-1"),
        top_k=1,
    )
    assert result[0].chunk_id == "c1"
    assert result[0].sparse_score is not None


def test_bm25_matrix_mapping_and_tokenizer_identity_are_rebuildable(tmp_path: Path) -> None:
    index = VersionedBM25Index(
        index_version_id="iv-1",
        documents=[SparseDocument("c1", "dv", "C++ 启发式搜索")],
    )
    index.save(tmp_path / "sparse")
    loaded = VersionedBM25Index.load(tmp_path / "sparse")
    assert loaded.corpus_sha256 == index.corpus_sha256
    result = loaded.search(
        "C++",
        filters=RetrievalFilter(course_id="course", index_version_id="iv-1"),
        top_k=1,
    )
    assert result[0].chunk_id == "c1"


def test_dense_batches_and_never_returns_chroma_document() -> None:
    collection = FakeCollection()
    retriever = VersionedChromaDenseRetriever(
        index_version_id="iv-1", collection=collection, embedder=FakeEmbedder()
    )
    retriever.index(
        chunk_ids=["c1", "c2"],
        texts=["one", "two"],
        metadata=[{"index_version_id": "iv-1"}, {"index_version_id": "iv-1"}],
        batch_size=1,
    )
    assert len(collection.upserts) == 2
    result = retriever.search(
        "query",
        filters=RetrievalFilter(course_id="course", index_version_id="iv-1"),
        top_k=1,
    )
    assert result[0].chunk_id == "chunk-1"
    assert result[0].text == ""
    assert result[0].dense_score == 0.9
