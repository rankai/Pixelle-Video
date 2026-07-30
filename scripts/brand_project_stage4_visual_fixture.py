"""Seed an isolated BRAND-PROJECT-4 visual/runtime fixture.

The fixture uses only local repositories and the digital-human isolated
executor. It never calls an LLM, media provider, browser platform, or publish
endpoint.
"""

from __future__ import annotations

import argparse
import asyncio
import io
import json
import os
import wave
from pathlib import Path

from PIL import Image

from pixelle_video.app_center.brand_project import (
    BrandProjectService,
    ProjectContextResolver,
)
from pixelle_video.app_center.carousel import (
    CAROUSEL_HEIGHT,
    CAROUSEL_WIDTH,
    DouyinCarouselExecutor,
    DouyinCarouselRenderer,
)
from pixelle_video.app_center.ip_broadcast_adapter import (
    IpBroadcastAppAdapter,
    IpBroadcastBindingStore,
)
from pixelle_video.app_center.repository import AppCenterRepository
from pixelle_video.app_center.runner import AppRunner
from pixelle_video.services.assets_v2.repository import AssetLibraryRepository
from pixelle_video.services.ip_broadcast_workflow import IpBroadcastSessionStore


def _image_bytes(color: str) -> bytes:
    output = io.BytesIO()
    Image.new("RGB", (96, 96), color).save(output, format="PNG")
    return output.getvalue()


