from fastapi import FastAPI
from fastapi.testclient import TestClient

from liferesets.error_handlers import register_error_handlers


def test_validation_response_does_not_echo_input() -> None:
    app = FastAPI()
    register_error_handlers(app)

    @app.get("/items/{item_id}")
    def read_item(item_id: int) -> dict[str, int]:
        return {"item_id": item_id}

    response = TestClient(app).get("/items/private-value")

    assert response.status_code == 422
    assert response.json() == {
        "error": {
            "code": "validation_error",
            "message": "Request validation failed.",
            "issues": [{"location": ["path", "item_id"], "code": "int_parsing"}],
        }
    }
    assert "private-value" not in response.text


def test_unexpected_error_response_and_log_are_redacted(caplog) -> None:
    app = FastAPI()
    register_error_handlers(app)

    @app.get("/fail")
    def fail() -> None:
        raise RuntimeError("private-value")

    response = TestClient(app, raise_server_exceptions=False).get("/fail")

    assert response.status_code == 500
    assert response.json() == {
        "error": {"code": "internal_error", "message": "An unexpected error occurred."}
    }
    assert "private-value" not in response.text
    assert "private-value" not in caplog.text
