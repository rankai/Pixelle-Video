"""Desktop-mode security helpers for the local FastAPI sidecar."""

import os
from collections.abc import Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

DESKTOP_TOKEN_HEADER = "X-Pixelle-Desktop-Token"


def is_desktop_mode() -> bool:
    return os.getenv("PIXELLE_DESKTOP_MODE", "").lower() in {"1", "true", "yes", "on"}


def get_desktop_token() -> str:
    return os.getenv("PIXELLE_DESKTOP_TOKEN", "")


def get_desktop_origin() -> str:
    return os.getenv("PIXELLE_DESKTOP_ORIGIN", "tauri://localhost")


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
