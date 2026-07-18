#!/usr/bin/env python3
"""Create the stage-0 asset migration baseline and optional manifest backup."""

from __future__ import annotations

import argparse
from pathlib import Path

from pixelle_video.services.asset_library_baseline import (
    backup_manifests,
    collect_baseline,
    restore_manifests,
    write_baseline,
)
from pixelle_video.utils.os_util import get_data_path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--data-root",
        type=Path,
        default=Path(get_data_path()),
        help="Legacy data directory containing asset manifests (default: ./data)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("output/asset-library-stage0-baseline.json"),
        help="Baseline JSON output path",
    )
    parser.add_argument(
        "--backup-dir",
        type=Path,
        help="Optional rollback directory for manifest backups",
    )
    parser.add_argument(
        "--restore-dir",
        type=Path,
        help="Restore manifests from a verified rollback directory",
    )
    parser.add_argument(
        "--confirm-restore",
        action="store_true",
        help="Required with --restore-dir because it writes legacy manifests",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.restore_dir:
        if not args.confirm_restore:
            raise SystemExit("--restore-dir requires --confirm-restore")
        restored = restore_manifests(args.data_root, args.restore_dir)
        print(f"legacy manifests restored: {len(restored)}")
        return 0
    baseline = collect_baseline(args.data_root)
    if args.backup_dir:
        baseline["rollback"]["manifest_backup_dir"] = str(args.backup_dir)
        baseline["rollback"]["manifest_backup_count"] = len(
            backup_manifests(args.data_root, args.backup_dir)
        )
    write_baseline(args.output, baseline)
    print(
        f"asset-library baseline written: {args.output} "
        f"(missing_files={len(baseline['missing_files'])})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
