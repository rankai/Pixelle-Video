"""Shared conservative publisher that stops before the final submit action."""

import hashlib
import inspect
import re
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from pixelle_video.services.publish.browser_runtime import BrowserRuntime
from pixelle_video.services.publish.execution_protocol import (
    CoverReceipt,
    DraftIdentity,
    PublishExecutionCheckpoint,
    PublishStage,
    TopicEntityEvidence,
    UploadMode,
)
from pixelle_video.services.publish.models import PublishPackage, PublishResult, PublishStatus
from pixelle_video.services.publish.platform_profiles import (
    canonical_platform,
    get_platform_profile,
)

PLATFORM_LABELS = {
    "douyin": "抖音",
    "xiaohongshu": "小红书",
    "shipinhao": "视频号",
    "video_channel": "视频号",
    "kuaishou": "快手",
}


class HumanConfirmedPublisher:
    """Fill a creator draft without exposing a final-publish browser action."""

    platform: str

    def __init__(
        self,
        runtime: BrowserRuntime,
        platform: str,
        *,
        profile_path: str | Path | None = None,
        account_id: str | None = None,
        profile_ref: str | None = None,
        checkpoint: PublishExecutionCheckpoint | None = None,
        checkpoint_callback: Callable[[PublishExecutionCheckpoint, PublishStage, str | None], Awaitable[Any] | Any] | None = None,
    ):
        if platform not in PLATFORM_LABELS:
            raise ValueError(f"Unsupported publish platform: {platform}")
        self.runtime = runtime
        self.requested_platform = platform
        self.platform = canonical_platform(platform)
        self.profile = get_platform_profile(platform) if self.platform != "douyin" else None
        self.adapter_version = self.profile.adapter_version if self.profile else "douyin@1"
        self.profile_path = profile_path
        self.account_id = account_id
        raw_profile_ref = str(profile_ref or account_id or f"{self.platform}_legacy")
        safe_profile_ref = re.sub(r"[^A-Za-z0-9_-]+", "_", raw_profile_ref).strip("_")
        self.profile_ref = safe_profile_ref if safe_profile_ref.startswith("profile_") else f"profile_{safe_profile_ref}"
        self.checkpoint = checkpoint
        self.checkpoint_callback = checkpoint_callback
        self._last_context: Any = None

    async def prepare_draft(self, package: PublishPackage) -> PublishResult:
        if canonical_platform(package.platform) != self.platform:
            raise ValueError(
                f"Publish package platform mismatch: {package.platform} != {self.platform}"
            )

        launch = self.runtime.launch_persistent_context
        parameters = inspect.signature(launch).parameters
        launch_kwargs: dict[str, Any] = {}
        if "profile_path" in parameters and self.profile_path is not None:
            launch_kwargs["profile_path"] = self.profile_path
        if "account_id" in parameters and self.account_id is not None:
            launch_kwargs["account_id"] = self.account_id
        context = await launch(self.platform, **launch_kwargs)
        self._last_context = context
        label = PLATFORM_LABELS[self.platform]
        if self.checkpoint is not None and self.checkpoint_callback is None:
            return PublishResult(
                status=PublishStatus.FAILED,
                platform=self.platform,
                message="CHECKPOINT_CALLBACK_UNAVAILABLE",
                adapter_state="needs_attention",
                adapter_version=self.adapter_version,
            )
        if not hasattr(context, "open_creator_page"):
            return self._failure("PLATFORM_ENTRY_OPEN_FAILED")
        open_page = await _call_required(context, "open_creator_page")
        if open_page is False:
            return self._failure("PLATFORM_ENTRY_OPEN_FAILED")
        state = await call_if_available(context, "wait_for_interactive_state", default=None)
        if state is None:
            state = await call_if_available(context, "detect_state", default=None)
        if state is None:
            return self._failure("PLATFORM_STATE_PROBE_UNAVAILABLE")
        if state in {"signed_out", "login_required"}:
            return PublishResult(
                status=PublishStatus.LOGIN_REQUIRED,
                platform=self.platform,
                message=f"请先在发布助手浏览器中登录{label}创作平台。登录后重新打开发布助手即可自动填充。",
                adapter_state="waiting_for_human",
                adapter_version=self.adapter_version,
            )
        if state in {
            "captcha",
            "unknown",
            "network_error",
            "window_closed",
            "loading",
            "uploading",
            "processing",
        }:
            return self._failure(f"PLATFORM_UNSAFE_STATE:{state}")
        if not await _call_required(context, "is_logged_in"):
            return PublishResult(
                status=PublishStatus.LOGIN_REQUIRED,
                platform=self.platform,
                message=f"请先在发布助手浏览器中登录{label}创作平台。登录后重新打开发布助手即可自动填充。",
                adapter_state="waiting_for_human",
                adapter_version=self.adapter_version,
            )

        current_url = await _call_required(context, "current_url")
        if not _same_platform_origin(str(current_url or ""), self.profile.entry_url):
            return self._failure("PLATFORM_ENTRY_IDENTITY_MISMATCH")
        page_fingerprint = await _call_required(context, "page_fingerprint")
        task_space = await _call_required(context, "task_space_identity")
        if not isinstance(page_fingerprint, str) or not re.fullmatch(r"sha256:[0-9a-f]{64}", page_fingerprint) or not isinstance(task_space, dict) or not task_space.get("id") or not task_space.get("name"):
            return self._failure("PLATFORM_DRAFT_IDENTITY_UNAVAILABLE")
        current_path = urlsplit(str(current_url)).path.rstrip("/")
        expected_path = urlsplit(self.profile.entry_url).path.rstrip("/")
        if not (current_path == expected_path or current_path.startswith(f"{expected_path}/")):
            return self._failure("PLATFORM_ENTRY_IDENTITY_MISMATCH")

        required_fields = set(self.profile.required_fields)
        missing = [field for field in required_fields if not _package_field_present(package, field)]
        if missing:
            return self._failure(f"REQUIRED_PLATFORM_FIELDS_MISSING:{','.join(sorted(missing))}")
        media_sha = _sha256_file(package.video_path)
        if media_sha is None:
            return self._failure("VIDEO_MEDIA_NOT_READABLE")
        identity = DraftIdentity(
            runtime_kind="playwright",
            profile_ref=self.profile_ref,
            task_space_id=int(task_space["id"]),
            task_space_name=str(task_space["name"]),
            page_fingerprint=page_fingerprint,
            media_identity=media_sha,
        )
        if self.checkpoint is not None:
            if canonical_platform(self.checkpoint.platform) != self.platform:
                return self._failure("CHECKPOINT_PLATFORM_MISMATCH")
            prior_identity = self.checkpoint.draft_identity
            if prior_identity and (
                prior_identity.page_fingerprint != identity.page_fingerprint
                or prior_identity.task_space_id != identity.task_space_id
            ):
                return self._failure("STATE_AMBIGUOUS")
            await self._record_stage(PublishStage.INSPECT, identity=identity)

        expected_values = {
            "video": package.video_path,
            "title": package.title,
            "description": package.description,
            "hashtags": package.hashtags,
            "cover": package.cover_path,
        }
        filled_fields: list[str] = []
        readback_fields: list[str] = []
        prior_upload = self.checkpoint is not None and PublishStage.UPLOAD in self.checkpoint.completed_stages
        if prior_upload:
            if await _call_required(context, "verify_field", "video", package.video_path) is not True:
                return self._failure("STATE_AMBIGUOUS")
        else:
            if await _call_required(context, "upload_video", package.video_path) is not True:
                return self._failure("VIDEO_UPLOAD_FAILED")
        video_readback = await _call_required(context, "verify_field", "video", package.video_path)
        if video_readback is not True:
            return self._failure("VIDEO_READBACK_FAILED", filled_fields=filled_fields)
        remote_media_identity = await call_if_available(context, "read_remote_media_identity", default=None)
        media_identity_boundary: str | None = None
        if not remote_media_identity:
            media_identity_boundary = getattr(self.profile, "media_identity_boundary", None)
        if self.checkpoint is not None and not remote_media_identity:
            profile_requires_identity = bool(getattr(self.profile, "media_identity_required", True))
            if profile_requires_identity or not media_identity_boundary:
                return self._failure("VIDEO_PLATFORM_READBACK_UNAVAILABLE", filled_fields=filled_fields)
        remote_media_digest = _remote_identity_digest(remote_media_identity)
        if self.checkpoint is not None and prior_identity and prior_identity.remote_media_identity and remote_media_digest != prior_identity.remote_media_identity:
            return self._failure("VIDEO_MEDIA_IDENTITY_MISMATCH", filled_fields=filled_fields)
        readback_fields.append("video")
        filled_fields.append("video")
        if self.checkpoint is not None:
            identity = identity.model_copy(update={"remote_media_identity": remote_media_digest})
            await self._record_stage(PublishStage.UPLOAD, identity=identity, media_sha=media_sha, upload_mode=UploadMode.RESUME_EXISTING if prior_upload else UploadMode.INJECTED)
        if not hasattr(context, "wait_until_draft_ready"):
            return self._failure("PLATFORM_PROCESSING_PROBE_UNAVAILABLE", filled_fields=filled_fields)
        if await _call_required(context, "wait_until_draft_ready") is False:
            return self._failure("PLATFORM_PROCESSING_FAILED", filled_fields=filled_fields)
        if self.checkpoint is not None:
            await self._record_stage(PublishStage.WAIT, identity=identity, media_sha=media_sha, upload_mode=UploadMode.RESUME_EXISTING if prior_upload else UploadMode.INJECTED)

        prior_mutate = self.checkpoint is not None and PublishStage.MUTATE in self.checkpoint.completed_stages
        if not prior_mutate:
            operations = {
                "title": ("fill_title", package.title),
                "description": ("fill_description", package.description),
                "hashtags": ("fill_hashtags", package.hashtags),
                "cover": ("upload_cover", package.cover_path),
            }
            for field in self.profile.required_fields:
                if field == "video":
                    continue
                method_name, value = operations[field]
                if await _call_required(context, method_name, value) is not True:
                    return self._failure(f"{field.upper()}_FILL_FAILED", filled_fields=filled_fields)
                filled_fields.append(field)
        for field in self.profile.required_fields:
            if field == "video":
                continue
            if await _call_required(context, "verify_field", field, expected_values[field]) is not True:
                return self._failure(f"{field.upper()}_READBACK_FAILED", filled_fields=filled_fields)
            readback_fields.append(field)
            if field not in filled_fields:
                filled_fields.append(field)
        topic_evidence: list[TopicEntityEvidence] = []
        if "hashtags" not in self.profile.required_fields or not package.hashtags:
            fallbacks = list(self.checkpoint.platform_fallback_boundaries) if self.checkpoint is not None else []
        elif not self.profile.supports_topic_entities:
            fallbacks = await call_if_available(context, "platform_fallback_boundaries", default=[])
            if not fallbacks and self.checkpoint is not None:
                fallbacks = list(self.checkpoint.platform_fallback_boundaries)
            if "HASHTAGS_TEXT_FALLBACK" not in set(fallbacks or []):
                return self._failure("HASHTAGS_FALLBACK_BOUNDARY_MISSING", filled_fields=filled_fields)
        else:
            raw_entities = await call_if_available(context, "read_topic_entities", default=[])
            topic_evidence = _topic_evidence(raw_entities, package.hashtags)
            if package.hashtags and topic_evidence is None:
                return self._failure("HASHTAGS_READBACK_FAILED", filled_fields=filled_fields)
            fallbacks = await call_if_available(context, "platform_fallback_boundaries", default=[])
        fallbacks = list(fallbacks or [])
        unsupported_fields = tuple(getattr(self.profile, "unsupported_fields", ()) or ())
        for field in unsupported_fields:
            boundary = f"FIELD_UNSUPPORTED:{str(field).upper()}"
            if boundary not in fallbacks:
                fallbacks.append(boundary)
        if media_identity_boundary and media_identity_boundary not in fallbacks:
            fallbacks.append(media_identity_boundary)
        if not fallbacks and self.checkpoint is not None and self.checkpoint.platform_fallback_boundaries:
            fallbacks = list(self.checkpoint.platform_fallback_boundaries)
        cover_receipts: list[CoverReceipt] = []
        raw_cover_receipt = await call_if_available(context, "read_cover_receipt", package.cover_path, default=None)
        if package.cover_path:
            cover_receipt = _cover_receipt_from_raw(package.cover_path, raw_cover_receipt, task_space)
            if cover_receipt is None:
                boundary = getattr(self.profile, "cover_receipt_boundary", None)
                raw_accepted_url = (
                    str(raw_cover_receipt.get("accepted_url") or "")
                    if isinstance(raw_cover_receipt, dict)
                    else ""
                )
                if (
                    boundary
                    and raw_accepted_url.startswith("blob:")
                    and (
                        self.checkpoint is None
                        or self.platform in {"shipinhao", "xiaohongshu"}
                    )
                ):
                    fallbacks.append(str(boundary))
                else:
                    return self._failure("COVER_RECEIPT_READBACK_FAILED", filled_fields=filled_fields)
            if self.checkpoint is not None and self.checkpoint.cover_receipts:
                prior_cover = self.checkpoint.cover_receipts[0]
                if cover_receipt is None:
                    return self._failure("COVER_RECEIPT_IDENTITY_MISMATCH", filled_fields=filled_fields)
                if (
                    prior_cover.accepted_url != cover_receipt.accepted_url
                    or prior_cover.task_space_id != cover_receipt.task_space_id
                ):
                    return self._failure("COVER_RECEIPT_IDENTITY_MISMATCH", filled_fields=filled_fields)
            if cover_receipt is not None:
                cover_receipts = [cover_receipt]
        if self.checkpoint is not None:
            await self._record_stage(
                PublishStage.MUTATE,
                identity=identity,
                media_sha=media_sha,
                upload_mode=UploadMode.RESUME_EXISTING if prior_upload else UploadMode.INJECTED,
                topic_entities=topic_evidence,
                cover_receipts=cover_receipts,
                fallback_boundaries=fallbacks,
            )
        if await _call_required(context, "request_final_action") is not False:
            return self._failure("FINAL_ACTION_BLOCKED", filled_fields=filled_fields)
        if await _call_required(context, "final_action_guard_armed") is not True:
            return self._failure("FINAL_ACTION_GUARD_NOT_ARMED", filled_fields=filled_fields)
        if self.checkpoint is not None:
            await self._record_stage(PublishStage.VERIFY, identity=identity, media_sha=media_sha, upload_mode=UploadMode.RESUME_EXISTING if prior_upload else UploadMode.INJECTED, final_guard=True)
        draft_url = await call_if_available(context, "current_url", default="")
        return PublishResult(
            status=PublishStatus.DRAFT_READY,
            platform=self.platform,
            message=f"{label}发布信息已自动填充，请在浏览器中检查预览，并由你亲自点击最终发布。",
            draft_url=str(draft_url or ""),
            requires_human_confirmation=True,
            filled_fields=filled_fields,
            adapter_state="waiting_for_human",
            adapter_version=self.adapter_version,
            readback_fields=readback_fields,
            platform_fallback_boundaries=fallbacks,
            media_readback="video" in readback_fields,
            cover_readback="cover" in readback_fields,
            cover_receipt_present=bool(cover_receipts),
            final_publish_click_count=0,
        )

    def _failure(self, message: str, *, filled_fields: list[str] | None = None) -> PublishResult:
        return PublishResult(
            status=PublishStatus.FAILED,
            platform=self.platform,
            message=message,
            requires_human_confirmation=True,
            filled_fields=filled_fields or [],
            adapter_state="needs_attention",
            adapter_version=self.adapter_version,
        )

    async def _record_stage(
        self,
        stage: PublishStage,
        *,
        identity: DraftIdentity,
        media_sha: str | None = None,
        upload_mode: UploadMode | None = None,
        final_guard: bool = False,
        topic_entities: list[TopicEntityEvidence] | None = None,
        cover_receipts: list[CoverReceipt] | None = None,
        fallback_boundaries: list[str] | None = None,
    ) -> None:
        if self.checkpoint is None or self.checkpoint_callback is None:
            return
        # A same-attempt resume re-inspects the live draft, but must not move
        # a durable checkpoint backwards (for example verify -> inspect) or
        # emit a CAS event whose stage no longer matches ``last_stage``.
        if stage in self.checkpoint.completed_stages:
            return
        data = self.checkpoint.model_dump(mode="json")
        data["draft_identity"] = identity.model_dump(mode="json")
        if media_sha:
            data["media_sha256"] = media_sha
        if upload_mode:
            data["upload_mode"] = upload_mode.value
        data["final_action_guard_armed"] = final_guard or bool(data.get("final_action_guard_armed"))
        if topic_entities is not None:
            data["topic_entities"] = [item.model_dump(mode="json") for item in topic_entities]
        if cover_receipts is not None:
            data["cover_receipts"] = [item.model_dump(mode="json") for item in cover_receipts]
        if fallback_boundaries is not None:
            data["platform_fallback_boundaries"] = list(dict.fromkeys(fallback_boundaries))
        completed = list(data.get("completed_stages") or [])
        if stage.value not in completed:
            completed.append(stage.value)
        data["completed_stages"] = completed
        data["last_stage"] = stage.value
        data["blocker_code"] = None
        data["blocked_stage"] = None
        self.checkpoint = PublishExecutionCheckpoint.model_validate(data)
        result = self.checkpoint_callback(self.checkpoint, stage, None)
        if inspect.isawaitable(result):
            await result


