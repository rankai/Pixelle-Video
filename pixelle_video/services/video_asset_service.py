"""Persistent video asset library for IP broadcast overlay clips."""

import json
import os
import subprocess
import threading
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable

from loguru import logger

from pixelle_video.services.subtitle_service import extract_first_frame
from pixelle_video.services.upload_security import (
    atomic_write_json,
    normalize_extension,
    safe_library_child,
    validate_file_size,
)
from pixelle_video.utils.os_util import get_data_path

SUPPORTED_VIDEO_ASSET_EXTENSIONS = {"mp4", "mov", "webm"}
MAX_VIDEO_ASSET_BYTES = 1024 * 1024 * 1024


@dataclass
class VideoAssetInfo:
    asset_id: str
    name: str
    filename: str
    created_at: str
    duration: float = 0.0
    size: int = 0
    thumbnail_filename: str = ""

    def asset_path(self) -> str:
        return get_data_path("video_assets", "overlay", self.filename)

    def thumbnail_path(self) -> str:
        if not self.thumbnail_filename:
            return ""
        return get_data_path("video_assets", "overlay", self.thumbnail_filename)

    def exists(self) -> bool:
        return os.path.exists(self.asset_path())

    def thumbnail_exists(self) -> bool:
        thumbnail_path = self.thumbnail_path()
        return bool(thumbnail_path and os.path.exists(thumbnail_path))


class VideoAssetService:
    """Manages reusable overlay video assets in data/video_assets/overlay/."""

    def __init__(self, cover_extractor: Callable[[str, str], str] | None = None):
        self._assets_dir = Path(get_data_path("video_assets", "overlay"))
        self._manifest_path = self._assets_dir / "video_assets.json"
        self._assets_dir.mkdir(parents=True, exist_ok=True)
        self._cover_extractor = cover_extractor or extract_first_frame
        self._lock = threading.Lock()

    def _load_manifest(self) -> list[dict]:
        if not self._manifest_path.exists():
            return []
        try:
            return json.loads(self._manifest_path.read_text(encoding="utf-8"))
        except Exception as e:
            logger.warning(f"Failed to load video assets manifest: {e}")
            return []

    def _save_manifest(self, assets: list[dict]) -> None:
        atomic_write_json(self._manifest_path, assets)

    def list_assets(self) -> list[VideoAssetInfo]:
        with self._lock:
            raw = self._load_manifest()
            result = []
            for item in raw:
                item.setdefault("duration", 0.0)
                item.setdefault("size", 0)
                item.setdefault("thumbnail_filename", "")
                try:
                    info = VideoAssetInfo(**item)
                except TypeError:
                    continue
                if info.exists():
                    result.append(info)
            if len(result) != len(raw):
                self._save_manifest([asdict(item) for item in result])
        return result

    def save_asset(self, name: str, video_bytes: bytes, ext: str) -> VideoAssetInfo:
        clean_ext = normalize_extension(ext, SUPPORTED_VIDEO_ASSET_EXTENSIONS)
        validate_file_size(video_bytes, MAX_VIDEO_ASSET_BYTES, "Video asset")

        asset_id = uuid.uuid4().hex[:12]
        filename = f"{asset_id}.{clean_ext}"
        thumbnail_filename = f"{asset_id}_cover.jpg"
        dest = self._assets_dir / filename
        thumbnail_path = self._assets_dir / thumbnail_filename
        dest.write_bytes(video_bytes)

        thumbnail = ""
        try:
            self._cover_extractor(str(dest), str(thumbnail_path))
            if thumbnail_path.exists():
                thumbnail = thumbnail_filename
        except Exception as e:
            logger.warning(f"Failed to extract video asset cover: {e}")

        info = VideoAssetInfo(
            asset_id=asset_id,
            name=name,
            filename=filename,
            created_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            duration=_probe_duration_safely(str(dest)),
            size=len(video_bytes),
            thumbnail_filename=thumbnail,
        )

        try:
            with self._lock:
                assets = self._load_manifest()
                assets.append(asdict(info))
                self._save_manifest(assets)
        except Exception:
            dest.unlink(missing_ok=True)
            thumbnail_path.unlink(missing_ok=True)
            raise

        logger.info(f"Video asset saved: {name} ({filename})")
        return info

    def delete_asset(self, asset_id: str) -> bool:
        with self._lock:
            assets = self._load_manifest()
            updated = [item for item in assets if item["asset_id"] != asset_id]
            if len(updated) == len(assets):
                return False
            removed = next(item for item in assets if item["asset_id"] == asset_id)
            self._save_manifest(updated)

        asset_path = safe_library_child(self._assets_dir, removed.get("filename", ""))
        if asset_path:
            asset_path.unlink(missing_ok=True)
        thumbnail = removed.get("thumbnail_filename")
        if thumbnail:
            thumbnail_path = safe_library_child(self._assets_dir, thumbnail)
            if thumbnail_path:
                thumbnail_path.unlink(missing_ok=True)
        logger.info(f"Video asset deleted: {asset_id}")
        return True

    def get_asset_path(self, asset_id: str) -> str | None:
        with self._lock:
            manifest = self._load_manifest()
        for item in manifest:
            if item["asset_id"] == asset_id:
                path = safe_library_child(self._assets_dir, item.get("filename", ""))
                if not path:
                    return None
                return str(path) if path.exists() else None
        return None


def _probe_duration_safely(media_path: str) -> float:
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        media_path,
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return round(float(result.stdout.strip()), 2)
    except Exception:
        return 0.0
