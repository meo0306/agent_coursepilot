def test_document_upload_creates_record(coursepilot_client):
    course = coursepilot_client.post(
        "/api/coursepilot/courses",
        json={"course_name": "AI"},
    ).json()

    response = coursepilot_client.post(
        f"/api/coursepilot/courses/{course['id']}/documents/upload",
        files={"file": ("lesson.txt", b"search algorithms and state space")},
        data={"source_type": "textbook"},
    )

    assert response.status_code == 201
    document = response.json()
    assert document["course_id"] == course["id"]
    assert document["file_type"] == "txt"
    assert document["source_type"] == "textbook"
    assert document["parse_status"] == "uploaded"


def test_document_upload_rejects_unknown_type(coursepilot_client):
    course = coursepilot_client.post(
        "/api/coursepilot/courses",
        json={"course_name": "AI"},
    ).json()

    response = coursepilot_client.post(
        f"/api/coursepilot/courses/{course['id']}/documents/upload",
        files={"file": ("malware.exe", b"nope")},
        data={"source_type": "textbook"},
    )

    assert response.status_code == 400
    assert "Unsupported file type" in response.json()["detail"]
