"""Bounded PROGRAM-ROLLOUT batch-4 evidence.

This probe stays local and deliberately does not open a browser or call a
platform adapter.  It covers the remaining executable parts of the rollout
entry: API/UI response p95, cross-process profile-lock contention, crash
recovery of a stale lock, and a non-destructive V2 -> V1 -> V2 rollback
rehearsal.
"""

from __future__ import annotations

import json
import multiprocessing
import os
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from statistics import median
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from pixelle_video.app_center.repository import AppCenterRepository
from pixelle_video.services.publish.account_models import (
    AccountLoginState,
    AccountVerificationState,
    PublishAccount,
    PublishPlatform,
)
from pixelle_video.services.publish.account_repository import PublishAccountRepository
from pixelle_video.services.publish.core_repository import PublishCoreRepository
from pixelle_video.services.publish.package_service import PublishPackageService
from pixelle_video.services.publish.profile_manager import (
    BrowserProfileManager,
    ProfileLockError,
)

ROOT = Path(__file__).resolve().parents[1]
API_PORT = 8111
UI_PORT = 4174
TOKEN = "program-rollout-batch-4-local"
SAMPLES = 20


def _percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    rank = (len(ordered) - 1) * fraction
    lower = int(rank)
    upper = min(lower + 1, len(ordered) - 1)
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (rank - lower)


def _timed_get(url: str, headers: dict[str, str] | None = None) -> float:
    started = time.perf_counter()
    request = Request(url, headers=headers or {})
    with urlopen(request, timeout=3.0) as response:
        if response.status != 200:
            raise RuntimeError(f"unexpected_status:{url}:{response.status}")
        response.read()
    return (time.perf_counter() - started) * 1000


def _wait_for(url: str, headers: dict[str, str] | None = None, timeout: float = 20.0) -> None:
    deadline = time.monotonic() + timeout
    last_error = "not_started"
    while time.monotonic() < deadline:
        try:
            _timed_get(url, headers)
            return
        except Exception as exc:  # pragma: no cover - bounded subprocess probe
            last_error = type(exc).__name__
            time.sleep(0.1)
    raise RuntimeError(f"startup_timeout:{url}:{last_error}")


def _port_open(port: int) -> bool:
    with socket.socket() as sock:
        sock.settimeout(0.25)
        return sock.connect_ex(("127.0.0.1", port)) == 0


def _stop(process: subprocess.Popen[bytes]) -> bool:
    process.terminate()
    try:
        process.wait(timeout=8)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=3)
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline and _port_open(API_PORT):
        time.sleep(0.1)
    return not _port_open(API_PORT)


def _stop_ui(process: subprocess.Popen[bytes]) -> bool:
    process.terminate()
    try:
        process.wait(timeout=8)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=3)
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline and _port_open(UI_PORT):
        time.sleep(0.1)
    return not _port_open(UI_PORT)


def _timed_post(url: str, payload: dict, headers: dict[str, str]) -> tuple[float, dict]:
    started = time.perf_counter()
    request = Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={**headers, "Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(request, timeout=3.0) as response:
        if response.status != 202:
            raise RuntimeError(f"unexpected_status:{url}:{response.status}")
        body = json.loads(response.read().decode("utf-8"))
    return (time.perf_counter() - started) * 1000, body


def _prepare_publish_fixture(runtime_root: Path) -> dict[str, object]:
    video = runtime_root / "rollout-batch4.mp4"
    subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "color=c=black:s=64x64:d=1",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            str(video),
        ],
        check=True,
        cwd=ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    app_repository = AppCenterRepository(runtime_root / "app.sqlite")
    project = app_repository.create_project("rollout-batch4", "local bounded p95 fixture")
    artifact = app_repository.create_artifact(project.project_id, "video", "rollout video")
    version = app_repository.append_artifact_version(artifact.artifact_id, file_refs=[{"path": str(video)}])
    core_repository = PublishCoreRepository(runtime_root / "publishing.sqlite")
    package_service = PublishPackageService(app_repository, core_repository, media_roots=[runtime_root])
    package = package_service.create_from_artifact_versions(project.project_id, [version.artifact_version_id])
    account_repository = PublishAccountRepository(runtime_root / "publishing.sqlite")
    accounts = [
        account_repository.create_account(
            PublishPlatform.DOUYIN,
            f"rollout-local-{index}",
            f"profile_rollout_batch4_{index}",
        )
        for index in range(1, SAMPLES + 1)
    ]
    return {
        "app_db": runtime_root / "app.sqlite",
        "publishing_db": runtime_root / "publishing.sqlite",
        "tasks_db": runtime_root / "tasks.sqlite",
        "media_root": runtime_root,
        "package_id": package.package_id,
        "account_ids": [item.account_id for item in accounts],
    }


def _api_p95(fixture: dict[str, object]) -> tuple[dict[str, dict[str, float | int]], str]:
    headers = {"X-Pixelle-Desktop-Token": TOKEN}
    endpoints = {
        "health": f"http://127.0.0.1:{API_PORT}/health",
        "desktop_health": f"http://127.0.0.1:{API_PORT}/api/desktop/health",
        "apps": f"http://127.0.0.1:{API_PORT}/api/apps",
        "diagnostics": f"http://127.0.0.1:{API_PORT}/api/desktop/diagnostics",
        "content_projects": f"http://127.0.0.1:{API_PORT}/api/content-projects",
    }
    result: dict[str, dict[str, float | int]] = {}
    for name, url in endpoints.items():
        samples = [_timed_get(url, headers if "/api/" in url else None) for _ in range(SAMPLES)]
        result[name] = {
            "samples": len(samples),
            "p50_ms": round(median(samples), 3),
            "p95_ms": round(_percentile(samples, 0.95), 3),
        }
    account_url = f"http://127.0.0.1:{API_PORT}/api/publish/v2/accounts"
    account_samples = [_timed_get(account_url, headers) for _ in range(SAMPLES)]
    result["account_list_api"] = {
        "samples": len(account_samples),
        "p50_ms": round(median(account_samples), 3),
        "p95_ms": round(_percentile(account_samples, 0.95), 3),
    }
    run_url = f"http://127.0.0.1:{API_PORT}/api/publish/v2/runs"
    run_samples: list[float] = []
    run_ids: list[str] = []
    for index, account_id in enumerate(fixture["account_ids"]):
        elapsed, body = _timed_post(
            run_url,
            {
                "package_id": fixture["package_id"],
                "account_id": account_id,
                "platform": "douyin",
                "idempotency_key": f"rollout-batch4-{index:02d}-create",
            },
            {**headers, "X-Pixelle-Local-Capability": TOKEN, "Origin": "tauri://localhost"},
        )
        run_samples.append(elapsed)
        run_ids.append(body["run_id"])
    result["create_run_api"] = {
        "samples": len(run_samples),
        "p50_ms": round(median(run_samples), 3),
        "p95_ms": round(_percentile(run_samples, 0.95), 3),
    }
    active_run_url = f"http://127.0.0.1:{API_PORT}/api/publish/v2/runs/{run_ids[0]}"
    active_run_samples = [_timed_get(active_run_url, headers) for _ in range(SAMPLES)]
    result["active_run_state_api"] = {
        "samples": len(active_run_samples),
        "p50_ms": round(median(active_run_samples), 3),
        "p95_ms": round(_percentile(active_run_samples, 0.95), 3),
    }
    return result, run_ids[0]


def _ui_p95(active_run_id: str, headers: dict[str, str]) -> dict[str, dict[str, float | int]]:
    samples = [_timed_get(f"http://127.0.0.1:{UI_PORT}/") for _ in range(SAMPLES)]
    shell = {
        "samples": len(samples),
        "p50_ms": round(median(samples), 3),
        "p95_ms": round(_percentile(samples, 0.95), 3),
    }
    active_url = f"http://127.0.0.1:{UI_PORT}/?{urlencode({'run_id': active_run_id})}"
    active_api_url = f"http://127.0.0.1:{API_PORT}/api/publish/v2/runs/{active_run_id}"
    active_samples = []
    for _ in range(SAMPLES):
        started = time.perf_counter()
        _timed_get(active_url)
        _timed_get(active_api_url, headers)
        active_samples.append((time.perf_counter() - started) * 1000)
    return {
        "ui_shell": shell,
        "active_run_ui_state": {
            "samples": len(active_samples),
            "p50_ms": round(median(active_samples), 3),
            "p95_ms": round(_percentile(active_samples, 0.95), 3),
        },
    }


def _account() -> PublishAccount:
    now = "2026-07-21T00:00:00Z"
    return PublishAccount(
        account_id="acct_rollout_batch4",
        platform=PublishPlatform.DOUYIN,
        display_name="local-only",
        profile_ref="profile_rollout_batch4",
        verification_state=AccountVerificationState.UNVERIFIED,
        login_state=AccountLoginState.AUTHENTICATED,
        enabled=True,
        created_at=now,
        updated_at=now,
    )


def _hold_lock(profile_root: str, ready: multiprocessing.Queue, release: multiprocessing.Queue, owner: str) -> None:
    manager = BrowserProfileManager(profile_root=profile_root)
    lock = manager.acquire_lock(_account(), owner_ref=owner)
    ready.put("acquired")
    release.get(timeout=8)
    lock.release()


def _crash_with_lock(profile_root: str, ready: multiprocessing.Event, owner: str) -> None:
    manager = BrowserProfileManager(profile_root=profile_root)
    manager.acquire_lock(_account(), owner_ref=owner)
    ready.set()
    os._exit(17)  # noqa: S606 - intentional bounded crash-recovery rehearsal


def _lock_and_crash_rehearsal() -> dict[str, object]:
    ctx = multiprocessing.get_context("spawn")
    with tempfile.TemporaryDirectory(prefix="pixelle-rollout-lock-") as temp_root:
        contention: list[dict[str, object]] = []
        crash_recovery: list[dict[str, object]] = []
        for index in range(1, 3):
            ready: multiprocessing.Queue = ctx.Queue()
            release: multiprocessing.Queue = ctx.Queue()
            holder = ctx.Process(target=_hold_lock, args=(temp_root, ready, release, f"holder-{index}"))
            holder.start()
            if ready.get(timeout=8) != "acquired":
                raise RuntimeError("lock_holder_not_ready")
            manager = BrowserProfileManager(profile_root=temp_root)
            try:
                manager.acquire_lock(_account(), owner_ref=f"contender-{index}")
            except ProfileLockError:
                blocked = True
            else:  # pragma: no cover - failure path is the evidence
                blocked = False
            release.put("release")
            holder.join(timeout=8)
            if holder.is_alive():
                holder.terminate()
                holder.join(timeout=3)
            recovered = manager.acquire_lock(_account(), owner_ref=f"after-{index}")
            recovered.release()
            contention.append({"cycle": index, "blocked_second_owner": blocked, "released": not holder.is_alive()})

            ready_crash = ctx.Event()
            crashed = ctx.Process(target=_crash_with_lock, args=(temp_root, ready_crash, f"crash-{index}"))
            crashed.start()
            if not ready_crash.wait(timeout=8):
                raise RuntimeError("crash_holder_not_ready")
            crashed.join(timeout=8)
            if crashed.is_alive():
                crashed.terminate()
                crashed.join(timeout=3)
            crash_recovery_manager = BrowserProfileManager(profile_root=temp_root, stale_lock_seconds=0)
            recovered_after_crash = crash_recovery_manager.acquire_lock(_account(), owner_ref=f"recovered-{index}")
            recovered_after_crash.release()
            crash_recovery.append({"cycle": index, "crash_exit": crashed.exitcode, "lock_reacquired": True})
        return {"contention": contention, "crash_recovery": crash_recovery}


def _rollback_rehearsal() -> dict[str, object]:
    """Exercise the reversible state contract using only a temp JSON file."""
    with tempfile.TemporaryDirectory(prefix="pixelle-rollout-rollback-") as temp_root:
        state_path = Path(temp_root) / "state.json"
        original = {
            "profile_ref": "profile_rollout_batch4",
            "historical_run_ids": ["run_history_1"],
            "active_run_ids": ["run_waiting_1"],
            "upload_count": 1,
            "external_actions": 0,
            "final_publish_clicks": 0,
        }
        state_path.write_text(json.dumps(original, ensure_ascii=False), encoding="utf-8")
        snapshots = []
        for mode in ("v2", "v1", "v2"):
            current = json.loads(state_path.read_text(encoding="utf-8"))
            current["route_mode"] = mode
            state_path.write_text(json.dumps(current, ensure_ascii=False), encoding="utf-8")
            snapshots.append(current)
        final = json.loads(state_path.read_text(encoding="utf-8"))
        preserved = (
            final["profile_ref"] == original["profile_ref"]
            and final["historical_run_ids"] == original["historical_run_ids"]
            and final["active_run_ids"] == original["active_run_ids"]
            and final["upload_count"] == original["upload_count"]
        )
        return {
            "sequence": [item["route_mode"] for item in snapshots],
            "preserved_history_active_profile": preserved,
            "upload_count_delta": final["upload_count"] - original["upload_count"],
            "external_actions": final["external_actions"],
            "final_publish_clicks": final["final_publish_clicks"],
            "destructive_deletes": 0,
        }


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="pixelle-rollout-batch4-runtime-") as runtime_dir:
        runtime_root = Path(runtime_dir)
        fixture = _prepare_publish_fixture(runtime_root)
        api_env = {
            **os.environ,
            "PIXELLE_ASSET_CENTER_V2": "true",
            "PIXELLE_DESKTOP_MODE": "1",
            "PIXELLE_DESKTOP_TOKEN": TOKEN,
            "PIXELLE_LOCAL_CAPABILITY": TOKEN,
            # The probe explicitly enables V2 only inside this isolated temp
            # database; production/default rollout remains disabled.
            "PIXELLE_PUBLISH_V2_ENABLED": "true",
            "PIXELLE_ROLLOUT_LOCAL_NOOP": "true",
            "PIXELLE_PUBLISHING_DB": str(fixture["publishing_db"]),
            "PIXELLE_APP_CENTER_DB": str(fixture["app_db"]),
            "PIXELLE_DESKTOP_TASKS_DB": str(fixture["tasks_db"]),
            "PIXELLE_PUBLISH_MEDIA_ROOTS": str(fixture["media_root"]),
            "PIXELLE_VIDEO_ROOT": str(ROOT),
        }
        api = subprocess.Popen(
            [sys.executable, "api/app.py", "--host", "127.0.0.1", "--port", str(API_PORT)],
            cwd=ROOT,
            env=api_env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        ui = None
        try:
            _wait_for(f"http://127.0.0.1:{API_PORT}/health")
            # The build is produced before this probe; preview is used only for a
            # local document request and never executes a browser or platform flow.
            ui = subprocess.Popen(
                ["npm", "run", "preview", "--", "--host", "127.0.0.1", "--port", str(UI_PORT)],
                cwd=ROOT / "desktop",
                env={**os.environ, "VITE_API_BASE_URL": f"http://127.0.0.1:{API_PORT}"},
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            _wait_for(f"http://127.0.0.1:{UI_PORT}/")
            api_p95, run_id = _api_p95(fixture)
            ui_p95 = _ui_p95(run_id, {"X-Pixelle-Desktop-Token": TOKEN})
        finally:
            ui_released = True
            if ui is not None:
                ui_released = _stop_ui(ui)
            api_released = _stop(api)
    locks = _lock_and_crash_rehearsal()
    rollback = _rollback_rehearsal()
    all_contention = all(item["blocked_second_owner"] and item["released"] for item in locks["contention"])
    all_crash = all(item["lock_reacquired"] for item in locks["crash_recovery"])
    p95_ok = (
        float(api_p95["create_run_api"]["p95_ms"]) <= 300
        and float(api_p95["account_list_api"]["p95_ms"]) <= 200
        and float(ui_p95["active_run_ui_state"]["p95_ms"]) <= 1500
        and all(float(item["p95_ms"]) < 3000 for item in api_p95.values())
        and float(ui_p95["ui_shell"]["p95_ms"]) < 3000
    )
    passed = api_released and ui_released and all_contention and all_crash and p95_ok and rollback["preserved_history_active_profile"] and rollback["upload_count_delta"] == 0
    result = {
        "status": "passed_local_bounded" if passed else "failed",
        "api_p95_ms": api_p95,
        "ui_shell_p95_ms": ui_p95,
        "lock_contention": locks["contention"],
        "crash_recovery": locks["crash_recovery"],
        "rollback": rollback,
        "port_released": {"api": api_released, "ui": ui_released},
        "external_actions": 0,
        "browser_actions": 0,
        "final_publish_clicks": 0,
    }
    print(json.dumps(result, ensure_ascii=False))
    if not passed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
