"""Read-only VoiceProfile migration planner used by the UX-0 gate."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_asset_key(value: str) -> str:
    clean = re.sub(r"[^A-Za-z0-9._-]", "_", value).strip("._-") or "asset"
    if clean != value:
        clean = f"{clean[:48]}-{hashlib.sha256(value.encode('utf-8')).hexdigest()[:8]}"
    return clean


def _load_json_list(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    return [item for item in payload if isinstance(item, dict)] if isinstance(payload, list) else []


def _session_voice_references(session_root: Path | None) -> list[dict[str, str]]:
    if session_root is None or not session_root.is_dir():
        return []
    references: list[dict[str, str]] = []
    for path in sorted(session_root.glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            continue
        state = payload.get("state") if isinstance(payload, dict) else None
        state = state if isinstance(state, dict) else payload if isinstance(payload, dict) else {}
        reference_id = str(state.get("tts_ref_audio_id") or state.get("voice_id") or "").strip()
        if reference_id:
            references.append({"session_id": str(payload.get("session_id") or path.stem), "voice_id": reference_id})
    return references


def dry_run_voice_profile_migration(
    data_root: str | Path,
    *,
    session_root: str | Path | None = None,
    ordinary_audio_manifest: str | Path | None = None,
) -> dict[str, Any]:
    """Plan VoiceProfile rows without changing manifests, SQLite or media files."""

    root = Path(data_root).resolve()
    manifest_path = root / "voice_references" / "voice_references.json"
    # The direct-file fallback keeps small review fixtures easy to inspect;
    # production data uses the namespaced path above.
    if not manifest_path.is_file() and (root / "voice_references.json").is_file():
        manifest_path = root / "voice_references.json"
    records = _load_json_list(manifest_path)
    candidates: list[dict[str, Any]] = []
    invalid_records: list[dict[str, str]] = []
    for record in records:
        legacy_id = str(record.get("reference_id") or "").strip()
        filename = str(record.get("filename") or "").strip()
        if not legacy_id or not filename or Path(filename).name != filename:
            invalid_records.append({"reference_id": legacy_id, "reason": "invalid_id_or_filename"})
            continue
        source = manifest_path.parent / filename
        source_exists = source.is_file()
        asset_key = _safe_asset_key(legacy_id)
        candidates.append(
            {
                "voice_id": legacy_id,
                "legacy_reference_id": legacy_id,
                "name": str(record.get("name") or Path(filename).stem),
                "audio_asset_id": f"media-audio-{asset_key}",
                "audio_revision_id": f"revision-audio-{asset_key}-1",
                "source_relative_path": f"voice_references/{filename}",
                "source_sha256": _sha256(source) if source_exists else None,
                "source_exists": source_exists,
                "production_reference_preserved": True,
            }
        )

    by_voice_id = {item["voice_id"]: item for item in candidates}
    session_refs = _session_voice_references(Path(session_root).resolve() if session_root else None)
    resolved_refs = [
        {
            **reference,
            "resolved_voice_id": reference["voice_id"] if reference["voice_id"] in by_voice_id else None,
            "resolvable": reference["voice_id"] in by_voice_id and by_voice_id[reference["voice_id"]]["source_exists"],
        }
        for reference in session_refs
    ]

    ordinary_audio: list[dict[str, Any]] = []
    if ordinary_audio_manifest:
        audio_path = Path(ordinary_audio_manifest).resolve()
        for record in _load_json_list(audio_path):
            resource_id = str(record.get("asset_id") or record.get("audio_id") or "").strip()
            if resource_id and resource_id not in by_voice_id:
                ordinary_audio.append(
                    {
                        "resource_id": resource_id,
                        "name": str(record.get("name") or ""),
                        "excluded_from_voice_profile": True,
                    }
                )

    missing_files = [item["source_relative_path"] for item in candidates if not item["source_exists"]]
    unresolved = [item for item in resolved_refs if not item["resolvable"]]
    return {
        "schema_version": "voice-profile-migration-dry-run-v1",
        "dry_run": True,
        "writes_performed": 0,
        "source": {
            "data_root_name": root.name,
            "manifest": "voice_references/voice_references.json",
            "manifest_sha256": _sha256(manifest_path) if manifest_path.is_file() else None,
            "record_count": len(records),
        },
        "voice_profiles": candidates,
        "invalid_records": invalid_records,
        "ordinary_audio_excluded_from_voice_facet": ordinary_audio,
        "session_reconciliation": {
            "sessions_seen": len(resolved_refs),
            "references_resolved": len(resolved_refs) - len(unresolved),
            "references_unresolved": len(unresolved),
            "unresolved": unresolved,
            "all_references_resolvable": not unresolved,
        },
        "missing_files": missing_files,
        "rollback": {
            "manifest_backup_required": True,
            "voice_profile_rows_are_additive": True,
            "legacy_voice_id_unchanged": True,
            "rollback_action": "disable_voice_profile_projection_and_restore_manifest_backup",
            "media_files_deleted": False,
        },
        "ready_for_review": not invalid_records and not missing_files and not unresolved,
    }


def write_migration_report(output_path: str | Path, report: dict[str, Any]) -> None:
    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f".{destination.name}.tmp")
    temporary.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(destination)


__all__ = ["dry_run_voice_profile_migration", "write_migration_report"]
