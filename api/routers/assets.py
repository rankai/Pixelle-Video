"""Reusable asset-library endpoints for the desktop app."""

from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse

from api.config import api_config
from pixelle_video.services.brand_kit_service import BrandKitService
from pixelle_video.services.image_asset_service import ImageAssetService
from pixelle_video.services.ip_broadcast_presets import list_ip_broadcast_presets
from pixelle_video.services.ip_broadcast_templates import (
    IP_BROADCAST_CANVAS_HEIGHT,
    IP_BROADCAST_CANVAS_WIDTH,
    get_template_subtitle_style,
    list_ip_broadcast_templates,
)
from pixelle_video.services.portrait_service import PortraitService
from pixelle_video.services.video_asset_service import VideoAssetService
from pixelle_video.services.voice_reference_service import VoiceReferenceService

router = APIRouter(prefix="/assets", tags=["Assets"])


def _v2_repository_if_enabled():
    """Return the shared V2 repository during the compatibility window.

    Legacy routes remain available for rollback, but once V2 is explicitly
    enabled they must read/write the SQLite source of truth so the home page,
    old deep links and the new asset center do not diverge.
    """
    if not api_config.asset_center_v2_enabled:
        return None
    from api.routers.assets_v2 import get_asset_repository

    return get_asset_repository()


def _v2_upload_bytes(repository: Any, filename: str, kind: str, name: str, payload: bytes) -> dict[str, Any]:
    session = repository.create_upload_session(
        filename=filename,
        declared_bytes=len(payload),
        target_kind=kind,
        name=name,
    )
    if payload:
        repository.append_upload_chunk(session["upload_id"], payload)
    completed = repository.finalize_upload(session["upload_id"])
    asset_id = completed.get("asset_id") or completed.get("duplicate_asset_id")
    if not asset_id:
        raise ValueError("Upload completed without an asset record")
    asset = repository.get_asset(str(asset_id))
    if not asset:
        raise ValueError("Uploaded asset record is unavailable")
    return asset


def _legacy_v2_media(asset: dict[str, Any], repository: Any, kind: str) -> dict[str, Any]:
    asset_id = str(asset["asset_id"])
    path = repository.get_revision_path(asset_id)
    poster = repository.get_revision_path(asset_id, "poster")
    file_url = f"/api/assets/{'videos' if kind == 'video' else 'images'}/{asset_id}/file"
    if kind == "video":
        return {
            "asset_id": asset_id,
            "name": asset["name"],
            "filename": Path(asset.get("relative_path") or "").name,
            "created_at": asset["created_at"],
            "duration": round(float(asset.get("duration_ms") or 0) / 1000, 3),
            "size": int(asset.get("bytes") or 0),
            "thumbnail_exists": bool(poster),
            "asset_path": str(path) if path else "",
            "file_url": file_url,
            "thumbnail_url": f"/api/assets/videos/{asset_id}/thumbnail" if poster else "",
        }
    return {
        "asset_id": asset_id,
        "name": asset["name"],
        "filename": Path(asset.get("relative_path") or "").name,
        "created_at": asset["created_at"],
        "size": int(asset.get("bytes") or 0),
        "asset_path": str(path) if path else "",
        "file_url": file_url,
    }


def _legacy_v2_voice(item: dict[str, Any], repository: Any) -> dict[str, Any]:
    asset_id = str(item.get("asset_id") or item.get("resource_id") or "")
    asset = repository.get_asset(asset_id) or repository.get_asset_by_legacy_id("audio", asset_id)
    path = repository.get_revision_path(asset["asset_id"]) if asset else None
    reference_id = str(item.get("resource_id") or asset_id)
    return {
        "reference_id": reference_id,
        "name": str(item.get("name") or (asset or {}).get("name") or "未命名音色"),
        "filename": Path((asset or {}).get("relative_path") or "").name,
        "created_at": str(item.get("created_at") or (asset or {}).get("created_at") or ""),
        "asset_path": str(path) if path else "",
        "file_url": f"/api/assets/voices/{reference_id}/file",
    }


def _legacy_v2_portrait(item: dict[str, Any], repository: Any) -> dict[str, Any]:
    profile_id = str(item.get("resource_id") or "")
    path = repository.get_profile_source_path(profile_id)
    media_type = str((item.get("summary") or {}).get("media_type") or "image")
    return {
        "portrait_id": profile_id,
        "name": str(item.get("name") or "未命名数字人"),
        "filename": Path(str(path or "")).name,
        "created_at": str(item.get("created_at") or ""),
        "media_type": media_type,
        "asset_path": str(path) if path else "",
        "file_url": f"/api/assets/portraits/{profile_id}/file",
    }


