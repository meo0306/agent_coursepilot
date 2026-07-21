import pytest
from fastapi.testclient import TestClient

from service import app


@pytest.fixture
def test_client():
    return TestClient(app)
