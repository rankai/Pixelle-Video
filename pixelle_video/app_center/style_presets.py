"""Trusted, code-shipped style presets for application workbench text apps."""

from __future__ import annotations

import json
from copy import deepcopy
from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class StylePresetError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


class StylePreset(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: int = Field(default=1, ge=1, le=1)
    style_id: str = Field(pattern=r"^[a-z][a-z0-9-]*\.[a-z][a-z0-9_-]*$")
    version: int = Field(ge=1)
    family: str
    name: str = Field(min_length=1, max_length=40)
    description: str = Field(min_length=1, max_length=200)
    example: str = Field(min_length=1, max_length=500)
    prompt_rules: list[str] = Field(min_length=1, max_length=30)
    forbidden_patterns: list[str] = Field(max_length=50)
    supported_apps: list[str] = Field(min_length=1)
    status: str

    def public_projection(self) -> dict[str, Any]:
        return {
            "style_id": self.style_id,
            "version": self.version,
            "family": self.family,
            "name": self.name,
            "description": self.description,
            "example": self.example,
        }


def _registry_path() -> Path:
    return (
        Path(__file__).resolve().parents[2]
        / "docs"
        / "contracts"
        / "app-center"
        / "fixtures"
        / "style-preset-registry-v1.json"
    )


@lru_cache(maxsize=1)
def _registry() -> tuple[StylePreset, ...]:
    payload = json.loads(_registry_path().read_text(encoding="utf-8"))
    presets = tuple(StylePreset.model_validate(item) for item in payload["presets"])
    identities = {(item.style_id, item.version) for item in presets}
    if len(identities) != len(presets):
        raise StylePresetError("STYLE_REGISTRY_INVALID", "风格目录存在重复版本")
    return presets


def list_style_presets(
    *,
    app_id: str | None = None,
    family: str | None = None,
) -> list[dict[str, Any]]:
    items = [
        item
        for item in _registry()
        if item.status == "active"
        and (app_id is None or app_id in item.supported_apps)
        and (family is None or item.family == family)
    ]
    return [deepcopy(item.public_projection()) for item in items]


def resolve_style_preset(
    style_id: str,
    version: int,
    *,
    app_id: str,
) -> StylePreset:
    preset = next(
        (item for item in _registry() if item.style_id == style_id and item.version == version),
        None,
    )
    if preset is None or preset.status != "active":
        raise StylePresetError("STYLE_NOT_FOUND", "所选风格版本不存在或已停用")
    if app_id not in preset.supported_apps:
        raise StylePresetError("STYLE_APP_UNSUPPORTED", "所选风格不支持当前应用")
    return preset
