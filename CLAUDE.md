# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

Pixelle-Video is an AI-powered automated short-video engine. Given a topic, it generates a complete video: LLM-written script → AI-generated images/video clips → TTS narration → frame composition via HTML templates → FFmpeg concatenation with BGM.

## Development commands

This project uses `uv` for environment management (Python >= 3.11).

```bash
# Install dependencies (editable install)
uv pip install -e .

# Install dev dependencies
uv pip install -e ".[dev]"

# Start the FastAPI backend (port 8000)
uv run python api/app.py              # default
uv run python api/app.py --reload     # with hot reload

# Start the Streamlit web UI (port 8501)
uv run streamlit run web/app.py --server.port 8501 --server.address 0.0.0.0

# Lint
uv run ruff check .

# Format
uv run ruff format .

# Tests (no tests directory exists yet; pyproject.toml expects them at tests/)
uv run pytest
uv run pytest tests/path/to/test_file.py::test_name
```

## Architecture

**Two entry points, one core library:**

```
api/          FastAPI backend (port 8000)
web/          Streamlit frontend (port 8501) — multi-page: Home + History
pixelle_video/     Core library shared by both
```

**`pixelle_video/service.py`** — `PixelleVideoCore`, the central singleton. Initializes all services and pipelines. Accessed via the global `pixelle_video` instance or FastAPI's dependency injection (`PixelleVideoDep`).

**Services** (`pixelle_video/services/`):
- `LLMService` — OpenAI-SDK-compatible wrapper, supports structured output via Pydantic models. Any provider works (OpenAI, Qwen, DeepSeek, Ollama, etc.)
- `TTSService` — Dual-mode: local Edge-TTS or ComfyUI workflows
- `MediaService` — Image/video generation via ComfyKit (ComfyUI or RunningHub)
- `frame_processor.py` — Orchestrates per-frame work: TTS → media gen → HTML template rendering → video segment assembly
- `frame_html.py` — `HTMLFrameGenerator`, renders HTML templates to PNG images using Playwright (headless Chromium)
- `video.py` (VideoService) — FFmpeg operations: concatenation, BGM mixing
- `persistence.py` / `history_manager.py` — Task metadata and storyboard persistence to `output/`

**Pipelines** (`pixelle_video/pipelines/`) — the video generation strategy layer:
- `BasePipeline` — abstract base; receives `PixelleVideoCore`, implements `async __call__(text, progress_callback, **kwargs) → VideoGenerationResult`
- `LinearVideoPipeline` — Template Method pattern with 8 lifecycle steps: `setup_environment → generate_content → determine_title → plan_visuals → initialize_storyboard → produce_assets → post_production → finalize`. Uses `PipelineContext` dataclass for state.
- `StandardPipeline` — default pipeline. Two modes: `generate` (LLM creates narrations from topic) and `fixed` (split user-provided script by paragraph/line/sentence). Supports parallel RunningHub execution via `asyncio.Semaphore`.
- `CustomPipeline` — user-extensible template pipeline
- `AssetBasedPipeline` — handles user-uploaded media (photos/videos) with AI analysis

**Content generators** (`pixelle_video/utils/content_generators.py`) — stateless LLM-powered functions: `generate_narrations_from_topic`, `split_narration_script`, `generate_image_prompts`, `generate_title`. These are pipeline-agnostic.

**Templates** (`templates/`) — HTML frame templates organized by resolution: `1080x1920/`, `1080x1080/`, `1920x1080/`. Naming convention: `image_*.html` (needs AI images), `video_*.html` (needs AI video clips), `static_*.html` (text-only, no media generation). Resolution is parsed from the parent directory name.

**Workflows** (`workflows/`) — JSON ComfyUI/RunningHub workflow files: `selfhost/` (local ComfyUI) and `runninghub/` (cloud API). Referenced by path in config (e.g., `runninghub/image_flux.json`).

**Configuration** — `config.example.yaml` is the template; copy to `config.yaml` for actual use. Pydantic schema in `pixelle_video/config/schema.py` validates all fields. Config supports hot-reload for ComfyKit changes. `pixelle_video/config/manager.py` provides the `config_manager` singleton.

**API layer** (`api/`):
- `app.py` — FastAPI app with lifespan (starts TaskManager on boot, cleans up on shutdown), CORS middleware, 10 routers under `/api/`
- `dependencies.py` — lazy-initialized `PixelleVideoCore` singleton, injected as `PixelleVideoDep`
- `tasks/manager.py` — `TaskManager`: in-memory async task queue with create/execute/cancel/list/cleanup. Used by `/api/video/generate/async`.

**Resource resolution** (`pixelle_video/utils/os_util.py`): custom user resources in `data/` (mounted volume in Docker) override built-in resources in `bgm/`, `templates/`, `workflows/` — checked via `get_resource_path()`.

## Docker

Docker Compose runs three services: `init` (ensures `config.yaml` exists), `api` (FastAPI on 8000), `web` (Streamlit on 8501). Build arg `USE_CN_MIRROR=true` enables China mirrors.

## Key constraints

- `moviepy==1.0.3` is pinned (do not upgrade — newer versions have breaking API changes)
- `edge-tts==7.2.7` is pinned (newer versions have stability issues)
- Playwright Chromium must be installed (`playwright install --with-deps chromium`) for HTML frame rendering
- FFmpeg must be available on the system PATH
- No test suite exists yet (testpaths configured but directory not created)
