"""Desktop runtime, configuration, and diagnostics endpoints."""

import os
import shutil
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from api.desktop_security import is_desktop_mode
from pixelle_video.config import config_manager

router = APIRouter(prefix="/desktop", tags=["Desktop"])
REDACTED_SECRET = "***redacted***"


class DesktopConfigPatch(BaseModel):
    llm: dict | None = None
    runninghub: dict | None = None
    output_dir: str | None = None


@router.get("/health")
async def desktop_health():
    return {"status": "healthy", "service": "Pixelle Desktop Sidecar"}


@router.get("/diagnostics")
async def diagnostics():
    return {
        "ffmpeg": {"available": bool(shutil.which("ffmpeg"))},
        "playwright": {"available": _playwright_available()},
        "yt_dlp": {"available": _module_available("yt_dlp")},
        "config": {
            "path_present": config_manager.config_path.exists(),
            "llm_configured": config_manager.config.is_llm_configured(),
            "runninghub_configured": bool(config_manager.config.comfyui.runninghub_api_key),
            "privacy": {"local_only": True, "raw_path_redacted": True, "secrets_redacted": True},
        },
        "checks": _diagnostic_checks(),
    }


@router.get("/config")
async def get_desktop_config():
    cfg = config_manager.config
    return {
        "llm": {
            "base_url": cfg.llm.base_url,
            "api_key": _redact_secret(cfg.llm.api_key),
            "model": cfg.llm.model,
        },
        "runninghub": {
            "api_key": _redact_secret(cfg.comfyui.runninghub_api_key or ""),
            "instance_type": cfg.comfyui.runninghub_instance_type or "",
        },
        "output_dir": str(Path("output").resolve()),
    }


@router.patch("/config")
async def update_desktop_config(patch: DesktopConfigPatch):
    if not is_desktop_mode():
        raise HTTPException(status_code=403, detail="配置写入仅支持桌面端本地运行。")

    updates = {}
    if patch.llm:
        updates["llm"] = {
            key: value
            for key, value in patch.llm.items()
            if key in {"base_url", "api_key", "model"}
            and not (key == "api_key" and _is_redacted_secret(value))
        }
    if patch.runninghub:
        comfy_updates = {}
        if "api_key" in patch.runninghub and not _is_redacted_secret(patch.runninghub["api_key"]):
            comfy_updates["runninghub_api_key"] = patch.runninghub["api_key"]
        if "instance_type" in patch.runninghub:
            instance_type = patch.runninghub["instance_type"] or None
            comfy_updates["runninghub_instance_type"] = instance_type
        if comfy_updates:
            updates["comfyui"] = comfy_updates
    if updates:
        config_manager.update(updates)
        config_manager.save()
    return await get_desktop_config()


@router.post("/config/check")
async def check_desktop_config(patch: DesktopConfigPatch):
    if not is_desktop_mode():
        raise HTTPException(status_code=403, detail="配置检查仅支持桌面端本地运行。")

    checks = _config_draft_checks(patch)
    return {
        "ok": all(item["status"] != "missing" for item in checks),
        "checks": checks,
    }


def _check_item(check_id: str, label: str, status: str, message: str) -> dict:
    return {
        "id": check_id,
        "label": label,
        "status": status,
        "message": message,
    }


