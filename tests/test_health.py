"""Tests for the health check endpoint."""

from fastapi.testclient import TestClient

from backend.main import app

client = TestClient(app)


def test_health():
    """Verify that the GET /health endpoint returns the expected status, project, and phase."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["project"] == "RuleWise AI"
    assert data["phase"] == 1
