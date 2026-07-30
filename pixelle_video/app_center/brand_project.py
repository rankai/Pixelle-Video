"""Brand-package binding and immutable project-context resolution.

This module owns the server trust boundary for ContextSnapshot v3. Clients
select a brand and may submit project-only overrides, but never provide the
stored brand projection or its source revision.
"""

from __future__ import annotations

import hashlib
import json
from contextlib import contextmanager, nullcontext
from copy import deepcopy
from pathlib import Path
from typing import Any, Iterator, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from pixelle_video.services.assets_v2.repository import DomainRevisionGuardError

from .models import ContentProject, ContextSnapshot
from .project_context import (
    ApplicationContext,
    ContextFact,
    ProjectContextError,
    context_projection_fingerprint,
    project_context_v3_to_v2,
)
from .repository import AppCenterRepository

_BRAND_VALUE_FIELDS = (
    "display_name",
    "logo_ref",
    "store_address",
    "phone",
    "primary_color",
    "secondary_color",
    "font_family",
    "default_subtitle_style",
    "default_bgm_ref",
    "ending_card_text",
    "coupon_phrase",
)
_MEDIA_OVERRIDE_FIELDS = {
    "logo_ref": "image",
    "default_bgm_ref": "audio",
}
_UI_SCALAR_OVERRIDE_FIELDS = {
    "display_name",
    "store_address",
    "phone",
    "primary_color",
    "secondary_color",
    "font_family",
    "default_subtitle_style",
    "ending_card_text",
    "coupon_phrase",
}
_SOURCE_TO_VALUE_FIELD = {
    "display_name": "brand_name",
    "store_address": "store_address",
    "phone": "phone",
    "primary_color": "primary_color",
    "secondary_color": "secondary_color",
    "font_family": "font_family",
    "default_subtitle_style": "default_subtitle_style",
    "ending_card_text": "ending_card_text",
    "coupon_phrase": "coupon_phrase",
}
_BRAND_FIELD_LABELS = {
    "display_name": "品牌名称",
    "logo_ref": "Logo",
    "store_address": "地址",
    "phone": "电话",
    "primary_color": "品牌主色",
    "secondary_color": "品牌辅色",
    "font_family": "默认字体",
    "default_subtitle_style": "默认字幕样式",
    "default_bgm_ref": "默认 BGM",
    "ending_card_text": "结尾卡文案",
    "coupon_phrase": "优惠话术",
}


class _StrictBrandRevisionModel(BaseModel):
    model_config = ConfigDict(extra="allow", strict=True)


class _BrandDomainPayload(_StrictBrandRevisionModel):
    brand_id: str = Field(min_length=1, max_length=200)
    brand_name: str = Field(min_length=1, max_length=200)
    logo_asset_id: str | None
    default_bgm_asset_id: str | None
    primary_color: str = Field(pattern=r"^#[0-9A-Fa-f]{6}$")
    secondary_color: str = Field(pattern=r"^#[0-9A-Fa-f]{6}$")
    font_family: str = Field(max_length=200)
    default_subtitle_style: str = Field(max_length=200)
    ending_card_text: str = Field(max_length=500)
    store_address: str = Field(max_length=500)
    phone: str = Field(max_length=200)
    coupon_phrase: str = Field(max_length=500)
    status: Literal["ready", "archived"]


class _BrandDomainRevision(_StrictBrandRevisionModel):
    resource_kind: Literal["brand"]
    resource_id: str = Field(min_length=1, max_length=200)
    revision: int = Field(ge=1)
    payload: _BrandDomainPayload
    created_at: str = Field(min_length=1)


def validate_brand_domain_revision(
    value: Any,
    *,
    expected_brand_id: str,
    expected_revision: int,
) -> dict[str, Any]:
    """Validate an immutable brand revision without defaults or coercion."""

    try:
        revision = _BrandDomainRevision.model_validate(value)
    except ValidationError as exc:
        raise ProjectContextError(
            "PROJECT_BRAND_REVISION_NOT_FOUND",
            "品牌历史版本无法读取，请保留当前项目资料并联系支持",
        ) from exc
    if (
        revision.resource_id != expected_brand_id
        or revision.payload.brand_id != expected_brand_id
        or revision.revision != expected_revision
    ):
        raise ProjectContextError(
            "PROJECT_BRAND_REVISION_NOT_FOUND",
            "品牌历史版本无法读取，请保留当前项目资料并联系支持",
        )
    return revision.payload.model_dump(mode="python")


def default_project_brief(name: str, primary_goal: str) -> dict[str, Any]:
    """Return a valid, deliberately minimal brief for a newly bound project."""

    return {
        "subject_type": "campaign",
        "offer": {
            "name": name,
            "category": "未分类",
            "price_facts": [],
            "promotion_facts": [],
        },
        "marketing_goal": primary_goal,
        "audience": {"primary": "待补充", "scenes": []},
        "selling_points": [],
        "proof_points": [],
        "required_facts": [],
        "forbidden_claims": [],
        "asset_refs": [],
    }


