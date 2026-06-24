def test_course_crud(coursepilot_client):
    create_response = coursepilot_client.post(
        "/api/coursepilot/courses",
        json={
            "course_name": "Artificial Intelligence",
            "course_type": "theory",
            "student_level": "undergraduate",
            "student_background": "computer science",
            "description": "AI course",
        },
    )
    assert create_response.status_code == 201
    course = create_response.json()
    assert course["course_name"] == "Artificial Intelligence"

    list_response = coursepilot_client.get("/api/coursepilot/courses")
    assert list_response.status_code == 200
    assert len(list_response.json()) == 1

    update_response = coursepilot_client.put(
        f"/api/coursepilot/courses/{course['id']}",
        json={"course_name": "AI Systems"},
    )
    assert update_response.status_code == 200
    assert update_response.json()["course_name"] == "AI Systems"

    delete_response = coursepilot_client.delete(f"/api/coursepilot/courses/{course['id']}")
    assert delete_response.status_code == 204

