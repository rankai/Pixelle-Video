import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_rollout_privacy_and_rollback_fixtures_are_safe():
    entry = json.loads((ROOT / "docs/contracts/publishing/program-rollout-entry.contract.json").read_text())
    rollback = json.loads((ROOT / "docs/contracts/publishing/fixtures/v1-rollback-smoke.json").read_text())

    assert entry["privacy_requirements"]["local_only"] is True
    assert entry["privacy_requirements"]["upload_default"] is False
    assert entry["privacy_requirements"]["raw_screenshot_default"] is False
    assert rollback == {
        "schema_version": 1,
        "v2_flag_before": True,
        "v2_flag_after": False,
        "profile_preserved": True,
        "v1_material_copy_available": True,
        "duplicate_uploads": 0,
        "history_readable": True,
        "production_writes": 0,
    }


def test_diagnostics_redaction_is_explicit_in_router_source():
    source = (ROOT / "api/routers/desktop.py").read_text()
    assert '"raw_path_redacted": True' in source
    assert "输出目录可写。" in source
    assert "str(output_dir)" not in source
