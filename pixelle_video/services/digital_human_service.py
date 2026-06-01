"""Digital human video generation service with pluggable provider pattern"""

import asyncio
import json
import os
import subprocess
import uuid
from abc import ABC, abstractmethod
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from loguru import logger

from pixelle_video.config import config_manager

VIDEO_EXTENSIONS = (".mp4", ".mov", ".webm", ".mkv", ".avi")
RUNNINGHUB_AI_APP_DEFAULT_TIMEOUT = 900
RUNNINGHUB_AI_APP_POLL_INTERVAL = 2.0


def _looks_like_video(value: str) -> bool:
    value = value.strip()
    if not value:
        return False
    clean_value = value.split("?", 1)[0].split("#", 1)[0].lower()
    return clean_value.endswith(VIDEO_EXTENSIONS)


def _iter_nested_values(value: Any):
    if isinstance(value, dict):
        for item in value.values():
            yield from _iter_nested_values(item)
    elif isinstance(value, (list, tuple, set)):
        for item in value:
            yield from _iter_nested_values(item)
    else:
        yield value


def _extract_video_output(result: Any) -> str | None:
    """Extract the first video URL/path from common ComfyKit result shapes."""
    for attr in ("videos", "files"):
        values = getattr(result, attr, None)
        if values:
            for value in values:
                if isinstance(value, str) and _looks_like_video(value):
                    return value

    outputs = getattr(result, "outputs", None)
    if outputs:
        for value in _iter_nested_values(outputs):
            if isinstance(value, str) and _looks_like_video(value):
                return value

    if isinstance(result, dict):
        for value in _iter_nested_values(result):
            if isinstance(value, str) and _looks_like_video(value):
                return value

    if hasattr(result, "model_dump"):
        for value in _iter_nested_values(result.model_dump()):
            if isinstance(value, str) and _looks_like_video(value):
                return value

    return None


def _summarize_result(result: Any) -> dict:
    return {
        "status": getattr(result, "status", None),
        "msg": getattr(result, "msg", None),
        "videos": getattr(result, "videos", None),
        "files": getattr(result, "files", None),
        "outputs": getattr(result, "outputs", None),
        "dict_keys": list(result.keys()) if isinstance(result, dict) else None,
    }


def _normalize_workflow_path(workflow: str) -> Path:
    workflow_path = Path(workflow)
    if workflow_path.exists():
        return workflow_path

    if not workflow_path.is_absolute() and workflow_path.parts[:1] in (
        ("runninghub",),
        ("selfhost",),
    ):
        workflow_path = Path("workflows") / workflow_path

    return workflow_path


def _resolve_workflow_input(workflow: str) -> str:
    """Resolve Home-style workflow config to the input ComfyKit expects."""
    workflow_config = _load_workflow_config(workflow)

    if workflow_config.get("source") == "runninghub" and workflow_config.get("workflow_id"):
        return workflow_config["workflow_id"]

    return str(_normalize_workflow_path(workflow))


def _load_workflow_config(workflow: str) -> dict:
    workflow_path = _normalize_workflow_path(workflow)
    if not workflow_path.exists():
        raise FileNotFoundError(f"Workflow file does not exist: {workflow_path}")

    with workflow_path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _build_workflow_params(
    workflow_config: dict,
    portrait_path: str,
    audio_path: str,
    duration: float | None = None,
    prompt: str | None = None,
) -> dict:
    mapping = workflow_config.get("ip_broadcast", {}).get("params", {})
    if not mapping:
        return {
            "videoimage": portrait_path,
            "audio": audio_path,
        }

    params = {
        mapping.get("audio", "audio"): audio_path,
        mapping.get("portrait", "videoimage"): portrait_path,
    }
    duration_key = mapping.get("duration")
    if duration_key and duration:
        params[duration_key] = duration
    prompt_key = mapping.get("prompt")
    if prompt_key and prompt:
        params[prompt_key] = prompt
    return params


def _param_node(param_config: Any, value: Any) -> dict | None:
    if not isinstance(param_config, dict):
        return None
    node_id = param_config.get("node_id")
    field_name = param_config.get("field_name")
    if not node_id or not field_name or value in (None, ""):
        return None
    return {
        "nodeId": str(node_id),
        "fieldName": str(field_name),
        "fieldValue": str(value),
        "description": str(param_config.get("description") or field_name),
    }


