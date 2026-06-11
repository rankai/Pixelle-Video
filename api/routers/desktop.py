"""Desktop runtime, configuration, and diagnostics endpoints."""

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
            "path": str(config_manager.config_path),
            "exists": config_manager.config_path.exists(),
            "llm_configured": config_manager.config.is_llm_configured(),
            "runninghub_configured": bool(config_manager.config.comfyui.runninghub_api_key),
        },
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