@router.get("/presets/ip-broadcast")
async def list_ip_broadcast_preset_assets():
    return {"items": [preset.to_dict() for preset in list_ip_broadcast_presets()]}


@router.get("/brand-kits")
async def list_brand_kits():
    repository = _v2_repository_if_enabled()
    if repository is not None:
        items = []
        for item in repository.list_domain_items("brand"):
            brand = item.get("brand") or {}
            items.append(
                {
                    "brand_id": item["resource_id"],
                    "brand_name": item["name"],
                    "created_at": item["created_at"],
                    "logo_filename": "",
                    "primary_color": brand.get("primary_color") or "#1f6feb",
                    "secondary_color": brand.get("secondary_color") or "#0f766e",
                    "font_family": brand.get("font_family") or "",
                    "default_bgm_path": "",
                    "default_subtitle_style": brand.get("default_subtitle_style") or "",
                    "ending_card_text": brand.get("ending_card_text") or "",
                    "store_address": brand.get("store_address") or "",
                    "phone": brand.get("phone") or "",
                    "coupon_phrase": brand.get("coupon_phrase") or "",
                }
            )
        return {"items": items}
    return {"items": [item.to_dict() for item in BrandKitService().list_brand_kits()]}


@router.post("/brand-kits")
async def create_brand_kit(values: dict[str, Any]):
    repository = _v2_repository_if_enabled()
    if repository is not None:
        item = repository.create_brand_kit(values)
        brand = item.get("brand") or {}
        return {
            "brand_id": item["resource_id"],
            "brand_name": item["name"],
            "created_at": item["created_at"],
            "logo_filename": "",
            "primary_color": brand.get("primary_color") or "#1f6feb",
            "secondary_color": brand.get("secondary_color") or "#0f766e",
            "font_family": brand.get("font_family") or "",
            "default_bgm_path": "",
            "default_subtitle_style": brand.get("default_subtitle_style") or "",
            "ending_card_text": brand.get("ending_card_text") or "",
            "store_address": brand.get("store_address") or "",
            "phone": brand.get("phone") or "",
            "coupon_phrase": brand.get("coupon_phrase") or "",
        }
    return BrandKitService().create_brand_kit(values).to_dict()


@router.patch("/brand-kits/{brand_id}")
async def update_brand_kit(brand_id: str, values: dict[str, Any]):
    repository = _v2_repository_if_enabled()
    if repository is not None:
        updated = repository.patch_brand_kit(brand_id, values)
        if not updated:
            raise HTTPException(status_code=404, detail="Brand kit not found")
        brand = updated.get("brand") or {}
        return {
            "brand_id": updated["resource_id"],
            "brand_name": updated["name"],
            "created_at": updated["created_at"],
            "logo_filename": "",
            "primary_color": brand.get("primary_color") or "#1f6feb",
            "secondary_color": brand.get("secondary_color") or "#0f766e",
            "font_family": brand.get("font_family") or "",
            "default_bgm_path": "",
            "default_subtitle_style": brand.get("default_subtitle_style") or "",
            "ending_card_text": brand.get("ending_card_text") or "",
            "store_address": brand.get("store_address") or "",
            "phone": brand.get("phone") or "",
            "coupon_phrase": brand.get("coupon_phrase") or "",
        }
    updated = BrandKitService().update_brand_kit(brand_id, values)
    if not updated:
        raise HTTPException(status_code=404, detail="Brand kit not found")
    return updated.to_dict()


@router.delete("/brand-kits/{brand_id}")
async def delete_brand_kit(brand_id: str):
    repository = _v2_repository_if_enabled()
    if repository is not None:
        return {"deleted": bool(repository.set_domain_status("brand", brand_id, "archived"))}
    return {"deleted": BrandKitService().delete_brand_kit(brand_id)}


