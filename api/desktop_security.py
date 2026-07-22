"""Desktop-mode security helpers for the local FastAPI sidecar."""

import os
import secrets
from collections.abc import Callable

from fastapi import HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

DESKTOP_TOKEN_HEADER = "X-Pixelle-Desktop-Token"
LOCAL_CAPABILITY_HEADER = "X-Pixelle-Local-Capability"


def is_desktop_mode() -> bool:
    return os.getenv("PIXELLE_DESKTOP_MODE", "").lower() in {"1", "true", "yes", "on"}


def get_desktop_token() -> str:
    return os.getenv("PIXELLE_DESKTOP_TOKEN", "")


def get_desktop_origin() -> str:
    return os.getenv("PIXELLE_DESKTOP_ORIGIN", "tauri://localhost")


def publish_v2_enabled() -> bool:
    return os.getenv("PIXELLE_PUBLISH_V2_ENABLED", "false").lower() in {"1", "true", "yes", "on"}


def require_publish_v2_enabled() -> None:
    if not publish_v2_enabled():
        raise HTTPException(status_code=404, detail="V2_DISABLED")


def issue_local_capability() -> str:
    """Create a capability value for a desktop launch without logging it."""
    return secrets.token_urlsafe(32)


def require_local_capability(request: Request) -> None:
    """Guard V2 mutating operations to the local desktop origin/token."""
    if not is_desktop_mode():
        raise HTTPException(status_code=403, detail="DESKTOP_LOCAL_ONLY")
    allowed_origins = {item.strip() for item in os.getenv("PIXELLE_DESKTOP_ALLOWED_ORIGINS", get_desktop_origin()).split(",") if item.strip()}
    origin = request.headers.get("origin")
    if origin and origin not in allowed_origins:
        raise HTTPException(status_code=403, detail="ORIGIN_NOT_ALLOWED")
    configured = os.getenv("PIXELLE_LOCAL_CAPABILITY", "") or get_desktop_token()
    presented = request.headers.get(LOCAL_CAPABILITY_HEADER)
    if not presented:
        authorization = request.headers.get("authorization", "")
        presented = authorization.removeprefix("Bearer ").strip() if authorization.startswith("Bearer ") else ""
    if not configured or not presented or not secrets.compare_digest(presented, configured):
        raise HTTPException(status_code=403, detail="CAPABILITY_REQUIRED")


class DesktopTokenMiddleware(BaseHTTPMiddleware):
    """Require a per-launch token for local desktop API calls."""

    def __init__(self, app, token: str):
        super().__init__(app)
        self._token = token

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        if request.method == "OPTIONS":
            return await call_next(request)
        if not request.url.path.startswith("/api/"):
            return await call_next(request)
        if not self._token:
            return JSONResponse(
                {"detail": "Desktop token is not configured"},
                status_code=500,
            )
        if request.headers.get(DESKTOP_TOKEN_HEADER) != self._token:
            return JSONResponse(
                {"detail": "Invalid desktop token"},
                status_code=401,
            )
        return await call_next(request)
