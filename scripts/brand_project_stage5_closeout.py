"""Bounded BRAND-PROJECT-5 closeout evidence on isolated local data.

The script never touches the source legacy database, never calls an external
provider, and never performs a publish action.  It supports discrete phases so
Browser validation can run between flag transitions.
"""

# ruff: noqa: E402

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import shutil
import socket
import sqlite3
import statistics
import subprocess
import sys
import tempfile
import time
from copy import deepcopy
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from brand_project_stage4_visual_fixture import seed

from api.config import APIConfig
from pixelle_video.app_center.brand_project import BrandProjectService, ProjectContextResolver
from pixelle_video.app_center.migration import AppCenterMigrationError, migrate_app_center
from pixelle_video.app_center.registry import BUILTIN_MANIFESTS
from pixelle_video.app_center.repository import AppCenterRepository
from pixelle_video.services.assets_v2.repository import AssetLibraryRepository

BUSINESS_TABLES = (
    "content_projects",
    "context_snapshots",
    "app_runs",
    "artifacts",
    "artifact_versions",
    "artifact_handoffs",
)
TOKEN = "brand-project-stage5-local"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _normalized(value: object) -> object:
    if isinstance(value, bytes):
        return {"bytes_sha256": hashlib.sha256(value).hexdigest()}
    return value


def _table_digest(connection: sqlite3.Connection, table: str) -> dict[str, object]:
    rows = connection.execute(f'SELECT * FROM "{table}" ORDER BY rowid').fetchall()
    payload = [[_normalized(value) for value in row] for row in rows]
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return {
        "rows": len(rows),
        "sha256": hashlib.sha256(encoded).hexdigest(),
    }


