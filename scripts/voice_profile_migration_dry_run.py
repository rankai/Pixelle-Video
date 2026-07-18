#!/usr/bin/env python3
"""Generate a read-only VoiceProfile migration and session reconciliation report."""

from __future__ import annotations

import argparse
from pathlib import Path

from pixelle_video.services.voice_profile_migration import (
    dry_run_voice_profile_migration,
    write_migration_report,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--session-root", type=Path)
    parser.add_argument("--ordinary-audio-manifest", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = dry_run_voice_profile_migration(
        args.data_root,
        session_root=args.session_root,
        ordinary_audio_manifest=args.ordinary_audio_manifest,
    )
    write_migration_report(args.output, report)
    print(
        "voice profile dry-run: "
        f"profiles={len(report['voice_profiles'])}, "
        f"session_refs={report['session_reconciliation']['sessions_seen']}, "
        f"unresolved={report['session_reconciliation']['references_unresolved']}, "
        f"writes={report['writes_performed']}"
    )
    return 0 if report["ready_for_review"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