async def call_if_available(target: Any, method_name: str, *args: Any, default: Any = None) -> Any:
    method = getattr(target, method_name, None)
    if method is None:
        return default
    result = method(*args)
    if inspect.isawaitable(result):
        return await result
    return result


async def _call_required(target: Any, method_name: str, *args: Any) -> Any:
    method = getattr(target, method_name, None)
    if method is None:
        return None
    result = method(*args)
    if inspect.isawaitable(result):
        return await result
    return result


def _package_field_present(package: PublishPackage, field_name: str) -> bool:
    value = getattr(package, f"{field_name}_path", None) if field_name in {"video", "cover"} else getattr(package, field_name, None)
    if field_name == "hashtags":
        return bool(value)
    return bool(str(value or "").strip())


def _sha256_file(path: str) -> str | None:
    try:
        digest = hashlib.sha256()
        with Path(path).open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return f"sha256:{digest.hexdigest()}"
    except (OSError, ValueError):
        return None


def _same_platform_origin(actual_url: str, expected_url: str) -> bool:
    actual = urlsplit(actual_url)
    expected = urlsplit(expected_url)
    return bool(actual.scheme == "https" and actual.netloc and actual.netloc == expected.netloc)


def _remote_identity_digest(value: Any) -> str | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    return f"sha256:{hashlib.sha256(raw.encode('utf-8')).hexdigest()}"


