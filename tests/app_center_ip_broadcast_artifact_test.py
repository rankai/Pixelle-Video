from __future__ import annotations

import os
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path

import pytest

from pixelle_video.app_center.ip_broadcast_adapter import (
    IpBroadcastAppAdapter,
    IpBroadcastBindingStore,
    IpBroadcastSessionError,
)
from pixelle_video.app_center.repository import AppCenterRepository
from pixelle_video.services.ip_broadcast_workflow import IpBroadcastSessionStore


def _media_files(root: Path) -> tuple[Path, Path]:
    output = root / "output"
    output.mkdir(parents=True, exist_ok=True)
    video = output / "legacy-final.mp4"
    # Minimal ISO-BMFF signature for deterministic MIME/signature validation.
    video.write_bytes(b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00isommp42")
    cover = output / "legacy-cover.png"
    cover.write_bytes(b"\x89PNG\r\n\x1a\n" + b"fixture-cover")
    return video, cover


@pytest.fixture
def harness(tmp_path: Path):
    repository = AppCenterRepository(tmp_path / "app-center.sqlite")
    project = repository.create_project("门店项目", "到店咨询")
    sessions = IpBroadcastSessionStore(tmp_path / "legacy-sessions")
    bindings = IpBroadcastBindingStore(tmp_path / "bindings.json")
    trusted = tmp_path / "trusted"
    trusted.mkdir()
    adapter = IpBroadcastAppAdapter(
        repository,
        session_store=sessions,
        binding_store=bindings,
        enforce_feature_flag=False,
        trusted_roots=[trusted],
    )
    return repository, project, sessions, adapter, trusted


def _needs_review(repository: AppCenterRepository, app_run_id: str):
    repository.transition_app_run(app_run_id, "queued")
    repository.transition_app_run(app_run_id, "running")
    return repository.transition_app_run(app_run_id, "needs_review")


def _bind_run(harness):
    repository, project, sessions, adapter, trusted = harness
    created = adapter.create_or_resume(
        project.project_id,
        {"source_mode": "blank_project", "goal": "到店咨询", "source_artifact_version_ids": []},
        idempotency_key="ip-artifact-1",
    )
    video, cover = _media_files(trusted)
    session = sessions.get_session(created.binding.session_id)
    assert session is not None
    session.state["final_video_path"] = str(video)
    session.state["cover_path"] = str(cover)
    session.state["publish_package"] = {
        "title": "到店前先看这件事",
        "description": "把到店服务和优惠讲清楚，欢迎来店咨询。",
        "hashtags": ["门店经营", "到店咨询"],
        "cover_title": "到店前先看这件事",
    }
    sessions.save_session(session)
    _needs_review(repository, created.run.app_run_id)
    return created


def test_registers_existing_outputs_as_hashed_artifact_versions_and_is_idempotent(harness):
    repository, project, sessions, adapter, trusted = harness
    created = _bind_run(harness)

    imported = adapter.register_legacy_outputs(created.run.app_run_id)
    assert imported.run.state == "needs_review"
    assert len(imported.run.output_artifact_ids) == 3
    assert {repository.get_artifact(item).artifact_type for item in imported.run.output_artifact_ids} == {
        "video",
        "cover",
        "publish_copy",
    }

    versions = [
        repository.get_artifact_version(repository.get_artifact(item).current_version_id)
        for item in imported.run.output_artifact_ids
    ]
    assert all(version.source == "imported" for version in versions)
    video_version = next(version for version in versions if repository.get_artifact(version.artifact_id).artifact_type == "video")
    cover_version = next(version for version in versions if repository.get_artifact(version.artifact_id).artifact_type == "cover")
    assert video_version.file_refs[0]["relative_path"] == "output/legacy-final.mp4"
    assert cover_version.file_refs[0]["relative_path"] == "output/legacy-cover.png"
    assert video_version.file_refs[0]["sha256"].startswith("sha256:")
    assert cover_version.file_refs[0]["size_bytes"] == (trusted / "output" / "legacy-cover.png").stat().st_size
    assert all("/" not in str(ref.get("absolute_path", "")) for version in versions for ref in version.file_refs)

    replay = adapter.register_legacy_outputs(created.run.app_run_id)
    assert replay.run.output_artifact_ids == imported.run.output_artifact_ids
    assert [repository.get_artifact_version(repository.get_artifact(item).current_version_id).version_number for item in imported.run.output_artifact_ids] == [1, 1, 1]
    assert sessions.get_session(created.binding.session_id) is not None


@pytest.mark.parametrize(
    ("mutator", "error"),
    [
        (lambda video, cover, trusted: (trusted / "outside.mp4").write_bytes(video.read_bytes()), "ARTIFACT_FILE_OUTSIDE_ROOT"),
        (lambda video, cover, trusted: cover.write_text("not png", encoding="utf-8"), "ARTIFACT_FILE_SIGNATURE_INVALID"),
    ],
)
def test_legacy_media_validation_is_fail_closed(harness, mutator, error):
    repository, project, sessions, adapter, trusted = harness
    created = _bind_run(harness)
    video, cover = _media_files(trusted)
    if error == "ARTIFACT_FILE_OUTSIDE_ROOT":
        outside = trusted.parent / "outside-real.mp4"
        outside.write_bytes(video.read_bytes())
        session = sessions.get_session(created.binding.session_id)
        assert session is not None
        session.state["final_video_path"] = str(outside)
        sessions.save_session(session)
    else:
        mutator(video, cover, trusted)
        session = sessions.get_session(created.binding.session_id)
        assert session is not None
        session.state["cover_path"] = str(cover)
        sessions.save_session(session)
    with pytest.raises(IpBroadcastSessionError, match=error):
        adapter.register_legacy_outputs(created.run.app_run_id)
    assert repository.list_artifacts(project.project_id) == []


def test_symlink_escape_and_incomplete_publish_copy_are_rejected(harness):
    repository, project, sessions, adapter, trusted = harness
    created = _bind_run(harness)
    video, cover = _media_files(trusted)
    outside = trusted.parent / "outside-cover.png"
    outside.write_bytes(cover.read_bytes())
    link = trusted / "output" / "escape.png"
    link.parent.mkdir(exist_ok=True)
    try:
        link.symlink_to(outside)
    except OSError as exc:
        pytest.skip(f"symlink unavailable: {exc}")
    session = sessions.get_session(created.binding.session_id)
    assert session is not None
    session.state["cover_path"] = str(link)
    sessions.save_session(session)
    with pytest.raises(IpBroadcastSessionError, match="ARTIFACT_FILE_OUTSIDE_ROOT"):
        adapter.register_legacy_outputs(created.run.app_run_id)
    assert repository.list_artifacts(project.project_id) == []

    link.unlink()
    session.state["cover_path"] = str(cover)
    session.state["publish_package"] = {"title": "只有标题", "hashtags": []}
    sessions.save_session(session)
    with pytest.raises(IpBroadcastSessionError, match="ARTIFACT_PUBLISH_COPY_INVALID"):
        adapter.register_legacy_outputs(created.run.app_run_id)
    assert repository.list_artifacts(project.project_id) == []


def test_only_needs_review_run_can_register_outputs(harness):
    repository, project, _, adapter, _ = harness
    created = adapter.create_or_resume(
        project.project_id,
        {"source_mode": "blank_project", "goal": "尚未完成", "source_artifact_version_ids": []},
        idempotency_key="ip-artifact-state-1",
    )
    with pytest.raises(IpBroadcastSessionError, match="ARTIFACT_OUTPUT_STATE_INVALID"):
        adapter.register_legacy_outputs(created.run.app_run_id)


def test_same_run_concurrent_registration_returns_one_immutable_batch(harness):
    repository, project, _, adapter, _ = harness
    created = _bind_run(harness)
    barrier = threading.Barrier(2)

    def register_once():
        barrier.wait(timeout=5)
        return adapter.register_legacy_outputs(created.run.app_run_id)

    with ThreadPoolExecutor(max_workers=2) as pool:
        first, second = list(pool.map(lambda _: register_once(), range(2)))
    assert first.run.output_artifact_ids == second.run.output_artifact_ids
    owned = [item for item in repository.list_artifacts(project.project_id) if item.source_app_run_id == created.run.app_run_id]
    assert len(owned) == 3
    assert {item.artifact_type for item in owned} == {"video", "cover", "publish_copy"}


def test_post_read_path_change_is_rejected_as_toctou(harness, monkeypatch):
    _, _, _, adapter, trusted = harness
    _bind_run(harness)
    video, _ = _media_files(trusted)
    original_stat = os.stat
    mutated = False

    def mutate_before_final_stat(path, *, follow_symlinks=True):
        nonlocal mutated
        if Path(path) == video and not mutated:
            mutated = True
            video.write_bytes(b"\x00\x00\x00\x18ftypZZZZ\x00\x00\x00\x00isomZZZZ")
        return original_stat(path, follow_symlinks=follow_symlinks)

    monkeypatch.setattr(os, "stat", mutate_before_final_stat)
    with pytest.raises(IpBroadcastSessionError, match="ARTIFACT_FILE_CHANGED"):
        adapter._read_stable_legacy_file(video, "video")


def test_import_compensation_removes_only_current_invocation_artifacts(harness, monkeypatch):
    repository, project, _, adapter, _ = harness
    created = _bind_run(harness)
    original_append = repository.append_artifact_version
    calls = 0

    def fail_on_second_append(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("injected append failure")
        return original_append(*args, **kwargs)

    monkeypatch.setattr(repository, "append_artifact_version", fail_on_second_append)
    with pytest.raises(RuntimeError, match="injected append failure"):
        adapter.register_legacy_outputs(created.run.app_run_id)
    assert [item for item in repository.list_artifacts(project.project_id) if item.source_app_run_id == created.run.app_run_id] == []
    assert repository.list_attempts(created.run.app_run_id) == []


def test_batch4_accept_requires_reviewable_import_and_is_idempotent(harness):
    repository, project, sessions, adapter, _ = harness
    created = _bind_run(harness)
    imported = adapter.register_legacy_outputs(created.run.app_run_id)
    attempt = repository.list_attempts(created.run.app_run_id)[-1]
    assert attempt.state == "needs_review"
    assert attempt.diagnostic and attempt.diagnostic.get("legacy_output_fingerprint", "").startswith("sha256:")
    publish_version = next(
        repository.get_artifact_version(repository.get_artifact(item).current_version_id)
        for item in imported.run.output_artifact_ids
        if repository.get_artifact(item).artifact_type == "publish_copy"
    )
    assert publish_version.content and publish_version.content["legacy_output_fingerprint"].startswith("sha256:")

    accepted = adapter.accept_legacy_outputs(created.run.app_run_id)
    assert accepted.run.state == "completed"
    assert accepted.projection["completion_allowed"] is True
    assert accepted.session.step_status[6] == "done"
    assert repository.list_attempts(created.run.app_run_id)[-1].state == "completed"
    session = sessions.get_session(created.binding.session_id)
    assert session is not None
    session.step_status[6] = "ready"
    sessions.save_session(session)

    restarted = IpBroadcastAppAdapter(
        repository,
        session_store=IpBroadcastSessionStore(sessions._store_path),
        binding_store=IpBroadcastBindingStore(sessions._store_path.parent / "bindings.json"),
        enforce_feature_flag=False,
        trusted_roots=[harness[-1]],
    )
    replay = restarted.accept_legacy_outputs(created.run.app_run_id)
    assert replay.run.app_run_id == accepted.run.app_run_id
    assert replay.run.state == "completed"
    assert replay.session.step_status[6] == "done"


def test_batch4_accept_fails_closed_without_review_attempt_or_on_fingerprint_drift(harness, monkeypatch):
    repository, project, sessions, adapter, trusted = harness
    created = _bind_run(harness)
    imported = adapter.register_legacy_outputs(created.run.app_run_id)
    monkeypatch.setattr(repository, "list_attempts", lambda _app_run_id: [])
    with pytest.raises(IpBroadcastSessionError, match="ARTIFACT_REVIEW_ATTEMPT_REQUIRED"):
        adapter.accept_legacy_outputs(created.run.app_run_id)

    # A current version carrying the old fingerprint but changed canonical
    # copy content is rejected; old history remains available.
    monkeypatch.undo()
    publish_artifact = next(
        repository.get_artifact(item)
        for item in imported.run.output_artifact_ids
        if repository.get_artifact(item).artifact_type == "publish_copy"
    )
    current = repository.get_artifact_version(publish_artifact.current_version_id)
    assert current.content is not None
    drifted = {**current.content, "description": "发生漂移", "legacy_output_fingerprint": current.content["legacy_output_fingerprint"]}
    repository.append_artifact_version(publish_artifact.artifact_id, content=drifted, source="imported")
    with pytest.raises(IpBroadcastSessionError, match="ARTIFACT_FINGERPRINT_MISMATCH"):
        adapter.accept_legacy_outputs(created.run.app_run_id)
    assert (trusted / "output" / "legacy-final.mp4").exists()


def test_batch4_accept_rejects_imported_file_ref_without_contract_file_key(harness):
    repository, _, _, adapter, _ = harness
    created = _bind_run(harness)
    imported = adapter.register_legacy_outputs(created.run.app_run_id)
    video_artifact = next(
        repository.get_artifact(item)
        for item in imported.run.output_artifact_ids
        if repository.get_artifact(item).artifact_type == "video"
    )
    current = repository.get_artifact_version(video_artifact.current_version_id)
    tampered_refs = [{key: value for key, value in current.file_refs[0].items() if key != "file_key"}]
    repository.append_artifact_version(video_artifact.artifact_id, file_refs=tampered_refs, source="imported")
    with pytest.raises(IpBroadcastSessionError, match="ARTIFACT_FINGERPRINT_MISMATCH"):
        adapter.accept_legacy_outputs(created.run.app_run_id)


def test_batch4_accept_requires_binding_and_exact_imported_output_ids(harness):
    repository, project, _, adapter, _ = harness
    created = _bind_run(harness)
    imported = adapter.register_legacy_outputs(created.run.app_run_id)

    brief = repository.create_artifact(project.project_id, "brief", "错误替换")
    repository.append_artifact_version(brief.artifact_id, content={"summary": "不得作为口播产物"})
    repository.set_output_artifacts(created.run.app_run_id, [brief.artifact_id])
    with pytest.raises(IpBroadcastSessionError, match="ARTIFACT_OUTPUT_BINDING_MISMATCH"):
        adapter.accept_legacy_outputs(created.run.app_run_id)

    repository.set_output_artifacts(created.run.app_run_id, list(imported.run.output_artifact_ids))
    binding = adapter.binding_store.get_by_app_run(created.run.app_run_id)
    assert binding is not None
    other_project = repository.create_project("另一个项目", "隔离")
    adapter.binding_store._bindings[binding.session_id] = replace(binding, project_id=other_project.project_id)
    with pytest.raises(IpBroadcastSessionError, match="SESSION_PROJECT_MISMATCH"):
        adapter.accept_legacy_outputs(created.run.app_run_id)


def test_batch4_attempt_conflict_is_preflighted_before_artifact_writes(harness):
    repository, project, _, adapter, _ = harness
    created = _bind_run(harness)
    attempt = repository.create_attempt(created.run.app_run_id)
    repository.update_attempt(
        attempt.attempt_id,
        state="needs_review",
        diagnostic_json={"legacy_output_fingerprint": "sha256:wrong"},
    )
    with pytest.raises(IpBroadcastSessionError, match="ARTIFACT_REVIEW_ATTEMPT_CONFLICT"):
        adapter.register_legacy_outputs(created.run.app_run_id)
    assert repository.list_artifacts(project.project_id) == []
    assert repository.get_app_run(created.run.app_run_id).output_artifact_ids == []


def test_batch4_archived_imported_output_is_not_reviewable(harness):
    repository, project, _, adapter, _ = harness
    created = _bind_run(harness)
    imported = adapter.register_legacy_outputs(created.run.app_run_id)
    cover_artifact = next(
        item for item in imported.run.output_artifact_ids if repository.get_artifact(item).artifact_type == "cover"
    )
    repository.archive_artifact(cover_artifact)
    with pytest.raises(IpBroadcastSessionError, match="ARTIFACT_REGISTRATION_PARTIAL"):
        adapter.accept_legacy_outputs(created.run.app_run_id)
