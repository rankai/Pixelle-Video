from types import SimpleNamespace

import pytest

from pixelle_video.services.digital_human_service import (
    _build_ai_app_node_info_list,
    _build_ai_app_run_request,
    _build_workflow_params,
    _extract_video_output,
    _load_workflow_config,
    _make_runninghub_ai_app_run_request,
    _query_runninghub_ai_app_task,
    _resolve_workflow_input,
    _runninghub_ai_app_headers,
    _runninghub_ai_app_outputs_to_result,
    _upload_runninghub_ai_app_media,
    _wait_for_runninghub_task,
    list_digital_human_workflows,
)


def test_extract_video_output_prefers_result_videos():
    result = SimpleNamespace(
        videos=["https://cdn.example.com/main.mp4"],
        files=["https://cdn.example.com/backup.mp4"],
        outputs={},
    )

    assert _extract_video_output(result) == "https://cdn.example.com/main.mp4"


def test_extract_video_output_falls_back_to_files():
    result = SimpleNamespace(
        videos=[],
        files=["https://cdn.example.com/result.webm"],
        outputs={},
    )

    assert _extract_video_output(result) == "https://cdn.example.com/result.webm"


def test_extract_video_output_searches_nested_outputs():
    result = SimpleNamespace(
        videos=[],
        files=[],
        outputs={
            "node_42": {
                "video": {
                    "url": "https://cdn.example.com/generated.mp4",
                    "filename": "generated.mp4",
                }
            }
        },
    )

    assert _extract_video_output(result) == "https://cdn.example.com/generated.mp4"


def test_resolve_workflow_input_reads_home_runninghub_config(tmp_path):
    workflow_path = tmp_path / "workflows" / "runninghub" / "digital_combination.json"
    workflow_path.parent.mkdir(parents=True)
    workflow_path.write_text(
        '{"source": "runninghub", "workflow_id": "2003717471859294210"}',
        encoding="utf-8",
    )

    workflow_input = _resolve_workflow_input(str(workflow_path))

    assert workflow_input == "2003717471859294210"


def test_resolve_workflow_input_normalizes_bare_runninghub_path(tmp_path, monkeypatch):
    workflow_path = tmp_path / "workflows" / "runninghub" / "digital_combination.json"
    workflow_path.parent.mkdir(parents=True)
    workflow_path.write_text(
        '{"source": "runninghub", "workflow_id": "home-workflow-id"}',
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)

    workflow_input = _resolve_workflow_input("runninghub/digital_combination.json")

    assert workflow_input == "home-workflow-id"


