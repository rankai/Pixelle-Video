"""Persistent reusable image library for product, store and campaign visuals."""

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

SUPPORTED_IMAGE_ASSET_EXTENSIONS = {"jpg", "jpeg", "png", "webp"}
MAX_IMAGE_ASSET_BYTES = 30 * 1024 * 1024


@dataclass
class ImageAssetInfo:
    asset_id: str
    name: str
    filename: str
    created_at: str
    size: int = 0

    def asset_path(self) -> str:
        return get_data_path("image_assets", self.filename)

    def exists(self) -> bool:
        return os.path.exists(self.asset_path())


class ImageAssetService:
    """Manage reusable company imagery under data/image_assets/."""

    def __init__(self):
        self._assets_dir = Path(get_data_path("image_assets"))
        self._manifest_path = self._assets_dir / "image_assets.json"
        self._assets_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def _load_manifest(self) -> list[dict]:
        if not self._manifest_path.exists():
            return []
        try:
            return json.loads(self._manifest_path.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning(f"Failed to load image assets manifest: {exc}")
            return []

    def _save_manifest(self, assets: list[dict]) -> None:
        atomic_write_json(self._manifest_path, assets)

    def list_assets(self) -> list[ImageAssetInfo]:
        with self._lock:
            raw = self._load_manifest()
            result: list[ImageAssetInfo] = []
            for item in raw:
                item.setdefault("size", 0)
                try:
                    info = ImageAssetInfo(**item)
                except TypeError:
                    continue
                if info.exists():
                    result.append(info)
            if len(result) != len(raw):
                self._save_manifest([asdict(item) for item in result])
        return result

    def save_asset(self, name: str, image_bytes: bytes, ext: str) -> ImageAssetInfo:
        clean_ext = normalize_extension(ext, SUPPORTED_IMAGE_ASSET_EXTENSIONS)
        validate_file_size(image_bytes, MAX_IMAGE_ASSET_BYTES, "Image asset")
        asset_id = uuid.uuid4().hex[:12]
        filename = f"{asset_id}.{clean_ext}"
        destination = self._assets_dir / filename
        destination.write_bytes(image_bytes)
        info = ImageAssetInfo(
            asset_id=asset_id,
            name=name,
            filename=filename,
            created_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            size=len(image_bytes),
        )
        try:
            with self._lock:
                assets = self._load_manifest()
                assets.append(asdict(info))
                self._save_manifest(assets)
        except Exception:
            destination.unlink(missing_ok=True)
            raise
        logger.info(f"Image asset saved: {name} ({filename})")
        return info

    def delete_asset(self, asset_id: str) -> bool:
        with self._lock:
            assets = self._load_manifest()
            updated = [item for item in assets if item.get("asset_id") != asset_id]
            if len(updated) == len(assets):
                return False
            removed = next(item for item in assets if item.get("asset_id") == asset_id)
            self._save_manifest(updated)
        path = safe_library_child(self._assets_dir, removed.get("filename", ""))
        if path:
            path.unlink(missing_ok=True)
        return True

    def get_asset_path(self, asset_id: str) -> str | None:
        with self._lock:
            assets = self._load_manifest()
        for item in assets:
            if item.get("asset_id") == asset_id:
                path = safe_library_child(self._assets_dir, item.get("filename", ""))
                return str(path) if path and path.exists() else None
        return None