def _build_ai_app_node_info_list(
    workflow_config: dict,
    uploaded_portrait: str,
    uploaded_audio: str,
    duration: float | None = None,
    prompt: str | None = None,
    width: int | None = None,
    height: int | None = None,
) -> list[dict]:
    ipb_config = workflow_config.get("ip_broadcast", {})
    mapping = ipb_config.get("params", {})
    defaults = ipb_config.get("defaults", {})
    node_info = []
    emitted_keys = set()
    value_by_key = {
        "portrait": uploaded_portrait,
        "audio": uploaded_audio,
        "duration": int(round(duration)) if duration else None,
        "width": int(width) if width else defaults.get("width"),
        "height": int(height) if height else defaults.get("height"),
        "prompt": prompt,
    }
    ordered_keys = [
        "audio_source_select",
        "portrait",
        "audio",
        "duration",
        "frame_load_cap",
        "skip_first_frames",
        "width",
        "height",
        "prompt",
    ]
    ordered_keys = sorted(
        ordered_keys,
        key=lambda key: int(mapping.get(key, {}).get("order", ordered_keys.index(key))),
    )
    for key in ordered_keys:
        value = value_by_key.get(key, defaults.get(key))
        node = _param_node(mapping.get(key), value)
        if node:
            node_info.append(node)
            emitted_keys.add(key)
    for key, value in defaults.items():
        if key in emitted_keys or key in {"width", "height", "duration", "prompt"}:
            continue
        node = _param_node(mapping.get(key), value)
        if node:
            node_info.append(node)
    return node_info


def _build_ai_app_run_request(
    webapp_id: str,
    api_key: str,
    node_info_list: list[dict],
    instance_type: str | None = None,
    use_personal_queue: bool | str = False,
    include_api_key: bool = False,
) -> tuple[str, dict]:
    use_personal_queue_value = (
        use_personal_queue
        if isinstance(use_personal_queue, str)
        else "true"
        if use_personal_queue
        else "false"
    )
    payload = {
        "nodeInfoList": node_info_list,
        "instanceType": instance_type or "default",
        "usePersonalQueue": use_personal_queue_value,
    }
    if include_api_key:
        payload["apiKey"] = api_key
    return (
        f"/openapi/v2/run/ai-app/{webapp_id}",
        payload,
    )


def _resolve_runninghub_api_key(comfyui_config: dict) -> str:
    return comfyui_config.get("runninghub_api_key") or os.getenv("RUNNINGHUB_API_KEY") or ""


def _runninghub_ai_app_headers(api_key: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }


def list_digital_human_workflows() -> list[dict]:
    workflows = []
    for base in (Path("workflows/runninghub"), Path("workflows/selfhost")):
        if not base.exists():
            continue
        for workflow_path in sorted(base.glob("digital*.json")):
            rel_path = workflow_path.as_posix()
            try:
                config = _load_workflow_config(rel_path)
            except Exception as e:
                logger.warning(f"Failed to load digital human workflow {rel_path}: {e}")
                continue
            ipb_params = config.get("ip_broadcast", {}).get("params", {})
            is_legacy_talking_workflow = workflow_path.name == "digital_combination.json"
            if not is_legacy_talking_workflow and not ipb_params:
                continue
            workflows.append(
                {
                    "key": rel_path,
                    "display_name": config.get("display_name") or workflow_path.stem,
                    "description": config.get("ip_broadcast", {}).get("description", ""),
                    "supports_prompt": bool(ipb_params.get("prompt")),
                    "supports_duration": bool(ipb_params.get("duration")),
                    "supports_width": bool(ipb_params.get("width")),
                    "supports_height": bool(ipb_params.get("height")),
                    "portrait_media_type": config.get("ip_broadcast", {}).get(
                        "portrait_media_type",
                        "image",
                    ),
                    "default_width": config.get("ip_broadcast", {})
                    .get("defaults", {})
                    .get("width"),
                    "default_height": config.get("ip_broadcast", {})
                    .get("defaults", {})
                    .get("height"),
                }
            )
    return workflows


class DigitalHumanProvider(ABC):
    """Abstract provider for digital human video generation"""

    provider_id: str = ""

    @abstractmethod
    async def generate(
        self,
        portrait_path: str,
        audio_path: str,
        output_path: str,
        workflow: str | None = None,
        duration: float | None = None,
        prompt: str | None = None,
        width: int | None = None,
        height: int | None = None,
    ) -> str:
        """
        Generate a digital human video.

        Args:
            portrait_path: Path to the portrait image
            audio_path: Path to the audio file
            output_path: Desired output video path

        Returns:
            Path to the generated video
        """


