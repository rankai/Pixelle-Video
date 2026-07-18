import asyncio
import shutil
import subprocess
from pathlib import Path

import pytest
from PIL import Image

from pixelle_video.services import subtitle_service
from pixelle_video.services.assets_v2.repository import AssetLibraryRepository
from pixelle_video.services.ip_broadcast_composer import (
    compose_ip_broadcast_video,
    normalize_video_to_canvas,
)
from pixelle_video.services.ip_broadcast_templates import render_ip_broadcast_cover
from pixelle_video.services.ip_broadcast_workflow import (
    IpBroadcastSession,
    _run_postproduction,
)


def test_generate_ass_uses_template_canvas_and_escapes_ass_markup(monkeypatch, tmp_path):
    monkeypatch.setattr(subtitle_service, "_probe_duration", lambda _path: 4.0)
    ass_path = tmp_path / "captions.ass"

    subtitle_service.generate_ass(
        "第一句{重点}。\n第二句",
        "/tmp/audio.mp3",
        str(ass_path),
    )

    ass = ass_path.read_text(encoding="utf-8")
    assert "PlayResX: 1080" in ass
    assert "PlayResY: 1920" in ass
    assert "Style: Default,PingFang SC" in ass
    assert "第一句\\{重点\\}。" in ass
    assert "第二句" in ass


def test_normalize_video_to_canvas_emits_single_canonical_geometry(monkeypatch, tmp_path):
    seen: dict[str, object] = {}
    monkeypatch.setattr(
        "pixelle_video.services.ip_broadcast_composer.probe_video_dimensions",
        lambda _path: (624, 832),
    )

    def fake_run(cmd, **kwargs):
        seen["cmd"] = cmd
        seen["kwargs"] = kwargs

    monkeypatch.setattr(
        "pixelle_video.services.ip_broadcast_composer.subprocess.run",
        fake_run,
    )

    output = tmp_path / "canvas.mp4"
    assert normalize_video_to_canvas("input.mp4", str(output)) == str(output)
    cmd = seen["cmd"]
    filter_graph = cmd[cmd.index("-vf") + 1]
    assert "scale=1080:1920:force_original_aspect_ratio=increase:flags=lanczos" in filter_graph
    assert "crop=1080:1920:(in_w-1080)/2:(in_h-1920)/2,setsar=1" in filter_graph
    assert cmd[-1] == str(output)


def test_cover_only_metadata_changes_do_not_discard_final_video(tmp_path):
    final_video = tmp_path / "final.mp4"
    final_video.write_bytes(b"video")
    session = IpBroadcastSession(session_id="s1")
    session.update_config(
        {
            "final_video_path": str(final_video),
            "cover_path": str(tmp_path / "cover.png"),
            "title": "旧标题",
        }
    )
    session.state["cover_path"] = str(tmp_path / "cover.png")
    session.state["final_video_path"] = str(final_video)

    session.update_config({"title": "新标题"})

    assert session.state["final_video_path"] == str(final_video)
    assert session.state["cover_path"] == ""
    assert session.state["publish_package"] == {}


def test_packaged_cover_renderer_falls_back_when_playwright_browser_is_missing(
    monkeypatch, tmp_path
):
    async def unavailable(*_args, **_kwargs):
        raise RuntimeError("BrowserType.launch: Executable doesn't exist")

    monkeypatch.setattr(
        "pixelle_video.services.ip_broadcast_templates.HTMLFrameGenerator.generate_frame",
        unavailable,
    )
    output = tmp_path / "fallback-cover.png"

    result = asyncio.run(
        render_ip_broadcast_cover(
            "boss_clean",
            "企业视频资产真正可复用的方法",
            "字幕与封面使用同一画布坐标",
            output_path=str(output),
        )
    )

    assert result == str(output)
    assert output.is_file()
    assert Image.open(output).size == (1080, 1920)


