"""Video script extraction — multi-strategy pipeline.

Strategy order:
1. Douyin/TikTok direct: mobile API → CDN URL → Doubao video_url transcription (no login needed)
2. yt-dlp subtitles: for platforms with embedded captions (YouTube, Bilibili, etc.)
3. yt-dlp video download + Doubao multimodal frame analysis (slow fallback)

The extractor intentionally does not infer a script from title/hashtags. If a
real video URL or Douyin video ID cannot be resolved, it raises a clear error
instead of generating plausible but incorrect口播.
"""

import asyncio
import base64
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Optional

import httpx
from loguru import logger
from openai import AsyncOpenAI

from pixelle_video.services.ytdlp_cookies import (
    is_cookie_unavailable_error,
    ytdlp_cookie_options,
)

_DOUYIN_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
    ),
    "Referer": "https://www.douyin.com/",
}

_DOUYIN_ID_RE = re.compile(
    r"(?:douyin\.com/video/|douyin\.com/share/video/)(\d{15,20})"
)


class VideoScriptExtractor:
    FRAME_COUNT = 8
    DEFAULT_MULTIMODAL_MODEL = "doubao-seed-2-0-pro-260215"

    def __init__(self, api_key: str, base_url: str, model: Optional[str] = None):
        self.api_key = api_key
        self.base_url = base_url
        self.model = model or self.DEFAULT_MULTIMODAL_MODEL

    async def extract(self, text_or_url: str) -> str:
        """Extract the narration script from a video URL or Douyin/TikTok share text."""
        url = _extract_url(text_or_url)

        # Resolve v.douyin.com short links to the canonical URL
        if url and "v.douyin.com" in url:
            url = await asyncio.get_event_loop().run_in_executor(None, _resolve_redirect, url)

        # ── Douyin path (no login required) ───────────────────────────────────
        if not url:
            url = await asyncio.get_event_loop().run_in_executor(
                None, _resolve_douyin_command_text, text_or_url
            )

        video_id = _extract_douyin_id(url or text_or_url)
        if not url and not video_id:
            raise ValueError(
                "检测到抖音分享口令，但当前没有可用的口令解析服务。"
                "请配置 TIKHUB_API_KEY，或粘贴包含 https://v.douyin.com/ "
                "的分享文本。"
            )

        if video_id:
            script = await self._extract_douyin(video_id)
            if script:
                return script

        if url and _is_douyin_url(url):
            direct_url = await self._get_ytdlp_direct_video_url(url)
            if direct_url:
                script = await self._transcribe_video_url(direct_url)
                if script:
                    return script

        # ── Generic yt-dlp subtitle path ──────────────────────────────────────
        if url:
            script = await self._try_subtitles(url)
            if script and script.strip():
                logger.info(f"Script extracted via subtitles ({len(script)} chars)")
                return script

            # ── yt-dlp video download + frame multimodal ───────────────────
            logger.info("No subtitles — trying multimodal frame analysis")
            try:
                return await self._extract_via_frames(url)
            except Exception as e:
                logger.warning(f"Frame analysis failed: {e}")

        raise ValueError("视频文案提取失败：无法从该视频获取可转写内容，请检查链接或手动粘贴文案。")

    # ── Douyin no-login path ──────────────────────────────────────────────────

    async def _extract_douyin(self, video_id: str) -> Optional[str]:
        cdn_url = await asyncio.get_event_loop().run_in_executor(
            None, self._get_douyin_cdn_url, video_id
        )
        if not cdn_url:
            logger.warning(f"Could not get Douyin CDN URL for {video_id}")
            return None

        logger.info(f"Transcribing Douyin video via Doubao video_url: {cdn_url[:60]}...")
        return await self._transcribe_video_url(cdn_url)

    async def _transcribe_video_url(self, video_url: str) -> Optional[str]:
        try:
            client = AsyncOpenAI(api_key=self.api_key, base_url=self.base_url)
            resp = await client.chat.completions.create(
                model=self.model,
                messages=[{
                    "role": "user",
                    "content": [
                        {"type": "video_url", "video_url": {"url": video_url}},
                        {
                            "type": "text",
                            "text": "请逐字转录这个视频的完整口播文案，只输出文案正文，不要添加任何说明。",
                        },
                    ],
                }],
                max_tokens=4000,
            )
            result = resp.choices[0].message.content or ""
            logger.info(f"Video transcription complete ({len(result)} chars)")
            return result
        except Exception as e:
            logger.warning(f"Doubao video_url transcription failed: {e}")
            return None

    @staticmethod
    def _get_douyin_cdn_url(video_id: str) -> Optional[str]:
        """Fetch the Douyin video CDN URL via the public mobile feed API (no login needed)."""
        try:
            with httpx.Client(
                headers=_DOUYIN_HEADERS, follow_redirects=True, timeout=15
            ) as client:
                r = client.get(
                    f"https://api.amemv.com/aweme/v1/feed/?aweme_id={video_id}"
                )
                data = r.json()
                items = data.get("aweme_list", [])
                # Prefer exact match, fall back to first item
                target = next(
                    (i for i in items if i.get("aweme_id") == video_id),
                    items[0] if items else None,
                )
                if target:
                    video = target.get("video", {})
                    for key in ("play_addr", "download_addr"):
                        urls = (video.get(key) or {}).get("url_list", [])
                        if urls:
                            return urls[0]
        except Exception as e:
            logger.warning(f"Douyin API error: {e}")
        return None

    # ── yt-dlp subtitle path ──────────────────────────────────────────────────

    async def _try_subtitles(self, url: str) -> Optional[str]:
        try:
            _require_ytdlp()
        except RuntimeError as e:
            logger.warning(str(e))
            return None

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            cmd = [
                *_ytdlp_base_cmd(),
                "--write-subs", "--write-auto-subs",
                "--sub-langs", "zh-Hans,zh-Hant,zh,en",
                "--sub-format", "vtt/srt/best",
                "--skip-download",
                "--output", str(tmp_path / "sub"),
                url,
            ]
            try:
                proc = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                _, stderr = await asyncio.wait_for(proc.communicate(), timeout=90)
                if proc.returncode != 0:
                    logger.debug(
                        f"yt-dlp subtitle stderr: {stderr.decode(errors='replace')[:300]}"
                    )
            except asyncio.TimeoutError:
                logger.warning("yt-dlp subtitle download timed out")
                return None
            except Exception as e:
                logger.warning(f"yt-dlp subtitle download failed: {e}")
                return None

            for ext in ("vtt", "srt", "srv3", "srv2", "srv1"):
                for sub_file in tmp_path.glob(f"*.{ext}"):
                    text = _parse_subtitle_file(sub_file)
                    if text.strip():
                        return text
        return None

    # ── yt-dlp video download + multimodal frame analysis ────────────────────

    async def _get_ytdlp_direct_video_url(self, url: str) -> Optional[str]:
        try:
            _require_ytdlp()
        except RuntimeError as e:
            logger.warning(str(e))
            return None

        for cookie_args in ytdlp_cookie_options():
            cmd = [
                *_ytdlp_base_cmd(),
                "--get-url",
                "--no-playlist",
                "--format", "best[height<=720]/best",
                *cookie_args,
                url,
            ]
            try:
                proc = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=120)
                if proc.returncode != 0:
                    error_text = stderr.decode(errors="replace")[:500]
                    if is_cookie_unavailable_error(error_text):
                        logger.debug(f"Skipping unavailable browser cookies: {error_text}")
                    else:
                        logger.debug(f"yt-dlp direct-url stderr: {error_text}")
                    continue
                for line in stdout.decode(errors="replace").splitlines():
                    line = line.strip()
                    if line.startswith("http"):
                        logger.info("Resolved direct video URL via yt-dlp")
                        return line
            except asyncio.TimeoutError:
                logger.warning("yt-dlp direct URL extraction timed out")
            except Exception as e:
                logger.warning(f"yt-dlp direct URL extraction failed: {e}")
        return None

    async def _extract_via_frames(self, url: str) -> str:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            video_path = await self._download_video(url, tmp_path)
            if not video_path:
                raise RuntimeError("无法下载视频，请检查 URL 或手动粘贴文案")

            frames = await self._extract_frames(video_path, tmp_path)
            if not frames:
                raise RuntimeError("无法从视频提取帧")

            return await self._analyze_frames_with_llm(frames)

    async def _download_video(self, url: str, out_dir: Path) -> Optional[Path]:
        _require_ytdlp()
        cmd = [
            *_ytdlp_base_cmd(),
            "--format", "bestvideo[height<=480]+bestaudio/best[height<=480]/best",
            "--output", str(out_dir / "video.%(ext)s"),
            "--no-playlist",
            url,
        ]
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await asyncio.wait_for(proc.communicate(), timeout=300)
            if proc.returncode != 0:
                logger.warning(
                    f"yt-dlp download failed: {stderr.decode(errors='replace')[:500]}"
                )
                return None
        except asyncio.TimeoutError:
            logger.warning("yt-dlp video download timed out (300 s)")
            return None
        except Exception as e:
            logger.warning(f"yt-dlp video download error: {e}")
            return None

        for f in out_dir.iterdir():
            if f.stem == "video":
                return f
        return None

    async def _extract_frames(self, video_path: Path, out_dir: Path) -> list[Path]:
        probe_cmd = [
            "ffprobe", "-v", "quiet",
            "-print_format", "json",
            "-show_format",
            str(video_path),
        ]
        try:
            result = subprocess.run(probe_cmd, capture_output=True, text=True, timeout=30)
            info = json.loads(result.stdout)
            duration = float(info["format"]["duration"])
        except Exception:
            duration = 60.0

        frames: list[Path] = []
        interval = max(1.0, duration / (self.FRAME_COUNT + 1))
        for i in range(self.FRAME_COUNT):
            t = interval * (i + 1)
            frame_path = out_dir / f"frame_{i:02d}.jpg"
            cmd = [
                "ffmpeg", "-y", "-ss", str(t),
                "-i", str(video_path),
                "-frames:v", "1", "-q:v", "3",
                str(frame_path),
            ]
            try:
                subprocess.run(cmd, capture_output=True, timeout=10)
                if frame_path.exists():
                    frames.append(frame_path)
            except Exception:
                pass

        return frames

    async def _analyze_frames_with_llm(self, frames: list[Path]) -> str:
        client = AsyncOpenAI(api_key=self.api_key, base_url=self.base_url)
        content: list[dict] = []
        for frame in frames:
            b64 = base64.b64encode(frame.read_bytes()).decode()
            content.append({
                "type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{b64}"},
            })
        content.append({
            "type": "text",
            "text": (
                "以下是一段视频的关键帧截图（按时间顺序排列）。"
                "请根据这些截图中的字幕文字、屏幕文字、人物口型等线索，"
                "尽可能完整地还原该视频的口播文案/字幕内容。"
                "只输出文案正文，不要添加任何解释。"
            ),
        })
        response = await client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": content}],
            max_tokens=4000,
        )
        return response.choices[0].message.content or ""

    # ── LLM text inference (last resort) ─────────────────────────────────────

    async def _infer_from_text(self, share_text: str) -> str:
        client = AsyncOpenAI(api_key=self.api_key, base_url=self.base_url)
        response = await client.chat.completions.create(
            model=self.model,
            messages=[{
                "role": "user",
                "content": (
                    "以下是一个短视频的分享文本，包含视频标题和话题标签。"
                    "请根据视频标题、话题标签以及你对该类内容的了解，"
                    "尽可能还原该视频中的完整口播文案（即视频里说的话）。"
                    "只输出口播文案正文，不要添加任何解释或说明。\n\n"
                    f"分享文本：\n{share_text}"
                ),
            }],
            max_tokens=3000,
        )
        result = response.choices[0].message.content or ""
        logger.info(f"LLM inferred script from text ({len(result)} chars)")
        return result


