"""Validate a Windows desktop installer and sidecar before artifact upload."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def _file_record(path: Path, *, expected_suffix: str | None = None) -> dict[str, object]:
    if not path.is_file():
        raise SystemExit(f"artifact_missing:{path}")
    if path.stat().st_size <= 0:
        raise SystemExit(f"artifact_empty:{path}")
    if expected_suffix and path.suffix.lower() != expected_suffix:
        raise SystemExit(f"artifact_suffix_invalid:{path}")
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return {
        "path": str(path),
        "size_bytes": path.stat().st_size,
        "sha256": digest.hexdigest(),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--installer", type=Path, required=True)
    parser.add_argument("--sidecar", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    installer = _file_record(args.installer, expected_suffix=".exe")
    sidecar = _file_record(args.sidecar, expected_suffix=".exe")
    if "x86_64-pc-windows-msvc" not in args.sidecar.name:
        raise SystemExit(f"sidecar_target_invalid:{args.sidecar.name}")
    result = {
        "schema_version": 1,
        "platform": "windows",
        "target": "x86_64-pc-windows-msvc",
        "installer": installer,
        "sidecar": sidecar,
        "install_test": "pending_windows_manual_install",
    }
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
