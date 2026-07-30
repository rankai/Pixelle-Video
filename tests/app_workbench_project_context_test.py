from __future__ import annotations

import sqlite3
from copy import deepcopy

import pytest
from fastapi.testclient import TestClient

from api.app import app
from api.routers.app_center import get_app_center_repository
from pixelle_video.app_center.migration import migrate_app_center
from pixelle_video.app_center.project_context import ProjectContextError
from pixelle_video.app_center.repository import AppCenterRepository


def _fact(fact_id: str, text: str, *, source: str = "user", source_ref: str | None = None):
    return {
        "fact_id": fact_id,
        "text": text,
        "source": source,
        **({"source_ref": source_ref} if source_ref is not None else {}),
    }


def _v2_payload():
    return {
        "schema_version": 2,
        "subject_type": "store",
        "store_or_brand": {
            "name": "街角咖啡",
            "industry": "咖啡餐饮",
            "address": None,
            "contact": None,
        },
        "offer": {
            "name": "夏日冰咖",
            "category": "饮品",
            "price_facts": [_fact("price-1", "到店价 19 元")],
            "promotion_facts": [],
        },
        "audience": {"primary": "周边上班族", "scenes": ["午休", "下班"]},
        "selling_points": [_fact("selling-1", "现磨咖啡豆")],
        "proof_points": [],
        "required_facts": [],
        "forbidden_claims": ["全网最低"],
        "asset_refs": [],
        "brand_revision_ref": None,
    }


class _FakeAssets:
    def __init__(self, known: set[tuple[str, str]] | None = None):
        self.known = known or set()

    def get_asset_revision(self, asset_id: str, revision_id: str):
        if (asset_id, revision_id) in self.known:
            return {"asset_id": asset_id, "revision_id": revision_id}
        return None


def test_context_snapshot_v1_and_v2_append_without_overwriting_history(tmp_path):
    repository = AppCenterRepository(tmp_path / "app.sqlite", asset_repository=_FakeAssets())
    project = repository.create_project("咖啡新品", "到店")

    v1 = repository.save_context_snapshot(project.project_id, {"store_name": "街角咖啡"})
    v2 = repository.save_context_snapshot(
        project.project_id,
        _v2_payload(),
        schema_version=2,
    )

    assert v1.schema_version == 1
    assert repository.get_context_snapshot(v1.context_snapshot_id).payload == {
        "store_name": "街角咖啡"
    }
    assert v2.schema_version == 2
    assert v2.context_snapshot_id != v1.context_snapshot_id
    assert (
        repository.get_project(project.project_id).current_context_snapshot_id
        == v2.context_snapshot_id
    )


def test_old_run_keeps_the_snapshot_that_was_selected_at_creation(tmp_path):
    repository = AppCenterRepository(tmp_path / "app.sqlite", asset_repository=_FakeAssets())
    project = repository.create_project("不可变上下文", "到店")
    old_snapshot = repository.save_context_snapshot(project.project_id, {"store_name": "旧店名"})
    old_run = repository.create_app_run(
        project.project_id,
        "builtin.marketing-copy",
        "1.0.0",
        {"goal": "到店"},
        idempotency_key="context-pinned-run",
        context_snapshot_id=old_snapshot.context_snapshot_id,
    )
    new_snapshot = repository.save_context_snapshot(
        project.project_id,
        _v2_payload(),
        schema_version=2,
    )

    assert (
        repository.get_app_run(old_run.app_run_id).context_snapshot_id
        == old_snapshot.context_snapshot_id
    )
    assert (
        repository.get_project(project.project_id).current_context_snapshot_id
        == new_snapshot.context_snapshot_id
    )


def test_context_v2_rejects_fact_conflicts_cross_project_artifacts_and_missing_assets(tmp_path):
    repository = AppCenterRepository(tmp_path / "app.sqlite", asset_repository=_FakeAssets())
    first = repository.create_project("项目一", "到店")
    second = repository.create_project("项目二", "咨询")
    artifact = repository.create_artifact(second.project_id, "brief", "其他项目事实")
    version = repository.append_artifact_version(
        artifact.artifact_id,
        content={"text": "只属于项目二"},
    )

    conflict = _v2_payload()
    conflict["proof_points"] = [_fact("selling-1", "与原卖点冲突")]
    with pytest.raises(ProjectContextError) as exc:
        repository.save_context_snapshot(first.project_id, conflict, schema_version=2)
    assert exc.value.code == "PROJECT_CONTEXT_FACT_CONFLICT"

    cross_project = _v2_payload()
    cross_project["required_facts"] = [
        _fact(
            "artifact-1",
            "引用其他项目",
            source="artifact_version",
            source_ref=version.artifact_version_id,
        )
    ]
    with pytest.raises(ProjectContextError) as exc:
        repository.save_context_snapshot(first.project_id, cross_project, schema_version=2)
    assert exc.value.code == "PROJECT_CONTEXT_CROSS_PROJECT_REF"

    missing_asset = _v2_payload()
    missing_asset["asset_refs"] = [
        {"asset_id": "asset-missing", "asset_revision": "revision-missing"}
    ]
    with pytest.raises(ProjectContextError) as exc:
        repository.save_context_snapshot(first.project_id, missing_asset, schema_version=2)
    assert exc.value.code == "PROJECT_CONTEXT_ASSET_NOT_FOUND"


