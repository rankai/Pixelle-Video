"""Platform-neutral PUB-2 publishing API; no final-publish endpoint exists."""

import asyncio
import hashlib
import json
import os
from functools import lru_cache
from pathlib import Path
from threading import Lock

from fastapi import APIRouter, Depends, HTTPException, Query, status

from api.desktop_security import (
    is_desktop_mode,
    require_local_capability,
    require_publish_v2_enabled,
)
from api.routers.ip_broadcast import _is_allowed_artifact_path, _session_store
from api.schemas.publish_accounts import (
    PublishAccountCreateRequest,
    PublishAccountListResponse,
)
from api.schemas.publish_v2 import (
    PublishCancelRequest,
    PublishEventsResponse,
    PublishOutcomeRequest,
    PublishPackageCreateRequest,
    PublishPackageFromSessionRequest,
    PublishRetryStepRequest,
    PublishRunAcceptedResponse,
    PublishRunCreateRequest,
    PublishRunResponse,
)
from pixelle_video.app_center.repository import AppCenterRepository, NotFound
from pixelle_video.services.publish.account_models import PublishAccount
from pixelle_video.services.publish.account_repository import (
    PublishAccountConflict,
    PublishAccountNotFound,
    PublishAccountRepository,
)
from pixelle_video.services.publish.account_service import PublishAccountService
from pixelle_video.services.publish.browser_runtime import PlaywrightBrowserRuntime
from pixelle_video.services.publish.core_models import PublishPackageV2, PublishRunState
from pixelle_video.services.publish.core_repository import (
    PublishCoreRepository,
    PublishPackageConflict,
    PublishPackageNotFound,
    PublishRunAlreadyActive,
    PublishRunConcurrencyConflict,
    PublishRunConflict,
    PublishRunNotFound,
)
from pixelle_video.services.publish.execution_protocol import (
    PublishExecutionCheckpoint,
    parse_checkpoint,
)
from pixelle_video.services.publish.media_preflight import MediaPreflightError, preflight_media
from pixelle_video.services.publish.models import PublishPackage
from pixelle_video.services.publish.package_service import (
    PublishPackageBuildError,
    PublishPackageService,
)
from pixelle_video.services.publish.platform_profiles import canonical_platform
from pixelle_video.services.publish.platforms.factory import create_platform_publisher
from pixelle_video.services.publish.profile_manager import BrowserProfileManager, ProfileLockError
from pixelle_video.services.publish.run_service import PublishRunService, PublishRunServiceError

router = APIRouter(prefix="/publish/v2", tags=["Publish V2"], dependencies=[Depends(require_publish_v2_enabled)])
_legacy_handoff_lock = Lock()
_active_v2_runtimes: dict[str, PlaywrightBrowserRuntime] = {}


def _handoff_fingerprint(project_id: str, video_manifest, cover_manifest, platform_copy) -> str:
    """Fingerprint trusted media and copy inputs before deciding whether to replay."""

    payload = {
        "project_id": project_id,
        "video_manifest": video_manifest.model_dump(mode="json"),
        "cover_manifest": cover_manifest.model_dump(mode="json") if cover_manifest else None,
        "platform_copy": platform_copy.model_dump(mode="json"),
    }
    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return f"sha256:{hashlib.sha256(serialized.encode('utf-8')).hexdigest()}"


@lru_cache(maxsize=1)
def get_publish_account_service_v2() -> PublishAccountService:
    repository = get_publish_account_repository()
    return PublishAccountService(
        repository=repository,
        profile_manager=BrowserProfileManager(repository=repository),
    )


@router.get("/accounts", response_model=PublishAccountListResponse)
async def list_publish_accounts_v2(include_archived: bool = False):
    return PublishAccountListResponse(items=get_publish_account_service_v2().list_accounts(include_archived=include_archived))


@router.post("/accounts", response_model=PublishAccount, status_code=status.HTTP_201_CREATED)
async def create_publish_account_v2(payload: PublishAccountCreateRequest, _capability: None = Depends(require_local_capability)):
    try:
        return get_publish_account_service_v2().create_account(payload.platform, payload.display_name, make_default=payload.make_default)
    except PublishAccountConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/accounts/{account_id}", response_model=PublishAccount)
async def get_publish_account_v2(account_id: str):
    try:
        return get_publish_account_service_v2().repository.get_account(account_id)
    except PublishAccountNotFound as exc:
        raise HTTPException(status_code=404, detail="PUBLISH_ACCOUNT_NOT_FOUND") from exc


