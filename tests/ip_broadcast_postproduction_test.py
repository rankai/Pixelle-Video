from pixelle_video.services.subtitle_service import _build_subtitles_filter
from pixelle_video.services.video import VideoService
from web.ip_broadcast import state
from web.ip_broadcast.modules.m5_postproduction import (
    _build_bgm_mix_command,
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
