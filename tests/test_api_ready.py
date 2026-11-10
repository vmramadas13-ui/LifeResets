from fastapi.testclient import TestClient

from liferesets.main import app

client = TestClient(app)


def test_readiness_endpoint_reports_database_available(monkeypatch) -> None:
    monkeypatch.setattr("liferesets.main.database_is_ready", lambda: True)

    response = client.get("/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ready"}


def test_readiness_endpoint_returns_service_unavailable(monkeypatch) -> None:
    monkeypatch.setattr("liferesets.main.database_is_ready", lambda: False)

    response = client.get("/ready")

    assert response.status_code == 503
    assert response.json() == {
        "error": {
            "code": "database_unavailable",
            "message": "Database is unavailable.",
        }
    }
