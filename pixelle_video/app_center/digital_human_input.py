"""V1/V2 digital-human input normalization and trusted media validation."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from .digital_human_workflow_catalog import (
    DigitalHumanWorkflowError,
    WorkflowBinding,
    resolve_workflow_profile,
)
from .validation import validate_business_payload

V1_APP_VERSION = "1.0.0"
V2_APP_VERSION = "1.1.0"
V2_SCHEMA_VERSION = 2
_V1_SOURCE_MODES = {"blank_project", "copywriting", "selected_title"}
_CONTENT_REQUIRED = {
    "custom_script": ("script",),
    "copywriting_artifact": ("source_artifact_version_id", "selected_variant_index"),
    "generated_marketing_copy": ("source_artifact_version_id", "selected_variant_index"),
    "title_plus_copywriting": (
        "title_artifact_version_id",
        "source_artifact_version_id",
        "selected_variant_index",
    ),
}
_DIGITAL_REQUIRED = ("mode", "portrait_id", "scene_id", "asset_revision_id", "workflow_profile")
_CONTENT_MODE_ALIASES = {
    "marketing_copy_artifact": "copywriting_artifact",
    "selected_title_with_copy": "title_plus_copywriting",
}
_QUALITY_SUBTITLE_PRESETS = {"readable_v2"}
_QUALITY_DEFAULT_DELIVERY = {"subtitle_preset": "readable_v2", "subtitle_enabled": True}
_MAX_SPOKEN_SCRIPT_CHARS = 2000


class DigitalHumanInputError(ValueError):
    def __init__(self, code: str, message: str | None = None):
        self.code = code
        super().__init__(f"{code}: {message or code}")


@dataclass(frozen=True)
class NormalizedDigitalHumanInput:
    payload: dict[str, Any]
    app_version: str
    schema_version: int
    source_revision: str
    resume_only: bool = False


def _fingerprint(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _require_object(value: Any, code: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise DigitalHumanInputError(code)
    return value


def _display_characters(value: str) -> int:
    """Count user-visible characters while treating CRLF as one line break."""

    return len(value.replace("\r\n", "\n").replace("\r", "\n"))


def _normalize_quality_delivery(value: Any) -> dict[str, Any]:
    if value is None:
        return dict(_QUALITY_DEFAULT_DELIVERY)
    if not isinstance(value, dict):
        raise DigitalHumanInputError("DIGITAL_HUMAN_DELIVERY_INVALID")

    normalized = dict(_QUALITY_DEFAULT_DELIVERY)
    subtitle_preset = value.get("subtitle_preset", "readable_v2")
    if not isinstance(subtitle_preset, str) or subtitle_preset not in _QUALITY_SUBTITLE_PRESETS:
        raise DigitalHumanInputError("DH_QUALITY_SUBTITLE_PRESET_REQUIRED")
    normalized["subtitle_preset"] = subtitle_preset
    subtitle_enabled = value.get("subtitle_enabled", True)
    if not isinstance(subtitle_enabled, bool):
        raise DigitalHumanInputError("DIGITAL_HUMAN_DELIVERY_INVALID")
    normalized["subtitle_enabled"] = subtitle_enabled

    for key in ("publish_title", "publish_description", "cover_title", "cover_subtitle"):
        raw = value.get(key)
        if raw is None:
            continue
        if not isinstance(raw, str):
            raise DigitalHumanInputError("DIGITAL_HUMAN_DELIVERY_INVALID")
        normalized[key] = raw.strip()

    raw_hashtags = value.get("hashtags")
    if raw_hashtags is not None:
        if not isinstance(raw_hashtags, list) or any(
            not isinstance(item, str) or not item.strip() for item in raw_hashtags
        ):
            raise DigitalHumanInputError("DIGITAL_HUMAN_DELIVERY_INVALID")
        normalized["hashtags"] = [item.strip().lstrip("#").strip() for item in raw_hashtags]
        if any(not item for item in normalized["hashtags"]):
            raise DigitalHumanInputError("DIGITAL_HUMAN_DELIVERY_INVALID")

    cover_title = normalized.get("cover_title")
    if isinstance(cover_title, str) and cover_title:
        title_lines = cover_title.replace("\r\n", "\n").replace("\r", "\n").split("\n")
        if (
            _display_characters(cover_title) > 24
            or len(title_lines) > 2
            or any(_display_characters(line) > 12 for line in title_lines)
        ):
            raise DigitalHumanInputError("DH_QUALITY_COVER_TITLE_TOO_LONG")
    cover_subtitle = normalized.get("cover_subtitle")
    if isinstance(cover_subtitle, str) and _display_characters(cover_subtitle) > 28:
        raise DigitalHumanInputError("DH_QUALITY_COVER_SUBTITLE_TOO_LONG")
    return normalized


def _normalize_voice_request(payload: dict[str, Any]) -> dict[str, str | None]:
    direct_voice_id = payload.get("voice_profile_id")
    nested_voice = payload.get("voice")
    if direct_voice_id not in (None, "") and nested_voice not in (None, {}):
        raise DigitalHumanInputError("DIGITAL_HUMAN_VOICE_INPUT_CONFLICT")
    # A pinned voice snapshot is a server-owned AppRun fact. Public callers may
    # only express a profile override and must never choose an audio revision.
    if nested_voice not in (None, {}):
        raise DigitalHumanInputError("DIGITAL_HUMAN_VOICE_INVALID")
    if direct_voice_id not in (None, ""):
        if not isinstance(direct_voice_id, str) or not direct_voice_id.strip():
            raise DigitalHumanInputError("DIGITAL_HUMAN_VOICE_INVALID")
        return {
            "voice_profile_id": direct_voice_id.strip(),
            "audio_revision_id": None,
        }
    return {"voice_profile_id": None, "audio_revision_id": None}


def _normalize_v2(payload: dict[str, Any], project_id: str) -> NormalizedDigitalHumanInput:
    if any(
        key in payload
        for key in (
            "digital_human_workflow",
            "digital_human_workflow_revision",
            "workflow_file_path",
            "runninghub_webapp_id",
        )
    ):
        raise DigitalHumanInputError("INPUT_PAYLOAD_INVALID")
    if payload.get("app_version") not in (None, V2_APP_VERSION):
        raise DigitalHumanInputError("INPUT_PAYLOAD_INVALID")
    if payload.get("project_id") not in (None, project_id):
        raise DigitalHumanInputError("PROJECT_ID_MISMATCH")
    content = _require_object(
        payload.get("content_source"), "DIGITAL_HUMAN_CONTENT_SOURCE_INCOMPLETE"
    )
    raw_mode = str(content.get("mode") or "").strip()
    mode = _CONTENT_MODE_ALIASES.get(raw_mode, raw_mode)
    content = {**content, "mode": mode}
    if mode not in _CONTENT_REQUIRED:
        raise DigitalHumanInputError("DIGITAL_HUMAN_CONTENT_SOURCE_INCOMPLETE")
    if mode == "custom_script" and ("goal" in content or "制作目标" in content):
        raise DigitalHumanInputError("DH_QUALITY_CUSTOM_SCRIPT_MUTATION")
    missing = [
        key for key in _CONTENT_REQUIRED[mode] if key not in content or content[key] in (None, "")
    ]
    if missing:
        raise DigitalHumanInputError(
            "DIGITAL_HUMAN_TITLE_REQUIRES_SCRIPT"
            if mode == "title_plus_copywriting"
            else "DIGITAL_HUMAN_CONTENT_SOURCE_INCOMPLETE"
        )
    if mode == "custom_script":
        if not isinstance(content.get("script"), str) or not content["script"].strip():
            raise DigitalHumanInputError("DIGITAL_HUMAN_CONTENT_SOURCE_INCOMPLETE")
    else:
        for key in ("source_artifact_version_id", "title_artifact_version_id"):
            if key in content and (not isinstance(content[key], str) or not content[key].strip()):
                raise DigitalHumanInputError("DIGITAL_HUMAN_CONTENT_SOURCE_INCOMPLETE")
        index = content.get("selected_variant_index")
        if not isinstance(index, int) or isinstance(index, bool) or index < 0:
            raise DigitalHumanInputError("DIGITAL_HUMAN_CONTENT_SOURCE_INCOMPLETE")
    spoken_script = content.get("spoken_script")
    if spoken_script is not None:
        if not isinstance(spoken_script, str) or not spoken_script.strip():
            raise DigitalHumanInputError("DIGITAL_HUMAN_SPOKEN_SCRIPT_INVALID")
        if len(spoken_script.strip()) > _MAX_SPOKEN_SCRIPT_CHARS:
            raise DigitalHumanInputError("DIGITAL_HUMAN_SPOKEN_SCRIPT_TOO_LONG")
        content["spoken_script"] = spoken_script.strip()
    human = _require_object(payload.get("digital_human"), "DIGITAL_HUMAN_MODE_REQUIRED")
    if any(
        key in human
        for key in (
            "digital_human_workflow",
            "digital_human_workflow_revision",
            "workflow_file_path",
            "runninghub_webapp_id",
        )
    ):
        raise DigitalHumanInputError("INPUT_PAYLOAD_INVALID")
    missing_human = [
        key
        for key in _DIGITAL_REQUIRED
        if not isinstance(human.get(key), str) or not human[key].strip()
    ]
    if missing_human:
        raise DigitalHumanInputError(
            "DIGITAL_HUMAN_ASSET_REQUIRED"
            if "asset_revision_id" in missing_human
            else "DIGITAL_HUMAN_MODE_REQUIRED"
        )
    if human["mode"] not in {"image_talking", "video_lipsync"}:
        raise DigitalHumanInputError("DIGITAL_HUMAN_MODE_INVALID")
    try:
        workflow = resolve_workflow_profile(
            human["mode"], human["workflow_profile"], require_released=False
        )
    except DigitalHumanWorkflowError as exc:
        raise DigitalHumanInputError(exc.code) from exc
    if mode == "title_plus_copywriting" and not content.get("source_artifact_version_id"):
        raise DigitalHumanInputError("DIGITAL_HUMAN_TITLE_REQUIRES_SCRIPT")
    canonical = {
        "project_id": project_id,
        "schema_version": V2_SCHEMA_VERSION,
        "content_source": content,
        "digital_human": {**human, "workflow_revision": workflow.workflow_revision},
        "voice_request": _normalize_voice_request(payload),
        "delivery": _normalize_quality_delivery(payload.get("delivery")),
    }
    return NormalizedDigitalHumanInput(
        payload=canonical,
        app_version=V2_APP_VERSION,
        schema_version=V2_SCHEMA_VERSION,
        source_revision=_fingerprint(canonical),
    )


def _normalize_v1(payload: dict[str, Any], project_id: str) -> NormalizedDigitalHumanInput:
    if payload.get("project_id") not in (None, project_id):
        raise DigitalHumanInputError("PROJECT_ID_MISMATCH")
    source_mode = payload.get("source_mode")
    if source_mode not in _V1_SOURCE_MODES:
        raise DigitalHumanInputError("DIGITAL_HUMAN_CONTENT_SOURCE_INCOMPLETE")
    if source_mode == "selected_title":
        if payload.get("resume_mode") != "resume_existing" or not payload.get("session_id"):
            raise DigitalHumanInputError("DIGITAL_HUMAN_TITLE_REQUIRES_SCRIPT")
        canonical = {"project_id": project_id, "app_version": V1_APP_VERSION, **payload}
        return NormalizedDigitalHumanInput(
            canonical, V1_APP_VERSION, 1, _fingerprint(canonical), resume_only=True
        )
    if source_mode == "blank_project":
        goal = str(payload.get("goal") or "").strip()
        if not goal:
            raise DigitalHumanInputError("DIGITAL_HUMAN_CONTENT_SOURCE_INCOMPLETE")
        content = {"mode": "custom_script", "script": goal}
    else:
        ids = payload.get("source_artifact_version_ids")
        index = payload.get("selected_variant_index")
        if (
            not isinstance(ids, list)
            or len(ids) != 1
            or not isinstance(index, int)
            or isinstance(index, bool)
        ):
            raise DigitalHumanInputError("DIGITAL_HUMAN_CONTENT_SOURCE_INCOMPLETE")
        content = {
            "mode": "copywriting_artifact",
            "source_artifact_version_id": ids[0],
            "selected_variant_index": index,
        }
    canonical = {
        "project_id": project_id,
        "schema_version": V2_SCHEMA_VERSION,
        "content_source": content,
        "legacy_input": payload,
    }
    return NormalizedDigitalHumanInput(
        canonical, V1_APP_VERSION, V2_SCHEMA_VERSION, _fingerprint(canonical)
    )


def normalize_digital_human_input(
    payload: dict[str, Any], *, project_id: str
) -> NormalizedDigitalHumanInput:
    if not isinstance(payload, dict):
        raise DigitalHumanInputError("INPUT_PAYLOAD_INVALID")
    try:
        validate_business_payload(payload, label="digital-human input")
    except ValueError as exc:
        raise DigitalHumanInputError("INPUT_PAYLOAD_INVALID") from exc
    schema_version = payload.get("schema_version")
    if schema_version not in (None, 1, V2_SCHEMA_VERSION):
        raise DigitalHumanInputError("INPUT_PAYLOAD_INVALID")
    app_version = payload.get("app_version")
    if app_version not in (None, V1_APP_VERSION, V2_APP_VERSION):
        raise DigitalHumanInputError("INPUT_PAYLOAD_INVALID")
    if schema_version == V2_SCHEMA_VERSION or app_version == V2_APP_VERSION:
        if schema_version != V2_SCHEMA_VERSION:
            raise DigitalHumanInputError("INPUT_PAYLOAD_INVALID")
        return _normalize_v2(payload, project_id)
    if schema_version == 1 and app_version not in (None, V1_APP_VERSION):
        raise DigitalHumanInputError("INPUT_PAYLOAD_INVALID")
    return _normalize_v1(payload, project_id)


def validate_trusted_media_binding(
    payload: dict[str, Any],
    *,
    asset: dict[str, Any],
    scene: dict[str, Any] | None = None,
    require_released_workflow: bool = True,
) -> WorkflowBinding:
    human = _require_object(payload.get("digital_human"), "DIGITAL_HUMAN_MODE_REQUIRED")
    mode = human.get("mode")
    expected_media = {"image_talking": "image", "video_lipsync": "video"}.get(mode)
    if expected_media is None:
        raise DigitalHumanInputError("DIGITAL_HUMAN_MODE_INVALID")
    if not isinstance(asset, dict) or asset.get("status") != "ready":
        raise DigitalHumanInputError("DIGITAL_HUMAN_ASSET_NOT_READY")
    if scene and scene.get("status") not in (None, "ready"):
        raise DigitalHumanInputError("DIGITAL_HUMAN_SCENE_NOT_READY")
    if asset.get("media_type") != expected_media or (
        scene and scene.get("media_type") != expected_media
    ):
        raise DigitalHumanInputError("DIGITAL_HUMAN_MEDIA_TYPE_MISMATCH")
    if scene and scene.get("profile_id") not in (None, "", human.get("portrait_id")):
        raise DigitalHumanInputError("DIGITAL_HUMAN_PORTRAIT_SCENE_MISMATCH")
    if asset.get("revision_id") != human.get("asset_revision_id"):
        raise DigitalHumanInputError("DIGITAL_HUMAN_ASSET_REVISION_MISMATCH")

    def _positive_int(value: Any) -> int | None:
        if isinstance(value, bool) or value is None:
            return None
        try:
            parsed = int(value)
        except (TypeError, ValueError, OverflowError):
            return None
        return parsed if parsed > 0 else None

    if expected_media == "image":
        width = _positive_int(asset.get("width"))
        height = _positive_int(asset.get("height"))
        if (
            asset.get("mime_type") not in {"image/png", "image/jpeg"}
            or width is None
            or height is None
            or min(width, height) < 720
        ):
            raise DigitalHumanInputError("DIGITAL_HUMAN_MEDIA_TYPE_MISMATCH")
    else:
        width = _positive_int(asset.get("width"))
        height = _positive_int(asset.get("height"))
        duration = _positive_int(asset.get("duration_ms"))
        if (
            asset.get("mime_type") not in {"video/mp4", "video/quicktime"}
            or width is None
            or height is None
            or width < 720
            or height < 1280
        ):
            raise DigitalHumanInputError("DIGITAL_HUMAN_VIDEO_GEOMETRY_INVALID")
        if duration is None or duration < 5000 or duration > 60000:
            raise DigitalHumanInputError("DIGITAL_HUMAN_VIDEO_DURATION_INVALID")
    try:
        return resolve_workflow_profile(
            mode,
            str(human.get("workflow_profile") or ""),
            require_released=require_released_workflow,
        )
    except DigitalHumanWorkflowError as exc:
        raise DigitalHumanInputError(exc.code) from exc


def resolve_asset_library_scene(scene_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
    """Resolve a scene and its current media revision from the asset library."""

    from pixelle_video.services.assets_v2.repository import AssetLibraryRepository

    repository = AssetLibraryRepository()
    scene = repository.get_digital_human_scene(scene_id)
    if not scene or not scene.get("source_asset_id"):
        raise DigitalHumanInputError("DIGITAL_HUMAN_SCENE_REQUIRED")
    source_asset_id = str(scene["source_asset_id"])
    source_revision_id = str(scene.get("source_revision_id") or "")
    if source_revision_id:
        asset = repository.get_asset_revision(source_asset_id, source_revision_id)
    else:
        asset = repository.get_asset(source_asset_id)
    if not asset:
        raise DigitalHumanInputError("DIGITAL_HUMAN_ASSET_REQUIRED")
    asset_projection = {
        **asset,
        "media_type": asset.get("media_kind"),
        "revision_id": asset.get("revision_id") or asset.get("current_revision_id"),
    }
    scene_projection = {**scene, "media_type": asset.get("media_kind")}
    return asset_projection, scene_projection
