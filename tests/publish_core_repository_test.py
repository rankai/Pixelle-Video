import sqlite3

import pytest

from pixelle_video.services.publish.account_models import PublishPlatform
from pixelle_video.services.publish.account_repository import PublishAccountRepository
from pixelle_video.services.publish.core_models import (
    ArtifactRef,
    MediaManifest,
    PublishPackageV2,
    PublishRunState,
    PublishSource,
)
from pixelle_video.services.publish.core_repository import (
    PublishCoreRepository,
    PublishPackageConflict,
    PublishRunAlreadyActive,
    PublishRunConcurrencyConflict,
    PublishRunConflict,
    sanitize_event_payload,
)


def _package(package_id: str, *, revision: str = "sha256:revision") -> PublishPackageV2:
    return PublishPackageV2(
        package_id=package_id,
        project_id="project_1",
        source=PublishSource(kind="artifact_versions", artifact_ids=["a1"], artifact_version_ids=["v1"], source_revision=revision),
        artifact_refs=[ArtifactRef(artifact_id="a1", artifact_version_id="v1", artifact_type="video", content_fingerprint="sha256:content")],
        video_manifest=MediaManifest(sha256="sha256:" + "a" * 64, size_bytes=12, mime_type="video/mp4", path_token="asset_video"),
        package_fingerprint="sha256:" + package_id,
    )


def test_repository_run_cas_idempotency_active_serialization_and_append_only_facts(tmp_path):
    db = tmp_path / "publishing.sqlite"
    accounts = PublishAccountRepository(db)
    account = accounts.create_account(PublishPlatform.DOUYIN, "门店", "profile_douyin")
    repository = PublishCoreRepository(db)
    package = repository.create_package(_package("pkg_repo_1"))

    run, replay = repository.create_run(package.package_id, account.account_id, PublishPlatform.DOUYIN, "idempotency-key-1")
    assert replay is False and run.state is PublishRunState.QUEUED
    replay_run, replay = repository.create_run(package.package_id, account.account_id, PublishPlatform.DOUYIN, "idempotency-key-1")
    assert replay is True and replay_run.run_id == run.run_id
    replay_same_package, replay = repository.create_run(package.package_id, account.account_id, PublishPlatform.DOUYIN, "idempotency-key-2")
    assert replay is True and replay_same_package.run_id == run.run_id

    running = repository.transition_run(run.run_id, PublishRunState.RUNNING, expected_version=1, current_step="preflight")
    event1 = repository.append_event(run.run_id, "run_started", state=running.state, state_version=running.state_version, payload={"step": "preflight"})
    event2 = repository.append_event(run.run_id, "run_progress", state=running.state, state_version=running.state_version, payload={"step": "preflight", "duration_ms": 2})
    assert (event1.event_seq, event2.event_seq) == (1, 2)
    assert [event.event_seq for event in repository.list_events(run.run_id, after=1)] == [2]
    repository.create_step_attempt(run.run_id, "preflight", 1)
    with pytest.raises(sqlite3.IntegrityError):
        repository.create_step_attempt(run.run_id, "preflight", 1)
    repository.update_step_attempt(run.run_id, "preflight", 1, PublishRunState.SUCCEEDED)
    with pytest.raises(PublishRunConflict, match="STEP_ATTEMPT_TERMINAL"):
        repository.update_step_attempt(run.run_id, "preflight", 1, PublishRunState.FAILED)
    with pytest.raises(PublishRunConcurrencyConflict, match="RUN_VERSION_CONFLICT"):
        repository.transition_run(run.run_id, PublishRunState.WAITING_FOR_HUMAN, expected_version=1)

    waiting = repository.transition_run(run.run_id, PublishRunState.WAITING_FOR_HUMAN, expected_version=2, current_step="await_human")
    with pytest.raises(PublishRunConflict, match="SUCCESS_REQUIRES_HUMAN_CONFIRMATION"):
        repository.transition_run(run.run_id, PublishRunState.SUCCEEDED, expected_version=waiting.state_version)
    succeeded = repository.transition_run(run.run_id, PublishRunState.SUCCEEDED, expected_version=waiting.state_version, human_confirmed=True, actor_ref="user:test")
    assert succeeded.human_confirmed is True and succeeded.actor_ref == "user:test"
    with pytest.raises(PublishRunConflict, match="EVENT_STATE_VERSION_MISMATCH"):
        repository.append_event(run.run_id, "stale", state=PublishRunState.SUCCEEDED, state_version=waiting.state_version, payload={"step": "stale"})


def test_repository_same_profile_different_package_is_rejected_and_stale_package_cannot_run(tmp_path):
    db = tmp_path / "publishing.sqlite"
    account = PublishAccountRepository(db).create_account(PublishPlatform.DOUYIN, "门店", "profile_douyin")
    repository = PublishCoreRepository(db)
    first = repository.create_package(_package("pkg_repo_a"))
    second = repository.create_package(_package("pkg_repo_b", revision="sha256:revision-b"))
    repository.create_run(first.package_id, account.account_id, PublishPlatform.DOUYIN, "first-key-1")
    with pytest.raises(PublishRunAlreadyActive, match="RUN_ALREADY_ACTIVE"):
        repository.create_run(second.package_id, account.account_id, PublishPlatform.DOUYIN, "second-key-1")
    repository.invalidate_package(second.package_id, "source changed")
    with pytest.raises(PublishPackageConflict, match="PUBLISH_PACKAGE_STALE"):
        repository.create_run(second.package_id, account.account_id, PublishPlatform.DOUYIN, "second-key-2")


def test_event_sanitizer_rejects_unknown_secrets_and_business_copy():
    assert sanitize_event_payload({"step": "preflight", "duration_ms": 1})["step"] == "preflight"
    for payload in ({"cookie": "secret"}, {"unknown": "x"}, {"step": "/Users/nickfury/video.mp4"}, {"title": "业务标题"}):
        with pytest.raises(ValueError):
            sanitize_event_payload(payload)


def test_invalidated_package_round_trips_and_cannot_create_run(tmp_path):
    db = tmp_path / "publishing.sqlite"
    accounts = PublishAccountRepository(db)
    account = accounts.create_account(PublishPlatform.DOUYIN, "门店", "profile_douyin")
    repository = PublishCoreRepository(db)
    package = repository.create_package(_package("pkg_invalidated", revision="sha256:invalid"))
    repository.invalidate_package(package.package_id, "superseded")
    assert repository.get_package(package.package_id).invalidated_at
    with pytest.raises(Exception, match="PUBLISH_PACKAGE_STALE"):
        repository.create_run(package.package_id, account.account_id, PublishPlatform.DOUYIN, "invalidated-key")


def test_attach_task_is_idempotent_and_never_overwrites(tmp_path):
    db = tmp_path / "publishing.sqlite"
    accounts = PublishAccountRepository(db)
    account = accounts.create_account(PublishPlatform.DOUYIN, "门店", "profile_douyin")
    repository = PublishCoreRepository(db)
    package = repository.create_package(_package("pkg_attach"))
    run, _ = repository.create_run(package.package_id, account.account_id, PublishPlatform.DOUYIN, "attach-key-001")
    assert repository.attach_task(run.run_id, "task-1").task_id == "task-1"
    assert repository.attach_task(run.run_id, "task-1").task_id == "task-1"
    with pytest.raises(PublishRunConflict, match="TASK_ALREADY_ATTACHED"):
        repository.attach_task(run.run_id, "task-2")
