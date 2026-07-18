#!/usr/bin/env python3
"""Run the deterministic SQL cursor benchmark for the UX-E performance gate."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from pixelle_video.services.assets_v2.repository import AssetLibraryRepository


def benchmark(root: Path, count: int, page_size: int = 60) -> dict[str, int | float | str]:
    repository = AssetLibraryRepository(root)
    with repository._lock, repository._connect() as connection:  # noqa: SLF001 - benchmark fixture
        for index in range(count):
            timestamp = f"2026-07-18T00:{index // 60:02d}:{index % 60:02d}+00:00"
            connection.execute(
                "INSERT INTO media_assets(asset_id, media_kind, name, description, source, status, created_at, updated_at) VALUES (?, 'image', ?, '', 'imported', 'ready', ?, ?)",
                (f"perf-{index:05d}", f"性能素材 {index:05d}", timestamp, timestamp),
            )
    start = time.perf_counter()
    first = repository.list_library_page(kind="image", page_size=page_size, sort="name")
    first_ms = (time.perf_counter() - start) * 1000
    pages = 1
    cursor = first["next_cursor"]
    while cursor:
        page = repository.list_library_page(kind="image", page_size=page_size, sort="name", cursor=cursor)
        cursor = page["next_cursor"]
        pages += 1
    return {"asset_count": count, "page_size": page_size, "pages": pages, "first_page_ms": round(first_ms, 2), "status": "pass" if pages == (count + page_size - 1) // page_size else "fail"}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--count", type=int, nargs="+", default=[1000, 5000])
    args = parser.parse_args()
    reports = []
    for count in args.count:
        reports.append(benchmark(args.output.parent / f".asset-ux4-perf-{count}", count))
    args.output.write_text(json.dumps({"schema_version": "asset-center-ux4-performance-v1", "reports": reports}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(reports, ensure_ascii=False))
    return 0 if all(report["status"] == "pass" for report in reports) else 1


if __name__ == "__main__":
    raise SystemExit(main())

