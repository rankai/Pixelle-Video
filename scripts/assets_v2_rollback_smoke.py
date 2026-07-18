#!/usr/bin/env python3
"""Run a non-destructive manifest backup/restore rollback smoke."""

from __future__ import annotations

import argparse
import json
import shutil
import tempfile
from pathlib import Path

from pixelle_video.services.asset_library_baseline import (
    backup_manifests,
    collect_baseline,
    restore_manifests,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    baseline = collect_baseline(args.data_root)
    with tempfile.TemporaryDirectory(prefix="asset-library-ux0-rollback-") as temporary:
        sandbox = Path(temporary) / "data"
        backup = Path(temporary) / "backup"
        for entry in baseline["manifests"]:
            if not entry.get("exists"):
                continue
            source = args.data_root / entry["relative_path"]
            destination = sandbox / entry["relative_path"]
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)

        copied = backup_manifests(sandbox, backup)
        mutated = copied[0]["relative_path"] if copied else None
        if mutated:
            (sandbox / mutated).write_text("[]\n", encoding="utf-8")
        restored = restore_manifests(sandbox, backup)
        restore_verified = bool(mutated) and (sandbox / mutated).read_bytes() == (
            backup / mutated
        ).read_bytes()

    report = {
        "schema_version": "asset-library-ux0-rollback-smoke-v1",
        "data_root_name": args.data_root.resolve().name,
        "source_baseline_schema": baseline["schema_version"],
        "source_missing_files": baseline["missing_files"],
        "manifest_backup_count": len(copied),
        "backed_up_manifests": [item["relative_path"] for item in copied],
        "restored_manifests": restored,
        "restore_verified": restore_verified,
        "original_data_root_modified": False,
        "media_files_moved_or_deleted": False,
        "rollback_command": "uv run python scripts/assets_v2_baseline.py --restore-dir <backup> --confirm-restore",
        "status": "pass" if restore_verified and not baseline["missing_files"] else "fail",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"rollback smoke: {report['status']} ({report['manifest_backup_count']} manifests)")
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
