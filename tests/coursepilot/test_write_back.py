from coursepilot.rag.vector_store import ChromaVectorStore


def test_rejected_review_does_not_write_to_vector_store(coursepilot_client, monkeypatch):
    calls = []

    def fake_add_verified_texts(self, **kwargs):
        calls.append(kwargs)
        return "coursepilot_test"

    monkeypatch.setattr(ChromaVectorStore, "add_verified_texts", fake_add_verified_texts)

    course = coursepilot_client.post("/api/coursepilot/courses", json={"course_name": "AI"}).json()
    missing_target = coursepilot_client.post(
        "/api/coursepilot/reviews",
        json={
            "target_type": "ppt_outline",
            "target_id": course["id"],
            "review_status": "rejected",
        },
    )

    assert missing_target.status_code == 404
    assert calls == []
