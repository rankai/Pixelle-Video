from pathlib import Path

from scripts.program_rollout_scale_smoke import (
    ARTIFACT_COUNT,
    ARTIFACTS_PER_PROJECT,
    PROJECT_COUNT,
    run_scale_check,
)


def test_scale_smoke_is_local_and_bounded():
    source = Path("scripts/program_rollout_scale_smoke.py").read_text(encoding="utf-8")
    assert "temporary_sqlite_only" in source
    assert '"api_started": False' in source
    assert '"browser_actions": 0' in source
    assert '"external_actions": 0' in source
    assert PROJECT_COUNT == 100
    assert ARTIFACT_COUNT == 1000
    assert ARTIFACTS_PER_PROJECT == 10


def test_scale_smoke_reads_back_100_projects_and_1000_artifacts(tmp_path):
    result = run_scale_check(tmp_path / "scale.sqlite")
    assert result["status"] == "passed_local_bounded"
    assert result["projects_read"] == PROJECT_COUNT
    assert result["artifacts_read"] == ARTIFACT_COUNT
    assert result["artifacts_per_project"] == [ARTIFACTS_PER_PROJECT] * PROJECT_COUNT
