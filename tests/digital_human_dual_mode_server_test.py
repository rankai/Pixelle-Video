import asyncio
import json
import sqlite3

import pytest

from pixelle_video.app_center import digital_human_input as digital_human_input_module
from pixelle_video.app_center.digital_human_feature_gate import evaluate_digital_human_feature_gate
from pixelle_video.app_center.digital_human_input import (
    DigitalHumanInputError,
    normalize_digital_human_input,
    validate_trusted_media_binding,
)
from pixelle_video.app_center.ip_broadcast_adapter import (
    IpBroadcastAppAdapter,
    IpBroadcastBindingStore,
    IpBroadcastInputError,
)
from pixelle_video.app_center.registry import BUILTIN_MANIFESTS, get_app, is_app_version_supported
from pixelle_video.app_center.repository import AppCenterRepository
from pixelle_video.services.ip_broadcast_workflow import IpBroadcastSessionStore


def _v2(mode="image_talking", profile="stable"):
    return {
        "schema_version": 2,
        "project_id": "project-a",
        "content_source": {"mode": "custom_script", "script": "完整门店口播文案。"},
        "digital_human": {
            "mode": mode,
            "portrait_id": "dh-a",
            "scene_id": "scene-a",
            "asset_revision_id": "rev-a",
            "workflow_profile": profile,
        },
        "delivery": {"subtitle_preset": "readable_v2"},
    }


def _copywriting_content():
    return {
        "schema_version": 1,
        "artifact_type": "copywriting",
        "variants": [
            {
                "version_name": name,
                "angle": angle,
                "hook": hook,
                "body": body,
                "cta": "欢迎来店咨询",
                "full_text": full_text,
                "word_count": len(full_text),
                "estimated_seconds": 6,
            }
            for name, angle, hook, body, full_text in (
                (
                    "门店口播",
                    "场景",
                    "路过别错过",
                    "今天到店有活动",
                    "路过别错过，今天到店有活动，欢迎来店咨询。",
                ),
                (
                    "优惠口播",
                    "利益",
                    "进店先看",
                    "到店有专属优惠",
                    "进店先看，到店有专属优惠，欢迎来店咨询。",
                ),
                (
                    "服务口播",
                    "身份",
                    "老板们看过来",
                    "把服务讲清楚",
                    "老板们看过来，把服务讲清楚，欢迎来店咨询。",
                ),
            )
        ],
        "missing_facts": [],
        "risk_flags": [],
    }


def test_v2_normalization_pins_mode_profile_and_source_fingerprint():
    normalized = normalize_digital_human_input(_v2(), project_id="project-a")

    assert normalized.app_version == "1.1.0"
    assert normalized.schema_version == 2
    assert normalized.payload["digital_human"]["workflow_revision"] == "digital_combination.v1"
    assert normalized.source_revision.startswith("sha256:")
    assert (
        normalized.source_revision
        != normalize_digital_human_input(
            {**_v2(), "digital_human": {**_v2()["digital_human"], "asset_revision_id": "rev-b"}},
            project_id="project-a",
        ).source_revision
    )


def test_v1_blank_and_selected_title_normalize_without_title_only_new_run():
    blank = normalize_digital_human_input(
        {"app_version": "1.0.0", "source_mode": "blank_project", "goal": "新店开业活动"},
        project_id="project-a",
    )
    assert blank.payload["content_source"] == {"mode": "custom_script", "script": "新店开业活动"}

    resume = normalize_digital_human_input(
        {
            "app_version": "1.0.0",
            "source_mode": "selected_title",
            "source_artifact_version_ids": ["av-title-a"],
            "session_id": "session-old",
            "resume_mode": "resume_existing",
        },
        project_id="project-a",
    )
    assert resume.resume_only is True

    with pytest.raises(DigitalHumanInputError, match="DIGITAL_HUMAN_TITLE_REQUIRES_SCRIPT"):
        normalize_digital_human_input(
            {
                "app_version": "1.0.0",
                "source_mode": "selected_title",
                "source_artifact_version_ids": ["av-title-a"],
            },
            project_id="project-a",
        )


