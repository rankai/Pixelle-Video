from pathlib import Path
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from pixelle_video.services.publish.core_models import PublishRunState


def test_batch4_probe_is_local_bounded_and_has_no_external_action_path():
    source = Path("scripts/program_rollout_batch4_smoke.py").read_text(encoding="utf-8")
    assert "passed_local_bounded" in source
    assert '"external_actions": 0' in source
    assert '"final_publish_clicks": 0' in source
    assert "BrowserProfileManager" in source
    assert "_rollback_rehearsal" in source
    assert "platform adapter" in source
    api_source = Path("api/routers/publish_v2.py").read_text(encoding="utf-8")
    assert "PIXELLE_ROLLOUT_LOCAL_NOOP" in api_source
    assert "auto_start=not local_noop" in api_source


def test_batch4_probe_records_api_ui_p95_and_releases_ports():
    source = Path("scripts/program_rollout_batch4_smoke.py").read_text(encoding="utf-8")
    assert "api_p95_ms" in source
    assert "ui_shell_p95_ms" in source
    assert '"port_released"' in source
    assert "_stop(api)" in source
    assert "_stop_ui(ui)" in source
    assert "_port_open(UI_PORT)" in source


def test_batch4_qa_boundary_keeps_pg_l_open():
    qa = Path(
        "docs/reviews/application-publishing-program/qa/PROGRAM-ROLLOUT-crash-lock-p95-rollback-2026-07-21.json"
    ).read_text(encoding="utf-8")
    assert '"pg_l": "open"' in qa
    assert '"external_actions": 0' in qa
    assert '"final_publish_clicks": 0' in qa


def test_local_rollout_noop_create_run_never_schedules_executor(monkeypatch):
    import api.routers.publish_v2 as publish_v2

    class FakeService:
        def __init__(self):
            self.auto_start = None

        def create_run(self, *_args, auto_start):
            self.auto_start = auto_start
            return SimpleNamespace(run_id="run_rollout_noop", task_id=None, state=PublishRunState.QUEUED), False

    fake = FakeService()
    monkeypatch.setenv("PIXELLE_DESKTOP_MODE", "1")
    monkeypatch.setenv("PIXELLE_PUBLISH_V2_ENABLED", "1")
    monkeypatch.setenv("PIXELLE_LOCAL_CAPABILITY", "batch4-cap")
    monkeypatch.setenv("PIXELLE_ROLLOUT_LOCAL_NOOP", "true")
    monkeypatch.setattr(publish_v2, "get_publish_run_service", lambda: fake)
    app = FastAPI()
    app.include_router(publish_v2.router, prefix="/api")

    with TestClient(app) as client:
        response = client.post(
            "/api/publish/v2/runs",
            headers={"X-Pixelle-Local-Capability": "batch4-cap", "Origin": "tauri://localhost"},
            json={
                "package_id": "pkg_rollout",
                "account_id": "acct_rollout",
                "platform": "douyin",
                "idempotency_key": "rollout-noop-001",
            },
        )
    assert response.status_code == 202
    assert fake.auto_start is False
