from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource

from api.app import app
from api.routers import app_center as app_center_api
from pixelle_video.app_center.repository import AppCenterRepository
from pixelle_video.app_center.result_history import (
    ResultHistoryError,
    ResultHistoryMediaService,
    ResultHistoryProjectionService,
)

ROOT = Path(__file__).resolve().parents[1]
CONTRACT_DIR = ROOT / "docs/contracts/app-center"


def _record_validator() -> Draft202012Validator:
    schema = json.loads(
        (CONTRACT_DIR / "generation-record-block-v1.schema.json").read_text(encoding="utf-8")
    )
    return Draft202012Validator(schema, format_checker=FormatChecker())


def _page_validator() -> Draft202012Validator:
    record_schema = json.loads(
        (CONTRACT_DIR / "generation-record-block-v1.schema.json").read_text(encoding="utf-8")
    )
    page_schema = json.loads(
        (CONTRACT_DIR / "generation-record-page-v1.schema.json").read_text(encoding="utf-8")
    )
    registry = Registry().with_resource(record_schema["$id"], Resource.from_contents(record_schema))
    return Draft202012Validator(
        page_schema,
        registry=registry,
        format_checker=FormatChecker(),
    )


def _copy_content(count: int = 3) -> dict[str, Any]:
    angles = ("利益", "好奇", "场景", "身份", "冲突", "数字")
    variants = []
    for index in range(count):
        hook = f"下午茶开场{index + 1}"
        body = f"现磨咖啡和当日面包组合{index + 1}"
        cta = "欢迎到店"
        full_text = hook + body + cta
        variants.append(
            {
                "version_name": f"文案 {index + 1}",
                "angle": angles[index % len(angles)],
                "hook": hook,
                "body": body,
                "cta": cta,
                "full_text": full_text,
                "word_count": len(full_text),
                "estimated_seconds": (len(full_text) + 3) // 4,
            }
        )
    return {
        "schema_version": 1,
        "artifact_type": "copywriting",
        "variants": variants,
        "missing_facts": [],
        "risk_flags": [],
    }


def _title_content(count: int = 6) -> dict[str, Any]:
    candidates = []
    for index in range(count):
        text = f"下午三点别硬撑，第{index + 1}份现磨咖啡等你"
        candidates.append(
            {
                "title": text,
                "angle": f"角度 {index + 1}",
                "objective": "click",
                "length": len(text),
                "banned_matches": [],
                "risk_labels": ["无"],
            }
        )
    return {
        "schema_version": 1,
        "artifact_type": "title_set",
        "candidates": candidates,
        "missing_facts": [],
        "risk_flags": [],
    }


def _complete_run(
    repository: AppCenterRepository,
    project_id: str,
    app_id: str,
    specs: list[tuple[str, str, dict[str, Any] | None, list[dict[str, Any]]]],
    *,
    suffix: str,
):
    run = repository.create_app_run(
        project_id,
        app_id,
        "1.1.0",
        {"goal": "推广下午茶"},
        idempotency_key=f"result-history-{suffix}",
    )
    repository.transition_app_run(run.app_run_id, "queued")
    repository.transition_app_run(run.app_run_id, "running")
    artifact_ids = []
    for artifact_type, name, content, file_refs in specs:
        artifact = repository.create_artifact(
            project_id,
            artifact_type,
            name,
            source_app_run_id=run.app_run_id,
        )
        repository.append_artifact_version(
            artifact.artifact_id,
            content=content,
            file_refs=file_refs,
            source="rendered" if file_refs else "generated",
        )
        artifact_ids.append(artifact.artifact_id)
    repository.set_output_artifacts(run.app_run_id, artifact_ids)
    repository.transition_app_run(run.app_run_id, "needs_review")
    return repository.transition_app_run(run.app_run_id, "completed")