@pytest.mark.parametrize(
    "payload",
    [
        {"schema_version": 99, "source_mode": "blank_project", "goal": "未知"},
        {"app_version": "9.9.9", "source_mode": "blank_project", "goal": "未知"},
        {
            "schema_version": 1,
            "app_version": "9.9.9",
            "source_mode": "blank_project",
            "goal": "未知",
        },
        {"schema_version": 2, "app_version": "1.0.0", **_v2()},
    ],
)
def test_unknown_or_mismatched_versions_fail_closed(payload):
    with pytest.raises(DigitalHumanInputError, match="INPUT_PAYLOAD_INVALID"):
        normalize_digital_human_input(payload, project_id="project-a")


@pytest.mark.parametrize(
    "mutator",
    [
        lambda value: value["content_source"].update({"script": []}),
        lambda value: value["content_source"].update({"script": 123}),
        lambda value: value["content_source"].update({"script": False}),
        lambda value: value["content_source"].update(
            {
                "mode": "copywriting_artifact",
                "source_artifact_version_id": [],
                "selected_variant_index": 0,
            }
        ),
        lambda value: value["content_source"].update(
            {
                "mode": "copywriting_artifact",
                "source_artifact_version_id": "copy-a",
                "selected_variant_index": 0.0,
            }
        ),
    ],
)
def test_v2_normalization_rejects_wrong_field_types(mutator):
    payload = _v2()
    mutator(payload)
    with pytest.raises(DigitalHumanInputError, match="DIGITAL_HUMAN_CONTENT_SOURCE_INCOMPLETE"):
        normalize_digital_human_input(payload, project_id="project-a")


@pytest.mark.parametrize(
    "injected_key", ["digital_human_workflow", "digital_human_workflow_revision"]
)
def test_v2_normalization_rejects_client_workflow_binding(injected_key):
    payload = _v2()
    payload[injected_key] = "/private/provider/workflow.json"
    with pytest.raises(DigitalHumanInputError, match="INPUT_PAYLOAD_INVALID"):
        normalize_digital_human_input(payload, project_id="project-a")


def test_media_mode_scene_revision_and_quality_are_server_validated():
    image = {
        "media_type": "image",
        "status": "ready",
        "revision_id": "rev-a",
        "mime_type": "image/jpeg",
        "width": 1080,
        "height": 1920,
    }
    binding = validate_trusted_media_binding(_v2(), asset=image, scene={"media_type": "image"})
    assert binding.workflow_key == "digital_combination"

    video_input = _v2("video_lipsync", "natural")
    video = {
        "media_type": "video",
        "status": "ready",
        "revision_id": "rev-a",
        "mime_type": "video/mp4",
        "width": 1080,
        "height": 1920,
        "duration_ms": 12000,
    }
    video_binding = validate_trusted_media_binding(
        video_input, asset=video, scene={"media_type": "video"}
    )
    assert video_binding.workflow_key == "digital_lip_sync_video"

    with pytest.raises(DigitalHumanInputError, match="DIGITAL_HUMAN_MEDIA_TYPE_MISMATCH"):
        validate_trusted_media_binding(
            video_input, asset=image, scene={"media_type": "image"}, require_released_workflow=False
        )

    with pytest.raises(DigitalHumanInputError, match="DIGITAL_HUMAN_VIDEO_DURATION_INVALID"):
        validate_trusted_media_binding(
            _v2("video_lipsync", "natural"),
            asset={**video, "duration_ms": 3000},
            scene={"media_type": "video"},
            require_released_workflow=False,
        )
    with pytest.raises(DigitalHumanInputError, match="DIGITAL_HUMAN_VIDEO_GEOMETRY_INVALID"):
        validate_trusted_media_binding(
            video_input,
            asset={**video, "width": "not-a-number"},
            scene={"media_type": "video"},
            require_released_workflow=False,
        )
    with pytest.raises(DigitalHumanInputError, match="DIGITAL_HUMAN_PORTRAIT_SCENE_MISMATCH"):
        validate_trusted_media_binding(
            _v2(), asset=image, scene={"media_type": "image", "profile_id": "other-portrait"}
        )
    with pytest.raises(DigitalHumanInputError, match="DIGITAL_HUMAN_SCENE_NOT_READY"):
        validate_trusted_media_binding(
            _v2(), asset=image, scene={"media_type": "image", "status": "archived"}
        )


