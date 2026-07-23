"""Fail-closed application-center boundary for the legacy IP workflow."""

from __future__ import annotations

import re

from fastapi import APIRouter, HTTPException, Query, status

from api.dependencies import get_pixelle_video
from api.routers.app_center import get_app_center_repository
from api.schemas.app_center import IpBroadcastAppRunCreateRequest, IpBroadcastAppRunResponse
from pixelle_video.app_center.ip_broadcast_adapter import (
    IpBroadcastAdapterError,
    IpBroadcastAppAdapter,
    IpBroadcastInputError,
)
from pixelle_video.app_center.repository import AppCenterRepositoryError

router = APIRouter(prefix="/app-center/ip-broadcast", tags=["application-center-ip-broadcast"])
_SECRET_RE = re.compile(r"(?i)(?:api[_-]?key|token|authorization|cookie|password|secret)\s*[:=]\s*[^\s,;]+")
_PATH_RE = re.compile(r"(?<![\w])(?:/(?:private|Users|tmp|var|home|etc)/[^\s,;]+|[A-Za-z]:\\[^\s,;]+)")
_SAFE_ARTIFACT_KEYS = frozenset({"video", "cover", "publish_copy", "final_video", "digital_human_video", "audio", "carousel_package", "carousel_page"})


def get_ip_broadcast_app_adapter() -> IpBroadcastAppAdapter:
    """Construct the production, flag/readiness-gated adapter per request."""

    return IpBroadcastAppAdapter(get_app_center_repository())


def _safe_notices(notices: dict[int, dict[str, str]]) -> dict[int, dict[str, str]]:
    allowed = {"kind", "message", "category", "retryable", "next_action"}

    def scrub(value: object) -> str:
        text = str(value)
        text = _SECRET_RE.sub("<redacted>", text)
        return _PATH_RE.sub("<redacted-path>", text)

    return {
        int(step): {str(key): scrub(value) for key, value in notice.items() if key in allowed}
        for step, notice in notices.items()
        if isinstance(notice, dict)
    }


def _response(handle) -> IpBroadcastAppRunResponse:
    run = handle.run
    return IpBroadcastAppRunResponse(
        app_run_id=run.app_run_id,
        project_id=run.project_id,
        app_id=run.app_id,
        app_version=run.app_version,
        state=run.state,
        state_version=run.state_version,
        session_id=handle.binding.session_id,
        output_artifact_ids=list(run.output_artifact_ids),
        error_code=run.error_code,
        source_revision=handle.binding.source_revision,
        explicit_claim=handle.binding.explicit_claim,
        projection=dict(handle.projection),
        step_status={int(step): str(value) for step, value in handle.session.step_status.items()},
        notices=_safe_notices(handle.session.notices),
        artifact_keys=sorted(set(handle.session.artifacts).intersection(_SAFE_ARTIFACT_KEYS)),
        created_at=run.created_at,
        updated_at=run.updated_at,
    )


def _raise_adapter_error(exc: Exception):
    if isinstance(exc, IpBroadcastInputError):
        raise HTTPException(status_code=422, detail={"code": exc.code}) from exc
    if isinstance(exc, IpBroadcastAdapterError):
        raise HTTPException(status_code=409, detail={"code": exc.code}) from exc
    if isinstance(exc, AppCenterRepositoryError):
        raise HTTPException(status_code=409, detail={"code": "APP_CENTER_REPOSITORY_ERROR"}) from exc
    if isinstance(exc, ValueError):
        raise HTTPException(status_code=422, detail={"code": "INPUT_PAYLOAD_INVALID"}) from exc
    raise exc


@router.post("/runs", response_model=IpBroadcastAppRunResponse, status_code=status.HTTP_201_CREATED)
def create_app_run(request: IpBroadcastAppRunCreateRequest):
    try:
        return _response(
            get_ip_broadcast_app_adapter().create_or_resume(
                request.project_id,
                {"project_id": request.project_id, **request.input_payload},
                idempotency_key=request.idempotency_key,
                explicit_claim=request.explicit_claim,
                context_snapshot_id=request.context_snapshot_id,
            )
        )
    except Exception as exc:
        _raise_adapter_error(exc)


@router.get("/runs/{app_run_id}", response_model=IpBroadcastAppRunResponse)
def get_app_run(app_run_id: str, project_id: str = Query(min_length=1, max_length=200)):
    try:
        adapter = get_ip_broadcast_app_adapter()
        binding = adapter.binding_store.get_by_app_run(app_run_id)
        if binding is None:
            raise HTTPException(status_code=404, detail="IP broadcast AppRun not found")
        return _response(adapter.reconcile(binding.session_id, project_id=project_id, app_run_id=app_run_id))
    except HTTPException:
        raise
    except Exception as exc:
        _raise_adapter_error(exc)


@router.post("/runs/{app_run_id}/cancel", response_model=IpBroadcastAppRunResponse)
def cancel_app_run(app_run_id: str):
    try:
        return _response(get_ip_broadcast_app_adapter().cancel(app_run_id))
    except Exception as exc:
        _raise_adapter_error(exc)


@router.post("/runs/{app_run_id}/retry", response_model=IpBroadcastAppRunResponse)
def retry_app_run(app_run_id: str):
    try:
        return _response(get_ip_broadcast_app_adapter().retry(app_run_id))
    except Exception as exc:
        _raise_adapter_error(exc)


@router.post("/runs/{app_run_id}/execute", response_model=IpBroadcastAppRunResponse)
async def execute_app_run(app_run_id: str):
    """Run the configured TTS, digital-human and media pipeline.

    The final platform publish action is not part of this endpoint; the
    resulting AppRun remains in ``needs_review`` until a human accepts it.
    """

    try:
        adapter = get_ip_broadcast_app_adapter()
        if not adapter.enforce_feature_flag:
            return _response(await adapter.execute_local(app_run_id))
        return _response(await adapter.execute_provider(app_run_id, await get_pixelle_video()))
    except Exception as exc:
        _raise_adapter_error(exc)


@router.post("/runs/{app_run_id}/accept", response_model=IpBroadcastAppRunResponse)
def accept_legacy_outputs(app_run_id: str):
    """Explicit human confirmation for generated or imported output sets."""

    try:
        adapter = get_ip_broadcast_app_adapter()
        if not adapter.enforce_feature_flag:
            run = get_app_center_repository().get_app_run(app_run_id)
            sources = []
            for artifact_id in run.output_artifact_ids:
                artifact = get_app_center_repository().get_artifact(artifact_id)
                if artifact.current_version_id:
                    sources.append(get_app_center_repository().get_artifact_version(artifact.current_version_id).source)
            if sources and all(source == "generated" for source in sources):
                return _response(adapter.accept_local_outputs(app_run_id))
        run = get_app_center_repository().get_app_run(app_run_id)
        if run.output_artifact_ids:
            sources = []
            for artifact_id in run.output_artifact_ids:
                artifact = get_app_center_repository().get_artifact(artifact_id)
                if artifact.current_version_id:
                    sources.append(get_app_center_repository().get_artifact_version(artifact.current_version_id).source)
            if sources and all(source == "generated" for source in sources):
                return _response(adapter.accept_generated_outputs(app_run_id))
        return _response(adapter.accept_legacy_outputs(app_run_id))
    except Exception as exc:
        _raise_adapter_error(exc)


__all__ = ["get_ip_broadcast_app_adapter", "router"]
