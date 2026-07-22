"""SQLite-backed enterprise asset kernel used by the V2 asset API.

Media revisions, upload sessions, domain projections, usage ledgers and
render snapshots share one transactional store. The legacy manifest readers
remain compatibility adapters during the Gate-C observation window; they are
still the explicit rollback path.
"""

from __future__ import annotations

import hashlib
import json
import mimetypes
import os
import re
import sqlite3
import subprocess
import threading
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from PIL import Image

from api.schemas.asset_library_ux0 import TemplateLayoutContract
from pixelle_video.services.asset_library_baseline import MANIFEST_SPECS
from pixelle_video.services.font_registry import resolve_registered_font
from pixelle_video.utils.os_util import get_data_path

SCHEMA_VERSION = 5
UPLOAD_CHUNK_SIZE = 1024 * 1024
MEDIA_KINDS = {"image", "video", "audio", "font"}
UPLOADABLE_MEDIA_KINDS = {"image", "video", "audio"}
UPLOAD_EXTENSIONS = {
    "image": {"jpg", "jpeg", "png", "webp", "gif", "bmp", "tif", "tiff"},
    "video": {"mp4", "mov", "webm", "m4v", "mkv", "avi"},
    "audio": {"mp3", "wav", "flac", "m4a", "aac", "ogg"},
}
LEGACY_SPECS = {
    "image": next(spec for spec in MANIFEST_SPECS if spec["resource_kind"] == "image"),
    "video": next(spec for spec in MANIFEST_SPECS if spec["resource_kind"] == "video"),
    "voice": next(spec for spec in MANIFEST_SPECS if spec["resource_kind"] == "voice"),
    "digital_human": next(spec for spec in MANIFEST_SPECS if spec["resource_kind"] == "digital_human"),
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(UPLOAD_CHUNK_SIZE), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_filename(filename: str) -> str:
    clean = Path(filename or "").name
    if not clean or clean in {".", ".."} or clean != filename:
        raise ValueError("Invalid upload filename")
    return clean


def _safe_relative_path(root: Path, relative_path: str) -> Path:
    relative = Path(relative_path)
    if relative.is_absolute():
        raise ValueError("Absolute media paths are not allowed")
    candidate = (root / relative).resolve()
    try:
        candidate.relative_to(root.resolve())
    except ValueError as exc:
        raise ValueError("Media path escapes data root") from exc
    return candidate


def _extension(filename: str) -> str:
    return Path(filename).suffix.lower().lstrip(".")


def _mime_type(filename: str) -> str:
    return mimetypes.guess_type(filename)[0] or "application/octet-stream"


def _validate_media_filename(kind: str, filename: str) -> None:
    extension = _extension(filename)
    if extension not in UPLOAD_EXTENSIONS.get(kind, set()):
        raise ValueError(f"Unsupported {kind} upload extension: {extension or 'none'}")


def _safe_asset_key(value: str) -> str:
    """Keep legacy IDs usable in generated variant directories."""
    clean = re.sub(r"[^A-Za-z0-9._-]", "_", value).strip("._-") or "asset"
    if clean != value:
        clean = f"{clean[:48]}-{hashlib.sha256(value.encode('utf-8')).hexdigest()[:8]}"
    return clean


def _image_metadata(path: Path) -> dict[str, Any]:
    with Image.open(path) as image:
        width, height = image.size
        has_transparency = image.convert("RGBA").getchannel("A").getextrema()[0] < 255
        return {
            "width": width,
            "height": height,
            "aspect_ratio": width / height if height else None,
            "has_transparency": has_transparency,
            "has_audio": False,
        }


def _video_metadata(path: Path) -> dict[str, Any]:
    command = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration:stream=codec_type,width,height,r_frame_rate",
        "-of",
        "json",
        str(path),
    ]
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise ValueError("Unable to inspect video metadata")
    payload = json.loads(result.stdout or "{}")
    streams = payload.get("streams") or []
    video_stream = next((stream for stream in streams if stream.get("codec_type") == "video"), {})
    has_audio = any(stream.get("codec_type") == "audio" for stream in streams)
    width = video_stream.get("width")
    height = video_stream.get("height")
    duration = (payload.get("format") or {}).get("duration")
    frame_rate = video_stream.get("r_frame_rate")
    fps = None
    if isinstance(frame_rate, str) and "/" in frame_rate:
        numerator, denominator = frame_rate.split("/", 1)
        if float(denominator):
            fps = float(numerator) / float(denominator)
    return {
        "width": int(width) if width else None,
        "height": int(height) if height else None,
        "aspect_ratio": (float(width) / float(height)) if width and height else None,
        "duration_ms": int(float(duration) * 1000) if duration else None,
        "frame_rate": fps,
        "has_audio": has_audio,
    }


def _audio_metadata(path: Path) -> dict[str, Any]:
    command = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration:stream=codec_type,sample_rate,channels",
        "-of",
        "json",
        str(path),
    ]
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise ValueError("Unable to inspect audio metadata")
    payload = json.loads(result.stdout or "{}")
    streams = payload.get("streams") or []
    audio_stream = next((stream for stream in streams if stream.get("codec_type") == "audio"), {})
    duration = (payload.get("format") or {}).get("duration")
    return {
        "duration_ms": int(float(duration) * 1000) if duration else None,
        "sample_rate": int(audio_stream["sample_rate"]) if audio_stream.get("sample_rate") else None,
        "channels": int(audio_stream["channels"]) if audio_stream.get("channels") else None,
        "has_audio": True,
    }


def _create_image_thumbnail(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(source) as image:
        image = image.convert("RGBA")
        image.thumbnail((640, 640), Image.Resampling.LANCZOS)
        background = Image.new("RGB", image.size, "white")
        background.paste(image, mask=image.getchannel("A"))
        background.save(destination, format="JPEG", quality=86, optimize=True)


def _create_video_poster(source: Path, destination: Path) -> bool:
    destination.parent.mkdir(parents=True, exist_ok=True)
    command = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-i",
        str(source),
        "-frames:v",
        "1",
        "-vf",
        "scale=640:-2",
        str(destination),
    ]
    result = subprocess.run(command, capture_output=True, check=False)
    return result.returncode == 0 and destination.is_file()