def test_registry_exposes_v1_and_v2_mapping_without_changing_directory_card():
    assert is_app_version_supported("builtin.digital-human-video", "1.0.0") is True
    assert is_app_version_supported("builtin.digital-human-video", "1.1.0") is True
    assert is_app_version_supported("builtin.digital-human-video", "9.9.9") is False
    v2 = get_app("builtin.digital-human-video", version="1.1.0")
    assert v2["version"] == "1.1.0"
    assert v2["input_schema"] == "digital-human-video-input.v2"


def test_adapter_binds_v2_run_to_new_version_and_preserves_v1_seam(tmp_path):
    repository = AppCenterRepository(tmp_path / "app-center.sqlite")
    project = repository.create_project("门店项目", "到店咨询")
    adapter = IpBroadcastAppAdapter(
        repository,
        session_store=IpBroadcastSessionStore(tmp_path / "sessions"),
        binding_store=IpBroadcastBindingStore(tmp_path / "bindings.json"),
        enforce_feature_flag=False,
        dual_backend_flag=True,
        dual_desktop_flag=True,
        dual_desktop_ready=True,
        digital_human_asset_resolver=lambda _scene_id: (
            {
                "media_type": "image",
                "status": "ready",
                "revision_id": "rev-a",
                "mime_type": "image/jpeg",
                "width": 1080,
                "height": 1920,
            },
            {"media_type": "image"},
        ),
    )
    payload = _v2()
    payload["project_id"] = project.project_id
    result = adapter.create_or_resume(project.project_id, payload, idempotency_key="dh-v2-server-1")

    assert result.run.app_version == "1.1.0"
    assert result.run.input_schema_version == 2
    assert result.binding.app_version == "1.1.0"
    assert result.run.input_payload["digital_human_mode"] == "image_talking"
    session = adapter.session_store.get_session(result.binding.session_id)
    assert (
        session.state["digital_human_workflow"] == "workflows/runninghub/digital_combination.json"
    )
    assert session.state["portrait_media_type"] == "image"
    assert session.state["portrait_id"] == "dh-a"
    assert session.state["digital_human_scene_id"] == "scene-a"
    assert session.state["digital_human_asset_revision_id"] == "rev-a"
    assert session.state["digital_human_workflow_revision"] == "digital_combination.v1"
    adapter.dual_backend_flag = False
    with pytest.raises(IpBroadcastInputError, match="APP_DUAL_MODE_NOT_READY"):
        asyncio.run(adapter.execute_provider(result.run.app_run_id, object()))
    adapter.dual_backend_flag = True
    replay = adapter.create_or_resume(project.project_id, payload, idempotency_key="dh-v2-server-1")
    assert replay.run.app_run_id == result.run.app_run_id
    repository.transition_app_run(result.run.app_run_id, "queued")
    repository.transition_app_run(result.run.app_run_id, "running")
    repository.transition_app_run(result.run.app_run_id, "failed")
    adapter.dual_backend_flag = False
    with pytest.raises(IpBroadcastInputError, match="APP_DUAL_MODE_NOT_READY"):
        adapter.retry(result.run.app_run_id)