def test_v2_asset_selection_reaches_successful_render_with_real_media(monkeypatch, tmp_path):
    """Exercise the Gate-B path with an actual V2 revision and ffmpeg output.

    The desktop picker stores ``video_asset_id`` rather than a filesystem path.
    This test proves the render boundary can resolve that ID and still produce
    a canonical 1080x1920 file with overlays and subtitles.
    """

    if shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None:
        pytest.skip("ffmpeg/ffprobe required for the real-media render contract")

    monkeypatch.setenv("PIXELLE_VIDEO_ROOT", str(tmp_path))
    base_video = tmp_path / "base.mp4"
    audio = tmp_path / "voice.mp3"
    subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            "color=c=0x243b53:s=320x568:r=25",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:sample_rate=16000",
            "-t",
            "1.2",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            str(base_video),
        ],
        check=True,
    )
    subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=660:sample_rate=16000",
            "-t",
            "1.2",
            "-c:a",
            "libmp3lame",
            str(audio),
        ],
        check=True,
    )

    repository = AssetLibraryRepository(tmp_path / "data")
    payload = base_video.read_bytes()
    upload = repository.create_upload_session("overlay.mp4", len(payload), "video")
    repository.append_upload_chunk(upload["upload_id"], payload)
    completed = repository.finalize_upload(upload["upload_id"])
    asset_id = completed["asset_id"]
    assert asset_id

    output = tmp_path / "final.mp4"
    compose_ip_broadcast_video(
        str(base_video),
        str(audio),
        str(output),
        "第一句\n第二句",
        story_segments=[
            {"segment_id": "1", "text": "第一句"},
            {"segment_id": "2", "text": "第二句"},
        ],
        visual_groups=[
            {
                "group_id": "v2-overlay",
                "visual_type": "uploaded_video",
                "video_asset_id": asset_id,
                "segment_ids": ["1"],
            }
        ],
        template_id="boss_clean",
    )

    assert output.is_file()
    probe = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "stream=width,height",
            "-of",
            "csv=p=0",
            str(output),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    assert probe.stdout.strip().splitlines()[0] == "1080,1920"


def test_v2_image_asset_selection_reaches_successful_render_with_real_media(monkeypatch, tmp_path):
    """Image storyboard selections use the same stable-ID render boundary."""

    if shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None:
        pytest.skip("ffmpeg/ffprobe required for the real-media render contract")

    monkeypatch.setenv("PIXELLE_VIDEO_ROOT", str(tmp_path))
    base_video = tmp_path / "base.mp4"
    audio = tmp_path / "voice.mp3"
    image = tmp_path / "product.png"
    subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            "color=c=0x243b53:s=320x568:r=25",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:sample_rate=16000",
            "-t",
            "1.2",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            str(base_video),
        ],
        check=True,
    )
    subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=660:sample_rate=16000",
            "-t",
            "1.2",
            "-c:a",
            "libmp3lame",
            str(audio),
        ],
        check=True,
    )
    subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            "color=c=orange:s=240x320",
            "-frames:v",
            "1",
            str(image),
        ],
        check=True,
    )

    repository = AssetLibraryRepository(tmp_path / "data")
    payload = image.read_bytes()
    upload = repository.create_upload_session("product.png", len(payload), "image")
    repository.append_upload_chunk(upload["upload_id"], payload)
    completed = repository.finalize_upload(upload["upload_id"])
    asset_id = completed["asset_id"]

    output = tmp_path / "final-image.mp4"
    compose_ip_broadcast_video(
        str(base_video),
        str(audio),
        str(output),
        "第一句\n第二句",
        story_segments=[
            {"segment_id": "1", "text": "第一句"},
            {"segment_id": "2", "text": "第二句"},
        ],
        visual_groups=[
            {
                "group_id": "v2-image-overlay",
                "visual_type": "uploaded_image",
                "image_asset_id": asset_id,
                "segment_ids": ["1"],
            }
        ],
        template_id="boss_clean",
    )

    assert output.is_file()
    probe = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "stream=width,height",
            "-of",
            "csv=p=0",
            str(output),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    assert probe.stdout.strip().splitlines()[0] == "1080,1920"


