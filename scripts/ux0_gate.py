#!/usr/bin/env python3
"""Verify that the versioned UX-0 evidence bundle is complete.

This is an evidence-index check only. It never mutates the application data
root and it deliberately reports UX-A user-study evidence separately.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from api.schemas.asset_library_ux0 import TemplateLayoutContract

REQUIRED_ADRS = [
    "002-asset-center-smb-ux-a-contracts.md",
    "003-template-layout-contract-v2.md",
    "004-voice-profile.md",
    "005-deferred-upload-finalize.md",
    "006-stable-cursor-facets.md",
]
REQUIRED_SCHEMAS = [
    "asset-view-model.schema.json",
    "picker-context.schema.json",
    "template-layout-contract-v2.schema.json",
    "voice-profile.schema.json",
    "deferred-upload-create.schema.json",
    "deferred-upload-finalize.schema.json",
    "deferred-upload-response.schema.json",
    "library-cursor.schema.json",
    "library-page-facets.schema.json",
]
REQUIRED_FIXTURES = [
    "asset-library-1000.seed.json",
    "cursor-pages.json",
    "deferred-upload/cases.json",
    "template-layout/valid.json",
    "template-layout/unknown-field.json",
    "template-layout/missing-font.json",
    "template-layout/golden.json",
    "voice-migration/legacy/voice_references.json",
    "voice-migration/legacy/audio_assets.json",
    "voice-migration/sessions/session-voice-001.json",
    "voice-migration/sessions/session-voice-002.json",
]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def artifact(root: Path, relative: str) -> dict[str, object]:
    path = root / relative
    return {
        "path": relative,
        "exists": path.is_file(),
        "sha256": sha256(path) if path.is_file() else None,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("docs/migrations/asset-library-ux0-gate-2026-07-18.json"),
    )
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]

    adr_items = [artifact(root / "docs/adr", name) for name in REQUIRED_ADRS]
    schema_items = [artifact(root / "docs/schemas", name) for name in REQUIRED_SCHEMAS]
    fixture_items = [artifact(root / "tests/fixtures/ux0", name) for name in REQUIRED_FIXTURES]
    contracts = json.loads(
        (root / "tests/fixtures/ux0/template-layout/valid.json").read_text(
            encoding="utf-8"
        )
    )
    TemplateLayoutContract.model_validate(contracts)

    baseline_path = root / "docs/migrations/asset-library-ux0-baseline-2026-07-18.json"
    voice_path = root / "docs/migrations/voice-profile-dry-run-2026-07-18.json"
    rollback_path = root / "docs/migrations/asset-library-ux0-rollback-2026-07-18.json"
    current_baseline_path = root / "docs/migrations/asset-center-ux0-current-baseline-2026-07-18/report.json"
    uxa_review_path = root / "docs/reviews/2026-07-18-asset-center-uxa-formal-evidence-review.md"
    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    voice = json.loads(voice_path.read_text(encoding="utf-8"))
    rollback = json.loads(rollback_path.read_text(encoding="utf-8"))
    current_baseline = json.loads(current_baseline_path.read_text(encoding="utf-8"))
    uxa_review_text = uxa_review_path.read_text(encoding="utf-8") if uxa_review_path.is_file() else ""
    current_tasks = current_baseline.get("tasks", [])
    current_baseline_complete = (
        current_baseline.get("status") == "evidence_recorded"
        and len(current_tasks) == 7
        and all(
            isinstance(task.get("click_count"), int)
            and isinstance(task.get("elapsed_ms"), int)
            and isinstance(task.get("screenshot"), str)
            and isinstance(task.get("errors"), list)
            for task in current_tasks
        )
        and bool(current_baseline.get("recordings"))
        and current_baseline.get("environment", {}).get("target_user_study") is False
    )

    checks = {
        "adrs_complete": all(item["exists"] for item in adr_items),
        "schemas_complete": all(item["exists"] for item in schema_items),
        "fixtures_complete": all(item["exists"] for item in fixture_items),
        "template_valid_fixture_loads": True,
        "baseline_has_no_missing_files": not baseline.get("missing_files"),
        "voice_dry_run_only": voice.get("dry_run") is True and voice.get("writes_performed") == 0,
        "voice_sessions_resolvable": voice.get("session_reconciliation", {}).get("references_unresolved") == 0,
        "rollback_pass": rollback.get("status") == "pass",
        "rollback_preserves_source": rollback.get("original_data_root_modified") is False,
        "rollback_preserves_media": rollback.get("media_files_moved_or_deleted") is False,
        "current_version_baseline_recordings": current_baseline_complete,
        "uxa_formal_evidence_review": '"verdict": "pass"' in uxa_review_text and '"evidence_items": 8' in uxa_review_text,
    }
    report = {
        "schema_version": "asset-library-ux0-gate-v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "pass" if all(checks.values()) else "fail",
        "checks": checks,
        "artifacts": {
            "adrs": adr_items,
            "schemas": schema_items,
            "fixtures": fixture_items,
            "baseline": artifact(root, "docs/migrations/asset-library-ux0-baseline-2026-07-18.json"),
            "voice_dry_run": artifact(root, "docs/migrations/voice-profile-dry-run-2026-07-18.json"),
            "rollback_smoke": artifact(root, "docs/migrations/asset-library-ux0-rollback-2026-07-18.json"),
            "current_version_baseline": artifact(root, "docs/migrations/asset-center-ux0-current-baseline-2026-07-18/report.json"),
            "uxa_formal_review": artifact(root, "docs/reviews/2026-07-18-asset-center-uxa-formal-evidence-review.md"),
        },
        "live_results": {
            "baseline_missing_files": len(baseline.get("missing_files", [])),
            "voice_profiles": len(voice.get("voice_profiles", [])),
            "voice_sessions_seen": voice.get("session_reconciliation", {}).get("sessions_seen", 0),
            "voice_references_resolved": voice.get("session_reconciliation", {}).get("references_resolved", 0),
            "voice_references_unresolved": voice.get("session_reconciliation", {}).get("references_unresolved", 0),
            "voice_writes_performed": voice.get("writes_performed"),
            "rollback_manifest_backup_count": rollback.get("manifest_backup_count", 0),
            "current_baseline_tasks": len(current_tasks),
            "current_baseline_observed_errors": sum(1 for task in current_tasks if task.get("status") == "observed_error"),
        },
        "ux_a_status": "pass" if checks["uxa_formal_evidence_review"] else "pending_formal_review",
        "next_gate": "UX-1 acceptance may proceed; UX-C/UX-D/UX-E evidence remains required before default rollout." if checks["uxa_formal_evidence_review"] else "UX-A must formally review the seven current-version task recordings and their observed gaps before UX-1 acceptance.",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"UX-0 gate: {report['status']} ({len(REQUIRED_ADRS)} ADRs, {len(REQUIRED_SCHEMAS)} schemas, {len(REQUIRED_FIXTURES)} fixture entries)")
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
