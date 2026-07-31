from __future__ import annotations

from pathlib import Path

import pytest

from pixelle_video.app_center.ip_broadcast_adapter import (
    IpBroadcastAppAdapter,
    IpBroadcastBindingStore,
    IpBroadcastInputError,
)
from pixelle_video.app_center.repository import AppCenterRepository
from pixelle_video.services import ip_broadcast_workflow as workflow_module
from pixelle_video.services.assets_v2.repository import AssetLibraryRepository
from pixelle_video.services.ip_broadcast_workflow import IpBroadcastSessionStore


def _seed_voice_repository(tmp_path: Path) -> tuple[AssetLibraryRepository, dict, dict]:
    repository = AssetLibraryRepository(tmp_path / "assets")
    first_path = repository.data_root / "asset_library/media/voice-v1.wav"
    second_path = repository.data_root / "asset_library/media/voice-v2.wav"
    replacement_path = repository.data_root / "asset_library/media/voice-replacement.wav"
    first_path.parent.mkdir(parents=True, exist_ok=True)
    first_path.write_bytes(b"voice revision one")
    second_path.write_bytes(b"voice revision two")
    replacement_path.write_bytes(b"replacement voice asset")
    with repository._lock, repository._connect() as connection:  # noqa: SLF001
        connection.execute(
            "INSERT INTO media_assets(asset_id, media_kind, name, source, status, "
            "current_revision_id, created_at, updated_at) VALUES "
            "('audio-owner', 'audio', '老板原声', 'upload', 'ready', 'voice-rev-1', ?, ?)",
            ("2026-07-30", "2026-07-30"),
        )
        for version, revision_id, relative_path in (
            (1, "voice-rev-1", "asset_library/media/voice-v1.wav"),
            (2, "voice-rev-2", "asset_library/media/voice-v2.wav"),
        ):
            connection.execute(
                "INSERT INTO asset_revisions(revision_id, asset_id, version, relative_path, "
                "mime_type, bytes, sha256, duration_ms, created_at) "
                "VALUES (?, 'audio-owner', ?, ?, 'audio/wav', 18, ?, 3000, ?)",
                (revision_id, version, relative_path, str(version) * 64, "2026-07-30"),
            )
        connection.execute(
            "INSERT INTO media_assets(asset_id, media_kind, name, source, status, "
            "current_revision_id, created_at, updated_at) VALUES "
            "('audio-owner-new', 'audio', '老板新参考音频', 'upload', 'ready', "
            "'voice-rev-new', ?, ?)",
            ("2026-07-30", "2026-07-30"),
        )
        connection.execute(
            "INSERT INTO asset_revisions(revision_id, asset_id, version, relative_path, "
            "mime_type, bytes, sha256, duration_ms, created_at) "
            "VALUES ('voice-rev-new', 'audio-owner-new', 1, "
            "'asset_library/media/voice-replacement.wav', 'audio/wav', 23, ?, 3000, ?)",
            ("3" * 64, "2026-07-30"),
        )
    voice = repository.create_voice_profile(
        {
            "voice_id": "voice-owner",
            "audio_asset_id": "audio-owner",
            "audio_revision_id": "voice-rev-1",
            "name": "老板自然声",
            "language": "zh-CN",
            "style": "自然",
            "authorization_status": "confirmed",
        }
    )
    human = repository.create_digital_human_profile(
        {
            "profile_id": "human-owner",
            "name": "老板数字人",
            "default_voice_id": voice["resource_id"],
        }
    )
    return repository, voice, human


def _build_adapter(
    tmp_path: Path,
    app_repository: AppCenterRepository,
    *,
    voice_resolver=None,
) -> IpBroadcastAppAdapter:
    return IpBroadcastAppAdapter(
        app_repository,
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
                "revision_id": "portrait-rev-1",
                "mime_type": "image/jpeg",
                "width": 1080,
                "height": 1920,
            },
            {"media_type": "image", "profile_id": "human-owner"},
        ),
        digital_human_voice_resolver=voice_resolver,
    )


def _v2_payload(project_id: str, *, voice_profile_id: str | None = None) -> dict:
    payload = {
        "schema_version": 2,
        "app_version": "1.1.0",
        "project_id": project_id,
        "content_source": {"mode": "custom_script", "script": "今天三十秒讲清楚门店活动。"},
        "digital_human": {
            "mode": "image_talking",
            "portrait_id": "human-owner",
            "scene_id": "scene-owner",
            "asset_revision_id": "portrait-rev-1",
            "workflow_profile": "stable",
        },
        "delivery": {"subtitle_preset": "readable_v2"},
    }
    if voice_profile_id:
        payload["voice_profile_id"] = voice_profile_id
    return payload


