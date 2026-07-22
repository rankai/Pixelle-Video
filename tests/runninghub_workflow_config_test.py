import json
from pathlib import Path

from pixelle_video.services.tts_service import TTSService


def test_tts_index_custom_uses_runninghub_workflow_wrapper():
    workflow = json.loads(Path("workflows/runninghub/tts_index_custom.json").read_text())

    assert workflow["source"] == "runninghub"
    assert workflow["workflow_id"] == "1961317560035819522"
    mappings = workflow["runninghub_node_mappings"]
    assert mappings["text"] == {
        "node_id": "7",
        "field_name": "text",
        "description": "text",
    }
    assert mappings["ref_audio"] == {
        "node_id": "4",
        "field_name": "audio",
        "description": "ref_audio",
        "upload": True,
    }
    assert mappings["temperature"] == {
        "node_id": "6",
        "field_name": "temperature",
        "description": "temperature",
    }
    assert "mode" not in mappings
    assert "do_sample_mode" not in mappings
    assert "max_tokens_per_sentence" not in mappings


def test_tts_edge_declares_supported_runninghub_node_mapping():
    workflow = json.loads(Path("workflows/runninghub/tts_edge.json").read_text())

    assert workflow["source"] == "runninghub"
    assert workflow["workflow_id"] == "1983513964837543938"
    mappings = workflow["runninghub_node_mappings"]
    assert mappings["text"] == {
        "node_id": "3",
        "field_name": "value",
        "description": "text",
    }
    assert mappings["voice"] == {
        "node_id": "1",
        "field_name": "voice",
        "description": "voice",
    }
    assert mappings["speed"] == {
        "node_id": "8",
        "field_name": "value",
        "description": "speed",
    }
    assert mappings["pitch"] == {
        "node_id": "1",
        "field_name": "pitch",
        "description": "pitch",
    }


def test_tts_spark_declares_supported_runninghub_node_mapping():
    workflow = json.loads(Path("workflows/runninghub/tts_spark.json").read_text())

    assert workflow["source"] == "runninghub"
    assert workflow["workflow_id"] == "1983921902282539009"
    mappings = workflow["runninghub_node_mappings"]
    for param_name in [
        "text",
        "gender",
        "pitch",
        "speed",
        "temperature",
        "top_k",
        "top_p",
        "max_new_tokens",
        "do_sample",
        "seed",
    ]:
        assert mappings[param_name] == {
            "node_id": "6" if param_name != "text" else "7",
            "field_name": "value" if param_name == "text" else param_name,
            "description": param_name,
        }


async def test_tts_runninghub_mapping_builds_node_info_and_uploads_reference_audio():
    class FakeClient:
        async def upload_file(self, path):
            assert path == "/tmp/ref.wav"
            return "uploaded-ref.wav"

    service = TTSService({"comfyui": {"tts": {}}})

    node_info = await service._build_runninghub_node_info_list(
        client=FakeClient(),
        workflow_params={
            "text": "完整口播文案",
            "ref_audio": "/tmp/ref.wav",
            "mode": "Auto",
            "temperature": 0.7,
            "ignored": "value",
        },
        node_mappings={
            "text": {"node_id": "7", "field_name": "text", "description": "text"},
            "ref_audio": {
                "node_id": "4",
                "field_name": "audio",
                "description": "ref_audio",
                "upload": True,
            },
            "temperature": {
                "node_id": "6",
                "field_name": "temperature",
                "description": "temperature",
            },
        },
    )

    assert node_info == [
        {
            "nodeId": "7",
            "fieldName": "text",
            "fieldValue": "完整口播文案",
            "description": "text",
        },
        {
            "nodeId": "4",
            "fieldName": "audio",
            "fieldValue": "uploaded-ref.wav",
            "description": "ref_audio",
        },
        {
            "nodeId": "6",
            "fieldName": "temperature",
            "fieldValue": 0.7,
            "description": "temperature",
        },
    ]