async def _probe_publish_account_v2(account_id: str):
    try:
        return await get_publish_account_service_v2().probe_account(account_id)
    except PublishAccountNotFound as exc:
        raise HTTPException(status_code=404, detail="PUBLISH_ACCOUNT_NOT_FOUND") from exc


@router.post("/accounts/{account_id}/connect", response_model=PublishAccount, operation_id="connectPublishAccountV2", dependencies=[Depends(require_local_capability)])
async def connect_publish_account_v2(account_id: str):
    return await _probe_publish_account_v2(account_id)


@router.post("/accounts/{account_id}/verify", response_model=PublishAccount, operation_id="verifyPublishAccountV2", dependencies=[Depends(require_local_capability)])
async def verify_publish_account_v2(account_id: str):
    return await _probe_publish_account_v2(account_id)


@router.post("/accounts/{account_id}/open", response_model=PublishAccount, operation_id="openPublishAccountV2", dependencies=[Depends(require_local_capability)])
async def open_publish_account_v2(account_id: str):
    return await _probe_publish_account_v2(account_id)


@router.post("/accounts/{account_id}/make-default", response_model=PublishAccount, dependencies=[Depends(require_local_capability)])
async def make_default_publish_account_v2(account_id: str):
    try:
        return get_publish_account_service_v2().set_default(account_id)
    except PublishAccountNotFound as exc:
        raise HTTPException(status_code=404, detail="PUBLISH_ACCOUNT_NOT_FOUND") from exc
    except PublishAccountConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/accounts/{account_id}/archive", response_model=PublishAccount, dependencies=[Depends(require_local_capability)])
async def archive_publish_account_v2(account_id: str):
    try:
        return get_publish_account_service_v2().archive(account_id)
    except PublishAccountNotFound as exc:
        raise HTTPException(status_code=404, detail="PUBLISH_ACCOUNT_NOT_FOUND") from exc
    except PublishAccountConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/accounts/{account_id}/clear-profile", response_model=PublishAccount, dependencies=[Depends(require_local_capability)])
async def clear_publish_account_v2(account_id: str):
    try:
        return get_publish_account_service_v2().clear_profile(account_id)
    except PublishAccountNotFound as exc:
        raise HTTPException(status_code=404, detail="PUBLISH_ACCOUNT_NOT_FOUND") from exc
    except ProfileLockError as exc:
        raise HTTPException(status_code=409, detail="PROFILE_LOCKED") from exc


@lru_cache(maxsize=1)
def get_publish_core_repository() -> PublishCoreRepository:
    return PublishCoreRepository(Path(os.environ["PIXELLE_PUBLISHING_DB"]) if os.environ.get("PIXELLE_PUBLISHING_DB") else None)


@lru_cache(maxsize=1)
def get_publish_account_repository() -> PublishAccountRepository:
    return PublishAccountRepository(get_publish_core_repository().db_path)


@lru_cache(maxsize=1)
def get_app_center_repository() -> AppCenterRepository:
    return AppCenterRepository(os.getenv("PIXELLE_APP_CENTER_DB"))


@lru_cache(maxsize=1)
def get_publish_package_service() -> PublishPackageService:
    configured_roots = tuple(Path(item).resolve() for item in os.getenv("PIXELLE_PUBLISH_MEDIA_ROOTS", "").split(os.pathsep) if item)
    return PublishPackageService(get_app_center_repository(), get_publish_core_repository(), media_roots=configured_roots or None)


@lru_cache(maxsize=1)
def get_publish_run_service() -> PublishRunService:
    package_service = get_publish_package_service()
    service = PublishRunService(
        get_publish_core_repository(),
        get_publish_account_repository(),
        # Keep lifespan/test seams tolerant of lightweight package-service
        # doubles; the production service always provides this verifier.
        media_verifier=getattr(package_service, "verify_package", None),
        executor=_execute_publish_run,
    )
    service.recover_after_restart()
    return service


async def _close_v2_runtime(run_id: str) -> None:
    runtime = _active_v2_runtimes.pop(run_id, None)
    if runtime is None:
        return
    try:
        await asyncio.wait_for(runtime.close(), timeout=5)
    except Exception:
        # A browser process must not prevent the durable run from reaching
        # ``needs_attention`` or block the next controlled retry.
        return