def test_context_v2_accepts_exact_project_artifact_and_asset_revisions(tmp_path):
    assets = _FakeAssets({("asset-known", "revision-2")})
    repository = AppCenterRepository(tmp_path / "app.sqlite", asset_repository=assets)
    project = repository.create_project("可验证引用", "到店")
    artifact = repository.create_artifact(project.project_id, "brief", "可信事实")
    version = repository.append_artifact_version(
        artifact.artifact_id,
        content={"text": "同项目事实"},
    )
    payload = _v2_payload()
    payload["required_facts"] = [
        _fact(
            "artifact-1",
            "同项目事实",
            source="artifact_version",
            source_ref=version.artifact_version_id,
        )
    ]
    payload["asset_refs"] = [{"asset_id": "asset-known", "asset_revision": "revision-2"}]

    snapshot = repository.save_context_snapshot(
        project.project_id,
        payload,
        schema_version=2,
    )
    assert snapshot.payload == payload


@pytest.mark.parametrize(
    ("mutator", "code"),
    [
        (lambda payload: payload.pop("audience"), "PROJECT_CONTEXT_INVALID"),
        (lambda payload: payload.update({"schema_version": 1}), "PROJECT_CONTEXT_INVALID"),
    ],
)
def test_context_v2_uses_stable_invalid_errors(tmp_path, mutator, code):
    repository = AppCenterRepository(tmp_path / "app.sqlite", asset_repository=_FakeAssets())
    project = repository.create_project("错误契约", "到店")
    payload = deepcopy(_v2_payload())
    mutator(payload)
    with pytest.raises(ProjectContextError) as exc:
        repository.save_context_snapshot(project.project_id, payload, schema_version=2)
    assert exc.value.code == code


def test_context_api_returns_stable_error_shape_and_keeps_v1_default(monkeypatch, tmp_path):
    monkeypatch.setenv("PIXELLE_APP_CENTER_DB", str(tmp_path / "api.sqlite"))
    get_app_center_repository.cache_clear()
    client = TestClient(app)
    project = client.post(
        "/api/content-projects",
        json={"name": "上下文 API", "primary_goal": "到店"},
    ).json()

    legacy = client.post(
        f"/api/content-projects/{project['project_id']}/context-snapshots",
        json={"payload": {"store_name": "旧版店铺"}},
    )
    assert legacy.status_code == 201
    assert legacy.json()["schema_version"] == 1

    invalid = client.post(
        f"/api/content-projects/{project['project_id']}/context-snapshots",
        json={"schema_version": 2, "payload": {"schema_version": 2}},
    )
    assert invalid.status_code == 409
    assert invalid.json()["detail"]["code"] == "PROJECT_CONTEXT_INVALID"

    unsupported = client.post(
        f"/api/content-projects/{project['project_id']}/context-snapshots",
        json={"schema_version": 3, "payload": {}},
    )
    assert unsupported.status_code == 422
    assert unsupported.json()["detail"]["code"] == "PROJECT_BRAND_CONTEXT_UNTRUSTED"
    get_app_center_repository.cache_clear()


def test_migration_upgrades_the_legacy_context_constraint_without_changing_rows(tmp_path):
    db_path = tmp_path / "legacy.sqlite"
    migrate_app_center(db_path)
    with sqlite3.connect(db_path) as connection:
        connection.execute("PRAGMA foreign_keys = OFF")
        connection.execute(
            "UPDATE app_schema_migrations SET checksum = ? WHERE migration_id = 'app-center-v1'",
            ("sha256:cd21d2b630a7601068e60a5edb4edf3130a3661f2c74eaadd323e2420b4c0712",),
        )
        connection.execute("ALTER TABLE context_snapshots RENAME TO context_snapshots_current")
        connection.execute(
            """
            CREATE TABLE context_snapshots (
              context_snapshot_id TEXT PRIMARY KEY,
              project_id TEXT NOT NULL REFERENCES content_projects(project_id),
              schema_version INTEGER NOT NULL DEFAULT 1 CHECK (schema_version = 1),
              payload_json TEXT NOT NULL,
              source_brand_id TEXT,
              source_brand_revision_id TEXT,
              fingerprint TEXT NOT NULL,
              created_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            INSERT INTO context_snapshots
            SELECT * FROM context_snapshots_current
            """
        )
        connection.execute("DROP TABLE context_snapshots_current")
        connection.commit()

    migrate_app_center(db_path)
    with sqlite3.connect(db_path) as connection:
        table_sql = connection.execute(
            "SELECT sql FROM sqlite_master WHERE name = 'context_snapshots'"
        ).fetchone()[0]
        assert "schema_version IN (1, 2, 3)" in table_sql
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
