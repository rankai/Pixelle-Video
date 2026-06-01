"""Reusable asset-library endpoints for the desktop app."""

from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse

from pixelle_video.services.brand_kit_service import BrandKitService
from pixelle_video.services.ip_broadcast_presets import list_ip_broadcast_presets
from pixelle_video.services.ip_broadcast_templates import list_ip_broadcast_templates
from pixelle_video.services.portrait_service import PortraitService
from pixelle_video.services.video_asset_service import VideoAssetService
from pixelle_video.services.voice_reference_service import VoiceReferenceService

router = APIRouter(prefix="/assets", tags=["Assets"])


@router.get("/presets/ip-broadcast")
async def list_ip_broadcast_preset_assets():
    return {"items": [preset.to_dict() for preset in list_ip_broadcast_presets()]}


@router.get("/brand-kits")
async def list_brand_kits():
    return {"items": [item.to_dict() for item in BrandKitService().list_brand_kits()]}


@router.post("/brand-kits")
async def create_brand_kit(values: dict[str, Any]):
    return BrandKitService().create_brand_kit(values).to_dict()


@router.patch("/brand-kits/{brand_id}")
async def update_brand_kit(brand_id: str, values: dict[str, Any]):
    updated = BrandKitService().update_brand_kit(brand_id, values)
    if not updated:
        raise HTTPException(status_code=404, detail="Brand kit not found")
    return updated.to_dict()


@router.delete("/brand-kits/{brand_id}")
async def delete_brand_kit(brand_id: str):
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
                "subtitle_style": template.subtitle_style.__dict__,
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
            return FileResponse(str(path), media_type="image/png", filename=path.name)
    raise HTTPException(status_code=404, detail="Template not found")


@router.get("/voices")
async def list_voice_references():
    service = VoiceReferenceService()
    return {"items": [_voice_to_dict(item) for item in service.list_references()]}


@router.post("/voices")
async def upload_voice_reference(
    name: Annotated[str, Form()],
    file: Annotated[UploadFile, File()],
):
    payload = await _read_upload(file)
    service = VoiceReferenceService()
    try:
        info = service.save_reference(name=name.strip() or _default_name(file), audio_bytes=payload, ext=_ext(file))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return _voice_to_dict(info)


@router.get("/voices/{reference_id}/file")
async def get_voice_reference_file(reference_id: str):
    service = VoiceReferenceService()
    path = service.get_reference_path(reference_id)
    if not path:
        raise HTTPException(status_code=404, detail="Voice reference not found")
    return FileResponse(path, filename=Path(path).name)


@router.delete("/voices/{reference_id}")
async def delete_voice_reference(reference_id: str):
    return {"deleted": VoiceReferenceService().delete_reference(reference_id)}


@router.get("/portraits")
async def list_portraits():
    service = PortraitService()
    return {"items": [_portrait_to_dict(item) for item in service.list_portraits()]}


@router.post("/portraits")
async def upload_portrait(
    name: Annotated[str, Form()],
    file: Annotated[UploadFile, File()],
):
    payload = await _read_upload(file)
    service = PortraitService()
    try:
        info = service.save_portrait(name=name.strip() or _default_name(file), image_bytes=payload, ext=_ext(file))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return _portrait_to_dict(info)


@router.get("/portraits/{portrait_id}/file")
async def get_portrait_file(portrait_id: str):
    service = PortraitService()
    path = service.get_portrait_path(portrait_id)
    if not path:
        raise HTTPException(status_code=404, detail="Portrait not found")
    return FileResponse(path, filename=Path(path).name)


@router.delete("/portraits/{portrait_id}")
async def delete_portrait(portrait_id: str):
    return {"deleted": PortraitService().delete_portrait(portrait_id)}


@router.get("/videos")
async def list_video_assets():
    service = VideoAssetService()
    return {"items": [_video_to_dict(item) for item in service.list_assets()]}


@router.post("/videos")
async def upload_video_asset(
    name: Annotated[str, Form()],
    file: Annotated[UploadFile, File()],
):
    payload = await _read_upload(file)
    service = VideoAssetService()
    try:
        info = service.save_asset(name=name.strip() or _default_name(file), video_bytes=payload, ext=_ext(file))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return _video_to_dict(info)


@router.get("/videos/{asset_id}/file")
async def get_video_asset_file(asset_id: str):
    service = VideoAssetService()
    path = service.get_asset_path(asset_id)
    if not path:
        raise HTTPException(status_code=404, detail="Video asset not found")
    return FileResponse(path, filename=Path(path).name)


@router.get("/videos/{asset_id}/thumbnail")
async def get_video_asset_thumbnail(asset_id: str):
    for item in VideoAssetService().list_assets():
        if item.asset_id == asset_id and item.thumbnail_exists():
            return FileResponse(item.thumbnail_path(), filename=Path(item.thumbnail_path()).name)
    raise HTTPException(status_code=404, detail="Video asset thumbnail not found")


@router.delete("/videos/{asset_id}")
async def delete_video_asset(asset_id: str):
    return {"deleted": VideoAssetService().delete_asset(asset_id)}


async def _read_upload(file: UploadFile) -> bytes:
    if not file.filename:
        raise HTTPException(status_code=400, detail="Missing upload filename")
    return await file.read()


def _ext(file: UploadFile) -> str:
    return Path(file.filename or "").suffix


def _default_name(file: UploadFile) -> str:
    return Path(file.filename or "未命名素材").stem or "未命名素材"


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
