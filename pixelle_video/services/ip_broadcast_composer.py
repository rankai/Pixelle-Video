"""FFmpeg composition helpers for IP broadcast desktop workflow."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Any

from loguru import logger

from pixelle_video.services.ip_broadcast_templates import (
    IP_BROADCAST_CANVAS_HEIGHT,
    IP_BROADCAST_CANVAS_WIDTH,
    build_ass_force_style,
    get_ip_broadcast_template_for_render,
    resolve_ip_broadcast_fonts_dir,
    wrap_template_subtitle_text,
)
from pixelle_video.services.subtitle_service import (
    _probe_duration,
    embed_subtitles,
    generate_ass,
    generate_srt,
    merge_audio_into_video,
    probe_video_dimensions,
)
from pixelle_video.utils.os_util import get_temp_path

CANVAS_WIDTH = IP_BROADCAST_CANVAS_WIDTH
CANVAS_HEIGHT = IP_BROADCAST_CANVAS_HEIGHT


def normalize_video_to_canvas(
    video_path: str,
    output_path: str,
    *,
    width: int = CANVAS_WIDTH,
    height: int = CANVAS_HEIGHT,
) -> str:
    """Encode a video onto the single canvas used by templates and captions.

    ``force_original_aspect_ratio=increase`` followed by a centered crop keeps
    the talking head full-height while removing provider-specific side bars.
    The explicit SAR reset prevents a second source of CSS/ASS drift.
    """
    probe_video_dimensions(video_path)
    filter_graph = (
        f"scale={int(width)}:{int(height)}:force_original_aspect_ratio=increase:flags=lanczos,"
        f"crop={int(width)}:{int(height)}:(in_w-{int(width)})/2:(in_h-{int(height)})/2,setsar=1"
    )
    cmd = [
        "ffmpeg", "-y",
        "-i", video_path,
        "-vf", filter_graph,
        "-map", "0:v:0",
        "-map", "0:a?",
        "-c:v", "libx264",
        "-preset", "veryfast",
        "-crf", "18",
        "-pix_fmt", "yuv420p",
        "-c:a", "copy",
        "-movflags", "+faststart",
        output_path,
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    return output_path


def build_segment_timeline(
    story_segments: list[dict[str, Any]],
    audio_duration: float,
) -> list[dict[str, float | str]]:
    total_chars = sum(max(len(str(item.get("text", "")).strip()), 1) for item in story_segments)
    if not story_segments or total_chars <= 0 or audio_duration <= 0:
        return []
    current = 0.0
    timeline = []
    for index, segment in enumerate(story_segments):
        chars = max(len(str(segment.get("text", "")).strip()), 1)
        duration = audio_duration * chars / total_chars
        end = audio_duration if index == len(story_segments) - 1 else current + duration
        timeline.append(
            {
                "segment_id": str(segment.get("segment_id") or index + 1),
                "start_time": round(current, 3),
                "end_time": round(end, 3),
                "duration": round(end - current, 3),
            }
        )
        current = end
    return timeline


def build_video_overlay_command(
    base_video: str,
    overlay_video: str,
    output_path: str,
    start_time: float,
    end_time: float,
    output_duration: float,
    width: int,
    height: int,
) -> list[str]:
    start = _format_time(start_time)
    end = _format_time(end_time)
    filter_complex = (
        f"[1:v]scale={width}:{height}:force_original_aspect_ratio=increase,"
        f"crop={width}:{height},setsar=1[ov];"
        f"[0:v][ov]overlay=0:0:enable='between(t,{start},{end})'[v]"
    )
    return [
        "ffmpeg",
        "-y",
        "-i",
        base_video,
        "-stream_loop",
        "-1",
        "-i",
        overlay_video,
        "-filter_complex",
        filter_complex,
        "-map",
        "[v]",
        "-map",
        "0:a?",
        "-t",
        _format_time(output_duration),
        "-c:v",
        "libx264",
        "-c:a",
        "copy",
        "-shortest",
        output_path,
    ]


def build_image_overlay_command(
    base_video: str,
    overlay_image: str,
    output_path: str,
    start_time: float,
    end_time: float,
    output_duration: float,
    width: int,
    height: int,
) -> list[str]:
    """Overlay a still image for a segment while preserving the base audio."""
    start = _format_time(start_time)
    end = _format_time(end_time)
    filter_complex = (
        f"[1:v]scale={width}:{height}:force_original_aspect_ratio=increase,"
        f"crop={width}:{height},format=rgba[ov];"
        f"[0:v][ov]overlay=0:0:enable='between(t,{start},{end})'[v]"
    )
    return [
        "ffmpeg",
        "-y",
        "-i",
        base_video,
        "-loop",
        "1",
        "-i",
        overlay_image,
        "-filter_complex",
        filter_complex,
        "-map",
        "[v]",
        "-map",
        "0:a?",
        "-t",
        _format_time(output_duration),
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "copy",
        "-shortest",
        output_path,
    ]


def compose_ip_broadcast_video(
    base_video: str,
    audio_path: str,
    output_path: str,
    script: str,
    story_segments: list[dict[str, Any]] | None = None,
    visual_groups: list[dict[str, Any]] | None = None,
    template_id: str | None = None,
    subtitle_style: dict[str, Any] | None = None,
    subtitle_enabled: bool = True,
    width: int = CANVAS_WIDTH,
    height: int = CANVAS_HEIGHT,
    clean_output_path: str | None = None,
) -> str:
    audio_duration = _probe_duration(audio_path)
    uid = Path(output_path).stem
    _validate_visual_overlay_assets(visual_groups or [])
    # Overlay and caption coordinates are defined in the canonical template
    # canvas, regardless of the provider's requested generation size.
    width, height = CANVAS_WIDTH, CANVAS_HEIGHT
    normalized = normalize_video_to_canvas(
        base_video,
        get_temp_path(f"{uid}_canvas.mp4"),
        width=CANVAS_WIDTH,
        height=CANVAS_HEIGHT,
    )
    merged = merge_audio_into_video(normalized, audio_path, get_temp_path(f"{uid}_audio.mp4"))
    composed = _apply_visual_overlays(
        merged,
        story_segments or [],
        visual_groups or [],
        audio_duration,
        width,
        height,
        uid,
    )
    if clean_output_path:
        shutil.copy2(composed, clean_output_path)
    if subtitle_enabled and script.strip():
        ass = get_temp_path(f"{uid}.ass")
        template = get_ip_broadcast_template_for_render(template_id)
        force_style = build_ass_force_style(
            template,
            subtitle_style,
            video_width=width,
            video_height=CANVAS_HEIGHT,
        )
        render_script = wrap_template_subtitle_text(script, template, video_width=width, video_height=height)
        try:
            generate_ass(
                render_script,
                audio_path,
                ass,
                play_res_x=CANVAS_WIDTH,
                play_res_y=CANVAS_HEIGHT,
                force_style=force_style,
            )
            embed_subtitles(
                composed,
                ass,
                output_path,
                force_style=force_style,
                fontsdir=resolve_ip_broadcast_fonts_dir(),
            )
        except (OSError, TypeError, ValueError, subprocess.CalledProcessError) as exc:
            logger.warning("ASS 字幕生成失败，回退 SRT：{}", exc)
            srt = get_temp_path(f"{uid}.srt")
            generate_srt(render_script, audio_path, srt)
            embed_subtitles(composed, srt, output_path, force_style=force_style, fontsdir=resolve_ip_broadcast_fonts_dir())
    else:
        shutil.copy2(composed, output_path)
    return output_path


def _validate_visual_overlay_assets(visual_groups: list[dict[str, Any]]) -> None:
    missing_groups = []
    for group in visual_groups:
        visual_type = group.get("visual_type")
        if visual_type not in {"uploaded_video", "uploaded_image"}:
            continue
        overlay_path = (
            _resolve_uploaded_video_path(group)
            if visual_type == "uploaded_video"
            else _resolve_uploaded_image_path(group)
        )
        if not overlay_path or not Path(overlay_path).exists():
            missing_groups.append(str(group.get("group_id") or "未命名画面组"))
    if missing_groups:
        raise ValueError(f"画面规划缺少图片/视频素材：{', '.join(missing_groups)}")


def _apply_visual_overlays(
    base_video: str,
    story_segments: list[dict[str, Any]],
    visual_groups: list[dict[str, Any]],
    audio_duration: float,
    width: int,
    height: int,
    uid: str,
) -> str:
    timeline = build_segment_timeline(story_segments, audio_duration)
    if not timeline:
        return base_video
    current_video = base_video
    for index, group in enumerate(visual_groups, start=1):
        if group.get("visual_type") in {"", None, "digital_human"}:
            continue
        visual_type = group.get("visual_type")
        if visual_type == "uploaded_image":
            overlay_path = _resolve_uploaded_image_path(group)
        else:
            # AI-video groups continue to use the legacy/provider-generated
            # video path; uploaded-video groups resolve through the V2 ID.
            overlay_path = _resolve_uploaded_video_path(group)
        if visual_type == "ai_video" and not overlay_path:
            continue
        if not overlay_path or not Path(overlay_path).exists():
            continue
        selected = [item for item in timeline if item["segment_id"] in set(group.get("segment_ids", []))]
        if not selected:
            continue
        start_time = float(selected[0]["start_time"])
        end_time = float(selected[-1]["end_time"])
        next_video = get_temp_path(f"{uid}_overlay_{index}.mp4")
        command_builder = build_image_overlay_command if visual_type == "uploaded_image" else build_video_overlay_command
        subprocess.run(
            command_builder(
                current_video,
                overlay_path,
                next_video,
                start_time,
                end_time,
                audio_duration,
                width,
                height,
            ),
            check=True,
            capture_output=True,
        )
        current_video = next_video
    return current_video


def _resolve_uploaded_video_path(group: dict[str, Any]) -> str:
    """Resolve a workflow reference to a local path at render time.

    Legacy clients persist an absolute ``uploaded_video_path``.  V2 clients
    persist a stable ``video_asset_id`` and only a protected API URL, so the
    worker resolves the current revision here without exposing filesystem
    paths to the desktop UI.
    """
    overlay_path = str(group.get("uploaded_video_path") or "")
    asset_id = str(group.get("video_asset_id") or "").strip()
    if asset_id:
        try:
            from pixelle_video.services.assets_v2.repository import AssetLibraryRepository

            repository = AssetLibraryRepository()
            asset = repository.get_asset(asset_id) or repository.get_asset_by_legacy_id("video", asset_id)
            resolved = repository.get_revision_path(asset["asset_id"]) if asset else None
            if resolved:
                return str(resolved)
        except (OSError, ValueError, RuntimeError) as exc:
            logger.warning("Unable to resolve V2 video asset {}: {}", asset_id, exc)
    return overlay_path


def _resolve_uploaded_image_path(group: dict[str, Any]) -> str:
    """Resolve a V2 image asset ID without exposing its filesystem path."""
    overlay_path = str(group.get("uploaded_image_path") or "")
    asset_id = str(group.get("image_asset_id") or "").strip()
    if asset_id:
        try:
            from pixelle_video.services.assets_v2.repository import AssetLibraryRepository

            repository = AssetLibraryRepository()
            asset = repository.get_asset(asset_id) or repository.get_asset_by_legacy_id("image", asset_id)
            resolved = repository.get_revision_path(asset["asset_id"]) if asset else None
            if resolved:
                return str(resolved)
        except (OSError, ValueError, RuntimeError) as exc:
            logger.warning("Unable to resolve V2 image asset {}: {}", asset_id, exc)
    return overlay_path


def _format_time(value: float) -> str:
    text = f"{value:.3f}".rstrip("0").rstrip(".")
    return text or "0"