def _seed_four_results(repository: AppCenterRepository):
    project = repository.create_project("下午茶项目", "推广工作日下午茶")
    copy_run = _complete_run(
        repository,
        project.project_id,
        "builtin.marketing-copy",
        [("copywriting", "下午茶门店文案", _copy_content(), [])],
        suffix="copy",
    )
    title_run = _complete_run(
        repository,
        project.project_id,
        "builtin.viral-titles",
        [("title_set", "下午茶标题", _title_content(), [])],
        suffix="titles",
    )
    carousel_specs = [
        (
            "carousel_package",
            "下午茶图文",
            {
                "schema_version": 1,
                "artifact_type": "carousel_package",
                "page_count": 5,
                "page_artifact_version_ids": [f"page-version-{index}" for index in range(1, 6)],
                "title": "三公里上班族下午茶",
                "description": "现磨咖啡与当日面包",
                "hashtags": ["下午茶"],
            },
            [
                {
                    "file_key": "page-01.png",
                    "relative_path": "run/page-01.png",
                    "kind": "image",
                    "mime_type": "image/png",
                    "sha256": "sha256:" + "1" * 64,
                    "size_bytes": 100,
                }
            ],
        )
    ]
    for index in range(1, 6):
        carousel_specs.append(
            (
                "carousel_page",
                f"图文第 {index} 页",
                {
                    "schema_version": 1,
                    "artifact_type": "carousel_page",
                    "page_index": index,
                    "text": f"第 {index} 页",
                },
                [
                    {
                        "file_key": f"page-{index:02d}.png",
                        "relative_path": f"run/page-{index:02d}.png",
                        "kind": "image",
                        "mime_type": "image/png",
                        "sha256": "sha256:" + str(index) * 64,
                        "size_bytes": 100,
                    }
                ],
            )
        )
    carousel_run = _complete_run(
        repository,
        project.project_id,
        "builtin.douyin-carousel",
        carousel_specs,
        suffix="carousel",
    )
    video_run = _complete_run(
        repository,
        project.project_id,
        "builtin.digital-human-video",
        [
            (
                "video",
                "下午茶数字人口播",
                {"schema_version": 1, "artifact_type": "video"},
                [
                    {
                        "file_key": "final.mp4",
                        "relative_path": "run/final.mp4",
                        "kind": "video",
                        "mime_type": "video/mp4",
                        "sha256": "sha256:" + "a" * 64,
                        "size_bytes": 1000,
                        "duration_seconds": 22.4,
                    }
                ],
            ),
            (
                "cover",
                "下午茶数字人口播封面",
                {"schema_version": 1, "artifact_type": "cover"},
                [
                    {
                        "file_key": "cover.png",
                        "relative_path": "run/cover.png",
                        "kind": "cover",
                        "mime_type": "image/png",
                        "sha256": "sha256:" + "b" * 64,
                        "size_bytes": 100,
                    }
                ],
            ),
            (
                "publish_copy",
                "发布文案",
                {
                    "schema_version": 1,
                    "artifact_type": "publish_copy",
                    "title": "工作日下午茶推荐",
                    "description": "来店里歇一会儿",
                    "hashtags": ["下午茶"],
                },
                [],
            ),
            (
                "spoken_script",
                "口播文案",
                {
                    "schema_version": 1,
                    "artifact_type": "spoken_script",
                    "spoken_script": "下午三点来店里坐坐，现磨咖啡和面包都准备好了。",
                },
                [],
            ),
        ],
        suffix="video",
    )
    return project, {
        "copy": copy_run,
        "titles": title_run,
        "carousel": carousel_run,
        "video": video_run,
    }


def _projected_media_item(
    repository: AppCenterRepository,
    project_id: str,
    app_id: str,
) -> dict[str, Any]:
    page = ResultHistoryProjectionService(repository).list_records(
        project_id,
        scope="current_app",
        app_id=app_id,
        limit=1,
    )
    return page["records"][0]["items"][0]


def _version_token(item: dict[str, Any]) -> str:
    return str(item["preview_url"]).split("?version=", 1)[1]


def _database_snapshot(path: Path) -> dict[str, list[tuple[Any, ...]]]:
    with sqlite3.connect(path) as conn:
        tables = [
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type = 'table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
            )
        ]
        return {
            table: sorted(
                [tuple(row) for row in conn.execute(f'SELECT * FROM "{table}"')],
                key=repr,
            )
            for table in tables
        }


def test_projection_returns_exact_four_business_shapes_and_complete_candidates(tmp_path):
    repository = AppCenterRepository(tmp_path / "result-history.sqlite")
    project, _runs = _seed_four_results(repository)
    page = ResultHistoryProjectionService(repository).list_records(
        project.project_id,
        scope="all_results",
        limit=10,
    )
    assert list(_page_validator().iter_errors(page)) == []
    records = {record["app_id"]: record for record in page["records"]}
    assert len(records["builtin.marketing-copy"]["items"]) == 3
    assert len(records["builtin.viral-titles"]["items"]) == 6
    assert records["builtin.viral-titles"]["items"][0]["item_id"].count(":") == 2
    assert len(records["builtin.douyin-carousel"]["items"]) == 1
    assert records["builtin.douyin-carousel"]["items"][0]["page_count"] == 5
    assert len(records["builtin.digital-human-video"]["items"]) == 1
    assert records["builtin.digital-human-video"]["items"][0]["duration_seconds"] == 22.4
    for record in page["records"]:
        assert list(_record_validator().iter_errors(record)) == []
        serialized = json.dumps(record, ensure_ascii=False)
        assert "relative_path" not in serialized
        assert "provider" not in serialized
        assert "RunningHub" not in serialized


