from types import SimpleNamespace

import pytest

from pixelle_video.services.digital_human_service import (
    _build_ai_app_node_info_list,
    _build_ai_app_run_request,
    _build_workflow_params,
    _extract_video_output,
    _load_workflow_config,
    _resolve_workflow_input,
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

    assert endpoint == "/run/ai-app/2030929648594460673"
    assert payload == {
        "apiKey": "rk-test",
        "nodeInfoList": [{"nodeId": "48", "fieldName": "audio", "fieldValue": "voice.mp3"}],
    }
    assert "webappId" not in payload


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
