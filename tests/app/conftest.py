from unittest.mock import patch

import pytest


@pytest.fixture
def mock_coursepilot_client(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.setenv("AGENT_URL", "http://coursepilot.test")
    monkeypatch.setenv("AUTH_SECRET", "test-secret")

    with patch("coursepilot.ui.knowledge_base_page.CoursePilotClient") as mocked:
        client = mocked.return_value
        client.list_courses.return_value = []
        yield client, mocked
