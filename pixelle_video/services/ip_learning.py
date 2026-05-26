"""IP profile learning helpers for extracting recent video scripts."""

import asyncio
import json
import re
import sys
from dataclasses import dataclass
from typing import Any
from urllib.parse import parse_qs, urlparse

from loguru import logger

from pixelle_video.services.script_extractor import VideoScriptExtractor
from pixelle_video.services.ytdlp_cookies import (
    is_cookie_unavailable_error,
    ytdlp_cookie_options,
)

_LOGIN_BLOCK_PATTERNS = (
    "login",
    "log in",
    "captcha",
    "verify",
    "verification",
    "扫码",
    "登录",
    "验证码",
    "安全验证",
    "请先登录",
)
_URL_PATTERN = re.compile(r"https?://[^\s，。]+")
_DOUYIN_VIDEO_ID_PATTERN = re.compile(
    r"(?:douyin\.com/video/|douyin\.com/share/video/|/video/)(\d{15,20})"
)


class ProfileFetchBlocked(RuntimeError):
    """Raised when a profile page appears to require login or verification."""


@dataclass
class IPVideoScriptResult:
    source: str
    script: str = ""
    error: str = ""
    ok: bool = False


def _is_login_blocked_message(message: str) -> bool:
    lower = message.lower()
    return any(pattern in lower for pattern in _LOGIN_BLOCK_PATTERNS)


def parse_manual_video_inputs(text: str, limit: int = 5) -> list[str]:
    blocks = [block.strip() for block in re.split(r"\n\s*\n|\n", text) if block.strip()]
    return blocks[:limit]


def _extract_first_url(text: str) -> str:
    match = _URL_PATTERN.search(text)
    return match.group(0).rstrip("，。,.") if match else text.strip()


def _is_unsupported_url_error(message: str) -> bool:
    lower = message.lower()
    return "unsupported url" in lower or "unsupported url:" in lower


def _is_douyin_profile_url(url: str) -> bool:
    parsed = urlparse(url)
    return "douyin.com" in parsed.netloc and parsed.path.startswith("/user/")


def _extract_douyin_profile_video_urls_from_text(text: str, limit: int = 5) -> list[str]:
    ids: list[str] = []
    seen: set[str] = set()

    for url_match in _URL_PATTERN.finditer(text):
        parsed = urlparse(url_match.group(0).rstrip("，。,."))
        for vid in parse_qs(parsed.query).get("vid", []):
            if vid.isdigit() and 15 <= len(vid) <= 20 and vid not in seen:
                seen.add(vid)
                ids.append(vid)
                if len(ids) >= limit:
                    break

    for match in _DOUYIN_VIDEO_ID_PATTERN.finditer(text):
        video_id = match.group(1)
        if video_id in seen:
            continue
        seen.add(video_id)
        ids.append(video_id)
        if len(ids) >= limit:
            break

    return [f"https://www.douyin.com/video/{video_id}" for video_id in ids[:limit]]


async def _fetch_douyin_profile_video_urls(profile_url: str, limit: int = 5) -> list[str]:
    urls = _extract_douyin_profile_video_urls_from_text(profile_url, limit=limit)
    if len(urls) >= limit:
        return urls

    try:
        from playwright.async_api import TimeoutError as PlaywrightTimeoutError
        from playwright.async_api import async_playwright
    except Exception as e:
        logger.warning(f"Playwright is unavailable for Douyin profile fetch: {e}")
        return urls

    browser = None
    playwright = None
    try:
        playwright = await async_playwright().start()
        browser = await playwright.chromium.launch(headless=True)
        page = await browser.new_page(
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 900},
        )
        await page.goto(profile_url, wait_until="domcontentloaded", timeout=30000)
        for _ in range(3):
            await page.mouse.wheel(0, 1200)
            await page.wait_for_timeout(1200)

        html = await page.content()
        page_text = await page.locator("body").inner_text(timeout=3000)
        urls = _merge_url_lists(
            urls,
            _extract_douyin_profile_video_urls_from_text(html, limit=limit),
            limit,
        )
        if urls:
            return urls
        if _is_login_blocked_message(page_text):
            raise ProfileFetchBlocked(_headless_profile_blocked_message())
    except ProfileFetchBlocked:
        raise
    except PlaywrightTimeoutError:
        logger.warning("Douyin profile Playwright fetch timed out")
    except Exception as e:
        logger.warning(f"Douyin profile Playwright fetch failed: {e}")
    finally:
        if browser:
            await browser.close()
        if playwright:
            await playwright.stop()

    return urls