def _append_adapter_result_event(run_id: str, result, adapter_version: str) -> None:
    """Append adapter outcome using the post-checkpoint CAS version."""

    repository = get_publish_core_repository()
    current = repository.get_run(run_id)
    platform = getattr(result, "platform", "douyin")
    repository.append_event(
        run_id,
        "adapter_result",
        state=current.state,
        state_version=current.state_version,
        payload={
            "step": "adapter_prepare",
            "adapter_version": adapter_version,
            "evidence_kind": f"live_{platform}_dom_readback"
            if result.status.value == "draft_ready"
            else f"live_{platform}_blocker",
            "adapter_state": getattr(result, "adapter_state", None),
            "filled_fields": list(getattr(result, "filled_fields", []) or []),
            "readback_fields": list(getattr(result, "readback_fields", []) or []),
            "platform_fallback_boundaries": list(
                getattr(result, "platform_fallback_boundaries", []) or []
            ),
            "media_readback": bool(getattr(result, "media_readback", False)),
            "cover_readback": bool(getattr(result, "cover_readback", False)),
            "cover_receipt_present": bool(getattr(result, "cover_receipt_present", False)),
            "final_publish_click_count": int(getattr(result, "final_publish_click_count", 0)),
        },
    )


async def _execute_publish_run(run) -> None:
    """Run the selected platform adapter and stop before final publish."""

    adapter_platform = canonical_platform(run.platform.value)
    package = get_publish_core_repository().get_package(run.package_id)
    account = get_publish_account_repository().get_account(run.account_id)
    package_service = get_publish_package_service()
    video_path = package_service.resolve_media_path(package, "video")
    cover_path = package_service.resolve_media_path(package, "cover") if package.cover_manifest else None
    profile_path = BrowserProfileManager(repository=get_publish_account_repository()).profile_path(account)
    runtime = PlaywrightBrowserRuntime()
    _active_v2_runtimes[run.run_id] = runtime
    try:
        previous = parse_checkpoint(run.checkpoint)
    except Exception as exc:
        await _close_v2_runtime(run.run_id)
        raise PublishRunServiceError("CHECKPOINT_CORRUPT") from exc
    if previous is not None and previous.package_fingerprint != package.package_fingerprint:
        await _close_v2_runtime(run.run_id)
        raise PublishRunServiceError("CHECKPOINT_PACKAGE_MISMATCH")
    if previous is not None and previous.attempt != run.attempt:
        # A retry is a new attempt.  Keep no stage/identity claims from the
        # prior attempt; the adapter must freshly inspect the live draft.
        previous = None
    checkpoint_data = previous.model_dump(mode="json") if previous is not None else {
        "package_fingerprint": package.package_fingerprint,
        "account_id": account.account_id,
        "platform": adapter_platform,
        "attempt": run.attempt,
        "runtime_kind": "playwright",
        "completed_stages": [],
        "last_stage": None,
        "upload_mode": None,
        "media_sha256": package.video_manifest.sha256 if package.video_manifest else None,
        "topic_entities": [],
        "cover_receipts": [],
        "blocker_code": None,
        "final_publish_clicked": False,
    }
    checkpoint_data.update(
        package_fingerprint=package.package_fingerprint,
        account_id=account.account_id,
        platform=adapter_platform,
        attempt=run.attempt,
        runtime_kind="playwright",
        blocker_code=None,
        blocked_stage=None,
        final_publish_clicked=False,
    )
    checkpoint = PublishExecutionCheckpoint.model_validate(checkpoint_data)

    safe_profile_ref = account.profile_ref
    if "/" in safe_profile_ref or "\\" in safe_profile_ref:
        safe_profile_ref = account.account_id

    def checkpoint_callback(updated, stage, blocker):
        return get_publish_run_service().record_execution_checkpoint(
            run.run_id,
            updated,
            stage=stage,
            blocker=blocker,
        )

    try:
        publisher = create_platform_publisher(
            run.platform.value,
            runtime,
            profile_path=profile_path,
            account_id=account.account_id,
            profile_ref=safe_profile_ref,
            checkpoint=checkpoint,
            checkpoint_callback=checkpoint_callback,
        )
    except ValueError as exc:
        await _close_v2_runtime(run.run_id)
        raise PublishRunServiceError("PLATFORM_ADAPTER_UNAVAILABLE") from exc
    adapter_package = PublishPackage(
        session_id=f"publish_run:{run.run_id}",
        platform=adapter_platform,
        video_path=str(video_path),
        title=package.platform_copy.title,
        description=package.platform_copy.description,
        hashtags=package.platform_copy.hashtags,
        cover_path=str(cover_path) if cover_path else "",
    )
    try:
        result = await publisher.prepare_draft(adapter_package)
        _append_adapter_result_event(run.run_id, result, getattr(publisher, "adapter_version", "platform-adapter@1"))
    except Exception:
        await _close_v2_runtime(run.run_id)
        raise
    if result.status.value != "draft_ready" or result.adapter_state != "waiting_for_human":
        await _close_v2_runtime(run.run_id)
        raise PublishRunServiceError(result.message or f"{adapter_platform.upper()}_ADAPTER_NOT_READY")