class ComfyUIDigitalHumanProvider(DigitalHumanProvider):
    """Phase 1 provider: delegates to ComfyUI workflow (same as existing digital_human pipeline)"""

    provider_id = "comfyui"

    def __init__(self, core):
        self._core = core

    async def generate(
        self,
        portrait_path: str,
        audio_path: str,
        output_path: str,
        workflow: str | None = None,
        duration: float | None = None,
        prompt: str | None = None,
        width: int | None = None,
        height: int | None = None,
    ) -> str:
        kit = await self._core._get_or_create_comfykit()
        dh_config = config_manager.get_digital_human_service_config()
        workflow = (
            workflow or dh_config.get("base_url") or "workflows/runninghub/digital_combination.json"
        )
        workflow_config = _load_workflow_config(workflow)
        if workflow_config.get("type") == "ai_app":
            result = await _execute_runninghub_ai_app(
                workflow_config=workflow_config,
                portrait_path=portrait_path,
                audio_path=audio_path,
                duration=duration,
                prompt=prompt,
                width=width,
                height=height,
            )
            if getattr(result, "status", "completed") != "completed":
                error_msg = getattr(result, "msg", None) or "Unknown error"
                raise RuntimeError(f"Digital human generation failed: {error_msg}")
            video_url_or_path = _extract_video_output(result)
            if video_url_or_path:
                await _save_video_output(video_url_or_path, output_path)
                _trim_video_to_audio_duration_if_needed(output_path, audio_path)
                return output_path
            logger.error(
                f"Digital human AI App result has no recognized video output: {_summarize_result(result)}"
            )
            raise RuntimeError(
                "Digital human generation returned no video output. "
                "请检查 AI App 是否输出 mp4/webm/mov 视频文件。"
            )

        workflow_input = _resolve_workflow_input(workflow)
        workflow_params = _build_workflow_params(
            workflow_config,
            portrait_path=portrait_path,
            audio_path=audio_path,
            duration=duration,
            prompt=prompt,
        )

        logger.info(f"Generating digital human video via ComfyUI: workflow={workflow}")
        result = await kit.execute(
            workflow_input,
            workflow_params,
        )

        if getattr(result, "status", "completed") != "completed":
            error_msg = getattr(result, "msg", None) or "Unknown error"
            raise RuntimeError(f"Digital human generation failed: {error_msg}")

        video_url_or_path = _extract_video_output(result)
        if video_url_or_path:
            await _save_video_output(video_url_or_path, output_path)
            _trim_video_to_audio_duration_if_needed(output_path, audio_path)
            return output_path

        logger.error(
            f"Digital human result has no recognized video output: {_summarize_result(result)}"
        )
        raise RuntimeError(
            "Digital human generation returned no video output. "
            "请检查数字人工作流是否输出 mp4/webm/mov 视频文件。"
        )


async def _execute_runninghub_ai_app(
    workflow_config: dict,
    portrait_path: str,
    audio_path: str,
    duration: float | None,
    prompt: str | None,
    width: int | None = None,
    height: int | None = None,
):
    from comfykit.comfyui.runninghub_client import RunningHubClient

    comfyui_config = config_manager.get_comfyui_config()
    api_key = _resolve_runninghub_api_key(comfyui_config)
    if not api_key:
        raise RuntimeError("RunningHub API key is required for AI App digital human workflow")

    webapp_id = workflow_config.get("webapp_id")
    if not webapp_id:
        raise RuntimeError("RunningHub AI App workflow is missing webapp_id")

    client = RunningHubClient(
        api_key=api_key,
        base_url="https://www.runninghub.cn",
        instance_type=comfyui_config.get("runninghub_instance_type"),
    )
    try:
        uploaded_portrait = await _upload_runninghub_ai_app_media(client, portrait_path, api_key)
        uploaded_audio = await _upload_runninghub_ai_app_media(client, audio_path, api_key)
        logger.info(
            "RunningHub AI App uploaded files: "
            f"portrait={uploaded_portrait}, audio={uploaded_audio}"
        )
        node_info_list = _build_ai_app_node_info_list(
            workflow_config,
            uploaded_portrait=uploaded_portrait,
            uploaded_audio=uploaded_audio,
            duration=duration,
            prompt=prompt,
            width=width or workflow_config.get("ip_broadcast", {}).get("defaults", {}).get("width"),
            height=height
            or workflow_config.get("ip_broadcast", {}).get("defaults", {}).get("height"),
        )
        logger.info(f"RunningHub AI App nodeInfoList: {node_info_list}")
        endpoint, payload = _build_ai_app_run_request(
            webapp_id=webapp_id,
            api_key=api_key,
            node_info_list=node_info_list,
            instance_type=comfyui_config.get("runninghub_instance_type") or "default",
        )
        run_result = await _make_runninghub_ai_app_run_request(client, endpoint, payload, api_key)
        task_id = run_result.get("taskId") or (run_result.get("data") or {}).get("taskId")
        if not task_id:
            raise RuntimeError(f"RunningHub AI App did not return taskId: {run_result}")
        return await _wait_for_runninghub_ai_app_task(client, task_id, api_key)
    finally:
        await client.close()