def test_resolve_workflow_input_raises_clear_error_for_missing_file(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    with pytest.raises(FileNotFoundError, match="Workflow file does not exist"):
        _resolve_workflow_input("runninghub/missing.json")


def test_load_workflow_config_reads_ip_broadcast_metadata(tmp_path):
    workflow_path = tmp_path / "workflows" / "runninghub" / "digital_talk_image_prompt.json"
    workflow_path.parent.mkdir(parents=True)
    workflow_path.write_text(
        """
        {
          "source": "runninghub",
          "workflow_id": "2030929648594460673",
          "display_name": "数字人口播",
          "ip_broadcast": {
            "params": {
              "audio": "audio",
              "portrait": "image",
              "duration": "duration",
              "prompt": "prompt"
            }
          }
        }
        """,
        encoding="utf-8",
    )

    config = _load_workflow_config(str(workflow_path))

    assert config["workflow_id"] == "2030929648594460673"
    assert config["ip_broadcast"]["params"]["prompt"] == "prompt"


def test_build_workflow_params_uses_configured_duration_and_prompt_keys():
    workflow_config = {
        "ip_broadcast": {
            "params": {
                "audio": "audio",
                "portrait": "image",
                "duration": "duration",
                "prompt": "prompt",
            }
        }
    }

    params = _build_workflow_params(
        workflow_config,
        portrait_path="/tmp/person.png",
        audio_path="/tmp/voice.mp3",
        duration=8.5,
        prompt="自然口播，正面镜头",
    )

    assert params == {
        "audio": "/tmp/voice.mp3",
        "image": "/tmp/person.png",
        "duration": 8.5,
        "prompt": "自然口播，正面镜头",
    }


def test_build_ai_app_node_info_list_uses_runninghub_api_node_mapping():
    workflow_config = {
        "ip_broadcast": {
            "params": {
                "audio": {"node_id": "48", "field_name": "audio", "description": "audio"},
                "portrait": {"node_id": "35", "field_name": "image", "description": "image"},
                "duration": {"node_id": "115", "field_name": "value", "description": "时长S"},
                "prompt": {"node_id": "105", "field_name": "text", "description": "prompt"},
            }
        }
    }

    node_info = _build_ai_app_node_info_list(
        workflow_config,
        uploaded_portrait="portrait.png",
        uploaded_audio="voice.mp3",
        duration=28,
        prompt="女孩说话，正视镜头",
    )

    assert node_info == [
        {
            "nodeId": "35",
            "fieldName": "image",
            "fieldValue": "portrait.png",
            "description": "image",
        },
        {
            "nodeId": "48",
            "fieldName": "audio",
            "fieldValue": "voice.mp3",
            "description": "audio",
        },
        {
            "nodeId": "115",
            "fieldName": "value",
            "fieldValue": "28",
            "description": "时长S",
        },
        {
            "nodeId": "105",
            "fieldName": "text",
            "fieldValue": "女孩说话，正视镜头",
            "description": "prompt",
        },
    ]


def test_build_ai_app_run_request_uses_documented_endpoint():
    endpoint, payload = _build_ai_app_run_request(
        webapp_id="2030929648594460673",
        api_key="rk-test",
        node_info_list=[{"nodeId": "48", "fieldName": "audio", "fieldValue": "voice.mp3"}],
    )

    assert endpoint == "/openapi/v2/run/ai-app/2030929648594460673"
    assert payload == {
        "nodeInfoList": [{"nodeId": "48", "fieldName": "audio", "fieldValue": "voice.mp3"}],
        "instanceType": "default",
        "usePersonalQueue": "false",
    }


def test_build_ai_app_run_request_can_include_legacy_api_key_fallback():
    endpoint, payload = _build_ai_app_run_request(
        webapp_id="2030929648594460673",
        api_key="rk-test",
        node_info_list=[],
        include_api_key=True,
    )

    assert endpoint == "/openapi/v2/run/ai-app/2030929648594460673"
    assert payload["apiKey"] == "rk-test"


def test_build_ai_app_run_request_uses_configured_instance_type():
    endpoint, payload = _build_ai_app_run_request(
        webapp_id="2030929648594460673",
        api_key="rk-test",
        node_info_list=[],
        instance_type="plus",
        use_personal_queue=True,
    )

    assert endpoint == "/openapi/v2/run/ai-app/2030929648594460673"
    assert payload["instanceType"] == "plus"
    assert payload["usePersonalQueue"] == "true"


def test_resolve_runninghub_api_key_falls_back_to_environment(monkeypatch):
    from pixelle_video.services.digital_human_service import _resolve_runninghub_api_key

    monkeypatch.setenv("RUNNINGHUB_API_KEY", "env-key")

    assert _resolve_runninghub_api_key({"runninghub_api_key": ""}) == "env-key"


def test_runninghub_ai_app_headers_include_bearer_auth():
    assert _runninghub_ai_app_headers("rk-test") == {
        "Authorization": "Bearer rk-test",
        "Content-Type": "application/json",
    }


@pytest.mark.asyncio
async def test_upload_ai_app_media_uses_openapi_v2_binary_upload(tmp_path):
    media_path = tmp_path / "portrait.png"
    media_path.write_bytes(b"image")

    class FakeResponse:
        status = 200

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def json(self):
            return {
                "code": 0,
                "message": "success",
                "data": {
                    "download_url": "https://cdn.runninghub.cn/openapi/portrait.png",
                    "fileName": "openapi/portrait.png",
                },
            }

        async def text(self):
            return '{"code":0}'

    class FakeSession:
        def __init__(self):
            self.calls = []

        def post(self, url, data, headers):
            self.calls.append({"url": url, "data": data, "headers": headers})
            return FakeResponse()

    class FakeClient:
        base_url = "https://www.runninghub.cn"

        def __init__(self):
            self.session = FakeSession()

        async def _get_session(self):
            return self.session

    client = FakeClient()

    uploaded = await _upload_runninghub_ai_app_media(client, str(media_path), "rk-test")

    assert uploaded == "https://cdn.runninghub.cn/openapi/portrait.png"
    assert client.session.calls[0]["url"] == (
        "https://www.runninghub.cn/openapi/v2/media/upload/binary"
    )
    assert client.session.calls[0]["headers"] == {"Authorization": "Bearer rk-test"}


@pytest.mark.asyncio
async def test_upload_ai_app_media_falls_back_to_file_name(tmp_path):
    media_path = tmp_path / "voice.mp3"
    media_path.write_bytes(b"audio")

    class FakeResponse:
        status = 200

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def json(self):
            return {
                "code": 0,
                "message": "success",
                "data": {"fileName": "openapi/voice.mp3"},
            }

        async def text(self):
            return '{"code":0}'

    class FakeSession:
        def post(self, url, data, headers):
            return FakeResponse()

    class FakeClient:
        base_url = "https://www.runninghub.cn"

        async def _get_session(self):
            return FakeSession()

    uploaded = await _upload_runninghub_ai_app_media(FakeClient(), str(media_path), "rk-test")

    assert uploaded == "openapi/voice.mp3"


@pytest.mark.asyncio
async def test_make_ai_app_run_request_reuses_runninghub_client_session():
    class FakeResponse:
        status = 200

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def json(self):
            return {"code": 0, "data": {"taskId": "task-1"}}

        async def text(self):
            return '{"code":0}'

    class FakeSession:
        def __init__(self):
            self.calls = []

        def post(self, url, json, headers):
            self.calls.append({"url": url, "json": json, "headers": headers})
            return FakeResponse()

    class FakeClient:
        base_url = "https://www.runninghub.cn"

        def __init__(self):
            self.session = FakeSession()

        async def _get_session(self):
            return self.session

    client = FakeClient()
    payload = {"nodeInfoList": [], "instanceType": "default", "usePersonalQueue": "false"}

    result = await _make_runninghub_ai_app_run_request(
        client,
        "/openapi/v2/run/ai-app/2030929648594460673",
        payload,
        "rk-test",
    )

    assert result == {"code": 0, "data": {"taskId": "task-1"}}
    assert client.session.calls == [
        {
            "url": "https://www.runninghub.cn/openapi/v2/run/ai-app/2030929648594460673",
            "json": payload,
            "headers": {
                "Authorization": "Bearer rk-test",
                "Content-Type": "application/json",
            },
        }
    ]


@pytest.mark.asyncio
async def test_make_ai_app_run_request_allows_top_level_task_id():
    class FakeResponse:
        status = 200

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def json(self):
            return {"taskId": "task-top", "status": "RUNNING", "errorCode": ""}

        async def text(self):
            return '{"taskId":"task-top"}'

    class FakeSession:
        def post(self, url, json, headers):
            return FakeResponse()

    class FakeClient:
        base_url = "https://www.runninghub.cn"

        async def _get_session(self):
            return FakeSession()

    result = await _make_runninghub_ai_app_run_request(
        FakeClient(),
        "/openapi/v2/run/ai-app/2030929648594460673",
        {"nodeInfoList": [], "instanceType": "default", "usePersonalQueue": "false"},
        "rk-test",
    )

    assert result["taskId"] == "task-top"


@pytest.mark.asyncio
async def test_make_ai_app_run_request_retries_legacy_api_key_body_on_401():
    class FakeResponse:
        def __init__(self, status, body):
            self.status = status
            self._body = body

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def json(self):
            return self._body

        async def text(self):
            return str(self._body)

    class FakeSession:
        def __init__(self):
            self.calls = []

        def post(self, url, json, headers):
            self.calls.append({"url": url, "json": json, "headers": headers})
            if len(self.calls) == 1:
                return FakeResponse(401, {"msg": "unauthorized"})
            return FakeResponse(200, {"code": 0, "data": {"taskId": "task-1"}})

    class FakeClient:
        base_url = "https://www.runninghub.cn"

        def __init__(self):
            self.session = FakeSession()

        async def _get_session(self):
            return self.session

    client = FakeClient()
    payload = {"nodeInfoList": [], "instanceType": "default", "usePersonalQueue": "false"}

    result = await _make_runninghub_ai_app_run_request(
        client,
        "/openapi/v2/run/ai-app/2030929648594460673",
        payload,
        "rk-test",
    )

    assert result == {"code": 0, "data": {"taskId": "task-1"}}
    assert "apiKey" not in client.session.calls[0]["json"]
    assert client.session.calls[0]["headers"]["Authorization"] == "Bearer rk-test"
    assert client.session.calls[1]["json"]["apiKey"] == "rk-test"
    assert client.session.calls[1]["headers"] == {"Content-Type": "application/json"}


@pytest.mark.asyncio
async def test_make_ai_app_run_request_raises_runninghub_error_code():
    class FakeResponse:
        status = 200

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def json(self):
            return {"errorCode": "1101", "errorMessage": "Node info error"}

        async def text(self):
            return '{"errorCode":"1101","errorMessage":"Node info error"}'

    class FakeSession:
        def post(self, url, json, headers):
            return FakeResponse()

    class FakeClient:
        base_url = "https://www.runninghub.cn"

        async def _get_session(self):
            return FakeSession()

    with pytest.raises(RuntimeError, match="1101.*Node info error"):
        await _make_runninghub_ai_app_run_request(
            FakeClient(),
            "/openapi/v2/run/ai-app/2030929648594460673",
            {"nodeInfoList": []},
            "rk-test",
        )


@pytest.mark.asyncio
async def test_wait_for_runninghub_task_times_out_by_default(monkeypatch):
    class FakeClient:
        async def query_task_status(self, task_id):
            return {"status": "RUNNING"}

    monkeypatch.setattr(
        "pixelle_video.services.digital_human_service.RUNNINGHUB_AI_APP_DEFAULT_TIMEOUT",
        0.01,
    )
    monkeypatch.setattr(
        "pixelle_video.services.digital_human_service.RUNNINGHUB_AI_APP_POLL_INTERVAL",
        0.001,
    )

    result = await _wait_for_runninghub_task(FakeClient(), "task-1")

    assert result.status == "error"
    assert "timeout" in result.msg


@pytest.mark.asyncio
async def test_query_ai_app_task_uses_openapi_v2_query():
    class FakeResponse:
        status = 200

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def json(self):
            return {
                "taskId": "task-1",
                "status": "SUCCESS",
                "results": [{"url": "https://cdn.example.com/out.mp4", "outputType": "mp4"}],
            }

        async def text(self):
            return '{"status":"SUCCESS"}'

    class FakeSession:
        def __init__(self):
            self.calls = []

        def post(self, url, json, headers):
            self.calls.append({"url": url, "json": json, "headers": headers})
            return FakeResponse()

    class FakeClient:
        base_url = "https://www.runninghub.cn"

        def __init__(self):
            self.session = FakeSession()

        async def _get_session(self):
            return self.session

    client = FakeClient()

    result = await _query_runninghub_ai_app_task(client, "task-1", "rk-test")

    assert result["status"] == "SUCCESS"
    assert client.session.calls == [
        {
            "url": "https://www.runninghub.cn/openapi/v2/query",
            "json": {"taskId": "task-1"},
            "headers": {
                "Authorization": "Bearer rk-test",
                "Content-Type": "application/json",
            },
        }
    ]


def test_ai_app_outputs_to_result_extracts_video_url_from_results():
    result = _runninghub_ai_app_outputs_to_result(
        "task-1",
        {
            "results": [
                {"url": "https://cdn.example.com/cover.png", "outputType": "png"},
                {"url": "https://cdn.example.com/video.mp4", "outputType": "mp4"},
            ]
        },
    )

    assert result.status == "completed"
    assert result.videos == ["https://cdn.example.com/video.mp4"]
    assert result.files == [
        "https://cdn.example.com/cover.png",
        "https://cdn.example.com/video.mp4",
    ]


def test_build_workflow_params_defaults_to_legacy_videoimage_mapping():
    params = _build_workflow_params(
        {},
        portrait_path="/tmp/person.png",
        audio_path="/tmp/voice.mp3",
    )

    assert params == {
        "videoimage": "/tmp/person.png",
        "audio": "/tmp/voice.mp3",
    }


def test_list_workflows_only_includes_direct_talking_workflows(tmp_path, monkeypatch):
    workflows_dir = tmp_path / "workflows" / "runninghub"
    workflows_dir.mkdir(parents=True)
    (workflows_dir / "digital_image.json").write_text(
        '{"source": "runninghub", "workflow_id": "image-only"}',
        encoding="utf-8",
    )
    (workflows_dir / "digital_combination.json").write_text(
        '{"source": "runninghub", "workflow_id": "legacy-talking"}',
        encoding="utf-8",
    )
    (workflows_dir / "digital_talk_image_prompt.json").write_text(
        '{"source": "runninghub", "workflow_id": "new-talking", "ip_broadcast": {"params": {"audio": "audio", "portrait": "image"}}}',
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)

    keys = [wf["key"] for wf in list_digital_human_workflows()]

    assert "workflows/runninghub/digital_combination.json" in keys
    assert "workflows/runninghub/digital_talk_image_prompt.json" in keys
    assert "workflows/runninghub/digital_image.json" not in keys
