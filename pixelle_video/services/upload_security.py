"""Shared upload and asset-library safety helpers."""

import json
import os
from pathlib import Path
from typing import Any


def normalize_extension(ext: str, allowed_extensions: set[str]) -> str:
    clean_ext = ext.lstrip(".").lower()
    if not clean_ext or clean_ext != Path(clean_ext).name or any(sep in clean_ext for sep in ("/", "\\")):
        raise ValueError(f"Invalid file extension: {ext}")
    if clean_ext not in allowed_extensions:
        raise ValueError(f"Unsupported file extension: {clean_ext}")
    return clean_ext


def validate_file_size(file_bytes: bytes, max_bytes: int, label: str) -> None:
    if len(file_bytes) > max_bytes:
        raise ValueError(f"{label} exceeds size limit: {len(file_bytes)} > {max_bytes}")


def atomic_write_json(path: Path, payload: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f"{path.name}.tmp")
    tmp_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    os.replace(tmp_path, path)


def safe_library_child(library_dir: Path, filename: str) -> Path | None:
    if not filename or filename != Path(filename).name:
        return None
    candidate = (library_dir / filename).resolve()
    library_root = library_dir.resolve()
    try:
        candidate.relative_to(library_root)
    except ValueError:
        return None
    return candidate
