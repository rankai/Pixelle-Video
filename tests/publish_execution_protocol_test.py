import pytest
from pydantic import ValidationError

from pixelle_video.services.publish.execution_protocol import (
    CoverReceipt,
    DraftIdentity,
    PublishBlockerCode,
    PublishExecutionCheckpoint,
    PublishStage,
    TopicEntityEvidence,
    UploadMode,
    parse_checkpoint,
)

PACKAGE_FP = "sha256:" + "e" * 64


def _identity() -> DraftIdentity:
    return DraftIdentity(
        runtime_kind="playwright",
        profile_ref="profile_ref_douyin",
        page_fingerprint="sha256:" + "a" * 64,
        media_identity="sha256:" + "f" * 64,
    )


def test_checkpoint_records_ordered_stages_without_secrets_or_final_action():
    checkpoint = PublishExecutionCheckpoint(
        package_fingerprint=PACKAGE_FP,
        account_id="acct_1",
        platform="douyin",
        attempt=1,
        runtime_kind="playwright",
        draft_identity=_identity(),
        completed_stages=[PublishStage.INSPECT, PublishStage.UPLOAD, PublishStage.WAIT],
        last_stage=PublishStage.WAIT,
        upload_mode=UploadMode.INJECTED,
        media_sha256="sha256:" + "b" * 64,
    )
    serialized = checkpoint.as_checkpoint()
    assert serialized["final_publish_clicked"] is False
    assert "cookie" not in str(serialized).lower()
    assert parse_checkpoint(serialized) == checkpoint


def test_checkpoint_rejects_out_of_order_or_blocked_ready_state():
    base = dict(
        package_fingerprint=PACKAGE_FP,
        account_id="acct_1",
        platform="douyin",
        attempt=1,
        runtime_kind="playwright",
        draft_identity=_identity(),
        upload_mode=UploadMode.ALREADY_READY,
        media_sha256="sha256:" + "b" * 64,
    )
    with pytest.raises(ValidationError, match="COMPLETED_STAGES_MUST_BE_CONTIGUOUS_PREFIX"):
        PublishExecutionCheckpoint(**base, completed_stages=[PublishStage.VERIFY, PublishStage.INSPECT])
    with pytest.raises(ValidationError, match="LAST_STAGE_MUST_MATCH_COMPLETED_PREFIX"):
        PublishExecutionCheckpoint(**base, completed_stages=[PublishStage.INSPECT, PublishStage.UPLOAD], last_stage=PublishStage.INSPECT)
    blocker_base = dict(base)
    blocker_base.pop("upload_mode")
    blocker_base.pop("media_sha256")
    with pytest.raises(ValidationError, match="BLOCKER_REQUIRES_BLOCKED_STAGE"):
        PublishExecutionCheckpoint(**blocker_base, completed_stages=[], blocker_code=PublishBlockerCode.COVER_READBACK_MISMATCH)


def test_identity_requires_task_space_id_and_name_together():
    with pytest.raises(ValidationError, match="TASK_SPACE_ID_NAME_MUST_BE_PAIRED"):
        DraftIdentity(
            runtime_kind="ego-lite",
            profile_ref="profile_ref_douyin",
            task_space_id=7,
            page_fingerprint="sha256:" + "c" * 64,
        )


def test_cover_receipt_and_real_topic_evidence_are_structured():
    checkpoint = PublishExecutionCheckpoint(
        package_fingerprint=PACKAGE_FP,
        account_id="acct_1",
        platform="douyin",
        attempt=1,
        runtime_kind="playwright",
        draft_identity=_identity(),
        completed_stages=[PublishStage.INSPECT, PublishStage.UPLOAD, PublishStage.WAIT, PublishStage.MUTATE, PublishStage.VERIFY],
        last_stage=PublishStage.VERIFY,
        upload_mode=UploadMode.ALREADY_READY,
        media_sha256="sha256:" + "b" * 64,
        final_action_guard_armed=True,
        topic_entities=[TopicEntityEvidence(label="#门店营销", normalized_label="门店营销", mention_type="#", entity_id="topic_1")],
        cover_receipts=[CoverReceipt(slot="single", ratio="3:4", asset_sha256="sha256:" + "d" * 64, asset_path_token="asset_cover_1", accepted_url="https://cdn.example/cover.png")],
    )
    assert checkpoint.topic_entities[0].mention_type == "#"
    assert checkpoint.cover_receipts[0].accepted_url.startswith("https://")


def test_checkpoint_rejects_raw_profile_paths_urls_and_empty_entity_ids():
    with pytest.raises(ValidationError):
        DraftIdentity(runtime_kind="playwright", profile_ref="/Users/me/Profile", page_fingerprint="sha256:" + "a" * 64)
    with pytest.raises(ValidationError):
        CoverReceipt(slot="single", ratio="0:4", asset_sha256="sha256:" + "d" * 64, asset_path_token="asset_cover_1", accepted_url="https://cdn.example/cover.png")
    receipt = CoverReceipt(slot="single", ratio="3:4", asset_sha256="sha256:" + "d" * 64, asset_path_token="asset_cover_1", accepted_url="https://cdn.example/cover.png?token=secret")
    assert receipt.accepted_url == "https://cdn.example/cover.png"
    with pytest.raises(ValidationError):
        TopicEntityEvidence(label="#门店营销", normalized_label="门店营销", mention_type="#", entity_id="")


def test_checkpoint_rejects_unknown_schema_runtime_mismatch_and_unarmed_verify():
    with pytest.raises(ValidationError):
        PublishExecutionCheckpoint(schema_version=1, package_fingerprint=PACKAGE_FP, account_id="acct_1", platform="douyin", attempt=1, runtime_kind="playwright")
    with pytest.raises(ValidationError, match="DRAFT_IDENTITY_RUNTIME_MISMATCH"):
        PublishExecutionCheckpoint(package_fingerprint=PACKAGE_FP, account_id="acct_1", platform="douyin", attempt=1, runtime_kind="playwright", draft_identity=DraftIdentity(runtime_kind="ego-lite", profile_ref="profile_ref_douyin", page_fingerprint="sha256:" + "a" * 64))
    with pytest.raises(ValidationError, match="VERIFY_REQUIRES_FINAL_GUARD"):
        PublishExecutionCheckpoint(package_fingerprint=PACKAGE_FP, account_id="acct_1", platform="douyin", attempt=1, runtime_kind="playwright", draft_identity=_identity(), completed_stages=list(PublishStage), last_stage=PublishStage.VERIFY, upload_mode=UploadMode.ALREADY_READY, media_sha256="sha256:" + "b" * 64)
