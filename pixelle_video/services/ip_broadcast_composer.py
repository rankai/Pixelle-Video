"""FFmpeg composition helpers for IP broadcast desktop workflow."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Any

from pixelle_video.services.ip_broadcast_templates import (
    build_ass_force_style,
    get_ip_broadcast_template,
)
from pixelle_video.services.subtitle_service import (
    _probe_duration,
    embed_subtitles,
    generate_srt,
    merge_audio_into_video,
)
from pixelle_video.utils.os_util import get_temp_path


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
    width: int = 720,
    height: int = 1280,
) -> str:
    audio_duration = _probe_duration(audio_path)
    uid = Path(output_path).stem
    _validate_visual_overlay_assets(visual_groups or [])
    merged = merge_audio_into_video(base_video, audio_path, get_temp_path(f"{uid}_audio.mp4"))
    composed = _apply_visual_overlays(
        merged,
        story_segments or [],
        visual_groups or [],
        audio_duration,
        width,
        height,
        uid,
    )
    if subtitle_enabled and script.strip():
        srt = get_temp_path(f"{uid}.srt")
        generate_srt(script, audio_path, srt)
        template = get_ip_broadcast_template(template_id)
        embed_subtitles(
            composed,
            srt,
            output_path,
            force_style=build_ass_force_style(
                template,
                subtitle_style,
                video_height=height,
            ),
        )
    else:
        shutil.copy2(composed, output_path)
    return output_path


def _validate_visual_overlay_assets(visual_groups: list[dict[str, Any]]) -> None:
    missing_groups = []
    for group in visual_groups:
        if group.get("visual_type") != "uploaded_video":
            continue
        overlay_path = str(group.get("uploaded_video_path") or "")
        if not overlay_path or not Path(overlay_path).exists():
            missing_groups.append(str(group.get("group_id") or "未命名画面组"))
    if missing_groups:
        raise ValueError(f"画面规划缺少视频素材：{', '.join(missing_groups)}")


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
        overlay_path = str(group.get("uploaded_video_path") or "")
        if group.get("visual_type") == "ai_video" and not overlay_path:
            continue
        if not overlay_path or not Path(overlay_path).exists():
            continue
        selected = [item for item in timeline if item["segment_id"] in set(group.get("segment_ids", []))]
        if not selected:
            continue
        start_time = float(selected[0]["start_time"])
        end_time = float(selected[-1]["end_time"])
        next_video = get_temp_path(f"{uid}_overlay_{index}.mp4")
        subprocess.run(
            build_video_overlay_command(
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


def _format_time(value: float) -> str:
    text = f"{value:.3f}".rstrip("0").rstrip(".")
    return text or "0"
