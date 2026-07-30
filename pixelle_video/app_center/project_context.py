"""Versioned ContentProject context validation.

Context snapshots are immutable business inputs. This module deliberately
contains no model/provider configuration and never resolves filesystem paths.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .validation import validate_business_payload


class ProjectContextError(ValueError):
    """Stable, UI-safe validation failure for project context."""

    def __init__(self, code: str, message: str):
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class ContextFact(_StrictModel):
    fact_id: str = Field(min_length=1, max_length=200)
    text: str = Field(min_length=1, max_length=500)
    source: Literal["user", "brand_revision", "asset_metadata", "artifact_version"]
    source_ref: str | None = Field(default=None, max_length=200)


class StoreOrBrand(_StrictModel):
    name: str = Field(min_length=1, max_length=200)
    industry: str = Field(min_length=1, max_length=100)
    address: str | None = Field(default=None, max_length=500)
    contact: str | None = Field(default=None, max_length=200)


class Offer(_StrictModel):
    name: str = Field(min_length=1, max_length=200)
    category: str = Field(min_length=1, max_length=100)
    price_facts: list[ContextFact] = Field(max_length=50)
    promotion_facts: list[ContextFact] = Field(max_length=50)


class Audience(_StrictModel):
    primary: str = Field(min_length=1, max_length=300)
    scenes: list[str] = Field(max_length=20)


class AssetRevisionRef(_StrictModel):
    asset_id: str = Field(min_length=1, max_length=200)
    asset_revision: str = Field(min_length=1, max_length=200)


class ContextSnapshotV2(_StrictModel):
    schema_version: Literal[2]
    subject_type: Literal["store", "brand", "product", "service", "campaign"]
    store_or_brand: StoreOrBrand
    offer: Offer
    audience: Audience
    selling_points: list[ContextFact] = Field(max_length=50)
    proof_points: list[ContextFact] = Field(max_length=50)
    required_facts: list[ContextFact] = Field(max_length=50)
    forbidden_claims: list[str] = Field(max_length=50)
    asset_refs: list[AssetRevisionRef] = Field(max_length=100)
    brand_revision_ref: str | None = Field(default=None, max_length=200)


class BrandValues(_StrictModel):
    display_name: str = Field(min_length=1, max_length=200)
    logo_ref: AssetRevisionRef | None
    store_address: str = Field(max_length=500)
    phone: str = Field(max_length=200)
    primary_color: str = Field(pattern=r"^#[0-9A-Fa-f]{6}$")
    secondary_color: str = Field(pattern=r"^#[0-9A-Fa-f]{6}$")
    font_family: str = Field(max_length=200)
    default_subtitle_style: str = Field(max_length=200)
    default_bgm_ref: AssetRevisionRef | None
    ending_card_text: str = Field(max_length=500)
    coupon_phrase: str = Field(max_length=500)


BrandOverrideField = Literal[
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
]


class BrandContext(_StrictModel):
    brand_id: str = Field(min_length=1, max_length=200)
    domain_revision: int = Field(ge=1)
    values: BrandValues
    overridden_fields: list[BrandOverrideField] = Field(max_length=11)


class ProjectBrief(_StrictModel):
    subject_type: Literal["store", "brand", "product", "service", "campaign"]
    offer: Offer
    marketing_goal: str = Field(min_length=1, max_length=1000)
    audience: Audience
    selling_points: list[ContextFact] = Field(max_length=50)
    proof_points: list[ContextFact] = Field(max_length=50)
    required_facts: list[ContextFact] = Field(max_length=50)
    forbidden_claims: list[str] = Field(max_length=50)
    asset_refs: list[AssetRevisionRef] = Field(max_length=100)


class ContextSnapshotV3(_StrictModel):
    schema_version: Literal[3]
    brand_context: BrandContext | None
    project_brief: ProjectBrief


@dataclass(frozen=True)
class ApplicationContext:
    """Read-only application input resolved from an immutable snapshot."""

    project_id: str
    context_snapshot_id: str
    source_schema_version: int
    business_payload: dict[str, Any]
    brand_summary: dict[str, Any] | None


ArtifactVersionResolver = Callable[[str], Any | None]
AssetRevisionResolver = Callable[[str, str], Any | None]


def context_projection_fingerprint(
    *,
    project_id: str,
    source_context_snapshot_id: str,
    payload: dict[str, Any],
) -> str:
    """Fingerprint the explicit v2 projection DTO, not its v3 source row."""

    envelope = {
        "projection_kind": "context_snapshot_v2",
        "project_id": project_id,
        "source_context_snapshot_id": source_context_snapshot_id,
        "schema_version": 2,
        "payload": payload,
    }
    encoded = json.dumps(
        envelope,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _raise_invalid(message: str) -> None:
    raise ProjectContextError("PROJECT_CONTEXT_INVALID", message)


def _validate_unique_strings(values: list[str], field: str) -> None:
    normalized = [value.strip() for value in values]
    if any(not value for value in normalized):
        _raise_invalid(f"{field} contains an empty value")
    if len(set(normalized)) != len(normalized):
        _raise_invalid(f"{field} contains duplicate values")


def project_context_v3_to_v2(payload: dict[str, Any]) -> dict[str, Any]:
    """Return the frozen, read-only v3→v2 compatibility projection."""

    try:
        context = ContextSnapshotV3.model_validate(payload)
    except ValidationError as exc:
        first = exc.errors(include_url=False)[0]
        path = ".".join(str(item) for item in first.get("loc", ())) or "payload"
        _raise_invalid(f"{path}: {first.get('msg', 'invalid value')}")
    brief = context.project_brief
    brand = context.brand_context
    brand_values = brand.values if brand is not None else None
    asset_refs: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    refs = list(brief.asset_refs)
    if brand_values is not None:
        refs.extend(
            item
            for item in (brand_values.logo_ref, brand_values.default_bgm_ref)
            if item is not None
        )
    for item in refs:
        key = (item.asset_id, item.asset_revision)
        if key not in seen:
            seen.add(key)
            asset_refs.append(item.model_dump(mode="json"))
    return {
        "schema_version": 2,
        "subject_type": brief.subject_type,
        "store_or_brand": {
            "name": (brand_values.display_name if brand_values is not None else brief.offer.name),
            "industry": brief.offer.category,
            "address": (brand_values.store_address or None if brand_values is not None else None),
            "contact": (brand_values.phone or None if brand_values is not None else None),
        },
        "offer": brief.offer.model_dump(mode="json"),
        "audience": brief.audience.model_dump(mode="json"),
        "selling_points": [item.model_dump(mode="json") for item in brief.selling_points],
        "proof_points": [item.model_dump(mode="json") for item in brief.proof_points],
        "required_facts": [item.model_dump(mode="json") for item in brief.required_facts],
        "forbidden_claims": list(brief.forbidden_claims),
        "asset_refs": asset_refs,
        "brand_revision_ref": (
            f"brand:{brand.brand_id}@{brand.domain_revision}" if brand is not None else None
        ),
    }


def validate_context_snapshot(
    payload: dict[str, Any],
    *,
    schema_version: int,
    project_id: str,
    artifact_version_resolver: ArtifactVersionResolver | None = None,
    asset_revision_resolver: AssetRevisionResolver | None = None,
) -> None:
    """Validate a v1/v2/v3 snapshot without mutating or normalizing its payload."""

    validate_business_payload(payload, label="context snapshot")
    if schema_version == 1:
        return
    if schema_version not in {2, 3}:
        raise ProjectContextError(
            "PROJECT_CONTEXT_SCHEMA_UNSUPPORTED",
            f"unsupported context schema version: {schema_version}",
        )
    try:
        context = (
            ContextSnapshotV2.model_validate(payload)
            if schema_version == 2
            else ContextSnapshotV3.model_validate(payload)
        )
    except ValidationError as exc:
        first = exc.errors(include_url=False)[0]
        path = ".".join(str(item) for item in first.get("loc", ())) or "payload"
        _raise_invalid(f"{path}: {first.get('msg', 'invalid value')}")

    brief = context if isinstance(context, ContextSnapshotV2) else context.project_brief
    _validate_unique_strings(brief.audience.scenes, "audience.scenes")
    _validate_unique_strings(brief.forbidden_claims, "forbidden_claims")
    if isinstance(context, ContextSnapshotV3) and context.brand_context is not None:
        overridden = context.brand_context.overridden_fields
        if len(set(overridden)) != len(overridden):
            _raise_invalid("brand_context.overridden_fields contains duplicate values")

    seen_assets: set[tuple[str, str]] = set()
    asset_refs = list(brief.asset_refs)
    if isinstance(context, ContextSnapshotV3) and context.brand_context is not None:
        brand_values = context.brand_context.values
        asset_refs.extend(
            ref for ref in (brand_values.logo_ref, brand_values.default_bgm_ref) if ref is not None
        )
    for ref in asset_refs:
        key = (ref.asset_id, ref.asset_revision)
        if key in seen_assets:
            # A project may intentionally use the same pinned asset in the
            # brand defaults and the brief; validate it once.
            continue
        seen_assets.add(key)
        if asset_revision_resolver is None or asset_revision_resolver(*key) is None:
            raise ProjectContextError(
                "PROJECT_CONTEXT_ASSET_NOT_FOUND",
                f"asset revision not found: {ref.asset_id}@{ref.asset_revision}",
            )

    fact_groups = (
        brief.offer.price_facts,
        brief.offer.promotion_facts,
        brief.selling_points,
        brief.proof_points,
        brief.required_facts,
    )
    seen_facts: dict[str, tuple[str, str, str | None]] = {}
    for fact in (item for group in fact_groups for item in group):
        signature = (fact.text, fact.source, fact.source_ref)
        previous = seen_facts.get(fact.fact_id)
        if previous is not None and previous != signature:
            raise ProjectContextError(
                "PROJECT_CONTEXT_FACT_CONFLICT",
                f"fact_id has conflicting values: {fact.fact_id}",
            )
        seen_facts[fact.fact_id] = signature
        if fact.source == "artifact_version":
            if not fact.source_ref:
                _raise_invalid(f"artifact fact requires source_ref: {fact.fact_id}")
            version = (
                artifact_version_resolver(fact.source_ref)
                if artifact_version_resolver is not None
                else None
            )
            if version is None:
                _raise_invalid(f"artifact version not found: {fact.source_ref}")
            version_project_id = (
                version.get("project_id")
                if isinstance(version, dict)
                else getattr(version, "project_id", None)
            )
            if version_project_id != project_id:
                raise ProjectContextError(
                    "PROJECT_CONTEXT_CROSS_PROJECT_REF",
                    f"artifact version belongs to another project: {fact.source_ref}",
                )
