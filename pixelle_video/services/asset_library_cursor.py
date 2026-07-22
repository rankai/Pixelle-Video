"""Stable cursor and query-consistent facet primitives for UX-0.

The V2 endpoint does not consume this module yet.  It is the executable
reference for the contract that UX-1 pagination must implement: opaque signed
cursors carry the sort, filter hash, index generation and last sort tuple.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
from collections import Counter
from functools import cmp_to_key
from typing import Any

from api.schemas.asset_library_ux0 import CursorEnvelope, CursorSort


class CursorContractError(ValueError):
    code = "cursor_invalid"


class CursorFilterMismatchError(CursorContractError):
    code = "cursor_filter_mismatch"


class CursorStaleError(CursorContractError):
    code = "cursor_stale"


def canonical_filter_hash(filters: dict[str, Any] | None) -> str:
    payload = json.dumps(filters or {}, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _sign(payload: dict[str, Any], secret: str) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hmac.new(secret.encode("utf-8"), encoded.encode("utf-8"), hashlib.sha256).hexdigest()


def encode_cursor(
    *,
    sort: CursorSort | str,
    filters: dict[str, Any] | None,
    index_generation: int,
    last_tuple: list[str | int | float | None],
    secret: str,
) -> str:
    sort_value = CursorSort(sort)
    body = {
        "version": 1,
        "sort": sort_value.value,
        "filter_hash": canonical_filter_hash(filters),
        "index_generation": index_generation,
        "last_tuple": last_tuple,
    }
    envelope = {**body, "signature": _sign(body, secret)}
    serialized = json.dumps(envelope, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return base64.urlsafe_b64encode(serialized.encode("utf-8")).decode("ascii").rstrip("=")


def decode_cursor(cursor: str, *, secret: str) -> CursorEnvelope:
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8"))
        signature = str(payload.pop("signature"))
        expected = _sign(payload, secret)
        if not hmac.compare_digest(signature, expected):
            raise CursorContractError("cursor_signature_invalid")
        return CursorEnvelope(**{**payload, "signature": signature})
    except CursorContractError:
        raise
    except Exception as exc:  # pragma: no cover - boundary normalization
        raise CursorContractError("cursor_invalid") from exc


def _normalized_name(item: dict[str, Any]) -> str:
    return " ".join(str(item.get("name") or "").casefold().split())


def sort_tuple(item: dict[str, Any], sort: CursorSort | str) -> list[str | None]:
    sort_value = CursorSort(sort)
    if sort_value is CursorSort.RECENT:
        return [
            str(item.get("last_used_at")) if item.get("last_used_at") else None,
            str(item.get("updated_at") or ""),
            str(item.get("kind") or ""),
            str(item.get("resource_id") or ""),
        ]
    if sort_value is CursorSort.UPDATED:
        return [
            str(item.get("updated_at") or ""),
            str(item.get("kind") or ""),
            str(item.get("resource_id") or ""),
        ]
    return [
        _normalized_name(item),
        str(item.get("kind") or ""),
        str(item.get("resource_id") or ""),
    ]


def _compare(a: Any, b: Any, *, descending: bool, nulls_last: bool = False) -> int:
    if a == b:
        return 0
    if a is None:
        return 1 if nulls_last else -1
    if b is None:
        return -1 if nulls_last else 1
    result = -1 if a < b else 1
    return -result if descending else result


def compare_sort_tuples(left: list[Any], right: list[Any], sort: CursorSort | str) -> int:
    sort_value = CursorSort(sort)
    for index, (a, b) in enumerate(zip(left, right)):
        descending = (sort_value in {CursorSort.RECENT, CursorSort.UPDATED}) and index == 0
        nulls_last = sort_value is CursorSort.RECENT and index == 0
        compared = _compare(a, b, descending=descending, nulls_last=nulls_last)
        if compared:
            return compared
    return _compare(len(left), len(right), descending=False)


def _matches(item: dict[str, Any], filters: dict[str, Any]) -> bool:
    kind = filters.get("kind")
    if kind and item.get("kind") != kind:
        return False
    status = filters.get("status")
    if status and item.get("status") != status:
        return False
    favorite = filters.get("favorite")
    if favorite is not None and bool(item.get("favorite")) != bool(favorite):
        return False
    tag = filters.get("tag")
    if tag and tag not in set(item.get("tags") or []):
        return False
    query = str(filters.get("query") or "").casefold().strip()
    if query and query not in str(item.get("name") or "").casefold():
        return False
    return True


def query_consistent_facets(items: list[dict[str, Any]], filters: dict[str, Any]) -> dict[str, dict[str, int]]:
    """Return facets while ignoring each facet's own dimension constraint."""

    dimensions = {
        "kinds": "kind",
        "statuses": "status",
        "tags": "tag",
    }
    result: dict[str, dict[str, int]] = {}
    for output_key, ignored_key in dimensions.items():
        constrained = {key: value for key, value in filters.items() if key != ignored_key}
        counters: Counter[str] = Counter()
        for item in items:
            if not _matches(item, constrained):
                continue
            values = [item.get(ignored_key)] if ignored_key != "tag" else list(item.get("tags") or [])
            counters.update(str(value) for value in values if value not in (None, ""))
        result[output_key] = dict(sorted(counters.items()))
    return result


def paginate_library_items(
    items: list[dict[str, Any]],
    *,
    filters: dict[str, Any] | None = None,
    sort: CursorSort | str = CursorSort.RECENT,
    page_size: int = 50,
    index_generation: int = 1,
    cursor: str | None = None,
    secret: str = "ux0-fixture-secret",
) -> dict[str, Any]:
    if page_size < 1 or page_size > 500:
        raise ValueError("page_size_out_of_range")
    active_filters = dict(filters or {})
    sort_value = CursorSort(sort)
    filter_hash = canonical_filter_hash(active_filters)
    decoded = decode_cursor(cursor, secret=secret) if cursor else None
    if decoded:
        if decoded.filter_hash != filter_hash:
            raise CursorFilterMismatchError("cursor_filter_mismatch")
        if decoded.sort is not sort_value:
            raise CursorFilterMismatchError("cursor_sort_mismatch")
        if decoded.index_generation != index_generation:
            raise CursorStaleError("cursor_stale")

    matched = [item for item in items if _matches(item, active_filters)]
    ordered = sorted(
        matched,
        key=cmp_to_key(lambda left, right: compare_sort_tuples(sort_tuple(left, sort_value), sort_tuple(right, sort_value), sort_value)),
    )
    if decoded:
        ordered = [
            item
            for item in ordered
            if compare_sort_tuples(sort_tuple(item, sort_value), decoded.last_tuple, sort_value) > 0
        ]
    page = ordered[:page_size]
    next_cursor = None
    if len(ordered) > page_size and page:
        next_cursor = encode_cursor(
            sort=sort_value,
            filters=active_filters,
            index_generation=index_generation,
            last_tuple=sort_tuple(page[-1], sort_value),
            secret=secret,
        )
    return {
        "items": page,
        "total": len(matched),
        "next_cursor": next_cursor,
        "index_generation": index_generation,
        "filter_hash": filter_hash,
        "facets": query_consistent_facets(items, active_filters),
    }


__all__ = [
    "CursorContractError",
    "CursorFilterMismatchError",
    "CursorStaleError",
    "canonical_filter_hash",
    "encode_cursor",
    "decode_cursor",
    "sort_tuple",
    "compare_sort_tuples",
    "query_consistent_facets",
    "paginate_library_items",
]
