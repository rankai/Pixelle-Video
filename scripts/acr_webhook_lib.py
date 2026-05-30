from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ACRWebhookConfig:
    secret: str = ""
    expected_services: frozenset[str] = frozenset({"api", "web"})


@dataclass(frozen=True)
class ACRWebhookEvent:
    repository: str
    service: str
    tag: str


@dataclass(frozen=True)
class WebhookStateUpdate:
    tag: str
    services: set[str]
    ready_to_deploy: bool


def should_accept_secret(config: ACRWebhookConfig, provided_secret: str | None) -> bool:
    if not config.secret:
        return True
    return provided_secret == config.secret


def extract_acr_event(payload: dict[str, Any]) -> ACRWebhookEvent:
    repository = _first_string(
        payload,
        [
            ("repository", "repo_full_name"),
            ("repository", "name"),
            ("data", "repository", "repo_full_name"),
            ("data", "repository", "name"),
            ("data", "repo_full_name"),
            ("repo_full_name",),
            ("repo_name",),
            ("image_repo_name",),
        ],
    )
    tag = _first_string(
        payload,
        [
            ("push_data", "tag"),
            ("data", "push_data", "tag"),
            ("data", "tag"),
            ("tag",),
            ("image_tag",),
        ],
    )
    if not repository or not tag:
        raise ValueError("ACR webhook payload missing repository or tag")

    repository_name = repository.rsplit("/", 1)[-1]
    service = _service_from_repository(repository_name)
    return ACRWebhookEvent(repository=repository_name, service=service, tag=tag)


def mark_image_ready(
    state_path: Path,
    tag: str,
    service: str,
    expected_services: set[str],
) -> WebhookStateUpdate:
    state = _load_state(state_path)
    tags = state.setdefault("tags", {})
    tag_state = tags.setdefault(tag, {})
    services = set(tag_state.get("services", []))
    services.add(service)
    tag_state["services"] = sorted(services)

    ready = expected_services.issubset(services) and not tag_state.get("deploy_triggered")
    if ready:
        tag_state["deploy_triggered"] = True

    _write_state_atomic(state_path, state)
    return WebhookStateUpdate(tag=tag, services=services, ready_to_deploy=ready)


def load_config_from_env() -> ACRWebhookConfig:
    expected = os.environ.get("ACR_WEBHOOK_EXPECTED_SERVICES", "api,web")
    services = frozenset(item.strip() for item in expected.split(",") if item.strip())
    return ACRWebhookConfig(
        secret=os.environ.get("ACR_WEBHOOK_SECRET", ""),
        expected_services=services or frozenset({"api", "web"}),
    )


def _service_from_repository(repository_name: str) -> str:
    if repository_name.endswith("-api"):
        return "api"
    if repository_name.endswith("-web"):
        return "web"
    raise ValueError(f"Unsupported ACR repository: {repository_name}")


def _first_string(payload: dict[str, Any], paths: list[tuple[str, ...]]) -> str | None:
    for path in paths:
        value: Any = payload
        for part in path:
            if not isinstance(value, dict) or part not in value:
                value = None
                break
            value = value[part]
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _load_state(state_path: Path) -> dict[str, Any]:
    if not state_path.exists():
        return {"tags": {}}
    try:
        return json.loads(state_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"tags": {}}


def _write_state_atomic(state_path: Path, state: dict[str, Any]) -> None:
    state_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        dir=state_path.parent,
        delete=False,
    ) as temp_file:
        json.dump(state, temp_file, ensure_ascii=False, indent=2, sort_keys=True)
        temp_name = temp_file.name
    Path(temp_name).replace(state_path)
