from coursepilot.rag.chunker import Chunker
from coursepilot.rag.types import ParsedDocument, ParsedSection


def test_chunker_splits_long_document_with_metadata():
    parsed = ParsedDocument(
        source_path="sample.txt",
        sections=[
            ParsedSection(
                content="第1章 搜索算法\n\n"
                + "状态空间搜索是人工智能中的基础问题。" * 80,
                page=3,
            )
        ],
    )

    chunks = Chunker(chunk_size=200, overlap=20).split(
        parsed,
        course_id="course-1",
        document_id="doc-1",
        source_type="textbook",
    )

    assert len(chunks) > 1
    assert all(chunk.course_id == "course-1" for chunk in chunks)
    assert all(chunk.document_id == "doc-1" for chunk in chunks)
    assert chunks[0].page == 3
    assert chunks[0].knowledge_points

