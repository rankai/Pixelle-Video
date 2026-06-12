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
    assert {item["id"] for item in payload["checks"]} >= {
        "ffmpeg",
        "playwright",
        "yt_dlp",
        "output_dir",
        "llm_config",
        "runninghub_config",
    }
    assert {"id", "label", "status", "message"} <= set(payload["checks"][0])


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


def test_desktop_config_check_uses_request_draft(monkeypatch):
    monkeypatch.setenv("PIXELLE_DESKTOP_MODE", "true")

    response = _client().post(
        "/api/desktop/config/check",
        json={
            "llm": {
                "base_url": "https://draft.example.com/v1",
                "api_key": "draft-key",
                "model": "draft-model",
            },
            "runninghub": {
                "api_key": "",
                "instance_type": "",
            },
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is False
    assert payload["checks"][0] == {
        "id": "llm",
        "label": "LLM 配置",
        "status": "warning",
        "message": "LLM 配置项已填写，尚未验证服务账号是否可用。生成失败时请检查 Key、模型和余额。",
    }
    assert payload["checks"][1]["id"] == "runninghub"
    assert payload["checks"][1]["status"] == "missing"
    assert "配置 > 云端生成" in payload["checks"][1]["message"]


def test_desktop_config_check_is_disabled_outside_desktop_mode(monkeypatch):
    monkeypatch.delenv("PIXELLE_DESKTOP_MODE", raising=False)

    response = _client().post(
        "/api/desktop/config/check",
        json={"llm": {"api_key": "draft-key"}},
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "配置检查仅支持桌面端本地运行。"
