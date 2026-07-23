# Copyright (C) 2025 AIDC-AI
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#     http://www.apache.org/licenses/LICENSE-2.0
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
AI-Video-Factory FastAPI Application

Main FastAPI app with all routers and middleware.

Run this script to start the FastAPI server:
    uv run python api/app.py

Or with custom settings:
    uv run python api/app.py --host 0.0.0.0 --port 8080 --reload
"""

# ruff: noqa: E402

import sys
from pathlib import Path

# Add project root to sys.path for module imports
# This ensures imports work correctly in both development and packaged environments
_script_dir = Path(__file__).resolve().parent
_project_root = _script_dir.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

import argparse
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from api.config import api_config
from api.dependencies import shutdown_pixelle_video
from api.desktop_security import (
    DesktopTokenMiddleware,
    get_desktop_origin,
    get_desktop_token,
    is_desktop_mode,
)

# Import routers
from api.routers import (
    app_center_router,
    apps_router,
    assets_router,
    assets_v2_router,
    content_router,
    desktop_router,
    files_router,
    frame_router,
    health_router,
    image_router,
    ip_broadcast_app_router,
    ip_broadcast_router,
    llm_router,
    publish_router,
    publish_v2_router,
    resources_router,
    tasks_router,
    tts_router,
    video_router,
)
from api.tasks import task_manager


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan manager

    Handles startup and shutdown events.
    """
    # Startup
    logger.info("🚀 Starting AI-Video-Factory API...")
    await task_manager.start()
    # Recover durable PublishRun facts before serving requests.  A browser
    # process may disappear with the sidecar; the run must not remain forever
    # in ``running`` or permit a blind duplicate upload after restart.
    from api.routers.publish_v2 import get_publish_run_service

    get_publish_run_service()
    logger.info("✅ AI-Video-Factory API started successfully\n")

    yield

    # Shutdown
    logger.info("🛑 Shutting down AI-Video-Factory API...")
    await task_manager.stop()
    await shutdown_pixelle_video()
    logger.info("✅ AI-Video-Factory API shutdown complete")


# Create FastAPI app
app = FastAPI(
    title="AI-Video-Factory API",
    description="""
    ## AI-Video-Factory - AI Video Generation Platform API
    
    ### Features
    - 🤖 **LLM**: Large language model integration
    - 🔊 **TTS**: Text-to-speech synthesis
    - 🎨 **Image**: AI image generation
    - 📝 **Content**: Automated content generation
    - 🎬 **Video**: End-to-end video generation
    
    ### Video Generation Modes
    - **Sync**: `/api/video/generate/sync` - For small videos (< 30s)
    - **Async**: `/api/video/generate/async` - For large videos with task tracking
    
    ### Getting Started
    1. Check health: `GET /health`
    2. Generate narrations: `POST /api/content/narration`
    3. Generate video: `POST /api/video/generate/sync` or `/async`
    4. Track task progress: `GET /api/tasks/{task_id}`
    """,
    version="0.1.0",
    docs_url=None if is_desktop_mode() else api_config.docs_url,
    redoc_url=None if is_desktop_mode() else api_config.redoc_url,
    openapi_url=None if is_desktop_mode() else api_config.openapi_url,
    lifespan=lifespan,
)

# Add CORS middleware
if api_config.cors_enabled:
    cors_origins = [get_desktop_origin()] if is_desktop_mode() else api_config.cors_origins
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    logger.info(f"CORS enabled for origins: {cors_origins}")

if is_desktop_mode():
    app.add_middleware(DesktopTokenMiddleware, token=get_desktop_token())

# Include routers
# Health check (no prefix)
app.include_router(health_router)
app.include_router(desktop_router, prefix=api_config.api_prefix)
app.include_router(assets_router, prefix=api_config.api_prefix)
app.include_router(assets_v2_router, prefix=api_config.api_prefix)
app.include_router(apps_router, prefix=api_config.api_prefix)
app.include_router(app_center_router, prefix=api_config.api_prefix)

# API routers (with /api prefix)
app.include_router(llm_router, prefix=api_config.api_prefix)
app.include_router(tts_router, prefix=api_config.api_prefix)
app.include_router(image_router, prefix=api_config.api_prefix)
app.include_router(ip_broadcast_router, prefix=api_config.api_prefix)
app.include_router(ip_broadcast_app_router, prefix=api_config.api_prefix)
app.include_router(publish_router, prefix=api_config.api_prefix)
app.include_router(publish_v2_router, prefix=api_config.api_prefix)
app.include_router(content_router, prefix=api_config.api_prefix)
app.include_router(video_router, prefix=api_config.api_prefix)
app.include_router(tasks_router, prefix=api_config.api_prefix)
app.include_router(files_router, prefix=api_config.api_prefix)
app.include_router(resources_router, prefix=api_config.api_prefix)
app.include_router(frame_router, prefix=api_config.api_prefix)


@app.get("/")
async def root():
    """Root endpoint with API information"""
    return {
        "service": "AI-Video-Factory API",
        "version": "0.1.0",
        "docs": api_config.docs_url,
        "health": "/health",
        "api": {
            "llm": f"{api_config.api_prefix}/llm",
            "tts": f"{api_config.api_prefix}/tts",
            "image": f"{api_config.api_prefix}/image",
            "content": f"{api_config.api_prefix}/content",
            "video": f"{api_config.api_prefix}/video",
            "tasks": f"{api_config.api_prefix}/tasks",
            "files": f"{api_config.api_prefix}/files",
            "resources": f"{api_config.api_prefix}/resources",
            "frame": f"{api_config.api_prefix}/frame",
        },
    }


if __name__ == "__main__":
    import uvicorn

    # Parse command line arguments
    parser = argparse.ArgumentParser(description="Start AI-Video-Factory API Server")
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind to")
    parser.add_argument("--port", type=int, default=8000, help="Port to bind to")
    parser.add_argument("--reload", action="store_true", help="Enable auto-reload")

    args = parser.parse_args()

    # Keep the frozen sidecar startup output ASCII-only.  Windows runners and
    # some end-user consoles still expose cp1252 stdout; box-drawing or CJK
    # banner characters would raise UnicodeEncodeError before uvicorn starts.
    print(
        "\n=== Pixelle-Video API Server ===\n"
        f"Starting server at http://{args.host}:{args.port}\n"
        f"API Docs: http://{args.host}:{args.port}/docs\n"
        f"ReDoc: http://{args.host}:{args.port}/redoc\n\n"
        "Press Ctrl+C to stop the server\n"
    )

    # PyInstaller executes this file as ``__main__`` and does not expose the
    # source package as an importable ``api.app`` module.  Pass the already
    # constructed ASGI app directly in the frozen sidecar; keep the import
    # string for normal development so ``--reload`` continues to work.
    server_app = app if getattr(sys, "frozen", False) else "api.app:app"

    # Start server
    uvicorn.run(
        server_app,
        host=args.host,
        port=args.port,
        reload=args.reload,
    )
