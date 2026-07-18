from pathlib import Path

SOURCE = Path("desktop/src/features/dashboard/DashboardView.tsx").read_text()


def test_home_readiness_reuses_existing_asset_tab_navigation():
    assert "onAssetTab" in SOURCE
    for tab in ["videos", "images", "voices", "portraits", "brands"]:
        assert f'onAssetTab("{tab}")' in SOURCE


def test_home_readiness_uses_production_ready_and_exact_asset_tabs():
    production_ready = SOURCE[SOURCE.index("const productionReady") : SOURCE.index("const stage")]

    assert "configReady" in production_ready
    assert "assets.voices > 0" in production_ready
    assert "assets.portraits > 0" in production_ready
    assert "assets.templates > 0" in production_ready
    assert "assets.videos" not in production_ready
    assert "assets.images" not in production_ready


def test_home_is_project_first_instead_of_metric_card_grid():
    assert "continue-project-panel" in SOURCE
    assert "project-progress-rail" in SOURCE
    assert "最近项目" in SOURCE
    assert "生产队列" in SOURCE
    assert "home-metrics" not in SOURCE


def test_dashboard_exposes_asset_production_and_publish_entry_points():
    assert "企业资产" in SOURCE
    assert "新建口播视频" in SOURCE
    assert "发布账号" in SOURCE
    assert "启动自检" in SOURCE
