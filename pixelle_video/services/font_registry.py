"""Stable renderer font identities shared by template and brand contracts."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Any

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_BUNDLED_FONT = "NotoSansCJKsc-Bold.otf"
_BUNDLED_FONT_SHA256 = "b5f0d1a190a7f9b43c310a8850630af12553df32c4c050543f9059732d9b4c0a"

REGISTERED_FONTS: dict[str, dict[str, Any]] = {
    "noto-sans-sc-bold": {
        "font_id": "noto-sans-sc-bold",
        "family": "Noto Sans CJK SC",
        "weight": 700,
        "style": "normal",
        "font_sha256": _BUNDLED_FONT_SHA256,
        "filename": _BUNDLED_FONT,
    },
}


def _font_candidates(filename: str) -> list[Path]:
    configured = str(os.getenv("PIXELLE_VIDEO_FONT_DIR") or "").strip()
    candidates = [
        Path(configured) / filename if configured else None,
        _PROJECT_ROOT / "assets" / "fonts" / filename,
        Path.cwd() / "assets" / "fonts" / filename,
    ]
    return [candidate for candidate in candidates if candidate is not None]


def resolve_font_path(font_id: str) -> Path | None:
    identity = REGISTERED_FONTS.get(font_id)
    if not identity:
        return None
    return next((candidate.resolve() for candidate in _font_candidates(str(identity["filename"])) if candidate.is_file()), None)


def resolve_registered_font(font_id: str) -> dict[str, Any] | None:
    value = REGISTERED_FONTS.get(font_id)
    if not value:
        return None
    path = resolve_font_path(font_id)
    return {**value, "font_path": str(path) if path else None}


def validate_registered_font(font_id: str, family: str, weight: int, style: str, font_sha256: str) -> None:
    identity = resolve_registered_font(font_id)
    if not identity:
        raise ValueError(f"font_id_not_registered:{font_id}")
    font_path = identity.get("font_path")
    if not font_path:
        raise ValueError(f"font_artifact_missing:{font_id}")
    digest = hashlib.sha256(Path(str(font_path)).read_bytes()).hexdigest()
    if (
        family != identity["family"]
        or int(weight) != int(identity["weight"])
        or style != identity["style"]
        or font_sha256 != identity["font_sha256"]
        or digest != identity["font_sha256"]
    ):
        raise ValueError(f"font_identity_mismatch:{font_id}")
