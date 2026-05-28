import json
from pathlib import Path


def test_tts_index_custom_uses_runninghub_workflow_wrapper():
    workflow = json.loads(Path("workflows/runninghub/tts_index_custom.json").read_text())

    assert workflow == {
        "source": "runninghub",
        "workflow_id": "1961317560035819522",
    }


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