# ── helpers ───────────────────────────────────────────────────────────────────

_URL_RE = re.compile(r'https?://\S+', re.IGNORECASE)
_DOUYIN_COMMAND_RE = re.compile(r"抖音\s+([A-Za-z0-9@._\-\s]{4,30}):/")


def _resolve_redirect(url: str) -> str:
    """Follow HTTP redirects and return the final URL."""
    try:
        with httpx.Client(
            follow_redirects=True, timeout=10,
            headers={"User-Agent": "Mozilla/5.0"}
        ) as client:
            r = client.get(url)
            return str(r.url)
    except Exception as e:
        logger.warning(f"Redirect resolve failed for {url}: {e}")
        return url


def _resolve_douyin_command_text(text: str) -> Optional[str]:
    """Resolve Douyin app command/share text to a web URL when possible."""
    for candidate in _douyin_short_url_candidates(text):
        resolved = _resolve_redirect(candidate)
        if resolved and not resolved.rstrip("/") == "https://www.douyin.com":
            return resolved

    tikhub_token = os.getenv("TIKHUB_API_KEY", "").strip()
    if not tikhub_token:
        return None

    try:
        with httpx.Client(timeout=20) as client:
            resp = client.get(
                "https://api.tikhub.io/api/v1/hybrid/video_data",
                params={"url": text},
                headers={"Authorization": f"Bearer {tikhub_token}"},
            )
            resp.raise_for_status()
            data = resp.json()
    except Exception as e:
        logger.warning(f"Douyin command resolver failed: {e}")
        return None

    return _find_best_video_url(data)