def _topic_evidence(raw_entities: Any, expected_hashtags: list[str]) -> list[TopicEntityEvidence] | None:
    if not isinstance(raw_entities, list):
        return None
    parsed: dict[str, TopicEntityEvidence] = {}
    for raw in raw_entities:
        try:
            item = TopicEntityEvidence.model_validate(raw)
        except Exception:
            continue
        parsed[item.normalized_label.casefold().lstrip("#")] = item
    expected = [str(item).strip().lstrip("#").casefold() for item in expected_hashtags if str(item).strip()]
    if any(item not in parsed for item in expected):
        return None
    return [parsed[item] for item in expected]


def _cover_receipt_from_raw(
    cover_path: str,
    raw_receipt: Any,
    task_space: dict[str, Any],
) -> CoverReceipt | None:
    if not isinstance(raw_receipt, dict):
        return None
    digest = _sha256_file(cover_path)
    accepted_url = str(raw_receipt.get("accepted_url") or "").strip()
    if digest is None or not accepted_url:
        return None
    try:
        return CoverReceipt(
            slot=str(raw_receipt.get("slot") or "single"),
            ratio=str(raw_receipt.get("ratio") or "3:4"),
            asset_sha256=digest,
            asset_path_token=f"asset_cover_{digest.split(':', 1)[1][:16]}",
            before_urls=list(raw_receipt.get("before_urls") or []),
            accepted_url=accepted_url,
            task_space_id=raw_receipt.get("task_space_id") or task_space.get("id"),
            reused_existing=bool(raw_receipt.get("reused_existing", False)),
        )
    except (TypeError, ValueError):
        return None
