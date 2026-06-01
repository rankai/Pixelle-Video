"""Small file cache for expensive IP broadcast generation steps."""

import hashlib
import json
import shutil
from pathlib import Path
from typing import Any

from pixelle_video.utils.os_util import get_data_path


def file_sha256(path: str) -> str:
    target = Path(path)
    if not target.exists():
        return ""
    digest = hashlib.sha256()
    with target.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def stable_hash(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def cache_path(namespace: str, key: str, suffix: str) -> str:
    directory = Path(get_data_path("ip_broadcast_cache", namespace))
    directory.mkdir(parents=True, exist_ok=True)
    clean_suffix = suffix if suffix.startswith(".") else f".{suffix}"
    return str(directory / f"{key}{clean_suffix}")


def existing_cache_path(namespace: str, key: str, suffix: str) -> str | None:
    path = Path(cache_path(namespace, key, suffix))
    return str(path) if path.exists() else None


def store_cache_file(source_path: str, namespace: str, key: str, suffix: str) -> str:
    target = cache_path(namespace, key, suffix)
    if Path(source_path).resolve() != Path(target).resolve():
        shutil.copy2(source_path, target)
    return target
