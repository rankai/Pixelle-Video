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


def test_mark_voice_generated_advances_progress_to_step_three(tmp_path):
    session = _base_session()
    audio_path = tmp_path / "voice.mp3"
    audio_path.write_text("audio")
    state.set_source_text("final copy", "视频链接", session=session)

    state.mark_voice_generated(str(audio_path), session=session)

    assert session["ipb_m3_audio_path"] == str(audio_path)
    assert session["ipb_step_status"][3] == "done"
    assert session["ipb_active_step"] == 4
    assert state.get_completed_step_count(session=session) == 3


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


def test_init_state_uses_six_user_visible_steps():
    session = _base_session()

    assert sorted(session["ipb_step_status"]) == [1, 2, 3, 4, 5, 6]


def test_get_next_action_skips_social_meta_after_final_video_exists(tmp_path):
    session = _base_session()
    state.set_final_script("final copy", session=session)
    audio_path = tmp_path / "voice.mp3"
    dh_path = tmp_path / "dh.mp4"
    final_path = tmp_path / "final.mp4"
    for path in (audio_path, dh_path, final_path):
        path.write_text("ok")
    session["ipb_m3_audio_path"] = str(audio_path)
    session["ipb_m4_portrait_id"] = "portrait-1"
    session["ipb_m4_dh_video_path"] = str(dh_path)
    session["ipb_m5_final_video_path"] = str(final_path)
    session["ipb_m6_title"] = "标题"
    session["ipb_m6_description"] = "描述"

    action = state.get_next_action(session=session)

    assert action.key == "publish"
    assert action.step == 6


def test_split_script_to_segments_uses_entered_paragraphs():
    assert state.split_script_to_segments("开场\n\n案例一\n案例二") == [
        "开场",
        "案例一",
        "案例二",
    ]


def test_sync_story_segments_from_script_creates_default_visual_groups():
    session = _base_session()

    state.sync_story_segments_from_script("第一段\n第二段", session=session)

    assert [item["text"] for item in session["ipb_story_segments"]] == ["第一段", "第二段"]
    assert [item["visual_group_id"] for item in session["ipb_story_segments"]] == [
        "group_1",
        "group_2",
    ]
    assert session["ipb_visual_groups"][0]["segment_ids"] == ["segment_1"]
    assert session["ipb_visual_groups"][0]["visual_type"] == "digital_human"


def test_merge_story_segments_requires_contiguous_ranges():
    session = _base_session()
    state.sync_story_segments_from_script("一\n二\n三\n四", session=session)

    state.merge_story_segments(["segment_2", "segment_3"], session=session)

    merged_groups = [
        group for group in session["ipb_visual_groups"]
        if group["segment_ids"] == ["segment_2", "segment_3"]
    ]
    assert len(merged_groups) == 1
    assert session["ipb_story_segments"][1]["visual_group_id"] == merged_groups[0]["group_id"]
    assert session["ipb_story_segments"][2]["visual_group_id"] == merged_groups[0]["group_id"]
