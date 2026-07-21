"""Conservative Douyin adapter with fixture-driven state and field guardrails."""

import hashlib
import inspect
import re
from pathlib import Path
from typing import Any, Awaitable, Callable
from urllib.parse import urlsplit

from pixelle_video.services.publish.browser_runtime import BrowserRuntime
from pixelle_video.services.publish.execution_protocol import (
    BLOCKER_REGISTRY,
    CoverReceipt,
    PublishBlockerCode,
    PublishExecutionCheckpoint,
    PublishStage,
    TopicEntityEvidence,
)
from pixelle_video.services.publish.models import PublishPackage, PublishResult, PublishStatus
from pixelle_video.services.publish.platforms.base import HumanConfirmedPublisher, call_if_available

DOUYIN_CREATOR_PLATFORM = "douyin"
DOUYIN_ADAPTER_VERSION = "douyin-entry@1"
DOUYIN_STATE_TO_RESULT = {
    "signed_out": (PublishStatus.LOGIN_REQUIRED, "DOUYIN_LOGIN_REQUIRED", "waiting_for_login"),
    "captcha": (PublishStatus.FAILED, "DOUYIN_CHALLENGE_REQUIRED", "waiting_for_human"),
    "loading": (PublishStatus.FAILED, "DOUYIN_PAGE_NOT_READY", "needs_attention"),
    "network_error": (PublishStatus.FAILED, "DOUYIN_NETWORK_ERROR", "needs_attention"),
    "uploading": (PublishStatus.UPLOADING, "DOUYIN_UPLOAD_IN_PROGRESS", "running"),
    "processing": (PublishStatus.UPLOADING, "DOUYIN_PROCESSING_IN_PROGRESS", "running"),
    "cover_error": (PublishStatus.FAILED, "DOUYIN_COVER_REJECTED", "needs_attention"),
    "cover_modal": (PublishStatus.DRAFT_READY, "DOUYIN_COVER_MODAL_READY_FOR_HUMAN", "waiting_for_human"),
    "waiting_for_human": (PublishStatus.DRAFT_READY, "DOUYIN_WAITING_FOR_HUMAN", "waiting_for_human"),
    "unknown": (PublishStatus.FAILED, "DOUYIN_PAGE_CHANGED", "needs_attention"),
    "window_closed": (PublishStatus.FAILED, "DOUYIN_WINDOW_CLOSED", "needs_attention"),
}


def _same_douyin_editor_space(left: Any, right: Any) -> bool:
    """Treat upload-entry and post/video as one known creator editor space."""

    values = [str(item or "") for item in (left, right)]
    if any(not item.startswith("douyin:") for item in values):
        return False
    raw_values = [item.removeprefix("douyin:") for item in values]
    parsed_values = [urlsplit(item) for item in raw_values]
    if any(parsed.scheme != "https" for parsed in parsed_values):
        return False
    if parsed_values[0].netloc != parsed_values[1].netloc:
        return False
    if parsed_values[0].netloc != "creator.douyin.com":
        return False
    paths = {parsed.path.rstrip("/") for parsed in parsed_values}
    return paths <= {
        "/creator-micro/content/upload",
        "/creator-micro/content/post/video",
        "/creator-micro/content/editor",
    }


