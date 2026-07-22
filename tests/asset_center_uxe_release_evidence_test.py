import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKET = ROOT / "docs/migrations/asset-center-uxe-release-evidence-template-2026-07-18.json"


def test_release_evidence_template_is_explicitly_pending_and_rollout_off():
    packet = json.loads(PACKET.read_text(encoding="utf-8"))
    assert packet["status"] == "pending_external_evidence"
    assert packet["review"]["default_rollout_authorized"] is False


def test_release_evidence_validator_rejects_unfilled_template():
    result = subprocess.run(
        [sys.executable, "scripts/validate_asset_center_uxe_release_evidence.py", "--input", str(PACKET)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1
    report = json.loads(result.stdout)
    assert report["status"] == "pending_external_evidence"
    assert report["default_rollout_authorized"] is False
    assert not all(report["checks"].values())
