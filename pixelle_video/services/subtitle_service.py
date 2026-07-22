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


def probe_video_dimensions(media_path: str) -> tuple[int, int]:
    """Return the encoded video dimensions (width, height).

    The workflow previously trusted the requested digital-human dimensions.  A
    number of providers return a different size, so every render path must use
    the dimensions reported by the actual media instead.
    """
    cmd = [
        "ffprobe", "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "stream=width,height",
        "-of", "csv=p=0:s=x",
        media_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    width, height = (int(value) for value in result.stdout.strip().split("x", 1))
    if width <= 0 or height <= 0:
        raise ValueError(f"Invalid video dimensions for {media_path}: {width}x{height}")
    return width, height


def _split_sentences(text: str, max_chars: int = 16) -> list[str]:
    """Split text into short subtitle units for vertical short videos."""
    sentence_candidates = re.split(r"(?<=[。！？.!?，,；;])\s*|\n+", text.strip())
    sentences: list[str] = []
    for candidate in sentence_candidates:
        candidate = candidate.strip()
        if not candidate:
            continue
        sentences.extend(_split_long_subtitle(candidate, max_chars=max_chars))
    return sentences


def _split_long_subtitle(text: str, max_chars: int = 16) -> list[str]:
    if len(text) <= max_chars:
        return [text]
    chunks = []
    current = text
    while len(current) > max_chars:
        split_at = max(
            current.rfind("，", 0, max_chars + 1),
            current.rfind(",", 0, max_chars + 1),
            current.rfind("、", 0, max_chars + 1),
            current.rfind(" ", 0, max_chars + 1),
        )
        if split_at < max_chars // 2:
            split_at = max_chars
        else:
            split_at += 1
        chunks.append(current[:split_at].strip())
        current = current[split_at:].strip()
    if current:
        chunks.append(current)
    return chunks


def _format_srt_time(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int((seconds - int(seconds)) * 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _format_ass_time(seconds: float) -> str:
    """Format seconds using ASS's h:mm:ss.cc timestamp format."""
    total_centiseconds = max(0, round(seconds * 100))
    hours, remainder = divmod(total_centiseconds, 360000)
    minutes, remainder = divmod(remainder, 6000)
    seconds_value, centiseconds = divmod(remainder, 100)
    return f"{hours}:{minutes:02d}:{seconds_value:02d}.{centiseconds:02d}"


def _build_timed_subtitles(
    text: str,
    audio_path: str,
) -> list[tuple[int, float, float, str]]:
    duration = _probe_duration(audio_path)
    sentences = _split_sentences(text)
    if not sentences:
        sentences = [text]
    char_counts = [max(len(sentence), 1) for sentence in sentences]
    total_chars = sum(char_counts)
    current_time = 0.0
    timed: list[tuple[int, float, float, str]] = []
    for index, (sentence, chars) in enumerate(zip(sentences, char_counts), start=1):
        segment_duration = duration * (chars / total_chars)
        end_time = duration if index == len(sentences) else current_time + segment_duration
        timed.append((index, current_time, end_time, sentence))
        current_time = end_time
    return timed


def generate_srt(text: str, audio_path: str, srt_path: str) -> str:
    """
    Generate an SRT subtitle file by distributing sentence timings proportionally
    over the total audio duration.
    """
    lines = []
    timed = _build_timed_subtitles(text, audio_path)
    for idx, start_time, end_time, sentence in timed:
        lines.append(str(idx))
        lines.append(f"{_format_srt_time(start_time)} --> {_format_srt_time(end_time)}")
        lines.append(sentence)
        lines.append("")

    Path(srt_path).parent.mkdir(parents=True, exist_ok=True)
    Path(srt_path).write_text("\n".join(lines), encoding="utf-8")
    logger.info(f"SRT generated: {srt_path} ({len(timed)} sentences)")
    return srt_path


def _escape_ass_text(text: str) -> str:
    """Escape user text for an ASS Dialogue event."""
    return (
        text.replace("\\", "\\\\")
        .replace("{", "\\{")
        .replace("}", "\\}")
        .replace("\n", r"\N")
        .replace("\r", "")
    )


def generate_ass(
    text: str,
    audio_path: str,
    ass_path: str,
    *,
    play_res_x: int = 1080,
    play_res_y: int = 1920,
    force_style: str | None = None,
) -> str:
    """Generate a canvas-aware ASS subtitle file.

    SRT converted by libass uses a small default PlayRes (384x288), which
    makes margins and font sizes drift on vertical videos.  Writing the ASS
    header explicitly makes the subtitle coordinate system identical to the
    cover templates and the normalized output video.
    """
    style_values = {
        "Fontname": "PingFang SC",
        "Fontsize": 26,
        "PrimaryColour": "&H00FFFFFF",
        "SecondaryColour": "&H00FFFFFF",
        "OutlineColour": "&H99000000",
        "BackColour": "&H66000000",
        "Bold": 0,
        "Italic": 0,
        "Underline": 0,
        "StrikeOut": 0,
        "ScaleX": 100,
        "ScaleY": 100,
        "Spacing": 0,
        "Angle": 0,
        "BorderStyle": 3,
        "Outline": 2,
        "Shadow": 1,
        "Alignment": 2,
        "MarginL": 70,
        "MarginR": 70,
        "MarginV": 340,
        "Encoding": 1,
    }
    if force_style:
        for part in force_style.split(","):
            key, separator, value = part.partition("=")
            normalized_key = "Fontname" if key == "FontName" else key
            if not separator or normalized_key not in style_values:
                continue
            style_values[normalized_key] = value

    style_order = (
        "Name", "Fontname", "Fontsize", "PrimaryColour", "SecondaryColour",
        "OutlineColour", "BackColour", "Bold", "Italic", "Underline",
        "StrikeOut", "ScaleX", "ScaleY", "Spacing", "Angle", "BorderStyle",
        "Outline", "Shadow", "Alignment", "MarginL", "MarginR", "MarginV",
        "Encoding",
    )
    style_line = ["Default"]
    for key in style_order[1:]:
        style_line.append(str(style_values.get(key, "")))

    lines = [
        "[Script Info]",
        "ScriptType: v4.00+",
        "PlayResX: %d" % int(play_res_x),
        "PlayResY: %d" % int(play_res_y),
        "WrapStyle: 2",
        "ScaledBorderAndShadow: yes",
        "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
        "Style: " + ",".join(style_line),
        "",
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]
    for _index, start_time, end_time, sentence in _build_timed_subtitles(text, audio_path):
        lines.append(
            "Dialogue: 0,%s,%s,Default,,0,0,0,,%s"
            % (_format_ass_time(start_time), _format_ass_time(end_time), _escape_ass_text(sentence))
        )

    Path(ass_path).parent.mkdir(parents=True, exist_ok=True)
    Path(ass_path).write_text("\n".join(lines) + "\n", encoding="utf-8")
    logger.info(f"ASS generated: {ass_path} ({len(lines) - 13} subtitles, {play_res_x}x{play_res_y})")
    return ass_path


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


def _build_subtitles_filter(
    subtitle_path: str,
    force_style: str | None = None,
    fontsdir: str | None = None,
) -> str:
    escaped = _escape_ffmpeg_filter_path(subtitle_path)
    options: list[str] = []
    if fontsdir:
        options.append(f"fontsdir={_escape_ffmpeg_filter_path(fontsdir)}")
    if not force_style:
        return f"subtitles={escaped}" + (":" + ":".join(options) if options else "")
    safe_style = force_style.replace("\\", "\\\\").replace("'", "\\'")
    options.append(f"force_style='{safe_style}'")
    return f"subtitles={escaped}:" + ":".join(options)


def embed_subtitles(
    video_path: str,
    srt_path: str,
    output_path: str,
    force_style: str | None = None,
    fontsdir: str | None = None,
) -> str:
    """Burn subtitles into video using FFmpeg libass filter"""
    cmd = [
        "ffmpeg", "-y",
        "-i", video_path,
        "-vf", _build_subtitles_filter(srt_path, force_style, fontsdir),
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