@router.get("/templates/ip-broadcast")
async def list_ip_broadcast_template_assets():
    return {
        "items": [
            {
                "template_id": template.template_id,
                "display_name": template.display_name,
                "short_description": template.short_description,
                "full_description": template.full_description,
                "cover_template_path": template.cover_template_path,
                "preview_image_path": template.preview_image_path,
                "preview_url": (
                    f"/api/assets/templates/ip-broadcast/{template.template_id}/preview"
                ),
                "subtitle_style": get_template_subtitle_style(template, video_height=1280).__dict__,
                # Kept as a separate field for clients that need the exact
                # render coordinates used by the 1080x1920 final video.
                "render_subtitle_style": get_template_subtitle_style(template).__dict__,
                "render_canvas": {
                    "width": IP_BROADCAST_CANVAS_WIDTH,
                    "height": IP_BROADCAST_CANVAS_HEIGHT,
                },
            }
            for template in list_ip_broadcast_templates()
        ]
    }


@router.get("/templates/ip-broadcast/{template_id}/preview")
async def get_ip_broadcast_template_preview(template_id: str):
    for template in list_ip_broadcast_templates():
        if template.template_id == template_id:
            path = Path(template.preview_image_path).resolve()
            if not path.exists() or not path.is_file():
                raise HTTPException(status_code=404, detail="Template preview not found")
            return FileResponse(str(path), media_type=_image_media_type(path), filename=path.name)
    raise HTTPException(status_code=404, detail="Template not found")


@router.get("/voices")
async def list_voice_references():
    repository = _v2_repository_if_enabled()
    if repository is not None:
        return {"items": [_legacy_v2_voice(item, repository) for item in repository.list_domain_items("voice")]}
    service = VoiceReferenceService()
    return {"items": [_voice_to_dict(item) for item in service.list_references()]}