def _audio_bytes(frames: int) -> bytes:
    output = io.BytesIO()
    with wave.open(output, "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(16_000)
        audio.writeframes(b"\x00\x00" * frames)
    return output.getvalue()


def _upload(
    repository: AssetLibraryRepository,
    kind: str,
    payload: bytes,
    *,
    name: str,
) -> dict:
    suffix = "png" if kind == "image" else "wav"
    session = repository.create_upload_session(f"{name}.{suffix}", len(payload), kind)
    repository.append_upload_chunk(session["upload_id"], payload)
    return repository.finalize_upload(session["upload_id"])


def _server_run(
    repository: AppCenterRepository,
    resolver: ProjectContextResolver,
    *,
    project_id: str,
    app_id: str,
    payload: dict,
    idempotency_key: str,
):
    snapshot_id = repository.resolve_run_context_snapshot(
        project_id,
        payload,
        expected_context_snapshot_id=None,
    )
    resolver.resolve_for_application(
        project_id,
        snapshot_id,
        app_id=app_id,
    )
    return repository.create_app_run(
        project_id,
        app_id,
        "1.0.0",
        repository.canonicalize_run_input(
            payload,
            project_id=project_id,
            app_id=app_id,
            context_snapshot_id=snapshot_id,
        ),
        idempotency_key=idempotency_key,
        context_snapshot_id=snapshot_id,
    )


def _artifact_for_run(
    repository: AppCenterRepository,
    run,
    *,
    artifact_type: str,
    name: str,
    content: dict,
):
    artifact = repository.create_artifact(
        run.project_id,
        artifact_type,
        name,
        source_app_run_id=run.app_run_id,
    )
    version = repository.append_artifact_version(
        artifact.artifact_id,
        content=content,
    )
    repository.set_output_artifacts(run.app_run_id, [artifact.artifact_id])
    repository.transition_app_run(run.app_run_id, "queued")
    repository.transition_app_run(run.app_run_id, "running")
    repository.transition_app_run(run.app_run_id, "needs_review")
    repository.transition_app_run(run.app_run_id, "completed")
    return artifact, version


def _copy_content(label: str, context: dict) -> dict:
    variants = []
    for index, angle in enumerate(("利益", "好奇", "场景"), start=1):
        hook = f"{label}第{index}个开场"
        body = "夏日冰咖啡，适合附近上班族午后到店。"
        cta = "欢迎到快闪店了解"
        full_text = hook + body + cta
        variants.append(
            {
                "version_name": f"版本{index}",
                "angle": angle,
                "hook": hook,
                "body": body,
                "cta": cta,
                "full_text": full_text,
                "word_count": len(full_text),
                "estimated_seconds": max(1, (len(full_text) + 3) // 4),
            }
        )
    return {
        "schema_version": 1,
        "artifact_type": "copywriting",
        "validation_facts": {"input": {"goal": label}, "context": context},
        "variants": variants,
        "missing_facts": [],
        "risk_flags": [],
    }


async def seed(root: Path) -> dict:
    os.environ["PIXELLE_VIDEO_ROOT"] = str(root)
    os.environ["PIXELLE_APP_CENTER_DB"] = str(root / "data" / "app_center.sqlite")
    data_root = root / "data"
    assets = AssetLibraryRepository(data_root)
    repository = AppCenterRepository(
        data_root / "app_center.sqlite",
        asset_repository=assets,
    )
    old_logo = _upload(assets, "image", _image_bytes("#EC4899"), name="stage4-old-logo")
    old_bgm = _upload(assets, "audio", _audio_bytes(800), name="stage4-old-bgm")
    new_logo = _upload(assets, "image", _image_bytes("#14B8A6"), name="stage4-new-logo")
    new_bgm = _upload(assets, "audio", _audio_bytes(1_600), name="stage4-new-bgm")
    content_image = _upload(
        assets,
        "image",
        _image_bytes("#F59E0B"),
        name="stage4-carousel-content",
    )
    assets.create_brand_kit(
        {
            "brand_id": "brand-stage4-visual",
            "brand_name": "北岸咖啡",
            "logo_asset_id": old_logo["asset_id"],
            "default_bgm_asset_id": old_bgm["asset_id"],
            "primary_color": "#7C3AED",
            "secondary_color": "#F5F3FF",
            "font_family": "noto-sans-sc-bold",
            "default_subtitle_style": "readable_v2",
            "ending_card_text": "北岸咖啡，午后见",
            "store_address": "江湾路 18 号",
            "phone": "021-88886666",
            "coupon_phrase": "到店出示视频享新品礼",
        }
    )
    service = BrandProjectService(repository, assets)
    project, old_snapshot = service.create_project(
        "夏日冰咖啡推广",
        "吸引附近上班族午后到店",
        brand_id="brand-stage4-visual",
        expected_domain_revision=1,
        project_overrides={
            "store_address": "江湾路 18 号夏日快闪店",
            "ending_card_text": "仅本项目：夏日快闪店见",
        },
    )
    resolver = ProjectContextResolver(repository, assets)
    old_run = _server_run(
        repository,
        resolver,
        project_id=project.project_id,
        app_id="builtin.marketing-copy",
        payload={
            "goal": "同步前文案",
            "product_or_service": "夏日冰咖啡",
            "content_format": "oral",
            "length_bucket": "short_15s",
        },
        idempotency_key="stage4-visual-old-copy",
    )
    old_context = resolver.resolve_for_application(
        project.project_id,
        old_snapshot.context_snapshot_id,
        app_id="builtin.marketing-copy",
    )
    old_artifact, old_version = _artifact_for_run(
        repository,
        old_run,
        artifact_type="copywriting",
        name="同步前固定品牌文案",
        content=_copy_content("同步前固定版本", old_context),
    )

    assets.patch_brand_kit(
        "brand-stage4-visual",
        {
            "brand_name": "北岸咖啡 · 焕新",
            "logo_asset_id": new_logo["asset_id"],
            "default_bgm_asset_id": new_bgm["asset_id"],
            "primary_color": "#0F766E",
            "secondary_color": "#ECFDF5",
            "store_address": "江湾路 88 号",
        },
    )
    sync_result = service.sync_brand(
        project.project_id,
        expected_context_snapshot_id=old_snapshot.context_snapshot_id,
        idempotency_key="stage4-visual-sync",
    )
    current_snapshot = repository.get_context_snapshot(sync_result["context_snapshot_id"])
    current_context = resolver.resolve_for_application(
        project.project_id,
        current_snapshot.context_snapshot_id,
        app_id="builtin.marketing-copy",
    )
    new_run = _server_run(
        repository,
        resolver,
        project_id=project.project_id,
        app_id="builtin.marketing-copy",
        payload={
            "goal": "同步后文案",
            "product_or_service": "夏日冰咖啡",
            "content_format": "oral",
            "length_bucket": "short_15s",
        },
        idempotency_key="stage4-visual-new-copy",
    )
    new_artifact, new_version = _artifact_for_run(
        repository,
        new_run,
        artifact_type="copywriting",
        name="同步后新品牌文案",
        content=_copy_content("同步后新版本", current_context),
    )

    title_run = _server_run(
        repository,
        resolver,
        project_id=project.project_id,
        app_id="builtin.viral-titles",
        payload={
            "platform": "douyin",
            "objective": "click",
            "count": 5,
            "source_artifact_version_id": old_version.artifact_version_id,
        },
        idempotency_key="stage4-visual-title",
    )
    title_artifact, title_version = _artifact_for_run(
        repository,
        title_run,
        artifact_type="title_set",
        name="固定旧来源的标题候选",
        content={
            "schema_version": 1,
            "artifact_type": "title_set",
            "validation_facts": {
                "input": title_run.input_payload,
                "context": resolver.resolve_for_application(
                    project.project_id,
                    title_run.context_snapshot_id,
                    app_id="builtin.viral-titles",
                ),
            },
            "candidates": [
                {
                    "title": f"夏日冰咖啡到店理由 {index}",
                    "angle": "场景",
                    "objective": "click",
                    "length": len(f"夏日冰咖啡到店理由 {index}"),
                    "banned_matches": [],
                    "risk_labels": ["无"],
                }
                for index in range(1, 6)
            ],
            "missing_facts": [],
            "risk_flags": [],
        },
    )
    repository.create_handoff(
        project.project_id,
        old_artifact.artifact_id,
        old_version.artifact_version_id,
        "builtin.viral-titles",
        "1.0.0",
        [old_version.artifact_version_id],
        source_app_run_id=old_run.app_run_id,
        target_run_id=title_run.app_run_id,
        mapping_version=2,
    )

    carousel_run = _server_run(
        repository,
        resolver,
        project_id=project.project_id,
        app_id="builtin.douyin-carousel",
        payload={
            "goal": "生成三页到店图文",
            "source_artifact_version_ids": [new_version.artifact_version_id],
            "page_count": 3,
            "template_id": "template:clean-01",
            "pages": [
                {
                    "page_index": index,
                    "purpose": "content",
                    "text": f"第{index}页：北岸咖啡夏日冰咖啡到店理由",
                    "asset_refs": [content_image["asset_id"]],
                    "font_id": "noto-sans-sc-bold",
                    "dimensions": {
                        "width_px": CAROUSEL_WIDTH,
                        "height_px": CAROUSEL_HEIGHT,
                    },
                }
                for index in range(1, 4)
            ],
        },
        idempotency_key="stage4-visual-carousel",
    )
    content_image_path = assets.get_revision_path(content_image["asset_id"])
    if content_image_path is None:
        raise RuntimeError("carousel content image revision missing")
    carousel_renderer = DouyinCarouselRenderer(
        asset_resolver=lambda ref: (
            content_image_path if ref == content_image["asset_id"] else None
        ),
    )
    carousel_runner = AppRunner(
        repository,
        executors={
            "builtin.douyin-carousel": DouyinCarouselExecutor(
                carousel_renderer,
                repository=repository,
                context_resolver=resolver,
            )
        },
        enforce_readiness=False,
    )
    carousel_result = await carousel_runner.run(carousel_run.app_run_id)
    if carousel_result.state != "needs_review":
        raise RuntimeError(f"carousel execution failed: {carousel_result.state}")
    carousel_result = carousel_runner.accept_output(carousel_result.app_run_id)
    carousel_outputs = [
        repository.get_artifact(artifact_id) for artifact_id in carousel_result.output_artifact_ids
    ]
    carousel_artifact = next(
        item for item in carousel_outputs if item.artifact_type == "carousel_package"
    )
    carousel_pages = sorted(
        (item for item in carousel_outputs if item.artifact_type == "carousel_page"),
        key=lambda item: item.name,
    )
    carousel_version = repository.get_artifact_version(carousel_artifact.current_version_id)
    carousel_page_versions = [
        repository.get_artifact_version(item.current_version_id) for item in carousel_pages
    ]

    sessions = IpBroadcastSessionStore(data_root / "ip_broadcast_sessions")
    bindings = IpBroadcastBindingStore(
        data_root / "app_center" / "ip_broadcast_bindings" / "bindings.json"
    )
    digital_adapter = IpBroadcastAppAdapter(
        repository,
        session_store=sessions,
        binding_store=bindings,
        enforce_feature_flag=False,
        trusted_roots=[data_root],
        context_resolver=resolver,
    )
    digital_handle = digital_adapter.create_or_resume(
        project.project_id,
        {
            "source_mode": "blank_project",
            "goal": "夏日冰咖啡口播视频",
            "source_artifact_version_ids": [],
        },
        idempotency_key="stage4-visual-digital",
    )
    digital_result = await digital_adapter.execute_local(digital_handle.run.app_run_id)
    digital_result = digital_adapter.accept_local_outputs(digital_result.run.app_run_id)
    digital_artifacts = {}
    for artifact_id in digital_result.run.output_artifact_ids:
        artifact = repository.get_artifact(artifact_id)
        digital_artifacts[artifact.artifact_type] = artifact.current_version_id

    return {
        "fixture": "BRAND-PROJECT-4",
        "project_id": project.project_id,
        "old_context_snapshot_id": old_snapshot.context_snapshot_id,
        "current_context_snapshot_id": current_snapshot.context_snapshot_id,
        "old_marketing_run_id": old_run.app_run_id,
        "old_marketing_artifact_version_id": old_version.artifact_version_id,
        "new_marketing_run_id": new_run.app_run_id,
        "new_marketing_artifact_version_id": new_version.artifact_version_id,
        "title_run_id": title_run.app_run_id,
        "title_artifact_id": title_artifact.artifact_id,
        "title_artifact_version_id": title_version.artifact_version_id,
        "carousel_run_id": carousel_run.app_run_id,
        "carousel_artifact_id": carousel_artifact.artifact_id,
        "carousel_artifact_version_id": carousel_version.artifact_version_id,
        "carousel_page_artifact_ids": [item.artifact_id for item in carousel_pages],
        "carousel_page_artifact_version_ids": [
            item.artifact_version_id for item in carousel_page_versions
        ],
        "carousel_page_file_refs": [item.file_refs[0] for item in carousel_page_versions],
        "digital_run_id": digital_result.run.app_run_id,
        "digital_session_id": digital_result.binding.session_id,
        "digital_source_revision": digital_result.binding.source_revision,
        "digital_step_status": digital_result.session.step_status,
        "digital_artifact_versions": digital_artifacts,
        "new_logo_asset_id": new_logo["asset_id"],
        "new_bgm_asset_id": new_bgm["asset_id"],
        "external_actions": 0,
        "platform_publish_actions": 0,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    args.root.mkdir(parents=True, exist_ok=True)
    result = asyncio.run(seed(args.root.resolve()))
    encoded = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded + "\n", encoding="utf-8")
    print(encoded)


if __name__ == "__main__":
    main()