async def _upload_runninghub_ai_app_media(client, file_path: str, api_key: str) -> str:
    import aiohttp

    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    url = f"{client.base_url}/openapi/v2/media/upload/binary"
    logger.info(f"RunningHub AI App media upload: url={url}, file={path.name}")
    form = aiohttp.FormData()
    form.add_field(
        "file",
        path.read_bytes(),
        filename=path.name,
        content_type="application/octet-stream",
    )

    session = await client._get_session()
    async with session.post(
        url,
        data=form,
        headers={"Authorization": f"Bearer {api_key}"},
    ) as response:
        text = await response.text()
        if response.status != 200:
            raise RuntimeError(f"RunningHub AI App media upload HTTP {response.status}: {text}")
        try:
            result = await response.json()
        except Exception as e:
            raise RuntimeError(
                f"RunningHub AI App media upload returned invalid JSON: {text}"
            ) from e

    if result.get("code") not in (0, "0", None):
        raise RuntimeError(
            "RunningHub AI App media upload API error: "
            f"{result.get('message') or result.get('msg') or result}"
        )
    data = result.get("data") or {}
    uploaded_value = data.get("download_url") or data.get("fileName")
    if not uploaded_value:
        raise RuntimeError(f"RunningHub AI App media upload returned no URL: {result}")
    logger.info(
        "RunningHub AI App media upload completed: "
        f"type={data.get('type')}, value={uploaded_value}, fileName={data.get('fileName')}"
    )
    return str(uploaded_value)


async def _make_runninghub_ai_app_run_request(
    client,
    endpoint: str,
    payload: dict,
    api_key: str,
) -> dict[str, Any]:
    url = f"{client.base_url}{endpoint}"
    logger.info(
        "RunningHub AI App run request: "
        f"url={url}, node_count={len(payload.get('nodeInfoList') or [])}, "
        f"instanceType={payload.get('instanceType')}, "
        f"usePersonalQueue={payload.get('usePersonalQueue')}"
    )
    session = await client._get_session()
    result = await _post_runninghub_ai_app_run(
        session=session,
        url=url,
        payload=payload,
        headers=_runninghub_ai_app_headers(api_key),
    )
    if result.get("_http_status") == 401:
        logger.warning(
            "RunningHub AI App Bearer auth returned 401; retrying with apiKey in JSON body"
        )
        fallback_payload = {**payload, "apiKey": api_key}
        result = await _post_runninghub_ai_app_run(
            session=session,
            url=url,
            payload=fallback_payload,
            headers={"Content-Type": "application/json"},
        )

    http_status = result.pop("_http_status", 200)
    if http_status != 200:
        raise RuntimeError(f"HTTP {http_status}: {result.get('_text', result)}")

    if result.get("errorCode"):
        error_message = result.get("errorMessage") or result.get("msg") or "Unknown error"
        raise RuntimeError(
            f"RunningHub AI App API error {result.get('errorCode')}: {error_message}"
        )
    if result.get("code") not in (0, "0", None) and not result.get("taskId"):
        raise RuntimeError(f"RunningHub AI App API error: {result.get('msg', 'Unknown error')}")
    return result


async def _post_runninghub_ai_app_run(
    session,
    url: str,
    payload: dict,
    headers: dict[str, str],
) -> dict[str, Any]:
    async with session.post(
        url,
        json=payload,
        headers=headers,
    ) as response:
        text = await response.text()
        try:
            result = await response.json()
        except Exception:
            result = {"_text": text}
        result["_http_status"] = response.status
    return result