def test_title_selection_is_hydrated_from_persisted_selected_artifact(tmp_path):
    repository = AppCenterRepository(tmp_path / "result-history.sqlite")
    project, runs = _seed_four_results(repository)
    title_run = runs["titles"]
    artifacts = repository.list_result_history_artifacts(
        project.project_id,
        app_run_ids=[title_run.app_run_id],
        output_artifact_ids=title_run.output_artifact_ids,
    )
    title_artifact = next(
        artifact for artifact in artifacts if artifact.artifact_type == "title_set"
    )
    selected = repository.create_artifact(
        project.project_id,
        "selected_title",
        "已采用标题",
        source_app_run_id=title_run.app_run_id,
    )
    repository.append_artifact_version(
        selected.artifact_id,
        content={
            "artifact_type": "selected_title",
            "title": "下午三点别硬撑，第3份现磨咖啡等你",
            "source_title_set_artifact_id": title_artifact.artifact_id,
            "source_title_set_version_id": title_artifact.current_version_id,
            "selected_index": 2,
        },
        source="generated",
    )

    items = ResultHistoryProjectionService(repository).list_records(
        project.project_id,
        scope="current_app",
        app_id="builtin.viral-titles",
        limit=10,
    )["records"][0]["items"]
    assert [candidate["selected"] for candidate in items] == [
        False,
        False,
        True,
        False,
        False,
        False,
    ]


def test_current_app_scope_and_project_isolation(tmp_path):
    repository = AppCenterRepository(tmp_path / "result-history.sqlite")
    project, _runs = _seed_four_results(repository)
    other = repository.create_project("其他项目", "隔离")
    other_run = repository.create_app_run(
        other.project_id,
        "builtin.viral-titles",
        "1.1.0",
        {},
        idempotency_key="result-history-other",
    )
    repository.transition_app_run(other_run.app_run_id, "queued")

    page = ResultHistoryProjectionService(repository).list_records(
        project.project_id,
        app_id="builtin.viral-titles",
    )
    assert page["scope"] == "current_app"
    assert page["app_id"] == "builtin.viral-titles"
    assert {record["project_id"] for record in page["records"]} == {project.project_id}
    assert {record["app_id"] for record in page["records"]} == {"builtin.viral-titles"}

    media_page = ResultHistoryProjectionService(repository).list_records(
        project.project_id,
        scope="all_results",
        result_shape="single_video",
        status="completed",
    )
    assert [record["app_id"] for record in media_page["records"]] == ["builtin.digital-human-video"]
    with pytest.raises(ResultHistoryError):
        ResultHistoryProjectionService(repository).list_records(
            project.project_id,
            app_id="builtin.viral-titles",
            result_shape="single_video",
        )


def test_projection_does_not_truncate_already_persisted_title_candidates(tmp_path):
    repository = AppCenterRepository(tmp_path / "result-history.sqlite")
    project, _runs = _seed_four_results(repository)
    title_artifact = next(
        item
        for item in repository.list_artifacts(project.project_id)
        if item.artifact_type == "title_set"
    )
    version = repository.get_artifact_version(title_artifact.current_version_id)
    stored = dict(version.content or {})
    template = dict(stored["candidates"][0])
    stored["candidates"] = [
        {
            **template,
            "title": f"已保存的候选标题 {index}",
            "length": len(f"已保存的候选标题 {index}"),
        }
        for index in range(1, 26)
    ]
    # Simulate a historical producer that already persisted more candidates
    # than today's request limit. The read model must preserve those facts.
    with repository._connect() as conn:
        conn.execute(
            "UPDATE artifact_versions SET content_json = ? WHERE artifact_version_id = ?",
            (
                json.dumps(stored, ensure_ascii=False, sort_keys=True),
                version.artifact_version_id,
            ),
        )

    page = ResultHistoryProjectionService(repository).list_records(
        project.project_id,
        app_id="builtin.viral-titles",
    )
    assert len(page["records"]) == 1
    assert len(page["records"][0]["items"]) == 25
    assert page["records"][0]["items"][-1]["text"] == "已保存的候选标题 25"


