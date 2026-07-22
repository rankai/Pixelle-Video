import asyncio

import pytest

from api.tasks.manager import TaskManager
from pixelle_video.services.publish.account_models import (
    AccountLoginState,
    AccountVerificationState,
    PublishPlatform,
)
from pixelle_video.services.publish.account_repository import PublishAccountRepository
from pixelle_video.services.publish.core_models import (
    ArtifactRef,
    MediaManifest,
    PublishPackageV2,
    PublishRunState,
    PublishSource,
)
from pixelle_video.services.publish.core_repository import PublishCoreRepository, PublishRunConflict
from pixelle_video.services.publish.execution_protocol import (
    DraftIdentity,
    PublishBlockerCode,
    PublishExecutionCheckpoint,
    PublishStage,
    UploadMode,
)
from pixelle_video.services.publish.profile_manager import BrowserProfileManager
from pixelle_video.services.publish.run_service import PublishRunService, PublishRunServiceError


def _package() -> PublishPackageV2:
    return PublishPackageV2(
        package_id="pkg_service_test",
        project_id="project_1",
        source=PublishSource(kind="artifact_versions", artifact_ids=["a1"], artifact_version_ids=["v1"], source_revision="sha256:rev"),
        artifact_refs=[ArtifactRef(artifact_id="a1", artifact_version_id="v1", artifact_type="video", content_fingerprint="sha256:content")],
        video_manifest=MediaManifest(sha256="sha256:" + "a" * 64, size_bytes=12, mime_type="video/mp4", path_token="asset_video"),
        package_fingerprint="sha256:" + "c" * 64,
    )


def test_run_service_stops_at_login_or_human_boundary_and_projects_generic_task(tmp_path):
    db = tmp_path / "publishing.sqlite"
    accounts = PublishAccountRepository(db)
    account = accounts.create_account(PublishPlatform.DOUYIN, "门店", "profile_douyin")
    core = PublishCoreRepository(db)
    package = core.create_package(_package())
    manager = TaskManager()
    service = PublishRunService(core, accounts, manager=manager, profile_manager=BrowserProfileManager(tmp_path / "profiles", repository=accounts))
    run, replay = service.create_run(package.package_id, account.account_id, PublishPlatform.DOUYIN, "run-service-key-1")
    assert replay is False and run.task_id
    assert manager.get_task(run.task_id).request_params is None
    waiting_login = asyncio.run(service.start(run.run_id))
    assert waiting_login.state is PublishRunState.WAITING_FOR_LOGIN
    assert manager.get_task(run.task_id).status.value == "waiting_for_login"

    accounts.record_probe(account.account_id, login_state=AccountLoginState.CONNECTING, verification_state=AccountVerificationState.UNVERIFIED, profile_exists=True)
    accounts.record_probe(account.account_id, login_state=AccountLoginState.AUTHENTICATED, verification_state=AccountVerificationState.VERIFIED, profile_exists=True, login_subject_hint="user")
    resumed = service.resume(run.run_id)
    assert resumed.state is PublishRunState.RUNNING
    waiting_human = asyncio.run(service.start(run.run_id))
    assert waiting_human.state is PublishRunState.WAITING_FOR_HUMAN
    assert "upload" not in (waiting_human.current_step or "").lower()
    assert accounts.list_profile_locks(account.account_id)
    recovered_service = PublishRunService(core, accounts, manager=TaskManager(), profile_manager=BrowserProfileManager(tmp_path / "profiles", repository=accounts))
    recovered = recovered_service.recover_after_restart()
    assert recovered == []
    assert core.get_run(run.run_id).state is PublishRunState.WAITING_FOR_HUMAN
    assert accounts.list_profile_locks(account.account_id)


def test_restart_recovery_downgrades_only_inflight_runs(tmp_path):
    db = tmp_path / "restart-recovery.sqlite"
    accounts = PublishAccountRepository(db)
    account = accounts.create_account(PublishPlatform.DOUYIN, "门店", "profile_douyin")
    core = PublishCoreRepository(db)
    package = core.create_package(_package())
    run, _ = core.create_run(package.package_id, account.account_id, PublishPlatform.DOUYIN, "restart-recovery-1")
    running = core.transition_run(
        run.run_id,
        PublishRunState.RUNNING,
        expected_version=run.state_version,
        current_step="preflight",
        event_type="run_started",
    )

    recovered = core.recover_inflight_runs()

    assert len(recovered) == 1
    assert recovered[0].run_id == running.run_id
    assert recovered[0].state is PublishRunState.NEEDS_ATTENTION
    assert recovered[0].error_code == "PROCESS_RESTART"


