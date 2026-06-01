"""Subtitle generation and embedding service using FFmpeg"""

import re
import subprocess
from pathlib import Path

from loguru import logger


def _probe_duration(media_path: str) -> float:
    """Return media duration in seconds using ffprobe"""
    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        media_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    return float(result.stdout.strip())


def _split_sentences(text: str) -> list[str]:
    """Split text into sentences on Chinese/English punctuation"""
    sentences = re.split(r"(?<=[。！？.!?])\s*", text.strip())
    return [s.strip() for s in sentences if s.strip()]


def _format_srt_time(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int((seconds - int(seconds)) * 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def generate_srt(text: str, audio_path: str, srt_path: str) -> str:
    """
    Generate an SRT subtitle file by distributing sentence timings proportionally
    over the total audio duration.
    """
    duration = _probe_duration(audio_path)
    sentences = _split_sentences(text)
    if not sentences:
        sentences = [text]

    char_counts = [max(len(s), 1) for s in sentences]
    total_chars = sum(char_counts)

    lines = []
    current_time = 0.0
    for idx, (sentence, chars) in enumerate(zip(sentences, char_counts), start=1):
        seg_duration = duration * (chars / total_chars)
        end_time = current_time + seg_duration
        lines.append(str(idx))
        lines.append(f"{_format_srt_time(current_time)} --> {_format_srt_time(end_time)}")
        lines.append(sentence)
        lines.append("")
        current_time = end_time

    Path(srt_path).parent.mkdir(parents=True, exist_ok=True)
    Path(srt_path).write_text("\n".join(lines), encoding="utf-8")
    logger.info(f"SRT generated: {srt_path} ({len(sentences)} sentences)")
    return srt_path


def _escape_ffmpeg_filter_path(path: str) -> str:
    """Escape a file path for safe embedding inside an FFmpeg filter string.

    FFmpeg's libavfilter parser treats these characters as special:
    backslash, single-quote, colon, square brackets, comma, semicolon.
    We normalise to forward slashes first (works on all platforms), then
    escape each special character, and finally wrap the whole thing in
    single quotes so that paths containing spaces are handled correctly.
    """
    path = path.replace("\\", "/")
    for ch in ("'", ":", "[", "]", ",", ";"):
        path = path.replace(ch, f"\\{ch}")
    return f"'{path}'"


def _build_subtitles_filter(srt_path: str, force_style: str | None = None) -> str:
    escaped = _escape_ffmpeg_filter_path(srt_path)
    if not force_style:
        return f"subtitles={escaped}"
    safe_style = force_style.replace("\\", "\\\\").replace("'", "\\'")
    return f"subtitles={escaped}:force_style='{safe_style}'"


def embed_subtitles(
    video_path: str,
    srt_path: str,
    output_path: str,
    force_style: str | None = None,
) -> str:
    """Burn subtitles into video using FFmpeg libass filter"""
    cmd = [
        "ffmpeg", "-y",
        "-i", video_path,
        "-vf", _build_subtitles_filter(srt_path, force_style),
        "-c:a", "copy",
        output_path,
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    logger.info(f"Subtitles embedded: {output_path}")
    return output_path


def remove_silence(audio_path: str, output_path: str, threshold_db: float = -50.0) -> str:
    """Remove silence segments from audio using FFmpeg silenceremove filter"""
    cmd = [
        "ffmpeg", "-y",
        "-i", audio_path,
        "-af", (
            f"silenceremove=start_periods=1:start_threshold={threshold_db}dB"
            f":stop_periods=-1:stop_threshold={threshold_db}dB"
        ),
        output_path,
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    logger.info(f"Silence removed: {output_path}")
    return output_path


def extract_first_frame(video_path: str, output_path: str) -> str:
    """Extract the first frame of a video as a PNG image"""
    cmd = [
        "ffmpeg", "-y",
        "-i", video_path,
        "-ss", "0",
        "-frames:v", "1",
        output_path,
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    logger.info(f"First frame extracted: {output_path}")
    return output_path


def merge_audio_into_video(video_path: str, audio_path: str, output_path: str) -> str:
    """Replace the audio track of a video with a given audio file"""
    cmd = [
        "ffmpeg", "-y",
        "-i", video_path,
        "-i", audio_path,
        "-map", "0:v",
        "-map", "1:a",
        "-c:v", "copy",
        "-shortest",
        output_path,
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    logger.info(f"Audio merged into video: {output_path}")
    return output_path
