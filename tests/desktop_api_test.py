from types import SimpleNamespace

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


def test_desktop_config_patch_preserves_redacted_api_keys(monkeypatch):
    import api.routers.desktop as desktop_router

    class FakeConfigManager:
        def __init__(self):
            self.config = SimpleNamespace(
                llm=SimpleNamespace(
                    base_url="https://old.example.com/v1",
                    api_key="real-llm-key",
                    model="old-model",
                ),
                comfyui=SimpleNamespace(
                    runninghub_api_key="real-runninghub-key",
                    runninghub_instance_type="plus",
                ),
            )
            self.updates = None

        def update(self, updates):
            self.updates = updates
            llm = updates.get("llm", {})
            if "base_url" in llm:
                self.config.llm.base_url = llm["base_url"]
            if "api_key" in llm:
                self.config.llm.api_key = llm["api_key"]
            if "model" in llm:
                self.config.llm.model = llm["model"]
            comfyui = updates.get("comfyui", {})
            if "runninghub_api_key" in comfyui:
                self.config.comfyui.runninghub_api_key = comfyui["runninghub_api_key"]
            if "runninghub_instance_type" in comfyui:
                self.config.comfyui.runninghub_instance_type = comfyui["runninghub_instance_type"]

        def save(self):
            pass

    fake = FakeConfigManager()
    monkeypatch.setenv("PIXELLE_DESKTOP_MODE", "true")
    monkeypatch.setattr(desktop_router, "config_manager", fake)

    response = _client().patch(
        "/api/desktop/config",
        json={
            "llm": {
                "base_url": "https://new.example.com/v1",
                "api_key": "***redacted***",
                "model": "new-model",
            },
            "runninghub": {
                "api_key": "***redacted***",
                "instance_type": "lite",
            },
        },
    )

    assert response.status_code == 200
    assert fake.config.llm.base_url == "https://new.example.com/v1"
    assert fake.config.llm.api_key == "real-llm-key"
    assert fake.config.comfyui.runninghub_api_key == "real-runninghub-key"
    assert fake.updates == {
        "llm": {
            "base_url": "https://new.example.com/v1",
            "model": "new-model",
        },
        "comfyui": {"runninghub_instance_type": "lite"},
    }


def test_desktop_config_patch_is_disabled_outside_desktop_mode(monkeypatch):
    import api.routers.desktop as desktop_router

    class FakeConfigManager:
        def __init__(self):
            self.config = SimpleNamespace(
                llm=SimpleNamespace(base_url="", api_key="", model=""),
                comfyui=SimpleNamespace(runninghub_api_key="", runninghub_instance_type=""),
            )
            self.updated = False

        def update(self, updates):
            self.updated = True

        def save(self):
            self.updated = True

    fake = FakeConfigManager()
    monkeypatch.delenv("PIXELLE_DESKTOP_MODE", raising=False)
    monkeypatch.setattr(desktop_router, "config_manager", fake)

    response = _client().patch(
        "/api/desktop/config",
        json={"llm": {"api_key": "new-key"}},
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "配置写入仅支持桌面端本地运行。"
    assert fake.updated is False