class BrandProjectService:
    def __init__(self, app_repository: AppCenterRepository, asset_repository: Any):
        self.app_repository = app_repository
        self.asset_repository = asset_repository
        self.app_repository.set_asset_repository(asset_repository)

    def create_project(
        self,
        name: str,
        primary_goal: str,
        *,
        brand_id: str,
        expected_domain_revision: int | None = None,
        project_overrides: dict[str, Any] | None = None,
        project_brief: dict[str, Any] | None = None,
    ) -> tuple[ContentProject, ContextSnapshot]:
        brand_context, brand_source = self._resolve_brand_context(
            brand_id,
            expected_domain_revision=expected_domain_revision,
            project_overrides=project_overrides or {},
        )
        payload = {
            "schema_version": 3,
            "brand_context": brand_context,
            "project_brief": deepcopy(project_brief or default_project_brief(name, primary_goal)),
        }
        with self._guard_current_brand(
            brand_id,
            brand_context["domain_revision"],
            brand_source,
            brand_context=brand_context,
        ):
            return self.app_repository.create_project_with_context(
                name,
                primary_goal,
                brand_id=brand_id,
                payload=payload,
                source_brand_revision_id=str(brand_context["domain_revision"]),
            )

    def create_unbound_project(
        self,
        name: str,
        primary_goal: str,
        *,
        project_brief: dict[str, Any] | None = None,
    ) -> tuple[ContentProject, ContextSnapshot]:
        """Create an explicit v3 project without inferring or binding a brand."""

        return self.app_repository.create_project_with_context(
            name,
            primary_goal,
            brand_id=None,
            payload={
                "schema_version": 3,
                "brand_context": None,
                "project_brief": deepcopy(
                    project_brief or default_project_brief(name, primary_goal)
                ),
            },
            source_brand_revision_id=None,
        )

    def replace_binding(
        self,
        project_id: str,
        *,
        brand_id: str | None,
        expected_context_snapshot_id: str | None,
        expected_domain_revision: int | None = None,
        project_overrides: dict[str, Any] | None = None,
    ) -> tuple[ContentProject, ContextSnapshot]:
        project = self.app_repository.get_project(project_id)
        if project.current_context_snapshot_id != expected_context_snapshot_id:
            raise ProjectContextError(
                "PROJECT_CONTEXT_CONFLICT",
                "项目信息已在其他位置更新，请刷新后重试",
            )
        project_brief, inherited_overrides = self._current_project_material(project)
        if brand_id is None:
            if project_overrides:
                raise ProjectContextError(
                    "PROJECT_BRAND_CONTEXT_UNTRUSTED",
                    "project overrides require a brand binding",
                )
            brand_context = None
            brand_source = None
            source_revision = None
        else:
            explicit_override_fields = set(project_overrides or {})
            effective_overrides = {
                **inherited_overrides,
                **(project_overrides or {}),
            }
            historical_media_override_fields = (
                set(inherited_overrides) - explicit_override_fields
            ) & set(_MEDIA_OVERRIDE_FIELDS)
            brand_context, brand_source = self._resolve_brand_context(
                brand_id,
                expected_domain_revision=expected_domain_revision,
                project_overrides=effective_overrides,
                historical_media_override_fields=historical_media_override_fields,
            )
            source_revision = str(brand_context["domain_revision"])
        payload = {
            "schema_version": 3,
            "brand_context": brand_context,
            "project_brief": project_brief,
        }
        guard = (
            self._guard_current_brand(
                brand_id,
                brand_context["domain_revision"],
                brand_source,
                brand_context=brand_context,
                historical_media_override_fields=historical_media_override_fields,
            )
            if brand_id is not None and brand_context is not None and brand_source is not None
            else nullcontext()
        )
        with guard:
            return self.app_repository.replace_project_brand_binding(
                project_id,
                brand_id=brand_id,
                payload=payload,
                source_brand_revision_id=source_revision,
                expected_context_snapshot_id=expected_context_snapshot_id,
            )

    def preview_brand_sync(
        self,
        project_id: str,
        *,
        expected_context_snapshot_id: str | None = None,
    ) -> dict[str, Any]:
        prepared = self._prepare_brand_sync(
            project_id,
            expected_context_snapshot_id=expected_context_snapshot_id,
            require_expected=False,
        )
        if prepared["status"] == "unbound":
            return {
                "project_id": project_id,
                "status": "unbound",
                "has_changes": False,
                "result_code": None,
                "changes_committed": False,
                "changes": [],
            }
        has_changes = bool(prepared["has_changes"])
        return {
            "project_id": project_id,
            "status": "changes_available" if has_changes else "no_change",
            "has_changes": has_changes,
            "result_code": None if has_changes else "PROJECT_BRAND_SYNC_NO_CHANGE",
            "changes_committed": False,
            "changes": deepcopy(prepared["changes"]),
        }

    def sync_brand(
        self,
        project_id: str,
        *,
        expected_context_snapshot_id: str | None,
        idempotency_key: str,
    ) -> dict[str, Any]:
        request_fingerprint = self._sync_request_fingerprint(
            project_id,
            expected_context_snapshot_id,
        )
        existing = self.app_repository.get_brand_sync_result(
            project_id,
            idempotency_key,
            request_fingerprint=request_fingerprint,
        )
        if existing is not None:
            return existing
        prepared = self._prepare_brand_sync(
            project_id,
            expected_context_snapshot_id=expected_context_snapshot_id,
            require_expected=True,
        )
        if prepared["status"] == "unbound":
            raise ProjectContextError(
                "PROJECT_BRAND_NOT_BOUND",
                "这个项目尚未关联品牌，请先选择品牌包",
            )
        brand_context = prepared["brand_context"]
        source = prepared["source"]
        payload = {
            "schema_version": 3,
            "brand_context": brand_context,
            "project_brief": prepared["project_brief"],
        }
        with self._guard_current_brand(
            prepared["brand_id"],
            brand_context["domain_revision"],
            source,
            brand_context=brand_context,
            historical_media_override_fields=prepared["historical_media_override_fields"],
        ):
            return self.app_repository.commit_brand_sync(
                project_id,
                brand_id=prepared["brand_id"],
                expected_context_snapshot_id=expected_context_snapshot_id,
                payload=payload,
                source_brand_revision_id=str(brand_context["domain_revision"]),
                idempotency_key=idempotency_key,
                request_fingerprint=request_fingerprint,
                changes=prepared["changes"],
                has_changes=prepared["has_changes"],
            )

    def update_project_material(
        self,
        project_id: str,
        *,
        expected_context_snapshot_id: str,
        project_brief: dict[str, Any],
        project_overrides: dict[str, Any],
    ) -> tuple[ContentProject, ContextSnapshot]:
        """Append business inputs while preserving the project's pinned brand revision.

        This command intentionally does not resolve the latest brand. Brand updates
        only enter a project through ``sync_brand``.
        """

        project = self.app_repository.get_project(project_id)
        if project.status == "archived":
            raise ProjectContextError("PROJECT_ARCHIVED", "已归档项目不能修改品牌资料")
        if project.current_context_snapshot_id != expected_context_snapshot_id:
            raise ProjectContextError(
                "PROJECT_CONTEXT_CONFLICT",
                "项目信息已在其他位置更新，请刷新后重试",
            )
        snapshot = self.app_repository.get_context_snapshot(expected_context_snapshot_id)
        if snapshot.schema_version != 3:
            raise ProjectContextError(
                "PROJECT_CONTEXT_LEGACY_MAPPING_REQUIRED",
                "旧项目资料无法安全转换，请先补全项目资料",
            )
        unknown = set(project_overrides) - _UI_SCALAR_OVERRIDE_FIELDS
        if unknown:
            raise ProjectContextError(
                "PROJECT_BRAND_CONTEXT_UNTRUSTED",
                f"unsupported project override: {sorted(unknown)[0]}",
            )

        current_brand = snapshot.payload.get("brand_context")
        if current_brand is None:
            if project_overrides:
                raise ProjectContextError(
                    "PROJECT_BRAND_CONTEXT_UNTRUSTED",
                    "project overrides require a brand binding",
                )
            brand_context = None
            source_revision = None
        else:
            brand_id = current_brand["brand_id"]
            domain_revision = current_brand["domain_revision"]
            exact = self._exact_brand_revision(brand_id, domain_revision)
            if exact is None:
                raise ProjectContextError(
                    "PROJECT_BRAND_REVISION_NOT_FOUND",
                    "品牌历史版本无法读取，请保留当前项目资料并联系支持",
                )
            source = validate_brand_domain_revision(
                exact,
                expected_brand_id=brand_id,
                expected_revision=domain_revision,
            )
            current_values = deepcopy(current_brand["values"])
            values = {
                field: deepcopy(source[source_field])
                for field, source_field in _SOURCE_TO_VALUE_FIELD.items()
            }
            # Logo and BGM are not editable in the lightweight project form.
            # Keep their immutable refs and any historical project-only override.
            values["logo_ref"] = deepcopy(current_values["logo_ref"])
            values["default_bgm_ref"] = deepcopy(current_values["default_bgm_ref"])
            media_overrides = set(current_brand["overridden_fields"]) & set(_MEDIA_OVERRIDE_FIELDS)
            for field, value in project_overrides.items():
                values[field] = deepcopy(value)
            brand_context = {
                "brand_id": brand_id,
                "domain_revision": domain_revision,
                "values": values,
                "overridden_fields": sorted(media_overrides | set(project_overrides)),
            }
            source_revision = str(domain_revision)

        payload = {
            "schema_version": 3,
            "brand_context": brand_context,
            "project_brief": deepcopy(project_brief),
        }
        return self.app_repository.replace_project_brand_binding(
            project_id,
            brand_id=project.brand_id,
            payload=payload,
            source_brand_revision_id=source_revision,
            expected_context_snapshot_id=expected_context_snapshot_id,
            primary_goal=project_brief.get("marketing_goal"),
        )

    def _prepare_brand_sync(
        self,
        project_id: str,
        *,
        expected_context_snapshot_id: str | None,
        require_expected: bool,
    ) -> dict[str, Any]:
        project = self.app_repository.get_project(project_id)
        if project.status == "archived":
            raise ProjectContextError(
                "PROJECT_ARCHIVED",
                "已归档项目不能同步品牌资料",
            )
        if (
            require_expected or expected_context_snapshot_id is not None
        ) and project.current_context_snapshot_id != expected_context_snapshot_id:
            raise ProjectContextError(
                "PROJECT_CONTEXT_CONFLICT",
                "项目信息已在其他位置更新，请刷新后重试",
            )
        if project.brand_id is None:
            return {"status": "unbound"}
        project_brief, overrides = self._current_project_material(project)
        brand_context, source = self._resolve_brand_context(
            project.brand_id,
            expected_domain_revision=None,
            project_overrides=overrides,
            historical_media_override_fields=set(overrides) & set(_MEDIA_OVERRIDE_FIELDS),
        )
        current_brand: dict[str, Any] | None = None
        current_snapshot = None
        if project.current_context_snapshot_id is not None:
            current_snapshot = self.app_repository.get_context_snapshot(
                project.current_context_snapshot_id
            )
            if current_snapshot.schema_version == 3:
                current_brand = current_snapshot.payload.get("brand_context")
                if (
                    not isinstance(current_brand, dict)
                    or current_brand.get("brand_id") != project.brand_id
                ):
                    raise ProjectContextError(
                        "PROJECT_BRAND_CONTEXT_UNTRUSTED",
                        "stored project brand does not match its binding",
                    )
        changes = self._brand_sync_changes(
            current_brand,
            brand_context,
        )
        has_changes = (
            current_snapshot is None
            or current_snapshot.schema_version != 3
            or current_brand != brand_context
        )
        if has_changes and not changes:
            changes.append(
                {
                    "field": "brand_context",
                    "label": "品牌资料",
                    "status": "updated",
                }
            )
        return {
            "status": "ready",
            "brand_id": project.brand_id,
            "brand_context": brand_context,
            "source": source,
            "project_brief": project_brief,
            "changes": changes,
            "has_changes": has_changes,
            "historical_media_override_fields": set(overrides) & set(_MEDIA_OVERRIDE_FIELDS),
        }

    @staticmethod
    def _brand_sync_changes(
        current: dict[str, Any] | None,
        candidate: dict[str, Any],
    ) -> list[dict[str, str]]:
        changes: list[dict[str, str]] = []
        current_values = current.get("values", {}) if current is not None else {}
        candidate_values = candidate["values"]
        overridden = set(candidate["overridden_fields"])
        for field in _BRAND_VALUE_FIELDS:
            if field in overridden:
                changes.append(
                    {
                        "field": field,
                        "label": _BRAND_FIELD_LABELS[field],
                        "status": "preserved_project_override",
                    }
                )
            elif current is None or current_values.get(field) != candidate_values[field]:
                changes.append(
                    {
                        "field": field,
                        "label": _BRAND_FIELD_LABELS[field],
                        "status": "updated",
                    }
                )
        return changes

    @staticmethod
    def _sync_request_fingerprint(
        project_id: str,
        expected_context_snapshot_id: str | None,
    ) -> str:
        encoded = json.dumps(
            {
                "project_id": project_id,
                "expected_context_snapshot_id": expected_context_snapshot_id,
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return "sha256:" + hashlib.sha256(encoded).hexdigest()

    def _current_project_material(
        self, project: ContentProject
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        if not project.current_context_snapshot_id:
            return default_project_brief(project.name, project.primary_goal), {}
        snapshot = self.app_repository.get_context_snapshot(project.current_context_snapshot_id)
        resolved = ProjectContextResolver(
            self.app_repository, self.asset_repository
        ).resolve_for_run(project.project_id, snapshot.context_snapshot_id)
        if snapshot.schema_version == 3:
            brand = snapshot.payload["brand_context"]
            inherited = (
                {field: deepcopy(brand["values"][field]) for field in brand["overridden_fields"]}
                if brand is not None
                else {}
            )
            return deepcopy(snapshot.payload["project_brief"]), inherited
        if snapshot.schema_version == 2:
            payload = snapshot.payload
            store = payload["store_or_brand"]
            inherited = {"display_name": store["name"]}
            if store.get("address") is not None:
                inherited["store_address"] = store["address"]
            if store.get("contact") is not None:
                inherited["phone"] = store["contact"]
            return (
                {
                    "subject_type": payload["subject_type"],
                    "offer": deepcopy(payload["offer"]),
                    "marketing_goal": project.primary_goal,
                    "audience": deepcopy(payload["audience"]),
                    "selling_points": deepcopy(payload["selling_points"]),
                    "proof_points": deepcopy(payload["proof_points"]),
                    "required_facts": deepcopy(payload["required_facts"]),
                    "forbidden_claims": deepcopy(payload["forbidden_claims"]),
                    "asset_refs": deepcopy(payload["asset_refs"]),
                },
                inherited,
            )
        return self._map_legacy_v1(project, resolved.business_payload)

    def _map_legacy_v1(
        self, project: ContentProject, payload: dict[str, Any]
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        allowed = {
            "store_name",
            "brand_name",
            "name",
            "industry",
            "category",
            "address",
            "contact",
            "product_or_service",
            "product",
            "service",
            "offer_name",
            "offer_category",
            "price_facts",
            "promotion_facts",
            "target_audience",
            "audience",
            "scenes",
            "selling_points",
            "proof_points",
            "required_facts",
            "forbidden_claims",
        }
        if set(payload) - allowed:
            self._legacy_mapping_required()
        store_name = self._first_text(payload, "store_name", "brand_name", "name")
        offer_name = self._first_text(
            payload,
            "product_or_service",
            "product",
            "service",
            "offer_name",
        )
        category = self._first_text(payload, "offer_category", "category", "industry")
        audience = self._first_text(payload, "target_audience", "audience")
        if not all((store_name, offer_name, category, audience)):
            self._legacy_mapping_required()
        brief = {
            "subject_type": "store",
            "offer": {
                "name": offer_name,
                "category": category,
                "price_facts": self._legacy_facts(payload.get("price_facts"), "legacy-price"),
                "promotion_facts": self._legacy_facts(
                    payload.get("promotion_facts"), "legacy-promotion"
                ),
            },
            "marketing_goal": project.primary_goal,
            "audience": {
                "primary": audience,
                "scenes": self._legacy_strings(payload.get("scenes")),
            },
            "selling_points": self._legacy_facts(payload.get("selling_points"), "legacy-selling"),
            "proof_points": self._legacy_facts(payload.get("proof_points"), "legacy-proof"),
            "required_facts": self._legacy_facts(payload.get("required_facts"), "legacy-required"),
            "forbidden_claims": self._legacy_strings(payload.get("forbidden_claims")),
            "asset_refs": [],
        }
        overrides = {"display_name": store_name}
        if payload.get("address") is not None:
            if not isinstance(payload["address"], str):
                self._legacy_mapping_required()
            overrides["store_address"] = payload["address"]
        if payload.get("contact") is not None:
            if not isinstance(payload["contact"], str):
                self._legacy_mapping_required()
            overrides["phone"] = payload["contact"]
        return brief, overrides

    @staticmethod
    def _first_text(payload: dict[str, Any], *keys: str) -> str:
        for key in keys:
            value = payload.get(key)
            if value is None:
                continue
            if not isinstance(value, str):
                BrandProjectService._legacy_mapping_required()
            if value.strip():
                return value.strip()
        return ""

    @staticmethod
    def _legacy_strings(value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            raw = value.splitlines()
        elif isinstance(value, list):
            raw = value
        else:
            BrandProjectService._legacy_mapping_required()
        if any(not isinstance(item, str) for item in raw):
            BrandProjectService._legacy_mapping_required()
        items = [item.strip() for item in raw if item.strip()]
        if len(items) != len(set(items)):
            BrandProjectService._legacy_mapping_required()
        return items

    @staticmethod
    def _legacy_facts(value: Any, prefix: str) -> list[dict[str, Any]]:
        if isinstance(value, list) and value and all(isinstance(item, dict) for item in value):
            try:
                facts = [ContextFact.model_validate(item) for item in value]
            except ValidationError:
                BrandProjectService._legacy_mapping_required()
            if len({fact.fact_id for fact in facts}) != len(facts):
                BrandProjectService._legacy_mapping_required()
            return [fact.model_dump(mode="json") for fact in facts]
        items = BrandProjectService._legacy_strings(value)
        return [
            {"fact_id": f"{prefix}-{index}", "text": text, "source": "user"}
            for index, text in enumerate(items, start=1)
        ]

    @staticmethod
    def _legacy_mapping_required() -> None:
        raise ProjectContextError(
            "PROJECT_CONTEXT_LEGACY_MAPPING_REQUIRED",
            "旧项目资料无法安全转换，请先补全项目资料",
        )

    def _resolve_brand_context(
        self,
        brand_id: str,
        *,
        expected_domain_revision: int | None,
        project_overrides: dict[str, Any],
        historical_media_override_fields: set[str] | None = None,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        historical_media_override_fields = historical_media_override_fields or set()
        current = self.asset_repository.domain_snapshot_metadata("brand", brand_id)
        if not current:
            raise ProjectContextError("PROJECT_BRAND_NOT_FOUND", "这个品牌已不存在，请重新选择")
        if current.get("status") != "ready":
            raise ProjectContextError(
                "PROJECT_BRAND_NOT_AVAILABLE",
                "这个品牌当前不可用于新项目",
            )
        revision = current.get("domain_revision")
        if not isinstance(revision, int) or isinstance(revision, bool) or revision < 1:
            raise ProjectContextError(
                "PROJECT_BRAND_REVISION_NOT_FOUND",
                "品牌历史版本无法读取，请保留当前项目资料并联系支持",
            )
        if expected_domain_revision is not None and revision != expected_domain_revision:
            raise ProjectContextError(
                "PROJECT_CONTEXT_CONFLICT",
                "项目信息已在其他位置更新，请刷新后重试",
            )
        historical = self._exact_brand_revision(brand_id, revision)
        if not historical:
            raise ProjectContextError(
                "PROJECT_BRAND_REVISION_NOT_FOUND",
                "品牌历史版本无法读取，请保留当前项目资料并联系支持",
            )
        source = validate_brand_domain_revision(
            historical,
            expected_brand_id=brand_id,
            expected_revision=revision,
        )
        values = {
            "display_name": source["brand_name"],
            "logo_ref": self._pin_current_media(source.get("logo_asset_id"), expected_kind="image"),
            "store_address": source["store_address"],
            "phone": source["phone"],
            "primary_color": source["primary_color"],
            "secondary_color": source["secondary_color"],
            "font_family": source["font_family"],
            "default_subtitle_style": source["default_subtitle_style"],
            "default_bgm_ref": self._pin_current_media(
                source.get("default_bgm_asset_id"), expected_kind="audio"
            ),
            "ending_card_text": source["ending_card_text"],
            "coupon_phrase": source["coupon_phrase"],
        }
        unknown = set(project_overrides) - set(_BRAND_VALUE_FIELDS)
        if unknown:
            raise ProjectContextError(
                "PROJECT_BRAND_CONTEXT_UNTRUSTED",
                f"unsupported project override: {sorted(unknown)[0]}",
            )
        for field, value in project_overrides.items():
            if field in _MEDIA_OVERRIDE_FIELDS:
                value = self._validate_media_ref(
                    value,
                    expected_kind=_MEDIA_OVERRIDE_FIELDS[field],
                    require_current=field not in historical_media_override_fields,
                )
            values[field] = deepcopy(value)
        return (
            {
                "brand_id": brand_id,
                "domain_revision": revision,
                "values": values,
                "overridden_fields": sorted(project_overrides),
            },
            source,
        )

    def _pin_current_media(self, asset_id: Any, *, expected_kind: str) -> dict[str, str] | None:
        if asset_id is None:
            return None
        if not isinstance(asset_id, str) or not asset_id:
            raise ProjectContextError(
                "PROJECT_BRAND_REVISION_NOT_FOUND",
                "品牌历史版本无法读取，请保留当前项目资料并联系支持",
            )
        asset = self.asset_repository.get_asset(asset_id)
        if not asset or asset.get("status") != "ready":
            raise ProjectContextError(
                "PROJECT_BRAND_ASSET_REVISION_MISSING",
                f"brand {expected_kind} asset is unavailable: {asset_id}",
            )
        if asset.get("media_kind") != expected_kind:
            raise ProjectContextError(
                "PROJECT_BRAND_ASSET_REVISION_MISSING",
                f"brand asset has wrong type: {asset_id}",
            )
        revision_id = asset.get("current_revision_id")
        if not isinstance(revision_id, str):
            revision_id = ""
        if not revision_id or not self.asset_repository.get_asset_revision(asset_id, revision_id):
            raise ProjectContextError(
                "PROJECT_BRAND_ASSET_REVISION_MISSING",
                f"brand asset revision is unavailable: {asset_id}",
            )
        return {"asset_id": asset_id, "asset_revision": revision_id}

    def _validate_media_ref(
        self,
        value: Any,
        *,
        expected_kind: str,
        require_current: bool,
    ) -> dict[str, str]:
        if not isinstance(value, dict):
            raise ProjectContextError(
                "PROJECT_BRAND_CONTEXT_UNTRUSTED",
                "media override must pin a revision",
            )
        if set(value) != {"asset_id", "asset_revision"}:
            self._legacy_mapping_required()
        asset_id = value.get("asset_id")
        revision_id = value.get("asset_revision")
        if not isinstance(asset_id, str) or not asset_id:
            self._legacy_mapping_required()
        if not isinstance(revision_id, str) or not revision_id:
            self._legacy_mapping_required()
        revision = self.asset_repository.get_asset_revision(asset_id, revision_id)
        if not revision:
            raise ProjectContextError(
                "PROJECT_BRAND_ASSET_REVISION_MISSING",
                f"project asset revision is unavailable: {asset_id}@{revision_id}",
            )
        if revision.get("media_kind") != expected_kind:
            raise ProjectContextError(
                "PROJECT_BRAND_ASSET_REVISION_MISSING",
                f"project asset has wrong type: {asset_id}",
            )
        if require_current and (
            revision.get("status") != "ready" or revision.get("current_revision_id") != revision_id
        ):
            raise ProjectContextError(
                "PROJECT_BRAND_ASSET_REVISION_MISSING",
                f"project asset is not the current ready revision: {asset_id}@{revision_id}",
            )
        return {"asset_id": asset_id, "asset_revision": revision_id}

    def _exact_brand_revision(self, brand_id: str, revision: int) -> dict[str, Any] | None:
        try:
            return self.asset_repository.get_domain_revision("brand", brand_id, revision)
        except (TypeError, ValueError) as exc:
            raise ProjectContextError(
                "PROJECT_BRAND_REVISION_NOT_FOUND",
                "品牌历史版本无法读取，请保留当前项目资料并联系支持",
            ) from exc

    @contextmanager
    def _guard_current_brand(
        self,
        brand_id: str,
        revision: int,
        source: dict[str, Any],
        *,
        brand_context: dict[str, Any],
        historical_media_override_fields: set[str] | None = None,
    ) -> Iterator[None]:
        historical_media_override_fields = historical_media_override_fields or set()
        current_media: list[tuple[str, str, str]] = []
        exact_media: list[tuple[str, str, str]] = []
        for field, media_kind in _MEDIA_OVERRIDE_FIELDS.items():
            ref = brand_context["values"][field]
            if ref is None:
                continue
            candidate = (ref["asset_id"], ref["asset_revision"], media_kind)
            if field in historical_media_override_fields:
                exact_media.append(candidate)
            else:
                current_media.append(candidate)
        try:
            with self.asset_repository.guard_domain_revision(
                "brand",
                brand_id,
                revision,
                expected_status="ready",
                expected_payload=source,
                expected_current_media=tuple(current_media),
                expected_exact_media=tuple(exact_media),
            ):
                yield
        except DomainRevisionGuardError as exc:
            if exc.reason == "not_found":
                raise ProjectContextError(
                    "PROJECT_BRAND_NOT_FOUND",
                    "这个品牌已不存在，请重新选择",
                ) from exc
            if exc.reason == "status_changed":
                raise ProjectContextError(
                    "PROJECT_BRAND_NOT_AVAILABLE",
                    "这个品牌当前不可用于新项目",
                ) from exc
            if exc.reason == "revision_changed":
                raise ProjectContextError(
                    "PROJECT_CONTEXT_CONFLICT",
                    "项目信息已在其他位置更新，请刷新后重试",
                ) from exc
            if exc.reason == "media_revision_changed":
                raise ProjectContextError(
                    "PROJECT_CONTEXT_CONFLICT",
                    "项目信息已在其他位置更新，请刷新后重试",
                ) from exc
            if exc.reason.startswith("media_"):
                raise ProjectContextError(
                    "PROJECT_BRAND_ASSET_REVISION_MISSING",
                    "品牌素材版本不完整，请到企业资产库检查",
                ) from exc
            raise ProjectContextError(
                "PROJECT_BRAND_REVISION_NOT_FOUND",
                "品牌历史版本无法读取，请保留当前项目资料并联系支持",
            ) from exc


class ProjectContextResolver:
    """Resolve immutable v1/v2/v3 snapshots for application execution."""

    def __init__(self, app_repository: AppCenterRepository, asset_repository: Any):
        self.app_repository = app_repository
        self.asset_repository = asset_repository
        self.app_repository.set_asset_repository(asset_repository)

    def resolve_for_run(
        self, project_id: str, context_snapshot_id: str | None = None
    ) -> ApplicationContext:
        project = self.app_repository.get_project(project_id)
        snapshot_id = context_snapshot_id or project.current_context_snapshot_id
        if not snapshot_id:
            raise ProjectContextError("PROJECT_CONTEXT_MISSING", "project has no context snapshot")
        snapshot = self.app_repository.get_context_snapshot(snapshot_id)
        if snapshot.project_id != project_id:
            raise ProjectContextError(
                "PROJECT_CONTEXT_CROSS_PROJECT_REF",
                "context snapshot belongs to another project",
            )
        self.app_repository.verify_context_snapshot_integrity(snapshot)
        if snapshot.schema_version == 3:
            # Structural validation is independent from external references so
            # brand-specific failures can retain their contract error codes.
            project_context_v3_to_v2(snapshot.payload)
            self._verify_v3(snapshot)
            self.app_repository.validate_context_snapshot_payload(
                snapshot.project_id,
                snapshot.payload,
                schema_version=3,
            )
            business_payload = deepcopy(snapshot.payload["project_brief"])
            brand = snapshot.payload["brand_context"]
            brand_summary = (
                {
                    "brand_id": brand["brand_id"],
                    "domain_revision": brand["domain_revision"],
                    "display_name": brand["values"]["display_name"],
                    "values": deepcopy(brand["values"]),
                    "overridden_fields": list(brand["overridden_fields"]),
                }
                if brand is not None
                else None
            )
        else:
            self.app_repository.validate_context_snapshot_payload(
                snapshot.project_id,
                snapshot.payload,
                schema_version=snapshot.schema_version,
            )
            business_payload = deepcopy(snapshot.payload)
            brand_summary = None
        return ApplicationContext(
            project_id=project_id,
            context_snapshot_id=snapshot.context_snapshot_id,
            source_schema_version=snapshot.schema_version,
            business_payload=business_payload,
            brand_summary=brand_summary,
        )

    def resolve_v2_projection(
        self, project_id: str, context_snapshot_id: str | None = None
    ) -> dict[str, Any]:
        context = self.resolve_for_run(project_id, context_snapshot_id)
        if context.source_schema_version == 3:
            snapshot = self.app_repository.get_context_snapshot(context.context_snapshot_id)
            return project_context_v3_to_v2(snapshot.payload)
        return deepcopy(context.business_payload)

    def resolve_for_application(
        self,
        project_id: str,
        context_snapshot_id: str,
        *,
        app_id: str,
    ) -> dict[str, Any]:
        """Return one app-specific view of the immutable trusted snapshot."""

        brand_fields = {
            "builtin.marketing-copy": {
                "display_name",
                "store_address",
                "phone",
                "coupon_phrase",
                "ending_card_text",
            },
            "builtin.viral-titles": {"display_name"},
            "builtin.douyin-carousel": {
                "display_name",
                "primary_color",
                "secondary_color",
                "font_family",
                "logo_ref",
                "ending_card_text",
                "coupon_phrase",
            },
            "builtin.digital-human-video": {
                "display_name",
                "store_address",
                "phone",
                "primary_color",
                "secondary_color",
                "font_family",
                "default_subtitle_style",
                "logo_ref",
                "default_bgm_ref",
                "ending_card_text",
                "coupon_phrase",
            },
        }
        fields = brand_fields.get(app_id)
        if fields is None:
            raise ProjectContextError(
                "PROJECT_CONTEXT_APP_UNSUPPORTED",
                f"unsupported application context consumer: {app_id}",
            )
        context = self.resolve_for_run(project_id, context_snapshot_id)
        brand: dict[str, Any] | None = None
        if context.brand_summary is not None:
            values = context.brand_summary["values"]
            brand = {
                "display_name": values["display_name"],
                "values": {key: deepcopy(value) for key, value in values.items() if key in fields},
                "overridden_fields": [
                    key for key in context.brand_summary["overridden_fields"] if key in fields
                ],
            }
        return {
            "schema_version": 1,
            "app_id": app_id,
            "lineage": {
                "project_id": context.project_id,
                "context_snapshot_id": context.context_snapshot_id,
                "source_schema_version": context.source_schema_version,
            },
            "project_brief": deepcopy(context.business_payload),
            "brand": brand,
        }

    def resolve_exact_asset_path(
        self, ref: dict[str, Any] | None, *, variant_role: str | None = None
    ) -> Path | None:
        """Resolve one pinned media revision without falling back to current."""

        if not isinstance(ref, dict):
            return None
        asset_id = str(ref.get("asset_id") or "")
        revision_id = str(ref.get("asset_revision") or "")
        if not asset_id or not revision_id:
            return None
        path = self.asset_repository.get_revision_path(
            asset_id,
            variant_role=variant_role,
            revision_id=revision_id,
        )
        if path is None and variant_role is not None:
            path = self.asset_repository.get_revision_path(
                asset_id,
                revision_id=revision_id,
            )
        return path

    def resolve_v2_projection_dto(
        self, project_id: str, context_snapshot_id: str | None = None
    ) -> dict[str, Any]:
        context = self.resolve_for_run(project_id, context_snapshot_id)
        payload = self.resolve_v2_projection(project_id, context.context_snapshot_id)
        return {
            "projection_kind": "context_snapshot_v2",
            "project_id": project_id,
            "source_context_snapshot_id": context.context_snapshot_id,
            "schema_version": 2,
            "payload": payload,
            "projection_fingerprint": context_projection_fingerprint(
                project_id=project_id,
                source_context_snapshot_id=context.context_snapshot_id,
                payload=payload,
            ),
        }

    def _verify_v3(self, snapshot: ContextSnapshot) -> None:
        brand = snapshot.payload["brand_context"]
        if brand is None:
            if snapshot.source_brand_id or snapshot.source_brand_revision_id:
                self._untrusted()
            return
        revision = int(brand["domain_revision"])
        if snapshot.source_brand_id != brand[
            "brand_id"
        ] or snapshot.source_brand_revision_id != str(revision):
            self._untrusted()
        try:
            historical = self.asset_repository.get_domain_revision(
                "brand", brand["brand_id"], revision
            )
        except (TypeError, ValueError) as exc:
            raise ProjectContextError(
                "PROJECT_BRAND_REVISION_NOT_FOUND",
                "品牌历史版本无法读取，请保留当前项目资料并联系支持",
            ) from exc
        if historical is None:
            raise ProjectContextError(
                "PROJECT_BRAND_REVISION_NOT_FOUND",
                "品牌历史版本无法读取，请保留当前项目资料并联系支持",
            )
        source = validate_brand_domain_revision(
            historical,
            expected_brand_id=brand["brand_id"],
            expected_revision=revision,
        )
        overridden = set(brand["overridden_fields"])
        self._verify_media_ref(
            brand["values"]["logo_ref"],
            expected_asset_id=source.get("logo_asset_id"),
            expected_kind="image",
            is_overridden="logo_ref" in overridden,
        )
        self._verify_media_ref(
            brand["values"]["default_bgm_ref"],
            expected_asset_id=source.get("default_bgm_asset_id"),
            expected_kind="audio",
            is_overridden="default_bgm_ref" in overridden,
        )
        source_values = {
            "display_name": source["brand_name"],
            "store_address": source["store_address"],
            "phone": source["phone"],
            "primary_color": source["primary_color"],
            "secondary_color": source["secondary_color"],
            "font_family": source["font_family"],
            "default_subtitle_style": source["default_subtitle_style"],
            "ending_card_text": source["ending_card_text"],
            "coupon_phrase": source["coupon_phrase"],
        }
        for field, expected in source_values.items():
            if field not in overridden and brand["values"][field] != expected:
                self._untrusted()

    def _verify_media_ref(
        self,
        ref: dict[str, Any] | None,
        *,
        expected_asset_id: Any,
        expected_kind: str,
        is_overridden: bool,
    ) -> None:
        if expected_asset_id is not None and (
            not isinstance(expected_asset_id, str) or not expected_asset_id
        ):
            self._untrusted()
        expected_id = expected_asset_id
        actual_id = ref.get("asset_id") if ref is not None else None
        if actual_id is not None and (not isinstance(actual_id, str) or not actual_id):
            self._untrusted()
        if not is_overridden and actual_id != expected_id:
            self._untrusted()
        if ref is None:
            return
        revision_id = ref.get("asset_revision")
        if not isinstance(revision_id, str) or not revision_id:
            self._untrusted()
        revision = self.asset_repository.get_asset_revision(actual_id, revision_id)
        if revision is None or revision.get("media_kind") != expected_kind:
            raise ProjectContextError(
                "PROJECT_BRAND_ASSET_REVISION_MISSING",
                "品牌素材版本不完整，请到企业资产库检查",
            )

    @staticmethod
    def _untrusted() -> None:
        raise ProjectContextError(
            "PROJECT_BRAND_CONTEXT_UNTRUSTED",
            "stored brand context does not match its server-owned source revision",
        )
