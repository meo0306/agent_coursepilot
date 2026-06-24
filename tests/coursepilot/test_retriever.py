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


def test_build_kb_marks_unsupported_doc_as_failed(coursepilot_client):
    course = coursepilot_client.post(
        "/api/coursepilot/courses",
        json={"course_name": "AI"},
    ).json()
    document = coursepilot_client.post(
        f"/api/coursepilot/courses/{course['id']}/documents/upload",
        files={"file": ("legacy.doc", b"legacy word file")},
        data={"source_type": "syllabus"},
    ).json()

    response = coursepilot_client.post(f"/api/coursepilot/documents/{document['id']}/build-kb")

    assert response.status_code == 200
    assert response.json()["parse_status"] == "failed"
    assert "Unsupported parser" in response.json()["error_message"]