def test_cursor_is_stable_tamper_evident_and_has_no_duplicate_or_omission(tmp_path):
    repository = AppCenterRepository(tmp_path / "result-history.sqlite")
    project = repository.create_project("分页项目", "验证分页")
    created_ids = []
    for index in range(23):
        run = repository.create_app_run(
            project.project_id,
            "builtin.viral-titles",
            "1.1.0",
            {},
            idempotency_key=f"history-page-{index:02d}",
        )
        repository.transition_app_run(run.app_run_id, "queued")
        repository.transition_app_run(run.app_run_id, "running")
        created_ids.append(run.app_run_id)
    with repository._connect() as conn:
        conn.execute(
            "UPDATE app_runs SET created_at = ?, updated_at = ? WHERE project_id = ?",
            (
                "2026-07-30T12:00:00.000Z",
                "2026-07-30T12:00:00.000Z",
                project.project_id,
            ),
        )

    service = ResultHistoryProjectionService(repository)
    first = service.list_records(
        project.project_id,
        app_id="builtin.viral-titles",
        limit=7,
    )
    observed = [record["app_run_id"] for record in first["records"]]
    cursor = first["next_cursor"]
    while True:
        page = service.list_records(
            project.project_id,
            app_id="builtin.viral-titles",
            cursor=cursor,
            limit=7,
        )
        observed.extend(record["app_run_id"] for record in page["records"])
        cursor = page["next_cursor"]
        if cursor is None:
            break
    assert len(observed) == len(set(observed)) == 23
    assert set(observed) == set(created_ids)
    assert observed == sorted(observed, reverse=True)

    fresh_first = service.list_records(
        project.project_id,
        app_id="builtin.viral-titles",
        limit=7,
    )
    moving_run_id = next(
        item
        for item in created_ids
        if item not in {record["app_run_id"] for record in fresh_first["records"]}
    )
    repository.transition_app_run(moving_run_id, "completed")
    with pytest.raises(ResultHistoryError) as stale:
        service.list_records(
            project.project_id,
            app_id="builtin.viral-titles",
            cursor=fresh_first["next_cursor"],
            limit=7,
        )
    assert stale.value.code == "APP_RESULT_CURSOR_STALE"

    tampered = first["next_cursor"][:-1] + ("A" if first["next_cursor"][-1] != "A" else "B")
    with pytest.raises(ResultHistoryError) as raised:
        service.list_records(
            project.project_id,
            app_id="builtin.viral-titles",
            cursor=tampered,
            limit=7,
        )
    assert raised.value.code == "APP_RESULT_CURSOR_INVALID"
    assert raised.value.message == "历史记录位置已失效，请重新加载"
    with pytest.raises(ResultHistoryError):
        service.list_records(
            project.project_id,
            app_id="builtin.marketing-copy",
            cursor=first["next_cursor"],
            limit=7,
        )
    with pytest.raises(ResultHistoryError):
        service.list_records(
            project.project_id,
            app_id="builtin.viral-titles",
            status="completed",
            cursor=first["next_cursor"],
            limit=7,
        )
    assert len(first["next_cursor"]) <= 256


def test_records_are_ordered_by_result_available_at_not_creation_time(tmp_path):
    repository = AppCenterRepository(tmp_path / "result-history.sqlite")
    project = repository.create_project("结果时间排序", "验证完成时间优先")
    earlier_created = repository.create_app_run(
        project.project_id,
        "builtin.viral-titles",
        "1.1.0",
        {},
        idempotency_key="history-order-earlier-created",
    )
    later_created = repository.create_app_run(
        project.project_id,
        "builtin.viral-titles",
        "1.1.0",
        {},
        idempotency_key="history-order-later-created",
    )
    for run in (earlier_created, later_created):
        repository.transition_app_run(run.app_run_id, "queued")
        repository.transition_app_run(run.app_run_id, "running")
        repository.transition_app_run(run.app_run_id, "completed")
    with repository._connect() as conn:
        conn.execute(
            """
            UPDATE app_runs
            SET created_at = ?, completed_at = ?, updated_at = ?
            WHERE app_run_id = ?
            """,
            (
                "2026-07-30T10:00:00.000Z",
                "2026-07-30T12:00:00.000Z",
                "2026-07-30T12:00:00.000Z",
                earlier_created.app_run_id,
            ),
        )
        conn.execute(
            """
            UPDATE app_runs
            SET created_at = ?, completed_at = ?, updated_at = ?
            WHERE app_run_id = ?
            """,
            (
                "2026-07-30T11:00:00.000Z",
                "2026-07-30T11:30:00.000Z",
                "2026-07-30T11:30:00.000Z",
                later_created.app_run_id,
            ),
        )

    page = ResultHistoryProjectionService(repository).list_records(
        project.project_id,
        app_id="builtin.viral-titles",
        limit=10,
    )
    assert [record["app_run_id"] for record in page["records"]] == [
        earlier_created.app_run_id,
        later_created.app_run_id,
    ]
    assert [record["result_available_at"] for record in page["records"]] == [
        "2026-07-30T12:00:00.000Z",
        "2026-07-30T11:30:00.000Z",
    ]