@pytest.mark.parametrize(
    "blocker",
    [PublishBlockerCode.FOREIGN_DRAFT, PublishBlockerCode.STATE_AMBIGUOUS],
)
def test_identity_blocker_resume_migrates_to_a_new_attempt(tmp_path, blocker):
    db = tmp_path / "identity-resume.sqlite"
    accounts = PublishAccountRepository(db)
    account = accounts.create_account(PublishPlatform.DOUYIN, "门店", "profile_douyin")
    core = PublishCoreRepository(db)
    package = core.create_package(_package())
    service = PublishRunService(core, accounts, manager=TaskManager())
    run, _ = service.create_run(package.package_id, account.account_id, PublishPlatform.DOUYIN, "identity-resume-1")
    blocked = core.transition_run(
        run.run_id,
        PublishRunState.NEEDS_ATTENTION,
        expected_version=run.state_version,
        current_step="inspect",
        error_code=blocker.value,
    )

    migrated = service.resume(run.run_id)

    assert migrated.state is PublishRunState.QUEUED
    assert migrated.attempt == blocked.attempt + 1
    assert migrated.current_step == "resume"
    assert migrated.error_code is None
    resume_attempts = core.list_step_attempts(run.run_id, step="resume")
    assert len(resume_attempts) == 1
    assert resume_attempts[0].attempt == 1


def test_verified_checkpoint_can_reconcile_runner_error_without_browser_retry(tmp_path):
    db = tmp_path / "verified-reconcile.sqlite"
    accounts = PublishAccountRepository(db)
    account = accounts.create_account(PublishPlatform.DOUYIN, "门店", "profile_douyin")
    core = PublishCoreRepository(db)
    package = core.create_package(_package())
    service = PublishRunService(core, accounts, manager=TaskManager())
    run, _ = service.create_run(package.package_id, account.account_id, PublishPlatform.DOUYIN, "verified-reconcile-1")
    run = core.transition_run(
        run.run_id,
        PublishRunState.NEEDS_ATTENTION,
        expected_version=run.state_version,
        current_step="verify",
        error_code="RUNNER_ERROR",
        checkpoint=PublishExecutionCheckpoint(
            package_fingerprint=package.package_fingerprint,
            account_id=account.account_id,
            platform="douyin",
            attempt=run.attempt,
            runtime_kind="playwright",
            draft_identity=DraftIdentity(
                runtime_kind="playwright",
                profile_ref=account.profile_ref,
                task_space_id=101,
                task_space_name="douyin:https://creator.douyin.com/creator-micro/content/editor",
                page_fingerprint="sha256:" + "a" * 64,
                media_identity="sha256:" + "f" * 64,
            ),
            completed_stages=[PublishStage.INSPECT, PublishStage.UPLOAD, PublishStage.WAIT, PublishStage.MUTATE, PublishStage.VERIFY],
            last_stage=PublishStage.VERIFY,
            upload_mode=UploadMode.INJECTED,
            media_sha256=package.video_manifest.sha256,
            final_action_guard_armed=True,
            final_publish_clicked=False,
        ).as_checkpoint(),
    )

    reconciled = service.reconcile_verified_checkpoint(run.run_id)

    assert reconciled.state is PublishRunState.WAITING_FOR_HUMAN
    assert reconciled.current_step == "await_human_publish"
    assert reconciled.error_code is None


def test_run_service_requires_actor_and_only_human_outcome_completes(tmp_path):
    db = tmp_path / "publishing.sqlite"
    accounts = PublishAccountRepository(db)
    account = accounts.create_account(PublishPlatform.DOUYIN, "门店", "profile_douyin")
    accounts.record_probe(account.account_id, login_state=AccountLoginState.CONNECTING, verification_state=AccountVerificationState.UNVERIFIED, profile_exists=True)
    accounts.record_probe(account.account_id, login_state=AccountLoginState.AUTHENTICATED, verification_state=AccountVerificationState.VERIFIED, profile_exists=True)
    core = PublishCoreRepository(db)
    package = core.create_package(_package())
    service = PublishRunService(core, accounts, manager=TaskManager(), profile_manager=BrowserProfileManager(tmp_path / "profiles", repository=accounts))
    run, _ = service.create_run(package.package_id, account.account_id, PublishPlatform.DOUYIN, "run-service-key-2")
    asyncio.run(service.start(run.run_id))
    with pytest.raises(Exception, match="ACTOR_REQUIRED"):
        service.mark_human_outcome(run.run_id, published=True, actor_ref=" ")
    succeeded = service.mark_human_outcome(run.run_id, published=True, actor_ref="user:test")
    assert succeeded.state is PublishRunState.SUCCEEDED
    assert accounts.list_profile_locks(account.account_id) == []
    with pytest.raises(PublishRunConflict, match="RUN_STATE_INVALID"):
        service.mark_human_outcome(run.run_id, published=True, actor_ref="user:test")

    second, _ = service.create_run(package.package_id, account.account_id, PublishPlatform.DOUYIN, "run-service-key-3")
    asyncio.run(service.start(second.run_id))
    abandoned = service.mark_human_outcome(second.run_id, published=False, actor_ref="user:test")
    assert abandoned.state is PublishRunState.CANCELLED


