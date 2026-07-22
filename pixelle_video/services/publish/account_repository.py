"""SQLite repository for local publish accounts and browser context metadata."""

from __future__ import annotations

import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from pixelle_video.services.publish.account_models import (
    ACCOUNT_LOGIN_TRANSITIONS,
    AccountLoginState,
    AccountVerificationState,
    PublishAccount,
    PublishPlatform,
)
from pixelle_video.utils.os_util import get_data_path

PLATFORM_LABELS = {
    PublishPlatform.DOUYIN.value: "抖音",
    PublishPlatform.VIDEO_CHANNEL.value: "视频号",
    PublishPlatform.KUAISHOU.value: "快手",
    PublishPlatform.XIAOHONGSHU.value: "小红书",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class PublishAccountNotFound(LookupError):
    """Requested account does not exist."""


class PublishAccountConflict(RuntimeError):
    """A safe account operation cannot proceed due to current state."""


class PublishAccountRepository:
    """Owns only publishing account metadata, never browser credentials."""

    def __init__(self, db_path: str | Path | None = None):
        self.db_path = Path(db_path or get_data_path("publishing", "publishing.sqlite3")).resolve()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.migrate()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 30000")
        return connection

    @contextmanager
    def _transaction(self) -> Iterator[sqlite3.Connection]:
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def migrate(self) -> None:
        schema_path = Path(__file__).resolve().parents[3] / "docs/contracts/publishing/publishing-v2.sql"
        with self._connect() as connection:
            if schema_path.exists():
                connection.executescript(schema_path.read_text(encoding="utf-8"))
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS publish_account_state (
                  account_id TEXT PRIMARY KEY REFERENCES publish_accounts(account_id) ON DELETE CASCADE,
                  platform TEXT NOT NULL,
                  login_state TEXT NOT NULL DEFAULT 'not_connected',
                  is_default INTEGER NOT NULL DEFAULT 0 CHECK (is_default IN (0, 1)),
                  profile_exists INTEGER NOT NULL DEFAULT 0 CHECK (profile_exists IN (0, 1)),
                  login_subject_hint TEXT,
                  identity_fingerprint TEXT,
                  last_error_code TEXT,
                  archived_at TEXT,
                  updated_at TEXT NOT NULL
                );
                CREATE UNIQUE INDEX IF NOT EXISTS publish_account_default_by_platform
                  ON publish_account_state(platform)
                  WHERE is_default = 1 AND archived_at IS NULL;
                CREATE TABLE IF NOT EXISTS publish_profile_locks (
                  account_id TEXT PRIMARY KEY REFERENCES publish_accounts(account_id) ON DELETE CASCADE,
                  owner_ref TEXT NOT NULL,
                  pid INTEGER,
                  acquired_at TEXT NOT NULL,
                  heartbeat_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS publish_context_registry (
                  context_id TEXT PRIMARY KEY,
                  account_id TEXT NOT NULL REFERENCES publish_accounts(account_id) ON DELETE CASCADE,
                  window_ref TEXT,
                  status TEXT NOT NULL CHECK (status IN ('open', 'closed', 'stale')),
                  created_at TEXT NOT NULL,
                  updated_at TEXT NOT NULL
                );
                """
            )
            now = utc_now()
            rows = connection.execute(
                "SELECT account_id, platform FROM publish_accounts"
            ).fetchall()
            for row in rows:
                connection.execute(
                    """
                    INSERT OR IGNORE INTO publish_account_state
                      (account_id, platform, updated_at)
                    VALUES (?, ?, ?)
                    """,
                    (row["account_id"], row["platform"], now),
                )
            connection.commit()

    def create_account(
        self,
        platform: PublishPlatform | str,
        display_name: str,
        profile_ref: str,
        *,
        make_default: bool = False,
        account_id: str | None = None,
    ) -> PublishAccount:
        platform_value = str(platform)
        if platform_value not in PLATFORM_LABELS:
            raise ValueError("不支持的发布平台")
        account_id = account_id or f"acct_{uuid.uuid4().hex[:16]}"
        now = utc_now()
        with self._transaction() as connection:
            try:
                connection.execute(
                    """
                    INSERT INTO publish_accounts
                      (account_id, schema_version, platform, display_name, profile_ref,
                       verification_state, enabled, created_at, last_verified_at)
                    VALUES (?, 1, ?, ?, ?, 'unverified', 1, ?, NULL)
                    """,
                    (account_id, platform_value, display_name.strip(), profile_ref, now),
                )
                connection.execute(
                    """
                    INSERT INTO publish_account_state
                      (account_id, platform, login_state, profile_exists, updated_at)
                    VALUES (?, ?, 'not_connected', 0, ?)
                    """,
                    (account_id, platform_value, now),
                )
                if make_default:
                    self._set_default_locked(connection, account_id)
            except sqlite3.IntegrityError as exc:
                raise PublishAccountConflict("账号或 profile_ref 已存在") from exc
        return self.get_account(account_id)

    def list_accounts(self, *, include_archived: bool = False) -> list[PublishAccount]:
        where = "" if include_archived else "WHERE COALESCE(s.archived_at, '') = ''"
        with self._connect() as connection:
            rows = connection.execute(
                f"""
                SELECT a.*, s.login_state, s.is_default, s.profile_exists,
                       s.login_subject_hint, s.last_error_code, s.archived_at,
                       s.updated_at
                FROM publish_accounts a
                LEFT JOIN publish_account_state s ON s.account_id = a.account_id
                {where}
                ORDER BY a.platform, a.created_at, a.account_id
                """
            ).fetchall()
        return [self._row_to_model(row) for row in rows]

    def get_account(self, account_id: str, *, include_archived: bool = True) -> PublishAccount:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT a.*, s.login_state, s.is_default, s.profile_exists,
                       s.login_subject_hint, s.last_error_code, s.archived_at,
                       s.updated_at
                FROM publish_accounts a
                LEFT JOIN publish_account_state s ON s.account_id = a.account_id
                WHERE a.account_id = ?
                """,
                (account_id,),
            ).fetchone()
        if row is None or (not include_archived and row["archived_at"]):
            raise PublishAccountNotFound(account_id)
        return self._row_to_model(row)

    def find_by_profile_ref(self, profile_ref: str) -> PublishAccount | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT a.*, s.login_state, s.is_default, s.profile_exists,
                       s.login_subject_hint, s.last_error_code, s.archived_at,
                       s.updated_at
                FROM publish_accounts a
                LEFT JOIN publish_account_state s ON s.account_id = a.account_id
                WHERE a.profile_ref = ?
                """,
                (profile_ref,),
            ).fetchone()
        return self._row_to_model(row) if row else None

    def set_default(self, account_id: str) -> PublishAccount:
        with self._transaction() as connection:
            self._set_default_locked(connection, account_id)
        return self.get_account(account_id)

    def _set_default_locked(self, connection: sqlite3.Connection, account_id: str) -> None:
        row = connection.execute(
            """
            SELECT a.platform, a.enabled, s.archived_at
            FROM publish_accounts a
            LEFT JOIN publish_account_state s ON s.account_id = a.account_id
            WHERE a.account_id = ?
            """,
            (account_id,),
        ).fetchone()
        if row is None:
            raise PublishAccountNotFound(account_id)
        if not row["enabled"] or row["archived_at"]:
            raise PublishAccountConflict("归档或停用账号不能设为默认账号")
        now = utc_now()
        connection.execute(
            "UPDATE publish_account_state SET is_default = 0, updated_at = ? WHERE platform = ?",
            (now, row["platform"]),
        )
        connection.execute(
            "UPDATE publish_account_state SET is_default = 1, updated_at = ? WHERE account_id = ?",
            (now, account_id),
        )

    def archive(self, account_id: str) -> PublishAccount:
        now = utc_now()
        with self._transaction() as connection:
            row = connection.execute(
                "SELECT account_id FROM publish_accounts WHERE account_id = ?", (account_id,)
            ).fetchone()
            if row is None:
                raise PublishAccountNotFound(account_id)
            connection.execute(
                "UPDATE publish_accounts SET enabled = 0, verification_state = 'revoked' WHERE account_id = ?",
                (account_id,),
            )
            connection.execute(
                """
                UPDATE publish_account_state
                SET is_default = 0, login_state = 'revoked', archived_at = ?, updated_at = ?
                WHERE account_id = ?
                """,
                (now, now, account_id),
            )
        return self.get_account(account_id)

    def mark_profile_cleared(self, account_id: str) -> PublishAccount:
        now = utc_now()
        with self._transaction() as connection:
            if connection.execute(
                "SELECT 1 FROM publish_accounts WHERE account_id = ?", (account_id,)
            ).fetchone() is None:
                raise PublishAccountNotFound(account_id)
            connection.execute(
                """
                UPDATE publish_accounts
                SET verification_state = 'unverified', last_verified_at = NULL
                WHERE account_id = ?
                """,
                (account_id,),
            )
            connection.execute(
                """
                UPDATE publish_account_state
                SET login_state = 'not_connected', profile_exists = 1,
                    login_subject_hint = NULL, identity_fingerprint = NULL,
                    last_error_code = NULL, updated_at = ?
                WHERE account_id = ?
                """,
                (now, account_id),
            )
        return self.get_account(account_id)

    def get_identity_fingerprint(self, account_id: str) -> str | None:
        """Return the internal identity fingerprint without exposing it in a model/API."""
        with self._connect() as connection:
            row = connection.execute(
                "SELECT identity_fingerprint FROM publish_account_state WHERE account_id = ?",
                (account_id,),
            ).fetchone()
        if row is None:
            raise PublishAccountNotFound(account_id)
        return row["identity_fingerprint"]

    def record_probe(
        self,
        account_id: str,
        *,
        login_state: AccountLoginState,
        verification_state: AccountVerificationState,
        profile_exists: bool,
        login_subject_hint: str | None = None,
        identity_fingerprint: str | None = None,
        error_code: str | None = None,
    ) -> PublishAccount:
        now = utc_now()
        last_verified_at = now if verification_state == AccountVerificationState.VERIFIED else None
        with self._transaction() as connection:
            current = connection.execute(
                "SELECT s.login_state FROM publish_account_state s WHERE s.account_id = ?",
                (account_id,),
            ).fetchone()
            if current is None:
                raise PublishAccountNotFound(account_id)
            current_state = AccountLoginState(current["login_state"])
            if (
                current_state != login_state
                and login_state not in ACCOUNT_LOGIN_TRANSITIONS[current_state]
            ):
                raise PublishAccountConflict(
                    f"不允许账号状态从 {current_state.value} 直接变更为 {login_state.value}"
                )
            connection.execute(
                """
                UPDATE publish_accounts
                SET verification_state = ?, last_verified_at = COALESCE(?, last_verified_at)
                WHERE account_id = ?
                """,
                (verification_state.value, last_verified_at, account_id),
            )
            connection.execute(
                """
                UPDATE publish_account_state
                SET login_state = ?, profile_exists = ?, login_subject_hint = ?,
                    identity_fingerprint = ?, last_error_code = ?, updated_at = ?
                WHERE account_id = ?
                """,
                (
                    login_state.value,
                    int(profile_exists),
                    login_subject_hint,
                    identity_fingerprint,
                    error_code,
                    now,
                    account_id,
                ),
            )
        return self.get_account(account_id)

    def register_context(self, account_id: str, *, window_ref: str | None = None) -> dict[str, Any]:
        context_id = f"ctx_{uuid.uuid4().hex[:16]}"
        now = utc_now()
        with self._transaction() as connection:
            if connection.execute(
                "SELECT 1 FROM publish_accounts WHERE account_id = ?", (account_id,)
            ).fetchone() is None:
                raise PublishAccountNotFound(account_id)
            connection.execute(
                """
                INSERT INTO publish_context_registry
                  (context_id, account_id, window_ref, status, created_at, updated_at)
                VALUES (?, ?, ?, 'open', ?, ?)
                """,
                (context_id, account_id, window_ref, now, now),
            )
        return {"context_id": context_id, "account_id": account_id, "status": "open"}

    def register_profile_lock(self, account_id: str, owner_ref: str, pid: int) -> None:
        """Mirror the atomic file lock in SQLite for diagnostics/recovery only."""
        now = utc_now()
        with self._transaction() as connection:
            if connection.execute(
                "SELECT 1 FROM publish_accounts WHERE account_id = ?", (account_id,)
            ).fetchone() is None:
                raise PublishAccountNotFound(account_id)
            connection.execute(
                """
                INSERT INTO publish_profile_locks
                  (account_id, owner_ref, pid, acquired_at, heartbeat_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(account_id) DO UPDATE SET
                  owner_ref = excluded.owner_ref,
                  pid = excluded.pid,
                  acquired_at = excluded.acquired_at,
                  heartbeat_at = excluded.heartbeat_at
                """,
                (account_id, owner_ref, pid, now, now),
            )

    def clear_profile_lock(self, account_id: str, owner_ref: str) -> None:
        with self._transaction() as connection:
            connection.execute(
                "DELETE FROM publish_profile_locks WHERE account_id = ? AND owner_ref = ?",
                (account_id, owner_ref),
            )

    def list_profile_locks(self, account_id: str) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT account_id, owner_ref, pid, acquired_at, heartbeat_at
                FROM publish_profile_locks
                WHERE account_id = ?
                ORDER BY acquired_at DESC
                """,
                (account_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def close_context(self, context_id: str, *, stale: bool = False) -> None:
        with self._transaction() as connection:
            connection.execute(
                "UPDATE publish_context_registry SET status = ?, updated_at = ? WHERE context_id = ?",
                ("stale" if stale else "closed", utc_now(), context_id),
            )

    def mark_open_contexts_stale(self) -> int:
        """Recover context rows left open by an app/sidecar crash."""
        with self._transaction() as connection:
            cursor = connection.execute(
                "UPDATE publish_context_registry SET status = 'stale', updated_at = ? WHERE status = 'open'",
                (utc_now(),),
            )
            return cursor.rowcount

    def list_contexts(self, account_id: str) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT context_id, account_id, window_ref, status, created_at, updated_at
                FROM publish_context_registry
                WHERE account_id = ? AND status = 'open'
                ORDER BY created_at DESC
                """,
                (account_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def _row_to_model(self, row: sqlite3.Row) -> PublishAccount:
        platform = str(row["platform"])
        return PublishAccount(
            account_id=row["account_id"],
            platform=platform,
            display_name=row["display_name"],
            profile_ref=row["profile_ref"],
            verification_state=row["verification_state"],
            login_state=row["login_state"] or AccountLoginState.NOT_CONNECTED.value,
            enabled=bool(row["enabled"]),
            is_default=bool(row["is_default"]),
            profile_exists=bool(row["profile_exists"]),
            platform_release_state="pilot" if platform == PublishPlatform.DOUYIN.value else "unverified",
            created_at=row["created_at"],
            updated_at=row["updated_at"] or row["created_at"],
            last_verified_at=row["last_verified_at"],
            last_error_code=row["last_error_code"],
            login_subject_hint=row["login_subject_hint"],
            archived_at=row["archived_at"],
        )
