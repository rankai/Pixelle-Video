from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routers.desktop import router


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(router, prefix="/api")
    return TestClient(app)


def test_desktop_diagnostics_reports_dependency_keys():
    response = _client().get("/api/desktop/diagnostics")

    assert response.status_code == 200
    payload = response.json()
    assert {"ffmpeg", "playwright", "yt_dlp", "config"} <= set(payload)


def test_desktop_config_response_redacts_api_keys():
    response = _client().get("/api/desktop/config")

    assert response.status_code == 200
    payload = response.json()
    assert "api_key" in payload["llm"]
    assert payload["llm"]["api_key"] in {"", "***redacted***"}
    assert payload["runninghub"]["api_key"] in {"", "***redacted***"}