def test_adapter_accepts_video_after_quality_gate_without_enabling_default_publish(tmp_path):
    repository = AppCenterRepository(tmp_path / "app-center.sqlite")
    project = repository.create_project("门店项目", "到店咨询")
    payload = _v2("video_lipsync", "natural")
    payload["project_id"] = project.project_id

    def resolver(_scene_id):
        return (
            {
                "media_type": "video",
                "status": "ready",
                "revision_id": "rev-a",
                "mime_type": "video/mp4",
                "width": 1080,
                "height": 1920,
                "duration_ms": 12000,
            },
            {"media_type": "video"},
        )

    adapter = IpBroadcastAppAdapter(
        repository,
        session_store=IpBroadcastSessionStore(tmp_path / "sessions"),
        binding_store=IpBroadcastBindingStore(tmp_path / "bindings.json"),
        enforce_feature_flag=False,
        dual_backend_flag=True,
        dual_desktop_flag=True,
        dual_desktop_ready=True,
        digital_human_asset_resolver=resolver,
    )
    result = adapter.create_or_resume(
        project.project_id, payload, idempotency_key="dh-video-stable-1"
    )
    assert result.run.app_version == "1.1.0"
    session = adapter.session_store.get_session(result.binding.session_id)
    assert session.state["digital_human_workflow"] == (
        "workflows/runninghub/digital_lip_sync_video.json"
    )
    assert session.state["portrait_media_type"] == "video"
    assert session.state.get("platform_actions", 0) == 0
    assert session.state.get("final_publish_clicked", False) is False


def test_adapter_does_not_silently_downgrade_explicit_v2_or_unknown_versions(tmp_path):
    repository = AppCenterRepository(tmp_path / "app-center.sqlite")
    project = repository.create_project("门店项目", "到店咨询")
    adapter = IpBroadcastAppAdapter(
        repository,
        session_store=IpBroadcastSessionStore(tmp_path / "sessions"),
        binding_store=IpBroadcastBindingStore(tmp_path / "bindings.json"),
        enforce_feature_flag=False,
        dual_backend_flag=True,
        dual_desktop_flag=True,
        dual_desktop_ready=True,
        digital_human_asset_resolver=lambda _scene_id: (
            {
                "media_type": "image",
                "status": "ready",
                "revision_id": "rev-a",
                "mime_type": "image/jpeg",
                "width": 1080,
                "height": 1920,
            },
            {"media_type": "image"},
        ),
    )
    missing_schema = _v2()
    missing_schema["project_id"] = project.project_id
    missing_schema["app_version"] = "1.1.0"
    missing_schema.pop("schema_version")
    with pytest.raises(IpBroadcastInputError, match="INPUT_PAYLOAD_INVALID"):
        adapter.create_or_resume(project.project_id, missing_schema, idempotency_key="dh-version-1")
    unknown = {"app_version": "9.9.9", "source_mode": "blank_project", "goal": "不能降级"}
    with pytest.raises(IpBroadcastInputError, match="INPUT_PAYLOAD_INVALID"):
        adapter.create_or_resume(project.project_id, unknown, idempotency_key="dh-version-2")


def test_adapter_rejects_v2_when_joint_runtime_gate_is_not_enabled(tmp_path):
    repository = AppCenterRepository(tmp_path / "app-center.sqlite")
    project = repository.create_project("门店项目", "到店咨询")
    payload = _v2()
    payload["project_id"] = project.project_id

    def inert_resolver(_scene_id):
        return {}, {}

    adapter = IpBroadcastAppAdapter(
        repository,
        session_store=IpBroadcastSessionStore(tmp_path / "sessions"),
        binding_store=IpBroadcastBindingStore(tmp_path / "bindings.json"),
        enforce_feature_flag=False,
        digital_human_asset_resolver=inert_resolver,
    )
    with pytest.raises(IpBroadcastInputError, match="APP_DUAL_MODE_NOT_READY"):
        adapter.create_or_resume(project.project_id, payload, idempotency_key="dh-gate-off-1")


