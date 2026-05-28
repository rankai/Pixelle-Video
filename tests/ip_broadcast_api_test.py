from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routers.ip_broadcast import router
from pixelle_video.services.ip_broadcast_workflow import (
    IpBroadcastSessionStore,
    run_ip_broadcast_step,
)


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(router, prefix="/api")
    return TestClient(app)


def test_create_ip_broadcast_session_returns_default_state():
    client = _client()

    response = client.post("/api/ip-broadcast/sessions")

    assert response.status_code == 200
    payload = response.json()
    assert payload["session_id"]
    assert payload["current_step"] == 1
    assert payload["completed_steps"] == 0
    assert payload["next_action"]["key"] == "source"
    assert payload["step_status"]["1"] == "pending"
    assert payload["artifacts"] == {}


def test_update_session_config_moves_ready_state_to_copywriting_step():
    client = _client()
    session_id = client.post("/api/ip-broadcast/sessions").json()["session_id"]

    response = client.patch(
        f"/api/ip-broadcast/sessions/{session_id}/config",
        json={"final_script": "这是一段老板口播文案。"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["current_step"] == 2
    assert payload["completed_steps"] == 1
    assert payload["next_action"]["key"] == "copywriting"
    assert payload["step_status"]["1"] == "done"
    assert payload["step_status"]["2"] == "ready"


async def test_run_source_step_uses_pasted_text_without_streamlit():
    store = IpBroadcastSessionStore()
    session = store.create_session()
    store.update_config(
        session.session_id,
        {
            "source_mode": "paste",
            "source_text": "粘贴的原始口播文案。",
        },
    )

    result = await run_ip_broadcast_step(
        pixelle_video=None,
        session=session,
        step_key="source",
    )

    assert result is True
    assert session.state["final_script"] == "粘贴的原始口播文案。"
    assert session.step_status[1] == "done"
    assert session.step_status[2] == "ready"
    assert session.next_action()["key"] == "copywriting"


def test_artifact_download_rejects_unknown_artifact():
    client = _client()
    session_id = client.post("/api/ip-broadcast/sessions").json()["session_id"]

    response = client.get(f"/api/ip-broadcast/sessions/{session_id}/artifacts/not-found")

    assert response.status_code == 404
