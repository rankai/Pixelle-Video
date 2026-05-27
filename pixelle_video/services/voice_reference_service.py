"""Persistent voice reference audio library for IP broadcast voice cloning."""

import json
import os
import threading
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

from loguru import logger

from pixelle_video.services.upload_security import (
    atomic_write_json,
    normalize_extension,
    safe_library_child,
    validate_file_size,
)
from pixelle_video.utils.os_util import get_data_path

SUPPORTED_VOICE_REFERENCE_EXTENSIONS = {"mp3", "wav", "flac", "m4a"}
MAX_VOICE_REFERENCE_BYTES = 100 * 1024 * 1024


@dataclass
class VoiceReferenceInfo:
    reference_id: str
    name: str
    filename: str
    created_at: str

    def asset_path(self) -> str:
        return get_data_path("voice_references", self.filename)

    def exists(self) -> bool:
        return os.path.exists(self.asset_path())


class VoiceReferenceService:
    """Manages reusable reference audio files in data/voice_references/."""

    def __init__(self):
        self._references_dir = Path(get_data_path("voice_references"))
        self._manifest_path = self._references_dir / "voice_references.json"
        self._references_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def _load_manifest(self) -> list[dict]:
        if not self._manifest_path.exists():
            return []
        try:
            return json.loads(self._manifest_path.read_text(encoding="utf-8"))
        except Exception as e:
            logger.warning(f"Failed to load voice references manifest: {e}")
            return []

    def _save_manifest(self, references: list[dict]) -> None:
        atomic_write_json(self._manifest_path, references)

    def list_references(self) -> list[VoiceReferenceInfo]:
        with self._lock:
            raw = self._load_manifest()
            result = []
            for item in raw:
                try:
                    info = VoiceReferenceInfo(**item)
                except TypeError:
                    continue
                if info.exists():
                    result.append(info)
            if len(result) != len(raw):
                self._save_manifest([asdict(item) for item in result])
        return result

    def save_reference(self, name: str, audio_bytes: bytes, ext: str) -> VoiceReferenceInfo:
        try:
            clean_ext = normalize_extension(ext, SUPPORTED_VOICE_REFERENCE_EXTENSIONS)
        except ValueError as e:
            if "Unsupported file extension" in str(e):
                raise ValueError(
                    f"Unsupported voice reference extension: {ext.lstrip('.').lower()}"
                ) from e
            raise
        validate_file_size(audio_bytes, MAX_VOICE_REFERENCE_BYTES, "Voice reference")

        reference_id = uuid.uuid4().hex[:12]
        filename = f"{reference_id}.{clean_ext}"
        dest = self._references_dir / filename
        info = VoiceReferenceInfo(
            reference_id=reference_id,
            name=name,
            filename=filename,
            created_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        )

        dest.write_bytes(audio_bytes)
        try:
            with self._lock:
                references = self._load_manifest()
                references.append(asdict(info))
                self._save_manifest(references)
        except Exception:
            dest.unlink(missing_ok=True)
            raise

        logger.info(f"Voice reference saved: {name} ({filename})")
        return info

    def delete_reference(self, reference_id: str) -> bool:
        with self._lock:
            references = self._load_manifest()
            updated = [item for item in references if item["reference_id"] != reference_id]
            if len(updated) == len(references):
                return False
            removed = next(item for item in references if item["reference_id"] == reference_id)
            self._save_manifest(updated)

        audio_path = safe_library_child(self._references_dir, removed.get("filename", ""))
        if audio_path:
            audio_path.unlink(missing_ok=True)
        logger.info(f"Voice reference deleted: {reference_id}")
        return True

    def get_reference_path(self, reference_id: str) -> str | None:
        with self._lock:
            manifest = self._load_manifest()
        for item in manifest:
            if item["reference_id"] == reference_id:
                path = safe_library_child(self._references_dir, item.get("filename", ""))
                if not path:
                    return None
                return str(path) if path.exists() else None
        return None