def test_v2_full_production_reference_set_is_snapshotted(monkeypatch, tmp_path):
    """The final-video boundary pins every V2 resource used by production.

    This is the deterministic Gate-C companion to the desktop picker check:
    media revisions, voice, digital human + scene, brand BGM and template
    contract must all be present in the session ledger before rendering.
    """

    if shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None:
        pytest.skip("ffmpeg/ffprobe required for the production reference contract")

    monkeypatch.setenv("PIXELLE_VIDEO_ROOT", str(tmp_path))
    base_video = tmp_path / "base.mp4"
    voice = tmp_path / "voice.mp3"
    bgm = tmp_path / "bgm.mp3"
    image = tmp_path / "portrait.png"
    subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "color=c=0x243b53:s=320x568:r=25",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:sample_rate=16000",
            "-t",
            "1.2",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            str(base_video),
        ],
        check=True,
    )
    for frequency, output in ((660, voice), (880, bgm)):
        subprocess.run(
            [
                "ffmpeg",
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-f",
                "lavfi",
                "-i",
                f"sine=frequency={frequency}:sample_rate=16000",
                "-t",
                "1.2",
                "-c:a",
                "libmp3lame",
                str(output),
            ],
            check=True,
        )
    subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "color=c=orange:s=240x320",
            "-frames:v",
            "1",
            str(image),
        ],
        check=True,
    )

    repository = AssetLibraryRepository()

    def upload(path, kind):
        payload = path.read_bytes()
        session = repository.create_upload_session(path.name, len(payload), kind)
        repository.append_upload_chunk(session["upload_id"], payload)
        result = repository.finalize_upload(session["upload_id"])
        assert result["asset_id"]
        return repository.get_asset(result["asset_id"])

    video_asset = upload(base_video, "video")
    image_asset = upload(image, "image")
    voice_asset = upload(voice, "audio")
    bgm_asset = upload(bgm, "audio")
    voice_profile = repository.create_voice_profile(
        {
            "voice_id": "gate-c-voice-profile",
            "name": "Gate-C 音色",
            "audio_asset_id": voice_asset["asset_id"],
            "language": "zh-CN",
            "style": "自然",
        }
    )
    person = repository.create_digital_human_profile(
        {"name": "Gate-C 数字人", "source_asset_id": image_asset["asset_id"]}
    )
    brand = repository.create_brand_kit(
        {"brand_name": "Gate-C 品牌", "default_bgm_asset_id": bgm_asset["asset_id"]}
    )
    template = repository.create_template_revision(
        {
            "display_name": "Gate-C 模板",
            "renderer_version": "ip-broadcast-composer-v2-test",
            "cover_contract": {
                "base_template_id": "boss_clean",
                "canvas_width": 1080,
                "canvas_height": 1920,
            },
            "subtitle_contract": {"font_size": 52, "margin_v": 168},
        }
    )

    session = IpBroadcastSession(session_id="gate-c-session")
    session.state.update(
        {
            "tts_ref_audio_id": voice_profile["resource_id"],
            "portrait_id": person["resource_id"],
            "digital_human_scene_id": person["scenes"][0]["scene_id"],
            "brand_kit_id": brand["resource_id"],
            "brand_bgm_asset_id": bgm_asset["asset_id"],
            "template_id": template["resource_id"],
            "audio_path": str(voice),
            "digital_human_video_path": str(base_video),
            "final_script": "第一句\n第二句",
            "story_segments": [
                {"segment_id": "1", "text": "第一句"},
                {"segment_id": "2", "text": "第二句"},
            ],
            "overlay_enabled": True,
            "subtitle_enabled": True,
            "visual_groups": [
                {
                    "group_id": "gate-c-overlay",
                    "visual_type": "uploaded_video",
                    "video_asset_id": video_asset["asset_id"],
                    "segment_ids": ["1"],
                }
            ],
        }
    )

    asyncio.run(_run_postproduction(None, session))
    assert Path(str(session.state["final_video_path"])).is_file()
    assert Path(str(session.state["cover_path"])).is_file()

    usage = repository.list_usage(session.session_id)
    snapshots = repository.list_snapshots(session.session_id)
    usage_keys = {(item["resource_kind"], item["resource_id"]) for item in usage}
    assert ("voice", voice_profile["resource_id"]) in usage_keys
    assert ("digital_human", person["resource_id"]) in usage_keys
    assert ("digital_human_scene", person["scenes"][0]["scene_id"]) in usage_keys
    assert ("brand", brand["resource_id"]) in usage_keys
    assert ("audio", bgm_asset["asset_id"]) in usage_keys
    assert ("template", template["resource_id"]) in usage_keys
    assert ("video", video_asset["asset_id"]) in usage_keys
    assert len(session.state["resource_snapshot_ids"]) == len(snapshots)

    media_snapshot = next(item for item in snapshots if item["resource_kind"] == "video")
    assert media_snapshot["revision_id"] == video_asset["current_revision_id"]
    template_snapshot = next(item for item in snapshots if item["resource_kind"] == "template")
    assert template_snapshot["template_revision"] == template["summary"]["revision"]
    assert template_snapshot["renderer_version"] == "ip-broadcast-composer-v2-test"

    probe = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "stream=width,height",
            "-of",
            "csv=p=0",
            str(session.state["final_video_path"]),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    assert probe.stdout.strip().splitlines()[0] == "1080,1920"