def test_generated_copy_requires_completed_source_run_and_natural_profile_routes(tmp_path):
    repository = AppCenterRepository(tmp_path / "app-center.sqlite")
    project = repository.create_project("门店项目", "到店咨询")
    source_run = repository.create_app_run(
        project.project_id,
        "builtin.marketing-copy",
        "1.0.0",
        {"goal": "生成门店营销文案"},
        idempotency_key="marketing-source-1",
    )
    artifact = repository.create_artifact(
        project.project_id,
        "copywriting",
        "已生成文案",
        source_app_run_id=source_run.app_run_id,
    )
    version = repository.append_artifact_version(
        artifact.artifact_id, content=_copywriting_content()
    )
    payload = _v2("image_talking", "natural")
    payload.update(
        {
            "project_id": project.project_id,
            "content_source": {
                "mode": "generated_marketing_copy",
                "source_artifact_version_id": version.artifact_version_id,
                "selected_variant_index": 0,
            },
        }
    )

    def resolver(_scene_id):
        return (
            {
                "media_type": "image",
                "status": "ready",
                "revision_id": "rev-a",
                "mime_type": "image/jpeg",
                "width": 1080,
                "height": 1920,
            },
            {"media_type": "image", "profile_id": "dh-a"},
        )

    def make_adapter():
        return IpBroadcastAppAdapter(
            repository,
            session_store=IpBroadcastSessionStore(tmp_path / "sessions"),
            binding_store=IpBroadcastBindingStore(tmp_path / "bindings.json"),
            enforce_feature_flag=False,
            dual_backend_flag=True,
            dual_desktop_flag=True,
            dual_desktop_ready=True,
            digital_human_asset_resolver=resolver,
            allow_unreleased_workflows_for_controlled_live=True,
        )

    with pytest.raises(IpBroadcastInputError, match="DIGITAL_HUMAN_CONTENT_SOURCE_INCOMPLETE"):
        make_adapter().create_or_resume(project.project_id, payload, idempotency_key="generated-1")
    repository.transition_app_run(source_run.app_run_id, "queued")
    repository.transition_app_run(source_run.app_run_id, "running")
    repository.transition_app_run(source_run.app_run_id, "completed")
    result = make_adapter().create_or_resume(
        project.project_id, payload, idempotency_key="generated-2"
    )
    assert (
        result.session.state["digital_human_workflow"]
        == "workflows/runninghub/digital_talk_image_prompt.json"
    )
    assert result.session.state["digital_human_workflow_revision"] == "digital_talk_image_prompt.v1"


def test_title_plus_copywriting_validates_title_artifact_type_and_project(tmp_path):
    repository = AppCenterRepository(tmp_path / "app-center.sqlite")
    project = repository.create_project("门店项目", "到店咨询")
    other_project = repository.create_project("其他项目", "其他目标")
    copy_artifact = repository.create_artifact(project.project_id, "copywriting", "文案")
    copy_version = repository.append_artifact_version(
        copy_artifact.artifact_id, content=_copywriting_content()
    )
    title_artifact = repository.create_artifact(project.project_id, "selected_title", "标题")
    title_version = repository.append_artifact_version(
        title_artifact.artifact_id, content={"title": "到店前先看这件事"}
    )
    other_title = repository.create_artifact(other_project.project_id, "selected_title", "其他标题")
    other_title_version = repository.append_artifact_version(
        other_title.artifact_id, content={"title": "跨项目标题"}
    )
    adapter = IpBroadcastAppAdapter(
        repository,
        session_store=IpBroadcastSessionStore(tmp_path / "sessions"),
        binding_store=IpBroadcastBindingStore(tmp_path / "bindings.json"),
        enforce_feature_flag=False,
        dual_backend_flag=True,
        dual_desktop_flag=True,
        dual_desktop_ready=True,
        allow_unreleased_workflows_for_controlled_live=True,
        digital_human_asset_resolver=lambda _scene_id: (
            {
                "media_type": "image",
                "status": "ready",
                "revision_id": "rev-a",
                "mime_type": "image/jpeg",
                "width": 1080,
                "height": 1920,
            },
            {"media_type": "image", "profile_id": "dh-a"},
        ),
    )
    payload = _v2()
    payload.update(
        {
            "project_id": project.project_id,
            "content_source": {
                "mode": "title_plus_copywriting",
                "title_artifact_version_id": title_version.artifact_version_id,
                "source_artifact_version_id": copy_version.artifact_version_id,
                "selected_variant_index": 0,
            },
        }
    )
    accepted = adapter.create_or_resume(project.project_id, payload, idempotency_key="title-plus-1")
    assert accepted.session.state["source_text"]
    wrong_type = {
        **payload,
        "content_source": {
            **payload["content_source"],
            "title_artifact_version_id": copy_version.artifact_version_id,
        },
    }
    with pytest.raises(IpBroadcastInputError, match="SOURCE_ARTIFACT_TYPE_MISMATCH"):
        adapter.create_or_resume(project.project_id, wrong_type, idempotency_key="title-plus-2")
    wrong_project = {
        **payload,
        "content_source": {
            **payload["content_source"],
            "title_artifact_version_id": other_title_version.artifact_version_id,
        },
    }
    with pytest.raises(IpBroadcastInputError, match="SOURCE_VERSION_PROJECT_MISMATCH"):
        adapter.create_or_resume(project.project_id, wrong_project, idempotency_key="title-plus-3")


