from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_frozen_sidecar_runs_the_constructed_asgi_app_directly():
    source = (ROOT / "api" / "app.py").read_text(encoding="utf-8")

    assert 'server_app = app if getattr(sys, "frozen", False)' in source
    assert 'uvicorn.run(\n        server_app,' in source
