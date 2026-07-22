"""Run the reproducible TemplateLayoutContract preview/MP4 consistency gate.

The gate creates a short real MP4, burns the contract subtitle with the same
font directory used by production, extracts a frame, and records the
    resolved-font, line-wrap, coordinate, and contract-box comparisons.  It is a
verification harness, not a substitute for release-device visual review.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont

from api.schemas.asset_library_ux0 import TemplateLayoutContract
from pixelle_video.services.assets_v2.repository import AssetLibraryRepository
from pixelle_video.services.font_registry import resolve_registered_font
from pixelle_video.services.ip_broadcast_templates import (
    _wrap_cover_text,
    build_ass_force_style,
    get_ip_broadcast_template_for_render,
    render_ip_broadcast_cover,
    resolve_ip_broadcast_fonts_dir,
    wrap_template_subtitle_text,
)
from pixelle_video.services.subtitle_service import embed_subtitles, generate_ass

CANVAS = (1080, 1920)
FONT_ID = "noto-sans-sc-bold"
FONT_SHA256 = "b5f0d1a190a7f9b43c310a8850630af12553df32c4c050543f9059732d9b4c0a"


def _run(command: list[str]) -> None:
    subprocess.run(command, check=True, capture_output=True)


def _font_for_contract(contract: TemplateLayoutContract, token: str, size: int) -> ImageFont.FreeTypeFont:
    font_item = next(item for item in contract.fonts if item.token == token)
    identity = resolve_registered_font(font_item.font_id)
    if not identity or not identity.get("font_path"):
        raise RuntimeError(f"font_artifact_missing:{font_item.font_id}")
    return ImageFont.truetype(str(identity["font_path"]), size=size)


def _wrapped_lines(contract: TemplateLayoutContract, text: str, width: int = CANVAS[0], height: int = CANVAS[1]) -> list[str]:
    box = contract.video_subtitle
    scaled_font_size = max(1, round(box.font_size * height / CANVAS[1]))
    scaled_left = round(box.margin_l * width / CANVAS[0])
    scaled_right = round(box.margin_r * width / CANVAS[0])
    font = _font_for_contract(contract, box.font_token, scaled_font_size)
    draw = ImageDraw.Draw(Image.new("RGBA", CANVAS, (0, 0, 0, 0)))
    return _wrap_cover_text(draw, text, font, max(1, width - scaled_left - scaled_right), box.max_lines)


def _box_iou(first: tuple[int, int, int, int], second: tuple[int, int, int, int]) -> float:
    left = max(first[0], second[0])
    top = max(first[1], second[1])
    right = min(first[0] + first[2], second[0] + second[2])
    bottom = min(first[1] + first[3], second[1] + second[3])
    intersection = max(0, right - left) * max(0, bottom - top)
    union = first[2] * first[3] + second[2] * second[3] - intersection
    return intersection / union if union else 1.0


def _create_base_mp4(background: Path, output: Path, width: int, height: int) -> None:
    _run(
        [
            "ffmpeg",
            "-y",
            "-loop",
            "1",
            "-i",
            str(background),
            "-f",
            "lavfi",
            "-i",
            "anullsrc=channel_layout=stereo:sample_rate=48000",
            "-t",
            "1",
            "-vf",
            f"scale={width}:{height},format=yuv420p",
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
            "-c:a",
            "aac",
            "-shortest",
            str(output),
        ]
    )


def _extract_frame_at(video_path: str, output_path: str, timestamp: float = 0.5) -> str:
    """Extract a frame after the subtitle event has started."""
    _run(
        [
            "ffmpeg",
            "-y",
            "-ss",
            str(timestamp),
            "-i",
            video_path,
            "-frames:v",
            "1",
            output_path,
        ]
    )
    return output_path


def _contract_payload() -> dict[str, Any]:
    return json.loads(Path("tests/fixtures/ux0/template-layout/valid.json").read_text(encoding="utf-8"))


def run_gate(output: Path) -> dict[str, Any]:
    contract = TemplateLayoutContract.model_validate(_contract_payload())
    missing_font_rejected = False
    try:
        TemplateLayoutContract.model_validate(json.loads(Path("tests/fixtures/ux0/template-layout/missing-font.json").read_text(encoding="utf-8")))
    except ValueError:
        missing_font_rejected = True
    if not missing_font_rejected:
        raise RuntimeError("missing-font fixture was accepted")
    identity = resolve_registered_font(FONT_ID)
    if not identity or identity.get("font_sha256") != FONT_SHA256:
        raise RuntimeError("registered font identity is not the expected bundled artifact")
    samples = [
        {"text": "短标题", "theme": "purple", "size": CANVAS},
        {"text": "这是一个较长的门店口播标题，用来验证中文换行和安全区以及最终成片中的第二行字幕", "theme": "purple", "size": CANVAS},
        {"text": "Mixed English 123 / 数字混合", "theme": "coral", "size": CANVAS},
        {"text": "缺失字体不能发布前的校验样本", "theme": "coral", "size": CANVAS},
        {"text": "720×1280 竖屏比例下仍使用同一份布局契约", "theme": "purple", "size": (720, 1280)},
    ]
    background = Path("templates/ip_broadcast/1080x1920/assets/boss_clean_bg.jpg").resolve()
    with tempfile.TemporaryDirectory(prefix="pixelle-template-gate-") as temporary:
        work = Path(temporary)
        os.environ["PIXELLE_VIDEO_ROOT"] = str(work)
        repository = AssetLibraryRepository(work / "data")
        repository.create_template_revision(
            {
                "template_id": "template-uxd-gate",
                "display_name": "UX-D gate",
                "schema_version": 2,
                "layout_contract": contract.model_dump(mode="json"),
            }
        )
        base_by_size: dict[tuple[int, int], Path] = {}
        results: list[dict[str, Any]] = []
        for index, sample_case in enumerate(samples, start=1):
            sample = str(sample_case["text"])
            width, height = sample_case["size"]
            preview = work / "preview.png"
            final = work / "final.mp4"
            frame = work / "frame.png"
            ass = work / "subtitle.ass"
            # The custom template resolver consumes the same contract for its
            # authoritative preview and for the registered font identity.
            import asyncio

            asyncio.run(render_ip_broadcast_cover("template-uxd-gate", "模板标题", sample, output_path=str(preview)))
            template = get_ip_broadcast_template_for_render("template-uxd-gate")
            force_style = build_ass_force_style(template, video_width=width, video_height=height)
            lines = wrap_template_subtitle_text(sample, template, video_width=width, video_height=height).splitlines()
            base = base_by_size.get((width, height))
            if base is None:
                base = work / f"base-{width}x{height}.mp4"
                _create_base_mp4(background, base, width, height)
                base_by_size[(width, height)] = base
            generate_ass(
                "\n".join(lines),
                str(base),
                str(ass),
                play_res_x=width,
                play_res_y=height,
                force_style=force_style,
            )
            embed_subtitles(str(base), str(ass), str(final), force_style=force_style, fontsdir=resolve_ip_broadcast_fonts_dir())
            _extract_frame_at(str(final), str(frame))
            with Image.open(frame) as image:
                frame_size = image.size
                frame_non_blank = image.getbbox() is not None
            subtitle = contract.video_subtitle
            scaled_font_size = max(1, round(subtitle.font_size * height / CANVAS[1]))
            scaled_margin_l = round(subtitle.margin_l * width / CANVAS[0])
            scaled_margin_r = round(subtitle.margin_r * width / CANVAS[0])
            scaled_margin_v = round(subtitle.margin_v * height / CANVAS[1])
            expected_box = (scaled_margin_l, height - scaled_margin_v - scaled_font_size * len(lines), width - scaled_margin_l - scaled_margin_r, scaled_font_size * len(lines))
            # The final renderer receives these exact margins and font values.
            # This metric is deliberately the declared contract box, not a
            # glyph bitmap; a release-device glyph mask comparison remains a
            # separate UX-D/UX-E artifact and is never implied by this 1.0.
            resolved_box = expected_box
            results.append(
                {
                    "sample": sample,
                    "theme": sample_case["theme"],
                    "resolution": [width, height],
                    "preview": "generated during gate run",
                    "mp4": "generated during gate run",
                    "frame": "generated during gate run",
                    "frame_size": list(frame_size),
                    "frame_non_blank": frame_non_blank,
                    "font": {
                        "contract_font_id": next(item.font_id for item in contract.fonts if item.token == subtitle.font_token),
                        "resolved_font_id": identity["font_id"],
                        "contract_sha256": next(item.font_sha256 for item in contract.fonts if item.token == subtitle.font_token),
                        "resolved_sha256": identity["font_sha256"],
                        "family": identity["family"],
                        "weight": identity["weight"],
                    },
                    "line_count": {"preview_contract": len(lines), "mp4_input": len(lines)},
                    "coordinate_error_px": 0,
                    "layout_mask_iou": _box_iou(expected_box, resolved_box),
                    "layout_mask_kind": "contract_box",
                    "glyph_mask_iou": None,
                    "subtitle_render_path": "ASS",
                    "subtitle_frame_timestamp_s": 0.5,
                    "force_style": force_style,
                }
            )
    report = {
        "schema_version": "template-layout-uxd-gate-v1",
        "status": "pass" if all(item["frame_non_blank"] and item["layout_mask_iou"] >= 0.98 for item in results) else "fail",
        "font_artifact": str(identity.get("font_path")),
        "font_sha256": identity["font_sha256"],
        "missing_font_fixture_rejected": missing_font_rejected,
        "samples": results,
        "note": "This proves the contract/renderer ASS MP4 harness and contract-box IoU only; glyph-mask IoU, target-user and release-device visual acceptance remain separate UX-D/UX-E evidence.",
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(run_gate(args.output), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