class AssetLibraryRepository:
    """SQLite-backed asset kernel shared by media and domain asset adapters."""

    def __init__(
        self,
        data_root: str | Path | None = None,
        max_upload_size: int = 100 * 1024 * 1024,
    ) -> None:
        self.data_root = Path(data_root or get_data_path()).resolve()
        self.db_path = self.data_root / "asset_library" / "asset_library.sqlite3"
        self.incoming_root = self.data_root / "asset_library" / "incoming"
        self.media_root = self.data_root / "asset_library" / "media"
        self.max_upload_size = max_upload_size
        self._lock = threading.RLock()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.incoming_root.mkdir(parents=True, exist_ok=True)
        self.media_root.mkdir(parents=True, exist_ok=True)
        self.initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            connection.execute("PRAGMA journal_mode = WAL")
        except sqlite3.OperationalError as exc:
            # A nearly-full removable/workspace volume may reject creation of
            # the WAL sidecar even though the database itself is readable.
            # Preserve correctness with SQLite's smaller rollback journal and
            # let the caller surface a real write failure if the volume is
            # genuinely out of space.
            if "disk I/O" not in str(exc).lower() and "full" not in str(exc).lower():
                connection.close()
                raise
            connection.execute("PRAGMA journal_mode = DELETE")
        return connection

    def initialize(self) -> None:
        with self._lock, self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS schema_meta (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS media_assets (
                    asset_id TEXT PRIMARY KEY,
                    legacy_id TEXT,
                    media_kind TEXT NOT NULL CHECK(media_kind IN ('image', 'video', 'audio', 'font')),
                    name TEXT NOT NULL,
                    description TEXT NOT NULL DEFAULT '',
                    source TEXT NOT NULL,
                    current_revision_id TEXT,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    archived_at TEXT
                );
                CREATE UNIQUE INDEX IF NOT EXISTS idx_media_legacy
                    ON media_assets(media_kind, legacy_id)
                    WHERE legacy_id IS NOT NULL;
                CREATE INDEX IF NOT EXISTS idx_media_kind_status
                    ON media_assets(media_kind, status, updated_at DESC);
                CREATE TABLE IF NOT EXISTS asset_revisions (
                    revision_id TEXT PRIMARY KEY,
                    asset_id TEXT NOT NULL REFERENCES media_assets(asset_id),
                    version INTEGER NOT NULL,
                    parent_revision_id TEXT,
                    relative_path TEXT NOT NULL UNIQUE,
                    mime_type TEXT NOT NULL,
                    bytes INTEGER NOT NULL,
                    sha256 TEXT NOT NULL,
                    width INTEGER,
                    height INTEGER,
                    aspect_ratio REAL,
                    duration_ms INTEGER,
                    frame_rate REAL,
                    has_audio INTEGER,
                    has_transparency INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    UNIQUE(asset_id, version)
                );
                CREATE INDEX IF NOT EXISTS idx_revision_sha256 ON asset_revisions(sha256);
                CREATE TABLE IF NOT EXISTS asset_variants (
                    variant_id TEXT PRIMARY KEY,
                    revision_id TEXT NOT NULL REFERENCES asset_revisions(revision_id),
                    role TEXT NOT NULL,
                    relative_path TEXT NOT NULL UNIQUE,
                    mime_type TEXT NOT NULL,
                    width INTEGER,
                    height INTEGER,
                    duration_ms INTEGER,
                    UNIQUE(revision_id, role)
                );
                CREATE TABLE IF NOT EXISTS upload_sessions (
                    upload_id TEXT PRIMARY KEY,
                    filename TEXT NOT NULL,
                    declared_bytes INTEGER NOT NULL,
                    received_bytes INTEGER NOT NULL DEFAULT 0,
                    target_kind TEXT NOT NULL CHECK(target_kind IN ('image', 'video', 'audio')),
                    name TEXT,
                    description TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL,
                    temp_relative_path TEXT NOT NULL UNIQUE,
                    asset_id TEXT,
                    duplicate_asset_id TEXT,
                    error_code TEXT,
                    error_message TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS voice_profiles (
                    voice_id TEXT PRIMARY KEY,
                    legacy_id TEXT UNIQUE,
                    audio_asset_id TEXT NOT NULL REFERENCES media_assets(asset_id),
                    audio_revision_id TEXT REFERENCES asset_revisions(revision_id),
                    name TEXT NOT NULL,
                    description TEXT NOT NULL DEFAULT '',
                    language TEXT NOT NULL DEFAULT '',
                    style TEXT NOT NULL DEFAULT '',
                    authorization_status TEXT NOT NULL DEFAULT 'unknown',
                    status TEXT NOT NULL DEFAULT 'ready',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_voice_profiles_status
                    ON voice_profiles(status, updated_at DESC);
                CREATE TABLE IF NOT EXISTS media_jobs (
                    job_id TEXT PRIMARY KEY,
                    asset_id TEXT,
                    kind TEXT NOT NULL,
                    status TEXT NOT NULL,
                    error_code TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS migration_runs (
                    run_id TEXT PRIMARY KEY,
                    schema_version INTEGER NOT NULL,
                    report_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS resource_usage (
                    usage_id TEXT PRIMARY KEY,
                    resource_kind TEXT NOT NULL,
                    resource_id TEXT NOT NULL,
                    revision_id TEXT REFERENCES asset_revisions(revision_id),
                    session_id TEXT NOT NULL,
                    step TEXT NOT NULL,
                    purpose TEXT NOT NULL,
                    slot_id TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(session_id, step, purpose, slot_id, resource_kind, resource_id)
                );
                CREATE INDEX IF NOT EXISTS idx_resource_usage_session
                    ON resource_usage(session_id, step, updated_at DESC);
                CREATE TABLE IF NOT EXISTS resource_snapshots (
                    snapshot_id TEXT PRIMARY KEY,
                    resource_kind TEXT NOT NULL,
                    resource_id TEXT NOT NULL,
                    revision_id TEXT REFERENCES asset_revisions(revision_id),
                    variant_id TEXT REFERENCES asset_variants(variant_id),
                    sha256 TEXT,
                    resolved_relative_path TEXT,
                    template_revision INTEGER,
                    renderer_version TEXT,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    session_id TEXT NOT NULL,
                    step TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_resource_snapshot_session
                    ON resource_snapshots(session_id, step, created_at DESC);
                CREATE TABLE IF NOT EXISTS digital_human_profiles (
                    profile_id TEXT PRIMARY KEY,
                    legacy_id TEXT UNIQUE,
                    name TEXT NOT NULL,
                    provider TEXT NOT NULL DEFAULT 'custom',
                    poster_asset_id TEXT,
                    gender TEXT,
                    style TEXT,
                    posture TEXT,
                    supported_workflows_json TEXT NOT NULL DEFAULT '[]',
                    default_scene_id TEXT,
                    quality_state TEXT NOT NULL DEFAULT 'unchecked',
                    status TEXT NOT NULL DEFAULT 'ready',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS digital_human_scenes (
                    scene_id TEXT PRIMARY KEY,
                    profile_id TEXT NOT NULL REFERENCES digital_human_profiles(profile_id),
                    name TEXT NOT NULL,
                    source_asset_id TEXT,
                    source_revision_id TEXT,
                    preview_variant_id TEXT,
                    shot_size TEXT,
                    location TEXT,
                    outfit TEXT,
                    posture TEXT,
                    sort_order INTEGER NOT NULL DEFAULT 0,
                    status TEXT NOT NULL DEFAULT 'ready',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_digital_human_scene_profile
                    ON digital_human_scenes(profile_id, updated_at DESC);
                CREATE TABLE IF NOT EXISTS brand_kits_v2 (
                    brand_id TEXT PRIMARY KEY,
                    legacy_id TEXT UNIQUE,
                    brand_name TEXT NOT NULL,
                    logo_asset_id TEXT,
                    default_bgm_asset_id TEXT,
                    primary_color TEXT NOT NULL,
                    secondary_color TEXT NOT NULL,
                    font_family TEXT NOT NULL DEFAULT '',
                    default_subtitle_style TEXT NOT NULL DEFAULT '',
                    ending_card_text TEXT NOT NULL DEFAULT '',
                    store_address TEXT NOT NULL DEFAULT '',
                    phone TEXT NOT NULL DEFAULT '',
                    coupon_phrase TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'ready',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS template_definitions (
                    template_id TEXT NOT NULL,
                    revision INTEGER NOT NULL,
                    display_name TEXT NOT NULL,
                    short_description TEXT NOT NULL,
                    full_description TEXT NOT NULL,
                    preview_url TEXT,
                    schema_version INTEGER NOT NULL DEFAULT 1,
                    renderer_version TEXT NOT NULL,
                    cover_contract_json TEXT NOT NULL DEFAULT '{}',
                    subtitle_contract_json TEXT NOT NULL DEFAULT '{}',
                    layout_contract_json TEXT NOT NULL DEFAULT '{}',
                    status TEXT NOT NULL DEFAULT 'ready',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY(template_id, revision)
                );
                CREATE INDEX IF NOT EXISTS idx_template_status
                    ON template_definitions(status, updated_at DESC);
                CREATE TABLE IF NOT EXISTS domain_revisions (
                    resource_kind TEXT NOT NULL,
                    resource_id TEXT NOT NULL,
                    revision INTEGER NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY(resource_kind, resource_id, revision)
                );
                CREATE INDEX IF NOT EXISTS idx_domain_revisions_resource
                    ON domain_revisions(resource_kind, resource_id, revision DESC);
                CREATE TABLE IF NOT EXISTS resource_tags (
                    resource_kind TEXT NOT NULL,
                    resource_id TEXT NOT NULL,
                    tag TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY(resource_kind, resource_id, tag)
                );
                CREATE INDEX IF NOT EXISTS idx_resource_tags_tag ON resource_tags(tag, resource_kind);
                CREATE TABLE IF NOT EXISTS resource_favorites (
                    resource_kind TEXT NOT NULL,
                    resource_id TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY(resource_kind, resource_id)
                );
                CREATE TABLE IF NOT EXISTS resource_collections (
                    collection_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    description TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'ready',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS collection_items (
                    collection_id TEXT NOT NULL REFERENCES resource_collections(collection_id) ON DELETE CASCADE,
                    resource_kind TEXT NOT NULL,
                    resource_id TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY(collection_id, resource_kind, resource_id)
                );
                """
            )
            self._migrate_media_check_constraints_locked(connection)
            self._migrate_ux1_schema_locked(connection)
            self._migrate_resource_ledger_foreign_keys_locked(connection)
            connection.execute(
                "INSERT OR IGNORE INTO schema_meta(key, value) VALUES('schema_version', ?)",
                (str(SCHEMA_VERSION),),
            )
            connection.execute(
                "UPDATE schema_meta SET value = ? WHERE key = 'schema_version'",
                (str(SCHEMA_VERSION),),
            )
            connection.execute(
                "INSERT OR IGNORE INTO schema_meta(key, value) VALUES('library_index_generation', '0')"
            )
            # Keep cursor invalidation tied to the data mutation itself.  A
            # wall-clock timestamp is not sufficient when two edits happen
            # within the same clock tick, and explicit calls at every API
            # adapter boundary are easy to miss as the domain model grows.
            for table in (
                "media_assets",
                "voice_profiles",
                "digital_human_profiles",
                "digital_human_scenes",
                "brand_kits_v2",
                "template_definitions",
                "resource_usage",
                "resource_tags",
                "resource_favorites",
                "resource_collections",
                "collection_items",
            ):
                trigger_prefix = f"asset_library_generation_{table}"
                connection.executescript(
                    f"""
                    CREATE TRIGGER IF NOT EXISTS {trigger_prefix}_insert
                    AFTER INSERT ON {table}
                    BEGIN
                      UPDATE schema_meta SET value = CAST(CAST(value AS INTEGER) + 1 AS TEXT)
                      WHERE key = 'library_index_generation';
                    END;
                    CREATE TRIGGER IF NOT EXISTS {trigger_prefix}_update
                    AFTER UPDATE ON {table}
                    BEGIN
                      UPDATE schema_meta SET value = CAST(CAST(value AS INTEGER) + 1 AS TEXT)
                      WHERE key = 'library_index_generation';
                    END;
                    CREATE TRIGGER IF NOT EXISTS {trigger_prefix}_delete
                    AFTER DELETE ON {table}
                    BEGIN
                      UPDATE schema_meta SET value = CAST(CAST(value AS INTEGER) + 1 AS TEXT)
                      WHERE key = 'library_index_generation';
                    END;
                    """
                )
            self._recover_stale_uploads(connection)
            self._expire_deferred_uploads(connection)
            migrated = connection.execute(
                "SELECT 1 FROM schema_meta WHERE key = 'legacy_media_migration_v1'"
            ).fetchone()
            media_delta_migrated = connection.execute(
                "SELECT 1 FROM schema_meta WHERE key = 'legacy_media_migration_v2'"
            ).fetchone()
            performed_legacy_media_migration = False
            if migrated is None:
                # Fresh databases complete the original import and the
                # incremental marker in one pass.  Existing Stage-1/Stage-2
                # databases have only the v1 marker; they receive the same
                # idempotent pass below so audio/FLAC references added after
                # the first release are not silently omitted.
                self._migrate_legacy_locked(connection)
                performed_legacy_media_migration = True
                connection.execute(
                    "INSERT INTO schema_meta(key, value) VALUES('legacy_media_migration_v1', ?)",
                    (_now(),),
                )
                # Record both markers for a genuinely fresh database.  If
                # only v1 were written here, the next process start would
                # repeat the full import before realizing it is already
                # complete.  Existing v1-only databases still take the
                # incremental branch below.
                connection.execute(
                    "INSERT INTO schema_meta(key, value) VALUES('legacy_media_migration_v2', ?)",
                    (_now(),),
                )
                media_delta_migrated = True
            if media_delta_migrated is None:
                self._migrate_legacy_locked(connection)
                performed_legacy_media_migration = True
                connection.execute(
                    "INSERT INTO schema_meta(key, value) VALUES('legacy_media_migration_v2', ?)",
                    (_now(),),
                )
            self._sync_legacy_media_manifests_locked(
                connection,
                skip_import=performed_legacy_media_migration,
            )
            self._backfill_voice_profiles_locked(connection)
            domain_migrated = connection.execute(
                "SELECT 1 FROM schema_meta WHERE key = 'legacy_domain_migration_v1'"
            ).fetchone()
            performed_legacy_domain_migration = False
            if domain_migrated is None:
                self._migrate_domain_locked(connection)
                performed_legacy_domain_migration = True
                connection.execute(
                    "INSERT INTO schema_meta(key, value) VALUES('legacy_domain_migration_v1', ?)",
                    (_now(),),
                )
            self._sync_legacy_domain_manifests_locked(
                connection,
                skip_import=performed_legacy_domain_migration,
            )

    def _migrate_media_check_constraints_locked(self, connection: sqlite3.Connection) -> None:
        """Rebuild Stage-1 tables whose CHECK constraints predate audio assets.

        SQLite cannot alter a CHECK constraint in place.  The rebuild is
        idempotent, keeps all rows and indexes, and only runs when an older
        database still has the image/video-only definition.
        """
        media_sql = connection.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='media_assets'"
        ).fetchone()
        if media_sql and "'audio'" not in str(media_sql["sql"]):
            connection.commit()
            connection.execute("PRAGMA foreign_keys = OFF")
            connection.execute("DROP INDEX IF EXISTS idx_media_legacy")
            connection.execute("DROP INDEX IF EXISTS idx_media_kind_status")
            connection.execute(
                """CREATE TABLE media_assets_v3 (
                    asset_id TEXT PRIMARY KEY,
                    legacy_id TEXT,
                    media_kind TEXT NOT NULL CHECK(media_kind IN ('image', 'video', 'audio', 'font')),
                    name TEXT NOT NULL,
                    description TEXT NOT NULL DEFAULT '',
                    source TEXT NOT NULL,
                    current_revision_id TEXT,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    archived_at TEXT
                )"""
            )
            connection.execute(
                "INSERT INTO media_assets_v3 SELECT asset_id, legacy_id, media_kind, name, description, source, current_revision_id, status, created_at, updated_at, archived_at FROM media_assets"
            )
            connection.execute("DROP TABLE media_assets")
            connection.execute("ALTER TABLE media_assets_v3 RENAME TO media_assets")
            connection.execute(
                "CREATE UNIQUE INDEX idx_media_legacy ON media_assets(media_kind, legacy_id) WHERE legacy_id IS NOT NULL"
            )
            connection.execute(
                "CREATE INDEX idx_media_kind_status ON media_assets(media_kind, status, updated_at DESC)"
            )
            connection.commit()
            connection.execute("PRAGMA foreign_keys = ON")

        upload_sql = connection.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='upload_sessions'"
        ).fetchone()
        if upload_sql and "'audio'" not in str(upload_sql["sql"]):
            connection.commit()
            connection.execute("PRAGMA foreign_keys = OFF")
            connection.execute("""CREATE TABLE upload_sessions_v3 (
                upload_id TEXT PRIMARY KEY,
                filename TEXT NOT NULL,
                declared_bytes INTEGER NOT NULL,
                received_bytes INTEGER NOT NULL DEFAULT 0,
                target_kind TEXT NOT NULL CHECK(target_kind IN ('image', 'video', 'audio')),
                name TEXT,
                description TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL,
                temp_relative_path TEXT NOT NULL UNIQUE,
                asset_id TEXT,
                duplicate_asset_id TEXT,
                error_code TEXT,
                error_message TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )""")
            connection.execute("INSERT INTO upload_sessions_v3 SELECT * FROM upload_sessions")
            connection.execute("DROP TABLE upload_sessions")
            connection.execute("ALTER TABLE upload_sessions_v3 RENAME TO upload_sessions")
            connection.commit()
            connection.execute("PRAGMA foreign_keys = ON")

    def _migrate_ux1_schema_locked(self, connection: sqlite3.Connection) -> None:
        """Add UX-1 upload/voice fields without rewriting user media."""
        revision_columns = {
            str(row["name"])
            for row in connection.execute("PRAGMA table_info(asset_revisions)").fetchall()
        }
        if "has_transparency" not in revision_columns:
            connection.execute("ALTER TABLE asset_revisions ADD COLUMN has_transparency INTEGER NOT NULL DEFAULT 0")
        columns = {
            str(row["name"])
            for row in connection.execute("PRAGMA table_info(upload_sessions)").fetchall()
        }
        additions = {
            "decision_mode": "TEXT NOT NULL DEFAULT 'auto'",
            "idempotency_key": "TEXT",
            "sha256": "TEXT",
            "expires_at": "TEXT",
            "duplicate_policy": "TEXT",
            "finalize_result_json": "TEXT",
        }
        for name, definition in additions.items():
            if name not in columns:
                connection.execute(f"ALTER TABLE upload_sessions ADD COLUMN {name} {definition}")
        connection.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_upload_idempotency "
            "ON upload_sessions(idempotency_key) WHERE idempotency_key IS NOT NULL"
        )
        connection.execute(
            "CREATE TABLE IF NOT EXISTS voice_profiles ("
            "voice_id TEXT PRIMARY KEY, legacy_id TEXT UNIQUE, "
            "audio_asset_id TEXT NOT NULL REFERENCES media_assets(asset_id), "
            "audio_revision_id TEXT REFERENCES asset_revisions(revision_id), "
            "name TEXT NOT NULL, description TEXT NOT NULL DEFAULT '', "
            "language TEXT NOT NULL DEFAULT '', style TEXT NOT NULL DEFAULT '', "
            "authorization_status TEXT NOT NULL DEFAULT 'unknown', "
            "status TEXT NOT NULL DEFAULT 'ready', created_at TEXT NOT NULL, updated_at TEXT NOT NULL)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_voice_profiles_status "
            "ON voice_profiles(status, updated_at DESC)"
        )
        scene_columns = {str(row["name"]) for row in connection.execute("PRAGMA table_info(digital_human_scenes)").fetchall()}
        for name, definition in {"sort_order": "INTEGER NOT NULL DEFAULT 0", "status": "TEXT NOT NULL DEFAULT 'ready'"}.items():
            if name not in scene_columns:
                connection.execute(f"ALTER TABLE digital_human_scenes ADD COLUMN {name} {definition}")
        collection_columns = {str(row["name"]) for row in connection.execute("PRAGMA table_info(resource_collections)").fetchall()}
        if "status" not in collection_columns:
            connection.execute("ALTER TABLE resource_collections ADD COLUMN status TEXT NOT NULL DEFAULT 'ready'")
        template_columns = {str(row["name"]) for row in connection.execute("PRAGMA table_info(template_definitions)").fetchall()}
        if "layout_contract_json" not in template_columns:
            connection.execute("ALTER TABLE template_definitions ADD COLUMN layout_contract_json TEXT NOT NULL DEFAULT '{}'")

    def _backfill_voice_profiles_locked(self, connection: sqlite3.Connection) -> None:
        """Give imported legacy voice references a first-class domain identity."""
        rows = connection.execute(
            "SELECT a.asset_id, a.legacy_id, a.name, a.description, a.current_revision_id, "
            "a.status, a.created_at, a.updated_at FROM media_assets a "
            "WHERE a.media_kind = 'audio' AND a.legacy_id IS NOT NULL "
            "AND a.legacy_id NOT LIKE 'digital_human:%'"
        ).fetchall()
        for row in rows:
            # Preserve the legacy reference ID as the stable public voice ID;
            # new profiles use the voice-* namespace generated below.
            voice_id = str(row["legacy_id"])
            connection.execute(
                "INSERT OR IGNORE INTO voice_profiles(voice_id, legacy_id, audio_asset_id, "
                "audio_revision_id, name, description, created_at, updated_at, status) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    voice_id,
                    row["legacy_id"],
                    row["asset_id"],
                    row["current_revision_id"],
                    row["name"],
                    row["description"] or "参考音色",
                    row["created_at"],
                    row["updated_at"],
                    row["status"],
                ),
            )

    def _expire_deferred_uploads(self, connection: sqlite3.Connection) -> None:
        now = _now()
        rows = connection.execute(
            "SELECT upload_id, temp_relative_path FROM upload_sessions "
            "WHERE decision_mode = 'deferred' AND status = 'awaiting_duplicate_decision' "
            "AND expires_at IS NOT NULL AND expires_at < ?",
            (now,),
        ).fetchall()
        for row in rows:
            _safe_relative_path(self.data_root, row["temp_relative_path"]).unlink(missing_ok=True)
            connection.execute(
                "UPDATE upload_sessions SET status = 'expired', error_code = 'ttl_expired', updated_at = ? WHERE upload_id = ?",
                (now, row["upload_id"]),
            )


    def _migrate_resource_ledger_foreign_keys_locked(self, connection: sqlite3.Connection) -> None:
        """Allow usage/snapshot rows to reference domain resources as Stage 2 expands.

        Stage 1 created these tables with a media-only foreign key.  Rebuild
        them once, preserving rows, so voice, digital-human, brand and
        template adapters can share the same ledger without weakening media
        revision foreign keys.
        """
        for table, columns, definition in (
            (
                "resource_usage",
                "usage_id, resource_kind, resource_id, revision_id, session_id, step, purpose, slot_id, created_at, updated_at",
                """CREATE TABLE resource_usage (
                    usage_id TEXT PRIMARY KEY,
                    resource_kind TEXT NOT NULL,
                    resource_id TEXT NOT NULL,
                    revision_id TEXT REFERENCES asset_revisions(revision_id),
                    session_id TEXT NOT NULL,
                    step TEXT NOT NULL,
                    purpose TEXT NOT NULL,
                    slot_id TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(session_id, step, purpose, slot_id, resource_kind, resource_id)
                )""",
            ),
            (
                "resource_snapshots",
                "snapshot_id, resource_kind, resource_id, revision_id, variant_id, sha256, resolved_relative_path, template_revision, renderer_version, metadata_json, session_id, step, created_at",
                """CREATE TABLE resource_snapshots (
                    snapshot_id TEXT PRIMARY KEY,
                    resource_kind TEXT NOT NULL,
                    resource_id TEXT NOT NULL,
                    revision_id TEXT REFERENCES asset_revisions(revision_id),
                    variant_id TEXT REFERENCES asset_variants(variant_id),
                    sha256 TEXT,
                    resolved_relative_path TEXT,
                    template_revision INTEGER,
                    renderer_version TEXT,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    session_id TEXT NOT NULL,
                    step TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )""",
            ),
        ):
            sql = connection.execute(
                "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = ?", (table,)
            ).fetchone()
            definition_sql = str(sql["sql"] if sql else "")
            needs_rebuild = "REFERENCES media_assets" in definition_sql or (
                table == "resource_usage"
                and "UNIQUE(session_id, step, purpose, slot_id, resource_id)" in definition_sql
                and "resource_kind, resource_id" not in definition_sql
            ) or (table == "resource_snapshots" and "metadata_json" not in definition_sql)
            if not sql or not needs_rebuild:
                continue
            legacy = f"{table}_stage1"
            connection.execute(f"DROP INDEX IF EXISTS idx_{table}_session")
            connection.execute(f"ALTER TABLE {table} RENAME TO {legacy}")
            connection.execute(definition)
            if table == "resource_snapshots" and "metadata_json" not in definition_sql:
                old_columns = columns.replace(", metadata_json", "")
                select_columns = old_columns.replace(", session_id", ", '{}' AS metadata_json, session_id")
                connection.execute(f"INSERT INTO {table}({columns}) SELECT {select_columns} FROM {legacy}")
            else:
                connection.execute(f"INSERT INTO {table}({columns}) SELECT {columns} FROM {legacy}")
            connection.execute(f"DROP TABLE {legacy}")
            index_columns = "step, updated_at DESC" if table == "resource_usage" else "step, created_at DESC"
            connection.execute(
                f"CREATE INDEX IF NOT EXISTS idx_{table}_session ON {table}(session_id, {index_columns})"
            )

    def _recover_stale_uploads(self, connection: sqlite3.Connection) -> None:
        rows = connection.execute(
            "SELECT upload_id, temp_relative_path FROM upload_sessions "
            "WHERE status IN ('created', 'uploading', 'analyzing')"
        ).fetchall()
        for row in rows:
            temporary = _safe_relative_path(self.data_root, row["temp_relative_path"])
            temporary.unlink(missing_ok=True)
            connection.execute(
                "UPDATE upload_sessions SET status = 'failed', error_code = ?, "
                "error_message = ?, updated_at = ? WHERE upload_id = ?",
                ("restart_recovery", "Upload interrupted by application restart", _now(), row["upload_id"]),
            )

    def _legacy_media_manifest_paths(self) -> dict[str, Path]:
        return {
            kind: self.data_root / LEGACY_SPECS[kind]["manifest"]
            for kind in ("image", "video", "voice")
        }

    def _legacy_media_manifest_fingerprints(self) -> dict[str, str]:
        fingerprints: dict[str, str] = {}
        for kind, path in self._legacy_media_manifest_paths().items():
            fingerprints[kind] = _sha256(path) if path.is_file() else "missing"
        return fingerprints

    def _legacy_media_manifest_ids(self, kind: str) -> set[str] | None:
        path = self._legacy_media_manifest_paths()[kind]
        if not path.is_file():
            return set()
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            return None
        if not isinstance(payload, list):
            return None
        id_field = LEGACY_SPECS[kind]["id_fields"][0]
        return {
            str(record.get(id_field)).strip()
            for record in payload
            if isinstance(record, dict) and str(record.get(id_field) or "").strip()
        }

    def _sync_legacy_media_manifests_locked(
        self,
        connection: sqlite3.Connection,
        *,
        skip_import: bool = False,
    ) -> None:
        """Keep the compatibility projection safe across V2 rollback cycles.

        The old UI can still write manifests while the kill switch is off. A
        later V2 process must therefore import newly-added legacy rows and
        archive imported rows removed by the legacy UI. Native V2 uploads are
        marked ``source='upload'`` and are intentionally left untouched.
        """

        fingerprints = self._legacy_media_manifest_fingerprints()
        stored = {
            kind: (
                connection.execute(
                    "SELECT value FROM schema_meta WHERE key = ?",
                    (f"legacy_media_manifest_sha:{kind}",),
                ).fetchone()
            )
            for kind in fingerprints
        }
        previous = {kind: (row["value"] if row else None) for kind, row in stored.items()}
        changed = any(previous[kind] != fingerprint for kind, fingerprint in fingerprints.items())
        if changed and not skip_import:
            self._migrate_legacy_locked(connection)

        media_kind_map = {"image": "image", "video": "video", "voice": "audio"}
        for kind, media_kind in media_kind_map.items():
            active_ids = self._legacy_media_manifest_ids(kind)
            if active_ids is None:
                # Never archive user data because a legacy manifest is
                # temporarily malformed; leave it for operator repair.
                continue
            # Portrait imports use the same media table but a namespaced
            # legacy_id; they are reconciled by the domain migration and must
            # not be archived when the ordinary image/video manifest changes.
            connection.execute(
                "UPDATE media_assets SET status = 'archived', archived_at = ?, updated_at = ? "
                "WHERE source = 'imported' AND media_kind = ? "
                "AND legacy_id IS NOT NULL AND legacy_id NOT LIKE 'digital_human:%' "
                "AND legacy_id NOT IN ({})".format(
                    ",".join("?" for _ in active_ids) or "''"
                ),
                (_now(), _now(), media_kind, *sorted(active_ids)),
            )

        for kind, fingerprint in fingerprints.items():
            connection.execute(
                "INSERT INTO schema_meta(key, value) VALUES(?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (f"legacy_media_manifest_sha:{kind}", fingerprint),
            )

    def _legacy_domain_manifest_paths(self) -> dict[str, Path]:
        return {
            "digital_human": self.data_root / LEGACY_SPECS["digital_human"]["manifest"],
            "brand": self.data_root / "brand_kits" / "brand_kits.json",
        }

    def _legacy_domain_manifest_fingerprints(self) -> dict[str, str]:
        fingerprints: dict[str, str] = {}
        for kind, path in self._legacy_domain_manifest_paths().items():
            fingerprints[kind] = _sha256(path) if path.is_file() else "missing"
        return fingerprints

    def _legacy_domain_manifest_ids(self, kind: str) -> set[str] | None:
        path = self._legacy_domain_manifest_paths()[kind]
        if not path.is_file():
            return set()
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            return None
        if not isinstance(payload, list):
            return None
        field = "portrait_id" if kind == "digital_human" else "brand_id"
        return {
            str(record.get(field)).strip()
            for record in payload
            if isinstance(record, dict) and str(record.get(field) or "").strip()
        }

    def _sync_legacy_domain_manifests_locked(
        self,
        connection: sqlite3.Connection,
        *,
        skip_import: bool = False,
    ) -> None:
        """Reconcile domain records created while the legacy UI was active."""

        fingerprints = self._legacy_domain_manifest_fingerprints()
        stored = {
            kind: connection.execute(
                "SELECT value FROM schema_meta WHERE key = ?",
                (f"legacy_domain_manifest_sha:{kind}",),
            ).fetchone()
            for kind in fingerprints
        }
        previous = {kind: (row["value"] if row else None) for kind, row in stored.items()}
        changed = any(previous[kind] != fingerprint for kind, fingerprint in fingerprints.items())
        if changed and not skip_import:
            self._migrate_domain_locked(connection)

        table_by_kind = {
            "digital_human": ("digital_human_profiles", "profile_id"),
            "brand": ("brand_kits_v2", "brand_id"),
        }
        for kind, (table, id_column) in table_by_kind.items():
            active_ids = self._legacy_domain_manifest_ids(kind)
            if active_ids is None:
                continue
            placeholders = ",".join("?" for _ in active_ids) or "''"
            connection.execute(
                f"UPDATE {table} SET status = 'archived', updated_at = ? "
                f"WHERE legacy_id IS NOT NULL AND {id_column} NOT IN ({placeholders})",
                (_now(), *sorted(active_ids)),
            )

        for kind, fingerprint in fingerprints.items():
            connection.execute(
                "INSERT INTO schema_meta(key, value) VALUES(?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (f"legacy_domain_manifest_sha:{kind}", fingerprint),
            )

    def _migrate_legacy_locked(self, connection: sqlite3.Connection) -> None:
        report: dict[str, Any] = {"schema_version": SCHEMA_VERSION, "kinds": {}}
        for kind in ("image", "video", "voice"):
            spec = LEGACY_SPECS[kind]
            media_kind = "audio" if kind == "voice" else kind
            manifest_path = self.data_root / spec["manifest"]
            kind_report = {"manifest": spec["manifest"], "media_kind": media_kind, "records": 0, "imported": 0, "missing": []}
            if not manifest_path.is_file():
                report["kinds"][kind] = kind_report
                continue
            try:
                payload = json.loads(manifest_path.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError, json.JSONDecodeError):
                kind_report["error"] = "invalid_manifest"
                report["kinds"][kind] = kind_report
                continue
            records = payload if isinstance(payload, list) else []
            kind_report["records"] = len(records)
            for record in records:
                if not isinstance(record, dict):
                    continue
                legacy_id = str(record.get(spec["id_fields"][0]) or "").strip()
                filename = str(record.get("filename") or "").strip()
                if not legacy_id or not filename:
                    continue
                existing = connection.execute(
                    "SELECT asset_id FROM media_assets WHERE media_kind = ? AND legacy_id = ?",
                    (media_kind, legacy_id),
                ).fetchone()
                if existing:
                    continue
                relative_path = {
                    "image": f"image_assets/{Path(filename).name}",
                    "video": f"video_assets/overlay/{Path(filename).name}",
                    "voice": f"voice_references/{Path(filename).name}",
                }[kind]
                source = _safe_relative_path(self.data_root, relative_path)
                if not source.is_file():
                    kind_report["missing"].append(relative_path)
                    continue
                legacy_key = _safe_asset_key(legacy_id)
                asset_id = f"media-{media_kind}-{legacy_key}"
                revision_id = f"revision-{media_kind}-{legacy_key}-1"
                metadata = self._inspect_media(source, media_kind, record)
                created_at = str(record.get("created_at") or _now())
                now = _now()
                connection.execute(
                    "INSERT INTO media_assets(asset_id, legacy_id, media_kind, name, description, "
                    "source, current_revision_id, status, created_at, updated_at) "
                    "VALUES (?, ?, ?, ?, '', 'imported', ?, ?, ?, ?)",
                    (
                        asset_id,
                        legacy_id,
                        media_kind,
                        str(record.get("name") or Path(filename).stem),
                        revision_id,
                        "ready" if metadata["valid"] else "warning",
                        created_at,
                        now,
                    ),
                )
                connection.execute(
                    "INSERT INTO asset_revisions(revision_id, asset_id, version, relative_path, "
                    "mime_type, bytes, sha256, width, height, aspect_ratio, duration_ms, frame_rate, "
                    "has_audio, has_transparency, created_at) VALUES (?, ?, 1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        revision_id,
                        asset_id,
                        relative_path,
                        _mime_type(filename),
                        source.stat().st_size,
                        _sha256(source),
                        metadata.get("width"),
                        metadata.get("height"),
                        metadata.get("aspect_ratio"),
                        metadata.get("duration_ms"),
                        metadata.get("frame_rate"),
                        int(metadata.get("has_audio", False)),
                        int(metadata.get("has_transparency", False)),
                        created_at,
                    ),
                )
                self._ensure_variant_locked(connection, asset_id, revision_id, source, media_kind, record)
                kind_report["imported"] += 1
            report["kinds"][kind] = kind_report
        connection.execute(
            "INSERT INTO migration_runs(run_id, schema_version, report_json, created_at) VALUES (?, ?, ?, ?)",
            (f"legacy-media-{uuid.uuid4().hex}", SCHEMA_VERSION, json.dumps(report), _now()),
        )

    def _migrate_domain_locked(self, connection: sqlite3.Connection) -> None:
        """Import digital-human, brand and template metadata without moving files."""
        report: dict[str, Any] = {"schema_version": SCHEMA_VERSION, "kinds": {}}
        portrait_manifest = self.data_root / LEGACY_SPECS["digital_human"]["manifest"]
        portrait_report = {"manifest": str(portrait_manifest.relative_to(self.data_root)), "records": 0, "imported": 0, "missing": []}
        if portrait_manifest.is_file():
            try:
                records = json.loads(portrait_manifest.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError, json.JSONDecodeError):
                records = []
                portrait_report["error"] = "invalid_manifest"
            records = records if isinstance(records, list) else []
            portrait_report["records"] = len(records)
            for record in records:
                if not isinstance(record, dict):
                    continue
                legacy_id = str(record.get("portrait_id") or "").strip()
                filename = str(record.get("filename") or "").strip()
                if not legacy_id or not filename:
                    continue
                media_kind = "video" if str(record.get("media_type") or "").lower() == "video" or Path(filename).suffix.lower() in {".mp4", ".mov", ".webm"} else "image"
                relative_path = f"portraits/{Path(filename).name}"
                source = _safe_relative_path(self.data_root, relative_path)
                if not source.is_file():
                    portrait_report["missing"].append(relative_path)
                    continue
                safe_key = _safe_asset_key(legacy_id)
                asset_id = f"media-digital-human-{safe_key}"
                revision_id = f"revision-digital-human-{safe_key}-1"
                if not connection.execute("SELECT 1 FROM media_assets WHERE asset_id = ?", (asset_id,)).fetchone():
                    metadata = self._inspect_media(source, media_kind, record)
                    created_at = str(record.get("created_at") or _now())
                    now = _now()
                    connection.execute(
                        "INSERT INTO media_assets(asset_id, legacy_id, media_kind, name, description, source, current_revision_id, status, created_at, updated_at) VALUES (?, ?, ?, ?, '', 'imported', ?, ?, ?, ?)",
                        (asset_id, f"digital_human:{legacy_id}", media_kind, str(record.get("name") or Path(filename).stem), revision_id, "ready" if metadata["valid"] else "warning", created_at, now),
                    )
                    connection.execute(
                        "INSERT INTO asset_revisions(revision_id, asset_id, version, relative_path, mime_type, bytes, sha256, width, height, aspect_ratio, duration_ms, frame_rate, has_audio, has_transparency, created_at) VALUES (?, ?, 1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (revision_id, asset_id, relative_path, _mime_type(filename), source.stat().st_size, _sha256(source), metadata.get("width"), metadata.get("height"), metadata.get("aspect_ratio"), metadata.get("duration_ms"), metadata.get("frame_rate"), int(metadata.get("has_audio", False)), int(metadata.get("has_transparency", False)), created_at),
                    )
                    self._ensure_variant_locked(connection, asset_id, revision_id, source, media_kind, record)
                # Keep the legacy portrait identifier stable for existing
                # workflow sessions and deep links.
                profile_id = legacy_id
                now = _now()
                connection.execute(
                    "INSERT OR IGNORE INTO digital_human_profiles(profile_id, legacy_id, name, provider, poster_asset_id, supported_workflows_json, default_scene_id, quality_state, status, created_at, updated_at) VALUES (?, ?, ?, 'custom', ?, ?, ?, 'unchecked', 'ready', ?, ?)",
                    (profile_id, legacy_id, str(record.get("name") or Path(filename).stem), asset_id, json.dumps([], ensure_ascii=False), f"scene-{safe_key}", str(record.get("created_at") or now), now),
                )
                connection.execute(
                    "INSERT OR IGNORE INTO digital_human_scenes(scene_id, profile_id, name, source_asset_id, source_revision_id, shot_size, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (f"scene-{safe_key}", profile_id, str(record.get("name") or "默认场景"), asset_id, revision_id, "medium", str(record.get("created_at") or now), now),
                )
                self._record_domain_revision_locked(connection, "digital_human", profile_id, self._domain_row_payload_locked(connection, "digital_human", profile_id))
                portrait_report["imported"] += 1
        report["kinds"]["digital_human"] = portrait_report

        brand_manifest = self.data_root / "brand_kits" / "brand_kits.json"
        brand_report = {"manifest": "brand_kits/brand_kits.json", "records": 0, "imported": 0, "missing": []}
        if brand_manifest.is_file():
            try:
                records = json.loads(brand_manifest.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError, json.JSONDecodeError):
                records = []
                brand_report["error"] = "invalid_manifest"
            records = records if isinstance(records, list) else []
            brand_report["records"] = len(records)
            for record in records:
                if not isinstance(record, dict):
                    continue
                legacy_id = str(record.get("brand_id") or "").strip()
                if not legacy_id:
                    continue
                now = _now()
                connection.execute(
                    "INSERT OR IGNORE INTO brand_kits_v2(brand_id, legacy_id, brand_name, primary_color, secondary_color, font_family, default_subtitle_style, ending_card_text, store_address, phone, coupon_phrase, status, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'ready', ?, ?)",
                    (legacy_id, legacy_id, str(record.get("brand_name") or "未命名品牌"), str(record.get("primary_color") or "#1f6feb"), str(record.get("secondary_color") or "#0f766e"), str(record.get("font_family") or ""), str(record.get("default_subtitle_style") or ""), str(record.get("ending_card_text") or ""), str(record.get("store_address") or ""), str(record.get("phone") or ""), str(record.get("coupon_phrase") or ""), str(record.get("created_at") or now), now),
                )
                self._record_domain_revision_locked(connection, "brand", legacy_id, self._domain_row_payload_locked(connection, "brand", legacy_id))
                brand_report["imported"] += 1
        report["kinds"]["brand"] = brand_report

        try:
            from pixelle_video.services.ip_broadcast_templates import (
                IP_BROADCAST_CANVAS_HEIGHT,
                IP_BROADCAST_CANVAS_WIDTH,
                get_template_subtitle_style,
                list_ip_broadcast_templates,
            )

            templates = list_ip_broadcast_templates()
        except (OSError, ValueError):
            templates = []
        template_report = {"records": len(templates), "imported": 0}
        for template in templates:
            style = get_template_subtitle_style(template)
            now = _now()
            connection.execute(
                "INSERT OR IGNORE INTO template_definitions(template_id, revision, display_name, short_description, full_description, preview_url, schema_version, renderer_version, cover_contract_json, subtitle_contract_json, status, created_at, updated_at) VALUES (?, 1, ?, ?, ?, ?, 1, ?, ?, ?, 'ready', ?, ?)",
                (template.template_id, template.display_name, template.short_description, template.full_description, f"/api/assets/templates/ip-broadcast/{template.template_id}/preview", "ip-broadcast-composer-v2", json.dumps({"canvas_width": IP_BROADCAST_CANVAS_WIDTH, "canvas_height": IP_BROADCAST_CANVAS_HEIGHT}, ensure_ascii=False), json.dumps(style.__dict__, ensure_ascii=False), now, now),
            )
            template_report["imported"] += 1
        report["kinds"]["template"] = template_report
        connection.execute(
            "INSERT INTO migration_runs(run_id, schema_version, report_json, created_at) VALUES (?, ?, ?, ?)",
            (f"legacy-domain-{uuid.uuid4().hex}", SCHEMA_VERSION, json.dumps(report, ensure_ascii=False), _now()),
        )

    def _inspect_media(self, source: Path, kind: str, record: dict[str, Any]) -> dict[str, Any]:
        try:
            metadata = (
                _image_metadata(source)
                if kind == "image"
                else _audio_metadata(source)
                if kind == "audio"
                else _video_metadata(source)
            )
            if kind == "video" and not metadata.get("duration_ms") and record.get("duration"):
                metadata["duration_ms"] = int(float(record["duration"]) * 1000)
            metadata["valid"] = True
            return metadata
        except (OSError, ValueError, json.JSONDecodeError, subprocess.SubprocessError):
            fallback: dict[str, Any] = {"valid": False}
            if kind == "video" and record.get("duration"):
                fallback["duration_ms"] = int(float(record["duration"]) * 1000)
            return fallback

    def _ensure_variant_locked(
        self,
        connection: sqlite3.Connection,
        asset_id: str,
        revision_id: str,
        source: Path,
        kind: str,
        record: dict[str, Any] | None = None,
    ) -> None:
        record = record or {}
        if kind not in {"image", "video"}:
            return
        variant_path: Path | None = None
        role = "thumbnail" if kind == "image" else "poster"
        if kind == "video":
            thumbnail_filename = str(record.get("thumbnail_filename") or "").strip()
            if thumbnail_filename:
                candidate = _safe_relative_path(self.data_root, f"video_assets/overlay/{Path(thumbnail_filename).name}")
                if candidate.is_file():
                    variant_path = candidate
        else:
            variant_path = self.media_root / asset_id / "v1" / "thumbnail.jpg"
            if not variant_path.is_file():
                try:
                    _create_image_thumbnail(source, variant_path)
                except (OSError, ValueError):
                    variant_path = None
        if variant_path is None or not variant_path.is_file():
            if kind == "video":
                generated = self.media_root / asset_id / "v1" / "poster.jpg"
                if _create_video_poster(source, generated):
                    variant_path = generated
            if variant_path is None or not variant_path.is_file():
                return
        relative_path = variant_path.resolve().relative_to(self.data_root).as_posix()
        width = height = None
        try:
            with Image.open(variant_path) as image:
                width, height = image.size
        except (OSError, ValueError):
            pass
        connection.execute(
            "INSERT OR IGNORE INTO asset_variants(variant_id, revision_id, role, relative_path, "
            "mime_type, width, height) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                f"variant-{asset_id}-{role}",
                revision_id,
                role,
                relative_path,
                _mime_type(variant_path.name),
                width,
                height,
            ),
        )

    def _asset_row(self, asset_id: str) -> sqlite3.Row | None:
        with self._connect() as connection:
            return connection.execute(
                "SELECT a.*, r.revision_id, r.version, r.relative_path, r.mime_type, r.bytes, "
                "r.sha256, r.width, r.height, r.aspect_ratio, r.duration_ms, r.frame_rate, r.has_audio, r.has_transparency "
                "FROM media_assets a LEFT JOIN asset_revisions r ON r.revision_id = a.current_revision_id "
                "WHERE a.asset_id = ?",
                (asset_id,),
            ).fetchone()

    def _row_to_dict(self, row: sqlite3.Row) -> dict[str, Any]:
        return dict(row)

    def list_assets(
        self,
        kind: str | None = None,
        query: str = "",
        include_archived: bool = False,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        if kind is not None and kind not in MEDIA_KINDS:
            raise ValueError("Repository supports image, video, audio and font")
        limit = max(1, min(limit, 500))
        offset = max(0, offset)
        clauses: list[str] = []
        params: list[Any] = []
        if kind:
            clauses.append("a.media_kind = ?")
            params.append(kind)
        if not include_archived:
            clauses.append("a.status <> 'archived'")
        if query.strip():
            clauses.append("(a.name LIKE ? OR r.relative_path LIKE ?)")
            value = f"%{query.strip()}%"
            params.extend([value, value])
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT a.*, r.revision_id, r.version, r.relative_path, r.mime_type, r.bytes, "
                "r.sha256, r.width, r.height, r.aspect_ratio, r.duration_ms, r.frame_rate, r.has_audio, r.has_transparency "
                "FROM media_assets a LEFT JOIN asset_revisions r ON r.revision_id = a.current_revision_id "
                f"{where} ORDER BY a.updated_at DESC LIMIT ? OFFSET ?",
                (*params, limit, offset),
            ).fetchall()
        return [self._row_to_dict(row) for row in rows]

    def count_assets(
        self,
        kind: str | None = None,
        query: str = "",
        include_archived: bool = False,
    ) -> int:
        if kind is not None and kind not in MEDIA_KINDS:
            raise ValueError("Repository supports image, video, audio and font")
        clauses: list[str] = []
        params: list[Any] = []
        if kind:
            clauses.append("a.media_kind = ?")
            params.append(kind)
        if not include_archived:
            clauses.append("a.status <> 'archived'")
        if query.strip():
            clauses.append("(a.name LIKE ? OR r.relative_path LIKE ?)")
            value = f"%{query.strip()}%"
            params.extend([value, value])
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with self._connect() as connection:
            row = connection.execute(
                "SELECT COUNT(*) AS total FROM media_assets a "
                "LEFT JOIN asset_revisions r ON r.revision_id = a.current_revision_id "
                f"{where}",
                params,
            ).fetchone()
        return int(row["total"] if row else 0)

    def get_asset(self, asset_id: str) -> dict[str, Any] | None:
        row = self._asset_row(asset_id)
        return self._row_to_dict(row) if row else None

    def list_domain_items(
        self,
        kind: str,
        query: str = "",
        include_archived: bool = False,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """Return normalized domain projections from the V2 tables.

        Legacy manifests are imported once during initialization; reads after
        that point come from SQLite so the library page and production picker
        share one source of truth.
        """
        limit = max(1, min(limit, 500))
        offset = max(0, offset)
        needle = query.strip()
        with self._connect() as connection:
            if kind == "voice":
                status_clause = "" if include_archived else "AND v.status <> 'archived' "
                rows = connection.execute(
                    "SELECT v.*, a.asset_id, a.legacy_id AS audio_legacy_id, a.status AS audio_status, "
                    "r.revision_id, r.version, r.relative_path, r.mime_type, r.bytes, r.sha256, r.duration_ms "
                    "FROM voice_profiles v JOIN media_assets a ON a.asset_id = v.audio_asset_id "
                    "LEFT JOIN asset_revisions r ON r.revision_id = v.audio_revision_id "
                    "WHERE 1 = 1 " + status_clause
                    + ("AND (v.name LIKE ? OR v.description LIKE ? OR r.relative_path LIKE ?) " if needle else "")
                    + "ORDER BY v.updated_at DESC LIMIT ? OFFSET ?",
                    (*([f"%{needle}%", f"%{needle}%", f"%{needle}%"] if needle else []), limit, offset),
                ).fetchall()
                return [self._voice_profile_item(row) for row in rows]
            if kind == "digital_human":
                status_clause = "" if include_archived else "p.status <> 'archived' AND "
                rows = connection.execute(
                    "SELECT p.*, a.asset_id AS poster_asset_id_resolved, "
                    "a.media_kind AS poster_media_kind, r.relative_path AS poster_relative_path, "
                    "r.mime_type AS poster_mime_type "
                    "FROM digital_human_profiles p LEFT JOIN media_assets a ON a.asset_id = p.poster_asset_id "
                    "LEFT JOIN asset_revisions r ON r.revision_id = a.current_revision_id "
                    + ("WHERE " + status_clause + "(p.name LIKE ? OR p.legacy_id LIKE ?) " if needle else "WHERE " + status_clause + "1 = 1 ")
                    + "ORDER BY p.updated_at DESC LIMIT ? OFFSET ?",
                    (*([f"%{needle}%", f"%{needle}%"] if needle else []), limit, offset),
                ).fetchall()
                return [self._domain_profile_item(row) for row in rows]
            if kind == "brand":
                status_clause = "" if include_archived else "status <> 'archived' AND "
                rows = connection.execute(
                    "SELECT * FROM brand_kits_v2 "
                    + ("WHERE " + status_clause + "(brand_name LIKE ? OR legacy_id LIKE ?) " if needle else "WHERE " + status_clause + "1 = 1 ")
                    + "ORDER BY updated_at DESC LIMIT ? OFFSET ?",
                    (*([f"%{needle}%", f"%{needle}%"] if needle else []), limit, offset),
                ).fetchall()
                return [self._domain_brand_item(row) for row in rows]
            if kind == "template":
                status_clause = "" if include_archived else "t.status <> 'archived' AND "
                rows = connection.execute(
                    "SELECT t.* FROM template_definitions t JOIN (SELECT template_id, MAX(revision) AS revision FROM template_definitions GROUP BY template_id) latest ON latest.template_id = t.template_id AND latest.revision = t.revision "
                    + ("WHERE " + status_clause + "(t.display_name LIKE ? OR t.short_description LIKE ?) " if needle else "WHERE " + status_clause + "1 = 1 ")
                    + "ORDER BY CASE WHEN t.template_id = 'boss_clean' THEN 0 ELSE 1 END, t.template_id ASC LIMIT ? OFFSET ?",
                    (*([f"%{needle}%", f"%{needle}%"] if needle else []), limit, offset),
                ).fetchall()
                return [self._domain_template_item(row) for row in rows]
        return []

    def count_domain_items(self, kind: str, query: str = "", include_archived: bool = False) -> int:
        return len(self.list_domain_items(kind, query, include_archived, 500, 0))

    def _library_union_sql(self) -> str:
        """Server-side projection used by the cursor API.

        The query deliberately keeps pagination in SQLite. The API may enrich
        only the returned page with type-specific previews; it never loads a
        500-row batch and slices it in Python.
        """
        return """WITH library AS (
            SELECT a.asset_id AS resource_id, a.media_kind AS kind, a.name,
                a.description, a.status, a.source, a.created_at, a.updated_at,
                a.asset_id AS media_asset_id, r.width, r.height,
                r.aspect_ratio, r.duration_ms,
                (SELECT MAX(u.updated_at) FROM resource_usage u
                 WHERE u.resource_kind = a.media_kind AND u.resource_id = a.asset_id) AS last_used_at
            FROM media_assets a
            LEFT JOIN asset_revisions r ON r.revision_id = a.current_revision_id
            UNION ALL
            SELECT v.voice_id, 'voice', v.name, v.description, v.status, 'domain',
                v.created_at, v.updated_at, v.audio_asset_id, NULL, NULL,
                NULL, r.duration_ms,
                (SELECT MAX(u.updated_at) FROM resource_usage u
                 WHERE u.resource_kind = 'voice' AND u.resource_id = v.voice_id)
            FROM voice_profiles v
            LEFT JOIN asset_revisions r ON r.revision_id = v.audio_revision_id
            UNION ALL
            SELECT p.profile_id, 'digital_human', p.name,
                COALESCE(p.provider, '数字人'), p.status, 'domain', p.created_at,
                p.updated_at, p.poster_asset_id, NULL, NULL, NULL, NULL,
                (SELECT MAX(u.updated_at) FROM resource_usage u
                 WHERE u.resource_kind = 'digital_human' AND u.resource_id = p.profile_id)
            FROM digital_human_profiles p
            UNION ALL
            SELECT b.brand_id, 'brand', b.brand_name, b.ending_card_text,
                b.status, 'domain', b.created_at, b.updated_at, NULL, NULL, NULL,
                NULL, NULL,
                (SELECT MAX(u.updated_at) FROM resource_usage u
                 WHERE u.resource_kind = 'brand' AND u.resource_id = b.brand_id)
            FROM brand_kits_v2 b
            UNION ALL
            SELECT t.template_id, 'template', t.display_name,
                t.short_description, t.status, 'domain', t.created_at, t.updated_at,
                NULL, NULL, NULL, NULL, NULL,
                (SELECT MAX(u.updated_at) FROM resource_usage u
                 WHERE u.resource_kind = 'template' AND u.resource_id = t.template_id)
            FROM template_definitions t
            JOIN (SELECT template_id, MAX(revision) AS revision
                  FROM template_definitions GROUP BY template_id) latest
              ON latest.template_id = t.template_id AND latest.revision = t.revision
        )"""

    def _library_generation(self, connection: sqlite3.Connection) -> int:
        row = connection.execute(
            "SELECT value FROM schema_meta WHERE key = 'library_index_generation'"
        ).fetchone()
        if row:
            return int(row["value"])
        # Compatibility for a database created before the explicit counter.
        # The counter is initialized on the next repository startup, while
        # this fallback keeps reads safe during an in-process migration.
        return 0

    @staticmethod
    def _touch_library_generation_locked(connection: sqlite3.Connection) -> None:
        """Advance the opaque index generation for every index-affecting mutation."""
        connection.execute(
            "INSERT INTO schema_meta(key, value) VALUES('library_index_generation', '1') "
            "ON CONFLICT(key) DO UPDATE SET value = CAST(CAST(schema_meta.value AS INTEGER) + 1 AS TEXT)"
        )

    def list_library_page(
        self,
        *,
        kind: str | None = None,
        query: str = "",
        include_archived: bool = False,
        page_size: int = 50,
        offset: int = 0,
        cursor: str | None = None,
        favorite: bool | None = None,
        tags: list[str] | None = None,
        collection_id: str | None = None,
        recently_used: bool | None = None,
        orientation: str | None = None,
        aspect: str | None = None,
        min_duration_ms: int | None = None,
        max_duration_ms: int | None = None,
        status: str | None = None,
        source: str | None = None,
        sort: str = "updated",
    ) -> dict[str, Any]:
        from pixelle_video.services.asset_library_cursor import (
            CursorFilterMismatchError,
            CursorStaleError,
            canonical_filter_hash,
            decode_cursor,
            encode_cursor,
        )

        page_size = max(1, min(page_size, 100))
        offset = max(0, offset)
        filters: dict[str, Any] = {
            "kind": kind,
            "q": query.strip(),
            "include_archived": include_archived,
            "favorite": favorite,
            "tags": sorted(tags or []),
            "collection_id": collection_id,
            "recently_used": recently_used,
            "orientation": orientation,
            "aspect": aspect,
            "min_duration_ms": min_duration_ms,
            "max_duration_ms": max_duration_ms,
            "status": status,
            "source": source,
            "sort": sort,
        }
        filter_hash = canonical_filter_hash(filters)
        allowed = {None, "image", "video", "audio", "voice", "digital_human", "brand", "template"}
        if kind not in allowed:
            raise ValueError("Unsupported library item kind")
        if sort not in {"updated", "recent", "name"}:
            raise ValueError("Unsupported library sort")

        clauses: list[str] = ["1 = 1"]
        params: list[Any] = []
        if kind:
            clauses.append("library.kind = ?")
            params.append(kind)
        if query.strip():
            clauses.append("(library.name LIKE ? OR library.description LIKE ? OR library.resource_id LIKE ?)")
            needle = f"%{query.strip()}%"
            params.extend([needle, needle, needle])
        if not include_archived:
            clauses.append("library.status <> 'archived'")
        if status:
            clauses.append("library.status = ?")
            params.append(status)
        if source:
            clauses.append("library.source = ?")
            params.append(source)
        if favorite is not None:
            clauses.append("EXISTS (SELECT 1 FROM resource_favorites f WHERE f.resource_kind = library.kind AND f.resource_id = library.resource_id) = ?")
            params.append(int(favorite))
        if collection_id:
            clauses.append("EXISTS (SELECT 1 FROM collection_items ci WHERE ci.collection_id = ? AND ci.resource_kind = library.kind AND ci.resource_id = library.resource_id)")
            params.append(collection_id)
        if recently_used is not None:
            clauses.append("(library.last_used_at IS NOT NULL) = ?")
            params.append(int(recently_used))
        orientation = aspect or orientation
        if orientation in {"portrait", "landscape", "square"}:
            clauses.append(
                "((? = 'portrait' AND library.height > library.width) OR (? = 'landscape' AND library.width > library.height) OR (? = 'square' AND library.width = library.height))"
            )
            params.extend([orientation, orientation, orientation])
        if min_duration_ms is not None:
            clauses.append("duration_ms >= ?")
            params.append(min_duration_ms)
        if max_duration_ms is not None:
            clauses.append("duration_ms <= ?")
            params.append(max_duration_ms)
        for tag in tags or []:
            clauses.append("EXISTS (SELECT 1 FROM resource_tags rt WHERE rt.resource_kind = library.kind AND rt.resource_id = library.resource_id AND rt.tag = ?)")
            params.append(tag)

        order = {
            "name": "LOWER(name) ASC, kind ASC, resource_id ASC",
            "recent": "COALESCE(last_used_at, '') DESC, updated_at DESC, kind ASC, resource_id ASC",
            "updated": "updated_at DESC, kind ASC, resource_id ASC",
        }[sort]
        with self._connect() as connection:
            generation = self._library_generation(connection)
            facet_clauses = list(clauses)
            facet_params = list(params)
            if cursor:
                decoded = decode_cursor(cursor, secret="ux0-fixture-secret")
                if decoded.filter_hash != filter_hash:
                    raise CursorFilterMismatchError("Cursor does not match current filters")
                if decoded.index_generation != generation:
                    raise CursorStaleError("Cursor is stale; refresh the library")
                if str(decoded.sort.value) != sort:
                    raise CursorFilterMismatchError("Cursor does not match current sort")
                tuple_value = decoded.last_tuple
                if sort == "name":
                    clauses.append("(LOWER(name), kind, resource_id) > (?, ?, ?)")
                    params.extend([str(tuple_value[0]), str(tuple_value[1]), str(tuple_value[2])])
                elif sort == "recent":
                    clauses.append("(COALESCE(last_used_at, ''), updated_at, kind, resource_id) < (?, ?, ?, ?)")
                    params.extend([str(tuple_value[0] or ""), str(tuple_value[1]), str(tuple_value[2]), str(tuple_value[3])])
                else:
                    clauses.append("(updated_at, kind, resource_id) < (?, ?, ?)")
                    params.extend([str(tuple_value[0]), str(tuple_value[1]), str(tuple_value[2])])
            where = " AND ".join(clauses)
            rows = connection.execute(
                self._library_union_sql()
                + f" SELECT resource_id, kind, name, description, status, source, created_at, updated_at, media_asset_id, width, height, aspect_ratio, duration_ms, last_used_at FROM library WHERE {where} ORDER BY {order} LIMIT ? OFFSET ?",
                (*params, page_size + 1, offset),
            ).fetchall()
            has_more = len(rows) > page_size
            rows = rows[:page_size]
            items = [dict(row) for row in rows]
            next_cursor = None
            if has_more and items:
                last = items[-1]
                if sort == "name":
                    last_tuple = [str(last["name"]).lower(), last["kind"], last["resource_id"]]
                elif sort == "recent":
                    last_tuple = [last.get("last_used_at"), last["updated_at"], last["kind"], last["resource_id"]]
                else:
                    last_tuple = [last["updated_at"], last["kind"], last["resource_id"]]
                next_cursor = encode_cursor(sort=sort, filters=filters, index_generation=generation, last_tuple=last_tuple, secret="ux0-fixture-secret")
            total = connection.execute(
                self._library_union_sql() + f" SELECT COUNT(*) AS total FROM library WHERE {' AND '.join(facet_clauses)}",
                facet_params,
            ).fetchone()["total"]
            facet_where = " AND ".join(facet_clauses)
            facet_kinds = connection.execute(self._library_union_sql() + f" SELECT kind, COUNT(*) AS total FROM library WHERE {facet_where} GROUP BY kind", facet_params).fetchall()
            facet_statuses = connection.execute(self._library_union_sql() + f" SELECT status, COUNT(*) AS total FROM library WHERE {facet_where} GROUP BY status", facet_params).fetchall()
            facet_tags = connection.execute(self._library_union_sql() + f" SELECT rt.tag, COUNT(DISTINCT library.resource_id) AS total FROM library JOIN resource_tags rt ON rt.resource_kind = library.kind AND rt.resource_id = library.resource_id WHERE {facet_where} GROUP BY rt.tag", facet_params).fetchall()
        return {"items": items, "total": int(total), "next_cursor": next_cursor, "index_generation": generation, "filter_hash": filter_hash, "facets": {"kinds": {str(row["kind"]): int(row["total"]) for row in facet_kinds}, "statuses": {str(row["status"]): int(row["total"]) for row in facet_statuses}, "tags": {str(row["tag"]): int(row["total"]) for row in facet_tags}}}

    def library_facets(self, **filters: Any) -> dict[str, Any]:
        """Return facets using the same SQL predicate as the current page."""
        return self.list_library_page(page_size=1, **filters)["facets"]

    def get_domain_item(self, kind: str, resource_id: str) -> dict[str, Any] | None:
        items = self.list_domain_items(kind, "", True, 500, 0)
        return next((item for item in items if item["resource_id"] == resource_id), None)

    def _domain_media_item(self, row: sqlite3.Row, kind: str) -> dict[str, Any]:
        data = dict(row)
        return {
            "resource_id": data.get("legacy_id") or data["asset_id"],
            "kind": kind,
            "name": data["name"],
            "description": data.get("relative_path") or "参考音色",
            "status": data["status"],
            "cover_url": f"/api/v2/media-assets/{data['asset_id']}/file",
            "file_url": f"/api/v2/media-assets/{data['asset_id']}/file",
            "tags": ["audio"],
            "favorite": False,
            "created_at": data["created_at"],
            "updated_at": data["updated_at"],
            "summary": {"filename": Path(data.get("relative_path") or "").name, "bytes": int(data.get("bytes") or 0)},
            "asset_id": data["asset_id"],
            "revision": {"revision_id": data.get("revision_id"), "version": data.get("version"), "duration_ms": data.get("duration_ms")},
        }

    def _voice_profile_item(self, row: sqlite3.Row) -> dict[str, Any]:
        data = dict(row)
        return {
            "resource_id": data["voice_id"],
            "kind": "voice",
            "name": data["name"],
            "description": "参考音色" if str(data.get("description") or "").startswith(("voice_references/", "/")) else (data.get("description") or "参考音色"),
            "status": data["status"],
            "cover_url": f"/api/v2/media-assets/{data['asset_id']}/file",
            "file_url": f"/api/v2/media-assets/{data['asset_id']}/file",
            "tags": [tag for tag in (data.get("language"), data.get("style")) if tag],
            "favorite": False,
            "created_at": data["created_at"],
            "updated_at": data["updated_at"],
            "summary": {
                "language": data.get("language") or "未设置",
                "style": data.get("style") or "未设置",
                "authorization_status": data.get("authorization_status") or "unknown",
                "reference_duration_ms": int(data.get("duration_ms") or 0),
            },
            "asset_id": data["asset_id"],
            "revision": {
                "revision_id": data.get("revision_id"),
                "version": data.get("version"),
                "bytes": data.get("bytes"),
                "sha256": data.get("sha256"),
                "duration_ms": data.get("duration_ms"),
            },
            "voice_profile": {
                "voice_id": data["voice_id"],
                "legacy_id": data.get("legacy_id"),
                "language": data.get("language") or "",
                "style": data.get("style") or "",
                "authorization_status": data.get("authorization_status") or "unknown",
            },
        }

    def _domain_profile_item(self, row: sqlite3.Row) -> dict[str, Any]:
        data = dict(row)
        scenes = self.list_digital_human_scenes(data["profile_id"])
        poster_asset_id = str(data["poster_asset_id"]) if data.get("poster_asset_id") else None
        poster_media_type = "video" if (
            data.get("poster_media_kind") == "video"
            or str(data.get("poster_mime_type") or "").lower().startswith("video/")
            or str(data.get("poster_relative_path") or "").lower().endswith((".mp4", ".mov", ".webm", ".m4v"))
        ) else "image"
        file_url = f"/api/v2/media-assets/{poster_asset_id}/file" if poster_asset_id else None
        cover_url = file_url
        # A video is the source/demo file, not an <img>-compatible cover. Use
        # the generated poster variant for cards while keeping file_url for
        # the full media preview and the production resolver.
        if poster_asset_id and poster_media_type == "video":
            variant = next(
                (
                    item
                    for item in self.get_variants(poster_asset_id)
                    if item.get("role") in {"poster", "thumbnail"}
                ),
                None,
            )
            cover_url = (
                f"/api/v2/media-assets/{poster_asset_id}/variants/{variant['role']}"
                if variant
                else None
            )
        return {
            "resource_id": data["profile_id"],
            "kind": "digital_human",
            "name": data["name"],
            "description": "人物档案",
            "status": data["status"],
            "cover_url": cover_url,
            "file_url": file_url,
            "tags": [item for item in (data.get("gender"), data.get("style"), data.get("posture")) if item],
            "favorite": False,
            "created_at": data["created_at"],
            "updated_at": data["updated_at"],
            "summary": {"provider": data.get("provider") or "custom", "quality_state": data.get("quality_state") or "unchecked", "default_scene_id": data.get("default_scene_id") or "", "media_type": poster_media_type},
            "poster_asset_id": poster_asset_id,
            "scenes": scenes,
        }

    def list_digital_human_scenes(self, profile_id: str) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT s.*, a.asset_id AS preview_asset_id, a.media_kind AS preview_media_kind, "
                "r.mime_type AS preview_mime_type "
                "FROM digital_human_scenes s "
                "LEFT JOIN media_assets a ON a.asset_id = s.source_asset_id "
                "LEFT JOIN asset_revisions r ON r.asset_id = a.asset_id "
                "AND r.revision_id = COALESCE(s.source_revision_id, a.current_revision_id) "
                "WHERE s.profile_id = ? AND s.status <> 'archived' ORDER BY s.sort_order ASC, s.updated_at DESC",
                (profile_id,),
            ).fetchall()
        result: list[dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            if item.get("preview_asset_id"):
                revision_query = (
                    f"?revision_id={item['source_revision_id']}"
                    if item.get("source_revision_id")
                    else ""
                )
                item["preview_url"] = (
                    f"/api/v2/media-assets/{item['preview_asset_id']}/file{revision_query}"
                )
                item["preview_media_type"] = "video" if (
                    item.get("preview_media_kind") == "video"
                    or str(item.get("preview_mime_type") or "").lower().startswith("video/")
                ) else "image"
            result.append(item)
        return result

    def get_digital_human_scene(self, scene_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT s.*, a.media_kind AS preview_media_kind, r.mime_type AS preview_mime_type "
                "FROM digital_human_scenes s "
                "LEFT JOIN media_assets a ON a.asset_id = s.source_asset_id "
                "LEFT JOIN asset_revisions r ON r.asset_id = a.asset_id "
                "AND r.revision_id = COALESCE(s.source_revision_id, a.current_revision_id) "
                "WHERE s.scene_id = ?",
                (scene_id,),
            ).fetchone()
        if not row:
            return None
        item = dict(row)
        if item.get("source_asset_id"):
            revision_query = (
                f"?revision_id={item['source_revision_id']}"
                if item.get("source_revision_id")
                else ""
            )
            item["preview_url"] = (
                f"/api/v2/media-assets/{item['source_asset_id']}/file{revision_query}"
            )
            item["preview_media_type"] = "video" if (
                item.get("preview_media_kind") == "video"
                or str(item.get("preview_mime_type") or "").lower().startswith("video/")
            ) else "image"
        return item

    def get_scene_source_path(self, scene_id: str) -> Path | None:
        scene = self.get_digital_human_scene(scene_id)
        if not scene or not scene.get("source_asset_id"):
            return None
        return self.get_revision_path(
            str(scene["source_asset_id"]),
            revision_id=str(scene.get("source_revision_id") or "") or None,
        )

    def get_profile_source_path(self, profile_id: str) -> Path | None:
        """Resolve a profile's poster/source asset for legacy image profiles.

        A profile can exist without an explicit scene source (for example a
        newly imported image portrait).  The profile's poster asset is still
        a valid deterministic source for the digital-human provider.
        """
        profile = self.get_domain_item("digital_human", profile_id)
        if not profile or not profile.get("poster_asset_id"):
            return None
        return self.get_revision_path(str(profile["poster_asset_id"]))

    def _domain_brand_item(self, row: sqlite3.Row) -> dict[str, Any]:
        data = dict(row)
        return {
            "resource_id": data["brand_id"],
            "kind": "brand",
            "name": data["brand_name"],
            "description": data.get("ending_card_text") or "品牌套件",
            "status": data["status"],
            "cover_url": f"/api/v2/media-assets/{data['logo_asset_id']}/file" if data.get("logo_asset_id") else None,
            "tags": [],
            "favorite": False,
            "created_at": data["created_at"],
            "updated_at": data["updated_at"],
            "summary": {"primary_color": data["primary_color"], "secondary_color": data["secondary_color"], "font_family": data["font_family"], "has_logo": bool(data.get("logo_asset_id")), "has_bgm": bool(data.get("default_bgm_asset_id")), "has_contact": bool(data.get("store_address") or data.get("phone"))},
            "brand": data,
        }

    def _domain_template_item(self, row: sqlite3.Row) -> dict[str, Any]:
        data = dict(row)
        try:
            cover_contract = json.loads(data.get("cover_contract_json") or "{}")
            subtitle_contract = json.loads(data.get("subtitle_contract_json") or "{}")
            layout_contract = json.loads(data.get("layout_contract_json") or "{}")
        except json.JSONDecodeError:
            cover_contract, subtitle_contract, layout_contract = {}, {}, {}
        return {
            "resource_id": data["template_id"],
            "kind": "template",
            "name": data["display_name"],
            "description": data["short_description"],
            "status": data["status"],
            "cover_url": data.get("preview_url"),
            "tags": [],
            "favorite": False,
            "created_at": data["created_at"],
            "updated_at": data["updated_at"],
            "summary": {"revision": int(data["revision"]), "canvas_width": int(cover_contract.get("canvas_width") or 0), "canvas_height": int(cover_contract.get("canvas_height") or 0), "subtitle_font_size": int(subtitle_contract.get("font_size") or 0)},
            "template": data,
            "layout_contract": layout_contract or None,
        }

    @staticmethod
    def _require_media_reference_locked(
        connection: sqlite3.Connection,
        asset_id: str,
        allowed_kinds: set[str],
        revision_id: str | None = None,
    ) -> sqlite3.Row:
        """Validate a domain link before persisting it.

        Domain resources keep typed references to media revisions.  Failing
        early here prevents a profile/brand from becoming visible in the
        library with a broken preview or an unresolvable render source.
        """
        row = connection.execute(
            "SELECT * FROM media_assets WHERE asset_id = ?",
            (asset_id,),
        ).fetchone()
        if not row or row["media_kind"] not in allowed_kinds:
            expected = "/".join(sorted(allowed_kinds))
            raise ValueError(f"Media asset {asset_id!r} must be an existing {expected} asset")
        if revision_id:
            revision = connection.execute(
                "SELECT 1 FROM asset_revisions WHERE asset_id = ? AND revision_id = ?",
                (asset_id, revision_id),
            ).fetchone()
            if not revision:
                raise ValueError(f"Revision {revision_id!r} does not belong to media asset {asset_id!r}")
        return row

    def create_brand_kit(self, values: dict[str, Any]) -> dict[str, Any]:
        now = _now()
        brand_id = str(values.get("brand_id") or f"brand-{uuid.uuid4().hex[:12]}")
        font_id = str(values.get("font_family") or "")
        if font_id and not resolve_registered_font(font_id):
            raise ValueError(f"font_id_not_registered:{font_id}")
        with self._lock, self._connect() as connection:
            if values.get("logo_asset_id"):
                self._require_media_reference_locked(connection, str(values["logo_asset_id"]), {"image"})
            if values.get("default_bgm_asset_id"):
                self._require_media_reference_locked(connection, str(values["default_bgm_asset_id"]), {"audio"})
            connection.execute(
                "INSERT INTO brand_kits_v2(brand_id, legacy_id, brand_name, logo_asset_id, default_bgm_asset_id, primary_color, secondary_color, font_family, default_subtitle_style, ending_card_text, store_address, phone, coupon_phrase, status, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'ready', ?, ?)",
                (brand_id, values.get("legacy_id"), str(values.get("brand_name") or "未命名品牌"), values.get("logo_asset_id"), values.get("default_bgm_asset_id"), str(values.get("primary_color") or "#1f6feb"), str(values.get("secondary_color") or "#0f766e"), str(values.get("font_family") or ""), str(values.get("default_subtitle_style") or ""), str(values.get("ending_card_text") or ""), str(values.get("store_address") or ""), str(values.get("phone") or ""), str(values.get("coupon_phrase") or ""), now, now),
            )
            self._record_domain_revision_locked(connection, "brand", brand_id, self._domain_row_payload_locked(connection, "brand", brand_id))
        return self.get_domain_item("brand", brand_id) or {}

    def patch_brand_kit(self, brand_id: str, values: dict[str, Any]) -> dict[str, Any] | None:
        allowed = {key: value for key, value in values.items() if key in {"brand_name", "logo_asset_id", "default_bgm_asset_id", "primary_color", "secondary_color", "font_family", "default_subtitle_style", "ending_card_text", "store_address", "phone", "coupon_phrase", "status"} and value is not None}
        if not allowed:
            return self.get_domain_item("brand", brand_id)
        if allowed.get("font_family") and not resolve_registered_font(str(allowed["font_family"])):
            raise ValueError(f"font_id_not_registered:{allowed['font_family']}")
        updates = ", ".join(f"{key} = ?" for key in allowed)
        with self._lock, self._connect() as connection:
            if allowed.get("logo_asset_id"):
                self._require_media_reference_locked(connection, str(allowed["logo_asset_id"]), {"image"})
            if allowed.get("default_bgm_asset_id"):
                self._require_media_reference_locked(connection, str(allowed["default_bgm_asset_id"]), {"audio"})
            cursor = connection.execute(f"UPDATE brand_kits_v2 SET {updates}, updated_at = ? WHERE brand_id = ?", (*allowed.values(), _now(), brand_id))
            if cursor.rowcount == 0:
                return None
            self._record_domain_revision_locked(connection, "brand", brand_id, self._domain_row_payload_locked(connection, "brand", brand_id))
        return self.get_domain_item("brand", brand_id)

    def set_domain_status(self, kind: str, resource_id: str, status: str) -> dict[str, Any] | None:
        table_and_column = {"brand": ("brand_kits_v2", "brand_id"), "digital_human": ("digital_human_profiles", "profile_id"), "template": ("template_definitions", "template_id")}
        if kind == "voice":
            with self._lock, self._connect() as connection:
                row = connection.execute("SELECT voice_id FROM voice_profiles WHERE voice_id = ? OR legacy_id = ?", (resource_id, resource_id)).fetchone()
                if not row:
                    return None
                connection.execute("UPDATE voice_profiles SET status = ?, updated_at = ? WHERE voice_id = ?", (status, _now(), row["voice_id"]))
                resource_id = str(row["voice_id"])
            return self.get_domain_item(kind, resource_id)
        table_info = table_and_column.get(kind)
        if not table_info:
            return None
        table, column = table_info
        with self._lock, self._connect() as connection:
            if kind == "template":
                cursor = connection.execute(f"UPDATE {table} SET status = ?, updated_at = ? WHERE {column} = ?", (status, _now(), resource_id))
            else:
                cursor = connection.execute(f"UPDATE {table} SET status = ?, updated_at = ? WHERE {column} = ?", (status, _now(), resource_id))
            if cursor.rowcount == 0:
                return None
            self._record_domain_revision_locked(
                connection,
                kind,
                resource_id,
                self._domain_row_payload_locked(connection, kind, resource_id),
            )
        return self.get_domain_item(kind, resource_id)

    def get_asset_by_legacy_id(self, media_kind: str, legacy_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute("SELECT asset_id FROM media_assets WHERE media_kind = ? AND legacy_id = ?", (media_kind, legacy_id)).fetchone()
        return self.get_asset(row["asset_id"]) if row else None

    def create_voice_profile(self, values: dict[str, Any]) -> dict[str, Any]:
        now = _now()
        voice_id = str(values.get("voice_id") or f"voice-{uuid.uuid4().hex[:12]}")
        audio_asset_id = str(values.get("audio_asset_id") or "")
        with self._lock, self._connect() as connection:
            row = self._require_media_reference_locked(
                connection,
                audio_asset_id,
                {"audio"},
                str(values["audio_revision_id"]) if values.get("audio_revision_id") else None,
            )
            revision_id = values.get("audio_revision_id") or row["current_revision_id"]
            connection.execute(
                "INSERT INTO voice_profiles(voice_id, legacy_id, audio_asset_id, audio_revision_id, name, description, language, style, authorization_status, status, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'ready', ?, ?)",
                (voice_id, values.get("legacy_id"), audio_asset_id, revision_id, str(values.get("name") or "未命名音色"), str(values.get("description") or ""), str(values.get("language") or ""), str(values.get("style") or ""), str(values.get("authorization_status") or "unknown"), now, now),
            )
        return self.get_domain_item("voice", voice_id) or {}

    def patch_voice_profile(self, voice_id: str, values: dict[str, Any]) -> dict[str, Any] | None:
        allowed = {key: value for key, value in values.items() if key in {"name", "description", "language", "style", "authorization_status", "status", "audio_asset_id", "audio_revision_id"} and value is not None}
        if not allowed:
            return self.get_domain_item("voice", voice_id)
        with self._lock, self._connect() as connection:
            if allowed.get("audio_asset_id"):
                row = self._require_media_reference_locked(connection, str(allowed["audio_asset_id"]), {"audio"}, str(allowed.get("audio_revision_id")) if allowed.get("audio_revision_id") else None)
                allowed.setdefault("audio_revision_id", row["current_revision_id"])
            updates = ", ".join(f"{key} = ?" for key in allowed)
            cursor = connection.execute(f"UPDATE voice_profiles SET {updates}, updated_at = ? WHERE voice_id = ?", (*allowed.values(), _now(), voice_id))
            if cursor.rowcount == 0:
                return None
        return self.get_domain_item("voice", voice_id)

    def create_digital_human_profile(self, values: dict[str, Any]) -> dict[str, Any]:
        now = _now()
        profile_id = str(values.get("profile_id") or f"digital-human-{uuid.uuid4().hex[:12]}")
        scene_id = str(values.get("default_scene_id") or f"scene-{uuid.uuid4().hex[:12]}")
        source_asset_id = values.get("source_asset_id") or values.get("poster_asset_id")
        source_revision_id = values.get("source_revision_id")
        with self._lock, self._connect() as connection:
            poster_asset_id = values.get("poster_asset_id") or source_asset_id
            if poster_asset_id:
                self._require_media_reference_locked(connection, str(poster_asset_id), {"image", "video"})
            if source_asset_id:
                source_row = self._require_media_reference_locked(
                    connection,
                    str(source_asset_id),
                    {"image", "video"},
                    str(source_revision_id) if source_revision_id else None,
                )
            else:
                source_row = None
            if source_asset_id and not source_revision_id:
                source_revision_id = source_row["current_revision_id"] if source_row else None
            connection.execute(
                "INSERT INTO digital_human_profiles(profile_id, legacy_id, name, provider, poster_asset_id, gender, style, posture, supported_workflows_json, default_scene_id, quality_state, status, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'unchecked', 'ready', ?, ?)",
                (profile_id, values.get("legacy_id"), str(values.get("name") or "未命名数字人"), str(values.get("provider") or "custom"), poster_asset_id, values.get("gender"), values.get("style"), values.get("posture"), json.dumps(values.get("supported_workflows") or [], ensure_ascii=False), scene_id, now, now),
            )
            connection.execute(
                "INSERT INTO digital_human_scenes(scene_id, profile_id, name, source_asset_id, source_revision_id, shot_size, location, outfit, posture, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (scene_id, profile_id, str(values.get("scene_name") or "默认场景"), source_asset_id, source_revision_id, str(values.get("shot_size") or "medium"), str(values.get("location") or ""), str(values.get("outfit") or ""), str(values.get("posture") or ""), now, now),
            )
            self._record_domain_revision_locked(connection, "digital_human", profile_id, self._domain_row_payload_locked(connection, "digital_human", profile_id))
        return self.get_domain_item("digital_human", profile_id) or {}

    def patch_digital_human_profile(
        self, profile_id: str, values: dict[str, Any]
    ) -> dict[str, Any] | None:
        allowed = {
            key: value
            for key, value in values.items()
            if key
            in {
                "name",
                "provider",
                "poster_asset_id",
                "gender",
                "style",
                "posture",
                "supported_workflows_json",
                "default_scene_id",
                "quality_state",
                "status",
            }
            and value is not None
        }
        if "supported_workflows" in values and values["supported_workflows"] is not None:
            allowed["supported_workflows_json"] = json.dumps(
                values["supported_workflows"], ensure_ascii=False
            )
        if not allowed:
            return self.get_domain_item("digital_human", profile_id)
        updates = ", ".join(f"{key} = ?" for key in allowed)
        with self._lock, self._connect() as connection:
            if allowed.get("poster_asset_id"):
                self._require_media_reference_locked(connection, str(allowed["poster_asset_id"]), {"image", "video"})
            cursor = connection.execute(
                f"UPDATE digital_human_profiles SET {updates}, updated_at = ? WHERE profile_id = ?",
                (*allowed.values(), _now(), profile_id),
            )
            if cursor.rowcount == 0:
                return None
            self._record_domain_revision_locked(
                connection,
                "digital_human",
                profile_id,
                self._domain_row_payload_locked(connection, "digital_human", profile_id),
            )
        return self.get_domain_item("digital_human", profile_id)

    def create_digital_human_scene(
        self, profile_id: str, values: dict[str, Any]
    ) -> dict[str, Any] | None:
        now = _now()
        scene_id = str(values.get("scene_id") or f"scene-{uuid.uuid4().hex[:12]}")
        source_asset_id = values.get("source_asset_id")
        source_revision_id = values.get("source_revision_id")
        with self._lock, self._connect() as connection:
            if not connection.execute(
                "SELECT 1 FROM digital_human_profiles WHERE profile_id = ?",
                (profile_id,),
            ).fetchone():
                return None
            source_row = None
            if source_asset_id:
                source_row = self._require_media_reference_locked(
                    connection,
                    str(source_asset_id),
                    {"image", "video"},
                    str(source_revision_id) if source_revision_id else None,
                )
            if source_asset_id and not source_revision_id:
                source_revision_id = source_row["current_revision_id"] if source_row else None
            connection.execute(
                "INSERT INTO digital_human_scenes(scene_id, profile_id, name, source_asset_id, source_revision_id, shot_size, location, outfit, posture, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    scene_id,
                    profile_id,
                    str(values.get("name") or "默认场景"),
                    source_asset_id,
                    source_revision_id,
                    str(values.get("shot_size") or "medium"),
                    str(values.get("location") or ""),
                    str(values.get("outfit") or ""),
                    str(values.get("posture") or ""),
                    now,
                    now,
                ),
            )
            connection.execute(
                "UPDATE digital_human_profiles SET updated_at = ? WHERE profile_id = ?",
                (now, profile_id),
            )
            self._record_domain_revision_locked(
                connection,
                "digital_human",
                profile_id,
                self._domain_row_payload_locked(connection, "digital_human", profile_id),
            )
        return self.get_digital_human_scene(scene_id)

    def patch_digital_human_scene(self, scene_id: str, values: dict[str, Any]) -> dict[str, Any] | None:
        allowed = {key: value for key, value in values.items() if key in {"name", "shot_size", "location", "outfit", "posture", "source_asset_id", "source_revision_id", "status"} and value is not None}
        if not allowed:
            return self.get_digital_human_scene(scene_id)
        with self._lock, self._connect() as connection:
            if allowed.get("source_asset_id"):
                row = self._require_media_reference_locked(connection, str(allowed["source_asset_id"]), {"image", "video"}, str(allowed.get("source_revision_id")) if allowed.get("source_revision_id") else None)
                allowed.setdefault("source_revision_id", row["current_revision_id"])
            updates = ", ".join(f"{key} = ?" for key in allowed)
            cursor = connection.execute(f"UPDATE digital_human_scenes SET {updates}, updated_at = ? WHERE scene_id = ?", (*allowed.values(), _now(), scene_id))
            if cursor.rowcount == 0:
                return None
            profile = connection.execute("SELECT profile_id FROM digital_human_scenes WHERE scene_id = ?", (scene_id,)).fetchone()
            if profile:
                connection.execute("UPDATE digital_human_profiles SET updated_at = ? WHERE profile_id = ?", (_now(), profile["profile_id"]))
        return self.get_digital_human_scene(scene_id)

    def reorder_digital_human_scenes(self, profile_id: str, scene_ids: list[str]) -> list[dict[str, Any]]:
        with self._lock, self._connect() as connection:
            existing = {str(row["scene_id"]) for row in connection.execute("SELECT scene_id FROM digital_human_scenes WHERE profile_id = ?", (profile_id,)).fetchall()}
            if set(scene_ids) != existing:
                raise ValueError("Scene order must include every scene exactly once")
            now = _now()
            connection.executemany("UPDATE digital_human_scenes SET sort_order = ?, updated_at = ? WHERE scene_id = ? AND profile_id = ?", [(index, now, scene_id, profile_id) for index, scene_id in enumerate(scene_ids)])
            connection.execute("UPDATE digital_human_profiles SET updated_at = ? WHERE profile_id = ?", (now, profile_id))
        return self.list_digital_human_scenes(profile_id)

    def _domain_row_payload_locked(self, connection: sqlite3.Connection, kind: str, resource_id: str) -> dict[str, Any]:
        if kind == "brand":
            row = connection.execute("SELECT * FROM brand_kits_v2 WHERE brand_id = ?", (resource_id,)).fetchone()
            return dict(row) if row else {}
        if kind == "digital_human":
            row = connection.execute("SELECT * FROM digital_human_profiles WHERE profile_id = ?", (resource_id,)).fetchone()
            return dict(row) if row else {}
        if kind == "template":
            row = connection.execute(
                "SELECT * FROM template_definitions WHERE template_id = ? "
                "ORDER BY revision DESC LIMIT 1",
                (resource_id,),
            ).fetchone()
            return dict(row) if row else {}
        return {}

    def _record_domain_revision_locked(self, connection: sqlite3.Connection, kind: str, resource_id: str, payload: dict[str, Any]) -> int:
        row = connection.execute("SELECT COALESCE(MAX(revision), 0) AS revision FROM domain_revisions WHERE resource_kind = ? AND resource_id = ?", (kind, resource_id)).fetchone()
        revision = int(row["revision"] or 0) + 1
        connection.execute("INSERT INTO domain_revisions(resource_kind, resource_id, revision, payload_json, created_at) VALUES (?, ?, ?, ?, ?)", (kind, resource_id, revision, json.dumps(payload, ensure_ascii=False, default=str), _now()))
        return revision

    def list_domain_revisions(self, kind: str, resource_id: str) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute("SELECT * FROM domain_revisions WHERE resource_kind = ? AND resource_id = ? ORDER BY revision DESC", (kind, resource_id)).fetchall()
        return [self._row_to_dict(row) for row in rows]

    def create_template_revision(self, values: dict[str, Any]) -> dict[str, Any]:
        now = _now()
        template_id = str(values.get("template_id") or f"template-{uuid.uuid4().hex[:12]}")
        layout_contract = values.get("layout_contract")
        if layout_contract is not None:
            try:
                layout_contract = TemplateLayoutContract.model_validate(layout_contract).model_dump(mode="json")
            except (TypeError, ValueError) as exc:
                raise ValueError(f"Invalid TemplateLayoutContract: {exc}") from exc
        with self._lock, self._connect() as connection:
            current = connection.execute("SELECT COALESCE(MAX(revision), 0) AS revision FROM template_definitions WHERE template_id = ?", (template_id,)).fetchone()
            revision = int(current["revision"] or 0) + 1
            connection.execute(
                "INSERT INTO template_definitions(template_id, revision, display_name, short_description, full_description, preview_url, schema_version, renderer_version, cover_contract_json, subtitle_contract_json, layout_contract_json, status, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'ready', ?, ?)",
                (template_id, revision, str(values.get("display_name") or "未命名模板"), str(values.get("short_description") or ""), str(values.get("full_description") or ""), values.get("preview_url"), int(values.get("schema_version") or 1), str(values.get("renderer_version") or "ip-broadcast-composer-v2"), json.dumps(values.get("cover_contract") or {}, ensure_ascii=False), json.dumps(values.get("subtitle_contract") or {}, ensure_ascii=False), json.dumps(layout_contract or {}, ensure_ascii=False), now, now),
            )
            self._record_domain_revision_locked(
                connection,
                "template",
                template_id,
                self._domain_row_payload_locked(connection, "template", template_id),
            )
        return self.get_domain_item("template", template_id) or {}

    def patch_template_revision(
        self, template_id: str, values: dict[str, Any]
    ) -> dict[str, Any] | None:
        current = self.get_template_revision(template_id)
        if not current:
            return None
        payload = {
            "template_id": template_id,
            "display_name": values.get("display_name", current["display_name"]),
            "short_description": values.get("short_description", current["short_description"]),
            "full_description": values.get("full_description", current["full_description"]),
            "preview_url": values.get("preview_url", current.get("preview_url")),
            "schema_version": values.get("schema_version", current["schema_version"]),
            "renderer_version": values.get("renderer_version", current["renderer_version"]),
            "cover_contract": values.get(
                "cover_contract", json.loads(current.get("cover_contract_json") or "{}")
            ),
            "subtitle_contract": values.get(
                "subtitle_contract", json.loads(current.get("subtitle_contract_json") or "{}")
            ),
            "layout_contract": values.get("layout_contract", json.loads(current.get("layout_contract_json") or "{}")) or None,
        }
        if values.get("status") is not None:
            payload["status"] = values["status"]
        return self.create_template_revision(payload)

    def resource_tags(self, resource_kind: str, resource_id: str) -> list[str]:
        with self._connect() as connection:
            rows = connection.execute("SELECT tag FROM resource_tags WHERE resource_kind = ? AND resource_id = ? ORDER BY tag", (resource_kind, resource_id)).fetchall()
        return [str(row["tag"]) for row in rows]

    def is_favorite(self, resource_kind: str, resource_id: str) -> bool:
        with self._connect() as connection:
            return connection.execute("SELECT 1 FROM resource_favorites WHERE resource_kind = ? AND resource_id = ?", (resource_kind, resource_id)).fetchone() is not None

    def set_resource_tags(self, resource_kind: str, resource_id: str, tags: list[str]) -> list[str]:
        clean = sorted({tag.strip() for tag in tags if tag and tag.strip()})[:30]
        with self._lock, self._connect() as connection:
            connection.execute("DELETE FROM resource_tags WHERE resource_kind = ? AND resource_id = ?", (resource_kind, resource_id))
            connection.executemany("INSERT INTO resource_tags(resource_kind, resource_id, tag, created_at) VALUES (?, ?, ?, ?)", [(resource_kind, resource_id, tag, _now()) for tag in clean])
        return clean

    def set_favorite(self, resource_kind: str, resource_id: str, favorite: bool) -> bool:
        with self._lock, self._connect() as connection:
            if favorite:
                connection.execute("INSERT OR IGNORE INTO resource_favorites(resource_kind, resource_id, created_at) VALUES (?, ?, ?)", (resource_kind, resource_id, _now()))
            else:
                connection.execute("DELETE FROM resource_favorites WHERE resource_kind = ? AND resource_id = ?", (resource_kind, resource_id))
        return favorite

    def create_collection(self, name: str, description: str = "") -> dict[str, Any]:
        now = _now()
        clean_name = name.strip() or "未命名集合"
        item = {"collection_id": f"collection-{uuid.uuid4().hex[:12]}", "name": clean_name, "description": description, "status": "ready", "created_at": now, "updated_at": now}
        with self._lock, self._connect() as connection:
            if connection.execute("SELECT 1 FROM resource_collections WHERE lower(name) = lower(?) AND status <> 'archived'", (clean_name,)).fetchone():
                raise ValueError("Collection name already exists")
            connection.execute("INSERT INTO resource_collections(collection_id, name, description, status, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)", tuple(item.values()))
        return item

    def list_collections(self) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute("SELECT c.*, COUNT(i.resource_id) AS item_count FROM resource_collections c LEFT JOIN collection_items i ON i.collection_id = c.collection_id GROUP BY c.collection_id ORDER BY c.updated_at DESC").fetchall()
        return [dict(row) for row in rows]

    def patch_collection(self, collection_id: str, name: str | None = None, description: str | None = None) -> dict[str, Any] | None:
        updates: list[str] = []
        values: list[Any] = []
        if name is not None:
            updates.append("name = ?")
            values.append(name.strip() or "未命名集合")
        if description is not None:
            updates.append("description = ?")
            values.append(description)
        if not updates:
            return next((item for item in self.list_collections() if item["collection_id"] == collection_id), None)
        updates.append("updated_at = ?")
        values.extend([_now(), collection_id])
        with self._lock, self._connect() as connection:
            if name is not None and connection.execute("SELECT 1 FROM resource_collections WHERE lower(name) = lower(?) AND status <> 'archived' AND collection_id <> ?", (name.strip(), collection_id)).fetchone():
                raise ValueError("Collection name already exists")
            cursor = connection.execute(f"UPDATE resource_collections SET {', '.join(updates)} WHERE collection_id = ?", values)
            if cursor.rowcount == 0:
                return None
        return next((item for item in self.list_collections() if item["collection_id"] == collection_id), None)

    def set_collection_status(self, collection_id: str, status: str) -> dict[str, Any] | None:
        with self._lock, self._connect() as connection:
            cursor = connection.execute("UPDATE resource_collections SET status = ?, updated_at = ? WHERE collection_id = ?", (status, _now(), collection_id))
            if cursor.rowcount == 0:
                return None
        return next((item for item in self.list_collections() if item["collection_id"] == collection_id), None)

    def delete_collection(self, collection_id: str) -> bool:
        with self._lock, self._connect() as connection:
            cursor = connection.execute("DELETE FROM resource_collections WHERE collection_id = ?", (collection_id,))
        return cursor.rowcount > 0

    def list_collection_items(self, collection_id: str) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute("SELECT resource_kind, resource_id, created_at FROM collection_items WHERE collection_id = ? ORDER BY created_at DESC", (collection_id,)).fetchall()
        return [dict(row) for row in rows]

    def add_collection_item(self, collection_id: str, resource_kind: str, resource_id: str) -> bool:
        with self._lock, self._connect() as connection:
            if not connection.execute("SELECT 1 FROM resource_collections WHERE collection_id = ?", (collection_id,)).fetchone():
                return False
            connection.execute("INSERT OR IGNORE INTO collection_items(collection_id, resource_kind, resource_id, created_at) VALUES (?, ?, ?, ?)", (collection_id, resource_kind, resource_id, _now()))
            connection.execute("UPDATE resource_collections SET updated_at = ? WHERE collection_id = ?", (_now(), collection_id))
        return True

    def remove_collection_item(self, collection_id: str, resource_kind: str, resource_id: str) -> bool:
        with self._lock, self._connect() as connection:
            cursor = connection.execute("DELETE FROM collection_items WHERE collection_id = ? AND resource_kind = ? AND resource_id = ?", (collection_id, resource_kind, resource_id))
            connection.execute("UPDATE resource_collections SET updated_at = ? WHERE collection_id = ?", (_now(), collection_id))
        return cursor.rowcount > 0

    def get_variants(self, asset_id: str) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT v.* FROM asset_variants v JOIN media_assets a "
                "ON a.current_revision_id = v.revision_id WHERE a.asset_id = ?",
                (asset_id,),
            ).fetchall()
        return [self._row_to_dict(row) for row in rows]

    def list_revisions(self, asset_id: str) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM asset_revisions WHERE asset_id = ? ORDER BY version DESC",
                (asset_id,),
            ).fetchall()
        return [self._row_to_dict(row) for row in rows]

    def record_usage(
        self,
        asset_id: str,
        session_id: str,
        step: str,
        purpose: str,
        slot_id: str,
    ) -> dict[str, Any] | None:
        asset = self.get_asset(asset_id)
        if not asset:
            return None
        now = _now()
        usage_id = f"usage-{uuid.uuid4().hex}"
        with self._lock, self._connect() as connection:
            connection.execute(
                "INSERT INTO resource_usage(usage_id, resource_kind, resource_id, revision_id, "
                "session_id, step, purpose, slot_id, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(session_id, step, purpose, slot_id, resource_kind, resource_id) DO UPDATE SET "
                "revision_id = excluded.revision_id, updated_at = excluded.updated_at",
                (
                    usage_id,
                    asset["media_kind"],
                    asset_id,
                    asset.get("current_revision_id"),
                    session_id,
                    step,
                    purpose,
                    slot_id,
                    now,
                    now,
                ),
            )
            row = connection.execute(
                "SELECT * FROM resource_usage WHERE session_id = ? AND step = ? "
                "AND purpose = ? AND slot_id = ? AND resource_kind = ? AND resource_id = ?",
                (session_id, step, purpose, slot_id, asset["media_kind"], asset_id),
            ).fetchone()
        return self._row_to_dict(row) if row else None

    def record_external_usage(
        self,
        resource_kind: str,
        resource_id: str,
        session_id: str,
        step: str,
        purpose: str,
        slot_id: str,
        revision_id: str | None = None,
    ) -> dict[str, Any] | None:
        """Record usage for a domain adapter that is not media-backed yet."""
        now = _now()
        usage_id = f"usage-{uuid.uuid4().hex}"
        with self._lock, self._connect() as connection:
            connection.execute(
                "INSERT INTO resource_usage(usage_id, resource_kind, resource_id, revision_id, "
                "session_id, step, purpose, slot_id, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(session_id, step, purpose, slot_id, resource_kind, resource_id) DO UPDATE SET "
                "revision_id = excluded.revision_id, updated_at = excluded.updated_at",
                (
                    usage_id,
                    resource_kind,
                    resource_id,
                    revision_id,
                    session_id,
                    step,
                    purpose,
                    slot_id,
                    now,
                    now,
                ),
            )
            row = connection.execute(
                "SELECT * FROM resource_usage WHERE session_id = ? AND step = ? "
                "AND purpose = ? AND slot_id = ? AND resource_kind = ? AND resource_id = ?",
                (session_id, step, purpose, slot_id, resource_kind, resource_id),
            ).fetchone()
        return self._row_to_dict(row) if row else None

    def reconcile_session_usage(self, session_id: str, references: list[dict[str, Any]]) -> dict[str, int]:
        """Rebuild a session's usage rows from its current state.

        The session is authoritative during migration/recovery.  Rebuilding
        in one transaction removes stale slots (including cancelled choices)
        and upserts the desired set, making the operation safe to repeat.
        """
        desired: dict[tuple[str, str, str, str, str], dict[str, Any]] = {}
        for reference in references:
            kind = str(reference.get("resource_kind") or "").strip()
            resource_id = str(reference.get("resource_id") or "").strip()
            step = str(reference.get("step") or "").strip()
            purpose = str(reference.get("purpose") or "").strip()
            slot_id = str(reference.get("slot_id") or "").strip()
            if not all((kind, resource_id, step, purpose, slot_id)):
                continue
            desired[(step, purpose, slot_id, resource_id, kind)] = {
                "resource_kind": kind,
                "resource_id": resource_id,
                "revision_id": reference.get("revision_id"),
                "step": step,
                "purpose": purpose,
                "slot_id": slot_id,
            }
        now = _now()
        with self._lock, self._connect() as connection:
            connection.execute("DELETE FROM resource_usage WHERE session_id = ?", (session_id,))
            for item in desired.values():
                revision_id = item["revision_id"]
                if not revision_id and item["resource_kind"] in MEDIA_KINDS:
                    row = connection.execute(
                        "SELECT current_revision_id FROM media_assets WHERE asset_id = ?",
                        (item["resource_id"],),
                    ).fetchone()
                    revision_id = row["current_revision_id"] if row else None
                connection.execute(
                    "INSERT INTO resource_usage(usage_id, resource_kind, resource_id, revision_id, session_id, step, purpose, slot_id, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?) ",
                    (f"usage-{uuid.uuid4().hex}", item["resource_kind"], item["resource_id"], revision_id, session_id, item["step"], item["purpose"], item["slot_id"], now, now),
                )
        return {"desired": len(desired), "written": len(desired)}

    def create_snapshot(
        self,
        asset_id: str,
        session_id: str,
        step: str,
        *,
        variant_role: str | None = None,
        template_revision: int | None = None,
        renderer_version: str | None = None,
    ) -> dict[str, Any] | None:
        asset = self.get_asset(asset_id)
        if not asset or not asset.get("current_revision_id"):
            return None
        variant_id = None
        if variant_role:
            variants = [item for item in self.get_variants(asset_id) if item["role"] == variant_role]
            variant_id = variants[0]["variant_id"] if variants else None
        snapshot = {
            "snapshot_id": f"snapshot-{uuid.uuid4().hex}",
            "resource_kind": asset["media_kind"],
            "resource_id": asset_id,
            "revision_id": asset["current_revision_id"],
            "variant_id": variant_id,
            "sha256": asset.get("sha256"),
            "resolved_relative_path": asset.get("relative_path"),
            "template_revision": template_revision,
            "renderer_version": renderer_version,
            "metadata_json": "{}",
            "session_id": session_id,
            "step": step,
            "created_at": _now(),
        }
        with self._lock, self._connect() as connection:
            connection.execute(
                "INSERT INTO resource_snapshots(snapshot_id, resource_kind, resource_id, revision_id, "
                "variant_id, sha256, resolved_relative_path, template_revision, renderer_version, metadata_json, "
                "session_id, step, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                tuple(snapshot.values()),
            )
        return snapshot

    def create_external_snapshot(
        self,
        resource_kind: str,
        resource_id: str,
        session_id: str,
        step: str,
        *,
        revision_id: str | None = None,
        resolved_relative_path: str | None = None,
        template_revision: int | None = None,
        renderer_version: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Pin a non-media domain resource at a render boundary."""
        snapshot = {
            "snapshot_id": f"snapshot-{uuid.uuid4().hex}",
            "resource_kind": resource_kind,
            "resource_id": resource_id,
            "revision_id": revision_id,
            "variant_id": None,
            "sha256": None,
            "resolved_relative_path": resolved_relative_path,
            "template_revision": template_revision,
            "renderer_version": renderer_version,
            "metadata_json": json.dumps(metadata or {}, ensure_ascii=False, sort_keys=True),
            "session_id": session_id,
            "step": step,
            "created_at": _now(),
        }
        with self._lock, self._connect() as connection:
            connection.execute(
                "INSERT INTO resource_snapshots(snapshot_id, resource_kind, resource_id, revision_id, variant_id, sha256, resolved_relative_path, template_revision, renderer_version, metadata_json, session_id, step, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                tuple(snapshot.values()),
            )
        return snapshot

    def get_template_revision(self, template_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM template_definitions WHERE template_id = ? ORDER BY revision DESC LIMIT 1",
                (template_id,),
            ).fetchone()
        return self._row_to_dict(row) if row else None

    def domain_snapshot_metadata(self, resource_kind: str, resource_id: str) -> dict[str, Any]:
        if resource_kind == "template":
            template = self.get_template_revision(resource_id)
            return template or {}
        if resource_kind == "brand":
            with self._connect() as connection:
                row = connection.execute("SELECT * FROM brand_kits_v2 WHERE brand_id = ?", (resource_id,)).fetchone()
            payload = dict(row) if row else {}
            revisions = self.list_domain_revisions(resource_kind, resource_id)
            payload["domain_revision"] = revisions[0]["revision"] if revisions else 1
            return payload
        if resource_kind == "digital_human":
            item = self.get_domain_item("digital_human", resource_id) or {}
            revisions = self.list_domain_revisions(resource_kind, resource_id)
            return {"profile": item, "scenes": item.get("scenes") or [], "domain_revision": revisions[0]["revision"] if revisions else 1}
        if resource_kind == "digital_human_scene":
            return self.get_digital_human_scene(resource_id) or {}
        if resource_kind == "voice":
            asset = self.get_asset(resource_id) or self.get_asset_by_legacy_id("audio", resource_id)
            return {"asset_id": asset.get("asset_id"), "revision_id": asset.get("current_revision_id"), "sha256": asset.get("sha256")} if asset else {}
        return {}

    def list_usage(self, session_id: str) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM resource_usage WHERE session_id = ? ORDER BY updated_at DESC",
                (session_id,),
            ).fetchall()
        return [self._row_to_dict(row) for row in rows]

    def list_resource_usage(self, resource_kind: str, resource_id: str) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM resource_usage WHERE resource_kind = ? AND resource_id = ? ORDER BY updated_at DESC",
                (resource_kind, resource_id),
            ).fetchall()
        return [self._row_to_dict(row) for row in rows]

    def recent_resource_keys(self, limit: int = 500) -> list[tuple[str, str]]:
        limit = max(1, min(limit, 5000))
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT resource_kind, resource_id, MAX(updated_at) AS last_used "
                "FROM resource_usage GROUP BY resource_kind, resource_id "
                "ORDER BY last_used DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [(str(row["resource_kind"]), str(row["resource_id"])) for row in rows]

    def list_snapshots(self, session_id: str) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM resource_snapshots WHERE session_id = ? ORDER BY created_at DESC",
                (session_id,),
            ).fetchall()
        return [self._row_to_dict(row) for row in rows]

    def get_revision_path(
        self,
        asset_id: str,
        variant_role: str | None = None,
        revision_id: str | None = None,
    ) -> Path | None:
        if revision_id:
            with self._connect() as connection:
                row = connection.execute(
                    "SELECT relative_path FROM asset_revisions "
                    "WHERE asset_id = ? AND revision_id = ?",
                    (asset_id, revision_id),
                ).fetchone()
            if not row:
                return None
            relative_path = row["relative_path"]
        else:
            row = self._asset_row(asset_id)
            if not row:
                return None
            relative_path = row["relative_path"]
        if variant_role:
            with self._connect() as connection:
                variant = connection.execute(
                    "SELECT v.relative_path FROM asset_variants v JOIN asset_revisions r "
                    "ON r.revision_id = v.revision_id WHERE r.asset_id = ? AND v.role = ? "
                    "ORDER BY r.version DESC LIMIT 1",
                    (asset_id, variant_role),
                ).fetchone()
            relative_path = variant["relative_path"] if variant else None
        if not relative_path:
            return None
        path = _safe_relative_path(self.data_root, relative_path)
        return path if path.is_file() else None

    def patch_asset(self, asset_id: str, name: str | None = None, description: str | None = None) -> dict[str, Any] | None:
        if name is None and description is None:
            return self.get_asset(asset_id)
        updates: list[str] = []
        values: list[Any] = []
        if name is not None:
            updates.append("name = ?")
            values.append(name.strip() or "未命名素材")
        if description is not None:
            updates.append("description = ?")
            values.append(description)
        updates.append("updated_at = ?")
        values.extend([_now(), asset_id])
        with self._lock, self._connect() as connection:
            cursor = connection.execute(
                f"UPDATE media_assets SET {', '.join(updates)} WHERE asset_id = ?", values
            )
            if cursor.rowcount == 0:
                return None
        return self.get_asset(asset_id)

    def archive_asset(self, asset_id: str) -> bool:
        with self._lock, self._connect() as connection:
            cursor = connection.execute(
                "UPDATE media_assets SET status = 'archived', archived_at = ?, updated_at = ? "
                "WHERE asset_id = ? AND status <> 'archived'",
                (_now(), _now(), asset_id),
            )
            return cursor.rowcount > 0

    def restore_asset(self, asset_id: str) -> bool:
        with self._lock, self._connect() as connection:
            cursor = connection.execute(
                "UPDATE media_assets SET status = CASE WHEN current_revision_id IS NULL THEN 'warning' ELSE 'ready' END, archived_at = NULL, updated_at = ? WHERE asset_id = ? AND status = 'archived'",
                (_now(), asset_id),
            )
            return cursor.rowcount > 0

    def activate_revision(self, asset_id: str, revision_id: str) -> dict[str, Any] | None:
        with self._lock, self._connect() as connection:
            revision = connection.execute(
                "SELECT revision_id FROM asset_revisions WHERE asset_id = ? AND revision_id = ?",
                (asset_id, revision_id),
            ).fetchone()
            if not revision:
                return None
            connection.execute(
                "UPDATE media_assets SET current_revision_id = ?, status = 'ready', archived_at = NULL, updated_at = ? WHERE asset_id = ?",
                (revision_id, _now(), asset_id),
            )
        return self.get_asset(asset_id)

    def retry_analysis(self, asset_id: str, revision_id: str | None = None) -> dict[str, Any] | None:
        asset = self.get_asset(asset_id)
        if not asset:
            return None
        selected_revision = revision_id or str(asset.get("current_revision_id") or "")
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM asset_revisions WHERE asset_id = ? AND revision_id = ?",
                (asset_id, selected_revision),
            ).fetchone()
        if not row:
            return None
        source = _safe_relative_path(self.data_root, row["relative_path"])
        if not source.is_file():
            return None
        metadata = self._inspect_media(source, asset["media_kind"], {})
        with self._lock, self._connect() as connection:
            connection.execute(
                "UPDATE asset_revisions SET mime_type = ?, bytes = ?, sha256 = ?, width = ?, height = ?, aspect_ratio = ?, duration_ms = ?, frame_rate = ?, has_audio = ?, has_transparency = ? WHERE revision_id = ?",
                (_mime_type(source.name), source.stat().st_size, _sha256(source), metadata.get("width"), metadata.get("height"), metadata.get("aspect_ratio"), metadata.get("duration_ms"), metadata.get("frame_rate"), int(metadata.get("has_audio", False)), int(metadata.get("has_transparency", False)), selected_revision),
            )
            connection.execute(
                "UPDATE media_assets SET status = ?, updated_at = ? WHERE asset_id = ?",
                ("ready" if metadata.get("valid") else "warning", _now(), asset_id),
            )
        return self.get_asset(asset_id)

    def create_revision_from_path(self, asset_id: str, filename: str, temporary: Path, *, allow_duplicate: bool = False) -> dict[str, Any] | None:
        asset = self.get_asset(asset_id)
        if not asset or not temporary.is_file():
            return None
        _validate_media_filename(str(asset["media_kind"]), filename)
        digest = _sha256(temporary)
        with self._lock, self._connect() as connection:
            duplicate = connection.execute(
                "SELECT revision_id FROM asset_revisions WHERE asset_id = ? AND sha256 = ?",
                (asset_id, digest),
            ).fetchone()
            if duplicate and not allow_duplicate:
                temporary.unlink(missing_ok=True)
                return self.get_asset(asset_id)
            row = connection.execute("SELECT COALESCE(MAX(version), 0) AS version FROM asset_revisions WHERE asset_id = ?", (asset_id,)).fetchone()
            version = int(row["version"] or 0) + 1
            revision_id = f"revision-{uuid.uuid4().hex}"
            extension = _extension(filename) or "bin"
            relative_path = f"asset_library/media/{asset_id}/v{version}/original.{extension}"
            destination = _safe_relative_path(self.data_root, relative_path)
            destination.parent.mkdir(parents=True, exist_ok=True)
            os.replace(temporary, destination)
            metadata = self._inspect_media(destination, asset["media_kind"], {})
            now = _now()
            try:
                connection.execute(
                    "INSERT INTO asset_revisions(revision_id, asset_id, version, parent_revision_id, relative_path, mime_type, bytes, sha256, width, height, aspect_ratio, duration_ms, frame_rate, has_audio, has_transparency, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (revision_id, asset_id, version, asset.get("current_revision_id"), relative_path, _mime_type(filename), destination.stat().st_size, digest, metadata.get("width"), metadata.get("height"), metadata.get("aspect_ratio"), metadata.get("duration_ms"), metadata.get("frame_rate"), int(metadata.get("has_audio", False)), int(metadata.get("has_transparency", False)), now),
                )
                self._ensure_variant_locked(connection, asset_id, revision_id, destination, asset["media_kind"])
                connection.execute("UPDATE media_assets SET current_revision_id = ?, status = ?, updated_at = ? WHERE asset_id = ?", (revision_id, "ready" if metadata.get("valid") else "warning", now, asset_id))
            except Exception:
                destination.unlink(missing_ok=True)
                raise
        return self.get_asset(asset_id)

    def create_upload_session(
        self,
        filename: str,
        declared_bytes: int,
        target_kind: str,
        name: str | None = None,
        description: str = "",
        *,
        decision_mode: str = "auto",
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        clean_filename = _safe_filename(filename)
        if target_kind not in UPLOADABLE_MEDIA_KINDS:
            raise ValueError("Upload supports image, video and audio assets only")
        _validate_media_filename(target_kind, clean_filename)
        if declared_bytes < 0 or declared_bytes > self.max_upload_size:
            raise ValueError("Upload exceeds configured size limit")
        upload_id = f"upload-{uuid.uuid4().hex}"
        temp_relative_path = f"asset_library/incoming/{upload_id}.part"
        with self._lock, self._connect() as connection:
            if idempotency_key:
                existing = connection.execute(
                    "SELECT * FROM upload_sessions WHERE idempotency_key = ?",
                    (idempotency_key,),
                ).fetchone()
                if existing:
                    return self._row_to_dict(existing)
            connection.execute(
                "INSERT INTO upload_sessions(upload_id, filename, declared_bytes, target_kind, name, "
                "description, status, temp_relative_path, decision_mode, idempotency_key, expires_at, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, 'created', ?, ?, ?, ?, ?, ?)",
                (
                    upload_id,
                    clean_filename,
                    declared_bytes,
                    target_kind,
                    name.strip() if name else None,
                    description,
                    temp_relative_path,
                    decision_mode,
                    idempotency_key,
                    None,
                    _now(),
                    _now(),
                ),
            )
        temporary = _safe_relative_path(self.data_root, temp_relative_path)
        temporary.parent.mkdir(parents=True, exist_ok=True)
        temporary.touch()
        return self.get_upload_session(upload_id) or {}

    def complete_upload_content(self, upload_id: str) -> dict[str, Any]:
        """Close the byte stream without making a duplicate decision."""
        session = self.get_upload_session(upload_id)
        if not session:
            raise KeyError("Upload session not found")
        if session.get("decision_mode") != "deferred":
            return self.finalize_upload(upload_id)
        if session.get("status") in {"awaiting_duplicate_decision", "uploaded", "finalized", "ready"}:
            return session
        if session["status"] not in {"created", "uploading"}:
            raise ValueError("Upload session is no longer writable")
        if int(session["received_bytes"]) != int(session["declared_bytes"]):
            self.fail_upload(upload_id, "incomplete", "Received bytes do not match declared bytes")
            raise ValueError("Incomplete upload")
        temporary = _safe_relative_path(self.data_root, session["temp_relative_path"])
        if not temporary.is_file():
            self.fail_upload(upload_id, "missing_temp_file", "Upload temporary file is missing")
            raise FileNotFoundError("Upload temporary file is missing")
        digest = _sha256(temporary)
        with self._lock, self._connect() as connection:
            duplicate = connection.execute(
                "SELECT r.asset_id FROM asset_revisions r "
                "JOIN media_assets a ON a.asset_id = r.asset_id "
                "WHERE r.sha256 = ? AND a.media_kind = ? AND a.status <> 'archived' "
                "ORDER BY r.created_at LIMIT 1",
                (digest, session["target_kind"]),
            ).fetchone()
            next_status = "awaiting_duplicate_decision" if duplicate else "uploaded"
            connection.execute(
                "UPDATE upload_sessions SET status = ?, duplicate_asset_id = ?, sha256 = ?, expires_at = ?, updated_at = ? WHERE upload_id = ?",
                (next_status, duplicate["asset_id"] if duplicate else None, digest, (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat(), _now(), upload_id),
            )
        return self.get_upload_session(upload_id) or {}

    def get_upload_session(self, upload_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM upload_sessions WHERE upload_id = ?", (upload_id,)
            ).fetchone()
        return self._row_to_dict(row) if row else None

    def append_upload_chunk(self, upload_id: str, chunk: bytes) -> dict[str, Any]:
        if not chunk:
            return self.get_upload_session(upload_id) or {}
        session = self.get_upload_session(upload_id)
        if not session:
            raise KeyError("Upload session not found")
        if session["status"] not in {"created", "uploading"}:
            raise ValueError("Upload session is no longer writable")
        received = int(session["received_bytes"]) + len(chunk)
        if received > self.max_upload_size or received > int(session["declared_bytes"]):
            self.fail_upload(upload_id, "size_limit", "Upload exceeds declared or configured size")
            raise ValueError("Upload exceeds declared or configured size")
        temporary = _safe_relative_path(self.data_root, session["temp_relative_path"])
        with temporary.open("ab") as handle:
            handle.write(chunk)
        with self._lock, self._connect() as connection:
            connection.execute(
                "UPDATE upload_sessions SET received_bytes = ?, status = 'uploading', updated_at = ? "
                "WHERE upload_id = ?",
                (received, _now(), upload_id),
            )
        return self.get_upload_session(upload_id) or {}

    def finalize_upload(self, upload_id: str) -> dict[str, Any]:
        session = self.get_upload_session(upload_id)
        if not session:
            raise KeyError("Upload session not found")
        if session.get("finalize_result_json"):
            return session
        if session.get("decision_mode") == "deferred" and session["status"] in {"created", "uploading"}:
            self.complete_upload_content(upload_id)
            session = self.get_upload_session(upload_id) or session
        allowed_statuses = {"created", "uploading"}
        if session.get("decision_mode") == "deferred":
            allowed_statuses.update({"awaiting_duplicate_decision", "uploaded"})
        if session["status"] not in allowed_statuses:
            raise ValueError("Upload session is not finalizable")
        if int(session["received_bytes"]) != int(session["declared_bytes"]):
            self.fail_upload(upload_id, "incomplete", "Received bytes do not match declared bytes")
            raise ValueError("Incomplete upload")
        temporary = _safe_relative_path(self.data_root, session["temp_relative_path"])
        if not temporary.is_file():
            self.fail_upload(upload_id, "missing_temp_file", "Upload temporary file is missing")
            raise FileNotFoundError("Upload temporary file is missing")
        digest = _sha256(temporary)
        duplicate_policy = str(session.get("duplicate_policy") or "reuse_existing")
        with self._lock, self._connect() as connection:
            duplicate_query = (
                "SELECT r.asset_id FROM asset_revisions r "
                "JOIN media_assets a ON a.asset_id = r.asset_id "
                "WHERE r.sha256 = ? AND a.media_kind = ? "
                + ("AND a.asset_id = ? " if duplicate_policy == "attach_revision" and session.get("duplicate_asset_id") else "")
                + "ORDER BY r.created_at LIMIT 1"
            )
            duplicate_params: tuple[Any, ...] = (digest, session["target_kind"])
            if duplicate_policy == "attach_revision" and session.get("duplicate_asset_id"):
                duplicate_params += (str(session["duplicate_asset_id"]),)
            duplicate = connection.execute(duplicate_query, duplicate_params).fetchone()
            if duplicate_policy == "attach_revision" and not duplicate:
                raise ValueError("Target asset does not contain the uploaded revision content")
            if duplicate and duplicate_policy == "reuse_existing":
                temporary.unlink(missing_ok=True)
                connection.execute(
                    "UPDATE upload_sessions SET status = 'ready', duplicate_asset_id = ?, "
                    "finalize_result_json = ?, updated_at = ? WHERE upload_id = ?",
                    (duplicate["asset_id"], json.dumps({"policy": duplicate_policy, "asset_id": duplicate["asset_id"]}), _now(), upload_id),
                )
                # The session is read through a separate connection below;
                # commit before returning the updated projection.
                connection.commit()
                result = self.get_upload_session(upload_id) or {}
                result["duplicate_asset_id"] = duplicate["asset_id"]
                return result

            if duplicate and duplicate_policy == "attach_revision":
                connection.commit()
                self.create_revision_from_path(duplicate["asset_id"], session["filename"], temporary, allow_duplicate=True)
                with self._lock, self._connect() as finalize_connection:
                    finalize_connection.execute(
                        "UPDATE upload_sessions SET status = 'finalized', asset_id = ?, duplicate_asset_id = ?, "
                        "finalize_result_json = ?, updated_at = ? WHERE upload_id = ?",
                        (duplicate["asset_id"], duplicate["asset_id"], json.dumps({"policy": duplicate_policy, "asset_id": duplicate["asset_id"]}), _now(), upload_id),
                    )
                result = self.get_upload_session(upload_id) or {}
                result["asset_id"] = duplicate["asset_id"]
                result["duplicate_asset_id"] = duplicate["asset_id"]
                return result

            asset_id = f"media-{uuid.uuid4().hex}"
            revision_id = f"revision-{uuid.uuid4().hex}"
            extension = _extension(session["filename"]) or "bin"
            relative_path = f"asset_library/media/{asset_id}/v1/original.{extension}"
            destination = _safe_relative_path(self.data_root, relative_path)
            destination.parent.mkdir(parents=True, exist_ok=True)
            os.replace(temporary, destination)
            metadata = self._inspect_media(destination, session["target_kind"], {})
            status = "ready" if metadata["valid"] else "warning"
            now = _now()
            try:
                connection.execute(
                    "INSERT INTO media_assets(asset_id, media_kind, name, description, source, "
                    "current_revision_id, status, created_at, updated_at) VALUES (?, ?, ?, ?, 'upload', ?, ?, ?, ?)",
                    (
                        asset_id,
                        session["target_kind"],
                        session["name"] or Path(session["filename"]).stem,
                        session["description"],
                        revision_id,
                        status,
                        now,
                        now,
                    ),
                )
                connection.execute(
                    "INSERT INTO asset_revisions(revision_id, asset_id, version, relative_path, "
                    "mime_type, bytes, sha256, width, height, aspect_ratio, duration_ms, frame_rate, "
                    "has_audio, has_transparency, created_at) VALUES (?, ?, 1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        revision_id,
                        asset_id,
                        relative_path,
                        _mime_type(session["filename"]),
                        destination.stat().st_size,
                        digest,
                        metadata.get("width"),
                        metadata.get("height"),
                        metadata.get("aspect_ratio"),
                        metadata.get("duration_ms"),
                        metadata.get("frame_rate"),
                        int(metadata.get("has_audio", False)),
                        int(metadata.get("has_transparency", False)),
                        now,
                    ),
                )
                self._ensure_variant_locked(connection, asset_id, revision_id, destination, session["target_kind"])
                connection.execute(
                    "INSERT INTO media_jobs(job_id, asset_id, kind, status, created_at, updated_at) VALUES (?, ?, 'metadata', ?, ?, ?)",
                    (f"job-{uuid.uuid4().hex}", asset_id, "completed" if metadata.get("valid") else "warning", now, now),
                )
                connection.execute(
                    "UPDATE upload_sessions SET status = ?, asset_id = ?, updated_at = ?, "
                    "finalize_result_json = ? WHERE upload_id = ?",
                    ("finalized" if session.get("decision_mode") == "deferred" else "ready", asset_id, now, json.dumps({"policy": duplicate_policy, "asset_id": asset_id}), upload_id),
                )
            except Exception:
                destination.unlink(missing_ok=True)
                raise
        return self.get_upload_session(upload_id) or {}

    def finalize_deferred_upload(
        self,
        upload_id: str,
        duplicate_policy: str | None = None,
        *,
        target_asset_id: str | None = None,
    ) -> dict[str, Any]:
        session = self.get_upload_session(upload_id)
        if not session:
            raise KeyError("Upload session not found")
        if session.get("decision_mode") != "deferred":
            raise ValueError("Upload session is not deferred")
        if session.get("finalize_result_json"):
            return session
        if session.get("status") not in {"awaiting_duplicate_decision", "uploaded"}:
            raise ValueError("Upload content must be completed before finalize")
        if session.get("status") == "awaiting_duplicate_decision":
            if duplicate_policy not in {"reuse_existing", "attach_revision", "create_separate"}:
                raise ValueError("Duplicate policy is required for an existing asset")
        else:
            # A unique upload has no decision dialog.  The server still keeps
            # the finalize operation explicit and idempotent.
            duplicate_policy = duplicate_policy or "create_separate"
        if duplicate_policy not in {"reuse_existing", "attach_revision", "create_separate"}:
            raise ValueError("Unsupported duplicate policy")
        if duplicate_policy == "attach_revision" and not target_asset_id:
            raise ValueError("attach_revision requires target_asset_id")
        if target_asset_id and duplicate_policy == "attach_revision":
            with self._connect() as connection:
                target = connection.execute(
                    "SELECT a.asset_id, a.media_kind FROM media_assets a WHERE a.asset_id = ?",
                    (target_asset_id,),
                ).fetchone()
            if not target or target["media_kind"] != session["target_kind"]:
                raise ValueError("Target asset does not match the uploaded media kind")
            session["duplicate_asset_id"] = target_asset_id
        with self._lock, self._connect() as connection:
            connection.execute(
                "UPDATE upload_sessions SET duplicate_policy = ?, duplicate_asset_id = COALESCE(?, duplicate_asset_id), updated_at = ? WHERE upload_id = ?",
                (duplicate_policy, target_asset_id if duplicate_policy == "attach_revision" else None, _now(), upload_id),
            )
        return self.finalize_upload(upload_id)

    def fail_upload(self, upload_id: str, error_code: str, error_message: str) -> None:
        session = self.get_upload_session(upload_id)
        if session:
            temporary = _safe_relative_path(self.data_root, session["temp_relative_path"])
            temporary.unlink(missing_ok=True)
        with self._lock, self._connect() as connection:
            connection.execute(
                "UPDATE upload_sessions SET status = 'failed', error_code = ?, error_message = ?, updated_at = ? "
                "WHERE upload_id = ?",
                (error_code, error_message, _now(), upload_id),
            )

    def cancel_upload(self, upload_id: str) -> bool:
        session = self.get_upload_session(upload_id)
        if not session:
            return False
        temporary = _safe_relative_path(self.data_root, session["temp_relative_path"])
        temporary.unlink(missing_ok=True)
        with self._lock, self._connect() as connection:
            cursor = connection.execute(
                "UPDATE upload_sessions SET status = 'cancelled', updated_at = ? "
                "WHERE upload_id = ? AND status IN ('created', 'uploading')",
                (_now(), upload_id),
            )
            return cursor.rowcount > 0

    def migration_report(self) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT report_json FROM migration_runs ORDER BY created_at DESC LIMIT 1"
            ).fetchone()
        return json.loads(row["report_json"]) if row else None