@router.post("/packages", response_model=PublishPackageV2, status_code=status.HTTP_201_CREATED)
async def create_publish_package(payload: PublishPackageCreateRequest, _capability: None = Depends(require_local_capability)):
    try:
        package = get_publish_package_service().create_from_artifact_versions(
            payload.project_id,
            payload.artifact_version_ids,
            package_id=payload.package_id,
            platform_copy=payload.platform_copy if "platform_copy" in payload.model_fields_set else None,
            supersedes_package_id=payload.supersedes_package_id,
        )
        return package
    except PublishPackageBuildError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except PublishPackageConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/packages/from-session", response_model=PublishPackageV2, status_code=status.HTTP_201_CREATED)
async def create_publish_package_from_session(payload: PublishPackageFromSessionRequest, _capability: None = Depends(require_local_capability)):
    with _legacy_handoff_lock:
        session = _session_store.get_session(payload.session_id)
        if session is None:
            raise HTTPException(status_code=404, detail="LEGACY_SESSION_NOT_FOUND")

        existing_package = None
        existing_package_id = session.state.get("publish_package_id")
        if existing_package_id:
            try:
                existing_package = get_publish_core_repository().get_package(str(existing_package_id))
            except PublishPackageNotFound:
                session.state.pop("publish_package_id", None)
                session.state.pop("publish_package_project_id", None)
                session.state.pop("publish_package_handoff_fingerprint", None)

        video_path = session.artifacts.get("final_video") or session.state.get("final_video_path")
        cover_path = session.artifacts.get("cover") or session.state.get("cover_path")
        if not video_path:
            raise HTTPException(status_code=422, detail="LEGACY_SESSION_ARTIFACT_REQUIRED")
        for candidate in (video_path, cover_path):
            if candidate and not _is_allowed_artifact_path(Path(candidate).resolve()):
                raise HTTPException(status_code=422, detail="LEGACY_SESSION_ARTIFACT_UNTRUSTED")

        package_service = get_publish_package_service()
        try:
            video_manifest = preflight_media(video_path, kind="video", roots=package_service.media_roots or None)
            cover_manifest = preflight_media(cover_path, kind="cover", roots=package_service.media_roots or None) if cover_path else None
        except MediaPreflightError as exc:
            raise HTTPException(status_code=422, detail=exc.code) from exc

        try:
            app_repository = get_app_center_repository()
            project_id = payload.project_id
            if existing_package:
                # Legacy callers use a deterministic alias (legacy_<session_id>).
                # Once resolved, keep the canonical project stable across content mutations.
                try:
                    app_repository.get_project(project_id)
                except NotFound:
                    project_id = str(session.state.get("publish_package_project_id") or existing_package.project_id)
                if project_id != existing_package.project_id:
                    raise HTTPException(status_code=409, detail="LEGACY_SESSION_PROJECT_MISMATCH")
            else:
                try:
                    app_repository.get_project(project_id)
                except NotFound:
                    project_id = app_repository.create_project("口播发布项目", f"来自 session {payload.session_id} 的受信交接").project_id

            handoff_fingerprint = _handoff_fingerprint(project_id, video_manifest, cover_manifest, payload.platform_copy)
            if existing_package and not existing_package.invalidated_at:
                recorded_fingerprint = session.state.get("publish_package_handoff_fingerprint")
                if not recorded_fingerprint:
                    recorded_fingerprint = _handoff_fingerprint(
                        existing_package.project_id,
                        existing_package.video_manifest,
                        existing_package.cover_manifest,
                        existing_package.platform_copy,
                    )
                if recorded_fingerprint == handoff_fingerprint:
                    session.state["publish_package_project_id"] = existing_package.project_id
                    session.state["publish_package_handoff_fingerprint"] = handoff_fingerprint
                    _session_store.save_session(session)
                    return existing_package

            video_artifact = app_repository.create_artifact(project_id, "video", "口播视频")
            video_version = app_repository.append_artifact_version(video_artifact.artifact_id, content={"handoff_source": "legacy_session"}, file_refs=[{"path": str(video_path)}], source="imported")
            artifact_version_ids = [video_version.artifact_version_id]
            if cover_path:
                cover_artifact = app_repository.create_artifact(project_id, "cover", "口播封面")
                cover_version = app_repository.append_artifact_version(cover_artifact.artifact_id, content={"handoff_source": "legacy_session"}, file_refs=[{"path": str(cover_path)}], source="imported")
                artifact_version_ids.append(cover_version.artifact_version_id)
            package = package_service.create_from_artifact_versions(
                project_id,
                artifact_version_ids,
                package_id=payload.package_id if not existing_package else None,
                platform_copy=payload.platform_copy,
                supersedes_package_id=existing_package.package_id if existing_package else None,
            )
            session.state["publish_package_id"] = package.package_id
            session.state["publish_package_project_id"] = project_id
            session.state["publish_package_handoff_fingerprint"] = handoff_fingerprint
            _session_store.save_session(session)
            return package
        except PublishPackageBuildError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/packages/resolve", response_model=PublishPackageV2)