def test_runner_error_keeps_truthful_fact_but_redacts_business_field_from_event(tmp_path):
    db = tmp_path / "publishing.sqlite"
    accounts = PublishAccountRepository(db)
    account = accounts.create_account(PublishPlatform.DOUYIN, "门店", "profile_douyin")
    accounts.record_probe(account.account_id, login_state=AccountLoginState.CONNECTING, verification_state=AccountVerificationState.UNVERIFIED, profile_exists=True)
    accounts.record_probe(account.account_id, login_state=AccountLoginState.AUTHENTICATED, verification_state=AccountVerificationState.VERIFIED, profile_exists=True)
    core = PublishCoreRepository(db)
    package = core.create_package(_package())

    async def executor(_run):
        raise PublishRunServiceError("DOUYIN_DESCRIPTION_READBACK_FAILED")

    service = PublishRunService(
        core,
        accounts,
        manager=TaskManager(),
        profile_manager=BrowserProfileManager(tmp_path / "profiles", repository=accounts),
        executor=executor,
    )
    run, _ = service.create_run(package.package_id, account.account_id, PublishPlatform.DOUYIN, "runner-redaction-1")
    failed = asyncio.run(service.start(run.run_id))
    assert failed.state is PublishRunState.NEEDS_ATTENTION
    assert failed.error_code == "DOUYIN_DESCRIPTION_READBACK_FAILED"
    event = core.list_events(run.run_id)[-1]
    assert event.event_type == "runner_error"
    assert event.payload["error_code"] == "RUNNER_ERROR"


def test_record_execution_checkpoint_binds_stage_and_projects_typed_blocker(tmp_path):
    db = tmp_path / "checkpoint.sqlite"
    accounts = PublishAccountRepository(db)
    account = accounts.create_account(PublishPlatform.DOUYIN, "门店", "profile_douyin")
    core = PublishCoreRepository(db)
    package = core.create_package(_package())
    service = PublishRunService(core, accounts, manager=TaskManager(), profile_manager=BrowserProfileManager(tmp_path / "profiles", repository=accounts))
    run, _ = service.create_run(package.package_id, account.account_id, PublishPlatform.DOUYIN, "checkpoint-binding-1")
    run = core.transition_run(run.run_id, PublishRunState.RUNNING, expected_version=run.state_version, current_step="inspect")
    identity = DraftIdentity(
        runtime_kind="playwright",
        profile_ref=account.profile_ref,
        task_space_id=101,
        task_space_name="douyin:fixture-editor",
        page_fingerprint="sha256:" + "a" * 64,
    )
    checkpoint = PublishExecutionCheckpoint(
        package_fingerprint=package.package_fingerprint,
        account_id=account.account_id,
        platform="douyin",
        attempt=run.attempt,
        runtime_kind="playwright",
        draft_identity=identity,
        completed_stages=[PublishStage.INSPECT],
        last_stage=PublishStage.INSPECT,
    )
    saved = service.record_execution_checkpoint(run.run_id, checkpoint, stage=PublishStage.INSPECT)
    assert saved.state is PublishRunState.RUNNING
    assert saved.checkpoint["last_stage"] == "inspect"

    blocker_checkpoint = PublishExecutionCheckpoint(
        package_fingerprint=package.package_fingerprint,
        account_id=account.account_id,
        platform="douyin",
        attempt=run.attempt,
        runtime_kind="playwright",
        blocker_code=PublishBlockerCode.AUTH_REQUIRED,
        blocked_stage=PublishStage.INSPECT,
    )
    blocked = service.record_execution_checkpoint(
        run.run_id,
        blocker_checkpoint,
        stage=PublishStage.INSPECT,
        blocker=PublishBlockerCode.AUTH_REQUIRED.value,
    )
    assert blocked.state is PublishRunState.WAITING_FOR_LOGIN
    assert blocked.error_code == PublishBlockerCode.AUTH_REQUIRED.value


def test_record_execution_checkpoint_rejects_stage_and_profile_mismatch(tmp_path):
    db = tmp_path / "checkpoint-mismatch.sqlite"
    accounts = PublishAccountRepository(db)
    account = accounts.create_account(PublishPlatform.DOUYIN, "门店", "profile_douyin")
    core = PublishCoreRepository(db)
    package = core.create_package(_package())
    service = PublishRunService(core, accounts, manager=TaskManager(), profile_manager=BrowserProfileManager(tmp_path / "profiles", repository=accounts))
    run, _ = service.create_run(package.package_id, account.account_id, PublishPlatform.DOUYIN, "checkpoint-binding-2")
    core.transition_run(run.run_id, PublishRunState.RUNNING, expected_version=run.state_version, current_step="inspect")
    checkpoint = PublishExecutionCheckpoint(
        package_fingerprint=package.package_fingerprint,
        account_id=account.account_id,
        platform="douyin",
        attempt=run.attempt,
        runtime_kind="playwright",
        draft_identity=DraftIdentity(
            runtime_kind="playwright",
            profile_ref="profile_other",
            page_fingerprint="sha256:" + "a" * 64,
        ),
        completed_stages=[PublishStage.INSPECT],
        last_stage=PublishStage.INSPECT,
    )
    with pytest.raises(PublishRunServiceError, match="CHECKPOINT_PROFILE_MISMATCH"):
        service.record_execution_checkpoint(run.run_id, checkpoint, stage=PublishStage.INSPECT)