def _douyin_short_url_candidates(text: str) -> list[str]:
    m = _DOUYIN_COMMAND_RE.search(text or "")
    if not m:
        return []
    raw = m.group(1)
    variants = {
        raw.strip(),
        re.sub(r"\s+", "", raw),
        re.sub(r"[^A-Za-z0-9]", "", raw),
    }
    return [f"https://v.douyin.com/{v}/" for v in variants if v]


def _find_best_video_url(data) -> Optional[str]:
    urls: list[str] = []

    def visit(value):
        if isinstance(value, dict):
            for item in value.values():
                visit(item)
        elif isinstance(value, list):
            for item in value:
                visit(item)
        elif isinstance(value, str):
            for url in re.findall(r"https?://[^\s\"'<>]+", value):
                urls.append(url.rstrip(".,)"))

    visit(data)
    if not urls:
        return None

    priority_markers = (
        "douyin.com/video/",
        "douyin.com/share/video/",
        "aweme.snssdk.com",
        "douyinvod.com",
        "bytefcdn",
        "byteimg",
    )
    for marker in priority_markers:
        match = next((url for url in urls if marker in url), None)
        if match:
            return match
    return urls[0]


def _extract_url(text: str) -> Optional[str]:
    m = _URL_RE.search(text)
    return m.group(0).rstrip('.,)') if m else None


