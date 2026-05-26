"""Digital human video generation service with pluggable provider pattern"""

import asyncio
import json
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

    if not workflow_path.is_absolute() and workflow_path.parts[:1] in (("runninghub",), ("selfhost",)):
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
) -> list[dict]:
    mapping = workflow_config.get("ip_broadcast", {}).get("params", {})
    node_info = []
    for key, value in (
        ("portrait", uploaded_portrait),
        ("audio", uploaded_audio),
        ("duration", int(round(duration)) if duration else None),
        ("prompt", prompt),
    ):
        node = _param_node(mapping.get(key), value)
        if node:
            node_info.append(node)
    return node_info


def _build_ai_app_run_request(
    webapp_id: str,
    api_key: str,
    node_info_list: list[dict],
) -> tuple[str, dict]:
    _ = api_key
    return (
        f"/openapi/v2/run/ai-app/{webapp_id}",
        {
            "nodeInfoList": node_info_list,
        },
    )


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
    ) -> str:
        kit = await self._core._get_or_create_comfykit()
        dh_config = config_manager.get_digital_human_service_config()
        workflow = (
            workflow
            or dh_config.get("base_url")
            or "workflows/runninghub/digital_combination.json"
        )
        workflow_config = _load_workflow_config(workflow)
        if workflow_config.get("type") == "ai_app":
            result = await _execute_runninghub_ai_app(
                workflow_config=workflow_config,
                portrait_path=portrait_path,
                audio_path=audio_path,
                duration=duration,
                prompt=prompt,
            )
            if getattr(result, "status", "completed") != "completed":
                error_msg = getattr(result, "msg", None) or "Unknown error"
                raise RuntimeError(f"Digital human generation failed: {error_msg}")
            video_url_or_path = _extract_video_output(result)
            if video_url_or_path:
                await _save_video_output(video_url_or_path, output_path)
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
            return output_path

        logger.error(f"Digital human result has no recognized video output: {_summarize_result(result)}")
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
):
    from comfykit.comfyui.runninghub_client import RunningHubClient

    comfyui_config = config_manager.get_comfyui_config()
    api_key = comfyui_config.get("runninghub_api_key")
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
        uploaded_portrait = await client.upload_file(portrait_path)
        uploaded_audio = await client.upload_file(audio_path)
        node_info_list = _build_ai_app_node_info_list(
            workflow_config,
            uploaded_portrait=uploaded_portrait,
            uploaded_audio=uploaded_audio,
            duration=duration,
            prompt=prompt,
        )
        logger.info(f"RunningHub AI App nodeInfoList: {node_info_list}")
        endpoint, payload = _build_ai_app_run_request(
            webapp_id=webapp_id,
            api_key=api_key,
            node_info_list=node_info_list,
        )
        run_result = await _make_runninghub_ai_app_run_request(client, endpoint, payload, api_key)
        task_id = (run_result.get("data") or {}).get("taskId")
        if not task_id:
            raise RuntimeError(f"RunningHub AI App did not return taskId: {run_result}")
        return await _wait_for_runninghub_task(client, task_id)
    finally:
        await client.close()


async def _make_runninghub_ai_app_run_request(
    client,
    endpoint: str,
    payload: dict,
    api_key: str,
) -> dict[str, Any]:
    import httpx

    url = f"{client.base_url}{endpoint}"
    async with httpx.AsyncClient(timeout=getattr(client, "timeout", 300)) as http_client:
        response = await http_client.post(
            url,
            json=payload,
            headers=_runninghub_ai_app_headers(api_key),
        )
    if response.status_code != 200:
        raise RuntimeError(f"HTTP {response.status_code}: {response.text}")

    result = response.json()
    if result.get("code") not in (0, "0", None):
        raise RuntimeError(f"RunningHub AI App API error: {result.get('msg', 'Unknown error')}")
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
        if max_wait_time is not None and asyncio.get_event_loop().time() - start_time > max_wait_time:
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
        )
