"""Trusted local media preflight for PUB-2.

The API never accepts arbitrary paths from the browser.  This module is used
after a trusted session/artifact resolver has produced a local path, and it
re-resolves plus re-hashes immediately before a browser step.
"""

from __future__ import annotations

import hashlib
import mimetypes
import os
from pathlib import Path
from typing import Iterable

from .core_models import MediaManifest


class MediaPreflightError(ValueError):
    def __init__(self, code: str, message: str | None = None):
        super().__init__(message or code)
        self.code = code


def default_media_roots() -> tuple[Path, ...]:
    cwd = Path.cwd().resolve()
    return tuple(
        root
        for root in (
            cwd / "data",
            cwd / "output",
            cwd / "temp",
            Path("/tmp").resolve(),
            Path("/private/tmp").resolve(),
        )
    )


def resolve_trusted_path(path_value: str | os.PathLike[str], *, roots: Iterable[Path] | None = None) -> Path:
    candidate = Path(path_value).expanduser()
    if not candidate.is_absolute():
        candidate = Path.cwd() / candidate
    if candidate.is_symlink():
        raise MediaPreflightError("MEDIA_SYMLINK_REJECTED")
    try:
        resolved = candidate.resolve(strict=True)
    except FileNotFoundError as exc:
        raise MediaPreflightError("MEDIA_MISSING") from exc
    allowed_roots = tuple(root.resolve() for root in (roots or default_media_roots()))
    if not any(_is_relative_to(resolved, root) for root in allowed_roots):
        raise MediaPreflightError("MEDIA_PATH_UNTRUSTED")
    for root in allowed_roots:
        if _is_relative_to(resolved, root):
            current = candidate.absolute()
            while current != root and root in current.parents:
                if current.is_symlink():
                    raise MediaPreflightError("MEDIA_SYMLINK_REJECTED")
                current = current.parent
            break
    return resolved


def preflight_media(
    path_value: str | os.PathLike[str],
    *,
    kind: str,
    path_token: str | None = None,
    roots: Iterable[Path] | None = None,
) -> MediaManifest:
    path = resolve_trusted_path(path_value, roots=roots)
    if not path.is_file() or path.stat().st_size <= 0:
        raise MediaPreflightError("MEDIA_INVALID")
    suffix = path.suffix.lower()
    if kind == "video" and suffix not in {".mp4", ".mov", ".m4v"}:
        raise MediaPreflightError("MEDIA_INVALID")
    if kind == "cover" and suffix not in {".png", ".jpg", ".jpeg", ".webp"}:
        raise MediaPreflightError("MEDIA_INVALID")
    if kind == "video" and b"ftyp" not in path.read_bytes()[:4096]:
        raise MediaPreflightError("MEDIA_PROBE_FAILED")
    if kind == "cover":
        header = path.read_bytes()[:16]
        if not (header.startswith(b"\x89PNG\r\n\x1a\n") or header.startswith(b"\xff\xd8\xff")):
            raise MediaPreflightError("MEDIA_PROBE_FAILED")
    digest = _sha256(path)
    mime = mimetypes.guess_type(path.name)[0] or ("video/mp4" if kind == "video" else "image/png")
    token = path_token or f"asset_{digest[:16]}"
    if not token.startswith("asset_") or "/" in token or "\\" in token:
        raise MediaPreflightError("MEDIA_PATH_TOKEN_INVALID")
    return MediaManifest(
        sha256=f"sha256:{digest}",
        size_bytes=path.stat().st_size,
        mime_type=mime,
        path_token=token,
    )


def verify_manifest(path_value: str | os.PathLike[str], manifest: MediaManifest, *, roots: Iterable[Path] | None = None) -> Path:
    path = resolve_trusted_path(path_value, roots=roots)
    if path.stat().st_size != manifest.size_bytes or f"sha256:{_sha256(path)}" != manifest.sha256:
        raise MediaPreflightError("MEDIA_HASH_MISMATCH")
    return path


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False