def test_cursor_revision_detects_timestamp_collision_that_moves_unseen_row(tmp_path):
    repository = AppCenterRepository(tmp_path / "result-history.sqlite")
    project = repository.create_project("游标碰撞", "验证只改时间也不会漏项")
    runs = [
        repository.create_app_run(
            project.project_id,
            "builtin.viral-titles",
            "1.1.0",
            {},
            idempotency_key=f"history-collision-{index}",
        )
        for index in range(2)
    ]
    for run in runs:
        repository.transition_app_run(run.app_run_id, "queued")
        repository.transition_app_run(run.app_run_id, "running")
    lower_id, higher_id = sorted(run.app_run_id for run in runs)
    with repository._connect() as conn:
        conn.execute(
            "UPDATE app_runs SET updated_at = ? WHERE app_run_id = ?",
            ("2026-07-30T12:00:00.000Z", lower_id),
        )
        conn.execute(
            "UPDATE app_runs SET updated_at = ? WHERE app_run_id = ?",
            ("2026-07-30T11:00:00.000Z", higher_id),
        )

    service = ResultHistoryProjectionService(repository)
    first = service.list_records(
        project.project_id,
        app_id="builtin.viral-titles",
        limit=1,
    )
    assert [record["app_run_id"] for record in first["records"]] == [lower_id]
    with repository._connect() as conn:
        conn.execute(
            "UPDATE app_runs SET updated_at = ? WHERE app_run_id = ?",
            ("2026-07-30T12:00:00.000Z", higher_id),
        )
    with pytest.raises(ResultHistoryError) as stale:
        service.list_records(
            project.project_id,
            app_id="builtin.viral-titles",
            cursor=first["next_cursor"],
            limit=1,
        )
    assert stale.value.code == "APP_RESULT_CURSOR_STALE"


def test_legacy_record_degrades_per_item_without_breaking_page(tmp_path):
    repository = AppCenterRepository(tmp_path / "result-history.sqlite")
    project, _runs = _seed_four_results(repository)
    legacy = repository.create_app_run(
        project.project_id,
        "builtin.digital-human-video",
        "1.0.0",
        {},
        idempotency_key="history-legacy-video",
    )
    repository.transition_app_run(legacy.app_run_id, "queued")
    repository.transition_app_run(legacy.app_run_id, "running")
    repository.transition_app_run(legacy.app_run_id, "completed")

    page = ResultHistoryProjectionService(repository).list_records(
        project.project_id,
        scope="all_results",
        limit=10,
    )
    record = next(item for item in page["records"] if item["app_run_id"] == legacy.app_run_id)
    assert record["compatibility"] == {
        "state": "legacy_unavailable",
        "unavailable_reason": "这条旧记录暂时无法预览",
    }
    assert record["items"] == []
    assert len(page["records"]) == 5


def test_old_oversized_text_degrades_one_record_and_api_stays_200(monkeypatch, tmp_path):
    repository = AppCenterRepository(tmp_path / "result-history.sqlite")
    project, _runs = _seed_four_results(repository)
    title_artifact = next(
        item
        for item in repository.list_artifacts(project.project_id)
        if item.artifact_type == "title_set"
    )
    version = repository.get_artifact_version(title_artifact.current_version_id)
    stored = dict(version.content or {})
    stored["candidates"] = [dict(stored["candidates"][0], title="超" * 201, length=201)]
    with repository._connect() as conn:
        conn.execute(
            "UPDATE artifact_versions SET content_json = ? WHERE artifact_version_id = ?",
            (
                json.dumps(stored, ensure_ascii=False, sort_keys=True),
                version.artifact_version_id,
            ),
        )

    monkeypatch.setattr(app_center_api.api_config, "app_result_history_v1_enabled", True)
    monkeypatch.setattr(app_center_api, "get_app_center_repository", lambda: repository)
    isolated_api = FastAPI()
    isolated_api.include_router(app_center_api.router, prefix="/api")
    response = TestClient(isolated_api).get(
        f"/api/content-projects/{project.project_id}/result-records",
        params={"app_id": "builtin.viral-titles"},
    )
    assert response.status_code == 200
    record = response.json()["records"][0]
    assert record["compatibility"]["state"] == "legacy_unavailable"
    assert record["items"] == []


