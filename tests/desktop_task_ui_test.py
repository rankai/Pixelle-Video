from pathlib import Path

SOURCE = Path("desktop/src/StudioApp.tsx").read_text()


def test_task_step_mapping_matches_six_step_workflow():
    assert "voice: 3" in SOURCE
    assert "digital_human: 4" in SOURCE
    assert "postproduction: 5" in SOURCE
    assert "publish: 6" in SOURCE


def test_failed_task_action_does_not_claim_true_retry():
    assert ">重试<" not in SOURCE
    assert ">创建重试记录<" in SOURCE


def test_completed_postproduction_task_can_download_final_video():
    assert "taskFinalVideoArtifact" in SOURCE
    assert "下载成片" in SOURCE


def test_ip_workflow_recovers_active_step_and_running_task_after_refresh():
    assert "pixelle_ipb_task_id" in SOURCE
    assert "restoreCurrentTask" in SOURCE
    assert "uiStepForApiStep(restored.current_step)" in SOURCE
    assert "window.localStorage.setItem(IPB_TASK_STORAGE_KEY, result.task_id)" in SOURCE


def test_digital_human_workflow_options_explain_input_and_output():
    assert "上传老板照片生成自然口播视频" in SOURCE
    assert "只替换口型和声音，保留原视频动作" in SOURCE
    assert "workflowConfig.description" in SOURCE


def test_cloud_tts_copy_does_not_imply_clone_workflow_supports_speed():
    assert '<option value="comfyui">云端声音生成</option>' in SOURCE
    assert "老板声音克隆会使用参考音频复刻音色，但当前工作流不支持语速调节" in SOURCE
    assert "选择声音来源、音色和语速" not in SOURCE


def test_postproduction_exposes_subtitle_style_controls():
    assert "字幕字号" in SOURCE
    assert "字幕底部距离" in SOURCE
    assert "subtitle_style" in SOURCE
    assert "patchSubtitleStyle" in SOURCE
