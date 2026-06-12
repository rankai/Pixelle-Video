from pathlib import Path


SOURCE = Path("desktop/src/App.tsx").read_text()


def test_home_readiness_reuses_existing_asset_tab_navigation():
    start = SOURCE.index("{view === \"home\"")
    app_render = SOURCE[start : SOURCE.index("{view === \"assets\"", start)]

    assert "onAssetTab={openAssetTab}" in app_render
    assert "goToAssetTab" not in SOURCE


def test_home_readiness_uses_production_ready_and_exact_asset_tabs():
    home_view = SOURCE[SOURCE.index("function HomeView(") : SOURCE.index("function SystemStatusPanel")]
    production_ready = home_view[
        home_view.index("const productionReady") : home_view.index("const assetCount")
    ]

    assert "configReady" in home_view
    assert "productionReady" in home_view
    assert "assets.videos.length > 0" not in production_ready
    assert 'onAssetTab("voices")' in home_view
    assert 'onAssetTab("portraits")' in home_view
    assert 'onAssetTab("templates")' in home_view
    assert 'onAssetTab("videos")' in home_view
    assert "商家口播声音" in home_view
    assert "出镜数字人形象" in home_view


def test_home_video_assets_are_recommended_not_blocking():
    home_view = SOURCE[SOURCE.index("function HomeView(") : SOURCE.index("function SystemStatusPanel")]
    required_block = home_view[
        home_view.index("const requiredReadinessItems") : home_view.index("const recommendedReadinessItems")
    ]
    recommended_block = home_view[
        home_view.index("const recommendedReadinessItems") : home_view.index("const readinessItems")
    ]

    assert "assets.videos.length > 0" not in required_block
    assert "assets.videos.length > 0" in recommended_block
    assert "不影响生成" in recommended_block
    assert "recommended: true" in recommended_block


def test_system_status_panel_prioritizes_missing_actions_without_crowding():
    panel = SOURCE[SOURCE.index("function SystemStatusPanel(") : SOURCE.index("function QuickAccessCard")]

    assert "visibleMissingItems" in panel
    assert "requiredItems.filter" in panel
    assert "recommendedMissing" in panel
    assert "推荐补充" in panel
    assert "system-status-action" in panel
    assert "先补齐：" in panel
    assert "displayItems[visibleMissingItems.length]?.onClick" in panel
