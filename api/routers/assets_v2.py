"""Stage-1 media asset API for the enterprise asset-library V2.

The router remains runtime-switchable. The feature flag is checked at request
time so a running desktop process can roll back to the legacy UI/API without
rebuilding; Gate C now makes V2 the default.
"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request, status
from fastapi.responses import FileResponse

from api.config import api_config
from api.schemas.asset_library_ux0 import TemplateLayoutContract
from api.schemas.asset_library_v2 import (
    BrandKitV2Request,
    BulkActionRequest,
    CollectionCreateRequest,
    CollectionPatchRequest,
    DeferredUploadFinalizeRequest,
    DigitalHumanPatchRequest,
    DigitalHumanScenePatchRequest,
    DigitalHumanSceneReorderRequest,
    DigitalHumanSceneV2Request,
    DigitalHumanV2Request,
    FavoriteRequest,
    MediaAssetPatchRequest,
    ResourceTagsRequest,
    ResourceUsageCreateRequest,
    SessionReconcileRequest,
    TemplatePatchRequest,
    TemplatePreviewRequest,
    TemplateV2Request,
    UploadSessionCreateRequest,
    VoiceProfileCreateRequest,
    VoiceProfilePatchRequest,
)
from pixelle_video.services.asset_library_cursor import (
    CursorContractError,
    CursorFilterMismatchError,
    CursorStaleError,
)
from pixelle_video.services.assets_v2.repository import AssetLibraryRepository
from pixelle_video.services.brand_kit_service import BrandKitService
from pixelle_video.services.ip_broadcast_templates import (
    IP_BROADCAST_CANVAS_HEIGHT,
    IP_BROADCAST_CANVAS_WIDTH,
    get_template_subtitle_style,
    list_ip_broadcast_templates,
    render_ip_broadcast_cover,
)
from pixelle_video.services.portrait_service import PortraitService
from pixelle_video.services.voice_reference_service import VoiceReferenceService
from pixelle_video.utils.os_util import get_data_path

router = APIRouter(prefix="/v2", tags=["Asset Library V2"])
_repository: AssetLibraryRepository | None = None
_repository_root: Path | None = None


def get_asset_repository() -> AssetLibraryRepository:
    global _repository, _repository_root
    # Test clients and embedded workers can switch PIXELLE_VIDEO_ROOT between
    # requests. Keying the singleton by its resolved data root prevents a
    # V2-enabled compatibility route from leaking assets across workspaces.
    data_root = Path(get_data_path()).resolve()
    if _repository is None or _repository_root != data_root:
        _repository = AssetLibraryRepository(data_root)
        _repository_root = data_root
    return _repository


def _ensure_enabled() -> None:
    if not api_config.asset_center_v2_enabled:
        raise HTTPException(status_code=404, detail="Asset Library V2 is not enabled")


def _asset_url(asset_id: str, suffix: str = "file") -> str:
    return f"/api/v2/media-assets/{asset_id}/{suffix}"


def _serialize_asset(asset: dict[str, Any], repository: AssetLibraryRepository) -> dict[str, Any]:
    revision = {
        "revision_id": asset.get("revision_id"),
        "version": asset.get("version"),
        "mime_type": asset.get("mime_type"),
        "bytes": asset.get("bytes"),
        "sha256": asset.get("sha256"),
        "width": asset.get("width"),
        "height": asset.get("height"),
        "aspect_ratio": asset.get("aspect_ratio"),
        "duration_ms": asset.get("duration_ms"),
        "frame_rate": asset.get("frame_rate"),
        "has_audio": bool(asset["has_audio"]) if asset.get("has_audio") is not None else None,
        "has_transparency": bool(asset["has_transparency"]) if asset.get("has_transparency") is not None else None,
        "relative_path": asset.get("relative_path"),
    }
    variants = []
    for variant in repository.get_variants(asset["asset_id"]):
        role = variant["role"]
        variants.append(
            {
                "variant_id": variant["variant_id"],
                "revision_id": variant["revision_id"],
                "role": role,
                "mime_type": variant["mime_type"],
                "width": variant.get("width"),
                "height": variant.get("height"),
                "duration_ms": variant.get("duration_ms"),
                "url": _asset_url(asset["asset_id"], f"variants/{role}"),
            }
        )
    return {
        "resource_id": asset["asset_id"],
        "kind": asset["media_kind"],
        "asset_id": asset["asset_id"],
        "legacy_id": asset.get("legacy_id"),
        "media_kind": asset["media_kind"],
        "name": asset["name"],
        "description": asset.get("description", ""),
        "source": asset["source"],
        "status": asset["status"],
        "created_at": asset["created_at"],
        "updated_at": asset["updated_at"],
        "archived_at": asset.get("archived_at"),
        "revision": revision,
        "file_url": _asset_url(asset["asset_id"]),
        "thumbnail_url": next(
            (item["url"] for item in variants if item["role"] in {"thumbnail", "poster"}),
            None,
        ),
        "cover_url": next(
            (item["url"] for item in variants if item["role"] in {"thumbnail", "poster"}),
            _asset_url(asset["asset_id"]),
        ),
        "tags": repository.resource_tags(asset["media_kind"], asset["asset_id"]),
        "favorite": repository.is_favorite(asset["media_kind"], asset["asset_id"]),
        "summary": {
            "bytes": int(asset.get("bytes") or 0),
            "width": int(asset["width"]) if asset.get("width") else 0,
            "height": int(asset["height"]) if asset.get("height") else 0,
            "aspect_ratio": float(asset["aspect_ratio"]) if asset.get("aspect_ratio") else 0,
            "duration_ms": int(asset["duration_ms"]) if asset.get("duration_ms") else 0,
            "has_audio": bool(asset.get("has_audio")) if asset.get("has_audio") is not None else False,
            "transparent": bool(asset.get("has_transparency")) if asset.get("has_transparency") is not None else False,
        },
        "display": {
            "orientation": "portrait" if asset.get("height") and asset.get("width") and asset["height"] > asset["width"] else "landscape" if asset.get("height") and asset.get("width") and asset["width"] > asset["height"] else "square" if asset.get("height") and asset.get("width") else "unknown",
            "width": int(asset["width"]) if asset.get("width") else 0,
            "height": int(asset["height"]) if asset.get("height") else 0,
            "duration_ms": int(asset["duration_ms"]) if asset.get("duration_ms") else 0,
            "bytes": int(asset.get("bytes") or 0),
            "transparent": bool(asset.get("has_transparency")) if asset.get("has_transparency") is not None else False,
        },
        "capabilities": ["preview", "use", "favorite", "archive", "edit"],
        "variants": variants,
    }


def _decorate_library_item(item: dict[str, Any], repository: AssetLibraryRepository) -> dict[str, Any]:
    kind = str(item.get("kind") or "")
    resource_id = str(item.get("resource_id") or "")
    return {
        **item,
        "tags": repository.resource_tags(kind, resource_id) or list(item.get("tags") or []),
        "favorite": repository.is_favorite(kind, resource_id),
    }


def _serialize_upload(session: dict[str, Any]) -> dict[str, Any]:
    return {
        "upload_id": session["upload_id"],
        "filename": session["filename"],
        "declared_bytes": session["declared_bytes"],
        "received_bytes": session["received_bytes"],
        "target_kind": session["target_kind"],
        "name": session.get("name"),
        "description": session.get("description", ""),
        "status": session["status"],
        "asset_id": session.get("asset_id"),
        "duplicate_asset_id": session.get("duplicate_asset_id"),
        "error_code": session.get("error_code"),
        "error_message": session.get("error_message"),
        "created_at": session["created_at"],
        "updated_at": session["updated_at"],
        "decision_mode": session.get("decision_mode", "auto"),
        "idempotency_key": session.get("idempotency_key"),
        "sha256": session.get("sha256"),
        "expires_at": session.get("expires_at"),
        "duplicate_policy": session.get("duplicate_policy"),
    }


def _domain_library_items(
    kind: str,
    repository: AssetLibraryRepository | None = None,
    include_archived: bool = False,
) -> list[dict[str, Any]]:
    if repository is not None:
        native = repository.list_domain_items(kind, include_archived=include_archived)
        # An empty filtered result can mean that every native row is
        # archived.  Check the unfiltered projection before falling back to
        # legacy services, otherwise an archived migrated item would appear
        # again as a ready duplicate.
        if native or repository.count_domain_items(kind, include_archived=True):
            return native
    if kind == "voice":
        return [
            {
                "resource_id": item.reference_id,
                "kind": "voice",
                "name": item.name,
                "description": item.filename,
                "status": "ready",
                "cover_url": f"/api/assets/voices/{item.reference_id}/file",
                "tags": [],
                "favorite": False,
                "created_at": item.created_at,
                "updated_at": item.created_at,
                "summary": {"filename": item.filename},
            }
            for item in VoiceReferenceService().list_references()
        ]
    if kind == "digital_human":
        return [
            {
                "resource_id": item.portrait_id,
                "kind": "digital_human",
                "name": item.name,
                "description": "视频形象" if item.media_type == "video" else "图片形象",
                "status": "ready",
                "cover_url": f"/api/assets/portraits/{item.portrait_id}/file",
                "tags": [item.media_type],
                "favorite": False,
                "created_at": item.created_at,
                "updated_at": item.created_at,
                "summary": {"media_type": item.media_type, "filename": item.filename},
            }
            for item in PortraitService().list_portraits()
        ]
    if kind == "brand":
        return [
            {
                "resource_id": item.brand_id,
                "kind": "brand",
                "name": item.brand_name,
                "description": item.ending_card_text,
                "status": "ready",
                "cover_url": None,
                "tags": [],
                "favorite": False,
                "created_at": item.created_at,
                "updated_at": item.created_at,
                "summary": {
                    "primary_color": item.primary_color,
                    "secondary_color": item.secondary_color,
                    "font_family": item.font_family,
                },
            }
            for item in BrandKitService().list_brand_kits()
        ]
    if kind == "template":
        return [
            {
                "resource_id": item.template_id,
                "kind": "template",
                "name": item.display_name,
                "description": item.short_description,
                "status": "ready",
                "cover_url": f"/api/assets/templates/ip-broadcast/{item.template_id}/preview",
                "tags": ["ip-broadcast"],
                "favorite": False,
                "created_at": "2026-07-17T00:00:00Z",
                "updated_at": "2026-07-17T00:00:00Z",
                "summary": {
                    "canvas_width": IP_BROADCAST_CANVAS_WIDTH,
                    "canvas_height": IP_BROADCAST_CANVAS_HEIGHT,
                    "subtitle_font_size": get_template_subtitle_style(item).font_size,
                    "subtitle_margin_v": get_template_subtitle_style(item).margin_v,
                },
            }
            for item in list_ip_broadcast_templates()
        ]
    return []


@router.get("/library/items")
async def list_library_items(
    kind: str | None = Query(default=None),
    q: str = Query(default=""),
    include_archived: bool = Query(default=False),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    favorite: bool | None = Query(default=None),
    tags: list[str] | None = Query(default=None),
    sort: str = Query(default="updated"),
    cursor: str | None = Query(default=None),
    orientation: str | None = Query(default=None),
    min_duration_ms: int | None = Query(default=None, ge=0),
    max_duration_ms: int | None = Query(default=None, ge=0),
    collection_id: str | None = Query(default=None),
    recently_used: bool | None = Query(default=None),
    status: str | None = Query(default=None),
    source: str | None = Query(default=None),
    aspect: str | None = Query(default=None),
):
    _ensure_enabled()
    repository = get_asset_repository()
    try:
        page = repository.list_library_page(
            kind=kind,
            query=q,
            include_archived=include_archived,
            page_size=limit,
            offset=offset if not cursor else 0,
            cursor=cursor,
            favorite=favorite,
            tags=tags,
            collection_id=collection_id,
            recently_used=recently_used,
            orientation=orientation,
            aspect=aspect,
            min_duration_ms=min_duration_ms,
            max_duration_ms=max_duration_ms,
            status=status,
            source=source,
            sort=sort,
        )
    except CursorFilterMismatchError as exc:
        raise HTTPException(status_code=400, detail={"code": "cursor_filter_mismatch", "message": str(exc)}) from exc
    except CursorStaleError as exc:
        raise HTTPException(status_code=409, detail={"code": "cursor_stale", "message": str(exc)}) from exc
    except (CursorContractError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    serialized: list[dict[str, Any]] = []
    for projection in page["items"]:
        resource_kind = str(projection["kind"])
        resource_id = str(projection["resource_id"])
        item: dict[str, Any] | None
        if resource_kind in {"image", "video", "audio"}:
            asset = repository.get_asset(str(projection.get("media_asset_id") or resource_id))
            item = _serialize_asset(asset, repository) if asset else None
        else:
            item = repository.get_domain_item(resource_kind, resource_id)
        if item is None:
            item = {
                "resource_id": resource_id,
                "kind": resource_kind,
                "name": projection["name"],
                "description": projection["description"] or "",
                "status": projection["status"],
                "created_at": projection["created_at"],
                "updated_at": projection["updated_at"],
                "cover_url": None,
                "tags": [],
                "favorite": False,
                "summary": {},
            }
        serialized.append({**_decorate_library_item(item, repository), "last_used_at": projection.get("last_used_at")})
    page["items"] = serialized
    # Preserve the established built-in template entry point for callers
    # that open the template category directly.  The SQL cursor order remains
    # the stable updated/kind/id tuple for pagination; this compatibility
    # preference only applies while the small built-in template page is
    # decorated for the legacy entry point.
    if kind == "template":
        page["items"] = sorted(serialized, key=lambda item: (0 if item.get("resource_id") == "boss_clean" else 1, str(item.get("resource_id") or "")))
    page["limit"] = limit
    page["offset"] = offset
    return page


def _sort_library_items(
    items: list[dict[str, Any]], sort: str, repository: AssetLibraryRepository
) -> list[dict[str, Any]]:
    if sort == "name":
        return sorted(items, key=lambda item: (str(item.get("name") or "").lower(), item.get("resource_id") or ""))
    if sort != "recent":
        return items
    order = {
        key: index
        for index, key in enumerate(repository.recent_resource_keys(max(len(items), 1)))
    }
    fallback = len(order) + 1
    return sorted(
        items,
        key=lambda item: order.get((str(item.get("kind") or ""), str(item.get("resource_id") or "")), fallback),
    )


@router.get("/media-assets/{asset_id}")
async def get_media_asset(asset_id: str):
    _ensure_enabled()
    repository = get_asset_repository()
    asset = repository.get_asset(asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail="Media asset not found")
    return _serialize_asset(asset, repository)


@router.post("/domain/brands", status_code=status.HTTP_201_CREATED)
async def create_domain_brand(payload: BrandKitV2Request):
    _ensure_enabled()
    try:
        return get_asset_repository().create_brand_kit(payload.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/domain/voices", status_code=status.HTTP_201_CREATED)
async def create_domain_voice(payload: VoiceProfileCreateRequest):
    _ensure_enabled()
    try:
        return get_asset_repository().create_voice_profile(payload.model_dump())
    except (ValueError, OSError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.patch("/domain/voices/{voice_id}")
async def patch_domain_voice(voice_id: str, payload: VoiceProfilePatchRequest):
    _ensure_enabled()
    try:
        updated = get_asset_repository().patch_voice_profile(voice_id, payload.model_dump(exclude_unset=True))
    except (ValueError, OSError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not updated:
        raise HTTPException(status_code=404, detail="Voice profile not found")
    return updated


@router.get("/domain/voices/{voice_id}")
async def get_domain_voice(voice_id: str):
    _ensure_enabled()
    item = get_asset_repository().get_domain_item("voice", voice_id)
    if not item:
        raise HTTPException(status_code=404, detail="Voice profile not found")
    return item


@router.post("/domain/voices/{voice_id}/archive")
async def archive_domain_voice(voice_id: str):
    _ensure_enabled()
    updated = get_asset_repository().set_domain_status("voice", voice_id, "archived")
    if not updated:
        raise HTTPException(status_code=404, detail="Voice profile not found")
    return updated


@router.post("/domain/voices/{voice_id}/restore")
async def restore_domain_voice(voice_id: str):
    _ensure_enabled()
    updated = get_asset_repository().set_domain_status("voice", voice_id, "ready")
    if not updated:
        raise HTTPException(status_code=404, detail="Voice profile not found")
    return updated


@router.post("/domain/digital-humans", status_code=status.HTTP_201_CREATED)
async def create_domain_digital_human(payload: DigitalHumanV2Request):
    _ensure_enabled()
    try:
        return get_asset_repository().create_digital_human_profile(payload.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/domain/digital-humans/{profile_id}/scenes")
async def list_domain_digital_human_scenes(profile_id: str):
    _ensure_enabled()
    if not get_asset_repository().get_domain_item("digital_human", profile_id):
        raise HTTPException(status_code=404, detail="Digital human profile not found")
    return {"items": get_asset_repository().list_digital_human_scenes(profile_id)}


@router.post("/domain/digital-humans/{profile_id}/scenes", status_code=status.HTTP_201_CREATED)
async def create_domain_digital_human_scene(
    profile_id: str, payload: DigitalHumanSceneV2Request
):
    _ensure_enabled()
    try:
        scene = get_asset_repository().create_digital_human_scene(
            profile_id, payload.model_dump()
        )
    except (OSError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not scene:
        raise HTTPException(status_code=404, detail="Digital human profile not found")
    return scene


@router.get("/domain/digital-human-scenes/{scene_id}")
async def get_domain_digital_human_scene(scene_id: str):
    _ensure_enabled()
    scene = get_asset_repository().get_digital_human_scene(scene_id)
    if not scene:
        raise HTTPException(status_code=404, detail="Digital human scene not found")
    return scene


@router.patch("/domain/digital-human-scenes/{scene_id}")
async def patch_domain_digital_human_scene(scene_id: str, payload: DigitalHumanScenePatchRequest):
    _ensure_enabled()
    try:
        updated = get_asset_repository().patch_digital_human_scene(scene_id, payload.model_dump(exclude_unset=True))
    except (ValueError, OSError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not updated:
        raise HTTPException(status_code=404, detail="Digital human scene not found")
    return updated


@router.post("/domain/digital-human-scenes/{scene_id}/archive")
async def archive_domain_digital_human_scene(scene_id: str):
    _ensure_enabled()
    updated = get_asset_repository().patch_digital_human_scene(scene_id, {"status": "archived"})
    if not updated:
        raise HTTPException(status_code=404, detail="Digital human scene not found")
    return updated


@router.post("/domain/digital-humans/{profile_id}/scenes/reorder")
async def reorder_domain_digital_human_scenes(profile_id: str, payload: DigitalHumanSceneReorderRequest):
    _ensure_enabled()
    try:
        return {"items": get_asset_repository().reorder_digital_human_scenes(profile_id, payload.scene_ids)}
    except (ValueError, OSError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.patch("/domain/digital-humans/{profile_id}")
async def patch_domain_digital_human(profile_id: str, payload: DigitalHumanPatchRequest):
    _ensure_enabled()
    updated = get_asset_repository().patch_digital_human_profile(
        profile_id, payload.model_dump(exclude_unset=True)
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Digital human profile not found")
    return updated


@router.post("/domain/templates", status_code=status.HTTP_201_CREATED)
async def create_domain_template(payload: TemplateV2Request):
    _ensure_enabled()
    try:
        return get_asset_repository().create_template_revision(payload.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/domain/templates/preview")
async def preview_domain_template(payload: TemplatePreviewRequest):
    _ensure_enabled()
    try:
        contract = TemplateLayoutContract.model_validate(payload.draft_contract)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail={"code": "invalid_template_layout_contract", "message": str(exc)}) from exc
    repository = get_asset_repository()
    resolved_fonts = [
        {"token": font.token, "font_id": font.font_id, "family": font.family, "weight": font.weight, "style": font.style, "sha256": font.font_sha256, "source": "bundled_registry"}
        for font in contract.fonts
    ]
    preview_id = f"template-preview-{uuid.uuid4().hex}"
    preview_root = repository.data_root / "asset_library" / "template_previews"
    preview_root.mkdir(parents=True, exist_ok=True)
    preview_path = preview_root / f"{preview_id}.png"
    background = ""
    background_asset_id = payload.sample.get("background_asset_id") or payload.sample.get("video_frame_asset_id")
    if background_asset_id:
        background_path = repository.get_revision_path(str(background_asset_id))
        if background_path:
            background = str(background_path)
    try:
        await render_ip_broadcast_cover(
            contract.base_template_id,
            str(payload.sample.get("title") or "门店口播标题"),
            str(payload.sample.get("subtitle") or "字幕预览：同一份布局契约用于封面与成片"),
            background,
            str(preview_path),
        )
    except (OSError, RuntimeError, ValueError, TypeError) as exc:
        preview_path.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail={"code": "template_preview_render_failed", "message": str(exc)}) from exc
    return {
        "preview_url": f"/api/v2/domain/templates/preview/{preview_id}",
        "resolved_contract": contract.model_dump(mode="json"),
        "resolved_fonts": resolved_fonts,
        "layout_boxes": {"title": contract.cover.title.model_dump(), "subtitle": contract.cover.subtitle.model_dump(), "video_subtitle": contract.video_subtitle.model_dump()},
        "warnings": ["preview_rendered_by_authoritative_service"],
    }


@router.get("/domain/templates/preview/{preview_id}")
async def get_domain_template_preview(preview_id: str):
    _ensure_enabled()
    if Path(preview_id).name != preview_id or not preview_id.startswith("template-preview-"):
        raise HTTPException(status_code=404, detail="Template preview not found")
    path = get_asset_repository().data_root / "asset_library" / "template_previews" / f"{preview_id}.png"
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Template preview not found")
    return FileResponse(path, media_type="image/png", filename=path.name)


@router.patch("/domain/templates/{template_id}")
async def patch_domain_template(template_id: str, payload: TemplatePatchRequest):
    _ensure_enabled()
    try:
        updated = get_asset_repository().patch_template_revision(
            template_id, payload.model_dump(exclude_unset=True)
        )
    except (OSError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not updated:
        raise HTTPException(status_code=404, detail="Template not found")
    return updated


@router.patch("/domain/brands/{brand_id}")
async def patch_domain_brand(brand_id: str, payload: BrandKitV2Request):
    _ensure_enabled()
    updated = get_asset_repository().patch_brand_kit(brand_id, payload.model_dump(exclude_unset=True))
    if not updated:
        raise HTTPException(status_code=404, detail="Brand kit not found")
    return updated


@router.post("/domain/brands/{brand_id}/archive")
async def archive_domain_brand(brand_id: str):
    _ensure_enabled()
    updated = get_asset_repository().patch_brand_kit(brand_id, {"status": "archived"})
    if not updated:
        raise HTTPException(status_code=404, detail="Brand kit not found")
    return updated


@router.get("/library/items/{resource_id}")
async def get_library_item(resource_id: str):
    _ensure_enabled()
    repository = get_asset_repository()
    asset = repository.get_asset(resource_id)
    if asset:
        return _serialize_asset(asset, repository)
    for kind in ("voice", "digital_human", "brand", "template"):
        match = next(
            (item for item in _domain_library_items(kind, repository, True) if item["resource_id"] == resource_id),
            None,
        )
        if match:
            return match
    raise HTTPException(status_code=404, detail="Library item not found")


@router.get("/library/facets")
async def library_facets(
    kind: str | None = Query(default=None),
    q: str = Query(default=""),
    include_archived: bool = Query(default=False),
    favorite: bool | None = Query(default=None),
    tags: list[str] | None = Query(default=None),
    collection_id: str | None = Query(default=None),
    recently_used: bool | None = Query(default=None),
    orientation: str | None = Query(default=None),
    aspect: str | None = Query(default=None),
    min_duration_ms: int | None = Query(default=None, ge=0),
    max_duration_ms: int | None = Query(default=None, ge=0),
    status: str | None = Query(default=None),
    source: str | None = Query(default=None),
):
    _ensure_enabled()
    repository = get_asset_repository()
    return repository.library_facets(
        kind=kind,
        query=q,
        include_archived=include_archived,
        favorite=favorite,
        tags=tags,
        collection_id=collection_id,
        recently_used=recently_used,
        orientation=orientation,
        aspect=aspect,
        min_duration_ms=min_duration_ms,
        max_duration_ms=max_duration_ms,
        status=status,
        source=source,
    )


@router.post("/library/bulk")
async def bulk_library_action(payload: BulkActionRequest):
    _ensure_enabled()
    repository = get_asset_repository()
    results: list[dict[str, Any]] = []
    for item in payload.items:
        kind = item.kind.value
        resource_id = item.resource_id
        try:
            if payload.action == "archive":
                changed = repository.archive_asset(resource_id) if kind in {"image", "video", "audio"} else bool(repository.set_domain_status(kind, resource_id, "archived"))
            elif payload.action == "restore":
                changed = repository.restore_asset(resource_id) if kind in {"image", "video", "audio"} else bool(repository.set_domain_status(kind, resource_id, "ready"))
            elif payload.action in {"favorite", "unfavorite"}:
                changed = repository.set_favorite(kind, resource_id, payload.action == "favorite")
            elif payload.action in {"tag", "untag"}:
                current = set(repository.resource_tags(kind, resource_id))
                next_tags = current | set(payload.tags) if payload.action == "tag" else current - set(payload.tags)
                repository.set_resource_tags(kind, resource_id, sorted(next_tags))
                changed = True
            else:
                changed = False
            results.append({"kind": kind, "resource_id": resource_id, "ok": bool(changed)})
        except (KeyError, OSError, ValueError) as exc:
            results.append({"kind": kind, "resource_id": resource_id, "ok": False, "error": str(exc)})
    return {"items": results, "succeeded": sum(1 for item in results if item["ok"]), "failed": sum(1 for item in results if not item["ok"])}


@router.get("/library/{kind}/{resource_id}/usage")
async def list_library_usage(kind: str, resource_id: str):
    _ensure_enabled()
    return {"items": get_asset_repository().list_resource_usage(kind, resource_id)}


@router.post("/library/{kind}/{resource_id}/archive")
async def archive_library_item(kind: str, resource_id: str):
    _ensure_enabled()
    repository = get_asset_repository()
    changed = repository.archive_asset(resource_id) if kind in {"image", "video", "audio"} else bool(repository.set_domain_status(kind, resource_id, "archived"))
    if not changed:
        raise HTTPException(status_code=404, detail="Library item not found")
    return {"kind": kind, "resource_id": resource_id, "status": "archived"}


@router.post("/library/{kind}/{resource_id}/restore")
async def restore_library_item(kind: str, resource_id: str):
    _ensure_enabled()
    repository = get_asset_repository()
    changed = repository.restore_asset(resource_id) if kind in {"image", "video", "audio"} else bool(repository.set_domain_status(kind, resource_id, "ready"))
    if not changed:
        raise HTTPException(status_code=404, detail="Library item not found")
    return {"kind": kind, "resource_id": resource_id, "status": "ready"}


@router.put("/library/items/{kind}/{resource_id}/favorite")
async def set_library_favorite(kind: str, resource_id: str, payload: FavoriteRequest):
    _ensure_enabled()
    if kind not in {"image", "video", "audio", "voice", "digital_human", "brand", "template"}:
        raise HTTPException(status_code=400, detail="Unsupported library item kind")
    return {"kind": kind, "resource_id": resource_id, "favorite": get_asset_repository().set_favorite(kind, resource_id, payload.favorite)}


@router.put("/library/items/{kind}/{resource_id}/tags")
async def set_library_tags(kind: str, resource_id: str, payload: ResourceTagsRequest):
    _ensure_enabled()
    return {"kind": kind, "resource_id": resource_id, "tags": get_asset_repository().set_resource_tags(kind, resource_id, payload.tags)}


@router.get("/collections")
async def list_collections():
    _ensure_enabled()
    return {"items": get_asset_repository().list_collections()}


@router.post("/collections", status_code=status.HTTP_201_CREATED)
async def create_collection(payload: CollectionCreateRequest):
    _ensure_enabled()
    try:
        return get_asset_repository().create_collection(payload.name, payload.description)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail={"code": "collection_name_conflict", "message": str(exc)}) from exc


@router.patch("/collections/{collection_id}")
async def patch_collection(collection_id: str, payload: CollectionPatchRequest):
    _ensure_enabled()
    try:
        result = get_asset_repository().patch_collection(collection_id, payload.name, payload.description)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail={"code": "collection_name_conflict", "message": str(exc)}) from exc
    if not result:
        raise HTTPException(status_code=404, detail="Collection not found")
    return result


@router.post("/collections/{collection_id}/archive")
async def archive_collection(collection_id: str):
    _ensure_enabled()
    result = get_asset_repository().set_collection_status(collection_id, "archived")
    if not result:
        raise HTTPException(status_code=404, detail="Collection not found")
    return result


@router.delete("/collections/{collection_id}")
async def delete_collection(collection_id: str):
    _ensure_enabled()
    if not get_asset_repository().delete_collection(collection_id):
        raise HTTPException(status_code=404, detail="Collection not found")
    return {"deleted": True}


@router.get("/collections/{collection_id}/items")
async def list_collection_items(collection_id: str):
    _ensure_enabled()
    result = get_asset_repository().list_collection_items(collection_id)
    if not result and not any(item["collection_id"] == collection_id for item in get_asset_repository().list_collections()):
        raise HTTPException(status_code=404, detail="Collection not found")
    return {"items": result}


@router.post("/collections/{collection_id}/items")
async def add_collection_item(collection_id: str, kind: str, resource_id: str):
    _ensure_enabled()
    if not get_asset_repository().add_collection_item(collection_id, kind, resource_id):
        raise HTTPException(status_code=404, detail="Collection not found")
    return {"collection_id": collection_id, "kind": kind, "resource_id": resource_id}


@router.delete("/collections/{collection_id}/items/{kind}/{resource_id}")
async def remove_collection_item(collection_id: str, kind: str, resource_id: str):
    _ensure_enabled()
    if not get_asset_repository().remove_collection_item(collection_id, kind, resource_id):
        raise HTTPException(status_code=404, detail="Collection item not found")
    return {"deleted": True}


@router.patch("/media-assets/{asset_id}")
async def patch_media_asset(asset_id: str, payload: MediaAssetPatchRequest):
    _ensure_enabled()
    repository = get_asset_repository()
    asset = repository.patch_asset(asset_id, payload.name, payload.description)
    if not asset:
        raise HTTPException(status_code=404, detail="Media asset not found")
    return _serialize_asset(asset, repository)


@router.post("/media-assets/{asset_id}/archive")
async def archive_media_asset(asset_id: str):
    _ensure_enabled()
    repository = get_asset_repository()
    if not repository.archive_asset(asset_id):
        raise HTTPException(status_code=404, detail="Media asset not found or already archived")
    return {"asset_id": asset_id, "status": "archived"}


@router.get("/media-assets/{asset_id}/revisions")
async def list_media_asset_revisions(asset_id: str):
    _ensure_enabled()
    repository = get_asset_repository()
    if not repository.get_asset(asset_id):
        raise HTTPException(status_code=404, detail="Media asset not found")
    return {"items": repository.list_revisions(asset_id)}


@router.post("/media-assets/{asset_id}/revisions")
async def create_media_asset_revision(asset_id: str, request: Request):
    _ensure_enabled()
    repository = get_asset_repository()
    asset = repository.get_asset(asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail="Media asset not found")
    filename = request.headers.get("x-filename") or request.query_params.get("filename") or "revision.bin"
    temporary = repository.incoming_root / f"revision-{uuid.uuid4().hex}.part"
    received = 0
    try:
        temporary.touch()
        async for chunk in request.stream():
            if not chunk:
                continue
            received += len(chunk)
            if received > repository.max_upload_size:
                raise ValueError("Revision exceeds configured size limit")
            with temporary.open("ab") as handle:
                handle.write(chunk)
        result = repository.create_revision_from_path(asset_id, filename, temporary)
    except (OSError, ValueError) as exc:
        temporary.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not result:
        temporary.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail="Unable to create asset revision")
    return _serialize_asset(result, repository)


@router.post("/media-assets/{asset_id}/revisions/{revision_id}/activate")
async def activate_media_asset_revision(asset_id: str, revision_id: str):
    _ensure_enabled()
    result = get_asset_repository().activate_revision(asset_id, revision_id)
    if not result:
        raise HTTPException(status_code=404, detail="Asset revision not found")
    return _serialize_asset(result, get_asset_repository())


@router.post("/media-assets/{asset_id}/analysis/retry")
async def retry_media_asset_analysis(asset_id: str, revision_id: str | None = Query(default=None)):
    _ensure_enabled()
    repository = get_asset_repository()
    result = repository.retry_analysis(asset_id, revision_id)
    if not result:
        raise HTTPException(status_code=404, detail="Asset or revision file not found")
    return _serialize_asset(result, repository)


@router.get("/media-assets/{asset_id}/file")
async def get_media_asset_file(asset_id: str, revision_id: str | None = Query(default=None)):
    _ensure_enabled()
    repository = get_asset_repository()
    asset = repository.get_asset(asset_id)
    path = repository.get_revision_path(asset_id, revision_id=revision_id)
    if not asset or not path:
        raise HTTPException(status_code=404, detail="Media asset file not found")
    return FileResponse(path, media_type=asset.get("mime_type"), filename=Path(path).name)


@router.get("/media-assets/{asset_id}/variants/{role}")
async def get_media_asset_variant(asset_id: str, role: str):
    _ensure_enabled()
    repository = get_asset_repository()
    path = repository.get_revision_path(asset_id, role)
    if not path:
        raise HTTPException(status_code=404, detail="Media asset variant not found")
    return FileResponse(path, filename=Path(path).name)


@router.post("/uploads", status_code=status.HTTP_201_CREATED)
async def create_upload(payload: UploadSessionCreateRequest):
    _ensure_enabled()
    repository = get_asset_repository()
    try:
        target_kind = "audio" if payload.target_kind.value == "voice" else payload.target_kind.value
        session = repository.create_upload_session(
            filename=payload.filename,
            declared_bytes=payload.declared_bytes,
            target_kind=target_kind,
            name=payload.name,
            description=payload.description,
            decision_mode="deferred" if payload.deferred else "auto",
            idempotency_key=payload.idempotency_key,
        )
    except (ValueError, OSError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _serialize_upload(session)


@router.get("/uploads/{upload_id}")
async def get_upload(upload_id: str):
    _ensure_enabled()
    session = get_asset_repository().get_upload_session(upload_id)
    if not session:
        raise HTTPException(status_code=404, detail="Upload session not found")
    return _serialize_upload(session)


@router.put("/uploads/{upload_id}/content")
async def stream_upload(upload_id: str, request: Request):
    _ensure_enabled()
    repository = get_asset_repository()
    try:
        if not repository.get_upload_session(upload_id):
            raise HTTPException(status_code=404, detail="Upload session not found")
        async for chunk in request.stream():
            repository.append_upload_chunk(upload_id, chunk)
        session_before_finalize = repository.get_upload_session(upload_id) or {}
        session = repository.complete_upload_content(upload_id) if session_before_finalize.get("decision_mode") == "deferred" else repository.finalize_upload(upload_id)
    except HTTPException:
        raise
    except (FileNotFoundError, KeyError, ValueError, OSError) as exc:
        if isinstance(exc, (KeyError, ValueError, OSError)):
            try:
                repository.fail_upload(upload_id, "upload_failed", str(exc))
            except (KeyError, ValueError, OSError):
                pass
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    response: dict[str, Any] = {"upload": _serialize_upload(session)}
    if session.get("asset_id"):
        asset = repository.get_asset(session["asset_id"])
        if asset:
            response["asset"] = _serialize_asset(asset, repository)
    if session.get("duplicate_asset_id"):
        duplicate = repository.get_asset(session["duplicate_asset_id"])
        if duplicate:
            response["duplicate_asset"] = _serialize_asset(duplicate, repository)
    return response


@router.post("/uploads/{upload_id}/finalize")
async def finalize_deferred_upload(upload_id: str, payload: DeferredUploadFinalizeRequest):
    _ensure_enabled()
    repository = get_asset_repository()
    try:
        session = repository.finalize_deferred_upload(
            upload_id,
            payload.duplicate_policy,
            target_asset_id=payload.target_asset_id,
        )
    except (FileNotFoundError, KeyError, ValueError, OSError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    response: dict[str, Any] = {"upload": _serialize_upload(session)}
    if session.get("asset_id"):
        asset = repository.get_asset(session["asset_id"])
        if asset:
            response["asset"] = _serialize_asset(asset, repository)
    if session.get("duplicate_asset_id"):
        duplicate = repository.get_asset(session["duplicate_asset_id"])
        if duplicate:
            response["duplicate_asset"] = _serialize_asset(duplicate, repository)
    return response


@router.post("/uploads/{upload_id}/cancel")
async def cancel_upload(upload_id: str):
    _ensure_enabled()
    if not get_asset_repository().cancel_upload(upload_id):
        raise HTTPException(status_code=404, detail="Upload session not found or already closed")
    return {"upload_id": upload_id, "status": "cancelled"}


@router.get("/sessions/{session_id}/resource-usage")
async def list_session_resource_usage(session_id: str):
    _ensure_enabled()
    return {"items": get_asset_repository().list_usage(session_id)}


@router.post("/sessions/{session_id}/reconcile")
async def reconcile_session_usage(session_id: str, payload: SessionReconcileRequest):
    _ensure_enabled()
    return get_asset_repository().reconcile_session_usage(
        session_id,
        [item.model_dump() for item in payload.references],
    )


@router.post("/sessions/{session_id}/resource-usage")
async def record_session_resource_usage(session_id: str, payload: ResourceUsageCreateRequest):
    _ensure_enabled()
    usage = get_asset_repository().record_external_usage(
        payload.resource_kind.value,
        payload.resource_id,
        session_id,
        payload.step,
        payload.purpose,
        payload.slot_id,
        payload.revision_id,
    )
    if not usage:
        raise HTTPException(status_code=400, detail="Unable to record resource usage")
    return usage


@router.get("/sessions/{session_id}/resource-snapshots")
async def list_session_resource_snapshots(session_id: str):
    _ensure_enabled()
    return {"items": get_asset_repository().list_snapshots(session_id)}
