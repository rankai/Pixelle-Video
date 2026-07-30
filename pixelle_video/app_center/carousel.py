"""Deterministic first-party renderer for the AC-4 Douyin carousel app.

The renderer is deliberately local and bounded: it consumes trusted asset
references resolved by the caller, renders fixed 3:4 PNG pages, and emits a
deterministic ZIP manifest. It never opens a browser or calls a platform.
"""

from __future__ import annotations

import hashlib
import zipfile
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Callable

from PIL import Image, ImageColor, ImageDraw, ImageFont, ImageOps, UnidentifiedImageError
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from pixelle_video.services.font_registry import resolve_font_path
from pixelle_video.utils.os_util import get_data_path

from .brand_project import ProjectContextResolver
from .llm_port import AppLLMPort, AppLLMPortError, StructuredGenerationRequest
from .models import AppRun
from .repository import AppCenterRepository, NotFound
from .runner import AppExecutor, ExecutorOutput, RelatedArtifactOutput
from .style_presets import StylePreset, StylePresetError, resolve_style_preset

CAROUSEL_APP_ID = "builtin.douyin-carousel"
CAROUSEL_APP_VERSION = "1.0.0"
CAROUSEL_SCHEMA_VERSION = 1
CAROUSEL_WIDTH = 1080
CAROUSEL_HEIGHT = 1440
ALLOWED_PAGE_COUNTS = frozenset({3, 5, 8})
MAX_TEXT_LINES = 10
MAX_TEXT_CHARS = 480
CAROUSEL_PROMPT_VERSION = "ac4-carousel-plan-v1"
CAROUSEL_PROMPT_VERSION_V2 = "app-workbench-carousel-v2"


class CarouselRenderError(ValueError):
    """Stable, user-visible renderer failure."""

    def __init__(self, code: str, message: str, *, page_index: int | None = None):
        super().__init__(message)
        self.code = code
        self.page_index = page_index


AssetResolver = Callable[[str], str | Path | None]


class CarouselPlanPage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    page_index: int = Field(ge=1, le=8)
    purpose: str = Field(min_length=1, max_length=40)
    text: str = Field(min_length=1, max_length=MAX_TEXT_CHARS)
    asset_ref: str = Field(min_length=1, max_length=300)


class CarouselPlanOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    page_count: int
    template_id: str = Field(min_length=1, max_length=100)
    pages: list[CarouselPlanPage]
    missing_facts: list[str] = Field(default_factory=list, max_length=20)


@dataclass(frozen=True)
class RenderedPage:
    page_index: int
    path: Path
    sha256: str
    size_bytes: int

    def file_ref(self, root: Path) -> dict[str, Any]:
        return {
            "file_key": f"page-{self.page_index:02d}.png",
            "relative_path": str(self.path.resolve().relative_to(root.resolve())),
            "kind": "image",
            "mime_type": "image/png",
            "sha256": f"sha256:{self.sha256}",
            "size_bytes": self.size_bytes,
            "width": CAROUSEL_WIDTH,
            "height": CAROUSEL_HEIGHT,
            "page_index": self.page_index,
        }


class DouyinCarouselRenderer:
    """Render fixed-size pages and a deterministic ZIP export."""

    def __init__(
        self,
        output_root: str | Path | None = None,
        *,
        asset_resolver: AssetResolver | None = None,
        asset_root: str | Path | None = None,
    ):
        self.output_root = Path(output_root or get_data_path("app_center", "carousel")).resolve()
        self.asset_resolver = asset_resolver
        self.asset_root = Path(asset_root).resolve() if asset_root else None

    def render_page(
        self,
        page: dict[str, Any],
        output_dir: str | Path,
        *,
        version_label: str | None = None,
        brand_render: dict[str, Any] | None = None,
    ) -> RenderedPage:
        page_index = page.get("page_index")
        if not isinstance(page_index, int) or page_index < 1:
            raise CarouselRenderError(
                "PAGE_INDEX_INVALID", "页码必须是正整数", page_index=page_index
            )
        dimensions = page.get("dimensions") or {
            "width_px": CAROUSEL_WIDTH,
            "height_px": CAROUSEL_HEIGHT,
        }
        if dimensions != {"width_px": CAROUSEL_WIDTH, "height_px": CAROUSEL_HEIGHT}:
            raise CarouselRenderError(
                "DIMENSIONS_NOT_3_4", "图文页必须使用 1080×1440（3:4）", page_index=page_index
            )
        text = str(page.get("text") or "").strip()
        if not text:
            raise CarouselRenderError("TEXT_REQUIRED", "图文页文案不能为空", page_index=page_index)
        if len(text) > MAX_TEXT_CHARS:
            raise CarouselRenderError(
                "TEXT_OVERFLOW", "图文页文案超出首期模板容量", page_index=page_index
            )

        font_id = str(page.get("font_id") or "noto-sans-sc-bold")
        font_path = resolve_font_path(font_id)
        if not font_path:
            raise CarouselRenderError(
                "FONT_MISSING", f"字体不可用：{font_id}", page_index=page_index
            )
        font_size = int(page.get("font_size") or 64)
        try:
            font = ImageFont.truetype(str(font_path), font_size)
        except OSError as exc:
            raise CarouselRenderError(
                "FONT_MISSING", f"字体加载失败：{font_id}", page_index=page_index
            ) from exc

        brand_render = brand_render or {}
        primary_color = _safe_color(brand_render.get("primary_color"), (31, 41, 55))
        secondary_color = _safe_color(brand_render.get("secondary_color"), (248, 245, 238))
        image = Image.new("RGB", (CAROUSEL_WIDTH, CAROUSEL_HEIGHT), secondary_color)
        self._draw_asset(image, page, page_index)
        # The asset canvas is RGB; passing a 4-tuple to ImageDraw on it ignores
        # alpha and paints an opaque rectangle over the source image. Composite
        # a translucent tint explicitly so the selected enterprise asset remains
        # visible while the copy remains readable.
        overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
        overlay_draw = ImageDraw.Draw(overlay)
        overlay_draw.rectangle((0, 155, CAROUSEL_WIDTH, 775), fill=(*secondary_color, 120))
        image = Image.alpha_composite(image.convert("RGBA"), overlay).convert("RGB")
        draw = ImageDraw.Draw(image)
        draw.rectangle((0, 0, CAROUSEL_WIDTH, 155), fill=primary_color)
        brand_name = str(brand_render.get("display_name") or "抖音图文")
        draw.text((72, 52), brand_name, fill=(255, 255, 255), font=font)
        self._draw_brand_logo(image, brand_render)

        lines = _wrap_text(draw, text, font, max_width=CAROUSEL_WIDTH - 144)
        if len(lines) > MAX_TEXT_LINES:
            raise CarouselRenderError(
                "TEXT_OVERFLOW", "图文页文案行数超出模板容量", page_index=page_index
            )
        line_height = font_size + 24
        start_y = 480
        for line_number, line in enumerate(lines):
            draw.text((72, start_y + line_number * line_height), line, fill=(17, 24, 39), font=font)
        draw.text((72, CAROUSEL_HEIGHT - 100), f"{page_index:02d}", fill=(107, 114, 128), font=font)

        output_dir_path = Path(output_dir).resolve()
        output_dir_path.mkdir(parents=True, exist_ok=True)
        suffix = f"-v{version_label}" if version_label else ""
        output_path = output_dir_path / f"page-{page_index:02d}{suffix}.png"
        image.save(output_path, format="PNG", optimize=True)
        digest = hashlib.sha256(output_path.read_bytes()).hexdigest()
        return RenderedPage(page_index, output_path, digest, output_path.stat().st_size)

    def render_package(
        self,
        pages: list[dict[str, Any]],
        *,
        title: str = "",
        description: str = "",
        hashtags: list[str] | None = None,
        source_artifact_version_ids: list[str] | None = None,
        run_ref: str = "local",
        brand_render: dict[str, Any] | None = None,
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        _validate_page_set(pages)
        run_dir = self.output_root / _safe_run_ref(run_ref)
        pages_dir = run_dir / "pages"
        rendered = [self.render_page(page, pages_dir, brand_render=brand_render) for page in pages]
        zip_path = run_dir / "carousel-package.zip"
        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for item in rendered:
                archive_info = zipfile.ZipInfo(
                    f"page-{item.page_index:02d}.png", date_time=(1980, 1, 1, 0, 0, 0)
                )
                archive_info.compress_type = zipfile.ZIP_DEFLATED
                archive_info.external_attr = 0o644 << 16
                archive.writestr(archive_info, item.path.read_bytes())
        zip_digest = hashlib.sha256(zip_path.read_bytes()).hexdigest()
        page_ids = [f"carousel_page_{item.sha256[:16]}" for item in rendered]
        manifest = {
            "files": [f"page-{item.page_index:02d}.png" for item in rendered],
            "zip_name": zip_path.name,
            "zip_sha256": f"sha256:{zip_digest}",
            "dimensions": {"width_px": CAROUSEL_WIDTH, "height_px": CAROUSEL_HEIGHT},
            "mime_type": "image/png",
            "brand_render": _public_brand_render_manifest(brand_render),
        }
        content = {
            "schema_version": CAROUSEL_SCHEMA_VERSION,
            "artifact_type": "carousel_package",
            "page_count": len(rendered),
            "page_artifact_version_ids": page_ids,
            "title": title,
            "description": description,
            "hashtags": list(hashtags or []),
            "source_artifact_version_ids": list(source_artifact_version_ids or []),
            "export_manifest": manifest,
            "publish_copy_required": True,
            "publish_v2_compatible": True,
            "delivery_manifest": {
                "brand_render": _public_brand_render_manifest(brand_render),
            },
        }
        file_refs = [item.file_ref(self.output_root) for item in rendered]
        file_refs.append(
            {
                "file_key": zip_path.name,
                "relative_path": str(zip_path.resolve().relative_to(self.output_root.resolve())),
                "kind": "zip",
                "mime_type": "application/zip",
                "sha256": f"sha256:{zip_digest}",
                "size_bytes": zip_path.stat().st_size,
                "page_count": len(rendered),
            }
        )
        return content, file_refs

    def resolve_file_ref(self, file_ref: dict[str, Any]) -> Path:
        """Resolve an internal relative file reference inside the output root."""

        relative_path = str(file_ref.get("relative_path") or "")
        if not relative_path or Path(relative_path).is_absolute():
            raise CarouselRenderError("FILE_REF_INVALID", "文件引用必须是相对路径")
        path = (self.output_root / relative_path).resolve()
        try:
            path.relative_to(self.output_root)
        except ValueError as exc:
            raise CarouselRenderError("FILE_REF_OUTSIDE_ROOT", "文件引用越过输出根目录") from exc
        return path

    def rebuild_package_archive(
        self,
        page_file_refs: list[dict[str, Any]],
        *,
        run_ref: str,
        version_number: int,
    ) -> dict[str, Any]:
        """Build a fresh ZIP from the current page file references.

        A page retry writes its PNG into the retry directory. Reusing the old
        package ZIP would silently hand the stale page to publishing, so the
        package version must carry a new archive with the exact current page
        bytes while preserving the previous archive for rollback/audit.
        """

        if not page_file_refs:
            raise CarouselRenderError("PACKAGE_PAGES_REQUIRED", "图文包至少需要一张图片")
        image_refs = [item for item in page_file_refs if item.get("kind") == "image"]
        if len(image_refs) != len(page_file_refs):
            raise CarouselRenderError("PACKAGE_FILE_REF_INVALID", "图文包只能由图片页组成")
        ordered_refs = sorted(
            image_refs,
            key=lambda item: int(
                item.get("page_index") or _page_index_from_file_key(item.get("file_key"))
            ),
        )
        run_dir = self.output_root / _safe_run_ref(run_ref) / "retries"
        run_dir.mkdir(parents=True, exist_ok=True)
        zip_path = run_dir / f"carousel-package-v{version_number}.zip"
        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for item in ordered_refs:
                legacy_path = item.get("path")
                page_path = (
                    Path(str(legacy_path)).resolve() if legacy_path else self.resolve_file_ref(item)
                )
                if not page_path.is_file():
                    raise CarouselRenderError("PACKAGE_PAGE_MISSING", "图文包页文件不存在")
                file_key = str(item.get("file_key") or page_path.name)
                archive_info = zipfile.ZipInfo(file_key, date_time=(1980, 1, 1, 0, 0, 0))
                archive_info.compress_type = zipfile.ZIP_DEFLATED
                archive_info.external_attr = 0o644 << 16
                archive.writestr(archive_info, page_path.read_bytes())
        digest = hashlib.sha256(zip_path.read_bytes()).hexdigest()
        return {
            "file_key": zip_path.name,
            "relative_path": str(zip_path.resolve().relative_to(self.output_root.resolve())),
            "kind": "zip",
            "mime_type": "application/zip",
            "sha256": f"sha256:{digest}",
            "size_bytes": zip_path.stat().st_size,
            "page_count": len(ordered_refs),
        }

    def retry_page(
        self,
        page: dict[str, Any],
        *,
        run_ref: str,
        version_number: int,
        brand_render: dict[str, Any] | None = None,
    ) -> RenderedPage:
        if not isinstance(version_number, int) or version_number < 1:
            raise CarouselRenderError(
                "RETRY_VERSION_INVALID", "重试版本必须是正整数", page_index=page.get("page_index")
            )
        return self.render_page(
            page,
            self.output_root / _safe_run_ref(run_ref) / "retries",
            version_label=str(version_number),
            brand_render=brand_render,
        )

    def _draw_asset(self, canvas: Image.Image, page: dict[str, Any], page_index: int) -> None:
        refs = page.get("asset_refs") or []
        if not refs:
            raise CarouselRenderError(
                "ASSET_REF_REQUIRED", "图文页至少需要一个已有资产引用", page_index=page_index
            )
        if not all(isinstance(ref, str) for ref in refs):
            raise CarouselRenderError(
                "ASSET_REF_INVALID", "资产引用必须是已登记的稳定 ID", page_index=page_index
            )
        _validate_asset_refs([str(ref) for ref in refs])
        asset_path = page.get("asset_path")
        if asset_path and not self.asset_root:
            raise CarouselRenderError(
                "ASSET_PATH_NOT_ALLOWED",
                "直接资产路径仅允许在受信上传根目录内使用",
                page_index=page_index,
            )
        if not asset_path and self.asset_resolver:
            asset_path = self.asset_resolver(str(refs[0]))
        if not asset_path:
            raise CarouselRenderError(
                "ASSET_NOT_FOUND", "图文页资产无法解析", page_index=page_index
            )
        path = Path(asset_path).resolve()
        if self.asset_root:
            try:
                path.relative_to(self.asset_root)
            except ValueError as exc:
                raise CarouselRenderError(
                    "ASSET_OUTSIDE_ROOT", "图文资产不在受信资产根目录内", page_index=page_index
                ) from exc
        if not path.is_file():
            raise CarouselRenderError("ASSET_NOT_FOUND", "图文页资产不存在", page_index=page_index)
        try:
            with Image.open(path) as source:
                fitted = ImageOps.fit(
                    source.convert("RGB"), (CAROUSEL_WIDTH, 620), method=Image.Resampling.LANCZOS
                )
                canvas.paste(fitted, (0, 155))
        except (OSError, UnidentifiedImageError) as exc:
            raise CarouselRenderError(
                "ASSET_NOT_FOUND", "图文页资产无法读取", page_index=page_index
            ) from exc

    @staticmethod
    def _draw_brand_logo(canvas: Image.Image, brand_render: dict[str, Any]) -> None:
        raw_path = brand_render.get("logo_path")
        if not raw_path:
            return
        path = Path(str(raw_path)).resolve()
        if not path.is_file():
            raise CarouselRenderError("BRAND_LOGO_NOT_FOUND", "固定品牌 Logo 无法读取")
        try:
            with Image.open(path) as source:
                logo = source.convert("RGBA")
                logo.thumbnail((104, 104), Image.Resampling.LANCZOS)
                x = CAROUSEL_WIDTH - logo.width - 64
                y = (155 - logo.height) // 2
                canvas.paste(logo, (x, y), logo)
        except (OSError, UnidentifiedImageError) as exc:
            raise CarouselRenderError("BRAND_LOGO_NOT_FOUND", "固定品牌 Logo 无法读取") from exc


class DouyinCarouselPlanner:
    """Generate only a bounded page plan through the shared AppLLMPort."""

    def __init__(
        self,
        repository: AppCenterRepository,
        llm_port: AppLLMPort,
        *,
        context_resolver: ProjectContextResolver | None = None,
    ):
        self.repository = repository
        self.llm_port = llm_port
        self.context_resolver = context_resolver

    async def plan(
        self,
        app_run: AppRun,
        *,
        source_ids: list[str],
        asset_refs: list[str],
        goal: str,
        payload: dict[str, Any] | None = None,
        selected_style: StylePreset | None = None,
        custom_style_reference: dict[str, Any] | None = None,
        execution_context: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        payload = payload or app_run.input_payload
        page_count = payload.get("page_count", 3)
        if (
            isinstance(page_count, bool)
            or not isinstance(page_count, int)
            or page_count not in ALLOWED_PAGE_COUNTS
        ):
            raise CarouselRenderError("PAGE_COUNT_NOT_ALLOWED", "图文页数只能是 3、5 或 8 页")
        if not asset_refs:
            raise CarouselRenderError("ASSET_REF_REQUIRED", "AI 分页前必须提供已登记的图片资产引用")
        _validate_asset_refs(asset_refs)
        context: dict[str, Any] = execution_context or {}
        if app_run.context_snapshot_id:
            try:
                if not context:
                    context = (
                        self.context_resolver.resolve_for_application(
                            app_run.project_id,
                            app_run.context_snapshot_id,
                            app_id=CAROUSEL_APP_ID,
                        )
                        if self.context_resolver is not None
                        else self.repository.get_context_snapshot(
                            app_run.context_snapshot_id
                        ).payload
                    )
            except NotFound as exc:
                raise CarouselRenderError(
                    "CONTEXT_SNAPSHOT_NOT_FOUND", "图文运行引用的上下文快照不存在"
                ) from exc
        source_contents: list[dict[str, Any]] = []
        for source_id in source_ids:
            try:
                source_version = self.repository.get_artifact_version(source_id)
                source_artifact = self.repository.get_artifact(source_version.artifact_id)
            except NotFound as exc:
                raise CarouselRenderError(
                    "SOURCE_VERSION_NOT_FOUND", "图文来源 ArtifactVersion 不存在"
                ) from exc
            if (
                source_version.project_id != app_run.project_id
                or source_artifact.artifact_type
                not in {"copywriting", "selected_title", "title_set"}
            ):
                raise CarouselRenderError(
                    "SOURCE_VERSION_INVALID", "图文来源必须属于当前项目的文案或标题产物"
                )
            source_contents.append(
                {
                    "artifact_version_id": source_version.artifact_version_id,
                    "artifact_type": source_artifact.artifact_type,
                    "content": source_version.content or {},
                }
            )
        template_id = str(payload.get("template_id") or "template:clean-01")
        base_request = StructuredGenerationRequest(
            app_id=CAROUSEL_APP_ID,
            prompt_version=app_run.prompt_version
            or (
                CAROUSEL_PROMPT_VERSION_V2
                if app_run.input_schema_version == 2
                else CAROUSEL_PROMPT_VERSION
            ),
            input_schema_ref=(
                "douyin-carousel-input.v2"
                if app_run.input_schema_version == 2
                else "douyin-carousel-input.v1"
            ),
            output_schema_ref="douyin-carousel-plan-output.v1",
            prompt_variables={
                "goal": goal,
                "page_count": page_count,
                "template_id": template_id,
                "asset_refs": asset_refs,
                "source_artifacts": source_contents,
                "cover_hook": str(payload.get("cover_hook") or ""),
                "cta": str(payload.get("cta") or ""),
                "custom_style_reference": custom_style_reference,
                "fact_policy": "仅使用 source_artifacts 与 goal 中的事实；不确定事实进入 missing_facts，不得补造价格、地址、日期、功效或承诺",
                "style_policy": "风格参考只控制表达和分页结构，不得导入任何业务事实",
                "output_contract": "返回恰好 page_count 个连续 page_index；每页 asset_ref 必须来自 asset_refs；只返回结构化 JSON",
            },
            context=context,
            request_id=f"{app_run.app_run_id}:carousel-plan",
            idempotency_key=app_run.idempotency_key,
            trusted_style_rules=(
                tuple(selected_style.prompt_rules)
                + tuple(f"禁止表达：{item}" for item in selected_style.forbidden_patterns)
                if selected_style
                else ()
            ),
        )
        original_error: AppLLMPortError | None = None
        for attempt in range(2):
            request = replace(
                base_request,
                prompt_variables={
                    **base_request.prompt_variables,
                    "repair_attempt": attempt,
                    "repair_reason": str(original_error) if original_error else "",
                },
                request_id=f"{app_run.app_run_id}:carousel-plan:{attempt}",
            )
            try:
                response = await self.llm_port.generate_structured(
                    request, response_type=CarouselPlanOutput
                )
                plan = (
                    response.parsed_output
                    if isinstance(response.parsed_output, CarouselPlanOutput)
                    else CarouselPlanOutput.model_validate(response.parsed_output)
                )
                if plan.page_count != page_count or len(plan.pages) != page_count:
                    raise AppLLMPortError(
                        "STRUCTURED_OUTPUT_INVALID",
                        "图文分页数量与输入不一致",
                        diagnostic="CAROUSEL_PAGE_COUNT",
                    )
                indexes = [page.page_index for page in plan.pages]
                if indexes != list(range(1, page_count + 1)):
                    raise AppLLMPortError(
                        "STRUCTURED_OUTPUT_INVALID",
                        "图文页码必须连续递增",
                        diagnostic="CAROUSEL_PAGE_INDEX",
                    )
                if any(page.asset_ref not in asset_refs for page in plan.pages):
                    raise AppLLMPortError(
                        "STRUCTURED_OUTPUT_INVALID",
                        "图文只能引用输入中的已有资产",
                        diagnostic="CAROUSEL_ASSET_REF",
                    )
                return [
                    {
                        "page_index": page.page_index,
                        "purpose": page.purpose,
                        "text": page.text,
                        "asset_refs": [page.asset_ref],
                        "font_id": "noto-sans-sc-bold",
                        "dimensions": {"width_px": CAROUSEL_WIDTH, "height_px": CAROUSEL_HEIGHT},
                    }
                    for page in plan.pages
                ]
            except AppLLMPortError as exc:
                if exc.code != "STRUCTURED_OUTPUT_INVALID":
                    raise
                original_error = exc
            except (ValidationError, TypeError, ValueError) as exc:
                original_error = AppLLMPortError(
                    "STRUCTURED_OUTPUT_INVALID",
                    "图文分页结构不符合契约",
                    diagnostic=type(exc).__name__,
                )
        raise original_error or AppLLMPortError(
            "STRUCTURED_OUTPUT_INVALID", "图文分页结构不符合契约"
        )


class DouyinCarouselExecutor(AppExecutor):
    """AppRunner executor for local carousel rendering."""

    def __init__(
        self,
        renderer: DouyinCarouselRenderer | None = None,
        *,
        repository: AppCenterRepository | None = None,
        llm_port: AppLLMPort | None = None,
        context_resolver: ProjectContextResolver | None = None,
    ):
        self.renderer = renderer or DouyinCarouselRenderer()
        self.repository = repository
        self.context_resolver = context_resolver
        self.planner = (
            DouyinCarouselPlanner(
                repository,
                llm_port,
                context_resolver=context_resolver,
            )
            if repository and llm_port
            else None
        )

    async def execute(self, app_run: AppRun) -> ExecutorOutput:
        if app_run.app_id != CAROUSEL_APP_ID:
            raise CarouselRenderError("APP_EXECUTOR_MISMATCH", "图文执行器与应用不匹配")
        payload, selected_style, custom_style_reference = _normalize_carousel_input(app_run)
        execution_context: dict[str, Any] = {}
        if app_run.context_snapshot_id and self.context_resolver is not None:
            execution_context = self.context_resolver.resolve_for_application(
                app_run.project_id,
                app_run.context_snapshot_id,
                app_id=CAROUSEL_APP_ID,
            )
        goal = payload.get("goal")
        if not isinstance(goal, str) or not goal.strip():
            raise CarouselRenderError("GOAL_REQUIRED", "图文运行必须提供经营目标")
        source_ids = payload.get("source_artifact_version_ids")
        if (
            not isinstance(source_ids, list)
            or not source_ids
            or any(not isinstance(item, str) or not item.strip() for item in source_ids)
        ):
            raise CarouselRenderError(
                "SOURCE_VERSION_REQUIRED", "图文运行必须绑定来源 ArtifactVersion"
            )
        source_contents: list[tuple[str, dict[str, Any]]] = []
        if self.repository:
            for source_id in source_ids:
                try:
                    source_version = self.repository.get_artifact_version(source_id)
                    source_artifact = self.repository.get_artifact(source_version.artifact_id)
                except NotFound as exc:
                    raise CarouselRenderError(
                        "SOURCE_VERSION_NOT_FOUND", "图文来源 ArtifactVersion 不存在"
                    ) from exc
                if (
                    source_version.project_id != app_run.project_id
                    or source_artifact.artifact_type
                    not in {"copywriting", "selected_title", "title_set"}
                ):
                    raise CarouselRenderError(
                        "SOURCE_VERSION_INVALID", "图文来源必须属于当前项目的文案或标题产物"
                    )
                source_contents.append(
                    (source_artifact.artifact_type, source_version.content or {})
                )
        pages = payload.get("pages")
        if pages is None:
            if not self.planner:
                raise AppLLMPortError(
                    "LLM_CONFIGURATION_MISSING", "图文分页规划需要复用现有大模型配置"
                )
            asset_refs = [
                str(item).strip() for item in payload.get("asset_refs") or [] if str(item).strip()
            ]
            pages = await self.planner.plan(
                app_run,
                payload=payload,
                source_ids=[str(item) for item in source_ids],
                asset_refs=asset_refs,
                goal=goal,
                selected_style=selected_style,
                custom_style_reference=custom_style_reference,
                execution_context=execution_context,
            )
        if not isinstance(pages, list):
            raise CarouselRenderError("CAROUSEL_PLAN_REQUIRED", "图文运行必须先提供分页计划")
        if any(isinstance(page, dict) and page.get("asset_path") for page in pages):
            raise CarouselRenderError(
                "ASSET_PATH_NOT_ALLOWED", "图文运行只能使用已登记的 asset_refs"
            )
        title, description, hashtags = _resolve_publish_copy(payload, source_contents)
        brand_values = (
            (execution_context.get("brand") or {}).get("values") or {} if execution_context else {}
        )
        logo_ref = brand_values.get("logo_ref")
        logo_path = (
            self.context_resolver.resolve_exact_asset_path(logo_ref, variant_role="thumbnail")
            if self.context_resolver is not None
            else None
        )
        brand_render = {
            "display_name": brand_values.get("display_name")
            or (execution_context.get("brand") or {}).get("display_name"),
            "primary_color": brand_values.get("primary_color"),
            "secondary_color": brand_values.get("secondary_color"),
            "font_family": brand_values.get("font_family"),
            "logo_ref": logo_ref,
            "logo_path": str(logo_path) if logo_path else None,
            "context_snapshot_id": app_run.context_snapshot_id,
        }
        content, file_refs = self.renderer.render_package(
            pages,
            title=title,
            description=description,
            hashtags=hashtags,
            source_artifact_version_ids=[str(item) for item in source_ids],
            run_ref=app_run.app_run_id,
            brand_render=brand_render,
        )
        page_refs = {ref["file_key"]: ref for ref in file_refs if ref.get("kind") == "image"}
        related: list[RelatedArtifactOutput] = [
            RelatedArtifactOutput(
                key="plan",
                artifact_type="carousel_plan",
                name="抖音图文分页计划",
                content={
                    "schema_version": CAROUSEL_SCHEMA_VERSION,
                    "artifact_type": "carousel_plan",
                    "page_count": len(pages),
                    "page_outline": [
                        {
                            "page_index": page["page_index"],
                            "purpose": str(page.get("purpose") or "content"),
                        }
                        for page in pages
                    ],
                    "template_id": str(payload.get("template_id") or "template:clean-01"),
                    "source_artifact_version_ids": list(source_ids),
                    "goal": goal,
                    "execution_context": execution_context,
                },
            )
        ]
        for page in pages:
            page_index = page["page_index"]
            page_ref = page_refs[f"page-{page_index:02d}.png"]
            related.append(
                RelatedArtifactOutput(
                    key=f"page:{page_index}",
                    artifact_type="carousel_page",
                    name=f"抖音图文第{page_index}页",
                    content={
                        "schema_version": CAROUSEL_SCHEMA_VERSION,
                        "artifact_type": "carousel_page",
                        "page_index": page_index,
                        "text": str(page.get("text") or ""),
                        "asset_refs": list(page.get("asset_refs") or []),
                        "render_state": "ready",
                        "dimensions": {"width_px": CAROUSEL_WIDTH, "height_px": CAROUSEL_HEIGHT},
                        "source_plan_artifact_version_id": "artifact_output:plan",
                        "brand_render": _public_brand_render_manifest(brand_render),
                    },
                    file_refs=[page_ref],
                )
            )
        content["page_artifact_version_ids"] = [
            f"artifact_output:page:{page['page_index']}" for page in pages
        ]
        content["source_plan_artifact_version_id"] = "artifact_output:plan"
        return ExecutorOutput(
            artifact_type="carousel_package",
            name="抖音图文内容包",
            content=content,
            file_refs=file_refs,
            source="rendered",
            provider_class="local-renderer",
            related_artifacts=related,
        )


def _validate_page_set(pages: list[dict[str, Any]]) -> None:
    if len(pages) not in ALLOWED_PAGE_COUNTS:
        raise CarouselRenderError("PAGE_COUNT_NOT_ALLOWED", "图文页数只能是 3、5 或 8 页")
    indexes = [page.get("page_index") for page in pages]
    if indexes != list(range(1, len(pages) + 1)):
        raise CarouselRenderError("PAGE_INDEX_NOT_CONTIGUOUS", "图文页码必须从 1 连续递增")


def _validate_asset_refs(asset_refs: list[str]) -> None:
    if any(not ref or "/" in ref or "\\" in ref or ref.startswith(".") for ref in asset_refs):
        raise CarouselRenderError("ASSET_REF_INVALID", "资产引用必须是已登记的稳定 ID")


def _normalize_carousel_input(
    app_run: AppRun,
) -> tuple[dict[str, Any], StylePreset | None, dict[str, Any] | None]:
    """Project workbench v2 into the proven AC-4 flat executor contract."""

    raw = app_run.input_payload
    if app_run.input_schema_version != 2:
        return dict(raw), None, None
    if (
        raw.get("schema_version") != 2
        or raw.get("app_id") != CAROUSEL_APP_ID
        or raw.get("input_schema_ref") != "douyin-carousel-input.v2"
        or raw.get("project_id") != app_run.project_id
        or raw.get("context_snapshot_id") != app_run.context_snapshot_id
    ):
        raise CarouselRenderError(
            "CAROUSEL_INPUT_V2_INVALID",
            "图文工作台输入与当前项目或版本不一致",
        )
    brief = raw.get("task_brief")
    if not isinstance(brief, dict):
        raise CarouselRenderError("CAROUSEL_INPUT_V2_INVALID", "图文工作台缺少本次任务信息")
    source_ids = raw.get("source_artifact_version_ids")
    if not isinstance(source_ids, list) or not source_ids:
        raise CarouselRenderError("SOURCE_VERSION_REQUIRED", "图文运行必须绑定来源 ArtifactVersion")
    style_ref = raw.get("style_ref")
    custom = raw.get("custom_style_reference")
    if bool(style_ref) == bool(custom):
        raise CarouselRenderError(
            "CAROUSEL_STYLE_REQUIRED", "图文风格必须选择内置风格或本次自定义参考"
        )
    selected_style = None
    if isinstance(style_ref, dict):
        try:
            selected_style = resolve_style_preset(
                str(style_ref.get("style_id") or ""),
                int(style_ref.get("version") or 0),
                app_id=CAROUSEL_APP_ID,
            )
        except (StylePresetError, TypeError, ValueError) as exc:
            raise CarouselRenderError("CAROUSEL_STYLE_INVALID", "所选图文风格版本不可用") from exc
    normalized_custom = None
    if isinstance(custom, dict):
        text = str(custom.get("text") or "").strip()
        expected = f"sha256:{hashlib.sha256(text.encode('utf-8')).hexdigest()}"
        if (
            not text
            or len(text) > 5000
            or custom.get("facts_imported") is not False
            or custom.get("content_fingerprint") != expected
        ):
            raise CarouselRenderError("CAROUSEL_STYLE_INVALID", "自定义风格参考不符合事实隔离规则")
        normalized_custom = {
            "text": text,
            "content_fingerprint": expected,
            "facts_imported": False,
        }
    asset_refs = brief.get("asset_refs")
    page_count = brief.get("page_count")
    template_id = str(brief.get("template_id") or "").strip()
    goal = str(brief.get("goal") or "").strip()
    if (
        not goal
        or page_count not in ALLOWED_PAGE_COUNTS
        or not template_id
        or not isinstance(asset_refs, list)
        or not asset_refs
    ):
        raise CarouselRenderError(
            "CAROUSEL_INPUT_V2_INVALID",
            "图文目标、页数、模板或图片资产不完整",
        )
    normalized = {
        "goal": goal,
        "page_count": page_count,
        "template_id": template_id,
        "asset_refs": list(asset_refs),
        "source_artifact_version_ids": list(source_ids),
        "cover_hook": str(brief.get("cover_hook") or "").strip(),
        "cta": str(brief.get("cta") or "").strip(),
        "title": str(brief.get("cover_hook") or "").strip(),
        "description": str(brief.get("publish_description") or "").strip(),
        "hashtags": list(brief.get("hashtags") or []),
    }
    return normalized, selected_style, normalized_custom


def _resolve_publish_copy(
    payload: dict[str, Any], source_contents: list[tuple[str, dict[str, Any]]]
) -> tuple[str, str, list[str]]:
    """Resolve publish metadata from explicit input, then trusted source artifacts.

    The desktop carousel flow intentionally only asks for a source version ID.
    A selected title or copywriting artifact must therefore still produce a
    usable publish-copy payload without inventing facts or requiring a second
    model/configuration source.
    """

    title = _non_empty_text(payload.get("title"))
    description = _non_empty_text(payload.get("description"))
    hashtags = _string_list(payload.get("hashtags"))
    for artifact_type, source in source_contents:
        if not title:
            if artifact_type == "selected_title":
                title = _non_empty_text(source.get("title"))
            elif artifact_type == "title_set":
                candidates = source.get("candidates")
                if isinstance(candidates, list) and candidates:
                    first = candidates[0]
                    if isinstance(first, dict):
                        title = _non_empty_text(first.get("title"))
        if not description and artifact_type == "copywriting":
            variants = source.get("variants")
            if isinstance(variants, list) and variants and isinstance(variants[0], dict):
                variant = variants[0]
                description = _non_empty_text(variant.get("full_text")) or "".join(
                    _non_empty_text(variant.get(field)) for field in ("hook", "body", "cta")
                )
        if not hashtags:
            hashtags = _string_list(source.get("hashtags"))
        if title and description and hashtags:
            break
    return title, description, hashtags


def _non_empty_text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item.strip() for item in value if isinstance(item, str) and item.strip()]


def _wrap_text(
    draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont, *, max_width: int
) -> list[str]:
    lines: list[str] = []
    for paragraph in text.splitlines() or [text]:
        current = ""
        for character in paragraph:
            candidate = current + character
            if current and draw.textlength(candidate, font=font) > max_width:
                lines.append(current)
                current = character
            else:
                current = candidate
        if current:
            lines.append(current)
    return lines


def _safe_run_ref(value: str) -> str:
    return "".join(char for char in value if char.isalnum() or char in {"-", "_"})[:80] or "run"


def _safe_color(value: Any, fallback: tuple[int, int, int]) -> tuple[int, int, int]:
    if not isinstance(value, str) or not value.strip():
        return fallback
    try:
        resolved = ImageColor.getrgb(value.strip())
    except ValueError:
        return fallback
    if len(resolved) == 4:
        return resolved[:3]
    return resolved


def _public_brand_render_manifest(
    brand_render: dict[str, Any] | None,
) -> dict[str, Any]:
    values = brand_render or {}
    logo_ref = values.get("logo_ref")
    return {
        "context_snapshot_id": values.get("context_snapshot_id"),
        "display_name": values.get("display_name"),
        "primary_color": values.get("primary_color"),
        "secondary_color": values.get("secondary_color"),
        "font_family": values.get("font_family"),
        "logo_ref": logo_ref,
        "logo_applied": bool(logo_ref and values.get("logo_path")),
        "applied_to": [
            "header",
            "background",
            *(["logo_overlay"] if logo_ref and values.get("logo_path") else []),
        ],
    }


def _page_index_from_file_key(value: Any) -> int:
    name = Path(str(value or "")).stem
    prefix, _, suffix = name.partition("-")
    if prefix != "page" or not suffix.isdigit():
        raise CarouselRenderError("PACKAGE_PAGE_INDEX_INVALID", "图文页文件名缺少有效页码")
    return int(suffix)


def resolve_registered_asset(asset_ref: str) -> Path | None:
    """Resolve only a registered asset-library ID, never a filesystem path."""

    normalized = str(asset_ref or "").strip()
    if normalized.startswith("asset:"):
        normalized = normalized.removeprefix("asset:")
    asset_id, separator, revision_id = normalized.partition("@")
    if not asset_id or "/" in normalized or "\\" in normalized or normalized.startswith("."):
        return None
    try:
        from pixelle_video.services.assets_v2.repository import AssetLibraryRepository

        repository = AssetLibraryRepository()
        asset = repository.get_asset(asset_id)
        if not asset or asset.get("status") == "archived" or asset.get("media_kind") != "image":
            return None
        if separator:
            return repository.get_revision_path(asset_id, revision_id=revision_id)
        return repository.get_revision_path(asset_id)
    except (OSError, ValueError):
        return None
