"""Safe local SQLite bootstrap for the application-center database."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Iterable

from .registry import BUILTIN_MANIFESTS


class AppCenterMigrationError(RuntimeError):
    """A fail-closed migration or seed error."""


def default_db_path() -> Path:
    return Path(os.environ.get("PIXELLE_APP_CENTER_DB", "data/app_center.sqlite"))


@contextmanager
def _exclusive_lock(lock_path: Path):
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    handle = lock_path.open("a+")
    try:
        try:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise AppCenterMigrationError("app-center migration is already running") from exc
        except ImportError:  # pragma: no cover - desktop target is POSIX
            pass
        yield
    finally:
        try:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        except (ImportError, OSError):
            pass
        handle.close()


def _script_checksum(script: str) -> str:
    return "sha256:" + hashlib.sha256(script.encode("utf-8")).hexdigest()


def _backup_path(path: Path) -> Path:
    stamp = time.strftime("%Y%m%d%H%M%S", time.gmtime())
    return path.with_name(f"{path.name}.bak.{stamp}")


def _seed_registry(conn: sqlite3.Connection, manifests: Iterable[dict]) -> None:
    manifests = tuple(manifests)
    for manifest in manifests:
        app_id = str(manifest["app_id"])
        version = str(manifest["version"])
        manifest_json = json.dumps(manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        existing = conn.execute(
            "SELECT manifest_json, source FROM app_registry WHERE app_id = ? AND version = ?",
            (app_id, version),
        ).fetchone()
        if existing and (existing[0] != manifest_json or existing[1] != "builtin_code"):
            raise AppCenterMigrationError(f"registry seed drift for {app_id}@{version}")
        conn.execute(
            """
            INSERT INTO app_registry (
                app_id, schema_version, version, manifest_json, status, feature_flag,
                source, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, 'builtin_code', datetime('now'), datetime('now'))
            ON CONFLICT(app_id, version) DO UPDATE SET
                schema_version=excluded.schema_version,
                manifest_json=excluded.manifest_json,
                status=excluded.status,
                feature_flag=excluded.feature_flag,
                source='builtin_code',
                updated_at=datetime('now')
            """,
            (
                app_id,
                int(manifest["schema_version"]),
                version,
                manifest_json,
                str(manifest["status"]),
                str(manifest["feature_flag"]),
            ),
        )
    expected = {(str(item["app_id"]), str(item["version"])) for item in manifests}
    actual = {
        (row[0], row[1])
        for row in conn.execute("SELECT app_id, version FROM app_registry WHERE source = 'builtin_code'")
    }
    if not expected <= actual:
        raise AppCenterMigrationError("registry seed verification failed")


def migrate_app_center(
    db_path: str | Path | None = None,
    *,
    manifests: Iterable[dict] = BUILTIN_MANIFESTS,
) -> Path:
    """Create/upgrade the app-center DB and seed trusted manifests.

    The function never downgrades or deletes a database. Existing databases are
    backed up before schema work; any error restores that backup and raises a
    read-only migration error.
    """

    path = Path(db_path) if db_path is not None else default_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = path.with_suffix(path.suffix + ".lock")
    existed = path.exists()
    script_path = Path(__file__).resolve().parents[2] / "docs/contracts/app-center/app-center-v1.sql"
    script = script_path.read_text(encoding="utf-8")
    checksum = _script_checksum(script)

    with _exclusive_lock(lock_path):
        staging = path.with_name(f"{path.name}.staging.{uuid.uuid4().hex}")
        if existed:
            shutil.copy2(path, _backup_path(path))
        try:
            # All schema and registry work happens in a private copy.  The
            # visible database is replaced only after every check, migration,
            # seed, and FK validation succeeds; a process crash cannot expose
            # a schema-without-seed window.
            if existed:
                shutil.copy2(path, staging)
            conn = sqlite3.connect(staging)
            conn.execute("PRAGMA foreign_keys = ON")
            integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
            if integrity != "ok":
                raise AppCenterMigrationError(f"SQLite integrity check failed: {integrity}")

            user_tables = {
                row[0]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
                )
            }
            if user_tables and "app_schema_migrations" not in user_tables:
                raise AppCenterMigrationError("not an application-center database")
            if "app_schema_migrations" in user_tables:
                row = conn.execute(
                    "SELECT checksum, schema_version FROM app_schema_migrations WHERE migration_id = 'app-center-v1'"
                ).fetchone()
                if row and row[1] > 1:
                    raise AppCenterMigrationError("future app-center schema version")
                if row and row[0] not in {"sha256:app-center-v1", checksum}:
                    raise AppCenterMigrationError("app-center migration checksum drift")

            # Keep schema creation, checksum update, registry seed, and FK
            # verification in the same staging transaction.  ``executescript``
            # normally commits around a script, so explicitly open the
            # transaction as the first statement and commit only below.
            conn.executescript("BEGIN IMMEDIATE;\n" + script)
            conn.execute(
                "UPDATE app_schema_migrations SET checksum = ? WHERE migration_id = 'app-center-v1'",
                (checksum,),
            )
            _seed_registry(conn, manifests)
            foreign_key_errors = conn.execute("PRAGMA foreign_key_check").fetchall()
            if foreign_key_errors:
                raise AppCenterMigrationError(f"foreign key check failed: {foreign_key_errors}")
            conn.commit()
            conn.close()
            os.replace(staging, path)
        except (sqlite3.DatabaseError, OSError, AppCenterMigrationError) as exc:
            try:
                conn.close()
            except (NameError, UnboundLocalError, sqlite3.Error):
                pass
            if staging.exists():
                staging.unlink()
            if isinstance(exc, AppCenterMigrationError):
                raise
            raise AppCenterMigrationError("app-center migration failed; database left unchanged") from exc
    return path


def connect_app_center(db_path: str | Path | None = None) -> sqlite3.Connection:
    """Open a migrated database with foreign-key enforcement."""

    path = migrate_app_center(db_path)
    conn = sqlite3.connect(path, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn
