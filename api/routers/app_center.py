from __future__ import annotations

import asyncio
from functools import lru_cache
from pathlib import Path

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import FileResponse

from api.schemas.app_center import (
    AppRunCreateRequest,
    AppRunDraftUpdateRequest,
    AppRunExecutionAccepted,
    AppRunResponse,
    AppRunTransitionRequest,
    ArtifactHandoffCreateRequest,
    ArtifactVersionCreateRequest,
    CarouselPageRetryRequest,
    ContentProjectCreateRequest,
    ContentProjectResponse,
    ContentProjectUpdateRequest,
    ContextSnapshotCreateRequest,
)
from pixelle_video.app_center.carousel import (
    DouyinCarouselExecutor,
    DouyinCarouselRenderer,
    resolve_registered_asset,
)
from pixelle_video.app_center.ip_broadcast_adapter import IpBroadcastAdapterError
from pixelle_video.app_center.llm_port import ConfigAppLLMPort
from pixelle_video.app_center.models import AppRun, ContentProject
from pixelle_video.app_center.registry import get_app
from pixelle_video.app_center.repository import (
    AppCenterRepository,
    AppCenterRepositoryError,
    NotFound,
)
from pixelle_video.app_center.runner import AppRunner, AppRunnerConfigurationError
from pixelle_video.app_center.structured_apps import build_builtin_structured_executors
from pixelle_video.app_center.task_projection import AppRunTaskProjector
from pixelle_video.utils.os_util import get_data_path

router = APIRouter(tags=["application-center-core"])
_running_app_jobs: dict[str, asyncio.Task] = {}


@lru_cache(maxsize=1)
def get_app_center_repository() -> AppCenterRepository:
    return AppCenterRepository()


def get_app_center_runner() -> AppRunner:
    repository = get_app_center_repository()
    executors = build_builtin_structured_executors(repository, ConfigAppLLMPort())
    executors["builtin.douyin-carousel"] = DouyinCarouselExecutor(
        DouyinCarouselRenderer(asset_resolver=resolve_registered_asset),
        repository=repository,
        llm_port=ConfigAppLLMPort(),
    )
    return AppRunner(
        repository,
        executors=executors,
        task_projector=AppRunTaskProjector(),
    )


def _project_response(project: ContentProject) -> ContentProjectResponse:
    return ContentProjectResponse.model_validate(project.__dict__)


def _run_response(run: AppRun) -> AppRunResponse:
    return AppRunResponse.model_validate(run.__dict__)


def _raise_repository_error(exc: Exception):
    if isinstance(exc, NotFound):
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if isinstance(exc, (AppCenterRepositoryError, ValueError)):
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if isinstance(exc, IpBroadcastAdapterError):
        raise HTTPException(status_code=409, detail={"code": exc.code}) from exc
    if isinstance(exc, AppRunnerConfigurationError):
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    raise exc


@router.post("/content-projects", response_model=ContentProjectResponse, status_code=status.HTTP_201_CREATED)
def create_content_project(request: ContentProjectCreateRequest):
    return _project_response(get_app_center_repository().create_project(request.name, request.primary_goal, request.brand_id))


@router.get("/content-projects", response_model=list[ContentProjectResponse])
def list_content_projects(include_archived: bool = False):
    return [_project_response(item) for item in get_app_center_repository().list_projects(include_archived)]


@router.get("/content-projects/{project_id}", response_model=ContentProjectResponse)
def get_content_project(project_id: str):
    try:
        return _project_response(get_app_center_repository().get_project(project_id))
    except Exception as exc:
        _raise_repository_error(exc)


@router.patch("/content-projects/{project_id}", response_model=ContentProjectResponse)
def update_content_project(project_id: str, request: ContentProjectUpdateRequest):
    try:
        return _project_response(get_app_center_repository().update_project(project_id, name=request.name, primary_goal=request.primary_goal))
    except Exception as exc:
        _raise_repository_error(exc)


@router.post("/content-projects/{project_id}/archive", response_model=ContentProjectResponse)
def archive_content_project(project_id: str):
    try:
        return _project_response(get_app_center_repository().archive_project(project_id))
    except Exception as exc:
        _raise_repository_error(exc)


@router.post("/content-projects/{project_id}/context-snapshots", status_code=status.HTTP_201_CREATED)
def save_context_snapshot(project_id: str, request: ContextSnapshotCreateRequest):
    try:
        snapshot = get_app_center_repository().save_context_snapshot(
            project_id,
            request.payload,
            source_brand_id=request.source_brand_id,
            source_brand_revision_id=request.source_brand_revision_id,
        )
        return snapshot.__dict__
    except Exception as exc:
        _raise_repository_error(exc)


@router.get("/content-projects/{project_id}/context-snapshots")
def get_current_context_snapshot(project_id: str):
    try:
        project = get_app_center_repository().get_project(project_id)
        if not project.current_context_snapshot_id:
            return None
        return get_app_center_repository().get_context_snapshot(project.current_context_snapshot_id).__dict__
    except Exception as exc:
        _raise_repository_error(exc)


@router.post("/app-runs", response_model=AppRunResponse, status_code=status.HTTP_201_CREATED)
def create_app_run(request: AppRunCreateRequest):
    try:
        run = get_app_center_repository().create_app_run(
            request.project_id,
            request.app_id,
            request.app_version,
            request.input_payload,
            idempotency_key=request.idempotency_key,
            context_snapshot_id=request.context_snapshot_id,
            prompt_version=request.prompt_version,
            session_id=request.session_id,
        )
        return _run_response(run)
    except Exception as exc:
        _raise_repository_error(exc)


@router.get("/app-runs", response_model=list[AppRunResponse])
def list_app_runs(project_id: str | None = None):
    return [_run_response(item) for item in get_app_center_repository().list_app_runs(project_id)]


@router.get("/app-runs/{app_run_id}", response_model=AppRunResponse)
def get_app_run(app_run_id: str):
    try:
        return _run_response(get_app_center_repository().get_app_run(app_run_id))
    except Exception as exc:
        _raise_repository_error(exc)


@router.post("/app-runs/{app_run_id}/transition", response_model=AppRunResponse)
def transition_app_run(app_run_id: str, request: AppRunTransitionRequest):
    try:
        repository = get_app_center_repository()
        current = repository.get_app_run(app_run_id)
        if current.app_id == "builtin.digital-human-video" and request.state == "completed":
            # Digital-human completion is a reviewed imported-output handoff,
            # never a generic state-machine transition.  Keep the strict
            # accept endpoint as the sole public completion path.
            raise IpBroadcastAdapterError("ARTIFACT_ACCEPT_EXPLICIT_REQUIRED", app_run_id)
        return _run_response(repository.transition_app_run(app_run_id, request.state, expected_state_version=request.expected_state_version))
    except Exception as exc:
        _raise_repository_error(exc)


@router.patch("/app-runs/{app_run_id}/draft", response_model=AppRunResponse)
def update_app_run_draft(app_run_id: str, request: AppRunDraftUpdateRequest):
    try:
        repository = get_app_center_repository()
        current = repository.get_app_run(app_run_id)
        values = request.model_dump(exclude_unset=True)
        values.setdefault("input_payload", current.input_payload)
        values.setdefault("context_snapshot_id", current.context_snapshot_id)
        values.setdefault("prompt_version", current.prompt_version)
        values.setdefault("session_id", current.session_id)
        return _run_response(repository.update_app_run_draft(app_run_id, **values))
    except Exception as exc:
        _raise_repository_error(exc)


@router.post("/app-runs/{app_run_id}/retry", response_model=AppRunResponse)
def retry_app_run(app_run_id: str):
    try:
        return _run_response(get_app_center_runner().retry(app_run_id))
    except Exception as exc:
        _raise_repository_error(exc)


@router.post("/app-runs/{app_run_id}/cancel", response_model=AppRunResponse)
def cancel_app_run(app_run_id: str):
    try:
        result = get_app_center_runner().cancel(app_run_id)
        job = _running_app_jobs.get(app_run_id)
        if job and not job.done():
            job.cancel()
        return _run_response(result)
    except Exception as exc:
        _raise_repository_error(exc)


@router.post("/app-runs/{app_run_id}/archive", response_model=AppRunResponse)
def archive_app_run(app_run_id: str):
    try:
        return _run_response(get_app_center_repository().archive_app_run(app_run_id))
    except Exception as exc:
        _raise_repository_error(exc)


@router.post("/app-runs/{app_run_id}/complete", response_model=AppRunResponse)
def complete_app_run(app_run_id: str):
    try:
        run = get_app_center_repository().get_app_run(app_run_id)
        if run.app_id == "builtin.digital-human-video":
            # Digital-human AppRuns have a stricter legacy-output review
            # contract than the generic fake/structured runner.  The generic
            # endpoint must never become an alternate success path (or expose
            # the full AppRun payload); callers must use the dedicated,
            # redacted IP-broadcast accept endpoint.
            raise IpBroadcastAdapterError("ARTIFACT_ACCEPT_EXPLICIT_REQUIRED", app_run_id)
        return _run_response(get_app_center_runner().accept_output(app_run_id))
    except Exception as exc:
        _raise_repository_error(exc)


@router.post("/app-runs/{app_run_id}/complete-review", response_model=AppRunResponse)
def complete_app_run_review(app_run_id: str):
    return complete_app_run(app_run_id)


@router.post("/app-runs/{app_run_id}/execute", response_model=AppRunExecutionAccepted, status_code=status.HTTP_202_ACCEPTED)
async def execute_app_run(app_run_id: str):
    """Execute a registered application through the shared structured runner."""

    repository = get_app_center_repository()
    try:
        run = repository.get_app_run(app_run_id)
        manifest = get_app(run.app_id)
        if manifest is None or manifest["version"] != run.app_version:
            raise HTTPException(status_code=409, detail="应用版本未登记")
        readiness = manifest["readiness"]
        if not manifest["enabled"] or readiness["status"] != "ready":
            raise HTTPException(status_code=409, detail={"code": "APP_NOT_READY", "readiness": readiness})
        if run.state in {"needs_review", "completed", "cancelled"}:
            raise HTTPException(status_code=409, detail="AppRun 当前状态不可重复执行")
        active_job = _running_app_jobs.get(app_run_id)
        if active_job and not active_job.done():
            attempts = repository.list_attempts(app_run_id)
            active_task_id = attempts[-1].task_id if attempts and attempts[-1].task_id else None
            if active_task_id:
                return {"app_run_id": app_run_id, "task_id": active_task_id, "state": run.state}
            raise HTTPException(status_code=409, detail="AppRun 已有执行任务")
        projector = AppRunTaskProjector()
        attempts = repository.list_attempts(app_run_id)
        existing_task_id = attempts[-1].task_id if attempts and attempts[-1].task_id else None
        task = projector.manager.get_task(existing_task_id) if existing_task_id else None
        if run.state in {"completed", "cancelled", "needs_review", "running"} and task is None:
            raise HTTPException(status_code=409, detail="AppRun 当前状态不可重复执行")
        if task is None:
            task = projector.create(run)
        runner = get_app_center_runner()
        job = asyncio.create_task(runner.run(app_run_id, task_id=task.task_id))
        _running_app_jobs[app_run_id] = job
        job.add_done_callback(lambda _done: _running_app_jobs.pop(app_run_id, None))
        return {"app_run_id": app_run_id, "task_id": task.task_id, "state": "queued"}
    except Exception as exc:
        _raise_repository_error(exc)


@router.get("/artifacts/{artifact_id}")
def get_artifact(artifact_id: str):
    try:
        return get_app_center_repository().get_artifact(artifact_id).__dict__
    except Exception as exc:
        _raise_repository_error(exc)


@router.get("/content-projects/{project_id}/artifacts")
def list_project_artifacts(project_id: str, include_archived: bool = False):
    try:
        return [item.__dict__ for item in get_app_center_repository().list_artifacts(project_id, include_archived=include_archived)]
    except Exception as exc:
        _raise_repository_error(exc)


@router.post("/artifacts/{artifact_id}/archive")
def archive_artifact(artifact_id: str):
    try:
        return get_app_center_repository().archive_artifact(artifact_id).__dict__
    except Exception as exc:
        _raise_repository_error(exc)


@router.get("/artifacts/{artifact_id}/files")
def list_artifact_files(artifact_id: str):
    try:
        get_app_center_repository().get_artifact(artifact_id)
        return [file_ref for version in get_app_center_repository().list_artifact_versions(artifact_id) for file_ref in version.file_refs]
    except Exception as exc:
        _raise_repository_error(exc)


@router.get("/artifacts/{artifact_id}/files/{file_key}")
def get_artifact_file(artifact_id: str, file_key: str):
    try:
        get_app_center_repository().get_artifact(artifact_id)
        for version in get_app_center_repository().list_artifact_versions(artifact_id):
            for file_ref in version.file_refs:
                if file_ref.get("file_key") == file_key or file_ref.get("key") == file_key:
                    return {"file_key": file_key, "file_ref": file_ref, "artifact_version_id": version.artifact_version_id}
        raise NotFound(f"artifact file not found: {file_key}")
    except Exception as exc:
        _raise_repository_error(exc)


