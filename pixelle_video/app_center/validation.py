"""Shared fail-closed validation for business payload boundaries."""

from __future__ import annotations

from typing import Any

FORBIDDEN_BUSINESS_FIELDS = frozenset(
    {
        "provider",
        "model",
        "base_url",
        "api_key",
        "model_profile_ref",
        "authorization",
        "cookie",
        "provider_path",
        "raw_provider_response",
    }
)


def find_forbidden_business_field(value: Any) -> str | None:
    if isinstance(value, dict):
        for key, child in value.items():
            normalized = str(key).strip().lower()
            if normalized in FORBIDDEN_BUSINESS_FIELDS:
                return normalized
            found = find_forbidden_business_field(child)
            if found:
                return found
    elif isinstance(value, (list, tuple)):
        for child in value:
            found = find_forbidden_business_field(child)
            if found:
                return found
    return None


def validate_business_payload(value: Any, *, label: str) -> None:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a JSON object")
    found = find_forbidden_business_field(value)
    if found:
        raise ValueError(f"{label} contains forbidden field: {found}")
