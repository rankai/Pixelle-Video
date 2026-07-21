from pathlib import Path


def test_user_simulation_uses_existing_window_and_one_hour_policy():
    source = Path("scripts/program_rollout_user_simulation.py").read_text(encoding="utf-8")
    assert "OBSERVATION_QA" in source
    assert "REQUIRED_WINDOW_HOURS = 1" in source
    assert "window_started_at" in source
    assert "stable_observation_window_complete" in source
    assert "product_owner_signoff" in source


def test_user_simulation_is_local_noop_and_requires_twenty_readbacks():
    source = Path("scripts/program_rollout_user_simulation.py").read_text(encoding="utf-8")
    assert "MINIMUM_BOUNDED_RUNS = 20" in source
    assert "run_scale_api_ui_check" in source
    assert "program_rollout_observation_probe.py" in source
    assert '"local_noop_only": True' in source
    assert '"final_publish_clicks"' in source