@router.get("/artifacts/{artifact_id}/files/{file_key}/download")
def download_artifact_file(artifact_id: str, file_key: str):
    """Serve an internal carousel export independently of the Publish V2 flag."""
    try:
        artifact = get_app_center_repository().get_artifact(artifact_id)
        if artifact.artifact_type not in {"carousel_package", "carousel_page"}:
            raise AppCenterRepositoryError("ARTIFACT_FILE_DOWNLOAD_UNSUPPORTED")
        file_ref = None
        for version in get_app_center_repository().list_artifact_versions(artifact_id):
            for candidate in version.file_refs:
                if candidate.get("file_key") == file_key or candidate.get("key") == file_key:
                    file_ref = candidate
        if not file_ref:
            raise NotFound(f"artifact file not found: {file_key}")
        root = Path(get_data_path("app_center", "carousel")).resolve()
        raw_path = file_ref.get("relative_path") or file_ref.get("path")
        if not isinstance(raw_path, str) or not raw_path.strip():
            raise AppCenterRepositoryError("ARTIFACT_FILE_PATH_REQUIRED")
        path = (root / raw_path).resolve() if not Path(raw_path).is_absolute() else Path(raw_path).resolve()
        try:
            path.relative_to(root)
        except ValueError as exc:
            raise AppCenterRepositoryError("ARTIFACT_FILE_OUTSIDE_ROOT") from exc
        if not path.is_file():
            raise NotFound(f"artifact file missing: {file_key}")
        return FileResponse(path, media_type=file_ref.get("mime_type"), filename=path.name)
    except Exception as exc:
        _raise_repository_error(exc)


@router.get("/artifact-handoffs/{handoff_id}")
def get_artifact_handoff(handoff_id: str):
    try:
        return get_app_center_repository().get_handoff(handoff_id).__dict__
    except Exception as exc:
        _raise_repository_error(exc)


@router.get("/artifacts/{artifact_id}/versions")
def list_artifact_versions(artifact_id: str):
    try:
        return [item.__dict__ for item in get_app_center_repository().list_artifact_versions(artifact_id)]
    except Exception as exc:
        _raise_repository_error(exc)


@router.post("/artifacts/{artifact_id}/versions", status_code=status.HTTP_201_CREATED)
def append_artifact_version(artifact_id: str, request: ArtifactVersionCreateRequest):
    try:
        version = get_app_center_repository().append_artifact_version(
            artifact_id,
            content=request.content,
            file_refs=request.file_refs,
            source=request.source,
            schema_version=request.schema_version,
        )
        return version.__dict__
    except Exception as exc:
        _raise_repository_error(exc)


