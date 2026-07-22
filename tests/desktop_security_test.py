from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.desktop_security import DesktopTokenMiddleware, is_desktop_mode


def test_desktop_token_middleware_rejects_api_without_token():
    app = FastAPI()
    app.add_middleware(DesktopTokenMiddleware, token="secret")

    @app.get("/api/protected")
    async def protected():
        return {"ok": True}

    client = TestClient(app)

    response = client.get("/api/protected")

    assert response.status_code == 401


def test_desktop_token_middleware_allows_api_with_token():
    app = FastAPI()
    app.add_middleware(DesktopTokenMiddleware, token="secret")

    @app.get("/api/protected")
    async def protected():
        return {"ok": True}

    client = TestClient(app)

    response = client.get("/api/protected", headers={"X-Pixelle-Desktop-Token": "secret"})

    assert response.status_code == 200
    assert response.json() == {"ok": True}


def test_desktop_token_middleware_allows_health_without_token():
    app = FastAPI()
    app.add_middleware(DesktopTokenMiddleware, token="secret")

    @app.get("/health")
    async def health():
        return {"status": "healthy"}

    client = TestClient(app)

    response = client.get("/health")

    assert response.status_code == 200


def test_desktop_token_middleware_allows_cors_preflight_without_token():
    app = FastAPI()
    app.add_middleware(DesktopTokenMiddleware, token="secret")

    @app.options("/api/protected")
    async def preflight():
        return {"ok": True}

    client = TestClient(app)

    response = client.options("/api/protected")

    assert response.status_code == 200


def test_is_desktop_mode_reads_environment(monkeypatch):
    monkeypatch.setenv("PIXELLE_DESKTOP_MODE", "1")

    assert is_desktop_mode() is True
