"""Read-only application result-history projection.

One AppRun becomes one user-facing record block.  Text candidates remain
inside that block, while carousel pages and digital-human attachments are
collapsed into one finished-product item.  This module never writes or
backfills domain rows.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
from collections import defaultdict
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any
from urllib.parse import quote

from pixelle_video.utils.os_util import get_data_path, get_output_path, get_temp_path

from .models import AppRun, Artifact, ArtifactVersion
from .repository import AppCenterRepository, NotFound

SUPPORTED_APPS: tuple[str, ...] = (
    "builtin.marketing-copy",
    "builtin.viral-titles",
    "builtin.douyin-carousel",
    "builtin.digital-human-video",
)
APP_PRESENTATION: dict[str, tuple[str, str]] = {
    "builtin.marketing-copy": ("门店营销文案", "multi_copy"),
    "builtin.viral-titles": ("爆款标题", "multi_title"),
    "builtin.douyin-carousel": ("抖音图文", "single_carousel"),
    "builtin.digital-human-video": ("数字人口播", "single_video"),
}
RESULT_SHAPES = frozenset(value[1] for value in APP_PRESENTATION.values())
APP_BY_SHAPE = {value[1]: app_id for app_id, value in APP_PRESENTATION.items()}
_RESULT_STATES = frozenset(
    {"queued", "running", "needs_review", "completed", "failed", "cancelled"}
)
_AVAILABLE_STATES = frozenset({"needs_review", "completed"})
_CURSOR_VERSION = 1
_CURSOR_SIGNING_KEY = hashlib.sha256(b"pixelle-video:app-result-history-v1:local-cursor").digest()
_CURSOR_SIGNATURE_BYTES = 16
_CURSOR_INVALID_MESSAGE = "历史记录位置已失效，请重新加载"
_MEDIA_TOKEN_VERSION = 1
_MEDIA_SIGNING_KEY = hashlib.sha256(b"pixelle-video:app-result-history-v1:media-version").digest()
_MEDIA_SIGNATURE_BYTES = 24
_MEDIA_TOKEN_MAX_LENGTH = 4096


@dataclass(frozen=True)
class ResultMediaFile:
    path: Path
    mime_type: str
    filename: str


class ResultHistoryError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def _clamp_text(value: Any, *, fallback: str, maximum: int) -> str:
    text = str(value or "").strip() or fallback
    return text[:maximum]


def _binding_digest(value: str | None) -> str:
    if value is None:
        return "-"
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


def _encode_cursor(payload: dict[str, Any]) -> str:
    body = json.dumps(
        {"v": _CURSOR_VERSION, **payload},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    signature = hmac.new(_CURSOR_SIGNING_KEY, body, hashlib.sha256).digest()[
        :_CURSOR_SIGNATURE_BYTES
    ]
    return base64.urlsafe_b64encode(body + signature).decode("ascii").rstrip("=")


def _decode_cursor(value: str) -> dict[str, Any]:
    try:
        padding = "=" * (-len(value) % 4)
        packed = base64.urlsafe_b64decode((value + padding).encode("ascii"))
        canonical = base64.urlsafe_b64encode(packed).decode("ascii").rstrip("=")
        if not hmac.compare_digest(canonical, value):
            raise ValueError("cursor encoding is not canonical")
        if len(packed) <= _CURSOR_SIGNATURE_BYTES:
            raise ValueError("cursor is too short")
        body = packed[:-_CURSOR_SIGNATURE_BYTES]
        signature = packed[-_CURSOR_SIGNATURE_BYTES:]
        expected = hmac.new(_CURSOR_SIGNING_KEY, body, hashlib.sha256).digest()[
            :_CURSOR_SIGNATURE_BYTES
        ]
        if not hmac.compare_digest(signature, expected):
            raise ValueError("cursor signature mismatch")
        payload = json.loads(body)
        if not isinstance(payload, dict) or payload.get("v") != _CURSOR_VERSION:
            raise ValueError("cursor version mismatch")
        return payload
    except (UnicodeError, ValueError, TypeError, json.JSONDecodeError) as exc:
        raise ResultHistoryError(
            "APP_RESULT_CURSOR_INVALID",
            _CURSOR_INVALID_MESSAGE,
        ) from exc


def _encode_media_binding(
    project_id: str,
    app_run_id: str,
    artifacts: list[Artifact],
) -> str:
    bindings = [
        [
            artifact.artifact_type,
            artifact.artifact_id,
            artifact.current_version_id,
        ]
        for artifact in sorted(
            artifacts,
            key=lambda item: (item.artifact_type, item.artifact_id),
        )
        if artifact.current_version_id
    ]
    body = json.dumps(
        {
            "v": _MEDIA_TOKEN_VERSION,
            "p": project_id,
            "r": app_run_id,
            "b": bindings,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    signature = hmac.new(_MEDIA_SIGNING_KEY, body, hashlib.sha256).digest()[:_MEDIA_SIGNATURE_BYTES]
    return base64.urlsafe_b64encode(body + signature).decode("ascii").rstrip("=")


def _decode_media_binding(value: str) -> dict[str, Any]:
    if not isinstance(value, str) or not value or len(value) > _MEDIA_TOKEN_MAX_LENGTH:
        raise ResultHistoryError(
            "RESULT_MEDIA_VERSION_INVALID",
            "成品版本凭证无效，请刷新生成记录",
        )
    try:
        padding = "=" * (-len(value) % 4)
        packed = base64.urlsafe_b64decode((value + padding).encode("ascii"))
        canonical = base64.urlsafe_b64encode(packed).decode("ascii").rstrip("=")
        if not hmac.compare_digest(canonical, value):
            raise ValueError("media token encoding is not canonical")
        if len(packed) <= _MEDIA_SIGNATURE_BYTES:
            raise ValueError("media token is too short")
        body = packed[:-_MEDIA_SIGNATURE_BYTES]
        signature = packed[-_MEDIA_SIGNATURE_BYTES:]
        expected = hmac.new(_MEDIA_SIGNING_KEY, body, hashlib.sha256).digest()[
            :_MEDIA_SIGNATURE_BYTES
        ]
        if not hmac.compare_digest(signature, expected):
            raise ValueError("media token signature mismatch")
        payload = json.loads(body)
        if not isinstance(payload, dict) or payload.get("v") != _MEDIA_TOKEN_VERSION:
            raise ValueError("media token version mismatch")
        return payload
    except (UnicodeError, ValueError, TypeError, json.JSONDecodeError) as exc:
        raise ResultHistoryError(
            "RESULT_MEDIA_VERSION_INVALID",
            "成品版本凭证无效，请刷新生成记录",
        ) from exc


def _version_for(
    artifact: Artifact | None,
    versions: dict[str, ArtifactVersion],
) -> ArtifactVersion | None:
    if artifact is None or not artifact.current_version_id:
        return None
    return versions.get(artifact.current_version_id)


def _file_ref_available(version: ArtifactVersion | None, kind: str) -> bool:
    if version is None:
        return False
    return any(
        isinstance(item, dict)
        and str(item.get("kind") or "").strip() == kind
        and bool(item.get("relative_path") or item.get("path"))
        for item in version.file_refs
    )


def _duration_seconds(
    run: AppRun,
    video_version: ArtifactVersion,
    spoken_version: ArtifactVersion | None,
) -> float | None:
    candidates: list[tuple[Any, float]] = []
    content = video_version.content if isinstance(video_version.content, dict) else {}
    candidates.extend(
        [
            (content.get("duration_seconds"), 1.0),
            (content.get("duration_ms"), 0.001),
            (run.input_payload.get("digital_human_duration"), 1.0),
        ]
    )
    for file_ref in video_version.file_refs:
        if isinstance(file_ref, dict):
            candidates.extend(
                [
                    (file_ref.get("duration_seconds"), 1.0),
                    (file_ref.get("duration_ms"), 0.001),
                ]
            )
    nested_human = run.input_payload.get("digital_human")
    if isinstance(nested_human, dict):
        source_asset = nested_human.get("source_asset")
        if isinstance(source_asset, dict):
            snapshot = source_asset.get("asset_snapshot")
            if isinstance(snapshot, dict):
                candidates.append((snapshot.get("duration_ms"), 0.001))
    for raw, multiplier in candidates:
        if isinstance(raw, bool):
            continue
        if isinstance(raw, (int, float)) and 0 < float(raw) * multiplier <= 3600:
            return round(float(raw) * multiplier, 3)
    if spoken_version and isinstance(spoken_version.content, dict):
        script = str(
            spoken_version.content.get("spoken_script") or spoken_version.content.get("text") or ""
        ).strip()
        if script:
            return round(min(3600.0, max(1.0, len(script) / 4.0)), 3)
    return None


def _digital_human_presentation(run: AppRun) -> tuple[str, str]:
    human = run.input_payload.get("digital_human")
    human = human if isinstance(human, dict) else {}
    voice = run.input_payload.get("voice")
    voice = voice if isinstance(voice, dict) else {}
    digital_human_name = str(
        human.get("display_name")
        or human.get("portrait_id")
        or "已选择数字人"
    ).strip()[:200]
    voice_name = str(
        voice.get("voice_name")
        or ("系统推荐男声" if voice.get("resolution_source") == "system_default" else "生成时固定声音")
    ).strip()[:200]
    return digital_human_name, voice_name


class ResultHistoryProjectionService:
    """Project existing result facts into stable, user-facing record blocks."""

    def __init__(self, repository: AppCenterRepository):
        self.repository = repository

    def list_records(
        self,
        project_id: str,
        *,
        scope: str = "current_app",
        app_id: str | None = None,
        result_shape: str | None = None,
        status: str | None = None,
        cursor: str | None = None,
        limit: int = 10,
    ) -> dict[str, Any]:
        if scope not in {"current_app", "all_results"}:
            raise ResultHistoryError(
                "RESULT_HISTORY_SCOPE_INVALID",
                "记录范围无效，请刷新后重试",
            )
        if scope == "current_app":
            if app_id not in SUPPORTED_APPS:
                raise ResultHistoryError(
                    "RESULT_HISTORY_APP_INVALID",
                    "当前应用无法读取生成记录",
                )
        elif app_id is not None:
            raise ResultHistoryError(
                "RESULT_HISTORY_APP_INVALID",
                "查看全部结果时不需要指定应用",
            )
        if result_shape is not None and result_shape not in RESULT_SHAPES:
            raise ResultHistoryError(
                "RESULT_HISTORY_SHAPE_INVALID",
                "结果类型无效，请刷新后重试",
            )
        if (
            scope == "current_app"
            and result_shape is not None
            and APP_BY_SHAPE[result_shape] != app_id
        ):
            raise ResultHistoryError(
                "RESULT_HISTORY_SHAPE_INVALID",
                "结果类型与当前应用不一致",
            )
        if status is not None and status not in _RESULT_STATES:
            raise ResultHistoryError(
                "RESULT_HISTORY_STATUS_INVALID",
                "记录状态无效，请刷新后重试",
            )
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 20:
            raise ResultHistoryError(
                "RESULT_HISTORY_LIMIT_INVALID",
                "每页记录数量必须在 1 到 20 之间",
            )

        before_sort_at: str | None = None
        before_run_id: str | None = None
        expected_revision: str | None = None
        if cursor:
            if len(cursor) > 256:
                raise ResultHistoryError(
                    "APP_RESULT_CURSOR_INVALID",
                    _CURSOR_INVALID_MESSAGE,
                )
            payload = _decode_cursor(cursor)
            expected = {
                "p": _binding_digest(project_id),
                "s": "c" if scope == "current_app" else "a",
                "a": _binding_digest(app_id),
                "h": _binding_digest(result_shape),
                "j": _binding_digest(status),
            }
            if any(payload.get(key) != value for key, value in expected.items()):
                raise ResultHistoryError(
                    "APP_RESULT_CURSOR_INVALID",
                    _CURSOR_INVALID_MESSAGE,
                )
            before_sort_at = payload.get("t")
            before_run_id = payload.get("r")
            expected_revision = payload.get("q")
            if (
                not isinstance(before_sort_at, str)
                or not isinstance(before_run_id, str)
                or not isinstance(expected_revision, str)
            ):
                raise ResultHistoryError(
                    "APP_RESULT_CURSOR_INVALID",
                    _CURSOR_INVALID_MESSAGE,
                )

        effective_app_ids = (
            (APP_BY_SHAPE[result_shape],) if result_shape is not None else SUPPORTED_APPS
        )
        rows, revision = self.repository.list_result_history_runs(
            project_id,
            app_ids=effective_app_ids,
            app_id=app_id if scope == "current_app" else None,
            statuses=(status,) if status is not None else None,
            before_sort_at=before_sort_at,
            before_app_run_id=before_run_id,
            limit=limit + 1,
        )
        revision_digest = _binding_digest(revision)
        if expected_revision is not None and expected_revision != revision_digest:
            raise ResultHistoryError(
                "APP_RESULT_CURSOR_STALE",
                "生成记录已更新，请刷新后继续查看",
            )
        has_more = len(rows) > limit
        page_rows = rows[:limit]
        runs = [run for run, _sort_at in page_rows]
        output_ids = [artifact_id for run in runs for artifact_id in run.output_artifact_ids]
        artifacts = self.repository.list_result_history_artifacts(
            project_id,
            app_run_ids=[run.app_run_id for run in runs],
            output_artifact_ids=output_ids,
        )
        versions = self.repository.get_result_history_versions(
            project_id,
            [item.current_version_id for item in artifacts if item.current_version_id],
        )
        records = self._project_records(runs, artifacts, versions)

        next_cursor = None
        if has_more and page_rows:
            last_run, last_sort_at = page_rows[-1]
            next_cursor = _encode_cursor(
                {
                    "p": _binding_digest(project_id),
                    "s": "c" if scope == "current_app" else "a",
                    "a": _binding_digest(app_id),
                    "h": _binding_digest(result_shape),
                    "j": _binding_digest(status),
                    "q": revision_digest,
                    "t": last_sort_at,
                    "r": last_run.app_run_id,
                }
            )
        return {
            "schema_version": 1,
            "project_id": project_id,
            "scope": scope,
            "app_id": app_id if scope == "current_app" else None,
            "records": records,
            "next_cursor": next_cursor,
        }

    def _project_records(
        self,
        runs: list[AppRun],
        artifacts: list[Artifact],
        versions: dict[str, ArtifactVersion],
    ) -> list[dict[str, Any]]:
        artifacts_by_run: dict[str, list[Artifact]] = defaultdict(list)
        run_by_output_id: dict[str, str] = {}
        for run in runs:
            for artifact_id in run.output_artifact_ids:
                run_by_output_id[artifact_id] = run.app_run_id
        for artifact in artifacts:
            owner = artifact.source_app_run_id or run_by_output_id.get(artifact.artifact_id)
            if owner:
                artifacts_by_run[owner].append(artifact)
        return [
            self._project_record(run, artifacts_by_run.get(run.app_run_id, []), versions)
            for run in runs
        ]

    def _project_record(
        self,
        run: AppRun,
        artifacts: list[Artifact],
        versions: dict[str, ArtifactVersion],
    ) -> dict[str, Any]:
        app_name, result_shape = APP_PRESENTATION[run.app_id]
        status = run.state if run.state in _RESULT_STATES else "failed"
        base = {
            "schema_version": 1,
            "record_id": run.app_run_id,
            "app_run_id": run.app_run_id,
            "project_id": run.project_id,
            "app_id": run.app_id,
            "app_name": app_name,
            "result_shape": result_shape,
            "status": status,
            "created_at": run.created_at,
            "result_available_at": (
                run.completed_at or run.updated_at if status in _AVAILABLE_STATES else None
            ),
            "summary": self._pending_summary(run, app_name),
            "compatibility": {"state": "normal"},
            "items": [],
        }
        if status not in _AVAILABLE_STATES:
            return base
        try:
            if run.app_id == "builtin.marketing-copy":
                summary, items = self._copy_items(artifacts, versions)
            elif run.app_id == "builtin.viral-titles":
                summary, items = self._title_items(artifacts, versions)
            elif run.app_id == "builtin.douyin-carousel":
                summary, items = self._carousel_items(run, artifacts, versions)
            else:
                summary, items = self._video_items(run, artifacts, versions)
            if not items:
                raise ValueError("result has no displayable items")
            base["summary"] = summary
            base["items"] = items
            return base
        except (KeyError, TypeError, ValueError):
            base["summary"] = f"{app_name}历史结果"
            base["compatibility"] = {
                "state": "legacy_unavailable",
                "unavailable_reason": "这条旧记录暂时无法预览",
            }
            base["items"] = []
            return base

    @staticmethod
    def _pending_summary(run: AppRun, app_name: str) -> str:
        if run.state == "failed":
            return "本次生成失败，可按原输入重试"
        if run.state == "cancelled":
            return "本次生成已取消"
        if run.state in {"queued", "running"}:
            return f"正在生成{app_name}"
        return f"{app_name}生成结果"

    @staticmethod
    def _artifacts_by_type(artifacts: list[Artifact]) -> dict[str, Artifact]:
        result: dict[str, Artifact] = {}
        for artifact in artifacts:
            result.setdefault(artifact.artifact_type, artifact)
        return result

    def _copy_items(
        self,
        artifacts: list[Artifact],
        versions: dict[str, ArtifactVersion],
    ) -> tuple[str, list[dict[str, Any]]]:
        artifact = self._artifacts_by_type(artifacts).get("copywriting")
        version = _version_for(artifact, versions)
        content = version.content if version and isinstance(version.content, dict) else {}
        variants = content.get("variants")
        if not isinstance(variants, list) or not variants:
            raise ValueError("copy variants unavailable")
        items: list[dict[str, Any]] = []
        for index, candidate in enumerate(variants):
            if not isinstance(candidate, dict):
                raise ValueError("copy candidate invalid")
            text = str(
                candidate.get("full_text")
                or " ".join(
                    str(candidate.get(key) or "").strip() for key in ("hook", "body", "cta")
                )
            ).strip()
            if not text:
                raise ValueError("copy candidate text unavailable")
            if len(text) > 5000:
                raise ValueError("copy candidate exceeds the safe display contract")
            label = _clamp_text(
                candidate.get("label"),
                fallback=f"文案 {index + 1}",
                maximum=30,
            )
            items.append(
                {
                    "item_id": (
                        f"{artifact.artifact_id}:{version.artifact_version_id}:{index + 1}"
                    ),
                    "kind": "copy",
                    "label": label,
                    "text": text,
                    "actions": ["copy", "edit", "select"],
                }
            )
        return f"本次生成 {len(items)} 条文案", items

    def _title_items(
        self,
        artifacts: list[Artifact],
        versions: dict[str, ArtifactVersion],
    ) -> tuple[str, list[dict[str, Any]]]:
        artifact = self._artifacts_by_type(artifacts).get("title_set")
        version = _version_for(artifact, versions)
        content = version.content if version and isinstance(version.content, dict) else {}
        candidates = content.get("candidates")
        if not isinstance(candidates, list) or not candidates:
            raise ValueError("title candidates unavailable")
        selected_indices: set[int] = set()
        for selected_artifact in artifacts:
            if selected_artifact.artifact_type != "selected_title":
                continue
            selected_version = _version_for(selected_artifact, versions)
            selected_content = (
                selected_version.content
                if selected_version and isinstance(selected_version.content, dict)
                else {}
            )
            if (
                selected_content.get("source_title_set_artifact_id") == artifact.artifact_id
                and selected_content.get("source_title_set_version_id")
                == version.artifact_version_id
            ):
                selected_index = selected_content.get("selected_index")
                if isinstance(selected_index, int) and not isinstance(selected_index, bool):
                    selected_indices.add(selected_index)
        items: list[dict[str, Any]] = []
        for index, candidate in enumerate(candidates):
            if not isinstance(candidate, dict):
                raise ValueError("title candidate invalid")
            text = str(candidate.get("title") or "").strip()
            if not text:
                raise ValueError("title candidate text unavailable")
            if len(text) > 200:
                raise ValueError("title candidate exceeds the safe display contract")
            items.append(
                {
                    "item_id": (
                        f"{artifact.artifact_id}:{version.artifact_version_id}:{index + 1}"
                    ),
                    "kind": "title",
                    "label": _clamp_text(
                        candidate.get("label"),
                        fallback=f"标题 {index + 1}",
                        maximum=30,
                    ),
                    "text": text,
                    "actions": ["copy", "edit", "select"],
                    "selected": index in selected_indices,
                }
            )
        return f"本次生成 {len(items)} 个标题", items

    def _carousel_items(
        self,
        run: AppRun,
        artifacts: list[Artifact],
        versions: dict[str, ArtifactVersion],
    ) -> tuple[str, list[dict[str, Any]]]:
        by_type = self._artifacts_by_type(artifacts)
        package = by_type.get("carousel_package")
        version = _version_for(package, versions)
        content = version.content if version and isinstance(version.content, dict) else {}
        page_count = content.get("page_count")
        if (
            package is None
            or version is None
            or isinstance(page_count, bool)
            or not isinstance(page_count, int)
            or not 1 <= page_count <= 100
            or not _file_ref_available(version, "image")
        ):
            raise ValueError("carousel product unavailable")
        title = _clamp_text(content.get("title") or package.name, fallback="抖音图文", maximum=80)
        missing_facts = [
            _clamp_text(item, fallback="", maximum=200)
            for item in content.get("missing_facts") or []
            if str(item).strip()
        ][:20]
        bound_artifacts = [
            artifact
            for artifact in artifacts
            if artifact.artifact_type in {"carousel_package", "publish_copy"}
        ]
        version_token = _encode_media_binding(run.project_id, run.app_run_id, bound_artifacts)
        version_query = f"?version={quote(version_token, safe='-_')}"
        root = (
            f"/api/content-projects/{quote(run.project_id, safe='')}"
            f"/result-records/{quote(run.app_run_id, safe='')}"
        )
        details = ["pages"]
        if by_type.get("publish_copy"):
            details.append("publish_copy")
        return title, [
            {
                "item_id": package.artifact_id,
                "kind": "carousel",
                "title": title,
                "cover_url": f"{root}/cover{version_query}",
                "preview_url": f"{root}/preview{version_query}",
                "download_url": f"{root}/download{version_query}",
                "page_count": page_count,
                "missing_facts": missing_facts,
                "actions": ["preview", "publish"],
                "details_available": details,
                "artifact_version_ids": [
                    artifact.current_version_id
                    for artifact in bound_artifacts
                    if artifact.current_version_id
                ],
            }
        ]

    def _video_items(
        self,
        run: AppRun,
        artifacts: list[Artifact],
        versions: dict[str, ArtifactVersion],
    ) -> tuple[str, list[dict[str, Any]]]:
        by_type = self._artifacts_by_type(artifacts)
        video = by_type.get("video")
        cover = by_type.get("cover")
        publish_copy = by_type.get("publish_copy")
        spoken = by_type.get("spoken_script")
        video_version = _version_for(video, versions)
        cover_version = _version_for(cover, versions)
        publish_version = _version_for(publish_copy, versions)
        spoken_version = _version_for(spoken, versions)
        if (
            video is None
            or video_version is None
            or not _file_ref_available(video_version, "video")
            or not _file_ref_available(cover_version, "cover")
        ):
            raise ValueError("video product unavailable")
        duration = _duration_seconds(run, video_version, spoken_version)
        if duration is None:
            raise ValueError("video duration unavailable")
        publish_content = (
            publish_version.content
            if publish_version and isinstance(publish_version.content, dict)
            else {}
        )
        title = _clamp_text(
            publish_content.get("title") or video.name,
            fallback="数字人口播",
            maximum=80,
        )
        bound_artifacts = [
            artifact
            for artifact in artifacts
            if artifact.artifact_type in {"video", "cover", "publish_copy", "spoken_script"}
        ]
        version_token = _encode_media_binding(run.project_id, run.app_run_id, bound_artifacts)
        version_query = f"?version={quote(version_token, safe='-_')}"
        root = (
            f"/api/content-projects/{quote(run.project_id, safe='')}"
            f"/result-records/{quote(run.app_run_id, safe='')}"
        )
        details = ["cover"]
        if publish_version:
            details.append("publish_copy")
        if spoken_version:
            details.append("spoken_script")
        details.append("download")
        digital_human_name, voice_name = _digital_human_presentation(run)
        return title, [
            {
                "item_id": video.artifact_id,
                "kind": "video",
                "title": title,
                "poster_url": f"{root}/poster{version_query}",
                "playback_url": f"{root}/play{version_query}",
                "preview_url": f"{root}/preview{version_query}",
                "download_url": f"{root}/download{version_query}",
                "duration_seconds": duration,
                "digital_human_name": digital_human_name,
                "voice_name": voice_name,
                "actions": ["play", "publish"],
                "details_available": details,
                "artifact_version_ids": [
                    artifact.current_version_id
                    for artifact in bound_artifacts
                    if artifact.current_version_id
                ],
            }
        ]


class ResultHistoryMediaService:
    """Resolve one AppRun's finished media without starting new work.

    The service only reads the current immutable artifact versions selected by
    the record projection. File paths stay behind controlled HTTP endpoints;
    callers receive business metadata and relative media URLs only.
    """

    def __init__(
        self,
        repository: AppCenterRepository,
        *,
        media_roots: dict[str, str | Path] | None = None,
    ):
        self.repository = repository
        configured = media_roots or {
            "data": get_data_path(),
            "output": get_output_path(),
            "temp": get_temp_path(),
            "carousel": get_data_path("app_center", "carousel"),
        }
        self.media_roots = {
            name: Path(path).expanduser().resolve() for name, path in configured.items()
        }

    def get_preview(
        self,
        project_id: str,
        app_run_id: str,
        *,
        version_token: str,
    ) -> dict[str, Any]:
        run, artifacts, versions = self._load_record(
            project_id,
            app_run_id,
            version_token=version_token,
        )
        by_type = ResultHistoryProjectionService._artifacts_by_type(artifacts)
        version_query = f"?version={quote(version_token, safe='-_')}"
        root = (
            f"/api/content-projects/{quote(project_id, safe='')}"
            f"/result-records/{quote(app_run_id, safe='')}"
        )
        if run.app_id == "builtin.douyin-carousel":
            package = by_type.get("carousel_package")
            package_version = _version_for(package, versions)
            if package is None or package_version is None:
                raise ResultHistoryError(
                    "RESULT_MEDIA_UNAVAILABLE",
                    "这组图文暂时无法预览",
                )
            content = package_version.content if isinstance(package_version.content, dict) else {}
            page_refs = self._carousel_page_refs(package_version)
            page_count = content.get("page_count")
            if (
                isinstance(page_count, bool)
                or not isinstance(page_count, int)
                or page_count != len(page_refs)
            ):
                raise ResultHistoryError(
                    "RESULT_MEDIA_UNAVAILABLE",
                    "这组图文页面不完整，仍可稍后重试",
                )
            for page_ref in page_refs:
                self._resolve_ref(page_ref, default_root="carousel")
            download_ref = self._find_file_ref(package_version, "zip")
            if download_ref is None:
                raise ResultHistoryError(
                    "RESULT_MEDIA_UNAVAILABLE",
                    "这组图文下载包暂时不可用",
                )
            self._resolve_ref(download_ref, default_root="carousel")
            title = _clamp_text(
                content.get("title") or package.name,
                fallback="抖音图文",
                maximum=80,
            )
            return {
                "schema_version": 1,
                "kind": "carousel",
                "record_id": run.app_run_id,
                "title": title,
                "page_count": page_count,
                "pages": [
                    {
                        "page_index": index,
                        "image_url": f"{root}/pages/{index}{version_query}",
                        "download_url": f"{root}/pages/{index}{version_query}",
                    }
                    for index in range(1, page_count + 1)
                ],
                "publish_copy": (
                    self._publish_copy(by_type, versions) or self._carousel_publish_copy(content)
                ),
                "download_url": f"{root}/download{version_query}",
            }
        if run.app_id == "builtin.digital-human-video":
            video = by_type.get("video")
            cover = by_type.get("cover")
            video_version = _version_for(video, versions)
            cover_version = _version_for(cover, versions)
            if video is None or video_version is None or cover is None or cover_version is None:
                raise ResultHistoryError(
                    "RESULT_MEDIA_UNAVAILABLE",
                    "这条视频暂时无法播放",
                )
            if self._find_file_ref(video_version, "video") is None:
                raise ResultHistoryError(
                    "RESULT_MEDIA_UNAVAILABLE",
                    "这条视频文件暂时不可用",
                )
            if self._find_file_ref(cover_version, "cover", "image") is None:
                raise ResultHistoryError(
                    "RESULT_MEDIA_UNAVAILABLE",
                    "这条视频封面暂时不可用",
                )
            self._resolve_ref(self._find_file_ref(video_version, "video"))
            self._resolve_ref(self._find_file_ref(cover_version, "cover", "image"))
            publish_copy = self._publish_copy(by_type, versions)
            spoken = _version_for(by_type.get("spoken_script"), versions)
            duration = _duration_seconds(run, video_version, spoken)
            if duration is None:
                raise ResultHistoryError(
                    "RESULT_MEDIA_UNAVAILABLE",
                    "这条视频时长信息不完整",
                )
            return {
                "schema_version": 1,
                "kind": "video",
                "record_id": run.app_run_id,
                "title": _clamp_text(
                    (publish_copy or {}).get("title") or video.name,
                    fallback="数字人口播",
                    maximum=80,
                ),
                "duration_seconds": duration,
                "poster_url": f"{root}/poster{version_query}",
                "playback_url": f"{root}/play{version_query}",
                "download_url": f"{root}/download{version_query}",
                "publish_copy": publish_copy,
            }
        raise ResultHistoryError(
            "RESULT_MEDIA_UNSUPPORTED",
            "当前记录不是可预览的媒体成品",
        )

    def get_file(
        self,
        project_id: str,
        app_run_id: str,
        *,
        slot: str,
        page_index: int | None = None,
        version_token: str,
    ) -> ResultMediaFile:
        run, artifacts, versions = self._load_record(
            project_id,
            app_run_id,
            version_token=version_token,
        )
        by_type = ResultHistoryProjectionService._artifacts_by_type(artifacts)
        if run.app_id == "builtin.douyin-carousel":
            package = by_type.get("carousel_package")
            version = _version_for(package, versions)
            if package is None or version is None:
                raise ResultHistoryError("RESULT_MEDIA_UNAVAILABLE", "这组图文暂时无法预览")
            pages = self._carousel_page_refs(version)
            if slot == "cover":
                target = pages[0] if pages else None
            elif slot == "page" and page_index is not None and 1 <= page_index <= len(pages):
                target = pages[page_index - 1]
            elif slot == "download":
                target = self._find_file_ref(version, "zip")
            else:
                target = None
            if target is None:
                raise ResultHistoryError("RESULT_MEDIA_UNAVAILABLE", "这组图文文件暂时不可用")
            return self._resolve_ref(target, default_root="carousel")

        if run.app_id == "builtin.digital-human-video":
            artifact_type = "cover" if slot == "poster" else "video"
            artifact = by_type.get(artifact_type)
            version = _version_for(artifact, versions)
            if artifact is None or version is None:
                raise ResultHistoryError("RESULT_MEDIA_UNAVAILABLE", "这条视频文件暂时不可用")
            if slot == "poster":
                target = self._find_file_ref(version, "cover", "image")
            elif slot in {"play", "download"}:
                target = self._find_file_ref(version, "video")
            else:
                target = None
            if target is None:
                raise ResultHistoryError("RESULT_MEDIA_UNAVAILABLE", "这条视频文件暂时不可用")
            return self._resolve_ref(target)
        raise ResultHistoryError(
            "RESULT_MEDIA_UNSUPPORTED",
            "当前记录不是可预览的媒体成品",
        )

    def _load_record(
        self,
        project_id: str,
        app_run_id: str,
        *,
        version_token: str,
    ) -> tuple[AppRun, list[Artifact], dict[str, ArtifactVersion]]:
        try:
            self.repository.get_project(project_id)
            run = self.repository.get_app_run(app_run_id)
        except NotFound as exc:
            raise ResultHistoryError("RESULT_MEDIA_NOT_FOUND", "这条生成记录不存在") from exc
        if run.project_id != project_id or run.archived_at is not None:
            raise ResultHistoryError("RESULT_MEDIA_NOT_FOUND", "这条生成记录不存在")
        if run.state not in _AVAILABLE_STATES:
            raise ResultHistoryError("RESULT_MEDIA_NOT_READY", "成品仍在生成，请稍后再看")
        if run.app_id not in {"builtin.douyin-carousel", "builtin.digital-human-video"}:
            raise ResultHistoryError(
                "RESULT_MEDIA_UNSUPPORTED",
                "当前记录不是可预览的媒体成品",
            )
        artifacts = self.repository.list_result_history_artifacts(
            project_id,
            app_run_ids=[run.app_run_id],
            output_artifact_ids=run.output_artifact_ids,
        )
        payload = _decode_media_binding(version_token)
        if payload.get("p") != project_id or payload.get("r") != app_run_id:
            raise ResultHistoryError(
                "RESULT_MEDIA_VERSION_INVALID",
                "成品版本凭证与当前记录不匹配，请刷新生成记录",
            )
        raw_bindings = payload.get("b")
        if not isinstance(raw_bindings, list) or not raw_bindings:
            raise ResultHistoryError(
                "RESULT_MEDIA_VERSION_INVALID",
                "成品版本凭证无效，请刷新生成记录",
            )
        artifacts_by_id = {artifact.artifact_id: artifact for artifact in artifacts}
        binding_by_artifact_id: dict[str, str] = {}
        for raw_binding in raw_bindings:
            if (
                not isinstance(raw_binding, list)
                or len(raw_binding) != 3
                or not all(isinstance(value, str) and value for value in raw_binding)
            ):
                raise ResultHistoryError(
                    "RESULT_MEDIA_VERSION_INVALID",
                    "成品版本凭证无效，请刷新生成记录",
                )
            artifact_type, artifact_id, version_id = raw_binding
            artifact = artifacts_by_id.get(artifact_id)
            if artifact is None or artifact.artifact_type != artifact_type:
                raise ResultHistoryError(
                    "RESULT_MEDIA_VERSION_INVALID",
                    "成品版本已经不可用，请刷新生成记录",
                )
            binding_by_artifact_id[artifact_id] = version_id
        versions = self.repository.get_result_history_versions(
            project_id,
            list(binding_by_artifact_id.values()),
        )
        pinned_artifacts: list[Artifact] = []
        for artifact_id, version_id in binding_by_artifact_id.items():
            version = versions.get(version_id)
            if version is None or version.artifact_id != artifact_id:
                raise ResultHistoryError(
                    "RESULT_MEDIA_VERSION_INVALID",
                    "成品版本已经不可用，请刷新生成记录",
                )
            pinned_artifacts.append(
                replace(artifacts_by_id[artifact_id], current_version_id=version_id)
            )
        return run, pinned_artifacts, versions

    @staticmethod
    def _find_file_ref(
        version: ArtifactVersion,
        *kinds: str,
    ) -> dict[str, Any] | None:
        allowed = set(kinds)
        return next(
            (
                item
                for item in version.file_refs
                if isinstance(item, dict)
                and str(item.get("kind") or "").strip() in allowed
                and bool(item.get("relative_path") or item.get("path"))
            ),
            None,
        )

    def _carousel_page_refs(self, version: ArtifactVersion) -> list[dict[str, Any]]:
        refs = [
            item
            for item in version.file_refs
            if isinstance(item, dict)
            and item.get("kind") == "image"
            and isinstance(item.get("page_index"), int)
        ]
        refs.sort(key=lambda item: (int(item["page_index"]), str(item.get("file_key") or "")))
        expected = list(range(1, len(refs) + 1))
        if [int(item["page_index"]) for item in refs] != expected:
            return []
        return refs

    @staticmethod
    def _publish_copy(
        by_type: dict[str, Artifact],
        versions: dict[str, ArtifactVersion],
    ) -> dict[str, Any] | None:
        version = _version_for(by_type.get("publish_copy"), versions)
        if version is None or not isinstance(version.content, dict):
            return None
        content = version.content
        title = str(content.get("title") or "").strip()
        description = str(content.get("description") or "").strip()
        hashtags = content.get("hashtags")
        return {
            "title": title[:80],
            "description": description[:2000],
            "hashtags": [str(item).strip()[:30] for item in hashtags if str(item).strip()][:20]
            if isinstance(hashtags, list)
            else [],
        }

    @staticmethod
    def _carousel_publish_copy(content: dict[str, Any]) -> dict[str, Any] | None:
        explicit_title = str(content.get("publish_title") or "").strip()
        description = str(
            content.get("publish_description") or content.get("description") or ""
        ).strip()
        raw_hashtags = content.get("hashtags")
        hashtags = (
            [str(item).strip().lstrip("#")[:30] for item in raw_hashtags if str(item).strip()][:20]
            if isinstance(raw_hashtags, list)
            else []
        )
        if not explicit_title and not description and not hashtags:
            return None
        title = explicit_title or str(content.get("title") or "").strip()
        return {
            "title": title[:80],
            "description": description[:2000],
            "hashtags": hashtags,
        }

    def _resolve_ref(
        self,
        file_ref: dict[str, Any],
        *,
        default_root: str | None = None,
    ) -> ResultMediaFile:
        raw_path = file_ref.get("relative_path") or file_ref.get("path")
        if not isinstance(raw_path, str) or not raw_path.strip():
            raise ResultHistoryError("RESULT_MEDIA_UNAVAILABLE", "成品文件暂时不可用")
        candidate = Path(raw_path).expanduser()
        root_name = str(file_ref.get("root") or default_root or "").strip().lower()
        if candidate.is_absolute():
            resolved = candidate.resolve()
            if not any(self._within(resolved, root) for root in self.media_roots.values()):
                raise ResultHistoryError("RESULT_MEDIA_FORBIDDEN", "成品文件位置无效")
        else:
            root = self.media_roots.get(root_name)
            if root is None:
                raise ResultHistoryError("RESULT_MEDIA_FORBIDDEN", "成品文件位置无效")
            resolved = (root / candidate).resolve()
            if not self._within(resolved, root):
                raise ResultHistoryError("RESULT_MEDIA_FORBIDDEN", "成品文件位置无效")
        if not resolved.is_file():
            raise ResultHistoryError("RESULT_MEDIA_UNAVAILABLE", "成品文件暂时不可用")
        return ResultMediaFile(
            path=resolved,
            mime_type=str(file_ref.get("mime_type") or "application/octet-stream"),
            filename=str(file_ref.get("file_key") or resolved.name),
        )

    @staticmethod
    def _within(path: Path, root: Path) -> bool:
        try:
            path.relative_to(root)
            return True
        except ValueError:
            return False
