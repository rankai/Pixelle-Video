"""Create a bounded, local observation sample for PG-L.

This is intentionally not the seven-day stability window: it records twenty
durable create-run observations against a temporary SQLite database while the
rollout-local no-op seam prevents executor/browser/platform work.
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

from scripts.program_rollout_batch4_smoke import (
    ROOT,
    TOKEN,
    _prepare_publish_fixture,
    _timed_post,
    _wait_for,
)

OBSERVATION_PORT = 8112
RUN_COUNT = 20
REQUIRED_WINDOW_HOURS = 1


def _port_is_bindable(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            probe.bind(("127.0.0.1", port))
        except OSError:
            return False
    return True


def _stop(process: subprocess.Popen[bytes], port: int) -> bool:
    process.terminate()
    try:
        process.wait(timeout=8)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=3)
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline and not _port_is_bindable(port):
        time.sleep(0.1)
    return process.poll() is not None and _port_is_bindable(port)


def _timed_get_json(url: str, headers: dict[str, str]) -> tuple[float, dict[str, object]]:
    from urllib.request import Request, urlopen

    started = time.perf_counter()
    request = Request(url, headers=headers)
    with urlopen(request, timeout=3.0) as response:
        if response.status != 200:
            raise RuntimeError(f"unexpected_status:{url}:{response.status}")
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError(f"unexpected_json_shape:{url}")
    return (time.perf_counter() - started) * 1000, payload


def main() -> None:
    started_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    records: list[dict[str, object]] = []
    with tempfile.TemporaryDirectory(prefix="pixelle-rollout-observation-") as runtime_dir:
        runtime_root = Path(runtime_dir)
        fixture = _prepare_publish_fixture(runtime_root)
        env = {
            **os.environ,
            "PIXELLE_ASSET_CENTER_V2": "true",
            "PIXELLE_DESKTOP_MODE": "1",
            "PIXELLE_DESKTOP_TOKEN": TOKEN,
            "PIXELLE_LOCAL_CAPABILITY": TOKEN,
            "PIXELLE_PUBLISH_V2_ENABLED": "true",
            "PIXELLE_ROLLOUT_LOCAL_NOOP": "true",
            "PIXELLE_PUBLISHING_DB": str(fixture["publishing_db"]),
            "PIXELLE_APP_CENTER_DB": str(fixture["app_db"]),
            "PIXELLE_DESKTOP_TASKS_DB": str(fixture["tasks_db"]),
            "PIXELLE_PUBLISH_MEDIA_ROOTS": str(fixture["media_root"]),
            "PIXELLE_VIDEO_ROOT": str(ROOT),
        }
        api = subprocess.Popen(
            [sys.executable, "api/app.py", "--host", "127.0.0.1", "--port", str(OBSERVATION_PORT)],
            cwd=ROOT,
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        try:
            _wait_for(f"http://127.0.0.1:{OBSERVATION_PORT}/health")
            headers = {
                "X-Pixelle-Desktop-Token": TOKEN,
                "X-Pixelle-Local-Capability": TOKEN,
                "Origin": "tauri://localhost",
            }
            for index, account_id in enumerate(fixture["account_ids"][:RUN_COUNT], start=1):
                elapsed, created = _timed_post(
                    f"http://127.0.0.1:{OBSERVATION_PORT}/api/publish/v2/runs",
                    {
                        "package_id": fixture["package_id"],
                        "account_id": account_id,
                        "platform": "douyin",
                        "idempotency_key": f"rollout-observation-{index:02d}-create",
                    },
                    headers,
                )
                state_elapsed, state_payload = _timed_get_json(
                    f"http://127.0.0.1:{OBSERVATION_PORT}/api/publish/v2/runs/{created['run_id']}",
                    {"X-Pixelle-Desktop-Token": TOKEN},
                )
                state_run = state_payload.get("run")
                state_readback = (
                    isinstance(state_run, dict)
                    and state_run.get("run_id") == created.get("run_id")
                    and state_run.get("state") == "queued"
                    and int(state_run.get("state_version", 0)) >= 1
                )
                records.append(
                    {
                        "sequence": index,
                        "run_id_present": bool(created.get("run_id")),
                        "state_readback": state_readback,
                        "readback_state": state_run.get("state") if isinstance(state_run, dict) else None,
                        "readback_state_version": state_run.get("state_version") if isinstance(state_run, dict) else None,
                        "readback_ms": round(state_elapsed, 3),
                        "create_ms": round(elapsed, 3),
                    }
                )
        finally:
            port_released = _stop(api, OBSERVATION_PORT)

    passed = len(records) == RUN_COUNT and all(item["run_id_present"] and item["state_readback"] for item in records)
    result = {
        "status": "pre_observation_complete" if passed else "failed",
        "window_started_at": started_at,
        "window_hours_elapsed": 0,
        "required_window_hours": 1,
        "durable_create_run_samples": len(records),
        "state_readback_passed": sum(1 for item in records if item["state_readback"]),
        "records": records,
        "port_released": port_released,
        "executor_scheduled": 0,
        "browser_actions": 0,
        "external_actions": 0,
        "final_publish_clicks": 0,
        "rollback_triggers": [
            "P0_or_P1_regression",
            "duplicate_upload",
            "final_publish_click",
            "profile_corruption",
        ],
        "product_owner_signoff": "pending",
        "stable_observation": "not_complete",
    }
    print(json.dumps(result, ensure_ascii=False))
    if not passed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