class DouyinPublisher(HumanConfirmedPublisher):
    """Prepare Douyin drafts through an injected browser runtime."""

    def __init__(
        self,
        runtime: BrowserRuntime,
        *,
        profile_path: str | Path | None = None,
        account_id: str | None = None,
        profile_ref: str | None = None,
        checkpoint: PublishExecutionCheckpoint | None = None,
        checkpoint_callback: Callable[
            [PublishExecutionCheckpoint, PublishStage, str | None], Awaitable[Any] | Any
        ] | None = None,
    ):
        super().__init__(runtime, DOUYIN_CREATOR_PLATFORM)
        self.adapter_version = DOUYIN_ADAPTER_VERSION
        self.profile_path = Path(profile_path).resolve() if profile_path else None
        self.account_id = account_id
        self.profile_ref = profile_ref or account_id or "profile_ref_unknown"
        self.checkpoint = checkpoint
        self.checkpoint_callback = checkpoint_callback

    async def _checkpoint(
        self,
        stage: PublishStage,
        *,
        blocker: PublishBlockerCode | None = None,
        page_fingerprint: str | None = None,
        task_space_id: int | None = None,
        task_space_name: str | None = None,
        media_identity: str | None = None,
        remote_media_identity: str | None = None,
        upload_mode: str | None = None,
        final_action_guard_armed: bool | None = None,
        topic_entities: list[TopicEntityEvidence] | None = None,
        cover_receipts: list[CoverReceipt] | None = None,
    ) -> None:
        if self.checkpoint is None or self.checkpoint_callback is None:
            return
        data = self.checkpoint.model_dump(mode="json")
        identity = dict(data.get("draft_identity") or {})
        identity.setdefault("runtime_kind", data.get("runtime_kind", "playwright"))
        identity.setdefault("profile_ref", self.profile_ref)
        if page_fingerprint:
            prior_fingerprint = identity.get("page_fingerprint")
            if prior_fingerprint and prior_fingerprint != page_fingerprint:
                prior_task_space_id = identity.get("task_space_id")
                same_task_space_id = (
                    prior_task_space_id == task_space_id
                    or (prior_task_space_id is None and task_space_id is None)
                )
                if not same_task_space_id or not _same_douyin_editor_space(identity.get("task_space_name"), task_space_name):
                    reset = dict(data)
                    reset.update(
                        draft_identity=None,
                        completed_stages=[],
                        last_stage=None,
                        blocked_stage=None,
                        upload_mode=None,
                        topic_entities=[],
                        cover_receipts=[],
                        blocker_code=None,
                        final_action_guard_armed=False,
                    )
                    self.checkpoint = PublishExecutionCheckpoint.model_validate(reset)
                    await self._record_blocker(PublishBlockerCode.FOREIGN_DRAFT)
                    raise RuntimeError("FOREIGN_DRAFT")
            identity["page_fingerprint"] = page_fingerprint
        if task_space_id is not None:
            identity["task_space_id"] = task_space_id
        if task_space_name:
            identity["task_space_name"] = task_space_name
        if media_identity:
            identity["media_identity"] = media_identity
        if remote_media_identity:
            identity["remote_media_identity"] = remote_media_identity
        if identity.get("page_fingerprint"):
            data["draft_identity"] = identity
        completed = list(data.get("completed_stages") or [])
        if stage.value not in completed:
            completed.append(stage.value)
            data["last_stage"] = stage.value
        data["completed_stages"] = completed
        data["blocker_code"] = blocker.value if blocker else None
        data["blocked_stage"] = None
        if upload_mode:
            data["upload_mode"] = upload_mode
        if final_action_guard_armed is not None:
            data["final_action_guard_armed"] = final_action_guard_armed
        if topic_entities is not None:
            data["topic_entities"] = [item.model_dump(mode="json") for item in topic_entities]
        if cover_receipts is not None:
            data["cover_receipts"] = [item.model_dump(mode="json") for item in cover_receipts]
        checkpoint = PublishExecutionCheckpoint.model_validate(data)
        callback_stage = checkpoint.last_stage or stage
        result = self.checkpoint_callback(
            checkpoint,
            callback_stage,
            blocker.value if blocker else None,
        )
        if inspect.isawaitable(result):
            await result
        self.checkpoint = checkpoint

    async def _record_blocker(self, code: PublishBlockerCode) -> None:
        if self.checkpoint is None or self.checkpoint_callback is None:
            return
        data = self.checkpoint.model_dump(mode="json")
        data["blocker_code"] = code.value
        data["blocked_stage"] = BLOCKER_REGISTRY[code].stage.value
        checkpoint = PublishExecutionCheckpoint.model_validate(data)
        result = self.checkpoint_callback(
            checkpoint,
            BLOCKER_REGISTRY[code].stage,
            code.value,
        )
        if inspect.isawaitable(result):
            await result
        self.checkpoint = checkpoint

    async def _reset_checkpoint_before(self, stage: PublishStage) -> None:
        """Discard only unverified later-stage claims before repair."""

        if self.checkpoint is None or self.checkpoint_callback is None:
            return
        order = list(PublishStage)
        keep = order[: order.index(stage)]
        data = self.checkpoint.model_dump(mode="json")
        data.update(
            completed_stages=[item.value for item in keep],
            last_stage=keep[-1].value if keep else None,
            blocked_stage=None,
            blocker_code=None,
            final_action_guard_armed=False,
            topic_entities=[],
            cover_receipts=[],
        )
        if PublishStage.UPLOAD not in keep:
            data["upload_mode"] = None
        self.checkpoint = PublishExecutionCheckpoint.model_validate(data)
        # An empty prefix must remain empty so an INSPECT blocker is valid and
        # cannot be persisted as a claim that inspection already completed.
        if keep:
            await self._checkpoint(keep[-1])

    async def _verify_existing_fields(self, context: Any, package: PublishPackage) -> list[str] | None:
        """Freshly verify a claimed mutation prefix before reusing it."""

        verified_fields: list[str] = []
        for field_name, expected in (
            ("title", package.title),
            ("description", package.description),
            ("hashtags", package.hashtags),
            ("cover", package.cover_path),
        ):
            if not expected:
                continue
            verified = await call_if_available(context, "wait_for_field", field_name, expected, default=None)
            if verified is None:
                verified = await call_if_available(context, "verify_field", field_name, expected, default=False)
            if verified is not True:
                return None
            verified_fields.append(field_name)
        return verified_fields

    @staticmethod
    def _normalize_topic(value: Any) -> str:
        return str(value or "").strip().lstrip("#").strip().casefold()

    async def _read_topic_evidence(
        self,
        context: Any,
        hashtags: list[str],
        existing: list[TopicEntityEvidence] | None = None,
    ) -> list[TopicEntityEvidence] | None:
        if not hashtags:
            return []
        raw_entities = await call_if_available(context, "read_topic_entities", default=None)
        if not isinstance(raw_entities, list):
            return None
        entities: list[TopicEntityEvidence] = []
        expected = [self._normalize_topic(item) for item in hashtags if item]
        for raw in raw_entities:
            if not isinstance(raw, dict):
                continue
            try:
                entity = TopicEntityEvidence.model_validate(raw)
            except Exception:
                continue
            entities.append(entity)
        by_label = {item.normalized_label.casefold().lstrip("#"): item for item in entities}
        if any(item not in by_label for item in expected):
            return None
        if existing:
            prior_by_label = {
                item.normalized_label.casefold().lstrip("#"): item for item in existing
            }
            for label in expected:
                if label not in prior_by_label or by_label[label].entity_id != prior_by_label[label].entity_id:
                    return None
        return [by_label[item] for item in expected]

    async def _read_cover_evidence(
        self,
        context: Any,
        cover_path: str,
        existing: list[CoverReceipt] | None = None,
    ) -> list[CoverReceipt] | None:
        if not cover_path:
            return []
        raw_receipt = await call_if_available(context, "read_cover_receipt", cover_path, default=None)
        if not isinstance(raw_receipt, dict):
            return None
        try:
            digest = hashlib.sha256(Path(cover_path).read_bytes()).hexdigest()
            accepted_url = str(raw_receipt.get("accepted_url") or "")
            task_space_id = raw_receipt.get("task_space_id")
            task_space_name = str(raw_receipt.get("task_space_name") or "")
            current_task_space_id = (
                self.checkpoint.draft_identity.task_space_id
                if self.checkpoint and self.checkpoint.draft_identity
                else None
            )
            current_task_space_name = (
                self.checkpoint.draft_identity.task_space_name
                if self.checkpoint and self.checkpoint.draft_identity
                else None
            )
            if current_task_space_id is not None and task_space_id != current_task_space_id:
                # A route change is only equivalent when the stable task-space
                # id also remains identical.  Same-URL/different-draft must
                # fail closed rather than inherit a prior cover claim.
                return None
            if current_task_space_name and task_space_name:
                if not _same_douyin_editor_space(current_task_space_name, task_space_name):
                    return None
            elif task_space_name and not current_task_space_name:
                # A receipt from a newer runtime cannot bind itself to a
                # checkpoint that has no task-space name; fail closed. The
                # inverse (legacy receipt without a name) remains compatible
                # when the stable id matches.
                return None
            reused_existing = bool(existing)
            receipt = CoverReceipt(
                slot=str(raw_receipt.get("slot") or "single"),
                ratio=str(raw_receipt.get("ratio") or "3:4"),
                asset_sha256=f"sha256:{digest}",
                asset_path_token=f"asset_cover_{digest[:16]}",
                before_urls=raw_receipt.get("before_urls") or [],
                accepted_url=accepted_url,
                task_space_id=task_space_id,
                reused_existing=reused_existing,
            )
            if existing:
                prior = existing[0]
                if receipt.accepted_url != prior.accepted_url:
                    return None
                if prior.task_space_id is not None and task_space_id != prior.task_space_id:
                    return None
        except (OSError, ValueError, TypeError):
            return None
        return [receipt]

    async def _derive_media_identity(self, context: Any, video_path: str) -> str | None:
        """Bind selected browser file metadata to the package media digest."""

        if self.checkpoint is None or not self.checkpoint.media_sha256:
            return None
        metadata = await call_if_available(context, "uploaded_media_metadata", default=None)
        if not isinstance(metadata, dict):
            return None
        try:
            expected_path = Path(video_path)
            expected_name = expected_path.name
            expected_size = expected_path.stat().st_size
            if str(metadata.get("name")) != expected_name or int(metadata.get("size")) != expected_size:
                return None
            payload = f"{expected_name}:{expected_size}:{self.checkpoint.media_sha256}"
            return "sha256:" + hashlib.sha256(payload.encode()).hexdigest()
        except (OSError, TypeError, ValueError):
            return None

    def _package_media_identity(self, video_path: str) -> str | None:
        if self.checkpoint is None or not self.checkpoint.media_sha256:
            return None
        try:
            path = Path(video_path)
            payload = f"{path.name}:{path.stat().st_size}:{self.checkpoint.media_sha256}"
            return "sha256:" + hashlib.sha256(payload.encode()).hexdigest()
        except OSError:
            return None

    async def _read_remote_media_identity(self, context: Any) -> str | None:
        """Read a stable platform media id/url digest when exposed."""

        raw = await call_if_available(context, "read_remote_media_identity", default=None)
        if isinstance(raw, dict):
            raw = raw.get("id") or raw.get("url")
        if not raw:
            return None
        return "sha256:" + hashlib.sha256(str(raw).strip().encode()).hexdigest()

    async def _record_identity_blocker(self) -> None:
        if self.checkpoint is not None and self.checkpoint.completed_stages:
            await self._reset_checkpoint_before(PublishStage.INSPECT)
        await self._record_blocker(PublishBlockerCode.STATE_AMBIGUOUS)

    async def prepare_draft(self, package: PublishPackage) -> PublishResult:
        """Prepare only a reviewable draft; never invoke a final publish action.

        Older injected runtimes used by the V1 assistant do not expose the new
        state/readback hooks, so they retain the shared conservative flow. The
        PUB-3 runtime path opts into state mapping and semantic readback when
        those hooks are present.
        """

        if package.platform != self.platform:
            raise ValueError(
                f"Publish package platform mismatch: {package.platform} != {self.platform}"
            )
        launch_kwargs = {}
        if self.profile_path is not None:
            launch_kwargs = {
                "profile_path": str(self.profile_path),
                "account_id": self.account_id,
            }
        context = await self.runtime.launch_persistent_context(self.platform, **launch_kwargs)
        await call_if_available(context, "open_creator_page")
        detected_state = await call_if_available(context, "wait_for_interactive_state", default=None)
        if detected_state is None:
            detected_state = await call_if_available(context, "detect_state", default=None)
        if detected_state in DOUYIN_STATE_TO_RESULT:
            blocker_by_state = {
                "signed_out": PublishBlockerCode.AUTH_REQUIRED,
                "captcha": PublishBlockerCode.CHALLENGE_REQUIRED,
                "loading": PublishBlockerCode.STATE_AMBIGUOUS,
                "network_error": PublishBlockerCode.INPUT_CHANNEL_BROKEN,
                "unknown": PublishBlockerCode.STATE_AMBIGUOUS,
                "window_closed": PublishBlockerCode.INPUT_CHANNEL_BROKEN,
            }
            if detected_state in blocker_by_state:
                if self.checkpoint is not None and self.checkpoint.completed_stages:
                    await self._reset_checkpoint_before(PublishStage.INSPECT)
                await self._record_blocker(blocker_by_state[detected_state])
            status, code, adapter_state = DOUYIN_STATE_TO_RESULT[detected_state]
            return PublishResult(
                status=status,
                platform=self.platform,
                message=code,
                requires_human_confirmation=True,
                adapter_state=adapter_state,
            )
        if detected_state is None:
            return await self._prepare_legacy_context(context, package)
        if detected_state not in {"signed_in", "editor_ready", "upload_entry", "ready_for_upload"}:
            return PublishResult(
                status=PublishStatus.FAILED,
                platform=self.platform,
                message="DOUYIN_UNSUPPORTED_STATE",
                requires_human_confirmation=True,
            )

        if not await call_if_available(context, "is_logged_in", default=False):
            if self.checkpoint is not None and self.checkpoint.completed_stages:
                await self._reset_checkpoint_before(PublishStage.INSPECT)
            await self._record_blocker(PublishBlockerCode.AUTH_REQUIRED)
            return PublishResult(
                status=PublishStatus.LOGIN_REQUIRED,
                platform=self.platform,
                message="DOUYIN_LOGIN_REQUIRED",
                requires_human_confirmation=True,
                )

        page_fingerprint = await call_if_available(context, "page_fingerprint", default=None)
        if self.checkpoint is not None and (
            not isinstance(page_fingerprint, str)
            or re.fullmatch(r"sha256:[0-9a-f]{64}", page_fingerprint) is None
        ):
            if self.checkpoint.completed_stages:
                await self._reset_checkpoint_before(PublishStage.INSPECT)
            await self._record_blocker(PublishBlockerCode.STATE_AMBIGUOUS)
            return PublishResult(
                status=PublishStatus.FAILED,
                platform=self.platform,
                message="DOUYIN_DRAFT_IDENTITY_UNAVAILABLE",
                requires_human_confirmation=True,
                adapter_state="needs_attention",
            )
        task_space = await call_if_available(context, "task_space_identity", default={})
        if not isinstance(task_space, dict):
            task_space = {}
        try:
            await self._checkpoint(
                PublishStage.INSPECT,
                page_fingerprint=page_fingerprint if isinstance(page_fingerprint, str) else None,
                task_space_id=task_space.get("id") if isinstance(task_space.get("id"), int) else None,
                task_space_name=str(task_space.get("name") or "") or None,
            )
        except RuntimeError as exc:
            if str(exc) != "FOREIGN_DRAFT":
                raise
            return PublishResult(
                status=PublishStatus.FAILED,
                platform=self.platform,
                message="DOUYIN_FOREIGN_DRAFT",
                requires_human_confirmation=True,
                adapter_state="needs_attention",
            )

        # Douyin exposes the selected topic as a semantic DOM node but hides
        # its remote challenge id after a browser restart.  Restore the id
        # accepted by the same fingerprint-bound checkpoint so the runtime can
        # still compare the selected node without inventing a new identity.
        await call_if_available(
            context,
            "seed_topic_entity_ids",
            [item.model_dump(mode="json") for item in (self.checkpoint.topic_entities if self.checkpoint else [])],
            default=None,
        )

        filled_fields: list[str] = []
        upload_claimed = self.checkpoint is not None and PublishStage.UPLOAD in self.checkpoint.completed_stages
        if upload_claimed:
            prior_media_identity = self.checkpoint.draft_identity.media_identity if self.checkpoint and self.checkpoint.draft_identity else None
            raw_metadata = await call_if_available(context, "uploaded_media_metadata", default=None)
            if raw_metadata is None:
                # A browser restart normally clears the local file input. A
                # preview alone is insufficient; only a stable remote media
                # identity may authorize reuse of the persisted claim.
                remote_identity = await self._read_remote_media_identity(context)
                prior_remote_identity = self.checkpoint.draft_identity.remote_media_identity if self.checkpoint and self.checkpoint.draft_identity else None
                preview_verified = await call_if_available(context, "verify_field", "video", package.video_path, default=False)
                media_identity = prior_media_identity if preview_verified is True and remote_identity and remote_identity == prior_remote_identity else None
            else:
                # A readable but different file is a foreign-media mismatch,
                # never an unavailable-input restart case.
                media_identity = await self._derive_media_identity(context, package.video_path)
            if media_identity is None or media_identity != prior_media_identity:
                await self._record_identity_blocker()
                return PublishResult(
                    status=PublishStatus.FAILED,
                    platform=self.platform,
                    message="DOUYIN_MEDIA_IDENTITY_MISMATCH",
                    requires_human_confirmation=True,
                    adapter_state="needs_attention",
                )
            verified = await call_if_available(context, "verify_field", "video", package.video_path, default=False)
            if verified is not True:
                await self._reset_checkpoint_before(PublishStage.UPLOAD)
                upload_claimed = False
            else:
                filled_fields.append("video")
                if PublishStage.WAIT not in self.checkpoint.completed_stages:
                    await self._checkpoint(PublishStage.WAIT, upload_mode=self.checkpoint.upload_mode.value if self.checkpoint.upload_mode else "already_ready")

        if not upload_claimed and detected_state in {"signed_in", "upload_entry", "ready_for_upload"}:
            changed = await call_if_available(context, "upload_video", package.video_path, default=False)
            if changed is False:
                await self._record_blocker(PublishBlockerCode.UPLOAD_NOT_STARTED)
                return PublishResult(
                    status=PublishStatus.FAILED,
                    platform=self.platform,
                    message="DOUYIN_VIDEO_WRITE_FAILED",
                    requires_human_confirmation=True,
                )
            waited_for_editor = await call_if_available(context, "wait_for_editor_ready", default=None)
            if waited_for_editor is None:
                await call_if_available(context, "wait_for_state", "editor_ready", default=None)
            state_after_upload = await call_if_available(context, "detect_state", default="editor_ready")
            if state_after_upload != "editor_ready":
                if state_after_upload in DOUYIN_STATE_TO_RESULT:
                    blocker = PublishBlockerCode.UPLOAD_STALLED
                    if state_after_upload == "signed_out":
                        blocker = PublishBlockerCode.AUTH_REQUIRED
                    if blocker is PublishBlockerCode.AUTH_REQUIRED and self.checkpoint is not None and self.checkpoint.completed_stages:
                        await self._reset_checkpoint_before(PublishStage.INSPECT)
                    await self._record_blocker(blocker)
                    status, code, adapter_state = DOUYIN_STATE_TO_RESULT[state_after_upload]
                    return PublishResult(
                        status=status,
                        platform=self.platform,
                        message=code,
                        requires_human_confirmation=True,
                        adapter_state=adapter_state,
                    )
                return PublishResult(
                    status=PublishStatus.FAILED,
                    platform=self.platform,
                message="DOUYIN_EDITOR_NOT_READY",
                requires_human_confirmation=True,
                adapter_state="needs_attention",
                )
            video_readback_waited = await call_if_available(context, "wait_for_video_readback", default=None)
            if video_readback_waited is False:
                await self._record_blocker(PublishBlockerCode.UPLOAD_STALLED)
                return PublishResult(
                    status=PublishStatus.FAILED,
                    platform=self.platform,
                    message="DOUYIN_VIDEO_READBACK_FAILED",
                    requires_human_confirmation=True,
                )
            verified = await call_if_available(context, "verify_field", "video", package.video_path, default=True)
            if verified is False:
                await self._record_blocker(PublishBlockerCode.UPLOAD_STALLED)
                return PublishResult(
                    status=PublishStatus.FAILED,
                    platform=self.platform,
                    message="DOUYIN_VIDEO_READBACK_FAILED",
                    requires_human_confirmation=True,
                )
            # The file input may be cleared immediately after a successful
            # injection.  At this point the action itself is known and the
            # package digest/path stat provide the persisted local identity;
            # resume paths above remain stricter and require fresh metadata or
            # a remote media id.
            media_identity = self._package_media_identity(package.video_path)
            remote_media_identity = await self._read_remote_media_identity(context)
            if self.checkpoint is not None and media_identity is None:
                await self._record_identity_blocker()
                return PublishResult(
                    status=PublishStatus.FAILED,
                    platform=self.platform,
                    message="DOUYIN_MEDIA_IDENTITY_UNAVAILABLE",
                    requires_human_confirmation=True,
                    adapter_state="needs_attention",
                )
            filled_fields.append("video")
            await self._checkpoint(
                PublishStage.UPLOAD,
                upload_mode="injected",
                media_identity=media_identity,
                remote_media_identity=remote_media_identity,
            )
            await self._checkpoint(PublishStage.WAIT)
        elif not upload_claimed:
            verified = await call_if_available(context, "verify_field", "video", package.video_path, default=True)
            if verified is False:
                await self._record_blocker(PublishBlockerCode.UPLOAD_STALLED)
                return PublishResult(
                    status=PublishStatus.FAILED,
                    platform=self.platform,
                    message="DOUYIN_VIDEO_READBACK_FAILED",
                    requires_human_confirmation=True,
                )
            media_identity = await self._derive_media_identity(context, package.video_path) if self.checkpoint is not None else None
            remote_media_identity = await self._read_remote_media_identity(context) if self.checkpoint is not None else None
            if self.checkpoint is not None and media_identity is None:
                await self._record_identity_blocker()
                return PublishResult(
                    status=PublishStatus.FAILED,
                    platform=self.platform,
                    message="DOUYIN_MEDIA_IDENTITY_UNAVAILABLE",
                    requires_human_confirmation=True,
                    adapter_state="needs_attention",
                )
            filled_fields.append("video")
            await self._checkpoint(
                PublishStage.UPLOAD,
                upload_mode="already_ready",
                media_identity=media_identity,
                remote_media_identity=remote_media_identity,
            )
            await self._checkpoint(PublishStage.WAIT)

        topic_evidence: list[TopicEntityEvidence] = []
        cover_evidence: list[CoverReceipt] = []
        mutation_claimed = self.checkpoint is not None and PublishStage.MUTATE in self.checkpoint.completed_stages
        if mutation_claimed:
            verified_fields = await self._verify_existing_fields(context, package)
            topic_evidence = await self._read_topic_evidence(
                context,
                package.hashtags,
                self.checkpoint.topic_entities if self.checkpoint is not None else None,
            )
            cover_evidence = await self._read_cover_evidence(
                context,
                package.cover_path,
                self.checkpoint.cover_receipts if self.checkpoint is not None else None,
            )
            evidence_complete = (
                topic_evidence is not None
                and cover_evidence is not None
                and (not package.hashtags or bool(topic_evidence))
                and (not package.cover_path or bool(cover_evidence))
            )
            if verified_fields is not None and evidence_complete:
                filled_fields.extend(item for item in verified_fields if item not in filled_fields)
            else:
                await self._reset_checkpoint_before(PublishStage.MUTATE)
                mutation_claimed = False

        actions: list[tuple[str, tuple[Any, ...], str]] = [
            ("fill_title", (package.title,), "title"),
            ("fill_description", (package.description,), "description"),
            ("fill_hashtags", (package.hashtags,), "hashtags"),
            ("upload_cover", (package.cover_path,), "cover"),
        ]
        for method_name, args, field_name in ([] if mutation_claimed else actions):
            if not args[0]:
                continue
            changed = await call_if_available(context, method_name, *args, default=False)
            if changed is False:
                blocker = PublishBlockerCode.COVER_READBACK_MISMATCH if field_name == "cover" else PublishBlockerCode.ACTION_FAILED
                await self._record_blocker(blocker)
                return PublishResult(
                    status=PublishStatus.FAILED,
                    platform=self.platform,
                    message=f"DOUYIN_{field_name.upper()}_WRITE_FAILED",
                    requires_human_confirmation=True,
                    filled_fields=filled_fields,
                )
            verified = await call_if_available(context, "wait_for_field", field_name, args[0], default=None)
            if verified is None:
                verified = await call_if_available(context, "verify_field", field_name, args[0], default=True)
            if verified is False:
                blocker = PublishBlockerCode.COVER_READBACK_MISMATCH if field_name == "cover" else PublishBlockerCode.TOPIC_READBACK_MISMATCH if field_name == "hashtags" else PublishBlockerCode.ACTION_FAILED
                await self._record_blocker(blocker)
                return PublishResult(
                    status=PublishStatus.FAILED,
                    platform=self.platform,
                    message=f"DOUYIN_{field_name.upper()}_READBACK_FAILED",
                    requires_human_confirmation=True,
                    filled_fields=filled_fields,
                )
            filled_fields.append(field_name)

        if not mutation_claimed and self.checkpoint is not None:
            topic_evidence = await self._read_topic_evidence(context, package.hashtags)
            cover_evidence = await self._read_cover_evidence(context, package.cover_path)
            if topic_evidence is None:
                await self._record_blocker(PublishBlockerCode.TOPIC_READBACK_MISMATCH)
                return PublishResult(
                    status=PublishStatus.FAILED,
                    platform=self.platform,
                    message="DOUYIN_TOPIC_ENTITY_READBACK_FAILED",
                    requires_human_confirmation=True,
                    filled_fields=filled_fields,
                )
            if cover_evidence is None:
                await self._record_blocker(PublishBlockerCode.COVER_READBACK_MISMATCH)
                return PublishResult(
                    status=PublishStatus.FAILED,
                    platform=self.platform,
                    message="DOUYIN_COVER_RECEIPT_READBACK_FAILED",
                    requires_human_confirmation=True,
                    filled_fields=filled_fields,
                )

        await self._checkpoint(
            PublishStage.MUTATE,
            topic_entities=topic_evidence,
            cover_receipts=cover_evidence,
        )
        await call_if_available(context, "wait_until_draft_ready")
        final_action = await call_if_available(context, "request_final_action", default=None)
        if final_action not in (None, False):
            return PublishResult(
                status=PublishStatus.FAILED,
                platform=self.platform,
                message="FINAL_ACTION_BLOCKED",
                requires_human_confirmation=True,
                filled_fields=filled_fields,
            )
        guard_armed = await call_if_available(context, "final_action_guard_armed", default=False)
        if self.checkpoint is not None and not guard_armed:
            await self._record_blocker(PublishBlockerCode.FINAL_ACTION_GUARD_FAILED)
            return PublishResult(
                status=PublishStatus.FAILED,
                platform=self.platform,
                message="FINAL_ACTION_GUARD_NOT_ARMED",
                requires_human_confirmation=True,
                filled_fields=filled_fields,
            )
        await self._checkpoint(
            PublishStage.VERIFY,
            final_action_guard_armed=True if self.checkpoint is not None else None,
        )
        draft_url = await call_if_available(context, "current_url", default="")
        return PublishResult(
            status=PublishStatus.DRAFT_READY,
            platform=self.platform,
            message="DOUYIN_DRAFT_READY_WAITING_FOR_HUMAN",
            draft_url=str(draft_url or ""),
            requires_human_confirmation=True,
            filled_fields=filled_fields,
            adapter_state="waiting_for_human",
        )

    async def _prepare_legacy_context(self, context: Any, package: PublishPackage) -> PublishResult:
        """Keep the V1 injected-runtime call sequence stable during migration."""

        if not await call_if_available(context, "is_logged_in", default=False):
            return PublishResult(
                status=PublishStatus.LOGIN_REQUIRED,
                platform=self.platform,
                message="请先在发布助手浏览器中登录抖音创作平台。登录后重新打开发布助手即可自动填充。",
            )
        filled_fields: list[str] = []
        for method_name, args, field_name in (
            ("upload_video", (package.video_path,), "video"),
            ("fill_title", (package.title,), "title"),
            ("fill_description", (package.description,), "description"),
            ("fill_hashtags", (package.hashtags,), "hashtags"),
            ("upload_cover", (package.cover_path,), "cover"),
        ):
            if not args[0]:
                continue
            changed = await call_if_available(context, method_name, *args, default=False)
            if changed is not False:
                filled_fields.append(field_name)
        await call_if_available(context, "wait_until_draft_ready")
        draft_url = await call_if_available(context, "current_url", default="")
        return PublishResult(
            status=PublishStatus.DRAFT_READY,
            platform=self.platform,
            message="抖音发布信息已自动填充，请在浏览器中检查预览，并由你亲自点击最终发布。",
            draft_url=str(draft_url or ""),
            requires_human_confirmation=True,
            filled_fields=filled_fields,
        )