def _database_digest(path: Path, tables: tuple[str, ...] = BUSINESS_TABLES) -> dict[str, object]:
    with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as connection:
        existing = {
            row[0]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        }
        table_state = {
            table: _table_digest(connection, table) for table in tables if table in existing
        }
        integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
        foreign_keys = connection.execute("PRAGMA foreign_key_check").fetchall()
    encoded = json.dumps(
        table_state,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return {
        "file_sha256": _sha256(path),
        "file_size": path.stat().st_size,
        "tables": table_state,
        "business_sha256": hashlib.sha256(encoded).hexdigest(),
        "integrity_check": integrity,
        "foreign_key_errors": foreign_keys,
    }


def _legacy_projection_digest(
    path: Path,
    table: str,
    columns: list[str] | None = None,
) -> tuple[list[str], dict[str, object]]:
    with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as connection:
        selected_columns = columns or [
            str(row[1]) for row in connection.execute(f'PRAGMA table_info("{table}")')
        ]
        projection = ", ".join(f'"{column}"' for column in selected_columns)
        rows = connection.execute(f'SELECT {projection} FROM "{table}" ORDER BY rowid').fetchall()
    payload = [[_normalized(value) for value in row] for row in rows]
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return selected_columns, {
        "rows": len(rows),
        "sha256": hashlib.sha256(encoded).hexdigest(),
    }


def _project_digest(path: Path, project_id: str) -> dict[str, object]:
    queries = {
        "content_projects": (
            "SELECT * FROM content_projects WHERE project_id = ? ORDER BY rowid",
            (project_id,),
        ),
        "context_snapshots": (
            "SELECT * FROM context_snapshots WHERE project_id = ? ORDER BY rowid",
            (project_id,),
        ),
        "app_runs": (
            "SELECT * FROM app_runs WHERE project_id = ? ORDER BY rowid",
            (project_id,),
        ),
        "artifacts": (
            "SELECT * FROM artifacts WHERE project_id = ? ORDER BY rowid",
            (project_id,),
        ),
        "artifact_versions": (
            "SELECT * FROM artifact_versions WHERE project_id = ? ORDER BY rowid",
            (project_id,),
        ),
        "artifact_handoffs": (
            "SELECT * FROM artifact_handoffs WHERE project_id = ? ORDER BY rowid",
            (project_id,),
        ),
    }
    state: dict[str, object] = {}
    with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as connection:
        for table, (query, params) in queries.items():
            rows = connection.execute(query, params).fetchall()
            payload = [[_normalized(value) for value in row] for row in rows]
            encoded = json.dumps(
                payload,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
            state[table] = {
                "rows": len(rows),
                "sha256": hashlib.sha256(encoded).hexdigest(),
            }
    encoded = json.dumps(
        state,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return {
        "project_id": project_id,
        "tables": state,
        "project_business_sha256": hashlib.sha256(encoded).hexdigest(),
    }


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _percentiles(samples_ms: list[float], budget_ms: float) -> dict[str, object]:
    ordered = sorted(samples_ms)
    p95_index = max(0, min(len(ordered) - 1, (95 * len(ordered) + 99) // 100 - 1))
    result = {
        "samples": len(ordered),
        "p50_ms": round(statistics.median(ordered), 3),
        "p95_ms": round(ordered[p95_index], 3),
        "max_ms": round(max(ordered), 3),
        "budget_ms": budget_ms,
        "within_budget": ordered[p95_index] <= budget_ms,
        "budget_kind": "wide_local_regression_guard_not_sla",
    }
    if not result["within_budget"]:
        raise RuntimeError(f"local regression guard exceeded: {result}")
    return result


def _benchmark(root: Path, fixture: dict[str, object]) -> dict[str, object]:
    data_root = root / "data"
    assets = AssetLibraryRepository(data_root)
    repository = AppCenterRepository(
        data_root / "app_center.sqlite",
        asset_repository=assets,
    )
    resolver = ProjectContextResolver(repository, assets)
    project_id = str(fixture["project_id"])
    snapshot_id = str(fixture["current_context_snapshot_id"])
    before = _project_digest(repository.db_path, project_id)
    operations = {
        "get_project": lambda: repository.get_project(project_id),
        "get_context_snapshot": lambda: repository.get_context_snapshot(snapshot_id),
        "resolve_for_run": lambda: resolver.resolve_for_run(project_id, snapshot_id),
    }
    results: dict[str, object] = {}
    for name, operation in operations.items():
        samples: list[float] = []
        for _ in range(10):
            started = time.perf_counter()
            operation()
            samples.append((time.perf_counter() - started) * 1000)
        results[name] = _percentiles(samples, 250.0)
    after = _project_digest(repository.db_path, project_id)
    if before != after:
        raise RuntimeError("benchmark reads changed project business rows")
    return {
        "iterations_per_operation": 10,
        "operations": results,
        "project_state_before": before,
        "project_state_after": after,
        "read_operations_zero_write": True,
    }


def _static_flags() -> dict[str, object]:
    name = "PIXELLE_BRAND_PROJECT_BOUNDARY_V1"
    previous = os.environ.pop(name, None)
    try:
        backend_default = APIConfig().brand_project_boundary_v1_enabled
    finally:
        if previous is not None:
            os.environ[name] = previous
    matrix = json.loads(
        (ROOT / "docs/contracts/app-center/feature-flag-matrix.json").read_text(encoding="utf-8")
    )
    matrix_flag = next(item for item in matrix["flags"] if item["name"] == "brandProjectBoundaryV1")
    production_env = (ROOT / "desktop/.env.production").read_text(encoding="utf-8")
    frontend_source = (ROOT / "desktop/src/flagResolver.ts").read_text(encoding="utf-8")
    result = {
        "backend_runtime_default": backend_default,
        "contract_default": matrix_flag["default"],
        "production_env_has_override": "VITE_BRAND_PROJECT_BOUNDARY_V1" in production_env,
        "frontend_fallback_false_present": (
            '"VITE_BRAND_PROJECT_BOUNDARY_V1"' in frontend_source
            and '"PIXELLE_BRAND_PROJECT_BOUNDARY_V1"' in frontend_source
            and "false," in frontend_source
        ),
    }
    if result != {
        "backend_runtime_default": False,
        "contract_default": False,
        "production_env_has_override": False,
        "frontend_fallback_false_present": True,
    }:
        raise RuntimeError(f"brand-project defaults are not fail-closed: {result}")
    return result


def _migration_evidence(old_db: Path) -> dict[str, object]:
    source_before = _sha256(old_db)
    with tempfile.TemporaryDirectory(prefix="pixelle-brand-project-stage5-migration-") as work:
        work_dir = Path(work)
        migration_copy = work_dir / "legacy-app-center-migration.sqlite"
        failure_copy = work_dir / "legacy-app-center-failure.sqlite"
        shutil.copy2(old_db, migration_copy)
        shutil.copy2(old_db, failure_copy)
        before = _database_digest(migration_copy)
        legacy_projections: dict[str, dict[str, object]] = {}
        legacy_columns: dict[str, list[str]] = {}
        for table in BUSINESS_TABLES:
            columns, digest = _legacy_projection_digest(migration_copy, table)
            legacy_columns[table] = columns
            legacy_projections[table] = digest
        migrate_app_center(migration_copy)
        after = _database_digest(migration_copy)
        migrated_legacy_projections = {
            table: _legacy_projection_digest(
                migration_copy,
                table,
                columns=legacy_columns[table],
            )[1]
            for table in BUSINESS_TABLES
        }
        source_after_success = _sha256(old_db)
        if source_before != source_after_success:
            raise RuntimeError("source legacy SQLite changed during copy migration")
        for table in BUSINESS_TABLES:
            if legacy_projections[table] != migrated_legacy_projections[table]:
                raise RuntimeError(f"migration changed legacy columns in business table: {table}")
        with sqlite3.connect(f"file:{migration_copy}?mode=ro", uri=True) as connection:
            artifact_version_columns = [
                row[1] for row in connection.execute("PRAGMA table_info(artifact_versions)")
            ]
            handoff_columns = [
                row[1] for row in connection.execute("PRAGMA table_info(artifact_handoffs)")
            ]
            context_sql = connection.execute(
                "SELECT sql FROM sqlite_master WHERE name = 'context_snapshots'"
            ).fetchone()[0]
        required_columns_added = {
            "artifact_versions": all(
                item in artifact_version_columns
                for item in ("source_app_run_id", "context_snapshot_id")
            ),
            "artifact_handoffs": all(
                item in handoff_columns
                for item in ("source_context_snapshot_id", "target_context_snapshot_id")
            ),
            "context_schema_v3_allowed": "schema_version IN (1, 2, 3)"
            in " ".join(context_sql.split()),
        }
        if not all(required_columns_added.values()):
            raise RuntimeError(f"legacy migration incomplete: {required_columns_added}")

        failed_before = _sha256(failure_copy)
        manifests = deepcopy(BUILTIN_MANIFESTS)
        manifests[0]["name"] = "intentional-stage5-registry-drift"
        failure_code = None
        try:
            migrate_app_center(failure_copy, manifests=manifests)
        except AppCenterMigrationError as exc:
            failure_code = str(exc)
        failed_after = _sha256(failure_copy)
        if failure_code is None or failed_before != failed_after:
            raise RuntimeError("failed migration did not preserve the visible database")
        source_after_failure = _sha256(old_db)
        if source_before != source_after_failure:
            raise RuntimeError("source legacy SQLite changed during rollback injection")
    return {
        "source": {
            "path": str(old_db),
            "sha256_before": source_before,
            "sha256_after": source_after_failure,
            "unchanged": source_before == source_after_failure,
        },
        "successful_copy": {
            "binary_copy_retained": False,
            "temporary_copy_deleted_after_verification": True,
            "before": before,
            "after": after,
            "legacy_column_projections_before": legacy_projections,
            "legacy_column_projections_after": migrated_legacy_projections,
            "business_rows_preserved": all(
                legacy_projections[table] == migrated_legacy_projections[table]
                for table in BUSINESS_TABLES
            ),
            "required_columns_added": required_columns_added,
            "integrity_check": after["integrity_check"],
            "foreign_key_errors": after["foreign_key_errors"],
        },
        "failure_injection": {
            "binary_copy_retained": False,
            "temporary_copy_deleted_after_verification": True,
            "error": failure_code,
            "sha256_before": failed_before,
            "sha256_after": failed_after,
            "visible_database_unchanged": failed_before == failed_after,
        },
    }


def _project_row_hashes(path: Path, project_id: str) -> dict[str, object]:
    queries = {
        "content_projects": ("project_id", "project_id = ?", (project_id,)),
        "context_snapshots": ("context_snapshot_id", "project_id = ?", (project_id,)),
        "app_runs": ("app_run_id", "project_id = ?", (project_id,)),
        "artifacts": ("artifact_id", "project_id = ?", (project_id,)),
        "artifact_versions": ("artifact_version_id", "project_id = ?", (project_id,)),
        "artifact_handoffs": ("handoff_id", "project_id = ?", (project_id,)),
    }
    result: dict[str, object] = {}
    with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as connection:
        connection.row_factory = sqlite3.Row
        for table, (primary_key, where, params) in queries.items():
            rows = connection.execute(
                f'SELECT * FROM "{table}" WHERE {where} ORDER BY rowid',
                params,
            ).fetchall()
            result[table] = {
                "primary_key": primary_key,
                "rows": {
                    str(row[primary_key]): hashlib.sha256(
                        json.dumps(
                            [_normalized(value) for value in tuple(row)],
                            ensure_ascii=False,
                            sort_keys=True,
                            separators=(",", ":"),
                        ).encode()
                    ).hexdigest()
                    for row in rows
                },
            }
    return result


def _project_stable_projection_hash(path: Path, project_id: str) -> str:
    excluded = {"current_context_snapshot_id", "updated_at"}
    with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as connection:
        columns = [
            str(row[1])
            for row in connection.execute('PRAGMA table_info("content_projects")')
            if row[1] not in excluded
        ]
        projection = ", ".join(f'"{column}"' for column in columns)
        row = connection.execute(
            f"SELECT {projection} FROM content_projects WHERE project_id = ?",
            (project_id,),
        ).fetchone()
    encoded = json.dumps(
        [_normalized(value) for value in row],
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def _port_open(port: int) -> bool:
    with socket.socket() as sock:
        sock.settimeout(0.25)
        return sock.connect_ex(("127.0.0.1", port)) == 0


def _request_json(url: str, *, timeout: float = 1.0) -> tuple[int, object]:
    request = Request(url, headers={"X-Pixelle-Desktop-Token": TOKEN})
    with urlopen(request, timeout=timeout) as response:
        return response.status, json.loads(response.read().decode("utf-8"))


def _wait_health(port: int, timeout: float = 15.0) -> dict[str, object]:
    deadline = time.monotonic() + timeout
    last_error = "not_started"
    while time.monotonic() < deadline:
        try:
            _status, payload = _request_json(f"http://127.0.0.1:{port}/health")
            return payload
        except Exception as exc:  # pragma: no cover - bounded runtime probe
            last_error = type(exc).__name__
            time.sleep(0.1)
    raise RuntimeError(f"health_timeout:{last_error}")


def _sidecar_cycles(
    root: Path,
    fixture: dict[str, object],
    *,
    cycles: int,
    port: int,
) -> dict[str, object]:
    app_db = root / "data/app_center.sqlite"
    project_id = str(fixture["project_id"])
    before = _project_digest(app_db, project_id)
    results: list[dict[str, object]] = []
    interface_samples: dict[str, list[float]] = {
        "list_projects": [],
        "get_project": [],
        "list_context_snapshots": [],
    }
    endpoints = {
        "list_projects": "/api/content-projects",
        "get_project": f"/api/content-projects/{project_id}",
        "list_context_snapshots": f"/api/content-projects/{project_id}/context-snapshots",
    }
    for cycle in range(1, cycles + 1):
        flag_enabled = cycle > cycles // 2
        env = {
            **os.environ,
            "PIXELLE_VIDEO_ROOT": str(root),
            "PIXELLE_APP_CENTER_DB": str(app_db),
            "PIXELLE_DESKTOP_TASKS_DB": str(root / "data/desktop_tasks.sqlite"),
            "PIXELLE_DESKTOP_MODE": "1",
            "PIXELLE_DESKTOP_TOKEN": TOKEN,
            "PIXELLE_LOCAL_CAPABILITY": TOKEN,
            "PIXELLE_ASSET_CENTER_V2": "true",
            "PIXELLE_BRAND_PROJECT_BOUNDARY_V1": ("true" if flag_enabled else "false"),
        }
        process = subprocess.Popen(
            [
                sys.executable,
                "api/app.py",
                "--host",
                "127.0.0.1",
                "--port",
                str(port),
            ],
            cwd=ROOT,
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        cycle_result: dict[str, object] = {
            "cycle": cycle,
            "flag_enabled": flag_enabled,
        }
        try:
            cycle_result["health"] = _wait_health(port)
            apps_status, apps = _request_json(f"http://127.0.0.1:{port}/api/apps")
            projects_status, projects = _request_json(
                f"http://127.0.0.1:{port}/api/content-projects"
            )
            cycle_result.update(
                {
                    "health_status": 200,
                    "apps_status": apps_status,
                    "app_count": len(apps.get("items", [])),
                    "projects_status": projects_status,
                    "project_count": len(projects),
                    "port_open": _port_open(port),
                }
            )
            if cycle == cycles:
                for name, endpoint in endpoints.items():
                    for _ in range(10):
                        started = time.perf_counter()
                        status, _payload = _request_json(f"http://127.0.0.1:{port}{endpoint}")
                        if status != 200:
                            raise RuntimeError(f"interface benchmark failed: {endpoint}")
                        interface_samples[name].append((time.perf_counter() - started) * 1000)
        finally:
            process.terminate()
            try:
                process.wait(timeout=8)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=3)
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline and _port_open(port):
            time.sleep(0.1)
        cycle_result["returncode"] = process.returncode
        cycle_result["port_released"] = not _port_open(port)
        results.append(cycle_result)
    after = _project_digest(app_db, project_id)
    if before != after:
        raise RuntimeError("sidecar startup or authenticated reads changed project business rows")
    if not all(
        item.get("health_status") == 200
        and item.get("apps_status") == 200
        and item.get("projects_status") == 200
        and item.get("port_released") is True
        for item in results
    ):
        raise RuntimeError(f"sidecar lifecycle failed: {results}")
    return {
        "cycles": results,
        "cycles_passed": cycles,
        "off_cycles": cycles // 2,
        "on_cycles": cycles - cycles // 2,
        "project_state_before": before,
        "project_state_after": after,
        "startup_and_reads_zero_business_write": True,
        "interface_benchmark": {
            name: _percentiles(samples, 500.0) for name, samples in interface_samples.items()
        },
        "external_actions": 0,
        "final_publish_clicks": 0,
    }


def _load_fixture(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def prepare(args: argparse.Namespace) -> None:
    root = args.root.resolve()
    root.mkdir(parents=True, exist_ok=True)
    fixture = asyncio.run(seed(root))
    _write_json(args.fixture, fixture)
    evidence = {
        "stage": "BRAND-PROJECT-5",
        "phase": "prepare",
        "isolated_root": str(root),
        "static_flags": _static_flags(),
        "fixture": fixture,
        "baseline_project_state": _project_digest(
            root / "data/app_center.sqlite",
            str(fixture["project_id"]),
        ),
        "benchmark": _benchmark(root, fixture),
        "migration": _migration_evidence(args.old_db.resolve()),
        "external_actions": 0,
        "final_publish_clicks": 0,
    }
    _write_json(args.output, evidence)
    print(json.dumps(evidence, ensure_ascii=False, indent=2))


def update_brand(args: argparse.Namespace) -> None:
    root = args.root.resolve()
    fixture = _load_fixture(args.fixture)
    app_db = root / "data/app_center.sqlite"
    project_id = str(fixture["project_id"])
    before = _project_digest(app_db, project_id)
    assets = AssetLibraryRepository(root / "data")
    desired = {
        "brand_name": "北岸咖啡 · Stage5 显式同步",
        "primary_color": "#155E75",
        "store_address": "江湾路 108 号",
    }
    metadata = assets.domain_snapshot_metadata("brand", "brand-stage4-visual")
    write_performed = not all(metadata.get(key) == value for key, value in desired.items())
    if write_performed:
        assets.patch_brand_kit("brand-stage4-visual", desired)
    updated_metadata = assets.domain_snapshot_metadata("brand", "brand-stage4-visual")
    after = _project_digest(app_db, project_id)
    if before != after:
        raise RuntimeError("brand update silently changed project business rows")
    evidence = {
        "stage": "BRAND-PROJECT-5",
        "phase": "brand_updated_before_rollback",
        "brand_domain_revision": updated_metadata["domain_revision"],
        "write_performed_by_this_invocation": write_performed,
        "desired_values_present": all(
            updated_metadata.get(key) == value for key, value in desired.items()
        ),
        "project_state_before": before,
        "project_state_after": after,
        "project_rows_unchanged": True,
        "external_actions": 0,
    }
    _write_json(args.output, evidence)
    print(json.dumps(evidence, ensure_ascii=False, indent=2))


def capture(args: argparse.Namespace) -> None:
    root = args.root.resolve()
    fixture = _load_fixture(args.fixture)
    evidence = {
        "stage": "BRAND-PROJECT-5",
        "phase": args.label,
        "project_state": _project_digest(
            root / "data/app_center.sqlite",
            str(fixture["project_id"]),
        ),
        "database_state": _database_digest(root / "data/app_center.sqlite"),
        "external_actions": 0,
    }
    _write_json(args.output, evidence)
    print(json.dumps(evidence, ensure_ascii=False, indent=2))


def continue_after_rollback(args: argparse.Namespace) -> None:
    root = args.root.resolve()
    fixture = _load_fixture(args.fixture)
    data_root = root / "data"
    assets = AssetLibraryRepository(data_root)
    repository = AppCenterRepository(
        data_root / "app_center.sqlite",
        asset_repository=assets,
    )
    project_id = str(fixture["project_id"])
    before_db = args.before_db.resolve() if args.before_db else repository.db_path
    before = _project_digest(before_db, project_id)
    row_hashes_before = _project_row_hashes(before_db, project_id)
    project_stable_hash_before = _project_stable_projection_hash(
        before_db,
        project_id,
    )
    project = repository.get_project(project_id)
    service = BrandProjectService(repository, assets)
    preview = service.preview_brand_sync(
        project_id,
        expected_context_snapshot_id=project.current_context_snapshot_id,
    )
    recovered_after_evidence_serialization_error = not preview["has_changes"]
    if preview["has_changes"]:
        sync = service.sync_brand(
            project_id,
            expected_context_snapshot_id=project.current_context_snapshot_id,
            idempotency_key="stage5-explicit-sync-after-rollback",
        )
        run = repository.create_app_run(
            project_id,
            "builtin.viral-titles",
            "1.0.0",
            {"goal": "Stage5 回滚后新运行"},
            idempotency_key="stage5-new-run-after-rollback",
        )
        artifact = repository.create_artifact(
            project_id,
            "selected_title",
            "Stage5 回滚后新结果",
            source_app_run_id=run.app_run_id,
        )
        version = repository.append_artifact_version(
            artifact.artifact_id,
            content={
                "artifact_type": "selected_title",
                "title": "回滚后仍可继续显式同步与新运行",
            },
        )
    else:
        sync = {
            "result_code": "PROJECT_BRAND_SYNC_APPLIED",
            "context_snapshot_id": project.current_context_snapshot_id,
        }
        run = repository.get_app_run_by_idempotency_key("stage5-new-run-after-rollback")
        if run is None:
            raise RuntimeError("post-sync recovery could not find the idempotent run")
        artifacts = [
            item
            for item in repository.list_artifacts(project_id)
            if item.source_app_run_id == run.app_run_id and item.name == "Stage5 回滚后新结果"
        ]
        if len(artifacts) != 1:
            raise RuntimeError(f"post-sync recovery found {len(artifacts)} result artifacts")
        artifact = artifacts[0]
        versions = repository.list_artifact_versions(artifact.artifact_id)
        if len(versions) != 1:
            raise RuntimeError(f"post-sync recovery found {len(versions)} result versions")
        version = versions[0]
    after = _project_digest(repository.db_path, project_id)
    row_hashes_after = _project_row_hashes(repository.db_path, project_id)
    project_stable_hash_after = _project_stable_projection_hash(
        repository.db_path,
        project_id,
    )
    expected_row_deltas = {
        "content_projects": 0,
        "context_snapshots": 1,
        "app_runs": 1,
        "artifacts": 1,
        "artifact_versions": 1,
        "artifact_handoffs": 0,
    }
    actual_row_deltas = {
        table: int(after["tables"][table]["rows"]) - int(before["tables"][table]["rows"])
        for table in BUSINESS_TABLES
    }
    immutable_existing_rows = {}
    for table in BUSINESS_TABLES[1:]:
        before_rows = row_hashes_before[table]["rows"]
        after_rows = row_hashes_after[table]["rows"]
        immutable_existing_rows[table] = {
            "before": before_rows,
            "after_for_existing_ids": {row_id: after_rows.get(row_id) for row_id in before_rows},
            "unchanged": all(
                after_rows.get(row_id) == row_hash for row_id, row_hash in before_rows.items()
            ),
        }
    evidence = {
        "stage": "BRAND-PROJECT-5",
        "phase": "continued_after_rollback",
        "preview_has_changes": preview["has_changes"],
        "sync_result": sync["result_code"],
        "recovered_after_evidence_serialization_error": (
            recovered_after_evidence_serialization_error
        ),
        "before_checkpoint": {
            "path": str(before_db),
            "project_business_sha256": before["project_business_sha256"],
        },
        "new_context_snapshot_id": sync["context_snapshot_id"],
        "new_run_id": run.app_run_id,
        "new_run_context_snapshot_id": run.context_snapshot_id,
        "new_artifact_id": artifact.artifact_id,
        "new_artifact_version_id": version.artifact_version_id,
        "new_artifact_context_snapshot_id": version.context_snapshot_id,
        "new_run_and_artifact_use_synced_context": (
            run.context_snapshot_id == version.context_snapshot_id == sync["context_snapshot_id"]
        ),
        "expected_row_deltas": expected_row_deltas,
        "actual_row_deltas": actual_row_deltas,
        "expected_row_deltas_match": actual_row_deltas == expected_row_deltas,
        "content_project_expected_pointer_update_only": {
            "excluded_columns": ["current_context_snapshot_id", "updated_at"],
            "stable_projection_sha256_before": project_stable_hash_before,
            "stable_projection_sha256_after": project_stable_hash_after,
            "unchanged": project_stable_hash_before == project_stable_hash_after,
        },
        "preexisting_append_only_row_hashes": immutable_existing_rows,
        "all_preexisting_append_only_rows_unchanged": all(
            item["unchanged"] for item in immutable_existing_rows.values()
        ),
        "project_state_before": before,
        "project_state_after": after,
        "external_actions": 0,
        "final_publish_clicks": 0,
    }
    if not evidence["new_run_and_artifact_use_synced_context"]:
        raise RuntimeError("post-rollback run did not pin the explicitly synced context")
    if not evidence["expected_row_deltas_match"]:
        raise RuntimeError(f"unexpected post-rollback row deltas: {actual_row_deltas}")
    if not evidence["content_project_expected_pointer_update_only"]["unchanged"]:
        raise RuntimeError("sync changed content_projects outside the expected pointer/timestamp")
    if not evidence["all_preexisting_append_only_rows_unchanged"]:
        raise RuntimeError("sync/new run changed preexisting append-only rows")
    _write_json(args.output, evidence)
    print(json.dumps(evidence, ensure_ascii=False, indent=2))


def sidecar(args: argparse.Namespace) -> None:
    fixture = _load_fixture(args.fixture)
    evidence = {
        "stage": "BRAND-PROJECT-5",
        "phase": "sidecar_lifecycle",
        **_sidecar_cycles(
            args.root.resolve(),
            fixture,
            cycles=args.cycles,
            port=args.port,
        ),
    }
    _write_json(args.output, evidence)
    print(json.dumps(evidence, ensure_ascii=False, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)

    prepare_parser = subparsers.add_parser("prepare")
    prepare_parser.add_argument("--root", type=Path, required=True)
    prepare_parser.add_argument("--old-db", type=Path, required=True)
    prepare_parser.add_argument("--fixture", type=Path, required=True)
    prepare_parser.add_argument("--output", type=Path, required=True)
    prepare_parser.set_defaults(func=prepare)

    update_parser = subparsers.add_parser("update-brand")
    update_parser.add_argument("--root", type=Path, required=True)
    update_parser.add_argument("--fixture", type=Path, required=True)
    update_parser.add_argument("--output", type=Path, required=True)
    update_parser.set_defaults(func=update_brand)

    capture_parser = subparsers.add_parser("capture")
    capture_parser.add_argument("--root", type=Path, required=True)
    capture_parser.add_argument("--fixture", type=Path, required=True)
    capture_parser.add_argument("--label", required=True)
    capture_parser.add_argument("--output", type=Path, required=True)
    capture_parser.set_defaults(func=capture)

    continue_parser = subparsers.add_parser("continue")
    continue_parser.add_argument("--root", type=Path, required=True)
    continue_parser.add_argument("--fixture", type=Path, required=True)
    continue_parser.add_argument("--before-db", type=Path)
    continue_parser.add_argument("--output", type=Path, required=True)
    continue_parser.set_defaults(func=continue_after_rollback)

    sidecar_parser = subparsers.add_parser("sidecar")
    sidecar_parser.add_argument("--root", type=Path, required=True)
    sidecar_parser.add_argument("--fixture", type=Path, required=True)
    sidecar_parser.add_argument("--cycles", type=int, default=10)
    sidecar_parser.add_argument("--port", type=int, default=8117)
    sidecar_parser.add_argument("--output", type=Path, required=True)
    sidecar_parser.set_defaults(func=sidecar)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
