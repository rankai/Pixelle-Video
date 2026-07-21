"""Bounded local sidecar lifecycle smoke for PROGRAM-ROLLOUT.

No browser, platform, upload, or publish action is involved. The script is
intentionally explicit so a failed cycle cannot be mistaken for a pass.
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
PORT = 8110
ENV = {
    **os.environ,
    "PIXELLE_ASSET_CENTER_V2": "true",
    "PIXELLE_DESKTOP_MODE": "1",
    "PIXELLE_DESKTOP_TOKEN": "program-rollout-local",
    "PIXELLE_LOCAL_CAPABILITY": "program-rollout-local",
    "PIXELLE_PUBLISH_V2_ENABLED": "false",
    "PIXELLE_VIDEO_ROOT": str(ROOT),
}


def wait_health(timeout: float = 15.0) -> dict:
    deadline = time.monotonic() + timeout
    url = f"http://127.0.0.1:{PORT}/health"
    last_error = "not_started"
    while time.monotonic() < deadline:
        try:
            with urlopen(url, timeout=0.5) as response:
                return json.loads(response.read().decode("utf-8"))
        except Exception as exc:  # pragma: no cover - bounded runtime probe
            last_error = type(exc).__name__
            time.sleep(0.1)
    raise RuntimeError(f"health_timeout:{last_error}")


def port_open() -> bool:
    with socket.socket() as sock:
        sock.settimeout(0.25)
        return sock.connect_ex(("127.0.0.1", PORT)) == 0


def run_cycle(cycle: int, env: dict[str, str]) -> dict:
    process = subprocess.Popen(
        [sys.executable, "api/app.py", "--host", "127.0.0.1", "--port", str(PORT)],
        cwd=ROOT,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        health = wait_health()
        if not port_open():
            raise RuntimeError("health_without_open_port")
    finally:
        process.terminate()
        try:
            process.wait(timeout=8)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=3)
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline and port_open():
        time.sleep(0.1)
    return {
        "cycle": cycle,
        "health": health,
        "returncode": process.returncode,
        "port_released": not port_open(),
        "external_actions": 0,
        "browser_actions": 0,
        "final_publish_clicks": 0,
    }


def main() -> None:
    global_task_db = ROOT / "data" / "desktop_tasks.sqlite"
    before_signature = _file_signature(global_task_db)
    with tempfile.TemporaryDirectory(prefix="pixelle-rollout-lifecycle-") as temp_root:
        env = {
            **ENV,
            "PIXELLE_DESKTOP_TASKS_DB": str(Path(temp_root) / "tasks.sqlite"),
        }
        cycles = [run_cycle(index, env) for index in range(1, 11)]
    after_signature = _file_signature(global_task_db)
    global_task_db_unchanged = before_signature == after_signature
    passed = (
        all(item["port_released"] and item["returncode"] in {0, -15} for item in cycles)
        and global_task_db_unchanged
    )
    result = {
        "status": "passed_local_bounded" if passed else "failed",
        "cycles": cycles,
        "global_task_db_unchanged": global_task_db_unchanged,
    }
    print(json.dumps(result, ensure_ascii=False))
    if not passed:
        raise SystemExit(1)


def _file_signature(path: Path) -> tuple[int, int] | None:
    try:
        stat = path.stat()
    except FileNotFoundError:
        return None
    return stat.st_mtime_ns, stat.st_size


if __name__ == "__main__":
    main()
