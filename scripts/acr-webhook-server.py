#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from acr_webhook_lib import (
    extract_acr_event,
    load_config_from_env,
    mark_image_ready,
    should_accept_secret,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def trigger_deploy(tag: str) -> None:
    env = os.environ.copy()
    env["IMAGE_TAG"] = tag
    log_path = Path(os.environ.get("ACR_WEBHOOK_DEPLOY_LOG", "logs/deploy-webhook.log"))
    if not log_path.is_absolute():
        log_path = PROJECT_ROOT / log_path
    log_path.parent.mkdir(parents=True, exist_ok=True)

    with log_path.open("a", encoding="utf-8") as log_file:
        log_file.write(f"\n==> Trigger deploy for tag {tag}\n")
        subprocess.run(
            ["./scripts/deploy.sh"],
            cwd=PROJECT_ROOT,
            env=env,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            check=False,
        )


class ACRWebhookHandler(BaseHTTPRequestHandler):
    server_version = "PixelleACRWebhook/1.0"

    def do_GET(self) -> None:
        if self.path == "/health":
            self._send_json(200, {"status": "ok"})
            return
        self._send_json(404, {"error": "not_found"})

    def do_POST(self) -> None:
        expected_path = os.environ.get("ACR_WEBHOOK_PATH", "/pixelle-acr-webhook")
        parsed_url = urlparse(self.path)
        if parsed_url.path != expected_path:
            self._send_json(404, {"error": "not_found"})
            return

        config = load_config_from_env()
        provided_secret = self._extract_secret(parsed_url.query)
        if not should_accept_secret(config, provided_secret):
            self._send_json(401, {"error": "invalid_secret"})
            return

        try:
            payload = self._read_json_body()
            event = extract_acr_event(payload)
            state_path = Path(
                os.environ.get("ACR_WEBHOOK_STATE_PATH", "data/deploy_webhook_state.json")
            )
            if not state_path.is_absolute():
                state_path = PROJECT_ROOT / state_path
            update = mark_image_ready(
                state_path=state_path,
                tag=event.tag,
                service=event.service,
                expected_services=set(config.expected_services),
            )
        except Exception as exc:
            self._send_json(400, {"error": str(exc)})
            return

        if update.ready_to_deploy:
            thread = threading.Thread(target=trigger_deploy, args=(event.tag,), daemon=True)
            thread.start()

        self._send_json(
            202,
            {
                "status": "accepted",
                "tag": event.tag,
                "service": event.service,
                "services": sorted(update.services),
                "deploy_triggered": update.ready_to_deploy,
            },
        )

    def log_message(self, format: str, *args: object) -> None:
        print(f"{self.address_string()} - {format % args}")

    def _extract_secret(self, query: str) -> str | None:
        query_values = parse_qs(query)
        query_secret = query_values.get("secret", [None])[0]
        return (
            self.headers.get("X-Pixelle-Webhook-Secret")
            or self.headers.get("X-Webhook-Secret")
            or self.headers.get("X-Webhook-Token")
            or query_secret
        )

    def _read_json_body(self) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length)
        if not body:
            raise ValueError("empty webhook body")
        payload = json.loads(body.decode("utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("webhook body must be a JSON object")
        return payload

    def _send_json(self, status_code: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main() -> None:
    os.chdir(PROJECT_ROOT)
    load_dotenv(PROJECT_ROOT / ".env")

    host = os.environ.get("ACR_WEBHOOK_HOST", "127.0.0.1")
    port = int(os.environ.get("ACR_WEBHOOK_PORT", "9001"))
    server = ThreadingHTTPServer((host, port), ACRWebhookHandler)
    print(f"Pixelle ACR webhook server listening on http://{host}:{port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
