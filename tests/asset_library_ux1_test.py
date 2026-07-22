from __future__ import annotations

import io
import json
from pathlib import Path

import pytest
from PIL import Image

from pixelle_video.services.asset_library_cursor import CursorStaleError
from pixelle_video.services.assets_v2.repository import AssetLibraryRepository


def _png() -> bytes:
    image = Image.new("RGBA", (8, 8), (255, 0, 0, 128))
    output = io.BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def test_sql_cursor_reaches_all_assets_without_page_duplicates(tmp_path):
    repository = AssetLibraryRepository(tmp_path / "data")
    with repository._lock, repository._connect() as connection:  # noqa: SLF001 - fixture population
        for index in range(1001):
            asset_id = f"media-fixture-{index:04d}"
            connection.execute(
                "INSERT INTO media_assets(asset_id, media_kind, name, description, source, status, created_at, updated_at) VALUES (?, 'image', ?, '', 'imported', 'ready', ?, ?)",
                (asset_id, f"素材 {index:04d}", f"2026-07-18T00:{index // 60:02d}:{index % 60:02d}+00:00", f"2026-07-18T00:{index // 60:02d}:{index % 60:02d}+00:00"),
            )
    cursor = None
    ids: list[str] = []
    while True:
        page = repository.list_library_page(kind="image", page_size=73, cursor=cursor, sort="name")
        ids.extend(str(item["resource_id"]) for item in page["items"])
        cursor = page["next_cursor"]
        if not cursor:
            break
    assert len(ids) == 1001
    assert len(set(ids)) == 1001
    assert ids[0] == "media-fixture-0000"


def test_deferred_upload_unique_finalize_and_duplicate_finalize_are_idempotent(tmp_path):
    repository = AssetLibraryRepository(tmp_path / "data")
    content = _png()
    session = repository.create_upload_session(
        "transparent.png",
        len(content),
        "image",
        decision_mode="deferred",
        idempotency_key="ux1-same-request",
    )
    repository.append_upload_chunk(session["upload_id"], content)
    uploaded = repository.complete_upload_content(session["upload_id"])
    assert uploaded["status"] == "uploaded"
    finalized = repository.finalize_deferred_upload(session["upload_id"])
    repeated = repository.finalize_deferred_upload(session["upload_id"], "reuse_existing")
    assert finalized["asset_id"] == repeated["asset_id"]
    assert finalized["status"] == "finalized"
    assert repository.create_upload_session("other.png", len(content), "image", idempotency_key="ux1-same-request")["upload_id"] == session["upload_id"]

    second = repository.create_upload_session("same-content.png", len(content), "image", decision_mode="deferred")
    repository.append_upload_chunk(second["upload_id"], content)
    awaiting = repository.complete_upload_content(second["upload_id"])
    assert awaiting["status"] == "awaiting_duplicate_decision"
    attached = repository.finalize_deferred_upload(second["upload_id"], "attach_revision", target_asset_id=finalized["asset_id"])
    assert attached["asset_id"] == finalized["asset_id"]
    assert len(repository.list_revisions(finalized["asset_id"])) == 2


def test_voice_profile_is_separate_from_plain_audio_and_scene_mutations_are_typed(tmp_path):
    repository = AssetLibraryRepository(tmp_path / "data")
    with repository._lock, repository._connect() as connection:  # noqa: SLF001
        connection.execute("INSERT INTO media_assets(asset_id, media_kind, name, source, status, created_at, updated_at) VALUES ('audio-bgm', 'audio', '普通 BGM', 'upload', 'ready', '2026-07-18', '2026-07-18')")
    assert repository.list_domain_items("voice") == []
    voice = repository.create_voice_profile({"name": "店长音色", "audio_asset_id": "audio-bgm", "language": "中文", "style": "亲切"})
    assert voice["kind"] == "voice"
    assert voice["resource_id"] != "audio-bgm"
    profile = repository.create_digital_human_profile({"name": "人物", "scene_name": "门店场景"})
    scene_id = profile["scenes"][0]["scene_id"]
    patched = repository.patch_digital_human_scene(scene_id, {"name": "收银台场景", "location": "门店"})
    assert patched and patched["name"] == "收银台场景"
    assert repository.patch_digital_human_scene(scene_id, {"status": "archived"})
    assert repository.list_digital_human_scenes(profile["resource_id"]) == []


def test_template_layout_contract_rejects_unknown_or_missing_font(tmp_path):
    repository = AssetLibraryRepository(tmp_path / "data")
    fixture = json.loads(Path("tests/fixtures/ux0/template-layout/valid.json").read_text())
    created = repository.create_template_revision({"display_name": "契约模板", "layout_contract": fixture, "schema_version": 2})
    assert created["layout_contract"]["schema_version"] == 2
    bad = json.loads(json.dumps(fixture))
    bad["cover"]["title"]["font_token"] = "missing"
    try:
        repository.create_template_revision({"display_name": "坏模板", "layout_contract": bad, "schema_version": 2})
    except ValueError as error:
        assert "font_token_not_registered" in str(error)
    else:
        raise AssertionError("missing template font must be rejected")


def test_cursor_generation_changes_on_same_tick_mutation_and_query_filters(tmp_path):
    repository = AssetLibraryRepository(tmp_path / "data")
    with repository._lock, repository._connect() as connection:  # noqa: SLF001
        connection.execute(
            "INSERT INTO media_assets(asset_id, media_kind, name, source, status, created_at, updated_at) VALUES ('portrait-upload', 'image', '竖版上传', 'upload', 'ready', '2026-07-18', '2026-07-18')"
        )
        connection.execute(
            "INSERT INTO media_assets(asset_id, media_kind, name, source, status, created_at, updated_at) VALUES ('landscape-import', 'image', '横版导入', 'imported', 'ready', '2026-07-18', '2026-07-18')"
        )
        connection.execute(
            "INSERT INTO media_assets(asset_id, media_kind, name, source, status, created_at, updated_at) VALUES ('portrait-upload-2', 'image', '竖版上传二', 'upload', 'ready', '2026-07-18', '2026-07-18')"
        )
        connection.execute(
            "INSERT INTO asset_revisions(revision_id, asset_id, version, relative_path, mime_type, bytes, sha256, width, height, aspect_ratio, created_at) VALUES ('rev-portrait', 'portrait-upload', 1, 'asset_library/media/portrait-upload.png', 'image/png', 1, ?, 900, 1600, 0.5625, '2026-07-18')",
            ("a" * 64,),
        )
        connection.execute("UPDATE media_assets SET current_revision_id = 'rev-portrait' WHERE asset_id = 'portrait-upload'")
        connection.execute("UPDATE media_assets SET current_revision_id = 'rev-portrait' WHERE asset_id = 'portrait-upload-2'")
    page = repository.list_library_page(kind="image", page_size=1, source="upload", aspect="portrait", sort="name")
    assert [item["resource_id"] for item in page["items"]] == ["portrait-upload"]
    with repository._lock, repository._connect() as connection:  # noqa: SLF001
        connection.execute("UPDATE media_assets SET name = '竖版上传（已改名）' WHERE asset_id = 'portrait-upload'")
    with pytest.raises(CursorStaleError):
        repository.list_library_page(kind="image", page_size=1, source="upload", aspect="portrait", sort="name", cursor=page["next_cursor"])
