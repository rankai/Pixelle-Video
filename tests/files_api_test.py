from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routers.files import router


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(router, prefix="/api")
    return TestClient(app)


def test_files_endpoint_rejects_parent_directory_escape(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "config.yaml").write_text("secret: value", encoding="utf-8")
    (tmp_path / "output").mkdir()

    response = _client().get("/api/files/output/%2E%2E/config.yaml")

    assert response.status_code == 403


def test_files_endpoint_serves_allowed_output_file(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    output = tmp_path / "output"
    output.mkdir()
    (output / "result.txt").write_text("ok", encoding="utf-8")

    response = _client().get("/api/files/output/result.txt")

    assert response.status_code == 200
    assert response.text == "ok"