@pytest.mark.parametrize("page_count", [3, 5, 8])
def test_carousel_preview_is_one_product_with_all_ordered_pages_and_zero_writes(
    tmp_path,
    page_count,
):
    repository = AppCenterRepository(tmp_path / "result-history.sqlite")
    project = repository.create_project("图文预览", "验证真实页面")
    media_root = tmp_path / "carousel"
    media_root.mkdir()
    for index in range(1, page_count + 1):
        (media_root / f"page-{index:02d}.png").write_bytes(b"\x89PNG\r\n\x1a\n" + bytes([index]))
    (media_root / "carousel.zip").write_bytes(b"PK\x03\x04")
    run = _complete_run(
        repository,
        project.project_id,
        "builtin.douyin-carousel",
        [
            (
                "carousel_package",
                "下午茶图文",
                {
                    "artifact_type": "carousel_package",
                    "title": "工作日下午茶",
                    "page_count": page_count,
                    "missing_facts": ["门店地址"],
                },
                [
                    {
                        "file_key": f"page-{index:02d}.png",
                        "root": "carousel",
                        "relative_path": f"page-{index:02d}.png",
                        "kind": "image",
                        "mime_type": "image/png",
                        "page_index": index,
                    }
                    for index in range(1, page_count + 1)
                ]
                + [
                    {
                        "file_key": "carousel.zip",
                        "root": "carousel",
                        "relative_path": "carousel.zip",
                        "kind": "zip",
                        "mime_type": "application/zip",
                    }
                ],
            )
        ],
        suffix="media-preview-carousel",
    )
    before = _database_snapshot(repository.db_path)
    service = ResultHistoryMediaService(
        repository,
        media_roots={"carousel": media_root},
    )
    item = _projected_media_item(
        repository,
        project.project_id,
        "builtin.douyin-carousel",
    )
    assert item["missing_facts"] == ["门店地址"]
    version_token = _version_token(item)
    preview = service.get_preview(
        project.project_id,
        run.app_run_id,
        version_token=version_token,
    )
    assert preview == {
        "schema_version": 1,
        "kind": "carousel",
        "record_id": run.app_run_id,
        "title": "工作日下午茶",
        "page_count": page_count,
        "pages": [
            {
                "page_index": index,
                "image_url": (
                    f"/api/content-projects/{project.project_id}/result-records/"
                    f"{run.app_run_id}/pages/{index}?version={version_token}"
                ),
                "download_url": (
                    f"/api/content-projects/{project.project_id}/result-records/"
                    f"{run.app_run_id}/pages/{index}?version={version_token}"
                ),
            }
            for index in range(1, page_count + 1)
        ],
        "publish_copy": None,
        "download_url": (
            f"/api/content-projects/{project.project_id}/result-records/"
            f"{run.app_run_id}/download?version={version_token}"
        ),
    }
    assert (
        service.get_file(
            project.project_id,
            run.app_run_id,
            slot="cover",
            version_token=version_token,
        ).path
        == media_root / "page-01.png"
    )
    assert (
        service.get_file(
            project.project_id,
            run.app_run_id,
            slot="page",
            page_index=page_count,
            version_token=version_token,
        ).path
        == media_root / f"page-{page_count:02d}.png"
    )
    assert _database_snapshot(repository.db_path) == before
    package = repository.get_artifact(run.output_artifact_ids[0])
    (media_root / "new-page.png").write_bytes(b"\x89PNG\r\n\x1a\nnew")
    (media_root / "new-carousel.zip").write_bytes(b"PK\x03\x04new")
    repository.append_artifact_version(
        package.artifact_id,
        content={
            "artifact_type": "carousel_package",
            "title": "后来修改的标题",
            "page_count": 1,
        },
        file_refs=[
            {
                "file_key": "new-page.png",
                "root": "carousel",
                "relative_path": "new-page.png",
                "kind": "image",
                "mime_type": "image/png",
                "page_index": 1,
            },
            {
                "file_key": "new-carousel.zip",
                "root": "carousel",
                "relative_path": "new-carousel.zip",
                "kind": "zip",
                "mime_type": "application/zip",
            },
        ],
        source="edited",
    )
    pinned_preview = service.get_preview(
        project.project_id,
        run.app_run_id,
        version_token=version_token,
    )
    assert pinned_preview["title"] == "工作日下午茶"
    assert pinned_preview["page_count"] == page_count
    assert (
        service.get_file(
            project.project_id,
            run.app_run_id,
            slot="cover",
            version_token=version_token,
        ).path
        == media_root / "page-01.png"
    )


