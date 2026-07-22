from pathlib import Path


def test_api_ui_scale_probe_is_local_and_covers_entry_target():
    source = Path("scripts/program_rollout_scale_api_ui_smoke.py").read_text(encoding="utf-8")
    assert "temporary_sqlite_api_ui_only" in source
    assert "PROJECT_COUNT = 100" in source
    assert "ARTIFACT_COUNT = 1000" in source
    assert "ui_project_option_counts" in source
    assert "ui_artifact_option_counts" in source
    assert '"browser_actions": 0' in source
    assert '"local_ui_browser_actions": 20' in source
    assert '"external_actions": 0' in source
    assert '"final_publish_clicks": 0' in source


def test_api_ui_scale_probe_uses_isolated_databases_and_no_provider_actions():
    source = Path("scripts/program_rollout_scale_api_ui_smoke.py").read_text(encoding="utf-8")
    assert '"PIXELLE_APP_CENTER_DB"' in source
    assert '"PIXELLE_DESKTOP_TASKS_DB"' in source
    assert '"PIXELLE_PUBLISHING_DB"' in source
    assert '"PIXELLE_PUBLISH_V2_ENABLED": "false"' in source
    assert "final_publish_clicks" in source
