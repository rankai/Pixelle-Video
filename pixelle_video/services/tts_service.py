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
TTS (Text-to-Speech) Service - Supports both local and ComfyUI inference
"""

import asyncio
import json
import os
import uuid
from pathlib import Path
from typing import Any, Optional

from loguru import logger

from pixelle_video.services.comfy_base_service import ComfyBaseService
from pixelle_video.tts_voices import speed_to_rate
from pixelle_video.utils.tts_util import edge_tts


def _format_percent_change(value: Optional[float | int | str]) -> str:
    if value is None:
        return "+0%"
    if isinstance(value, str):
        return value
    percentage = int(value)
    sign = "+" if percentage >= 0 else ""
    return f"{sign}{percentage}%"


def _format_pitch_change(value: Optional[float | int | str]) -> str:
    if value is None:
        return "+0Hz"
    if isinstance(value, str):
        return value
    pitch = int(value)
    sign = "+" if pitch >= 0 else ""
    return f"{sign}{pitch}Hz"


class TTSService(ComfyBaseService):
    """
    TTS (Text-to-Speech) service - Workflow-based
    
    Uses ComfyKit to execute TTS workflows.
    
    Usage:
        # Use default workflow
        audio_path = await pixelle_video.tts(text="Hello, world!")
        
        # Use specific workflow
        audio_path = await pixelle_video.tts(
            text="你好，世界！",
            workflow="tts_edge.json"
        )
        
        # List available workflows
        workflows = pixelle_video.tts.list_workflows()
    """
    
    WORKFLOW_PREFIX = "tts_"
    DEFAULT_WORKFLOW = None  # No hardcoded default, must be configured
    WORKFLOWS_DIR = "workflows"
    
    def __init__(self, config: dict, core=None):
        """
        Initialize TTS service
        
        Args:
            config: Full application config dict
            core: PixelleVideoCore instance (for accessing shared ComfyKit)
        """
        super().__init__(config, service_name="tts", core=core)
    
    
    async def __call__(
        self,
        text: str,
        workflow: Optional[str] = None,
        # ComfyUI connection (optional overrides)
        comfyui_url: Optional[str] = None,
        runninghub_api_key: Optional[str] = None,
        # TTS parameters
        voice: Optional[str] = None,
        speed: Optional[float | str] = None,
        pitch: Optional[float | str] = None,
        volume: Optional[float | str] = None,
        # Inference mode override
        inference_mode: Optional[str] = None,
        # Output path
        output_path: Optional[str] = None,
        **params
    ) -> str:
        """
        Generate speech using local Edge TTS or ComfyUI workflow
        
        Args:
            text: Text to convert to speech
            workflow: Workflow filename (for ComfyUI mode, default: from config)
            comfyui_url: ComfyUI URL (optional, overrides config)
            runninghub_api_key: RunningHub API key (optional, overrides config)
            voice: Voice ID (for local mode: Edge TTS voice ID; for ComfyUI: workflow-specific)
            speed: Speech speed multiplier (1.0 = normal, >1.0 = faster, <1.0 = slower)
            pitch: Local Edge pitch in Hz or workflow-specific pitch value
            volume: Local Edge volume percentage change
            inference_mode: Override inference mode ("local" or "comfyui", default: from config)
            output_path: Custom output path (auto-generated if None)
            **params: Additional workflow parameters
        
        Returns:
            Generated audio file path
        
        Examples:
            # Local inference (Edge TTS)
            audio_path = await pixelle_video.tts(
                text="Hello, world!",
                inference_mode="local",
                voice="zh-CN-YunjianNeural",
                speed=1.2
            )
            
            # ComfyUI inference
            audio_path = await pixelle_video.tts(
                text="你好，世界！",
                inference_mode="comfyui",
                workflow="runninghub/tts_edge.json"
            )
        """
        # Determine inference mode (param > config)
        mode = inference_mode or self.config.get("inference_mode", "local")
        
        # Route to appropriate implementation
        if mode == "local":
            return await self._call_local_tts(
                text=text,
                voice=voice,
                speed=speed,
                pitch=pitch,
                volume=volume,
                output_path=output_path
            )
        else:  # comfyui
            # 1. Resolve workflow (returns structured info)
            workflow_info = self._resolve_workflow(workflow=workflow)
            
            # 2. Execute ComfyUI workflow
            return await self._call_comfyui_workflow(
                workflow_info=workflow_info,
                text=text,
                comfyui_url=comfyui_url,
                runninghub_api_key=runninghub_api_key,
                voice=voice,
                speed=speed,
                pitch=pitch,
                output_path=output_path,
                **params
            )
    
    async def _call_local_tts(
        self,
        text: str,
        voice: Optional[str] = None,
        speed: Optional[float] = None,
        pitch: Optional[float | str] = None,
        volume: Optional[float | str] = None,
        output_path: Optional[str] = None,
    ) -> str:
        """
        Generate speech using local Edge TTS
        
        Args:
            text: Text to convert to speech
            voice: Edge TTS voice ID (default: from config)
            speed: Speech speed multiplier (default: from config)
            pitch: Pitch change in Hz (default: +0Hz)
            volume: Volume change in percent (default: +0%)
            output_path: Custom output path (auto-generated if None)
        
        Returns:
            Generated audio file path
        """
        # Get config defaults
        local_config = self.config.get("local", {})
        
        # Determine voice and speed (param > config)
        final_voice = voice or local_config.get("voice", "zh-CN-YunjianNeural")
        final_speed = speed if speed is not None else local_config.get("speed", 1.2)
        final_pitch = pitch if pitch is not None else local_config.get("pitch", 0)
        final_volume = volume if volume is not None else local_config.get("volume", 0)
        
        # Convert speed to rate parameter
        rate = speed_to_rate(final_speed)
        
        pitch_value = _format_pitch_change(final_pitch)
        volume_value = _format_percent_change(final_volume)

        logger.info(
            f"🎙️  Using local Edge TTS: voice={final_voice}, speed={final_speed}x "
            f"(rate={rate}, pitch={pitch_value}, volume={volume_value})"
        )
        
        # Generate output path if not provided
        if not output_path:
            # Generate unique filename
            unique_id = uuid.uuid4().hex
            output_path = f"output/{unique_id}.mp3"
            
            # Ensure output directory exists
            Path("output").mkdir(parents=True, exist_ok=True)
        
        # Call Edge TTS — use locale-aware fallback voice
        # If text contains CJK characters, fallback to zh-CN voice;
        # otherwise fallback to en-US voice.
        _has_cjk = any('一' <= c <= '鿿' or '㐀' <= c <= '䶿' for c in text)
        _fallback_voice = "zh-CN-XiaoxiaoNeural" if _has_cjk else "en-US-JennyNeural"

        try:
            await edge_tts(
                text=text,
                voice=final_voice,
                rate=rate,
                volume=volume_value,
                pitch=pitch_value,
                output_path=output_path,
                fallback_voice=_fallback_voice,
            )
            
            logger.info(f"✅ Generated audio (local Edge TTS): {output_path}")
            return output_path
        
        except Exception as e:
            logger.error(f"Local TTS generation error: {e}")
            raise
    
    async def _call_comfyui_workflow(
        self,
        workflow_info: dict,
        text: str,
        comfyui_url: Optional[str] = None,
        runninghub_api_key: Optional[str] = None,
        voice: Optional[str] = None,
        speed: Optional[float | str] = 1.0,
        pitch: Optional[float | str] = None,
        output_path: Optional[str] = None,
        **params
    ) -> str:
        """
        Generate speech using ComfyUI workflow
        
        Args:
            workflow_info: Workflow info dict from _resolve_workflow()
            text: Text to convert to speech
            comfyui_url: ComfyUI URL
            runninghub_api_key: RunningHub API key
            voice: Voice ID (workflow-specific)
            speed: Speech speed multiplier (workflow-specific)
            pitch: Pitch value (workflow-specific)
            output_path: Custom output path (downloads if URL returned)
            **params: Additional workflow parameters
        
        Returns:
            Generated audio file path (local if output_path provided, otherwise URL)
        """
        logger.info(f"🎙️  Using workflow: {workflow_info['key']}")
        
        # 1. Build workflow parameters (ComfyKit config is now managed by core)
        workflow_params = {"text": text}
        
        # Add optional TTS parameters (only if explicitly provided and not None)
        if voice is not None:
            workflow_params["voice"] = voice
        if speed is not None and speed != 1.0:
            workflow_params["speed"] = speed
        if pitch is not None:
            workflow_params["pitch"] = pitch
        
        # Add any additional parameters
        workflow_params.update(params)
        
        logger.debug(f"Workflow parameters: {workflow_params}")

        explicit_mapping = self._load_runninghub_node_mappings(workflow_info)
        if explicit_mapping:
            return await self._call_runninghub_mapped_workflow(
                workflow_info=workflow_info,
                workflow_params=workflow_params,
                runninghub_api_key=runninghub_api_key,
                output_path=output_path,
                node_mappings=explicit_mapping,
            )
        
        # 3. Execute workflow using shared ComfyKit instance from core
        try:
            # Get shared ComfyKit instance (lazy initialization + config hot-reload)
            kit = await self.core._get_or_create_comfykit()
            
            # Determine what to pass to ComfyKit based on source
            if workflow_info["source"] == "runninghub" and "workflow_id" in workflow_info:
                # RunningHub: pass workflow_id
                workflow_input = workflow_info["workflow_id"]
                logger.info(f"Executing RunningHub TTS workflow: {workflow_input}")
            else:
                # Selfhost: pass file path
                workflow_input = workflow_info["path"]
                logger.info(f"Executing selfhost TTS workflow: {workflow_input}")
            
            result = await kit.execute(workflow_input, workflow_params)
            
            # 4. Handle result
            if result.status != "completed":
                error_msg = result.msg or "Unknown error"
                logger.error(f"TTS generation failed: {error_msg}")
                raise Exception(f"TTS generation failed: {error_msg}")
            
            # ComfyKit result can have audio files in different output types
            # Try to get audio file path from result
            audio_path = None
            
            # Check for audio files in result.audios (if available)
            if hasattr(result, 'audios') and result.audios:
                audio_path = result.audios[0]
                logger.debug(f"✅ Found audio in result.audios: {audio_path}")
            # Check for files in result.files
            elif hasattr(result, 'files') and result.files:
                audio_path = result.files[0]
                logger.debug(f"✅ Found audio in result.files: {audio_path}")
            # Check in outputs dictionary
            elif hasattr(result, 'outputs') and result.outputs:
                logger.debug(f"Searching for audio file in result.outputs: {result.outputs}")
                # Try to find audio file in outputs
                for key, value in result.outputs.items():
                    if isinstance(value, str) and any(value.endswith(ext) for ext in ['.mp3', '.wav', '.flac']):
                        audio_path = value
                        logger.debug(f"✅ Found audio in result.outputs[{key}]: {audio_path}")
                        break
            
            if not audio_path:
                logger.error("No audio file generated")
                logger.error("❌ Result analysis:")
                logger.error(f"   - result.audios: {getattr(result, 'audios', 'NOT_FOUND')}")
                logger.error(f"   - result.files: {getattr(result, 'files', 'NOT_FOUND')}")
                logger.error(f"   - result.outputs: {getattr(result, 'outputs', 'NOT_FOUND')}")
                logger.error(f"   - Full __dict__: {result.__dict__}")
                raise Exception("No audio file generated by workflow")
            
            # If output_path provided and audio_path is URL, download to local
            if output_path and audio_path.startswith(('http://', 'https://')):
                import os

                import httpx
                
                # Ensure parent directory exists
                os.makedirs(os.path.dirname(output_path), exist_ok=True)
                
                logger.info(f"Downloading audio from {audio_path} to {output_path}")
                async with httpx.AsyncClient() as client:
                    response = await client.get(audio_path)
                    response.raise_for_status()
                    
                    with open(output_path, 'wb') as f:
                        f.write(response.content)
                
                logger.info(f"✅ Generated audio (ComfyUI): {output_path}")
                return output_path
            
            logger.info(f"✅ Generated audio (ComfyUI): {audio_path}")
            return audio_path
        
        except Exception as e:
            logger.error(f"TTS generation error: {e}")
            raise

    def _load_runninghub_node_mappings(self, workflow_info: dict[str, Any]) -> dict[str, Any]:
        if workflow_info.get("source") != "runninghub" or not workflow_info.get("workflow_id"):
            return {}
        try:
            with open(workflow_info["path"], "r", encoding="utf-8") as f:
                content = json.load(f)
        except Exception as e:
            logger.warning(f"Failed to read TTS workflow mapping {workflow_info.get('path')}: {e}")
            return {}
        mappings = content.get("runninghub_node_mappings")
        return mappings if isinstance(mappings, dict) else {}

    async def _call_runninghub_mapped_workflow(
        self,
        workflow_info: dict[str, Any],
        workflow_params: dict[str, Any],
        runninghub_api_key: Optional[str],
        output_path: Optional[str],
        node_mappings: dict[str, Any],
    ) -> str:
        from comfykit.comfyui.runninghub_client import RunningHubClient

        api_key = (
            runninghub_api_key
            or self.global_config.get("runninghub_api_key")
            or os.getenv("RUNNINGHUB_API_KEY")
        )
        if not api_key:
            raise RuntimeError("RunningHub API key is required for mapped TTS workflow")

        instance_type = (
            self.global_config.get("runninghub_instance_type")
            or os.getenv("RUNNINGHUB_INSTANCE_TYPE")
            or None
        )
        client = RunningHubClient(
            api_key=api_key,
            base_url=None,
            instance_type=instance_type,
        )
        try:
            node_info_list = await self._build_runninghub_node_info_list(
                client=client,
                workflow_params=workflow_params,
                node_mappings=node_mappings,
            )
            logger.info(
                "Executing mapped RunningHub TTS workflow: "
                f"{workflow_info['workflow_id']} with {len(node_info_list)} params"
            )
            task_data = await client.create_task(
                workflow_id=str(workflow_info["workflow_id"]),
                node_info_list=node_info_list,
            )
            task_id = task_data.get("taskId")
            if not task_id:
                raise RuntimeError(f"RunningHub TTS did not return taskId: {task_data}")

            result_data = await self._wait_for_runninghub_tts_result(client, task_id)
            audio_url = self._extract_audio_url(result_data)
            if not audio_url:
                raise RuntimeError(f"RunningHub TTS returned no audio output: {result_data}")
            if output_path:
                await self._download_audio_output(audio_url, output_path)
                return output_path
            return audio_url
        finally:
            await client.close()

    async def _build_runninghub_node_info_list(
        self,
        client: Any,
        workflow_params: dict[str, Any],
        node_mappings: dict[str, Any],
    ) -> list[dict[str, Any]]:
        node_info_list: list[dict[str, Any]] = []
        for param_name, value in workflow_params.items():
            if value is None:
                continue
            mapping = node_mappings.get(param_name)
            if not isinstance(mapping, dict):
                continue
            field_value = value
            if mapping.get("upload"):
                field_value = await client.upload_file(str(value))
            node_info_list.append(
                {
                    "nodeId": str(mapping["node_id"]),
                    "fieldName": str(mapping["field_name"]),
                    "fieldValue": field_value,
                    "description": str(mapping.get("description") or param_name),
                }
            )
        return node_info_list

    async def _wait_for_runninghub_tts_result(
        self,
        client: Any,
        task_id: str,
        max_wait_time: int = 600,
    ) -> list[dict[str, Any]]:
        start_time = asyncio.get_event_loop().time()
        while True:
            if asyncio.get_event_loop().time() - start_time > max_wait_time:
                raise RuntimeError(f"RunningHub TTS task {task_id} timeout")
            status_info = await client.query_task_status(task_id)
            task_status = status_info.get("status")
            if task_status == "SUCCESS":
                return await client.query_task_result(task_id)
            if task_status == "FAILED":
                raise RuntimeError(
                    status_info.get("msg") or f"RunningHub TTS task {task_id} failed"
                )
            await asyncio.sleep(2)

    def _extract_audio_url(self, result_data: Any) -> str:
        for item in result_data or []:
            if not isinstance(item, dict):
                continue
            file_url = item.get("fileUrl") or item.get("url")
            if not file_url:
                continue
            file_type = str(item.get("fileType") or item.get("outputType") or "").lower()
            if file_type in {"mp3", "wav", "flac", "m4a", "aac"} or "audio" in file_type:
                return str(file_url)
            if str(file_url).lower().split("?")[0].endswith((".mp3", ".wav", ".flac", ".m4a", ".aac")):
                return str(file_url)
        return ""

    async def _download_audio_output(self, audio_url: str, output_path: str) -> None:
        import httpx

        output_dir = os.path.dirname(output_path)
        if output_dir:
            os.makedirs(output_dir, exist_ok=True)
        async with httpx.AsyncClient(timeout=120) as client:
            response = await client.get(audio_url)
            response.raise_for_status()
            with open(output_path, "wb") as f:
                f.write(response.content)
