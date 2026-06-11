from pathlib import Path


SOURCE = Path("desktop/src/App.tsx").read_text()


def test_task_step_mapping_matches_six_step_workflow():
    assert "voice: 3" in SOURCE
    assert "digital_human: 4" in SOURCE
    assert "postproduction: 5" in SOURCE
    assert "publish: 6" in SOURCE


def test_failed_task_action_does_not_claim_true_retry():
    assert ">重试<" not in SOURCE
    assert ">创建重试记录<" in SOURCE
