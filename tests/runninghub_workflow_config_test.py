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