def _extract_douyin_id(text: str) -> Optional[str]:
    """Extract Douyin video ID from a URL or share text."""
    m = _DOUYIN_ID_RE.search(text or "")
    return m.group(1) if m else None


def _is_douyin_url(url: str) -> bool:
    return any(host in (url or "") for host in ("douyin.com", "iesdouyin.com", "amemv.com"))


def _ytdlp_base_cmd() -> list[str]:
    return [sys.executable, "-m", "yt_dlp"]


def _require_ytdlp():
    try:
        subprocess.run(_ytdlp_base_cmd() + ["--version"], capture_output=True, timeout=5)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        raise RuntimeError("yt-dlp 未安装，请执行: uv pip install yt-dlp")


def _parse_subtitle_file(path: Path) -> str:
    text = path.read_text(encoding="utf-8", errors="replace")
    if path.suffix == ".vtt":
        return _parse_vtt(text)
    return _parse_srt(text)


def _parse_vtt(vtt: str) -> str:
    lines = []
    for line in vtt.splitlines():
        line = line.strip()
        if not line or line.startswith("WEBVTT") or "-->" in line or re.match(r"^\d+$", line):
            continue
        line = re.sub(r"<[^>]+>", "", line)
        if line:
            lines.append(line)
    return _deduplicate_lines(lines)


def _parse_srt(srt: str) -> str:
    lines = []
    for line in srt.splitlines():
        line = line.strip()
        if not line or re.match(r"^\d+$", line) or "-->" in line:
            continue
        line = re.sub(r"<[^>]+>", "", line)
        if line:
            lines.append(line)
    return _deduplicate_lines(lines)


def _deduplicate_lines(lines: list[str]) -> str:
    deduped: list[str] = []
    for line in lines:
        if not deduped or line != deduped[-1]:
            deduped.append(line)
    return "\n".join(deduped)
