from fastapi.testclient import TestClient

from bridge.api import app


def test_healthz_returns_only_ok_status() -> None:
    with TestClient(app) as client:
        response = client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
