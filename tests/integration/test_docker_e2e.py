from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from client import AgentClient


@pytest.mark.docker
def test_service_prompt_entry_agent():
    client = AgentClient("http://0.0.0.0", agent="coursepilot-lesson-agent")

    response = client.invoke("hello")

    assert response.type == "ai"
    assert "/api/coursepilot/courses/{course_id}/lessons/generate" in response.content


@pytest.mark.docker
def test_streamlit_app_loads_coursepilot_page():
    app_path = Path(__file__).resolve().parents[2] / "src" / "streamlit_app.py"
    at = AppTest.from_file(str(app_path)).run(timeout=10)

    assert at.title[0].value == "CoursePilot Knowledge Base"
    assert not at.exception
