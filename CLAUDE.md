# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

Pixelle-Video is a desktop-first AI content and short-video workbench. The current product combines a React/Tauri desktop UI, a local FastAPI sidecar, and Python AI/media capabilities. It includes the application center, brand/project workflow, asset library, instant video creation, digital-human generation, and human-confirmed multi-platform publishing.

## Project-wide development principles

Before planning or implementing any feature, refactor, UI change, architecture change, automation, contract, or infrastructure, read and follow:

- `docs/development-principles.md`

Read only the relevant sections of `docs/engineering-playbook.md` for detailed examples and boundary guidance. Low-risk changes do not require a full playbook read; architecture, security, persistence, migration, cross-process, or infrastructure changes require the relevant ADRs and playbook sections.

Start from the current real problem, identify the root cause, and prefer the smallest sufficient change. "Smallest sufficient" must still preserve correctness, stability, security, maintainability, and proportionate extensibility; it does not mean demo-only or low-quality code. Keep feature-specific problems inside the feature unless a stable shared need has been demonstrated. Contracts protect objective boundaries; they do not replace product, content, visual, or other subjective judgment.

Do not add speculative branches for low-probability, low-impact scenarios. Fail clearly instead. Merge user-facing functionality only as a complete vertical slice; placeholder buttons, unused endpoints, unreachable adapters, fake-success implementations, and compatibility paths without a removal condition are not complete.

Backward compatibility is not the default. Existing code, tests, fixtures, or draft contracts are not evidence of a real compatibility requirement. Prefer updating callers and migrating real data in the same controlled cutover stage or release. Add a temporary compatibility layer only for proven live consumers or data that cannot be migrated safely, with one authoritative path and an explicit removal stage or date. Never stack compatibility layers.

Apply process in proportion to risk: low-risk fixes need a concise problem/root-cause/change/verification note; normal features need a lightweight vertical-slice plan; architecture, security, persistence, migration, irreversible external actions, and new infrastructure need a full plan and, when the long-term decision changes, an ADR. Choose the lowest-complexity implementation that still places logic in the correct layer; do not grow a router, page, or oversized service merely to avoid creating a focused module.

Pixelle's default engineering style is agile vertical delivery with continuous design, a modular monolith, feature-first organization, semantic design tokens, and Ports/Adapters only at real external or replaceable boundaries. Reuse semantically matching framework and project capabilities before creating new ones. Splitting a function, component, hook, style file, or feature-local service for clear responsibility does not require multiple callers and is not a shared abstraction; only promotion into cross-feature shared code requires stable semantics and proven consumers.

Prefer semantically matching project capabilities first, then mature capabilities already provided by React, Ant Design, Tauri, FastAPI, Pydantic, Python, Vitest, Testing Library, and pytest. Keep dependency assembly in composition roots, validate untrusted input at boundaries, and centralize authorization rules. Use queues for real asynchronous, recovery, concurrency, or external-side-effect needs. Use events for facts that require independent consumers, cross-process delivery, reliable asynchronous delivery, or independent producer/consumer lifecycles; do not hide required synchronous order behind events. Do not use a service container as a hidden global service locator.

Distinguish temporary rollout/migration flags from durable product/policy flags. Temporary flags need removal conditions. Durable product flags need stable business semantics, ownership, defaults, permission boundaries, and tests; they must not preserve two authoritative implementations.

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

# Python tests
uv run pytest
uv run pytest tests/path/to/test_file.py::test_name

# Desktop development and tests
cd desktop
npm run dev
npm run test
npm run build
npm run tauri:dev
```

## Architecture

**Current product runtime:**

```
desktop/            React + TypeScript + Tauri desktop product
api/                FastAPI transport layer and desktop sidecar entry
pixelle_video/      Python domain, AI, media, publishing, and persistence capabilities
tests/              Python contract, integration, desktop, publishing, and workflow tests
web/                Legacy Streamlit surface; not the product architecture authority unless a task explicitly targets it
```

The near-term architecture is a modular monolith: React/Tauri → FastAPI API layer → domain services/repositories/executors → Python AI/media providers and local persistence. Routers handle transport and authorization, not business rules. UI state does not define domain state. Each business fact has one authoritative owner.

**Application center and project workflow** — Application Registry holds manifests; projects hold reusable business context; AppRun records one execution; Artifact/ArtifactVersion owns generated facts and versions; generic tasks expose progress rather than replacing domain state. Brand kits remain the authoritative enterprise-information source and projects pin the selected brand-kit version.

**Publishing** — Account profiles, publish packages, PublishRun/Step state, browser automation, and human-confirmed final publishing are owned by the publishing domain. The application center hands off a `publish_package_ref`; it must not create a second publish-package authority.

**`pixelle_video/service.py`** — `PixelleVideoCore` initializes shared AI/media capabilities and is exposed through FastAPI dependency injection. Do not add new business rules to the core singleton. A workflow should use a narrow Port when it crosses an external provider, database, filesystem, operating-system, cross-process, or confirmed replaceable boundary; internal single implementations can use direct functions and feature-local services.

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
- `app.py` — FastAPI app with lifespan, sidecar startup/shutdown, CORS middleware, and versioned routers under `/api/`
- `dependencies.py` — lazy-initialized `PixelleVideoCore` singleton, injected as `PixelleVideoDep`
- `routers/app_center.py` and related domain services — application catalog, projects, runs, artifacts, handoff, and result history
- `routers/publish.py` / `publish_v2.py` and publish services — account management, publish preparation, batch queue, recovery, and human confirmation
- `tasks/manager.py` — generic task execution/progress support; it must not become the authoritative Project/AppRun/PublishRun state model

**Resource resolution** (`pixelle_video/utils/os_util.py`): custom user resources in `data/` (mounted volume in Docker) override built-in resources in `bgm/`, `templates/`, `workflows/` — checked via `get_resource_path()`.

## Docker

Docker Compose runs three services: `init` (ensures `config.yaml` exists), `api` (FastAPI on 8000), `web` (Streamlit on 8501). Build arg `USE_CN_MIRROR=true` enables China mirrors.

## Key constraints

- `moviepy==1.0.3` is pinned (do not upgrade — newer versions have breaking API changes)
- `edge-tts==7.2.7` is pinned (newer versions have stability issues)
- Playwright Chromium must be installed (`playwright install --with-deps chromium`) for HTML frame rendering
- FFmpeg must be available on the system PATH
- Python tests live under `tests/`; desktop Vitest suites live under `desktop/src/`
