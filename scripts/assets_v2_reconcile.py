"""Rebuild V2 resource usage from persisted IP broadcast sessions.

Usage:
  uv run python scripts/assets_v2_reconcile.py [--session-id ID] [--dry-run] [--verbose] [--json]
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

from pixelle_video.services.assets_v2.repository import AssetLibraryRepository
from pixelle_video.services.ip_broadcast_workflow import IpBroadcastSessionStore

BASELINE_KIND_MAP = {
    "image": ("media", "image"),
    "video": ("media", "video"),
    "voice": ("media", "audio"),
    "digital_human": ("profile", "digital_human"),
    "brand": ("brand", "brand"),
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _audit_baseline(repository: AssetLibraryRepository, baseline_path: str) -> dict[str, Any]:
    """Compare migration counts, manifest hashes and referenced file hashes."""

    baseline_file = Path(baseline_path).resolve()
    baseline = json.loads(baseline_file.read_text(encoding="utf-8"))
    data_root = repository.data_root
    report: dict[str, Any] = {
        "baseline": str(baseline_file),
        "manifest_checks": [],
        "resource_checks": [],
        "checksum_mismatches": [],
        "missing_files": [],
    }
    with repository._connect() as connection:
        for entry in baseline.get("manifests", []):
            kind = str(entry.get("resource_kind") or "")
            manifest = data_root / str(entry.get("relative_path") or "")
            expected_manifest_sha = entry.get("sha256")
            actual_manifest_sha = _sha256(manifest) if manifest.is_file() else None
            report["manifest_checks"].append(
                {
                    "resource_kind": kind,
                    "path": str(entry.get("relative_path") or ""),
                    "expected_sha256": expected_manifest_sha,
                    "actual_sha256": actual_manifest_sha,
                    "ok": expected_manifest_sha == actual_manifest_sha,
                }
            )
            table_kind = BASELINE_KIND_MAP.get(kind)
            ids = sorted({str(value) for value in entry.get("legacy_ids", []) if value})
            if not table_kind:
                continue
            table, mapped_kind = table_kind
            if table == "media":
                rows = connection.execute(
                    "SELECT legacy_id FROM media_assets WHERE media_kind = ? AND legacy_id IN (%s)"
                    % ",".join("?" for _ in ids),
                    [mapped_kind, *ids],
                ).fetchall() if ids else []
                migrated_ids = sorted(str(row["legacy_id"]) for row in rows)
            elif table == "profile":
                rows = connection.execute(
                    "SELECT legacy_id FROM digital_human_profiles WHERE legacy_id IN (%s)"
                    % ",".join("?" for _ in ids),
                    ids,
                ).fetchall() if ids else []
                migrated_ids = sorted(str(row["legacy_id"]) for row in rows)
            else:
                rows = connection.execute(
                    "SELECT legacy_id FROM brand_kits_v2 WHERE legacy_id IN (%s)"
                    % ",".join("?" for _ in ids),
                    ids,
                ).fetchall() if ids else []
                migrated_ids = sorted(str(row["legacy_id"]) for row in rows)
            report["resource_checks"].append(
                {
                    "resource_kind": kind,
                    "expected_count": len(ids),
                    "migrated_count": len(migrated_ids),
                    "missing_legacy_ids": sorted(set(ids) - set(migrated_ids)),
                    "ok": len(ids) == len(migrated_ids),
                }
            )
            for relative_path, expected_sha in (entry.get("referenced_file_checksums") or {}).items():
                if not expected_sha:
                    continue
                file_path = data_root / str(relative_path)
                if not file_path.is_file():
                    report["missing_files"].append(str(relative_path))
                    continue
                actual_sha = _sha256(file_path)
                if actual_sha != expected_sha:
                    report["checksum_mismatches"].append(
                        {"path": str(relative_path), "expected": expected_sha, "actual": actual_sha}
                    )
    report["ok"] = not (
        report["missing_files"]
        or report["checksum_mismatches"]
        or any(not item["ok"] for item in report["manifest_checks"] + report["resource_checks"])
    )
    return report


def _references(session: Any) -> list[dict[str, str]]:
    state = session.state
    refs: list[dict[str, str]] = []
    for kind, key, step, purpose, slot in (
        ("voice", "tts_ref_audio_id", "voice", "reference", "voice-reference"),
        ("digital_human", "portrait_id", "digital_human", "portrait", "digital-human"),
        ("digital_human_scene", "digital_human_scene_id", "digital_human", "scene", "digital-human-scene"),
        ("brand", "brand_kit_id", "postproduction", "brand_kit", "brand"),
        ("template", "template_id", "postproduction", "template", "template"),
    ):
        resource_id = str(state.get(key) or "").strip()
        if resource_id:
            refs.append({"resource_kind": kind, "resource_id": resource_id, "step": step, "purpose": purpose, "slot_id": slot})
    groups = state.get("visual_groups") if isinstance(state.get("visual_groups"), list) else []
    for index, group in enumerate(groups, start=1):
        if not isinstance(group, dict) or group.get("visual_type") != "uploaded_video":
            continue
        resource_id = str(group.get("video_asset_id") or "").strip()
        if resource_id:
            refs.append({"resource_kind": "video", "resource_id": resource_id, "step": "postproduction", "purpose": "overlay_video", "slot_id": str(group.get("group_id") or f"overlay-{index}")})
    return refs


def main() -> int:
    parser = argparse.ArgumentParser(description="Reconcile V2 asset usage from IP broadcast sessions")
    parser.add_argument("--session-id")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--verbose", action="store_true", help="Print one line per session")
    parser.add_argument("--json", action="store_true", help="Print a machine-readable summary")
    parser.add_argument("--baseline", help="Also audit manifest/resource/file checksums against a Stage-0 baseline JSON")
    args = parser.parse_args()
    store = IpBroadcastSessionStore()
    repository = AssetLibraryRepository()
    sessions = [store.get_session(args.session_id)] if args.session_id else list(store._sessions.values())
    summary: dict[str, Any] = {
        "dry_run": args.dry_run,
        "session_filter": args.session_id,
        "sessions_seen": len(sessions),
        "sessions_processed": 0,
        "sessions_skipped": 0,
        "sessions_failed": 0,
        "desired_usage_rows": 0,
        "written_usage_rows": 0,
        "references_by_kind": Counter(),
        "failures": [],
    }
    for session in sessions:
        if session is None:
            summary["sessions_skipped"] += 1
            continue
        try:
            refs = _references(session)
            result = {"desired": len(refs), "written": 0} if args.dry_run else repository.reconcile_session_usage(session.session_id, refs)
            summary["sessions_processed"] += 1
            summary["desired_usage_rows"] += int(result.get("desired", 0))
            summary["written_usage_rows"] += int(result.get("written", 0))
            for reference in refs:
                kind = str(reference.get("resource_kind") or "unknown")
                summary["references_by_kind"][kind] += 1
            if args.verbose:
                print(session.session_id, result)
        except Exception as exc:  # pragma: no cover - defensive CLI boundary
            summary["sessions_failed"] += 1
            summary["failures"].append({"session_id": session.session_id, "error": str(exc)})
    summary["references_by_kind"] = dict(summary["references_by_kind"])
    if args.baseline:
        summary["baseline_audit"] = _audit_baseline(repository, args.baseline)
    if args.json:
        print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    elif not args.verbose:
        print(
            "reconciliation summary: "
            f"sessions={summary['sessions_processed']}/{summary['sessions_seen']}, "
            f"desired={summary['desired_usage_rows']}, written={summary['written_usage_rows']}, "
            f"failed={summary['sessions_failed']}"
        )
        if args.baseline:
            print(f"baseline audit: {'PASS' if summary['baseline_audit']['ok'] else 'FAIL'}")
    if summary["sessions_failed"] or not summary.get("baseline_audit", {}).get("ok", True):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
