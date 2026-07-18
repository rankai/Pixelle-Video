import hashlib
import json
import shutil
from pathlib import Path

import pytest
from pydantic import ValidationError

from api.config import APIConfig
from api.schemas.asset_library_ux0 import (
    DeferredUploadCreateRequest,
    DuplicatePolicy,
    FinalizeUploadRequest,
    TemplateLayoutContract,
)
from pixelle_video.services.asset_library_cursor import (
    CursorFilterMismatchError,
    CursorStaleError,
    paginate_library_items,
)
from pixelle_video.services.font_registry import resolve_registered_font
from pixelle_video.services.voice_profile_migration import dry_run_voice_profile_migration

FIXTURE_ROOT = Path("tests/fixtures/ux0")


def _load_json(path: str) -> dict:
    return json.loads((FIXTURE_ROOT / path).read_text(encoding="utf-8"))


def test_template_layout_contract_accepts_golden_and_rejects_unknown_or_missing_font():
    valid = _load_json("template-layout/valid.json")
    contract = TemplateLayoutContract(**valid)
    assert contract.canvas.width == 1080
    assert contract.video_subtitle.font_token == "brand_primary"

    with pytest.raises(ValidationError):
        TemplateLayoutContract(**_load_json("template-layout/unknown-field.json"))
    with pytest.raises(ValidationError, match="font_token_not_registered"):
        TemplateLayoutContract(**_load_json("template-layout/missing-font.json"))


def test_registered_template_font_is_a_bundled_artifact_with_exact_identity():
    identity = resolve_registered_font("noto-sans-sc-bold")
    assert identity is not None
    font_path = Path(str(identity["font_path"]))
    assert font_path.is_file()
    assert hashlib.sha256(font_path.read_bytes()).hexdigest() == identity["font_sha256"]
    assert identity["family"] == "Noto Sans CJK SC"
    assert identity["weight"] == 700


def test_deferred_upload_contract_locks_policy_and_restart_copy():
    request = DeferredUploadCreateRequest(
        filename="same.png",
        declared_bytes=10,
        target_kind="image",
        idempotency_key="fixture-001",
    )
    assert request.decision_mode == "deferred"
    assert FinalizeUploadRequest(duplicate_policy=DuplicatePolicy.REUSE_EXISTING)
    assert FinalizeUploadRequest(
        duplicate_policy=DuplicatePolicy.ATTACH_REVISION,
        target_asset_id="asset-1",
    )
    with pytest.raises(ValidationError, match="target_asset_id_required"):
        FinalizeUploadRequest(duplicate_policy=DuplicatePolicy.ATTACH_REVISION)
    with pytest.raises(ValidationError, match="target_asset_id_only"):
        FinalizeUploadRequest(
            duplicate_policy=DuplicatePolicy.REUSE_EXISTING,
            target_asset_id="asset-1",
        )
    assert _load_json("deferred-upload/cases.json")["restart_copy"] == "应用已重启，请重新选择原文件继续上传"


def test_voice_profile_dry_run_preserves_ids_and_reconciles_sessions(tmp_path):
    source = FIXTURE_ROOT / "voice-migration" / "legacy"
    data_root = tmp_path / "data"
    (data_root / "voice_references").mkdir(parents=True)
    for filename in source.iterdir():
        if filename.is_file():
            shutil.copy2(filename, data_root / "voice_references" / filename.name)
    sessions = tmp_path / "sessions"
    shutil.copytree(FIXTURE_ROOT / "voice-migration" / "sessions", sessions)

    report = dry_run_voice_profile_migration(
        data_root,
        session_root=sessions,
        ordinary_audio_manifest=data_root / "voice_references" / "audio_assets.json",
    )

    assert report["dry_run"] is True
    assert report["writes_performed"] == 0
    assert [item["voice_id"] for item in report["voice_profiles"]] == [
        "voice-legacy-001",
        "voice-legacy-002",
    ]
    assert report["session_reconciliation"]["all_references_resolvable"] is True
    assert report["session_reconciliation"]["references_resolved"] == 2
    assert report["ordinary_audio_excluded_from_voice_facet"][0]["resource_id"] == "bgm-ordinary-001"
    assert report["ready_for_review"] is True
    assert report["rollback"]["media_files_deleted"] is False


def test_cursor_fixture_has_no_overlap_and_stale_generation_is_explicit():
    fixture = _load_json("cursor-pages.json")
    items = fixture["items"]
    filters = {}
    page = paginate_library_items(
        items,
        filters=filters,
        page_size=4,
        index_generation=fixture["index_generation"],
        secret=fixture["secret"],
    )
    seen = [item["resource_id"] for item in page["items"]]
    cursor = page["next_cursor"]
    while cursor:
        page = paginate_library_items(
            items,
            filters=filters,
            page_size=4,
            index_generation=fixture["index_generation"],
            cursor=cursor,
            secret=fixture["secret"],
        )
        seen.extend(item["resource_id"] for item in page["items"])
        cursor = page["next_cursor"]
    assert len(seen) == len(items) == len(set(seen))
    assert page["facets"]["kinds"]["voice"] == 1

    first = paginate_library_items(
        items,
        filters=filters,
        page_size=4,
        index_generation=fixture["index_generation"],
        secret=fixture["secret"],
    )
    with pytest.raises(CursorStaleError, match="cursor_stale"):
        paginate_library_items(
            items,
            filters=filters,
            page_size=4,
            index_generation=fixture["index_generation"] + 1,
            cursor=first["next_cursor"],
            secret=fixture["secret"],
        )
    with pytest.raises(CursorFilterMismatchError, match="cursor_filter_mismatch"):
        paginate_library_items(
            items,
            filters={"kind": "image"},
            page_size=4,
            index_generation=fixture["index_generation"],
            cursor=first["next_cursor"],
            secret=fixture["secret"],
        )


def test_deterministic_1000_item_fixture_is_pageable():
    seed = _load_json("asset-library-1000.seed.json")
    kinds = seed["kinds"]
    items = [
        {
            "resource_id": f"asset-{index:04d}",
            "kind": kinds[index % len(kinds)],
            "name": f"资产 {index:04d}",
            "status": "archived" if index % 37 == 0 else "ready",
            "favorite": index % 11 == 0,
            "updated_at": f"2026-07-18T00:{index // 60:02d}:{index % 60:02d}Z",
            "last_used_at": None,
            "tags": ["fixture"],
        }
        for index in range(seed["count"])
    ]
    first = paginate_library_items(items, page_size=50, index_generation=1)
    assert first["total"] == 1000
    assert len(first["items"]) == 50
    assert first["next_cursor"]


def test_smb_ux_flag_defaults_off_without_changing_v2_kernel_default(monkeypatch):
    monkeypatch.delenv("PIXELLE_ASSET_CENTER_SMB_UX", raising=False)
    monkeypatch.delenv("PIXELLE_ASSET_CENTER_V2", raising=False)
    config = APIConfig()
    assert config.asset_center_smb_ux_enabled is False
    assert config.asset_center_v2_enabled is True