@pytest.mark.parametrize(
    "backend_flag,desktop_flag,backend_ready,desktop_ready,enabled",
    [
        (False, False, True, True, False),
        (True, False, True, True, False),
        (True, True, False, True, False),
        (True, True, True, False, False),
        (True, True, True, True, True),
    ],
)
def test_dual_mode_requires_joint_backend_and_desktop_readiness(
    backend_flag, desktop_flag, backend_ready, desktop_ready, enabled
):
    gate = evaluate_digital_human_feature_gate(
        backend_flag=backend_flag,
        desktop_flag=desktop_flag,
        backend_ready=backend_ready,
        desktop_ready=desktop_ready,
    )
    assert gate.v2_enabled is enabled
    assert gate.v2_entry_visible is enabled
    if not backend_flag or not backend_ready:
        assert gate.legacy_route_available is True


def test_existing_v1_registry_seed_upgrades_to_v2_mapping_without_drift_failure(tmp_path):
    db_path = tmp_path / "app-center.sqlite"
    AppCenterRepository(db_path)
    legacy = next(
        item for item in BUILTIN_MANIFESTS if item["app_id"] == "builtin.digital-human-video"
    )
    legacy = {
        key: value
        for key, value in legacy.items()
        if key not in {"supported_versions", "input_schema_by_version"}
    }
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "UPDATE app_registry SET manifest_json = ? WHERE app_id = ? AND version = ?",
            (
                json.dumps(legacy, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
                legacy["app_id"],
                "1.0.0",
            ),
        )
        connection.commit()

    AppCenterRepository(db_path)
    with sqlite3.connect(db_path) as connection:
        versions = {
            row[0]
            for row in connection.execute(
                "SELECT version FROM app_registry WHERE app_id = ? ORDER BY version",
                ("builtin.digital-human-video",),
            )
        }
    assert versions == {"1.0.0", "1.1.0"}


def test_resolver_uses_scene_pinned_revision_instead_of_current(monkeypatch):
    class FakeRepository:
        def get_digital_human_scene(self, scene_id):
            assert scene_id == "scene-pinned"
            return {
                "scene_id": scene_id,
                "source_asset_id": "asset-a",
                "source_revision_id": "rev-old",
            }

        def get_asset_revision(self, asset_id, revision_id):
            assert (asset_id, revision_id) == ("asset-a", "rev-old")
            return {"media_kind": "image", "revision_id": "rev-old", "status": "ready"}

        def get_asset(self, _asset_id):
            raise AssertionError("pinned scene must not read current asset revision")

    monkeypatch.setattr(
        "pixelle_video.services.assets_v2.repository.AssetLibraryRepository", FakeRepository
    )
    asset, scene = digital_human_input_module.resolve_asset_library_scene("scene-pinned")
    assert asset["revision_id"] == "rev-old"
    assert scene["media_type"] == "image"
