import json
from pathlib import Path


def test_tts_index_custom_uses_runninghub_workflow_wrapper():
    workflow = json.loads(Path("workflows/runninghub/tts_index_custom.json").read_text())

    assert workflow == {
        "source": "runninghub",
        "workflow_id": "1961317560035819522",
    }
