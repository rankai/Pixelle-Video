#!/usr/bin/env python3
"""Validate the external UX-E release evidence packet without fabricating data."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

REQUIRED_ROLES = {
    "store_owner": 2,
    "store_manager_or_ops": 2,
    "experienced_video_operator": 1,
}
REQUIRED_TASK_IDS = {f"T{index}" for index in range(1, 9)}


def _filled(value: Any) -> bool:
    return value is not None and value != "" and value != []


def _valid_task_results(value: Any) -> bool:
    if not isinstance(value, list) or {str(item.get("task_id")) for item in value if isinstance(item, dict)} != REQUIRED_TASK_IDS:
        return False
    return all(
        isinstance(item, dict)
        and isinstance(item.get("success"), bool)
        and isinstance(item.get("elapsed_seconds"), (int, float))
        and item["elapsed_seconds"] >= 0
        and isinstance(item.get("intent_actions"), (int, float))
        and item["intent_actions"] >= 0
        and "error_code" in item
        for item in value
    )


def validate(packet: dict[str, Any]) -> dict[str, Any]:
    environment = packet.get("environment") or {}
    participants = packet.get("participants") or []
    glyph = packet.get("glyph_mask") or {}
    gray = packet.get("gray_observation") or {}
    review = packet.get("review") or {}
    role_counts = Counter(str(item.get("role")) for item in participants if isinstance(item, dict))

    participant_rows = []
    for participant in participants:
        if not isinstance(participant, dict):
            participant_rows.append(False)
            continue
        participant_rows.append(
            participant.get("independent") is True
            and isinstance(participant.get("success_rate"), (int, float))
            and isinstance(participant.get("median_seconds"), (int, float))
            and isinstance(participant.get("p95_seconds"), (int, float))
            and _filled(participant.get("recording_path"))
            and _valid_task_results(participant.get("task_results"))
        )

    checks = {
        "schema_version": packet.get("schema_version") == "asset-center-uxe-release-evidence-v1",
        "environment_complete": all(
            _filled(environment.get(key))
            for key in ("release_device_id", "app_version", "commit_sha", "fixed_dataset_sha256", "local_service_revision")
        ) and environment.get("fixed_dataset_count") == 1000,
        "participant_roles": all(role_counts[role] >= count for role, count in REQUIRED_ROLES.items()),
        "participant_metrics": len(participants) == 5 and all(participant_rows),
        "glyph_mask": (
            isinstance(glyph.get("observed_min_iou"), (int, float))
            and glyph["observed_min_iou"] >= float(glyph.get("required_min_iou", 0.98))
            and int(glyph.get("sample_count", 0)) > 0
            and bool(glyph.get("frame_paths"))
        ),
        "gray_observation": (
            _filled(gray.get("enabled_at"))
            and int(gray.get("observation_window_days", 0)) > 0
            and isinstance(gray.get("success_rate"), (int, float))
            and gray.get("revert_tested") is True
            and gray.get("old_v2_healthy") is True
            and _filled(gray.get("revert_evidence_path"))
        ),
        "review_signoff": (
            review.get("target_user_study_complete") is True
            and review.get("release_device_signoff") is True
            and review.get("default_rollout_authorized") is True
            and _filled(review.get("reviewer"))
            and _filled(review.get("reviewed_at"))
        ),
    }
    status = "pass" if all(checks.values()) else "pending_external_evidence"
    return {
        "schema_version": "asset-center-uxe-release-evidence-validation-v1",
        "status": status,
        "source_status": packet.get("status"),
        "checks": checks,
        "role_counts": dict(role_counts),
        "default_rollout_authorized": status == "pass",
        "note": "This validator only accepts supplied external evidence; it never generates participant, device, glyph, or gray-observation values.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=Path("docs/migrations/asset-center-uxe-release-evidence-template-2026-07-18.json"))
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = validate(json.loads(args.input.read_text(encoding="utf-8")))
    serialized = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(serialized, encoding="utf-8")
    print(serialized, end="")
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