async def _wait_for_runninghub_task(
    client,
    task_id: str,
    max_wait_time: float | None = None,
    poll_interval: float | None = None,
):
    max_wait_time = RUNNINGHUB_AI_APP_DEFAULT_TIMEOUT if max_wait_time is None else max_wait_time
    poll_interval = RUNNINGHUB_AI_APP_POLL_INTERVAL if poll_interval is None else poll_interval
    start_time = asyncio.get_event_loop().time()
    while True:
        if (
            max_wait_time is not None
            and asyncio.get_event_loop().time() - start_time > max_wait_time
        ):
            return SimpleNamespace(status="error", msg=f"RunningHub AI App task {task_id} timeout")
        status_info = await client.query_task_status(task_id)
        task_status = status_info.get("status")
        if task_status == "SUCCESS":
            result_data = await client.query_task_result(task_id)
            return _runninghub_outputs_to_result(task_id, result_data)
        if task_status == "FAILED":
            return SimpleNamespace(
                status="error",
                msg=status_info.get("msg") or f"RunningHub AI App task {task_id} failed",
            )
        await asyncio.sleep(poll_interval)


async def _query_runninghub_ai_app_task(client, task_id: str, api_key: str) -> dict[str, Any]:
    url = f"{client.base_url}/openapi/v2/query"
    session = await client._get_session()
    async with session.post(
        url,
        json={"taskId": task_id},
        headers=_runninghub_ai_app_headers(api_key),
    ) as response:
        text = await response.text()
        if response.status != 200:
            raise RuntimeError(f"RunningHub AI App query HTTP {response.status}: {text}")
        try:
            result = await response.json()
        except Exception as e:
            raise RuntimeError(f"RunningHub AI App query returned invalid JSON: {text}") from e
    if result.get("errorCode"):
        error_message = result.get("errorMessage") or result.get("msg") or "Unknown error"
        raise RuntimeError(
            f"RunningHub AI App query error {result.get('errorCode')}: {error_message}"
        )
    return result


async def _wait_for_runninghub_ai_app_task(
    client,
    task_id: str,
    api_key: str,
    max_wait_time: float | None = None,
    poll_interval: float | None = None,
):
    max_wait_time = RUNNINGHUB_AI_APP_DEFAULT_TIMEOUT if max_wait_time is None else max_wait_time
    poll_interval = RUNNINGHUB_AI_APP_POLL_INTERVAL if poll_interval is None else poll_interval
    start_time = asyncio.get_event_loop().time()
    while True:
        if (
            max_wait_time is not None
            and asyncio.get_event_loop().time() - start_time > max_wait_time
        ):
            return SimpleNamespace(status="error", msg=f"RunningHub AI App task {task_id} timeout")
        task_info = await _query_runninghub_ai_app_task(client, task_id, api_key)
        task_status = task_info.get("status")
        if task_status == "SUCCESS":
            return _runninghub_ai_app_outputs_to_result(task_id, task_info)
        if task_status == "FAILED":
            return SimpleNamespace(
                status="error",
                msg=task_info.get("errorMessage") or f"RunningHub AI App task {task_id} failed",
                outputs={"raw_data": task_info},
            )
        await asyncio.sleep(poll_interval)


def _runninghub_ai_app_outputs_to_result(task_id: str, task_info: dict[str, Any]):
    videos = []
    files = []
    for item in task_info.get("results") or []:
        if not isinstance(item, dict):
            continue
        file_url = item.get("url")
        if not file_url:
            continue
        files.append(file_url)
        output_type = str(item.get("outputType", "")).lower()
        if output_type in {"mp4", "mov", "webm", "mkv", "avi"} or _looks_like_video(file_url):
            videos.append(file_url)
    return SimpleNamespace(
        status="completed",
        prompt_id=task_id,
        videos=videos,
        files=files,
        outputs={"raw_data": task_info},
    )


def _runninghub_outputs_to_result(task_id: str, result_data: Any):
    videos = []
    files = []
    for item in result_data or []:
        if not isinstance(item, dict):
            continue
        file_url = item.get("fileUrl") or item.get("url")
        if not file_url:
            continue
        files.append(file_url)
        file_type = str(item.get("fileType", "")).lower()
        if "video" in file_type or _looks_like_video(file_url):
            videos.append(file_url)
    return SimpleNamespace(
        status="completed",
        prompt_id=task_id,
        videos=videos,
        files=files,
        outputs={"raw_data": result_data},
    )


