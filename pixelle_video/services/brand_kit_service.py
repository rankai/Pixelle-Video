"""Persistent brand kit library for desktop IP broadcast workflows."""

import json
import threading
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from loguru import logger

from pixelle_video.services.upload_security import atomic_write_json, safe_library_child
from pixelle_video.utils.os_util import get_data_path


@dataclass
class BrandKitInfo:
    brand_id: str
    brand_name: str
    created_at: str
    logo_filename: str = ""
    primary_color: str = "#1f6feb"
    secondary_color: str = "#0f766e"
    font_family: str = ""
    default_bgm_path: str = ""
    default_subtitle_style: str = ""
    ending_card_text: str = ""
    store_address: str = ""
    phone: str = ""
    coupon_phrase: str = ""

    def logo_path(self) -> str:
        if not self.logo_filename:
            return ""
        return get_data_path("brand_kits", self.logo_filename)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["logo_path"] = self.logo_path()
        return data


class BrandKitService:
    def __init__(self):
        self._brand_dir = Path(get_data_path("brand_kits"))
        self._manifest_path = self._brand_dir / "brand_kits.json"
        self._brand_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def list_brand_kits(self) -> list[BrandKitInfo]:
        with self._lock:
            raw = self._load_manifest()
            result = []
            for item in raw:
                item = _normalize_brand_payload(item)
                try:
                    result.append(BrandKitInfo(**item))
                except TypeError:
                    continue
            if len(result) != len(raw):
                self._save_manifest([asdict(item) for item in result])
        return result

    def create_brand_kit(self, values: dict[str, Any]) -> BrandKitInfo:
        info = BrandKitInfo(
            brand_id=uuid.uuid4().hex[:12],
            brand_name=str(values.get("brand_name") or "未命名品牌"),
            created_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            primary_color=str(values.get("primary_color") or "#1f6feb"),
            secondary_color=str(values.get("secondary_color") or "#0f766e"),
            font_family=str(values.get("font_family") or ""),
            default_bgm_path=str(values.get("default_bgm_path") or ""),
            default_subtitle_style=str(values.get("default_subtitle_style") or ""),
            ending_card_text=str(values.get("ending_card_text") or ""),
            store_address=str(values.get("store_address") or ""),
            phone=str(values.get("phone") or ""),
            coupon_phrase=str(values.get("coupon_phrase") or ""),
        )
        with self._lock:
            kits = self._load_manifest()
            kits.append(asdict(info))
            self._save_manifest(kits)
        return info

    def update_brand_kit(self, brand_id: str, values: dict[str, Any]) -> BrandKitInfo | None:
        with self._lock:
            kits = self._load_manifest()
            for item in kits:
                if item.get("brand_id") == brand_id:
                    item.update({key: value for key, value in values.items() if value is not None})
                    item.update(_normalize_brand_payload(item))
                    self._save_manifest(kits)
                    return BrandKitInfo(**item)
        return None

    def delete_brand_kit(self, brand_id: str) -> bool:
        with self._lock:
            kits = self._load_manifest()
            updated = [item for item in kits if item.get("brand_id") != brand_id]
            if len(updated) == len(kits):
                return False
            removed = next(item for item in kits if item.get("brand_id") == brand_id)
            self._save_manifest(updated)
        logo_filename = removed.get("logo_filename", "")
        if logo_filename:
            logo_path = safe_library_child(self._brand_dir, logo_filename)
            if logo_path:
                logo_path.unlink(missing_ok=True)
        return True

    def _load_manifest(self) -> list[dict[str, Any]]:
        if not self._manifest_path.exists():
            return []
        try:
            return json.loads(self._manifest_path.read_text(encoding="utf-8"))
        except Exception as e:
            logger.warning(f"Failed to load brand kits manifest: {e}")
            return []

    def _save_manifest(self, kits: list[dict[str, Any]]) -> None:
        atomic_write_json(self._manifest_path, kits)


def _normalize_brand_payload(item: dict[str, Any]) -> dict[str, Any]:
    defaults = {
        "brand_id": uuid.uuid4().hex[:12],
        "brand_name": "未命名品牌",
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "logo_filename": "",
        "primary_color": "#1f6feb",
        "secondary_color": "#0f766e",
        "font_family": "",
        "default_bgm_path": "",
        "default_subtitle_style": "",
        "ending_card_text": "",
        "store_address": "",
        "phone": "",
        "coupon_phrase": "",
    }
    return {**defaults, **item}