def test_runninghub_tts_failure_message_uses_failed_reason_not_success_msg():
    service = TTSService({"comfyui": {"tts": {}}})

    message = service._format_runninghub_tts_failure(
        "task-1",
        {"status": "FAILED", "msg": "success"},
        {
            "errorMessage": "工作流运行失败",
            "failedReason": {
                "node_name": "IndexTTSNode",
                "node_id": "6",
                "exception_message": "Value 1815 bigger than max of 1500",
            },
        },
    )

    assert message == (
        "RunningHub TTS task task-1 failed: 工作流运行失败；"
        "IndexTTSNode(node 6): Value 1815 bigger than max of 1500"
    )


def test_ip_broadcast_ai_app_workflow_declares_webapp_and_node_mapping():
    workflow = json.loads(Path("workflows/runninghub/digital_talk_image_prompt.json").read_text())

    assert workflow["source"] == "runninghub"
    assert workflow["type"] == "ai_app"
    assert workflow["webapp_id"] == "2030929648594460673"
    params = workflow["ip_broadcast"]["params"]
    assert params["audio"] == {
        "node_id": "48",
        "field_name": "audio",
        "description": "audio",
    }
    assert params["portrait"] == {
        "node_id": "35",
        "field_name": "image",
        "description": "image",
    }
    assert params["duration"] == {
        "node_id": "115",
        "field_name": "value",
        "description": "时长S",
    }
    assert params["prompt"] == {
        "node_id": "105",
        "field_name": "text",
        "description": "prompt",
    }


def test_ip_broadcast_fast_ai_app_workflow_declares_size_node_mapping():
    workflow = json.loads(Path("workflows/runninghub/digital_talk_fast_720p.json").read_text())

    assert workflow["source"] == "runninghub"
    assert workflow["type"] == "ai_app"
    assert workflow["webapp_id"] == "2042467436926083074"
    params = workflow["ip_broadcast"]["params"]
    assert params["portrait"] == {
        "node_id": "269",
        "field_name": "image",
        "description": "image",
    }
    assert params["audio"] == {
        "node_id": "276",
        "field_name": "audio",
        "description": "audio",
    }
    assert params["width"] == {
        "node_id": "368",
        "field_name": "value",
        "description": "宽",
    }
    assert params["height"] == {
        "node_id": "382",
        "field_name": "value",
        "description": "高",
    }
    assert params["prompt"] == {
        "node_id": "391",
        "field_name": "value",
        "description": "value",
    }


def test_ip_broadcast_lip_sync_ai_app_workflow_declares_video_node_mapping():
    workflow = json.loads(Path("workflows/runninghub/digital_lip_sync_video.json").read_text())

    assert workflow["source"] == "runninghub"
    assert workflow["type"] == "ai_app"
    assert workflow["webapp_id"] == "2005957723193831426"
    ipb = workflow["ip_broadcast"]
    assert ipb["portrait_media_type"] == "video"
    assert ipb["defaults"] == {
        "audio_source_select": "1",
        "frame_load_cap": 0,
        "skip_first_frames": 10,
        "width": 480,
        "height": 832,
    }
    params = ipb["params"]
    assert {"order": None} | params["audio_source_select"] == {
        "node_id": "520",
        "field_name": "select",
        "description": "音频对口型路径",
        "order": 1,
    }
    assert {"order": None} | params["audio"] == {
        "node_id": "348",
        "field_name": "audio",
        "description": "上传自定义音频",
        "order": 2,
    }
    assert {"order": None} | params["portrait"] == {
        "node_id": "473",
        "field_name": "video",
        "description": "对口型视频+音频",
        "order": 3,
    }
    assert {"order": None} | params["frame_load_cap"] == {
        "node_id": "473",
        "field_name": "frame_load_cap",
        "description": "视频总帧率（0为原长度，25帧/s）",
        "order": 4,
    }
    assert {"order": None} | params["skip_first_frames"] == {
        "node_id": "473",
        "field_name": "skip_first_frames",
        "description": "跳过前n帧",
        "order": 5,
    }
    assert {"order": None} | params["width"] == {
        "node_id": "521",
        "field_name": "value",
        "description": "宽度",
        "order": 6,
    }
    assert {"order": None} | params["height"] == {
        "node_id": "522",
        "field_name": "value",
        "description": "高度",
        "order": 7,
    }
