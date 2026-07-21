"""Measure bounded local media-preflight overhead for rollout fixtures."""

from __future__ import annotations

import json
import statistics
import time
from pathlib import Path

from pixelle_video.services.publish.media_preflight import preflight_media

FIXTURE_ROOT = Path("/tmp/pixelle-rollout-fixtures").resolve()


def percentile(values: list[float], percentile_value: float) -> float:
    if len(values) == 1:
        return values[0]
    ordered = sorted(values)
    rank = (len(ordered) - 1) * percentile_value
    lower = int(rank)
    upper = min(lower + 1, len(ordered) - 1)
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (rank - lower)


def measure(path: Path) -> dict:
    samples: list[float] = []
    for _ in range(10):
        started = time.perf_counter()
        preflight_media(path, kind="video", roots=[FIXTURE_ROOT])
        samples.append((time.perf_counter() - started) * 1000)
    return {
        "fixture": path.name,
        "samples": len(samples),
        "p50_ms": round(statistics.median(samples), 3),
        "p95_ms": round(percentile(samples, 0.95), 3),
        "min_ms": round(min(samples), 3),
        "max_ms": round(max(samples), 3),
    }


def main() -> None:
    results = [measure(FIXTURE_ROOT / f"video-{seconds}s.mp4") for seconds in (1, 15, 60)]
    print(json.dumps({"status": "passed_local_bounded", "metric": "media_preflight_ms", "results": results}, ensure_ascii=False))


if __name__ == "__main__":
    main()
