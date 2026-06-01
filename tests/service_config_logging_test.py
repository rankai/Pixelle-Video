from pixelle_video.service import _redact_sensitive_config


def test_redact_sensitive_config_hides_api_keys():
    config = {
        "comfyui_url": "http://127.0.0.1:8188",
        "api_key": "local-secret",
        "runninghub_api_key": "runninghub-secret",
        "runninghub_instance_type": "default",
    }

    redacted = _redact_sensitive_config(config)

    assert redacted == {
        "comfyui_url": "http://127.0.0.1:8188",
        "api_key": "***redacted***",
        "runninghub_api_key": "***redacted***",
        "runninghub_instance_type": "default",
    }
    assert config["api_key"] == "local-secret"
    assert config["runninghub_api_key"] == "runninghub-secret"
