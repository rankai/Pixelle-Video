from pathlib import Path

from api.tasks.persistence import TaskPersistence


def test_observation_probe_is_explicitly_incomplete_and_local_only():
    source = Path("scripts/program_rollout_observation_probe.py").read_text(encoding="utf-8")
    assert "pre_observation_complete" in source
    assert '"window_hours_elapsed": 0' in source
    assert '"required_window_hours": 1' in source
    assert '"product_owner_signoff": "pending"' in source
    assert '"browser_actions": 0' in source
    assert '"final_publish_clicks": 0' in source


def test_observation_probe_does_not_claim_stable_observation():
    source = Path("scripts/program_rollout_observation_probe.py").read_text(encoding="utf-8")
    assert '"stable_observation": "not_complete"' in source
    assert "PIXELLE_ROLLOUT_LOCAL_NOOP" in source
    assert "RUN_COUNT = 20" in source


def test_task_persistence_can_be_isolated_for_rollout_probes(tmp_path, monkeypatch):
    target = tmp_path / "isolated-tasks.sqlite"
    monkeypatch.setenv("PIXELLE_DESKTOP_TASKS_DB", str(target))
    assert TaskPersistence().db_path == target
