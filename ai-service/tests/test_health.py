from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_service_health() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_all_agent_routers_are_mounted() -> None:
    for path in [
        "/role-intelligence/health",
        "/resume-intelligence/health",
        "/matching-engine/health",
        "/interview-orchestrator/health",
        "/evaluation-engine/health",
    ]:
        response = client.get(path)
        assert response.status_code == 200, path
