"""Trusted built-in application registry for the P0 application directory.

This module is deliberately read-only. It owns manifest metadata and the
effective feature/capability calculation; execution, projects, runs, and
artifacts are later stages.
"""

from __future__ import annotations

import os
from copy import deepcopy
from typing import Any

from pixelle_video.config import config_manager

BUILTIN_MANIFESTS: tuple[dict[str, Any], ...] = (
    {
        "schema_version": 1,
        "app_id": "builtin.marketing-copy",
        "version": "1.0.0",
        "name": "门店营销文案",
        "description": "生成可编辑门店营销文案",
        "category": "copywriting",
        "status": "stable",
        "icon": "FilePenLine",
        "executor_type": "structured_llm",
        "executor_key": "marketing_copy_v1",
        "input_schema": "marketing-copy-input.v1",
        "output_schema": "marketing-copy-output.v1",
        "required_capabilities": ["llm"],
        "accepted_artifact_types": ["brief"],
        "produced_artifact_types": ["copywriting"],
        "handoff_targets": ["builtin.viral-titles", "builtin.douyin-carousel", "builtin.digital-human-video"],
        "feature_flag": "contentApps",
        "sort_order": 10,
    },
    {
        "schema_version": 1,
        "app_id": "builtin.viral-titles",
        "version": "1.0.0",
        "name": "爆款标题",
        "description": "生成多角度标题候选",
        "category": "copywriting",
        "status": "stable",
        "icon": "BadgeCheck",
        "executor_type": "structured_llm",
        "executor_key": "viral_titles_v1",
        "input_schema": "viral-titles-input.v1",
        "output_schema": "viral-titles-output.v1",
        "required_capabilities": ["llm"],
        "accepted_artifact_types": ["copywriting"],
        "produced_artifact_types": ["title_set", "selected_title"],
        "handoff_targets": ["builtin.douyin-carousel", "builtin.digital-human-video"],
        "feature_flag": "contentApps",
        "sort_order": 20,
    },
    {
        "schema_version": 1,
        "app_id": "builtin.douyin-carousel",
        "version": "1.0.0",
        "name": "抖音图文",
        "description": "策划、渲染和导出抖音图文",
        "category": "carousel",
        "status": "pilot",
        "icon": "Images",
        "executor_type": "document_render",
        "executor_key": "douyin_carousel_v1",
        "input_schema": "douyin-carousel-input.v1",
        "output_schema": "douyin-carousel-output.v1",
        "required_capabilities": ["llm", "template"],
        "accepted_artifact_types": ["copywriting", "selected_title"],
        "produced_artifact_types": ["carousel_plan", "carousel_page", "carousel_package", "publish_copy"],
        "handoff_targets": [],
        "feature_flag": "douyinCarousel",
        "sort_order": 30,
    },
    {
        "schema_version": 1,
        "app_id": "builtin.digital-human-video",
        "version": "1.0.0",
        "name": "数字人口播视频",
        "description": "复用既有口播链路制作视频",
        "category": "video",
        "status": "pilot",
        "icon": "Video",
        "executor_type": "workflow_adapter",
        "executor_key": "digital_human_video_v1",
        "input_schema": "digital-human-video-input.v1",
        "output_schema": "digital-human-video-output.v1",
        "required_capabilities": ["llm", "runninghub", "digital_human"],
        "accepted_artifact_types": ["copywriting", "selected_title"],
        "produced_artifact_types": ["video", "cover", "publish_copy"],
        "handoff_targets": [],
        "feature_flag": "digitalHumanInAppCenter",
        "sort_order": 40,
    },
)

FEATURE_FLAG_ENV = {
    "contentApps": "PIXELLE_APP_CENTER_CONTENT_APPS",
    "douyinCarousel": "PIXELLE_APP_CENTER_DOUYIN_CAROUSEL",
    "digitalHumanInAppCenter": "PIXELLE_APP_CENTER_DIGITAL_HUMAN",
}


def _flag_enabled(flag_name: str) -> bool:
    value = os.environ.get(FEATURE_FLAG_ENV.get(flag_name, ""), "")
    return value.strip().lower() in {"1", "true", "yes", "on"}


def configured_capabilities() -> set[str]:
    cfg = config_manager.config
    capabilities: set[str] = {"template"}
    if cfg.is_llm_configured():
        capabilities.add("llm")
    if cfg.comfyui.runninghub_api_key:
        capabilities.update({"runninghub", "digital_human"})
    return capabilities


def _effective_manifest(manifest: dict[str, Any], capabilities: set[str]) -> dict[str, Any]:
    item = deepcopy(manifest)
    enabled = _flag_enabled(str(item["feature_flag"]))
    missing = sorted(set(item["required_capabilities"]) - capabilities)
    if not enabled:
        readiness = "disabled"
    elif missing:
        readiness = "not_ready"
    elif item["status"] in {"disabled", "retired", "maintenance", "draft"}:
        readiness = "not_ready"
    else:
        readiness = "ready"
    item["enabled"] = enabled
    item["readiness"] = {
        "status": readiness,
        "missing_capabilities": missing,
        "configured_capabilities": sorted(capabilities),
    }
    return item


def list_effective_apps() -> list[dict[str, Any]]:
    capabilities = configured_capabilities()
    return [_effective_manifest(item, capabilities) for item in sorted(BUILTIN_MANIFESTS, key=lambda value: value["sort_order"])]


def get_app(app_id: str) -> dict[str, Any] | None:
    return next((item for item in list_effective_apps() if item["app_id"] == app_id), None)


def get_app_readiness(app_id: str) -> dict[str, Any] | None:
    item = get_app(app_id)
    if item is None:
        return None
    return {"app_id": item["app_id"], **item["readiness"]}
