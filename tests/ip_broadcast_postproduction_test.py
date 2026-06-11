import pytest

from pixelle_video.services import subtitle_service
from pixelle_video.services.ip_broadcast_composer import _validate_visual_overlay_assets
from pixelle_video.services.subtitle_service import _build_subtitles_filter
from pixelle_video.services.video import VideoService
from web.ip_broadcast import state
from web.ip_broadcast.modules import m5_composer, m5_postproduction, m5_publish_assets
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


def test_subtitle_generation_splits_long_chinese_sentence(monkeypatch, tmp_path):
    monkeypatch.setattr(subtitle_service, "_probe_duration", lambda _path: 12.0)
    srt_path = tmp_path / "long.srt"

    subtitle_service.generate_srt(
        "你真的会用滚筒洗衣机吗？99%的人不知道，4个隐藏常识。",
        "/tmp/audio.mp3",
        str(srt_path),
    )

    subtitle_lines = [
        line
        for line in srt_path.read_text(encoding="utf-8").splitlines()
        if line and not line.isdigit() and "-->" not in line
    ]
    assert len(subtitle_lines) > 2
    assert all(len(line) <= 16 for line in subtitle_lines)


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


def test_validate_visual_overlay_assets_rejects_missing_uploaded_video():
    visual_groups = [
        {
            "group_id": "group_1",
            "segment_ids": ["segment_1"],
            "visual_type": "uploaded_video",
            "uploaded_video_path": "",
        }
    ]

    with pytest.raises(ValueError, match="group_1"):
        _validate_visual_overlay_assets(visual_groups)


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


class AttrDict(dict):
    def __getattr__(self, key):
        try:
            return self[key]
        except KeyError as e:
            raise AttributeError(key) from e

    def __setattr__(self, key, value):
        self[key] = value


def test_publish_asset_settings_uses_shadow_widget_keys(monkeypatch):
    session = AttrDict()
    state.init_ip_broadcast_state(session)
    seen_keys = []

    def fake_text_input(_label, **kwargs):
        seen_keys.append(kwargs["key"])
        return kwargs.get("value", "")

    def fake_text_area(_label, **kwargs):
        seen_keys.append(kwargs["key"])
        return kwargs.get("value", "")

    monkeypatch.setattr(m5_publish_assets.st, "session_state", session)
    monkeypatch.setattr(m5_publish_assets.st, "text_input", fake_text_input)
    monkeypatch.setattr(m5_publish_assets.st, "text_area", fake_text_area)
    monkeypatch.setattr(m5_publish_assets.st, "radio", lambda *args, **kwargs: "first_frame")

    m5_publish_assets.render_publish_asset_settings()

    assert "ipb_m6_title" not in seen_keys
    assert "ipb_m6_description" not in seen_keys
    assert "_ipb_m6_title_input" in seen_keys
    assert "_ipb_m6_description_input" in seen_keys


def test_run_postproduction_error_uses_single_step_notice(monkeypatch):
    session = AttrDict()
    state.init_ip_broadcast_state(session)
    notices = []
    errors = []

    class FakeProgress:
        def progress(self, *_args, **_kwargs):
            pass

        def empty(self):
            pass

    class FakeLoading:
        def empty(self):
            pass

    monkeypatch.setattr(m5_composer.st, "session_state", session)
    monkeypatch.setattr(m5_composer.st, "progress", lambda *_args, **_kwargs: FakeProgress())
    monkeypatch.setattr(m5_composer.st, "error", lambda message: errors.append(message))
    monkeypatch.setattr(m5_composer, "show_global_loading", lambda _message: FakeLoading())
    monkeypatch.setattr(m5_composer, "set_step_notice", lambda *args: notices.append(args))
    monkeypatch.setattr(m5_composer, "_prepare_audio", lambda _uid: (_ for _ in ()).throw(RuntimeError("compose failed")))

    m5_composer.run_postproduction(object())

    assert errors == []
    assert notices == [(5, "error", "compose failed")]


@pytest.mark.asyncio
async def test_publish_cover_uses_subtitle_free_source_video(monkeypatch, tmp_path):
    session = AttrDict()
    state.init_ip_broadcast_state(session)
    final_video = tmp_path / "final_with_subtitles.mp4"
    cover_source = tmp_path / "merged_without_subtitles.mp4"
    final_video.write_bytes(b"final")
    cover_source.write_bytes(b"source")
    session.update(
        {
            "ipb_m2_output": "",
            "ipb_m6_title": "标题",
            "ipb_m6_description": "描述",
            "ipb_m6_cover_mode": "first_frame",
        }
    )
    extracted_from = []

    monkeypatch.setattr(m5_publish_assets.st, "session_state", session)
    monkeypatch.setattr(
        m5_publish_assets,
        "extract_first_frame",
        lambda video_path, output_path: extracted_from.append(video_path) or output_path,
    )

    async def fake_render_cover(**kwargs):
        return kwargs["output_path"]

    monkeypatch.setattr(m5_publish_assets, "render_ip_broadcast_cover", fake_render_cover)
    monkeypatch.setattr(
        m5_publish_assets,
        "get_temp_path",
        lambda name: str(tmp_path / name),
    )

    await m5_publish_assets.ensure_publish_assets_async(
        object(),
        str(final_video),
        cover_source_path=str(cover_source),
    )

    assert extracted_from == [str(cover_source)]


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