@router.post("/artifacts/{artifact_id}/carousel-page/retry", status_code=status.HTTP_201_CREATED)
def retry_carousel_page(artifact_id: str, request: CarouselPageRetryRequest):
    """Re-render one page into a new ArtifactVersion and refresh its package snapshot."""

    try:
        manifest = get_app("builtin.douyin-carousel")
        if manifest is None or not manifest["enabled"]:
            raise AppCenterRepositoryError("APP_NOT_READY")
        repository = get_app_center_repository()
        page_artifact = repository.get_artifact(artifact_id)
        if page_artifact.artifact_type != "carousel_page":
            raise AppCenterRepositoryError("CAROUSEL_PAGE_ARTIFACT_REQUIRED")
        if not page_artifact.current_version_id:
            raise AppCenterRepositoryError("CAROUSEL_PAGE_VERSION_REQUIRED")
        current_page = repository.get_artifact_version(page_artifact.current_version_id)
        page_content = dict(current_page.content or {})
        page_index = page_content.get("page_index")
        if not isinstance(page_index, int) or page_index < 1:
            raise AppCenterRepositoryError("CAROUSEL_PAGE_INDEX_INVALID")
        renderer = DouyinCarouselRenderer(asset_resolver=resolve_registered_asset)
        rendered = renderer.retry_page(
            {
                "page_index": page_index,
                "text": request.text,
                "asset_refs": request.asset_refs,
                "font_id": request.font_id,
                "dimensions": {"width_px": 1080, "height_px": 1440},
            },
            run_ref=page_artifact.source_app_run_id or artifact_id,
            version_number=current_page.version_number + 1,
        )
        page_content.update({
            "text": request.text,
            "asset_refs": list(request.asset_refs),
            "render_state": "ready",
            "retry_of_artifact_version_id": current_page.artifact_version_id,
        })
        next_page = repository.append_artifact_version(
            artifact_id,
            content=page_content,
            file_refs=[rendered.file_ref(renderer.output_root)],
            source="rendered",
        )

        from api.routers.publish_v2 import get_publish_core_repository, get_publish_package_service

        package_version = None
        publish_service = None
        core_repository = None
        publish_package_ids_before: set[str] = set()
        try:
            core_repository = get_publish_core_repository()
            for candidate in repository.list_artifacts(page_artifact.project_id):
                if candidate.artifact_type != "carousel_package" or candidate.source_app_run_id != page_artifact.source_app_run_id or not candidate.current_version_id:
                    continue
                current_package = repository.get_artifact_version(candidate.current_version_id)
                package_content = dict(current_package.content or {})
                page_ids = list(package_content.get("page_artifact_version_ids") or [])
                if current_page.artifact_version_id not in page_ids:
                    continue
                package_content["page_artifact_version_ids"] = [next_page.artifact_version_id if item == current_page.artifact_version_id else item for item in page_ids]
                package_content["retry_of_artifact_version_id"] = current_package.artifact_version_id
                package_refs = [dict(item) for item in current_package.file_refs]
                old_file_key = next((item.get("file_key") for item in current_page.file_refs if item.get("file_key")), None)
                next_file_ref = next_page.file_refs[0] if next_page.file_refs else None
                if old_file_key and next_file_ref:
                    package_refs = [next_file_ref if item.get("file_key") == old_file_key else item for item in package_refs]
                package_version = repository.append_artifact_version(candidate.artifact_id, content=package_content, file_refs=package_refs, source="rendered")
                break
            if package_version is None:
                raise AppCenterRepositoryError("CAROUSEL_PACKAGE_ARTIFACT_REQUIRED")
            previous_packages = core_repository.list_packages_for_source_version(current_page.artifact_version_id)
            publish_service = get_publish_package_service()
            publish_package_ids_before = {
                item.package_id
                for item in core_repository.list_packages_for_source_version(package_version.artifact_version_id)
            }
            publish_package = publish_service.create_from_artifact_versions(
                page_artifact.project_id,
                [package_version.artifact_version_id],
            )
        except Exception as exc:
            if core_repository is not None and package_version is not None:
                for candidate in core_repository.list_packages_for_source_version(package_version.artifact_version_id):
                    if candidate.package_id in publish_package_ids_before or candidate.invalidated_at is not None:
                        continue
                    invalidated = core_repository.invalidate_package(candidate.package_id, "CAROUSEL_RETRY_COMPENSATION")
                    if publish_service is not None:
                        publish_service.invalidate_publish_package_ref(invalidated)
            for created_version in (package_version, next_page):
                if created_version is not None:
                    repository.rollback_artifact_version(created_version.artifact_version_id)
            raise AppCenterRepositoryError("CAROUSEL_RETRY_FAILED") from exc
        for previous in previous_packages:
            if previous.package_id != publish_package.package_id and previous.invalidated_at is None:
                invalidated = core_repository.invalidate_package(previous.package_id, "CAROUSEL_ARTIFACT_VERSION_REPLACED")
                publish_service.invalidate_publish_package_ref(invalidated)
        return {
            "page_artifact_version": next_page.__dict__,
            "package_artifact_version": package_version.__dict__,
            "publish_package": publish_package.model_dump(mode="json"),
            "invalidated_package_ids": [item.package_id for item in previous_packages if item.package_id != publish_package.package_id],
        }
    except Exception as exc:
        _raise_repository_error(exc)


@router.post("/artifact-handoffs", status_code=status.HTTP_201_CREATED)
def create_artifact_handoff(request: ArtifactHandoffCreateRequest):
    try:
        handoff = get_app_center_repository().create_handoff(**request.model_dump())
        return handoff.__dict__
    except Exception as exc:
        _raise_repository_error(exc)


@router.post("/artifacts/{artifact_id}/handoffs", status_code=status.HTTP_201_CREATED)
def create_artifact_handoff_for_artifact(artifact_id: str, request: ArtifactHandoffCreateRequest):
    if request.source_artifact_id != artifact_id:
        raise HTTPException(status_code=409, detail="handoff source artifact does not match path")
    return create_artifact_handoff(request)


@router.get("/artifacts/{artifact_id}/handoffs")
def list_artifact_handoffs(artifact_id: str):
    try:
        return [item.__dict__ for item in get_app_center_repository().list_handoffs(artifact_id)]
    except Exception as exc:
        _raise_repository_error(exc)
