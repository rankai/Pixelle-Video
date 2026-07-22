import asyncio

import pytest

from api.tasks.manager import TaskManager
from pixelle_video.services.publish.account_models import PublishPlatform
from pixelle_video.services.publish.account_repository import PublishAccountRepository
from pixelle_video.services.publish.core_models import (
    ArtifactRef,
    MediaManifest,
    PublishPackageV2,
    PublishRunState,
    PublishSource,
)
from pixelle_video.services.publish.core_repository import PublishCoreRepository, PublishRunConflict
from pixelle_video.services.publish.run_service import PublishRunService


def test_retry_step_appends_new_attempt_without_overwriting_prior_fact(tmp_path):
    db = tmp_path / "publishing.sqlite"
    accounts = PublishAccountRepository(db)
    account = accounts.create_account(PublishPlatform.DOUYIN, "门店", "profile_douyin")
    core = PublishCoreRepository(db)
    package = core.create_package(
        PublishPackageV2(
            package_id="pkg_retry_test",
            project_id="project_1",
            source=PublishSource(kind="artifact_versions", artifact_ids=["a1"], artifact_version_ids=["v1"], source_revision="sha256:rev"),
            artifact_refs=[ArtifactRef(artifact_id="a1", artifact_version_id="v1", artifact_type="video", content_fingerprint="sha256:content")],
            video_manifest=MediaManifest(sha256="sha256:" + "a" * 64, size_bytes=12, mime_type="video/mp4", path_token="asset_video"),
            package_fingerprint="sha256:retry",
        )
    )
    service = PublishRunService(core, accounts, manager=TaskManager())
    run, _ = service.create_run(package.package_id, account.account_id, PublishPlatform.DOUYIN, "retry-key-001")
    first = core.create_step_attempt(run.run_id, "preflight", 1)
    run = core.transition_run(run.run_id, PublishRunState.RUNNING, expected_version=1, current_step="preflight")
    run = core.transition_run(run.run_id, PublishRunState.NEEDS_ATTENTION, expected_version=2, current_step="preflight", error_code="MEDIA_INVALID")
    retried = service.retry_step(run.run_id, "preflight", actor_ref="user:test")
    attempts = core.list_step_attempts(run.run_id, step="preflight")
    assert retried.state is PublishRunState.QUEUED
    assert [item.attempt for item in attempts] == [1, 2]
    assert attempts[0].step_attempt_id == first.step_attempt_id
    asyncio.run(service.start(run.run_id))
    assert core.list_step_attempts(run.run_id, step="preflight")[1].state is PublishRunState.SUCCEEDED
    with pytest.raises(PublishRunConflict, match="RUN_STATE_INVALID"):
        service.retry_step(run.run_id, "preflight")
