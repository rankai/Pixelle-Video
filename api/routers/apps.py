"""Read-only application-center registry endpoints."""

from fastapi import APIRouter, HTTPException

from pixelle_video.app_center.registry import get_app, get_app_readiness, list_effective_apps

router = APIRouter(tags=["Application Center"])


@router.get("/apps")
async def list_apps():
    return {"schema_version": 1, "apps": list_effective_apps()}


@router.get("/apps/{app_id}")
async def read_app(app_id: str):
    app = get_app(app_id)
    if app is None:
        raise HTTPException(status_code=404, detail="应用不存在")
    return app


@router.get("/apps/{app_id}/readiness")
async def read_app_readiness(app_id: str):
    readiness = get_app_readiness(app_id)
    if readiness is None:
        raise HTTPException(status_code=404, detail="应用不存在")
    return readiness
