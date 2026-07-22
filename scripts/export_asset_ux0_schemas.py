#!/usr/bin/env python3
"""Export reviewed UX-0 Pydantic contracts as JSON Schema artifacts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from api.schemas.asset_library_ux0 import (
    AssetViewModelContract,
    CursorEnvelope,
    DeferredUploadCreateRequest,
    DeferredUploadResponse,
    FinalizeUploadRequest,
    LibraryPageContract,
    PickerContextContract,
    TemplateLayoutContract,
    VoiceProfile,
)

SCHEMAS = {
    "asset-view-model": AssetViewModelContract,
    "picker-context": PickerContextContract,
    "template-layout-contract-v2": TemplateLayoutContract,
    "voice-profile": VoiceProfile,
    "deferred-upload-create": DeferredUploadCreateRequest,
    "deferred-upload-finalize": FinalizeUploadRequest,
    "deferred-upload-response": DeferredUploadResponse,
    "library-cursor": CursorEnvelope,
    "library-page-facets": LibraryPageContract,
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path("docs/schemas"))
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    for name, model in SCHEMAS.items():
        output = args.output_dir / f"{name}.schema.json"
        output.write_text(
            json.dumps(model.model_json_schema(), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