def _merge_url_lists(first: list[str], second: list[str], limit: int) -> list[str]:
    merged: list[str] = []
    seen: set[str] = set()
    for url in [*first, *second]:
        if url in seen:
            continue
        seen.add(url)
        merged.append(url)
        if len(merged) >= limit:
            break
    return merged


def _extract_profile_entries(payload: dict[str, Any], limit: int = 5) -> list[str]:
    entries = payload.get("entries") or []
    urls: list[str] = []
    seen: set[str] = set()
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        url = entry.get("webpage_url") or entry.get("url")
        if not url and entry.get("id"):
            url = f"https://www.douyin.com/video/{entry['id']}"
        if isinstance(url, str) and url.startswith("/"):
            url = f"https://www.douyin.com{url}"
        if not isinstance(url, str) or not url:
            continue
        if url in seen:
            continue
        seen.add(url)
        urls.append(url)
        if len(urls) >= limit:
            break
    return urls


async def fetch_latest_video_urls_from_profile(profile_url: str, limit: int = 5) -> list[str]:
    """Fetch recent video URLs from an IP homepage using yt-dlp flat playlist mode."""
    if not profile_url.strip():
        raise ValueError("请先输入 IP 主页链接")
    profile_target = _extract_first_url(profile_url)

    if _is_douyin_profile_url(profile_target):
        urls = await _fetch_douyin_profile_video_urls(profile_target, limit=limit)
        if urls:
            return urls

    last_error = ""
    skipped_cookie_errors: list[str] = []
    for cookie_args in ytdlp_cookie_options():
        cmd = [
            sys.executable,
            "-m",
            "yt_dlp",
            "--flat-playlist",
            "--dump-single-json",
            "--playlist-end",
            str(limit),
            *cookie_args,
            profile_target,
        ]
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=120)
            stderr_text = stderr.decode(errors="replace")
            stdout_text = stdout.decode(errors="replace")
            if proc.returncode != 0:
                error_text = stderr_text[:800]
                if _is_login_blocked_message(error_text):
                    raise ProfileFetchBlocked(_blocked_message())
                if is_cookie_unavailable_error(error_text):
                    skipped_cookie_errors.append(error_text)
                    logger.debug(f"Skipping unavailable browser cookies: {error_text}")
                    continue
                if _is_unsupported_url_error(error_text) and _is_douyin_profile_url(profile_target):
                    urls = await _fetch_douyin_profile_video_urls(profile_target, limit=limit)
                    if urls:
                        return urls
                last_error = error_text
                continue

            payload = json.loads(stdout_text)
            urls = _extract_profile_entries(payload, limit=limit)
            if urls:
                return urls
            last_error = stderr_text or stdout_text[:800]
        except ProfileFetchBlocked:
            raise
        except asyncio.TimeoutError:
            last_error = "主页抓取超时"
        except Exception as e:
            last_error = str(e)
            logger.warning(f"Profile fetch attempt failed: {e}")

    if _is_login_blocked_message(last_error):
        raise ProfileFetchBlocked(_blocked_message())
    if not last_error and skipped_cookie_errors:
        raise ValueError(_no_cookie_result_message())
    raise ValueError(f"未能从该 IP 主页抓取视频链接：{last_error or '无视频结果'}")


async def extract_many_video_scripts(
    extractor: VideoScriptExtractor,
    video_inputs: list[str],
    limit: int = 5,
) -> list[IPVideoScriptResult]:
    results: list[IPVideoScriptResult] = []
    for source in video_inputs[:limit]:
        try:
            script = (await extractor.extract(source)).strip()
            if script:
                results.append(IPVideoScriptResult(source=source, script=script, ok=True))
            else:
                results.append(IPVideoScriptResult(source=source, error="未提取到文案", ok=False))
        except Exception as e:
            results.append(IPVideoScriptResult(source=source, error=str(e), ok=False))
    return results


def _blocked_message() -> str:
    return (
        "当前 IP 主页需要登录或验证。请先在本机浏览器登录抖音后重试；"
        "仍失败时，可在下方手动粘贴最近 5 条视频链接。"
    )


def _headless_profile_blocked_message() -> str:
    return (
        "当前 IP 主页在自动页面抓取时出现登录或验证拦截。"
        "请在下方手动粘贴最近 5 条视频链接，系统会继续逐条提取口播文案。"
    )


def _no_cookie_result_message() -> str:
    return (
        "未能从该 IP 主页抓取视频链接：没有找到可用的浏览器 Cookie。"
        "已尝试 Chrome、Edge、Safari、Firefox、Brave、Vivaldi、Opera、Chromium、Whale "
        "以及 360 极速版、QQ 浏览器、搜狗浏览器的常见数据目录。"
        "请先在其中一个浏览器登录抖音后重试，或手动粘贴最近 5 条视频链接。"
    )