async def _save_video_output(video_url_or_path: str, output_path: str) -> None:
    import shutil

    import httpx

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    if video_url_or_path.startswith(("http://", "https://")):
        async with httpx.AsyncClient(timeout=300) as client:
            resp = await client.get(video_url_or_path)
            resp.raise_for_status()
            if not resp.content:
                raise RuntimeError(
                    f"Digital human API returned an empty response body for: {video_url_or_path}"
                )
            Path(output_path).write_bytes(resp.content)
    else:
        shutil.copy2(video_url_or_path, output_path)


def _probe_media_duration(media_path: str) -> float:
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            media_path,
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    return float(result.stdout.strip())


def _build_trim_video_to_duration_command(
    video_path: str,
    output_path: str,
    duration: float,
) -> list[str]:
    return [
        "ffmpeg",
        "-y",
        "-i",
        video_path,
        "-t",
        f"{duration:.3f}",
        "-map",
        "0:v:0",
        "-map",
        "0:a?",
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "18",
        "-c:a",
        "aac",
        "-movflags",
        "+faststart",
        output_path,
    ]


def _trim_video_to_audio_duration_if_needed(
    video_path: str,
    audio_path: str,
    tolerance_seconds: float = 0.35,
) -> bool:
    """Trim generated digital-human video when a workflow returns a silent tail."""
    try:
        video_duration = _probe_media_duration(video_path)
        audio_duration = _probe_media_duration(audio_path)
    except Exception as e:
        logger.warning(f"Failed to probe digital human durations, skip trimming: {e}")
        return False

    if audio_duration <= 0 or video_duration <= audio_duration + tolerance_seconds:
        return False

    output = Path(video_path)
    temp_output = output.with_name(
        f"{output.stem}.trim_{uuid.uuid4().hex[:8]}{output.suffix or '.mp4'}"
    )
    logger.info(
        "Trimming digital human video to audio duration: "
        f"video={video_duration:.2f}s, audio={audio_duration:.2f}s, path={video_path}"
    )
    try:
        subprocess.run(
            _build_trim_video_to_duration_command(
                video_path,
                str(temp_output),
                audio_duration,
            ),
            capture_output=True,
            text=True,
            check=True,
        )
        temp_output.replace(output)
        return True
    except subprocess.CalledProcessError as e:
        if temp_output.exists():
            temp_output.unlink()
        stderr = e.stderr or str(e)
        raise RuntimeError(f"Failed to trim digital human video to audio duration: {stderr}") from e


class HTTPDigitalHumanProvider(DigitalHumanProvider):
    """Future provider: 黑链/infomers HTTP API — placeholder until API docs are received"""

    provider_id = "http"

    async def generate(
        self,
        portrait_path: str,
        audio_path: str,
        output_path: str,
        workflow: str | None = None,
        duration: float | None = None,
        prompt: str | None = None,
        width: int | None = None,
        height: int | None = None,
    ) -> str:
        raise NotImplementedError(
            "HTTP digital human provider is not yet implemented. "
            "Please provide the API documentation for 黑链/infomers integration."
        )


_PROVIDERS: dict[str, type[DigitalHumanProvider]] = {
    "comfyui": ComfyUIDigitalHumanProvider,
    "heixiang": HTTPDigitalHumanProvider,
    "infomers": HTTPDigitalHumanProvider,
}


class DigitalHumanService:
    """Facade that selects and delegates to the configured provider"""

    def __init__(self, core):
        self._core = core

    def _get_provider(self) -> DigitalHumanProvider:
        cfg = config_manager.get_digital_human_service_config()
        provider_id = cfg.get("provider", "comfyui")
        cls = _PROVIDERS.get(provider_id, ComfyUIDigitalHumanProvider)
        if cls is ComfyUIDigitalHumanProvider:
            return cls(self._core)
        return cls()

    async def generate(
        self,
        portrait_path: str,
        audio_path: str,
        output_path: str,
        workflow: str | None = None,
        duration: float | None = None,
        prompt: str | None = None,
        width: int | None = None,
        height: int | None = None,
    ) -> str:
        provider = self._get_provider()
        logger.info(f"Digital human generation via provider: {provider.provider_id}")
        return await provider.generate(
            portrait_path,
            audio_path,
            output_path,
            workflow=workflow,
            duration=duration,
            prompt=prompt,
            width=width,
            height=height,
        )