async def resolve_publish_package(artifact_id: str = Query(min_length=1)):
    packages = get_publish_core_repository().list_packages_for_artifact(artifact_id)
    if not packages:
        raise HTTPException(status_code=404, detail="PUBLISH_PACKAGE_NOT_FOUND")
    if len(packages) != 1:
        raise HTTPException(status_code=409, detail="PUBLISH_PACKAGE_AMBIGUOUS")
    package = packages[0]
    if package.invalidated_at:
        raise HTTPException(status_code=409, detail="PUBLISH_PACKAGE_STALE")
    return package


@router.get("/packages/{package_id}", response_model=PublishPackageV2)
async def get_publish_package(package_id: str):
    try:
        return get_publish_core_repository().get_package(package_id)
    except PublishPackageNotFound as exc:
        raise HTTPException(status_code=404, detail="PUBLISH_PACKAGE_NOT_FOUND") from exc


@router.post("/packages/{package_id}/preflight")
async def preflight_publish_package(package_id: str, _capability: None = Depends(require_local_capability)):
    try:
        package = get_publish_core_repository().get_package(package_id)
    except PublishPackageNotFound as exc:
        raise HTTPException(status_code=404, detail="PUBLISH_PACKAGE_NOT_FOUND") from exc
    if package.invalidated_at:
        raise HTTPException(status_code=409, detail="PUBLISH_PACKAGE_STALE")
    try:
        get_publish_package_service().verify_package(package)
    except PublishPackageBuildError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {
        "package_id": package.package_id,
        "status": "ready",
        "video_manifest": package.video_manifest.model_dump(mode="json") if package.video_manifest else None,
        "carousel_manifests": [item.model_dump(mode="json") for item in package.carousel_manifests or []],
        "cover_manifest": package.cover_manifest.model_dump(mode="json") if package.cover_manifest else None,
    }


