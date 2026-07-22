"""Generate isolated PUB-0 media fixtures; never writes to the project data root."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
from pathlib import Path


def encode(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def ffmpeg(output: Path, *args: str) -> None:
    subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *args, str(output)],
        check=True,
    )


def generate(output_dir: Path) -> dict:
    if shutil.which("ffmpeg") is None:
        raise RuntimeError("ffmpeg is required to generate media fixtures")
    output_dir.mkdir(parents=True, exist_ok=True)
    valid_video = output_dir / "valid_mp4_h264.mp4"
    ffmpeg(valid_video, "-f", "lavfi", "-i", "color=c=blue:s=16x16:r=10", "-t", "0.2", "-pix_fmt", "yuv420p", "-movflags", "+faststart")
    missing_moov = output_dir / "missing_moov_atom.mp4"
    missing_moov.write_bytes(b"not-a-video")
    zero_byte = output_dir / "zero_byte.mp4"
    zero_byte.write_bytes(b"")
    fake_extension = output_dir / "fake_extension.mp4"
    fake_extension.write_text("<html>not media</html>")
    valid_cover = output_dir / "valid_cover_png.png"
    ffmpeg(valid_cover, "-f", "lavfi", "-i", "color=c=white:s=1080x1440", "-frames:v", "1", "-vf", "format=rgb24")
    invalid_cover = output_dir / "invalid_cover_dimensions.png"
    ffmpeg(invalid_cover, "-f", "lavfi", "-i", "color=c=white:s=1x1", "-frames:v", "1")
    files = [valid_video, missing_moov, zero_byte, fake_extension, valid_cover, invalid_cover]
    return {"generated_files": [{"name": path.name, "sha256": encode(path), "bytes": path.stat().st_size} for path in files]}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(generate(args.output_dir), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
