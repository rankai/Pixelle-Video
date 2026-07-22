"""Stage-0 baseline and rollback helpers for the asset-library migration.

The baseline is intentionally read-only with respect to the data directory.
It records manifest checksums, legacy IDs and referenced file checksums so a
future migration can prove that it did not lose or move user data.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

BASELINE_SCHEMA_VERSION = "asset-library-stage0-baseline-v1"

MANIFEST_SPECS: tuple[dict[str, Any], ...] = (
    {
        "resource_kind": "video",
        "manifest": "video_assets/overlay/video_assets.json",
        "id_fields": ("asset_id",),
        "file_fields": ("filename", "thumbnail_filename"),
    },
    {
        "resource_kind": "image",
        "manifest": "image_assets/image_assets.json",
        "id_fields": ("asset_id",),
        "file_fields": ("filename",),
    },
    {
        "resource_kind": "digital_human",
        "manifest": "portraits/portraits.json",
        "id_fields": ("portrait_id",),
        "file_fields": ("filename",),
    },
    {
        "resource_kind": "voice",
        "manifest": "voice_references/voice_references.json",
        "id_fields": ("reference_id",),
        "file_fields": ("filename",),
    },
    {
        "resource_kind": "brand",
        "manifest": "brand_kits/brand_kits.json",
        "id_fields": ("brand_id",),
        "file_fields": ("logo_filename", "default_bgm_filename"),
    },
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_child(parent: Path, filename: str) -> Path | None:
    if not filename or filename != Path(filename).name:
        return None
    candidate = (parent / filename).resolve()
    try:
        candidate.relative_to(parent.resolve())
    except ValueError:
        return None
    return candidate


def _safe_relative_child(root: Path, relative_path: str) -> Path | None:
    relative = Path(relative_path)
    if relative.is_absolute():
        return None
    candidate = (root / relative).resolve()
    try:
        candidate.relative_to(root.resolve())
    except ValueError:
        return None
    return candidate


def _relative(path: Path, root: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def _empty_manifest_entry(resource_kind: str, relative_path: str) -> dict[str, Any]:
    return {
        "resource_kind": resource_kind,
        "relative_path": relative_path,
        "exists": False,
        "sha256": None,
        "record_count": 0,
        "legacy_ids": [],
        "referenced_files": [],
        "referenced_file_checksums": {},
    }


def collect_baseline(data_root: str | Path) -> dict[str, Any]:
    """Collect a deterministic, read-only baseline for legacy manifests."""

    root = Path(data_root).resolve()
    manifests: list[dict[str, Any]] = []
    missing_files: list[str] = []

    for spec in MANIFEST_SPECS:
        manifest_path = root / spec["manifest"]
        entry = _empty_manifest_entry(spec["resource_kind"], spec["manifest"])
        if not manifest_path.is_file():
            manifests.append(entry)
            continue

        entry["exists"] = True
        entry["sha256"] = _sha256(manifest_path)
        try:
            payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            entry["error"] = f"invalid_manifest:{type(exc).__name__}"
            manifests.append(entry)
            continue

        records = payload if isinstance(payload, list) else []
        entry["record_count"] = len(records)
        entry["legacy_ids"] = [
            str(value)
            for record in records
            if isinstance(record, dict)
            for field in spec["id_fields"]
            if (value := record.get(field))
        ]

        referenced: list[str] = []
        checksums: dict[str, str | None] = {}
        for record in records:
            if not isinstance(record, dict):
                continue
            for field in spec["file_fields"]:
                filename = record.get(field)
                if not filename:
                    continue
                child = _safe_child(manifest_path.parent, str(filename))
                if child is None:
                    invalid_key = f"invalid:{field}:{filename}"
                    referenced.append(invalid_key)
                    checksums[invalid_key] = None
                    continue
                relative = _relative(child, root)
                referenced.append(relative)
                if not child.is_file():
                    missing_files.append(relative)
                    checksums[relative] = None
                else:
                    checksums[relative] = _sha256(child)
        entry["referenced_files"] = sorted(set(referenced))
        entry["referenced_file_checksums"] = {
            relative: checksums.get(relative)
            for relative in sorted(set(referenced))
        }
        manifests.append(entry)

    return {
        "schema_version": BASELINE_SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "data_root_name": root.name,
        "manifests": manifests,
        "missing_files": sorted(set(missing_files)),
        "rollback": {
            "original_files_untouched": True,
            "manifest_backup_required": True,
            "migration_is_transactional": True,
            "restore_strategy": "restore manifest backup and keep original media files",
        },
    }


def backup_manifests(data_root: str | Path, backup_root: str | Path) -> list[dict[str, str]]:
    """Copy legacy manifests to a rollback directory without changing source data."""

    root = Path(data_root).resolve()
    destination_root = Path(backup_root).resolve()
    copied: list[dict[str, str]] = []
    for spec in MANIFEST_SPECS:
        source = root / spec["manifest"]
        if not source.is_file():
            continue
        destination = destination_root / spec["manifest"]
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        copied.append(
            {
                "relative_path": spec["manifest"],
                "sha256": _sha256(destination),
            }
        )

    destination_root.mkdir(parents=True, exist_ok=True)
    index = destination_root / "manifest-backup-index.json"
    index.write_text(
        json.dumps(
            {
                "schema_version": BASELINE_SCHEMA_VERSION,
                "source_root_name": root.name,
                "copied": copied,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return copied


def restore_manifests(data_root: str | Path, backup_root: str | Path) -> list[str]:
    """Restore manifests after verifying the rollback index checksums."""

    root = Path(data_root).resolve()
    source_root = Path(backup_root).resolve()
    index_path = source_root / "manifest-backup-index.json"
    if not index_path.is_file():
        raise FileNotFoundError(f"Rollback index not found: {index_path}")
    index = json.loads(index_path.read_text(encoding="utf-8"))
    restored: list[str] = []
    for item in index.get("copied", []):
        relative_path = str(item["relative_path"])
        backup = _safe_relative_child(source_root, relative_path)
        if backup is None or not backup.is_file():
            raise FileNotFoundError(f"Rollback manifest not found: {relative_path}")
        expected_sha256 = str(item["sha256"])
        actual_sha256 = _sha256(backup)
        if actual_sha256 != expected_sha256:
            raise ValueError(f"Rollback checksum mismatch: {relative_path}")
        destination = root / relative_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(backup, destination)
        restored.append(relative_path)
    return restored


def write_baseline(output_path: str | Path, baseline: dict[str, Any]) -> None:
    """Atomically write a baseline report."""

    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f".{destination.name}.tmp")
    temporary.write_text(
        json.dumps(baseline, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, destination)
