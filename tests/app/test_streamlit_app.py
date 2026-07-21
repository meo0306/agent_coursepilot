from streamlit.testing.v1 import AppTest


def test_app_loads_coursepilot_page(mock_coursepilot_client):
    client, mocked_client_class = mock_coursepilot_client

    at = AppTest.from_file("../../src/streamlit_app.py").run(timeout=10)

    mocked_client_class.assert_called_with(
        base_url="http://coursepilot.test",
        headers={"Authorization": "Bearer test-secret"},
        timeout=30,
    )
    client.list_courses.assert_called_once()
    assert at.title[0].value == "CoursePilot Knowledge Base"
    assert at.info[0].value == "Create a course before uploading documents."
    assert not at.exception