@router.post("/voices")
async def upload_voice_reference(
    name: Annotated[str, Form()],
    file: Annotated[UploadFile, File()],
):
    payload = await _read_upload(file)
    repository = _v2_repository_if_enabled()
    if repository is not None:
        try:
            asset = _v2_upload_bytes(
                repository,
                file.filename or "voice.bin",
                "audio",
                name.strip() or _default_name(file),
                payload,
            )
        except (OSError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        try:
            # Keep the legacy reference ID stable while creating the typed
            # VoiceProfile projection required by the V2 library.
            voice = repository.create_voice_profile(
                {
                    "voice_id": asset["asset_id"],
                    "legacy_id": asset["asset_id"],
                    "name": asset["name"],
                    "audio_asset_id": asset["asset_id"],
                    "audio_revision_id": asset.get("current_revision_id"),
                }
            )
        except (OSError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return _legacy_v2_voice(
            {"resource_id": voice["resource_id"], "asset_id": asset["asset_id"], "name": asset["name"], "created_at": asset["created_at"]},
            repository,
        )
    service = VoiceReferenceService()
    try:
        info = service.save_reference(
            name=name.strip() or _default_name(file), audio_bytes=payload, ext=_ext(file)
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return _voice_to_dict(info)


@router.get("/voices/{reference_id}/file")
async def get_voice_reference_file(reference_id: str):
    repository = _v2_repository_if_enabled()
    if repository is not None:
        asset = repository.get_asset(reference_id) or repository.get_asset_by_legacy_id("audio", reference_id)
        path = repository.get_revision_path(asset["asset_id"]) if asset else None
        if not path:
            raise HTTPException(status_code=404, detail="Voice reference not found")
        return FileResponse(path, filename=Path(path).name)
    service = VoiceReferenceService()
    path = service.get_reference_path(reference_id)
    if not path:
        raise HTTPException(status_code=404, detail="Voice reference not found")
    return FileResponse(path, filename=Path(path).name)


@router.delete("/voices/{reference_id}")
async def delete_voice_reference(reference_id: str):
    repository = _v2_repository_if_enabled()
    if repository is not None:
        asset = repository.get_asset(reference_id) or repository.get_asset_by_legacy_id("audio", reference_id)
        changed = bool(asset and repository.archive_asset(asset["asset_id"]))
        if asset:
            repository.set_domain_status("voice", asset["asset_id"], "archived")
        return {"deleted": changed}
    return {"deleted": VoiceReferenceService().delete_reference(reference_id)}


@router.get("/portraits")
async def list_portraits():
    repository = _v2_repository_if_enabled()
    if repository is not None:
        return {"items": [_legacy_v2_portrait(item, repository) for item in repository.list_domain_items("digital_human")]}
    service = PortraitService()
    return {"items": [_portrait_to_dict(item) for item in service.list_portraits()]}


@router.post("/portraits")
async def upload_portrait(
    name: Annotated[str, Form()],
    file: Annotated[UploadFile, File()],
):
    payload = await _read_upload(file)
    repository = _v2_repository_if_enabled()
    if repository is not None:
        try:
            asset = _v2_upload_bytes(
                repository,
                file.filename or "portrait.bin",
                "video" if Path(file.filename or "").suffix.lower() in {".mp4", ".mov", ".webm"} else "image",
                name.strip() or _default_name(file),
                payload,
            )
            profile = repository.create_digital_human_profile(
                {
                    "name": name.strip() or _default_name(file),
                    "poster_asset_id": asset["asset_id"],
                    "source_asset_id": asset["asset_id"],
                    "source_revision_id": asset.get("current_revision_id"),
                }
            )
        except (OSError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return _legacy_v2_portrait(profile, repository)
    service = PortraitService()
    try:
        info = service.save_portrait(
            name=name.strip() or _default_name(file), image_bytes=payload, ext=_ext(file)
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return _portrait_to_dict(info)


@router.get("/portraits/{portrait_id}/file")
async def get_portrait_file(portrait_id: str):
    repository = _v2_repository_if_enabled()
    if repository is not None:
        path = repository.get_profile_source_path(portrait_id)
        if not path:
            raise HTTPException(status_code=404, detail="Portrait not found")
        return FileResponse(path, filename=Path(path).name)
    service = PortraitService()
    path = service.get_portrait_path(portrait_id)
    if not path:
        raise HTTPException(status_code=404, detail="Portrait not found")
    return FileResponse(path, filename=Path(path).name)


@router.delete("/portraits/{portrait_id}")
async def delete_portrait(portrait_id: str):
    repository = _v2_repository_if_enabled()
    if repository is not None:
        return {"deleted": bool(repository.set_domain_status("digital_human", portrait_id, "archived"))}
    return {"deleted": PortraitService().delete_portrait(portrait_id)}


@router.get("/videos")
async def list_video_assets():
    repository = _v2_repository_if_enabled()
    if repository is not None:
        return {"items": [_legacy_v2_media(item, repository, "video") for item in repository.list_assets("video")]}
    service = VideoAssetService()
    return {"items": [_video_to_dict(item) for item in service.list_assets()]}


@router.post("/videos")
async def upload_video_asset(
    name: Annotated[str, Form()],
    file: Annotated[UploadFile, File()],
):
    payload = await _read_upload(file)
    repository = _v2_repository_if_enabled()
    if repository is not None:
        try:
            asset = _v2_upload_bytes(
                repository,
                file.filename or "video.bin",
                "video",
                name.strip() or _default_name(file),
                payload,
            )
        except (OSError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return _legacy_v2_media(asset, repository, "video")
    service = VideoAssetService()
    try:
        info = service.save_asset(
            name=name.strip() or _default_name(file), video_bytes=payload, ext=_ext(file)
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return _video_to_dict(info)


@router.get("/videos/{asset_id}/file")
async def get_video_asset_file(asset_id: str):
    repository = _v2_repository_if_enabled()
    if repository is not None:
        asset = repository.get_asset(asset_id)
        path = repository.get_revision_path(asset_id)
        if not asset or not path:
            raise HTTPException(status_code=404, detail="Video asset not found")
        return FileResponse(path, media_type=asset.get("mime_type"), filename=Path(path).name)
    service = VideoAssetService()
    path = service.get_asset_path(asset_id)
    if not path:
        raise HTTPException(status_code=404, detail="Video asset not found")
    return FileResponse(path, filename=Path(path).name)


@router.get("/videos/{asset_id}/thumbnail")
async def get_video_asset_thumbnail(asset_id: str):
    repository = _v2_repository_if_enabled()
    if repository is not None:
        path = repository.get_revision_path(asset_id, "poster")
        if not path:
            raise HTTPException(status_code=404, detail="Video asset thumbnail not found")
        return FileResponse(path, filename=Path(path).name)
    for item in VideoAssetService().list_assets():
        if item.asset_id == asset_id and item.thumbnail_exists():
            return FileResponse(item.thumbnail_path(), filename=Path(item.thumbnail_path()).name)
    raise HTTPException(status_code=404, detail="Video asset thumbnail not found")


@router.delete("/videos/{asset_id}")
async def delete_video_asset(asset_id: str):
    repository = _v2_repository_if_enabled()
    if repository is not None:
        return {"deleted": repository.archive_asset(asset_id)}
    return {"deleted": VideoAssetService().delete_asset(asset_id)}


@router.get("/images")
async def list_image_assets():
    repository = _v2_repository_if_enabled()
    if repository is not None:
        return {"items": [_legacy_v2_media(item, repository, "image") for item in repository.list_assets("image")]}
    return {"items": [_image_to_dict(item) for item in ImageAssetService().list_assets()]}


@router.post("/images")
async def upload_image_asset(
    name: Annotated[str, Form()],
    file: Annotated[UploadFile, File()],
):
    payload = await _read_upload(file)
    repository = _v2_repository_if_enabled()
    if repository is not None:
        try:
            asset = _v2_upload_bytes(
                repository,
                file.filename or "image.bin",
                "image",
                name.strip() or _default_name(file),
                payload,
            )
        except (OSError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return _legacy_v2_media(asset, repository, "image")
    try:
        info = ImageAssetService().save_asset(
            name=name.strip() or _default_name(file),
            image_bytes=payload,
            ext=_ext(file),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _image_to_dict(info)


@router.get("/images/{asset_id}/file")
async def get_image_asset_file(asset_id: str):
    repository = _v2_repository_if_enabled()
    if repository is not None:
        asset = repository.get_asset(asset_id)
        path = repository.get_revision_path(asset_id)
        if not asset or not path:
            raise HTTPException(status_code=404, detail="Image asset not found")
        image_path = Path(path)
        return FileResponse(path, media_type=asset.get("mime_type") or _image_media_type(image_path), filename=image_path.name)
    path = ImageAssetService().get_asset_path(asset_id)
    if not path:
        raise HTTPException(status_code=404, detail="Image asset not found")
    image_path = Path(path)
    return FileResponse(path, media_type=_image_media_type(image_path), filename=image_path.name)


@router.delete("/images/{asset_id}")
async def delete_image_asset(asset_id: str):
    repository = _v2_repository_if_enabled()
    if repository is not None:
        return {"deleted": repository.archive_asset(asset_id)}
    return {"deleted": ImageAssetService().delete_asset(asset_id)}


async def _read_upload(file: UploadFile) -> bytes:
    if not file.filename:
        raise HTTPException(status_code=400, detail="Missing upload filename")
    return await file.read()


def _ext(file: UploadFile) -> str:
    return Path(file.filename or "").suffix


def _default_name(file: UploadFile) -> str:
    return Path(file.filename or "未命名素材").stem or "未命名素材"


def _image_media_type(path: Path) -> str:
    return {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".webp": "image/webp",
    }.get(path.suffix.lower(), "application/octet-stream")


def _voice_to_dict(info: Any) -> dict[str, Any]:
    return {
        "reference_id": info.reference_id,
        "name": info.name,
        "filename": info.filename,
        "created_at": info.created_at,
        "asset_path": info.asset_path(),
        "file_url": f"/api/assets/voices/{info.reference_id}/file",
    }


def _portrait_to_dict(info: Any) -> dict[str, Any]:
    return {
        "portrait_id": info.portrait_id,
        "name": info.name,
        "filename": info.filename,
        "created_at": info.created_at,
        "media_type": info.media_type,
        "asset_path": info.asset_path(),
        "file_url": f"/api/assets/portraits/{info.portrait_id}/file",
    }


def _video_to_dict(info: Any) -> dict[str, Any]:
    return {
        "asset_id": info.asset_id,
        "name": info.name,
        "filename": info.filename,
        "created_at": info.created_at,
        "duration": info.duration,
        "size": info.size,
        "thumbnail_exists": info.thumbnail_exists(),
        "asset_path": info.asset_path(),
        "file_url": f"/api/assets/videos/{info.asset_id}/file",
        "thumbnail_url": f"/api/assets/videos/{info.asset_id}/thumbnail"
        if info.thumbnail_exists()
        else "",
    }


def _image_to_dict(info: Any) -> dict[str, Any]:
    return {
        "asset_id": info.asset_id,
        "name": info.name,
        "filename": info.filename,
        "created_at": info.created_at,
        "size": info.size,
        "asset_path": info.asset_path(),
        "file_url": f"/api/assets/images/{info.asset_id}/file",
    }