def test_profile_default_voice_is_projected_and_run_resolution_pins_revision(tmp_path: Path):
    repository, voice, human = _seed_voice_repository(tmp_path)

    assert human["summary"]["default_voice_id"] == voice["resource_id"]
    assert human["summary"]["default_voice_name"] == "老板自然声"
    resolved = repository.resolve_digital_human_voice_binding(human["resource_id"])
    assert resolved["resolution_source"] == "digital_human_default"
    assert resolved["audio_revision_id"] == "voice-rev-1"

    repository.patch_voice_profile(voice["resource_id"], {"audio_revision_id": "voice-rev-2"})
    pinned = repository.resolve_digital_human_voice_binding(
        human["resource_id"],
        requested_voice_id=voice["resource_id"],
        requested_audio_revision_id=resolved["audio_revision_id"],
    )
    assert pinned["audio_revision_id"] == "voice-rev-1"
    assert pinned["resolution_source"] == "run_override"


def test_profile_voice_can_be_cleared_without_archiving_the_voice(tmp_path: Path):
    repository, voice, human = _seed_voice_repository(tmp_path)

    cleared = repository.patch_digital_human_profile(
        human["resource_id"], {"default_voice_id": None}
    )
    assert cleared and cleared["summary"]["default_voice_id"] == ""
    fallback = repository.resolve_digital_human_voice_binding(human["resource_id"])
    assert fallback["resolution_source"] == "system_default"
    assert fallback["voice_name"] == "系统推荐男声"
    assert repository.get_domain_item("voice", voice["resource_id"])["status"] == "ready"


def test_denied_voice_cannot_be_bound_or_resolved(tmp_path: Path):
    repository, voice, human = _seed_voice_repository(tmp_path)
    repository.patch_voice_profile(
        voice["resource_id"], {"authorization_status": "revoked"}
    )

    with pytest.raises(ValueError, match="VOICE_PROFILE_UNAUTHORIZED"):
        repository.resolve_digital_human_voice_binding(human["resource_id"])


def test_adapter_persists_voice_revision_and_applies_tts_runtime(tmp_path: Path):
    app_repository = AppCenterRepository(tmp_path / "app-center.sqlite")
    project = app_repository.create_project("门店项目", "快速生成口播")
    resolved_voice = {
        "voice_profile_id": "voice-owner",
        "voice_name": "老板自然声",
        "audio_asset_id": "audio-owner",
        "audio_revision_id": "voice-rev-1",
        "authorization_status": "confirmed",
        "resolution_source": "digital_human_default",
        "tts_provider": "index_tts",
    }
    adapter = _build_adapter(
        tmp_path,
        app_repository,
        voice_resolver=lambda _profile_id, **_kwargs: dict(resolved_voice),
    )

    created = adapter.create_or_resume(
        project.project_id,
        _v2_payload(project.project_id),
        idempotency_key="voice-binding-run",
    )
    assert created.run.input_payload["voice"] == resolved_voice
    assert created.session.state["voice_binding"] == resolved_voice
    assert created.session.state["tts_inference_mode"] == "comfyui"
    assert created.session.state["tts_ref_audio_id"] == "voice-owner"
    assert created.session.state["tts_ref_audio_asset_id"] == "audio-owner"
    assert created.session.state["tts_ref_audio_revision_id"] == "voice-rev-1"


def test_profile_default_voice_revalidates_without_reclassifying_or_drifting(
    tmp_path: Path,
    monkeypatch,
):
    asset_repository, voice, human = _seed_voice_repository(tmp_path)
    app_repository = AppCenterRepository(tmp_path / "app-center.sqlite")
    project = app_repository.create_project("门店项目", "快速生成口播")
    adapter = _build_adapter(
        tmp_path,
        app_repository,
        voice_resolver=asset_repository.resolve_digital_human_voice_binding,
    )

    created = adapter.create_or_resume(
        project.project_id,
        _v2_payload(project.project_id),
        idempotency_key="profile-default-revalidate",
    )
    assert created.run.input_payload["voice"]["resolution_source"] == "digital_human_default"
    adapter._revalidate_v2_snapshot(created.run, created.session)  # noqa: SLF001

    asset_repository.patch_voice_profile(
        voice["resource_id"],
        {
            "audio_asset_id": "audio-owner-new",
            "audio_revision_id": "voice-rev-new",
        },
    )
    asset_repository.patch_digital_human_profile(
        human["resource_id"], {"default_voice_id": None}
    )
    adapter._revalidate_v2_snapshot(created.run, created.session)  # noqa: SLF001
    assert created.session.state["quality_fixed_inputs"]["voice"] == {
        **created.run.input_payload["voice"],
    }
    assert created.session.state["voice_binding"]["audio_revision_id"] == "voice-rev-1"
    assert created.session.state["voice_binding"]["audio_asset_id"] == "audio-owner"
    provider_lookup: dict[str, str | None] = {}

    def _resolve(resource_id: str, fallback: str, revision_id: str | None = None) -> str:
        provider_lookup.update(
            resource_id=resource_id,
            fallback=fallback,
            revision_id=revision_id,
        )
        return "/tmp/pinned-owner-voice.wav"

    monkeypatch.setattr(workflow_module, "_resolve_v2_audio_path", _resolve)
    provider_kwargs = {"inference_mode": "comfyui"}
    workflow_module._append_tts_params(  # noqa: SLF001
        provider_kwargs,
        created.session.state,
    )
    assert provider_lookup == {
        "resource_id": "audio-owner",
        "fallback": "",
        "revision_id": "voice-rev-1",
    }
    assert provider_kwargs["ref_audio"] == "/tmp/pinned-owner-voice.wav"


