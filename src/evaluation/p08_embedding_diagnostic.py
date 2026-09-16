from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path

from core.settings import settings
from courserag.indexing.dense import OpenAICompatibleEmbeddingAdapter
from courserag.retrieval.models import RetrievalCandidate
from evaluation.p08_corpus import load_p08_child_corpus


def _probe(
    adapter: OpenAICompatibleEmbeddingAdapter,
    items: Sequence[RetrievalCandidate],
    *,
    offset: int,
) -> None:
    try:
        adapter.embed_documents([item.text for item in items])
    except RuntimeError as exc:
        if len(items) == 1:
            print(
                {
                    "range": f"{offset}:{offset + 1}",
                    "chunk_id": items[0].chunk_id,
                    "status": "rejected",
                    "reason": str(exc),
                }
            )
            return
        midpoint = len(items) // 2
        _probe(adapter, items[:midpoint], offset=offset)
        _probe(adapter, items[midpoint:], offset=offset + midpoint)
        return
    print({"range": f"{offset}:{offset + len(items)}", "status": "ok"})


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--course-offset", type=int, default=0)
    parser.add_argument("--count", type=int, default=64)
    args = parser.parse_args()
    if args.course_offset < 0 or not 1 <= args.count <= 64:
        raise ValueError("Diagnostic range must contain 1-64 non-negative-offset items")
    corpora = load_p08_child_corpus(Path.cwd())
    course_id, corpus = next(iter(corpora.items()))
    selected = corpus[args.course_offset : args.course_offset + args.count]
    if len(selected) != args.count:
        raise ValueError("Diagnostic range exceeds the first P08 course corpus")
    if (
        settings.COURSERAG_EMBEDDING_BASE_URL is None
        or settings.COURSERAG_EMBEDDING_API_KEY is None
        or settings.COURSERAG_EMBEDDING_MODEL is None
    ):
        raise ValueError("CourseRAG Embedding configuration is incomplete")
    print(
        {
            "course_id": course_id,
            "range": f"{args.course_offset}:{args.course_offset + args.count}",
            "content_logged": False,
        }
    )
    adapter = OpenAICompatibleEmbeddingAdapter(
        endpoint=settings.COURSERAG_EMBEDDING_BASE_URL,
        api_key=settings.COURSERAG_EMBEDDING_API_KEY.get_secret_value(),
        model=settings.COURSERAG_EMBEDDING_MODEL,
        timeout_seconds=settings.COURSERAG_EMBEDDING_TIMEOUT_SECONDS,
    )
    _probe(adapter, selected, offset=args.course_offset)


if __name__ == "__main__":
    main()