def _diagnostic_checks() -> list[dict]:
    cfg = config_manager.config
    output_dir = Path("output").resolve()
    ffmpeg_available = bool(shutil.which("ffmpeg"))
    playwright_available = _playwright_available()
    yt_dlp_available = _module_available("yt_dlp")
    output_writable = output_dir.exists() and os.access(output_dir, os.W_OK)
    llm_configured = cfg.is_llm_configured()
    runninghub_configured = bool(cfg.comfyui.runninghub_api_key)
    return [
        _check_item(
            "ffmpeg",
            "ffmpeg",
            "ok" if ffmpeg_available else "missing",
            "ffmpeg 可用。" if ffmpeg_available else "未检测到 ffmpeg，视频合成和转码可能失败。请先安装 ffmpeg 后重试。",
        ),
        _check_item(
            "playwright",
            "Playwright",
            "ok" if playwright_available else "missing",
            "Playwright 可用。" if playwright_available else "未检测到 Playwright，抖音草稿助手可能无法打开浏览器。请安装浏览器依赖后重试。",
        ),
        _check_item(
            "yt_dlp",
            "yt-dlp",
            "ok" if yt_dlp_available else "missing",
            "yt-dlp 可用。" if yt_dlp_available else "未检测到 yt-dlp，视频链接解析可能失败。",
        ),
        _check_item(
            "output_dir",
            "输出目录",
            "ok" if output_writable else "missing",
            "输出目录可写。" if output_writable else "输出目录不可写，请检查本地目录权限。",
        ),
        _check_item(
            "llm_config",
            "LLM 配置",
            "ok" if llm_configured else "missing",
            "LLM 配置已保存。" if llm_configured else "缺少 LLM 配置。请到“配置 > LLM 设置”填写 API Key、Base URL 和模型名称。",
        ),
        _check_item(
            "runninghub_config",
            "RunningHub 配置",
            "ok" if runninghub_configured else "missing",
            "RunningHub 配置已保存。" if runninghub_configured else "缺少 RunningHub API Key。请到“配置 > 云端生成”填写 API Key，否则无法生成数字人视频。",
        ),
    ]


def _config_draft_checks(patch: DesktopConfigPatch) -> list[dict]:
    cfg = config_manager.config
    llm = patch.llm or {}
    runninghub = patch.runninghub or {}
    llm_api_key = _effective_secret(llm.get("api_key"), cfg.llm.api_key)
    llm_base_url = str(llm.get("base_url") if llm.get("base_url") is not None else cfg.llm.base_url).strip()
    llm_model = str(llm.get("model") if llm.get("model") is not None else cfg.llm.model).strip()
    runninghub_api_key = _effective_secret(
        runninghub.get("api_key"),
        cfg.comfyui.runninghub_api_key or "",
    )

    checks = []
    if llm_api_key and llm_base_url and llm_model:
        checks.append(
            _check_item(
                "llm",
                "LLM 配置",
                "warning",
                "LLM 配置项已填写，尚未验证服务账号是否可用。生成失败时请检查 Key、模型和余额。",
            )
        )
    else:
        checks.append(
            _check_item(
                "llm",
                "LLM 配置",
                "missing",
                "缺少 LLM API Key、Base URL 或模型名称。请到“配置 > LLM 设置”填写完整。",
            )
        )
    if runninghub_api_key:
        checks.append(
            _check_item(
                "runninghub",
                "RunningHub 配置",
                "warning",
                "RunningHub API Key 已填写，尚未验证服务账号是否可用。生成失败时请检查 Key、额度和工作流配置。",
            )
        )
    else:
        checks.append(
            _check_item(
                "runninghub",
                "RunningHub 配置",
                "missing",
                "缺少 RunningHub API Key。请到“配置 > 云端生成”填写 API Key，否则无法生成数字人视频。",
            )
        )
    return checks


def _effective_secret(value: object, existing: str) -> str:
    if _is_redacted_secret(value):
        return existing.strip()
    if value is None:
        return existing.strip()
    return str(value).strip()


def _redact_secret(value: str) -> str:
    return REDACTED_SECRET if value else ""


def _is_redacted_secret(value: object) -> bool:
    return isinstance(value, str) and value.strip() == REDACTED_SECRET


def _module_available(module_name: str) -> bool:
    try:
        __import__(module_name)
        return True
    except Exception:
        return False


def _playwright_available() -> bool:
    try:
        from playwright.sync_api import sync_playwright  # noqa: F401

        return True
    except Exception:
        return False
