import pytest

from pixelle_video.services.subtitle_service import _build_subtitles_filter
from pixelle_video.services.video import VideoService
from web.ip_broadcast import state
from web.ip_broadcast.modules import m5_composer, m5_postproduction
from web.ip_broadcast.modules.m5_postproduction import (
    _build_bgm_mix_command,
    _visible_overlay_groups,
    estimate_overlay_timeline,
)


def test_bgm_mix_command_uses_voice_audio_as_duration_source():
    cmd = _build_bgm_mix_command(
        merged_video="/tmp/merged.mp4",
        bgm_path="/tmp/long-bgm.mp3",
        output_path="/tmp/out.mp4",
        bgm_volume=0.3,
        voice_volume=1.0,
    )

    filter_index = cmd.index("-filter_complex") + 1

    assert "[voice][bgm]amix=inputs=2:duration=first[aout]" in cmd[filter_index]
    assert "-shortest" in cmd


def test_subtitle_filter_accepts_template_force_style():
    filter_value = _build_subtitles_filter("/tmp/test.srt", "Fontsize=48,Alignment=2")

    assert filter_value.startswith("subtitles=")
    assert ":force_style='Fontsize=48,Alignment=2'" in filter_value


def test_estimate_overlay_timeline_uses_segment_character_ratio():
    session = {}
    state.init_ip_broadcast_state(session)
    state.set_final_script("一一\n二二二二\n三三", session=session)
    state.merge_story_segments(["segment_2", "segment_3"], session=session)
    group = next(
        item for item in session["ipb_visual_groups"]
        if item["segment_ids"] == ["segment_2", "segment_3"]
    )
    group["overlay_type"] = "uploaded_video"
    group["overlay_mode"] = "fullscreen"

    timeline = estimate_overlay_timeline(
        session["ipb_story_segments"],
        session["ipb_visual_groups"],
        audio_duration=80.0,
    )

    assert timeline == [
        {
            "group_id": group["group_id"],
            "start_time": 20.0,
            "end_time": 80.0,
            "duration": 60.0,
            "overlay_type": "uploaded_video",
            "overlay_mode": "fullscreen",
        }
    ]


def test_visible_overlay_groups_excludes_default_segment_groups():
    session = {}
    state.init_ip_broadcast_state(session)
    state.set_final_script("一\n二\n三", session=session)
    state.create_overlay_group(["segment_2"], session=session)

    visible = _visible_overlay_groups(session["ipb_visual_groups"])

    assert [group["segment_ids"] for group in visible] == [["segment_2"]]


def test_clear_overlay_segment_picker_uses_nonce_instead_of_mutating_widget_keys(monkeypatch):
    session = {"ipb_overlay_picker_nonce": 3}
    monkeypatch.setattr(m5_postproduction.st, "session_state", session)

    m5_postproduction._clear_overlay_segment_picker([{"segment_id": "segment_1"}])

    assert session["ipb_overlay_picker_nonce"] == 4
    assert "ipb_overlay_pick_3_segment_1" not in session


def test_apply_video_asset_to_overlay_group_sets_asset_and_legacy_path(tmp_path):
    video = tmp_path / "asset.mp4"
    video.write_bytes(b"video")
    group = {}

    m5_postproduction._apply_video_asset_to_group(
        group,
        asset_id="asset-1",
        asset_path=str(video),
    )

    assert group["video_asset_id"] == "asset-1"
    assert group["uploaded_video_path"] == str(video)


def test_video_asset_cover_html_uses_fixed_height(tmp_path):
    cover = tmp_path / "cover.jpg"
    cover.write_bytes(b"cover")

    html = m5_postproduction._build_video_asset_cover_html(str(cover), height=120)

    assert "height:120px" in html
    assert "object-fit:cover" in html
    assert "data:image/jpeg;base64" in html


def test_overlay_video_segment_command_preserves_base_audio_and_limits_time_range():
    cmd = VideoService._build_overlay_video_segment_command(
        base_video="/tmp/base.mp4",
        overlay_video="/tmp/overlay.mp4",
        output_path="/tmp/out.mp4",
        start_time=2.5,
        end_time=5.0,
        mode="pip",
        base_width=1080,
        base_height=1920,
    )

    filter_index = cmd.index("-filter_complex") + 1

    assert cmd[:6] == ["ffmpeg", "-y", "-i", "/tmp/base.mp4", "-stream_loop", "-1"]
    assert "-map" in cmd
    assert "0:a?" in cmd
    assert "enable='between(t,2.5,5)'" in cmd[filter_index]
    assert "scale=388:-2" in cmd[filter_index]
    assert "overlay=main_w-overlay_w-48:80" in cmd[filter_index]


@pytest.mark.asyncio
async def test_run_m5_failure_writes_error_notice_and_preserves_digital_human(
    monkeypatch,
    tmp_path,
):
    session = {}
    state.init_ip_broadcast_state(session)
    audio_path = tmp_path / "voice.mp3"
    dh_path = tmp_path / "dh.mp4"
    audio_path.write_bytes(b"audio")
    dh_path.write_bytes(b"video")
    session.update(
        {
            "ipb_m3_audio_path": str(audio_path),
            "ipb_m4_dh_video_path": str(dh_path),
        }
    )
    notices = []

    monkeypatch.setattr(m5_postproduction.st, "session_state", session)
    monkeypatch.setattr(m5_composer, "set_step_notice", lambda *args: notices.append(args))
    monkeypatch.setattr(
        m5_composer,
        "merge_audio_into_video",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("compose failed")),
    )

    ok = await m5_postproduction.run_m5(object())

    assert ok is False
    assert session["ipb_step_status"][5] == "error"
    assert session["ipb_m4_dh_video_path"] == str(dh_path)
    assert notices[-1] == (5, "error", "compose failed")