def test_run_override_voice_revalidates_with_its_original_resolution_source(tmp_path: Path):
    asset_repository, voice, _human = _seed_voice_repository(tmp_path)
    app_repository = AppCenterRepository(tmp_path / "app-center.sqlite")
    project = app_repository.create_project("门店项目", "快速生成口播")
    adapter = _build_adapter(
        tmp_path,
        app_repository,
        voice_resolver=asset_repository.resolve_digital_human_voice_binding,
    )

    created = adapter.create_or_resume(
        project.project_id,
        _v2_payload(project.project_id, voice_profile_id=voice["resource_id"]),
        idempotency_key="run-override-revalidate",
    )
    assert created.run.input_payload["voice"]["resolution_source"] == "run_override"
    adapter._revalidate_v2_snapshot(created.run, created.session)  # noqa: SLF001
    assert (
        created.session.state["quality_fixed_inputs"]["voice"]["resolution_source"]
        == "run_override"
    )


def test_system_voice_revalidates_after_profile_gets_a_new_default(tmp_path: Path):
    asset_repository, voice, human = _seed_voice_repository(tmp_path)
    asset_repository.patch_digital_human_profile(
        human["resource_id"], {"default_voice_id": None}
    )
    app_repository = AppCenterRepository(tmp_path / "app-center.sqlite")
    project = app_repository.create_project("门店项目", "快速生成口播")
    adapter = _build_adapter(
        tmp_path,
        app_repository,
        voice_resolver=asset_repository.resolve_digital_human_voice_binding,
    )

    created = adapter.create_or_resume(
        project.project_id,
        _v2_payload(project.project_id),
        idempotency_key="system-default-revalidate",
    )
    assert created.run.input_payload["voice"]["resolution_source"] == "system_default"
    asset_repository.patch_digital_human_profile(
        human["resource_id"], {"default_voice_id": voice["resource_id"]}
    )
    adapter._revalidate_v2_snapshot(created.run, created.session)  # noqa: SLF001
    assert (
        created.session.state["quality_fixed_inputs"]["voice"]["resolution_source"]
        == "system_default"
    )


def test_public_input_cannot_choose_a_pinned_voice_revision(tmp_path: Path):
    app_repository = AppCenterRepository(tmp_path / "app-center.sqlite")
    project = app_repository.create_project("门店项目", "快速生成口播")
    adapter = _build_adapter(tmp_path, app_repository)
    payload = _v2_payload(project.project_id)
    payload["voice"] = {
        "voice_profile_id": "voice-owner",
        "audio_revision_id": "voice-rev-1",
        "resolution_source": "run_override",
    }

    with pytest.raises(IpBroadcastInputError, match="DIGITAL_HUMAN_VOICE_INVALID"):
        adapter.validate_input(project.project_id, payload)


def test_index_tts_resolves_the_pinned_voice_revision(monkeypatch):
    observed: dict[str, str | None] = {}

    def _resolve(resource_id: str, fallback: str, revision_id: str | None = None) -> str:
        observed.update(
            resource_id=resource_id,
            fallback=fallback,
            revision_id=revision_id,
        )
        return "/tmp/pinned-voice.wav"

    monkeypatch.setattr(workflow_module, "_resolve_v2_audio_path", _resolve)
    kwargs = {"inference_mode": "comfyui"}
    workflow_module._append_tts_params(  # noqa: SLF001
        kwargs,
        {
            "tts_workflow": "runninghub/tts_index_custom.json",
            "tts_ref_audio_id": "voice-owner",
            "tts_ref_audio_asset_id": "audio-owner",
            "tts_ref_audio_revision_id": "voice-rev-1",
        },
    )

    assert observed == {
        "resource_id": "audio-owner",
        "fallback": "",
        "revision_id": "voice-rev-1",
    }
    assert kwargs["ref_audio"] == "/tmp/pinned-voice.wav"
