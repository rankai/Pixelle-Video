"""Portrait management service — persistent storage of digital human portrait images"""

import json
import os
import threading
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

from loguru import logger

from pixelle_video.services.upload_security import (
    atomic_write_json,
    normalize_extension,
    safe_library_child,
    validate_file_size,
)
from pixelle_video.utils.os_util import get_data_path

SUPPORTED_PORTRAIT_EXTENSIONS = {"jpg", "jpeg", "png", "webp", "mp4", "mov", "webm"}
MAX_PORTRAIT_IMAGE_BYTES = 20 * 1024 * 1024
MAX_PORTRAIT_VIDEO_BYTES = 1024 * 1024 * 1024


@dataclass
class PortraitInfo:
    portrait_id: str
    name: str
    filename: str
    created_at: str
    media_type: str = "image"

    def asset_path(self) -> str:
        return get_data_path("portraits", self.filename)

    def image_path(self) -> str:
        """Backward-compatible alias for older image-only call sites."""
        return self.asset_path()

    def exists(self) -> bool:
        return os.path.exists(self.asset_path())

    def is_video(self) -> bool:
        return self.media_type == "video"


class PortraitService:
    """Manages a persistent library of portrait images in data/portraits/"""

    def __init__(self):
        self._portraits_dir = Path(get_data_path("portraits"))
        self._manifest_path = self._portraits_dir / "portraits.json"
        self._portraits_dir.mkdir(parents=True, exist_ok=True)
        # Serialise all manifest read-modify-write operations so concurrent
        # Streamlit sessions sharing the same process don't corrupt the file.
        self._lock = threading.Lock()

    def _load_manifest(self) -> list[dict]:
        if not self._manifest_path.exists():
            return []
        try:
            return json.loads(self._manifest_path.read_text(encoding="utf-8"))
        except Exception as e:
            logger.warning(f"Failed to load portraits manifest: {e}")
            return []

    def _save_manifest(self, portraits: list[dict]):
        atomic_write_json(self._manifest_path, portraits)

    def list_portraits(self) -> list[PortraitInfo]:
        with self._lock:
            raw = self._load_manifest()
            result = []
            for item in raw:
                item.setdefault("media_type", _infer_media_type(item.get("filename", "")))
                info = PortraitInfo(**item)
                if info.exists():
                    result.append(info)
            if len(result) != len(raw):
                self._save_manifest([asdict(p) for p in result])
        return result

    def save_portrait(self, name: str, image_bytes: bytes, ext: str) -> PortraitInfo:
        portrait_id = uuid.uuid4().hex[:12]
        clean_ext = normalize_extension(ext, SUPPORTED_PORTRAIT_EXTENSIONS)
        filename = f"{portrait_id}.{clean_ext}"
        dest = self._portraits_dir / filename
        media_type = _infer_media_type(filename)
        max_bytes = MAX_PORTRAIT_VIDEO_BYTES if media_type == "video" else MAX_PORTRAIT_IMAGE_BYTES
        validate_file_size(image_bytes, max_bytes, "Portrait asset")

        info = PortraitInfo(
            portrait_id=portrait_id,
            name=name,
            filename=filename,
            created_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            media_type=media_type,
        )

        # Write image to disk first.
        dest.write_bytes(image_bytes)

        # Update manifest under lock; roll back the image file if this fails
        # so we never leave an orphaned file with no manifest entry.
        try:
            with self._lock:
                portraits = self._load_manifest()
                portraits.append(asdict(info))
                self._save_manifest(portraits)
        except Exception:
            dest.unlink(missing_ok=True)
            raise

        logger.info(f"Portrait saved: {name} ({filename})")
        return info

    def delete_portrait(self, portrait_id: str) -> bool:
        with self._lock:
            portraits = self._load_manifest()
            updated = [p for p in portraits if p["portrait_id"] != portrait_id]
            if len(updated) == len(portraits):
                return False
            removed = next(p for p in portraits if p["portrait_id"] == portrait_id)
            self._save_manifest(updated)

        # Delete the image file outside the lock — worst case it's an orphan
        # (safe: list_portraits filters missing files on next load).
        image_path = safe_library_child(self._portraits_dir, removed.get("filename", ""))
        if image_path and image_path.exists():
            image_path.unlink()
        logger.info(f"Portrait deleted: {portrait_id}")
        return True

    def get_portrait_path(self, portrait_id: str) -> str | None:
        with self._lock:
            manifest = self._load_manifest()
        for item in manifest:
            if item["portrait_id"] == portrait_id:
                path = safe_library_child(self._portraits_dir, item.get("filename", ""))
                if not path:
                    return None
                return str(path) if path.exists() else None
        return None

    def get_portrait_media_type(self, portrait_id: str) -> str:
        with self._lock:
            manifest = self._load_manifest()
        for item in manifest:
            if item["portrait_id"] == portrait_id:
                return item.get("media_type") or _infer_media_type(item.get("filename", ""))
        return "image"


def _infer_media_type(filename: str) -> str:
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext in {"mp4", "mov", "webm"}:
        return "video"
    return "image"
