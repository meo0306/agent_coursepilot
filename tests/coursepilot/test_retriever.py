from langchain_core.embeddings import Embeddings

from coursepilot.rag.vector_store import ChromaVectorStore


class RaisingEmbeddings(Embeddings):
    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [[0.0] for _ in texts]

    def embed_query(self, text: str) -> list[float]:
        raise AssertionError("empty collections should not embed the query")


def test_build_kb_and_search_returns_course_scoped_chunks(coursepilot_client):
    course = coursepilot_client.post(
        "/api/coursepilot/courses",
        json={"course_name": "AI"},
    ).json()
    other_course = coursepilot_client.post(
        "/api/coursepilot/courses",
        json={"course_name": "Math"},
    ).json()

    document = coursepilot_client.post(
        f"/api/coursepilot/courses/{course['id']}/documents/upload",
        files={"file": ("lesson.txt", b"state space search and heuristic search")},
        data={"source_type": "textbook"},
    ).json()
    other_document = coursepilot_client.post(
        f"/api/coursepilot/courses/{other_course['id']}/documents/upload",
        files={"file": ("math.txt", b"linear algebra and matrix factorization")},
        data={"source_type": "textbook"},
    ).json()

    build_response = coursepilot_client.post(
        f"/api/coursepilot/documents/{document['id']}/build-kb"
    )
    other_build_response = coursepilot_client.post(
        f"/api/coursepilot/documents/{other_document['id']}/build-kb"
    )

    assert build_response.status_code == 200
    assert build_response.json()["parse_status"] == "built"
    assert build_response.json()["chunk_count"] >= 1
    assert other_build_response.status_code == 200

    search_response = coursepilot_client.post(
        f"/api/coursepilot/courses/{course['id']}/kb/search",
        json={"query": "heuristic search", "top_k": 5},
    )

    assert search_response.status_code == 200
    results = search_response.json()["results"]
    assert results
    assert all(result["course_id"] == course["id"] for result in results)
    assert any("heuristic search" in result["content"] for result in results)


def test_upload_rejects_legacy_doc(coursepilot_client):
    course = coursepilot_client.post(
        "/api/coursepilot/courses",
        json={"course_name": "AI"},
    ).json()
    response = coursepilot_client.post(
        f"/api/coursepilot/courses/{course['id']}/documents/upload",
        files={"file": ("legacy.doc", b"legacy word file")},
        data={"source_type": "syllabus"},
    )

    assert response.status_code == 400
    assert "convert it to .docx" in response.json()["detail"]


def test_empty_vector_collection_returns_no_results_without_embedding(tmp_path):
    vector_store = ChromaVectorStore(
        persist_directory=str(tmp_path / "chroma"),
        embeddings=RaisingEmbeddings(),
    )

    assert (
        vector_store.search(
            course_id="empty-course",
            query="heuristic search",
            top_k=5,
        )
        == []
    )

