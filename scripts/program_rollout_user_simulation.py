"""Run the user-style local observation closeout for the one-hour policy.

The observation start timestamp is read from the existing QA record and is
never rewritten.  The run combines a real local React interaction probe with
twenty isolated durable publish-run create/state-readback samples.  It is
strictly local/no-op: no provider, account, platform, upload, or final publish
action is allowed.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from scripts.program_rollout_scale_api_ui_smoke import (
    ROOT,
    _user_data_signature,
    run_scale_api_ui_check,
)

OBSERVATION_QA = ROOT / "docs/reviews/application-publishing-program/qa/PROGRAM-ROLLOUT-observation-readiness-2026-07-21.json"
REQUIRED_WINDOW_HOURS = 1
MINIMUM_BOUNDED_RUNS = 20


def _parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _binary_sha256(path: Path) -> str | None:
    if not path.exists():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _desktop_version() -> str:
    config = json.loads((ROOT / "desktop/src-tauri/tauri.conf.json").read_text(encoding="utf-8"))
    version = str(config.get("version", "")).strip()
    if not version:
        raise RuntimeError("desktop version is missing")
    return f"pixelle-video-desktop@{version}"


def _observation_run_probe() -> dict[str, Any]:
    completed = subprocess.run(
        [sys.executable, "scripts/program_rollout_observation_probe.py"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    for line in reversed(completed.stdout.splitlines()):
        if line.lstrip().startswith("{"):
            return json.loads(line)
    raise RuntimeError("observation probe did not emit JSON evidence")


def _rollback_trigger_evidence(
    ui_probe: dict[str, Any],
    run_probe: dict[str, Any],
    user_data_before: dict[str, Any],
    user_data_after: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    """Compute trigger observations from this run instead of defaulting to zero.

    The local/no-op probe cannot exercise a real profile or platform upload.  That
    boundary is explicit in the profile entry rather than being represented as a
    fabricated zero count.
    """

    local_probe_passed = (
        ui_probe.get("status") == "passed_local_bounded"
        and run_probe.get("status") == "pre_observation_complete"
        and int(run_probe.get("durable_create_run_samples", 0)) == MINIMUM_BOUNDED_RUNS
        and int(run_probe.get("state_readback_passed", 0)) == MINIMUM_BOUNDED_RUNS
    )
    no_upload_actions = (
        int(ui_probe.get("browser_actions", 0)) == 0
        and int(ui_probe.get("external_actions", 0)) == 0
        and int(run_probe.get("browser_actions", 0)) == 0
        and int(run_probe.get("external_actions", 0)) == 0
    )
    no_final_click = (
        int(ui_probe.get("final_publish_clicks", 0)) == 0
        and int(run_probe.get("final_publish_clicks", 0)) == 0
    )
    data_unchanged = user_data_before == user_data_after
    return {
        "p0_p1_regression": {
            "count": 0 if local_probe_passed else 1,
            "status": "observed_local_noop",
            "basis": "ui_and_durable_run_probes_passed" if local_probe_passed else "local_probe_failure",
        },
        "duplicate_upload": {
            "count": 0 if no_upload_actions else 1,
            "status": "observed_local_noop",
            "basis": "no_browser_or_external_upload_action" if no_upload_actions else "unexpected_upload_action",
        },
        "unexpected_final_click": {
            "count": 0 if no_final_click else 1,
            "status": "observed_local_noop",
            "basis": "no_final_publish_click" if no_final_click else "unexpected_final_publish_click",
        },
        "profile_corruption": {
            "count": None,
            "status": "not_executed",
            "basis": "local_noop_probe_does_not_open_or_mutate_a_browser_profile",
            "persistent_data_unchanged": data_unchanged,
        },
    }


def run_user_simulation() -> dict[str, Any]:
    qa = json.loads(OBSERVATION_QA.read_text(encoding="utf-8"))
    started_at = str(qa["observation"]["window_started_at"])
    now = datetime.now(timezone.utc)
    elapsed_hours = (now - _parse_time(started_at)).total_seconds() / 3600
    user_data_before = _user_data_signature()
    started = time.perf_counter()
    with tempfile.TemporaryDirectory(prefix="pixelle-rollout-user-simulation-") as runtime_dir:
        ui_probe = run_scale_api_ui_check(runtime_dir)
    run_probe = _observation_run_probe()
    user_data_after = _user_data_signature()
    duration_ms = (time.perf_counter() - started) * 1000

    records = run_probe.get("records", [])
    durable_count = int(run_probe.get("durable_create_run_samples", len(records)))
    readback_count = sum(1 for item in records if item.get("run_id_present") and item.get("state_readback"))
    trigger_evidence = _rollback_trigger_evidence(ui_probe, run_probe, user_data_before, user_data_after)
    trigger_failures = [
        name for name, evidence in trigger_evidence.items() if evidence.get("count") not in (0, None)
    ]
    build_path = ROOT / "desktop/src-tauri/target/release/pixelle-video-desktop"
    observed_build_sha256 = _binary_sha256(build_path)
    observed_version = _desktop_version()
    build_verified = bool(observed_build_sha256) and build_path.is_file()
    observation_port_released = run_probe.get("port_released") is True
    ui_ports_released = ui_probe.get("api_port_released") is True and ui_probe.get("ui_port_released") is True
    stable = (
        elapsed_hours >= REQUIRED_WINDOW_HOURS
        and durable_count >= MINIMUM_BOUNDED_RUNS
        and readback_count == durable_count
        and not trigger_failures
        and ui_probe.get("status") == "passed_local_bounded"
        and observation_port_released
        and ui_ports_released
        and build_verified
        and ui_probe.get("user_database_touched") is False
        and user_data_before == user_data_after
    )
    return {
        "status": "stable_observation_window_complete" if stable else "stable_observation_incomplete",
        "policy": "user_approved_minimum_window_hours_1",
        "window_started_at": started_at,
        "window_checked_at": now.isoformat().replace("+00:00", "Z"),
        "window_hours_elapsed": round(elapsed_hours, 3),
        "required_window_hours": REQUIRED_WINDOW_HOURS,
        "minimum_versions": 1,
        "observed_version": observed_version,
        "observed_build_sha256": observed_build_sha256,
        "build_verified": build_verified,
        "observation_port_released": observation_port_released,
        "minimum_bounded_runs": MINIMUM_BOUNDED_RUNS,
        "durable_create_run_samples": durable_count,
        "state_readback_passed": readback_count,
        "max_create_ms": max((float(item.get("create_ms", 0)) for item in records), default=0),
        "user_simulation_duration_ms": round(duration_ms, 3),
        "user_simulation": {
            "ui_probe_status": ui_probe.get("status"),
            "local_ui_browser_actions": ui_probe.get("local_ui_browser_actions", 0),
            "projects_api_read": ui_probe.get("projects_api_read", 0),
            "artifacts_api_read": ui_probe.get("artifacts_api_read", 0),
            "ui_route_samples": ui_probe.get("ui_route_samples", 0),
            "ui_route_p95_ms": ui_probe.get("ui_route_p95_ms"),
            "api_port_released": ui_probe.get("api_port_released"),
            "ui_port_released": ui_probe.get("ui_port_released"),
        },
        "rollback_triggers": list(trigger_evidence),
        "rollback_trigger_evidence": trigger_evidence,
        "rollback_trigger_failures": trigger_failures,
        "executor_scheduled": int(run_probe.get("executor_scheduled", 0)),
        "browser_actions": int(run_probe.get("browser_actions", 0)),
        "external_actions": int(run_probe.get("external_actions", 0)),
        "final_publish_clicks": int(run_probe.get("final_publish_clicks", 0)),
        "user_data_unchanged": user_data_before == user_data_after,
        "user_data_mutations": 0 if user_data_before == user_data_after else 1,
        "product_owner_signoff": "pending",
        "windows_build": "deferred_current_macos_environment",
        "real_platform_rollback": "not_executed",
        "local_noop_only": True,
    }


def main() -> None:
    result = run_user_simulation()
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    if result["status"] != "stable_observation_window_complete":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