def test_video_preview_keeps_video_cover_and_publish_copy_in_one_product(tmp_path):
    repository = AppCenterRepository(tmp_path / "result-history.sqlite")
    project = repository.create_project("视频预览", "验证最终成片")
    output_root = tmp_path / "output"
    output_root.mkdir()
    (output_root / "final.mp4").write_bytes(b"\x00\x00\x00\x18ftypmp42")
    (output_root / "cover.jpg").write_bytes(b"\xff\xd8\xff\xd9")
    run = _complete_run(
        repository,
        project.project_id,
        "builtin.digital-human-video",
        [
            (
                "video",
                "门店下午茶推荐口播",
                {"artifact_type": "video", "duration_seconds": 28.4},
                [
                    {
                        "file_key": "final.mp4",
                        "root": "output",
                        "relative_path": "final.mp4",
                        "kind": "video",
                        "mime_type": "video/mp4",
                    }
                ],
            ),
            (
                "cover",
                "视频封面",
                {"artifact_type": "cover"},
                [
                    {
                        "file_key": "cover.jpg",
                        "root": "output",
                        "relative_path": "cover.jpg",
                        "kind": "cover",
                        "mime_type": "image/jpeg",
                    }
                ],
            ),
            (
                "publish_copy",
                "发布文案",
                {
                    "artifact_type": "publish_copy",
                    "title": "下班前来一杯刚磨好的咖啡",
                    "description": "工作日下午茶已经准备好了。",
                    "hashtags": ["下午茶", "附近好店"],
                },
                [],
            ),
        ],
        suffix="media-preview-video",
    )
    service = ResultHistoryMediaService(
        repository,
        media_roots={"output": output_root},
    )
    item = _projected_media_item(
        repository,
        project.project_id,
        "builtin.digital-human-video",
    )
    version_token = _version_token(item)
    preview = service.get_preview(
        project.project_id,
        run.app_run_id,
        version_token=version_token,
    )
    assert preview["kind"] == "video"
    assert preview["title"] == "下班前来一杯刚磨好的咖啡"
    assert preview["duration_seconds"] == 28.4
    assert preview["publish_copy"] == {
        "title": "下班前来一杯刚磨好的咖啡",
        "description": "工作日下午茶已经准备好了。",
        "hashtags": ["下午茶", "附近好店"],
    }
    assert (
        service.get_file(
            project.project_id,
            run.app_run_id,
            slot="play",
            version_token=version_token,
        ).path
        == output_root / "final.mp4"
    )
    assert (
        service.get_file(
            project.project_id,
            run.app_run_id,
            slot="poster",
            version_token=version_token,
        ).path
        == output_root / "cover.jpg"
    )


def test_media_preview_rejects_cross_project_and_path_escape(tmp_path):
    repository = AppCenterRepository(tmp_path / "result-history.sqlite")
    project = repository.create_project("安全预览", "验证边界")
    other = repository.create_project("其他项目", "隔离")
    media_root = tmp_path / "carousel"
    media_root.mkdir()
    outside = tmp_path / "outside.png"
    outside.write_bytes(b"\x89PNG\r\n\x1a\n")
    run = _complete_run(
        repository,
        project.project_id,
        "builtin.douyin-carousel",
        [
            (
                "carousel_package",
                "越界图文",
                {"artifact_type": "carousel_package", "title": "越界图文", "page_count": 1},
                [
                    {
                        "file_key": "outside.png",
                        "root": "carousel",
                        "relative_path": "../outside.png",
                        "kind": "image",
                        "mime_type": "image/png",
                        "page_index": 1,
                    },
                    {
                        "file_key": "carousel.zip",
                        "root": "carousel",
                        "relative_path": "../outside.png",
                        "kind": "zip",
                        "mime_type": "application/zip",
                    },
                ],
            )
        ],
        suffix="media-preview-escape",
    )
    service = ResultHistoryMediaService(
        repository,
        media_roots={"carousel": media_root},
    )
    item = _projected_media_item(
        repository,
        project.project_id,
        "builtin.douyin-carousel",
    )
    version_token = _version_token(item)
    with pytest.raises(ResultHistoryError) as cross_project:
        service.get_preview(
            other.project_id,
            run.app_run_id,
            version_token=version_token,
        )
    assert cross_project.value.code == "RESULT_MEDIA_NOT_FOUND"
    with pytest.raises(ResultHistoryError) as escaped:
        service.get_file(
            project.project_id,
            run.app_run_id,
            slot="cover",
            version_token=version_token,
        )
    assert escaped.value.code == "RESULT_MEDIA_FORBIDDEN"


