from tests.coursepilot.task_test_utils import complete_accepted_task, execute_accepted_task


def _post_twice(client, path, *, key, json=None):
    headers = {"Idempotency-Key": key}
    first = client.post(path, json=json, headers=headers)
    replay = client.post(path, json=json, headers=headers)
    assert first.status_code == replay.status_code
    assert first.json() == replay.json()
    assert "Idempotency-Replayed" not in first.headers
    assert replay.headers["Idempotency-Replayed"] == "true"
    return first


def test_p0_routes_replay_successful_results(coursepilot_client):
    course_response = _post_twice(
        coursepilot_client,
        "/api/coursepilot/courses",
        key="p0-course",
        json={"course_name": "Idempotency"},
    )
    assert course_response.status_code == 201
    course_id = course_response.json()["id"]

    document = coursepilot_client.post(
        f"/api/coursepilot/courses/{course_id}/documents/upload",
        files={
            "file": (
                "idempotency.txt",
                b"state space search heuristic search goal test path cost classroom activity",
            )
        },
        data={"source_type": "textbook"},
    ).json()
    build = _post_twice(
        coursepilot_client,
        f"/api/coursepilot/documents/{document['id']}/build-kb",
        key="p0-build-kb",
    )
    assert build.status_code == 202
    complete_accepted_task(coursepilot_client, build)

    lesson_task = _post_twice(
        coursepilot_client,
        f"/api/coursepilot/courses/{course_id}/lessons/generate",
        key="p0-lesson",
        json={
            "chapter_range": "Search",
            "total_sessions": 2,
            "session_duration": 45,
            "teaching_template": "standard",
        },
    )
    lesson = complete_accepted_task(coursepilot_client, lesson_task)
    lesson_id = lesson["lesson_id"]

    blueprint_task = _post_twice(
        coursepilot_client,
        f"/api/coursepilot/courses/{course_id}/exams/blueprint",
        key="p0-exam-blueprint",
        json={"chapter_range": "Search"},
    )
    blueprint = complete_accepted_task(coursepilot_client, blueprint_task)
    blueprint_id = blueprint["blueprint_id"]
    confirm = coursepilot_client.post(f"/api/coursepilot/exams/{blueprint_id}/confirm")
    assert confirm.status_code == 200
    questions_task = _post_twice(
        coursepilot_client,
        f"/api/coursepilot/exams/{blueprint_id}/generate",
        key="p0-exam-questions",
    )
    complete_accepted_task(coursepilot_client, questions_task)

    ppt_task = _post_twice(
        coursepilot_client,
        f"/api/coursepilot/lessons/{lesson_id}/ppt/generate",
        key="p0-ppt",
        json={
            "slide_count": 6,
            "style_template": "standard",
            "include_references": True,
        },
    )
    complete_accepted_task(coursepilot_client, ppt_task)


def test_same_key_with_changed_request_returns_conflict(coursepilot_client):
    headers = {"Idempotency-Key": "changed-course"}
    first = coursepilot_client.post(
        "/api/coursepilot/courses",
        json={"course_name": "First"},
        headers=headers,
    )
    conflict = coursepilot_client.post(
        "/api/coursepilot/courses",
        json={"course_name": "Second"},
        headers=headers,
    )

    assert first.status_code == 201
    assert conflict.status_code == 409
    assert "different request payload" in conflict.json()["detail"]


def test_failed_async_task_is_reenqueued_with_same_key(coursepilot_client):
    course = coursepilot_client.post(
        "/api/coursepilot/courses",
        json={"course_name": "Retry failed task"},
    ).json()
    path = f"/api/coursepilot/courses/{course['id']}/lessons/generate"
    request = {
        "chapter_range": "Search",
        "total_sessions": 1,
        "session_duration": 45,
    }
    headers = {"Idempotency-Key": "retry-failed-lesson"}

    first = coursepilot_client.post(path, json=request, headers=headers)
    assert first.status_code == 202
    failed = execute_accepted_task(coursepilot_client, first)
    assert failed["status"] == "failed"

    retry = coursepilot_client.post(path, json=request, headers=headers)
    assert retry.status_code == 202
    assert retry.json()["task_id"] != first.json()["task_id"]
    assert "Idempotency-Replayed" not in retry.headers
