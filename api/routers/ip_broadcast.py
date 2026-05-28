"""IP broadcast workflow endpoints for desktop and web clients."""

from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from loguru import logger

from api.dependencies import PixelleVideoDep
from api.schemas.ip_broadcast import (
    IpBroadcastConfigPatch,
    IpBroadcastCreateSessionResponse,
    IpBroadcastRunStepResponse,
)
from api.tasks import TaskType, task_manager
from pixelle_video.services.ip_broadcast_workflow import (
    STEP_KEYS,
    IpBroadcastSession,
    IpBroadcastSessionStore,
    run_ip_broadcast_step,
)

router = APIRouter(prefix="/ip-broadcast", tags=["IP Broadcast"])
_session_store = IpBroadcastSessionStore()


@router.post("/sessions", response_model=IpBroadcastCreateSessionResponse)
async def create_session():
    session = _session_store.create_session()
    return session.to_response()


@router.get("/sessions/{session_id}", response_model=IpBroadcastCreateSessionResponse)
async def get_session(session_id: str):
    session = _get_session_or_404(session_id)
    return session.to_response()


@router.patch("/sessions/{session_id}/config", response_model=IpBroadcastCreateSessionResponse)
async def update_session_config(session_id: str, patch: IpBroadcastConfigPatch):
    session = _get_session_or_404(session_id)
    session.update_config(patch.flattened())
    return session.to_response()


@router.post(
    "/sessions/{session_id}/steps/{step_key}/run",
    response_model=IpBroadcastRunStepResponse,
)
async def run_step(session_id: str, step_key: str, pixelle_video: PixelleVideoDep):
    session = _get_session_or_404(session_id)
    task = task_manager.create_task(
        task_type=TaskType.IP_BROADCAST_STEP,
        request_params={"session_id": session_id, "step_key": step_key},
        display_name=_step_display_name(step_key),
        flow_name="IP口播",
        step_key=step_key,
        session_id=session_id,
        artifact_keys=_step_artifacts(step_key),
        retry_payload={"kind": "ip_broadcast_step", "session_id": session_id, "step_key": step_key},
    )

    async def _execute():
        task_manager.update_progress(task.task_id, 1, 3, _step_progress_message(step_key))
        ok = await run_ip_broadcast_step(pixelle_video, session, step_key)
        if not ok:
            step = STEP_KEYS.get(step_key)
            notice = session.notices.get(step, {})
            raise RuntimeError(notice.get("message") or f"IP broadcast step failed: {step_key}")
        task_manager.update_progress(task.task_id, 3, 3, "步骤执行完成。")
        return session.to_response()

    await task_manager.execute_task(task.task_id, _execute)
    return IpBroadcastRunStepResponse(
        session_id=session_id,
        step_key=step_key,
        task_id=task.task_id,
    )


@router.post(
    "/sessions/{session_id}/continue",
    response_model=IpBroadcastRunStepResponse,
)
async def continue_session(session_id: str, pixelle_video: PixelleVideoDep):
    session = _get_session_or_404(session_id)
    action = session.next_action()
    if action.get("disabled"):
        raise HTTPException(status_code=409, detail=action["description"])
    return await run_step(session_id, action["key"], pixelle_video)


@router.get("/sessions/{session_id}/artifacts/{artifact_key}")
async def get_artifact(session_id: str, artifact_key: str):
    session = _get_session_or_404(session_id)
    artifact_path = session.artifacts.get(artifact_key)
    if not artifact_path:
        raise HTTPException(status_code=404, detail=f"Artifact not found: {artifact_key}")
    path = Path(artifact_path).resolve()
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail=f"Artifact file not found: {artifact_key}")
    if not _is_allowed_artifact_path(path):
        logger.warning(f"Blocked IP broadcast artifact path: {path}")
        raise HTTPException(status_code=403, detail="Artifact path is not allowed")
    return FileResponse(str(path), filename=path.name)


def _get_session_or_404(session_id: str) -> IpBroadcastSession:
    session = _session_store.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"IP broadcast session not found: {session_id}")
    return session


def _is_allowed_artifact_path(path: Path) -> bool:
    allowed_roots = [
        Path.cwd() / "output",
        Path.cwd() / "data",
        Path("/tmp"),
        Path("/private/tmp"),
    ]
    for root in allowed_roots:
        try:
            path.relative_to(root.resolve())
            return True
        except ValueError:
            continue
    return False


def _step_display_name(step_key: str) -> str:
    return {
        "source": "生成口播文案",
        "copywriting": "AI 改写文案",
        "voice": "生成语音",
        "digital_human": "生成数字人视频",
        "postproduction": "一键成片",
        "publish": "生成发布素材包",
    }.get(step_key, step_key)


def _step_artifacts(step_key: str) -> list[str]:
    return {
        "voice": ["audio"],
        "digital_human": ["digital_human_video"],
        "postproduction": ["final_video", "publish_package_json", "script"],
        "publish": ["publish_package_json", "script"],
    }.get(step_key, [])


def _step_progress_message(step_key: str) -> str:
    return {
        "source": "正在整理素材文本。",
        "copywriting": "正在改写口播文案，通常需要几十秒。",
        "voice": "正在生成配音。",
        "digital_human": "正在生成数字人视频，远程任务通常需要 1-5 分钟，可在 RunningHub 后台查看进度。",
        "postproduction": "正在合成最终视频。",
        "publish": "正在准备发布素材包。",
    }.get(step_key, "正在执行任务。")
