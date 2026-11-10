from fastapi.testclient import TestClient

from liferesets.main import app

client = TestClient(app)


def test_health_endpoint_reports_process_status() -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