@router.post("/runs", response_model=PublishRunAcceptedResponse, status_code=status.HTTP_202_ACCEPTED)
async def create_publish_run(payload: PublishRunCreateRequest, _capability: None = Depends(require_local_capability)):
    try:
        # PROGRAM-ROLLOUT local p95 probes must measure the durable create-run
        # seam without opening a browser or navigating a platform.  The flag
        # is explicit, desktop-only, and never enabled by default; production
        # calls retain the normal auto-start executor behavior.
        local_noop = is_desktop_mode() and os.getenv("PIXELLE_ROLLOUT_LOCAL_NOOP", "").lower() in {"1", "true", "yes", "on"}
        run, replay = get_publish_run_service().create_run(
            payload.package_id,
            payload.account_id,
            payload.platform,
            payload.idempotency_key,
            auto_start=not local_noop,
        )
        return PublishRunAcceptedResponse(run_id=run.run_id, task_id=run.task_id, state=run.state.value, idempotent_replay=replay)
    except PublishRunAlreadyActive as exc:
        raise HTTPException(status_code=409, detail="RUN_ALREADY_ACTIVE") from exc
    except PublishRunConflict as exc:
        detail = str(exc)
        if detail == "FOREIGN KEY constraint failed":
            detail = "ACCOUNT_NOT_FOUND"
        raise HTTPException(status_code=404 if detail == "ACCOUNT_NOT_FOUND" else 409, detail=detail) from exc
    except PublishPackageConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except (PublishRunNotFound, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/runs/{run_id}", response_model=PublishRunResponse)
async def get_publish_run(run_id: str):
    try:
        return PublishRunResponse(run=get_publish_core_repository().get_run(run_id))
    except PublishRunNotFound as exc:
        raise HTTPException(status_code=404, detail="PUBLISH_RUN_NOT_FOUND") from exc


@router.get("/runs/{run_id}/events", response_model=PublishEventsResponse)
async def list_publish_run_events(run_id: str, after: int = Query(default=0, ge=0)):
    try:
        events = get_publish_core_repository().list_events(run_id, after=after)
    except PublishRunNotFound as exc:
        raise HTTPException(status_code=404, detail="PUBLISH_RUN_NOT_FOUND") from exc
    return PublishEventsResponse(items=[event.model_dump(mode="json") for event in events], next_after=events[-1].event_seq if events else after)


@router.post("/runs/{run_id}/resume", response_model=PublishRunResponse, status_code=status.HTTP_202_ACCEPTED)
async def resume_publish_run(run_id: str, _capability: None = Depends(require_local_capability)):
    try:
        run = get_publish_run_service().resume(run_id)
        get_publish_run_service().schedule(run_id)
        return PublishRunResponse(run=run)
    except PublishRunNotFound as exc:
        raise HTTPException(status_code=404, detail="PUBLISH_RUN_NOT_FOUND") from exc
    except (PublishRunConflict, PublishRunConcurrencyConflict) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/runs/{run_id}/verify", response_model=PublishRunResponse, status_code=status.HTTP_202_ACCEPTED)
async def verify_publish_run(run_id: str, _capability: None = Depends(require_local_capability)):
    try:
        run = get_publish_core_repository().get_run(run_id)
        if run.state is PublishRunState.NEEDS_ATTENTION:
            run = get_publish_run_service().reconcile_verified_checkpoint(run_id)
            return PublishRunResponse(run=run)
        if run.state in {PublishRunState.QUEUED, PublishRunState.RUNNING}:
            get_publish_run_service().schedule(run_id)
        return PublishRunResponse(run=run)
    except PublishRunNotFound as exc:
        raise HTTPException(status_code=404, detail="PUBLISH_RUN_NOT_FOUND") from exc
    except (PublishRunConflict, PublishRunConcurrencyConflict) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/runs/{run_id}/retry-step", response_model=PublishRunResponse, status_code=status.HTTP_202_ACCEPTED)
async def retry_publish_run_step(run_id: str, payload: PublishRetryStepRequest, _capability: None = Depends(require_local_capability)):
    try:
        run = get_publish_run_service().retry_step(run_id, payload.step, actor_ref=payload.actor_ref)
        get_publish_run_service().schedule(run_id)
        return PublishRunResponse(run=run)
    except PublishRunNotFound as exc:
        raise HTTPException(status_code=404, detail="PUBLISH_RUN_NOT_FOUND") from exc
    except (PublishRunConflict, PublishRunConcurrencyConflict) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/runs/{run_id}/cancel", response_model=PublishRunResponse, status_code=status.HTTP_202_ACCEPTED)
async def cancel_publish_run(run_id: str, payload: PublishCancelRequest | None = None, _capability: None = Depends(require_local_capability)):
    try:
        run = get_publish_run_service().cancel(run_id, actor_ref=payload.actor_ref if payload else None)
        return PublishRunResponse(run=run)
    except PublishRunNotFound as exc:
        raise HTTPException(status_code=404, detail="PUBLISH_RUN_NOT_FOUND") from exc
    except (PublishRunConflict, PublishRunConcurrencyConflict) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/runs/{run_id}/mark-outcome", response_model=PublishRunResponse)
async def mark_publish_run_outcome(run_id: str, payload: PublishOutcomeRequest, _capability: None = Depends(require_local_capability)):
    try:
        run = get_publish_run_service().mark_human_outcome(run_id, published=payload.outcome == "published_by_user", actor_ref=payload.actor_ref)
        return PublishRunResponse(run=run)
    except PublishRunNotFound as exc:
        raise HTTPException(status_code=404, detail="PUBLISH_RUN_NOT_FOUND") from exc
    except (PublishRunConflict, PublishRunServiceError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
