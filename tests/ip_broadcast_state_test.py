from pathlib import Path

from web.ip_broadcast import state


def _base_session():
    session = {}
    state.init_ip_broadcast_state(session)
    return session


def test_set_source_text_seeds_final_script_and_legacy_output():
    session = _base_session()
    state.set_final_script("old final", session=session)

    state.set_source_text("new source", "视频链接", session=session)

    assert session["ipb_source_text"] == "new source"
    assert session["ipb_source_label"] == "视频链接"
    assert session["ipb_final_script"] == "new source"
    assert session["ipb_m2_output"] == "new source"
    assert session["ipb_step_status"][2] == "done"


def test_set_final_script_keeps_legacy_output_in_sync():
    session = _base_session()

    state.set_final_script("final copy", session=session)

    assert session["ipb_final_script"] == "final copy"
    assert session["ipb_m2_output"] == "final copy"
    assert session["ipb_step_status"][2] == "done"
    assert session["ipb_step_status"][3] == "ready"


def test_get_next_action_reports_missing_portrait_before_video_generation(tmp_path):
    session = _base_session()
    audio_path = tmp_path / "voice.mp3"
    audio_path.write_text("audio")
    state.set_final_script("final copy", session=session)
    session["ipb_m3_audio_path"] = str(audio_path)

    action = state.get_next_action(session=session)

    assert action.key == "select_portrait"
    assert action.step == 4


def test_get_next_action_advances_to_postproduction_when_assets_exist(tmp_path):
    session = _base_session()
    final_script = "final copy"
    state.set_final_script(final_script, session=session)
    audio_path = tmp_path / "voice.mp3"
    video_path = tmp_path / "dh.mp4"
    audio_path.write_text("audio")
    video_path.write_text("video")
    session["ipb_m3_audio_path"] = str(audio_path)
    session["ipb_m4_portrait_id"] = "portrait-1"
    session["ipb_m4_dh_video_path"] = str(video_path)

    action = state.get_next_action(session=session)

    assert Path(session["ipb_m4_dh_video_path"]).exists()
    assert action.key == "postproduce"
    assert action.step == 5


def test_init_state_includes_digital_human_workflow_controls():
    session = _base_session()

    assert session["ipb_m4_workflow"] == "workflows/runninghub/digital_combination.json"
    assert session["ipb_m4_prompt"] == "自然口播，正面镜头，表情稳定，唇形同步"
    assert session["ipb_m4_duration"] == 0.0


def test_init_state_includes_ip_learning_fields():
    session = _base_session()

    assert session["ipb_ip_profile_url"] == ""
    assert session["ipb_ip_manual_video_links"] == ""
    assert session["ipb_ip_video_urls"] == []
    assert session["ipb_ip_learning_scripts"] == []
    assert session["ipb_ip_learning_errors"] == []
    assert session["ipb_ip_learning_topics"] == []
    assert session["ipb_ip_selected_topic"] == ""
    assert session["ipb_ip_topic_script"] == ""