def test_media_preview_api_serves_real_carousel_without_starting_provider(
    monkeypatch,
    tmp_path,
):
    monkeypatch.setenv("PIXELLE_VIDEO_ROOT", str(tmp_path))
    repository = AppCenterRepository(tmp_path / "result-history.sqlite")
    project = repository.create_project("API 图文预览", "验证只读接口")
    carousel_root = tmp_path / "data" / "app_center" / "carousel"
    carousel_root.mkdir(parents=True)
    (carousel_root / "page-01.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    (carousel_root / "carousel.zip").write_bytes(b"PK\x03\x04")
    run = _complete_run(
        repository,
        project.project_id,
        "builtin.douyin-carousel",
        [
            (
                "carousel_package",
                "API 图文",
                {"artifact_type": "carousel_package", "title": "API 图文", "page_count": 1},
                [
                    {
                        "file_key": "page-01.png",
                        "relative_path": "page-01.png",
                        "kind": "image",
                        "mime_type": "image/png",
                        "page_index": 1,
                    },
                    {
                        "file_key": "carousel.zip",
                        "relative_path": "carousel.zip",
                        "kind": "zip",
                        "mime_type": "application/zip",
                    },
                ],
            )
        ],
        suffix="media-preview-api",
    )
    before = _database_snapshot(repository.db_path)
    monkeypatch.setattr(app_center_api.api_config, "app_result_history_v1_enabled", True)
    monkeypatch.setattr(app_center_api, "get_app_center_repository", lambda: repository)
    isolated_api = FastAPI()
    isolated_api.include_router(app_center_api.router, prefix="/api")
    client = TestClient(isolated_api)

    item = _projected_media_item(
        repository,
        project.project_id,
        "builtin.douyin-carousel",
    )
    preview = client.get(item["preview_url"])
    page = client.get(
        f"/api/content-projects/{project.project_id}/result-records/"
        f"{run.app_run_id}/pages/1?version={_version_token(item)}"
    )
    assert preview.status_code == 200
    assert preview.json()["pages"] == [
        {
            "page_index": 1,
            "image_url": (
                f"/api/content-projects/{project.project_id}/result-records/"
                f"{run.app_run_id}/pages/1?version={_version_token(item)}"
            ),
            "download_url": (
                f"/api/content-projects/{project.project_id}/result-records/"
                f"{run.app_run_id}/pages/1?version={_version_token(item)}"
            ),
        }
    ]
    assert page.status_code == 200
    assert page.headers["content-type"] == "image/png"
    assert _database_snapshot(repository.db_path) == before


def test_projection_is_read_only_and_uses_constant_query_count(tmp_path):
    class CountingRepository(AppCenterRepository):
        select_count = 0

        def _connect(self):
            connection = super()._connect()

            def trace(statement: str):
                if statement.lstrip().upper().startswith("SELECT"):
                    self.select_count += 1

            connection.set_trace_callback(trace)
            return connection

    repository = CountingRepository(tmp_path / "result-history.sqlite")
    project, _runs = _seed_four_results(repository)
    before = _database_snapshot(repository.db_path)
    repository.select_count = 0
    service = ResultHistoryProjectionService(repository)
    for _ in range(3):
        page = service.list_records(project.project_id, scope="all_results", limit=10)
        assert len(page["records"]) == 4
    after = _database_snapshot(repository.db_path)
    assert after == before
    assert repository.select_count == 15


def test_api_rolls_on_off_on_without_changing_result_data(monkeypatch, tmp_path):
    db_path = tmp_path / "result-history-api.sqlite"
    monkeypatch.setenv("PIXELLE_APP_CENTER_DB", str(db_path))
    app_center_api.get_app_center_repository.cache_clear()
    repository = app_center_api.get_app_center_repository()
    project, _runs = _seed_four_results(repository)
    client = TestClient(app)

    before = _database_snapshot(db_path)
    monkeypatch.setattr(app_center_api.api_config, "app_result_history_v1_enabled", True)
    initial = client.get(
        f"/api/content-projects/{project.project_id}/result-records",
        params={"scope": "all_results"},
    )
    assert initial.status_code == 200
    assert list(_page_validator().iter_errors(initial.json())) == []

    monkeypatch.setattr(app_center_api.api_config, "app_result_history_v1_enabled", False)
    disabled = client.get(
        f"/api/content-projects/{project.project_id}/result-records",
        params={"scope": "all_results"},
    )
    assert disabled.status_code == 404
    assert disabled.json()["detail"]["code"] == "APP_RESULT_HISTORY_DISABLED"

    monkeypatch.setattr(app_center_api.api_config, "app_result_history_v1_enabled", True)
    enabled_again = client.get(
        f"/api/content-projects/{project.project_id}/result-records",
        params={"scope": "all_results"},
    )
    assert enabled_again.status_code == 200
    assert enabled_again.json() == initial.json()
    assert _database_snapshot(db_path) == before


def test_local_latest_ten_projection_performance_budget(tmp_path):
    repository = AppCenterRepository(tmp_path / "result-history.sqlite")
    project = repository.create_project("性能项目", "验证最新十条")
    for index in range(100):
        run = repository.create_app_run(
            project.project_id,
            "builtin.marketing-copy",
            "1.1.0",
            {},
            idempotency_key=f"history-performance-{index:03d}",
        )
        repository.transition_app_run(run.app_run_id, "queued")
        repository.transition_app_run(run.app_run_id, "running")
    started = time.perf_counter()
    page = ResultHistoryProjectionService(repository).list_records(
        project.project_id,
        app_id="builtin.marketing-copy",
        limit=10,
    )
    elapsed_ms = (time.perf_counter() - started) * 1000
    assert len(page["records"]) == 10
    assert elapsed_ms < 350
