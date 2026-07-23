import platform
from pathlib import Path

from desktop.scripts.build_sidecar import data_separator

ROOT = Path(__file__).resolve().parents[1]


def test_frozen_sidecar_runs_the_constructed_asgi_app_directly():
    source = (ROOT / "api" / "app.py").read_text(encoding="utf-8")

    assert 'server_app = app if getattr(sys, "frozen", False)' in source
    assert 'uvicorn.run(\n        server_app,' in source


def test_sidecar_build_bundles_runtime_contract_schemas():
    source = (ROOT / "desktop" / "scripts" / "build_sidecar.py").read_text(encoding="utf-8")

    assert '"--add-data"' in source
    assert "docs/contracts" in source
    assert data_separator() == (";" if platform.system().lower() == "windows" else ":")


def test_frozen_sidecar_startup_banner_is_windows_console_safe():
    source = (ROOT / "api" / "app.py").read_text(encoding="utf-8")

    assert "Pixelle-Video API Server" in source
    assert "UnicodeEncodeError" in source
    assert "╔" not in source
    assert "║" not in source
    assert "╚" not in source
