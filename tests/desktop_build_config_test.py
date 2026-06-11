from pathlib import Path


def test_desktop_production_build_does_not_emit_source_maps_by_default():
    source = Path("desktop/vite.config.ts").read_text()

    assert "sourcemap: false" in source
